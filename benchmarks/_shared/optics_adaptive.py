"""Shared plumbing for the four Optics ``adaptive_*`` adaptive-optics benchmarks.

Historically each of those tasks did::

    candidate_fn = load_callable(candidate_path, "compute_dm_commands")
    ...
    cmd = candidate_fn(slopes, reconstructor, control_model, prev_applied, ...)

i.e. the candidate was ``exec_module``-ed straight into the scoring process and
then called once per simulation step. That is the exact process-boundary hole
``benchmarks/_shared/candidate_sandbox.py`` exists to close: a candidate sharing
the scorer's interpreter can monkeypatch numpy, the metric functions, the
reference controller, or ``json.dump`` and write its own score.

The conversion implemented here rests on one structural observation about all
four evaluators: **the disturbance stream never depends on the controller
output.** Phase screens, WFS slopes and sensor faults are drawn from the
evaluator's ``Generator`` *before* the controller is called in every iteration,
and nothing after the call consumes randomness. The only feedback path into the
controller is ``prev_applied``, which is a deterministic recurrence over the
controller's own past commands.

So the loop can be cut in two without changing a single number:

1. the scorer generates the whole disturbance stream up front and ships only the
   *observations* (slopes) to the candidate -- never the ground-truth phase;
2. the candidate runs alone in a subprocess, replays the documented actuator
   recurrence to reconstruct ``prev_applied`` itself, and returns a
   ``(n_steps, n_act)`` command matrix as data;
3. the scorer re-derives ``applied`` from the returned commands with its own copy
   of the recurrence, and recomputes every metric and the final score itself.

Step 3 is what makes step 2 harmless: whatever the candidate believed about the
plant, the scorer trusts only the commands and re-simulates. A candidate that
reports metrics, or that lies about its own internal state, changes nothing.

Invariants callers must preserve (mirrors ``candidate_sandbox``):

1. Import this module -- and every scoring dependency (numpy, aotools, the
   reference controller) -- before running the candidate.
2. Never read a score/metric field out of the candidate's output. Only
   ``commands`` is consumed, and only after ``validate_commands``.
3. A crash, a timeout, a missing ``submission.npz`` or a command matrix that
   fails validation is a hard rejection: the evaluator must not write
   ``metrics.json`` and must exit non-zero, so ``frontier_eval/parse_result.py``
   records ``combined_score = -1e18`` / ``valid = 0``.
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

# aotools expects numpy.math, which is absent in newer NumPy releases.
if not hasattr(np, "math"):  # pragma: no cover - environment shim
    np.math = math  # type: ignore[attr-defined]

import aotools
from aotools import fouriertransform

__all__ = [
    "CandidateRejected",
    "INVALID_COMBINED_SCORE",
    "build_optics_system",
    "clip01",
    "utility_lower_better",
    "utility_higher_better",
    "weighted_score",
    "strehl_from_residual",
    "npz_bytes",
    "pack_control_model",
    "run_candidate_controller",
    "validate_commands",
    "save_comparison_plots",
    "write_rejection",
    "add_common_cli_args",
]

INVALID_COMBINED_SCORE = -1e18

#: Name of the file the candidate subprocess must produce in its cwd.
SUBMISSION_NAME = "submission.npz"
#: Name of the problem file the scorer stages into the candidate's cwd.
PROBLEM_NAME = "problem.npz"
#: Optional pickled sklearn helper (fault-tolerant fusion task only).
ANOMALY_MODEL_NAME = "anomaly_model.pkl"
#: Key holding the candidate's command matrix inside ``submission.npz``.
COMMANDS_KEY = "commands"
#: Prefix used to flatten ``control_model`` entries into the npz namespace.
CONTROL_MODEL_PREFIX = "cm__"

# Hard cap on anything the candidate writes; exceeding it kills the child with
# SIGXFSZ, which surfaces as a non-zero return code (i.e. a rejection) instead
# of the scorer trying to read a multi-gigabyte "submission" into memory.
_CANDIDATE_FSIZE_BYTES = 512 * 1024 * 1024


class CandidateRejected(Exception):
    """The candidate produced nothing the scorer is willing to score."""


def find_repo_root() -> Path:
    """Locate the repository root, preferring the harness-provided env var."""
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    # This file lives at <repo>/benchmarks/_shared/, so two levels up is the root
    # even when the tree has been relocated without the marker directories.
    return Path(__file__).resolve().parents[2]


def _import_sandbox():
    shared_dir = str(Path(__file__).resolve().parent)
    if shared_dir not in sys.path:
        sys.path.insert(0, shared_dir)
    import candidate_sandbox  # noqa: PLC0415

    return candidate_sandbox


sandbox = _import_sandbox()


# --------------------------------------------------------------------------- #
# Scoring utilities (verbatim semantics of the four original evaluators).
# --------------------------------------------------------------------------- #
def clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def utility_lower_better(value: float, good: float, bad: float) -> float:
    return clip01((bad - value) / (bad - good + 1e-12))


def utility_higher_better(value: float, good: float, bad: float) -> float:
    return clip01((value - bad) / (good - bad + 1e-12))


def weighted_score(utilities: dict[str, float], weights: dict[str, float]) -> float:
    """Plain left-to-right accumulation of ``sum(w_i * u_i)``.

    Deliberately *not* ``sum()``: since 3.12 CPython applies Neumaier
    compensation there, which shifts the result by an ulp relative to the
    hand-written ``w1*u1 + w2*u2 + ...`` the published scores were computed with.
    """
    total = 0.0
    for name in weights:
        total = total + weights[name] * utilities[name]
    return float(total)


def strehl_from_residual(residual: np.ndarray, pupil: np.ndarray, strehl_ref: float):
    """Return ``(strehl, psf)`` for a residual phase map, as the originals did."""
    i_psf = np.abs(fouriertransform.ft2((pupil * np.exp(1j * residual)).astype(np.complex128), 1.0)) ** 2
    return float(i_psf.max() / strehl_ref), i_psf


# --------------------------------------------------------------------------- #
# Optical system construction shared by all four tasks.
# --------------------------------------------------------------------------- #
def build_optics_system(
    rng: np.random.Generator,
    *,
    n_pix: int = 96,
    pupil_radius: int = 40,
    n_sub: int = 12,
    n_modes: int = 25,
    reg_lambda: float = 1e-3,
    influence_sigma: float = 3.5,
    plant_gain_sigma: float | None = None,
    plant_gain_clip: tuple[float, float] = (0.66, 1.34),
) -> dict[str, Any]:
    """Build the pupil / WFS / DM model the four adaptive tasks share.

    Kept numerically identical to the inlined ``make_system`` bodies it replaces,
    including the *order* in which ``rng`` is consumed: the only draw made here
    is ``plant_gain`` (skipped entirely when ``plant_gain_sigma`` is ``None``, as
    in the fault-tolerant fusion task), so a caller's subsequent draws land on
    exactly the same stream positions as before.
    """
    pupil = aotools.circle(pupil_radius, n_pix).astype(np.float64)
    valid_mask = pupil > 0

    sub_w = n_pix // n_sub
    active = []
    for i in range(n_sub):
        for j in range(n_sub):
            x1, x2 = i * sub_w, (i + 1) * sub_w
            y1, y2 = j * sub_w, (j + 1) * sub_w
            if pupil[x1:x2, y1:y2].mean() > 0.45:
                active.append((i, j))
    active = np.array(active)
    n_sub_active = len(active)

    def slopes_from_phase(phase):
        gx = np.gradient(phase, axis=0)
        gy = np.gradient(phase, axis=1)
        s = np.zeros((2, n_sub_active), dtype=np.float64)
        for idx, (i, j) in enumerate(active):
            x1, x2 = i * sub_w, (i + 1) * sub_w
            y1, y2 = j * sub_w, (j + 1) * sub_w
            w = pupil[x1:x2, y1:y2]
            denom = w.sum() + 1e-12
            s[0, idx] = (gx[x1:x2, y1:y2] * w).sum() / denom
            s[1, idx] = (gy[x1:x2, y1:y2] * w).sum() / denom
        return s.reshape(-1)

    coords = np.linspace(8, n_pix - 8, 9)
    actuators = np.array(
        [(x, y) for x in coords for y in coords if pupil[int(round(x)), int(round(y))] > 0]
    )
    n_act = len(actuators)

    xg, yg = np.meshgrid(np.arange(n_pix), np.arange(n_pix), indexing="ij")
    influence = np.zeros((n_act, n_pix, n_pix), dtype=np.float64)
    for k, (x0, y0) in enumerate(actuators):
        influence[k] = np.exp(-((xg - x0) ** 2 + (yg - y0) ** 2) / (2 * influence_sigma**2)) * pupil

    def dm_surface(commands):
        return np.tensordot(commands, influence, axes=(0, 0))

    if plant_gain_sigma is None:
        plant_gain = None
        dm_surface_true = dm_surface
    else:
        plant_gain = np.clip(
            rng.normal(1.0, plant_gain_sigma, size=n_act), plant_gain_clip[0], plant_gain_clip[1]
        )

        def dm_surface_true(commands):
            return np.tensordot(commands * plant_gain, influence, axes=(0, 0))

    h = np.zeros((2 * n_sub_active, n_act), dtype=np.float64)
    for k in range(n_act):
        h[:, k] = slopes_from_phase(influence[k])

    gram = h.T @ h
    normal_matrix = gram + reg_lambda * np.eye(n_act)
    reconstructor = np.linalg.solve(normal_matrix, h.T)

    zern = aotools.zernikeArray(list(range(2, n_modes + 2)), n_pix, norm="rms") * pupil

    i0 = np.abs(fouriertransform.ft2(pupil.astype(np.complex128), 1.0)) ** 2
    strehl_ref = float(i0.max())

    return {
        "rng": rng,
        "n_pix": n_pix,
        "pupil": pupil,
        "valid_mask": valid_mask,
        "n_sub_active": n_sub_active,
        "slopes_from_phase": slopes_from_phase,
        "influence": influence,
        "dm_surface": dm_surface,
        "dm_surface_true": dm_surface_true,
        "plant_gain": plant_gain,
        "h_matrix": h,
        "gram": gram,
        "normal_matrix": normal_matrix,
        "reconstructor": reconstructor,
        "zern": zern,
        "strehl_ref": strehl_ref,
        "n_act": n_act,
    }


# --------------------------------------------------------------------------- #
# Candidate input packing.
# --------------------------------------------------------------------------- #
def npz_bytes(**arrays: Any) -> bytes:
    """Serialise ``arrays`` to in-memory ``.npz`` bytes (no pickled objects)."""
    buf = io.BytesIO()
    np.savez(buf, **arrays)
    return buf.getvalue()


def pack_control_model(control_model: dict[str, Any]) -> dict[str, Any]:
    """Flatten a ``control_model`` dict into npz-safe ``cm__*`` entries.

    Non-array objects (the fault-tolerant task's fitted ``IsolationForest``) are
    skipped; they are staged separately as an explicit pickle input.
    """
    packed: dict[str, Any] = {}
    for key, value in control_model.items():
        if isinstance(value, (bool, int, float, np.floating, np.integer, np.ndarray)):
            packed[f"{CONTROL_MODEL_PREFIX}{key}"] = np.asarray(value)
    return packed


# --------------------------------------------------------------------------- #
# Candidate isolation + output validation.
# --------------------------------------------------------------------------- #
def validate_commands(
    raw: Any,
    *,
    n_steps: int,
    n_act: int,
    max_voltage: float,
) -> np.ndarray:
    """Scorer-owned checks on the candidate's command matrix.

    Mirrors the per-step assertions the in-process loop used to make, applied to
    the whole trajectory before any of it is scored.
    """
    arr = np.asarray(raw)
    if arr.dtype.kind not in "fiub":
        raise CandidateRejected(f"commands must be numeric, got dtype {arr.dtype}")
    arr = arr.astype(np.float64, copy=False)
    if arr.shape != (n_steps, n_act):
        raise CandidateRejected(
            f"commands must have shape {(n_steps, n_act)}, got {arr.shape}"
        )
    if not np.all(np.isfinite(arr)):
        raise CandidateRejected("commands contain NaN/Inf")
    if np.any(np.abs(arr) > float(max_voltage) + 1e-8):
        worst = float(np.max(np.abs(arr)))
        raise CandidateRejected(
            f"commands violate voltage bounds: max|u| = {worst} > {max_voltage}"
        )
    return arr


def run_candidate_controller(
    candidate_path: Path,
    *,
    problem: dict[str, Any],
    extra_inputs: dict[str, bytes] | None = None,
    n_steps: int,
    n_act: int,
    max_voltage: float,
    timeout_s: float,
) -> np.ndarray:
    """Run the candidate alone in a subprocess and return validated commands.

    ``problem`` is written to ``problem.npz`` in the candidate's throwaway cwd;
    it must contain only the *observations* the controller is entitled to see
    (slopes, reconstructor, control model, plant/actuator constants) and never
    the ground-truth phase the score is computed against.

    Raises ``CandidateRejected`` for every failure mode -- crash, timeout,
    missing/unreadable submission, or a command matrix that fails validation.
    """
    inputs: dict[str, bytes | Path] = {PROBLEM_NAME: npz_bytes(**problem)}
    for rel, blob in (extra_inputs or {}).items():
        inputs[rel] = blob

    try:
        run = sandbox.run_candidate_isolated(
            Path(candidate_path),
            inputs=inputs,
            expected_outputs=(SUBMISSION_NAME,),
            timeout_s=timeout_s,
            copy_into_workdir=True,
            rlimits={"FSIZE": _CANDIDATE_FSIZE_BYTES},
        )
    except sandbox.InvalidSubmissionError as exc:
        raise CandidateRejected(str(exc)) from exc

    if run.timed_out:
        raise CandidateRejected(f"candidate timed out after {timeout_s}s")
    if run.returncode != 0:
        tail = (run.stderr_tail or "").strip().splitlines()[-5:]
        raise CandidateRejected(
            f"candidate exited non-zero ({run.returncode}): {' | '.join(tail)}"
        )

    try:
        with np.load(io.BytesIO(run.read_output_bytes(SUBMISSION_NAME)), allow_pickle=False) as data:
            if COMMANDS_KEY not in data.files:
                raise CandidateRejected(
                    f"{SUBMISSION_NAME} must contain a '{COMMANDS_KEY}' array, "
                    f"got keys {sorted(data.files)}"
                )
            raw = data[COMMANDS_KEY]
    except CandidateRejected:
        raise
    except Exception as exc:  # unreadable / pickled / truncated npz
        raise CandidateRejected(f"failed to read {SUBMISSION_NAME}: {exc}") from exc

    return validate_commands(raw, n_steps=n_steps, n_act=n_act, max_voltage=max_voltage)


def write_rejection(out_dir: Path, task: str, candidate_path: Path, error: str) -> None:
    """Record why the candidate was rejected, without writing ``metrics.json``.

    ``metrics.json`` staying absent is the signal ``frontier_eval/parse_result.py``
    turns into ``valid = 0`` / ``combined_score = -1e18``; the evaluator must also
    exit non-zero so the harness cannot be fooled by a stale file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "task": task,
        "candidate_module": str(Path(candidate_path).resolve()),
        "valid": 0.0,
        "combined_score": INVALID_COMBINED_SCORE,
        "candidate_error": error,
    }
    (out_dir / "candidate_rejected.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Reporting.
# --------------------------------------------------------------------------- #
def save_comparison_plots(
    out_dir: Path,
    baseline_metrics: dict,
    reference_metrics: dict,
    labels: Sequence[str],
) -> None:
    """Bar chart + example phase/residual/PSF panel, as the originals produced."""
    import matplotlib

    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)

    bvals = [baseline_metrics[k] for k in labels]
    rvals = [reference_metrics[k] for k in labels]

    plt.figure(figsize=(10, 4))
    x = np.arange(len(labels))
    w = 0.38
    plt.bar(x - w / 2, bvals, width=w, label="baseline")
    plt.bar(x + w / 2, rvals, width=w, label="reference")
    plt.xticks(x, list(labels), rotation=20)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "metrics_comparison.png", dpi=140)
    plt.close()

    fig, ax = plt.subplots(2, 3, figsize=(11, 6))
    for row, data, title in [
        (0, baseline_metrics["example"], "baseline"),
        (1, reference_metrics["example"], "reference"),
    ]:
        ax[row, 0].imshow(data["phase"], cmap="coolwarm")
        ax[row, 0].set_title(f"{title} phase")
        ax[row, 1].imshow(data["residual"], cmap="coolwarm")
        ax[row, 1].set_title(f"{title} residual")
        ax[row, 2].imshow(np.log10(data["psf"] + 1e-12), cmap="magma")
        ax[row, 2].set_title(f"{title} log10 PSF")
    for a in ax.ravel():
        a.axis("off")
    fig.tight_layout()
    fig.savefig(out_dir / "example_visualization.png", dpi=140)
    plt.close(fig)


def add_common_cli_args(parser, *, default_candidate: Path, default_max_voltage: float) -> None:
    parser.add_argument(
        "--candidate",
        type=str,
        default=str(default_candidate),
        help="Path to candidate controller script (run as its own process).",
    )
    parser.add_argument("--max_voltage", type=float, default=default_max_voltage)
    parser.add_argument(
        "--candidate-timeout",
        type=float,
        default=900.0,
        help="Wall-clock limit for the candidate subprocess.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="Where to write metrics/figures (default: verification/outputs).",
    )
