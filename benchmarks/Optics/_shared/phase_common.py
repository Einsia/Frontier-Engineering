"""Scorer-owned plumbing shared by the four Optics ``phase_*`` benchmarks.

Why this file lives outside every benchmark directory
-----------------------------------------------------
Each ``phase_*`` task copies its own directory into a sandbox where the
candidate program is dropped in as ``baseline/init.py``. Anything reachable
from that copy is, in principle, reachable by the candidate. This module sits
in ``benchmarks/Optics/_shared/``, which is *not* inside any benchmark dir, so
no ``copy_files.txt`` entry (not even ``.``) can pull it into the sandbox --
the same argument that keeps ``benchmarks/_shared/candidate_sandbox.py`` safe.

The contract this module enforces
---------------------------------
The audited failure of these four tasks was that ``verification/validate.py``
imported the candidate's module and then asked *the candidate* for the problem
definition, the forward model, and the metrics::

    problem      = baseline_module.build_problem()      # problem <- candidate
    baseline_sol = baseline_module.solve_baseline(problem)
    metrics_base = baseline_sol["metrics"]              # metrics <- candidate

Two archived exploits followed directly from that:

* ``phase_dammann_uniform_orders``: a candidate saturated its own
  ``evaluate_orders`` with ``np.tanh(64 * core / scale)``, driving the reported
  ``cv_orders`` to ~0 and the score to 99.999999999.
* ``phase_fourier_pattern_holography``: a candidate redefined ``target_amp`` in
  its own ``build_problem`` as the far field of a flat-phase aperture, then
  returned an all-zero phase, so its output matched its target pointwise --
  99.99998936, with the code commenting "The solver can then reproduce the
  target exactly".

Under the new contract the candidate is a subprocess that receives a
scorer-authored problem file and returns *only decision variables*. Every
number that enters a score is computed here, in ``verification/problem.py`` and
``verification/metrics.py`` -- code the candidate can neither supply nor edit.
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

__all__ = [
    "SubmissionError",
    "find_repo_root",
    "load_sandbox",
    "run_candidate",
    "take_decision",
    "require_phase_grid",
    "require_transition_vector",
    "circular_aperture",
    "far_field_intensity",
    "spot_window_energies",
    "clip01",
    "pack_json",
    "pack_npz",
    "write_summary",
    "invalid_summary",
    "PHASE_ABS_MAX",
    "CANDIDATE_TIMEOUT_S",
]


# A phase map is used only as exp(1j * phase), so any real value is physically
# meaningful. The cap exists to reject inf/absurd payloads, not to constrain
# the design: 1e4 rad is ~1591 full cycles and still carries ~1e-12 relative
# precision through the exponential.
PHASE_ABS_MAX = 1.0e4

# Wall clock the candidate subprocess gets. The unified harness allows the whole
# evaluation 300 s by default (FRONTIER_EVAL_EVALUATOR_TIMEOUT_S), so leave room
# for the oracle and the plots.
CANDIDATE_TIMEOUT_S = 120.0


class SubmissionError(ValueError):
    """The candidate ran but its decision variables are unusable."""


# --------------------------------------------------------------------------
# repo / sandbox plumbing
# --------------------------------------------------------------------------


def find_repo_root(start: Path | None = None) -> Path:
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / "benchmarks").is_dir():
            return candidate
    base = Path(start or __file__).resolve()
    for parent in base.parents:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    raise RuntimeError("could not locate the Frontier-Engineering repo root")


def load_sandbox():
    """Import the shared isolation helper.

    Imported eagerly by every validator *before* the candidate runs, so the
    candidate cannot race the scorer by rewriting a module the scorer has yet
    to load.
    """
    repo = find_repo_root()
    shared = str(repo / "benchmarks" / "_shared")
    if shared not in sys.path:
        sys.path.insert(0, shared)
    import candidate_sandbox  # noqa: PLC0415

    return candidate_sandbox


def run_candidate(
    candidate_path: Path,
    *,
    inputs: dict[str, bytes],
    timeout_s: float = CANDIDATE_TIMEOUT_S,
) -> tuple[dict[str, Any] | None, str | None, float]:
    """Run the candidate in its own process and hand back parsed JSON only.

    ``copy_into_workdir=True`` is deliberate: the candidate is copied into a
    throwaway directory and executed from there, so ``sys.path[0]`` is that
    directory and neither ``verification/`` nor any other task file is
    importable or writable by relative path. Everything the candidate is
    entitled to know arrives through ``inputs``.
    """
    sandbox = load_sandbox()
    try:
        run = sandbox.run_candidate_isolated(
            Path(candidate_path),
            inputs=dict(inputs),
            expected_outputs=("submission.json",),
            timeout_s=float(timeout_s),
            copy_into_workdir=True,
        )
    except sandbox.InvalidSubmissionError as exc:
        return None, str(exc), 0.0
    except Exception as exc:  # noqa: BLE001 - never let a candidate crash the scorer
        return None, f"candidate could not be launched: {exc}", 0.0

    runtime_s = float(getattr(run, "runtime_s", 0.0) or 0.0)
    if run.timed_out:
        return None, f"candidate timed out after {timeout_s:.0f}s", runtime_s
    if run.returncode != 0:
        tail = (run.stderr_tail or "").strip().splitlines()[-3:]
        detail = " | ".join(tail) if tail else ""
        return None, f"candidate exited non-zero ({run.returncode}) {detail}".strip(), runtime_s

    try:
        submission = sandbox.load_json_output(run)
    except sandbox.InvalidSubmissionError as exc:
        return None, str(exc), runtime_s
    return submission, None, runtime_s


def take_decision(submission: dict[str, Any], allowed: Sequence[str]) -> tuple[dict[str, Any], list[str]]:
    """Keep only the declared decision-variable keys.

    Anything else the candidate wrote -- ``metrics``, ``score``, ``score_pct``,
    ``cv_orders`` -- is dropped here and never reaches the scoring code. The
    dropped names are returned so the summary can record the attempt.
    """
    allowed_set = set(allowed)
    kept = {k: v for k, v in submission.items() if k in allowed_set}
    ignored = sorted(k for k in submission if k not in allowed_set)
    return kept, ignored


# --------------------------------------------------------------------------
# strict decision-variable validation
# --------------------------------------------------------------------------


def _as_finite_float(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SubmissionError(f"{where} must be a number, got {type(value).__name__}")
    out = float(value)
    if not math.isfinite(out):
        raise SubmissionError(f"{where} must be finite, got {value!r}")
    return out


def require_phase_grid(decision: dict[str, Any], n: int, key: str = "phase") -> np.ndarray:
    """Validate an (n, n) phase map delivered as nested JSON lists."""
    if key not in decision:
        raise SubmissionError(f"submission.json must contain '{key}'")
    rows = decision[key]
    if not isinstance(rows, list) or len(rows) != n:
        raise SubmissionError(f"'{key}' must be a list of {n} rows, got {type(rows).__name__} of length {len(rows) if isinstance(rows, list) else 'n/a'}")

    out = np.empty((n, n), dtype=float)
    for i, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != n:
            raise SubmissionError(f"'{key}' row {i} must be a list of {n} numbers")
        for j, value in enumerate(row):
            v = _as_finite_float(value, f"'{key}'[{i}][{j}]")
            if abs(v) > PHASE_ABS_MAX:
                raise SubmissionError(
                    f"'{key}'[{i}][{j}] = {v!r} exceeds the +/-{PHASE_ABS_MAX:g} rad bound"
                )
            out[i, j] = v
    return out


def require_transition_vector(
    decision: dict[str, Any],
    count: int,
    lo: float,
    hi: float,
    key: str = "transitions",
) -> np.ndarray:
    """Validate a strictly increasing in-range transition vector."""
    if key not in decision:
        raise SubmissionError(f"submission.json must contain '{key}'")
    raw = decision[key]
    if not isinstance(raw, list) or len(raw) != count:
        raise SubmissionError(
            f"'{key}' must be a list of exactly {count} numbers, got "
            f"{type(raw).__name__} of length {len(raw) if isinstance(raw, list) else 'n/a'}"
        )

    values = [_as_finite_float(v, f"'{key}'[{i}]") for i, v in enumerate(raw)]
    for i, v in enumerate(values):
        if v < lo or v > hi:
            raise SubmissionError(f"'{key}'[{i}] = {v!r} outside the period bounds [{lo:g}, {hi:g}]")
    for i in range(1, count):
        if not values[i] > values[i - 1]:
            raise SubmissionError(
                f"'{key}' must be strictly increasing: entry {i} ({values[i]!r}) "
                f"does not exceed entry {i - 1} ({values[i - 1]!r})"
            )
    return np.asarray(values, dtype=float)


# --------------------------------------------------------------------------
# forward model primitives (scorer-owned physics)
# --------------------------------------------------------------------------


def circular_aperture(n: int, radius_px: float) -> np.ndarray:
    y, x = np.indices((n, n))
    c = (n - 1) / 2.0
    return (((x - c) ** 2 + (y - c) ** 2) <= float(radius_px) ** 2).astype(float)


def far_field_intensity(aperture_amp: np.ndarray, phase: np.ndarray) -> np.ndarray:
    """Phase-only SLM -> far-field intensity.

    Amplitude is pinned to the scorer's aperture, so a candidate cannot buy
    score by shaping amplitude; the phase map is its only lever.
    """
    near = np.asarray(aperture_amp, dtype=float) * np.exp(1j * np.asarray(phase, dtype=float))
    far = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(near), norm="ortho"))
    return np.abs(far) ** 2


def spot_window_energies(
    intensity: np.ndarray,
    spots: np.ndarray,
    window_radius_px: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-spot window energy and on-pixel peak for a square window."""
    n = intensity.shape[0]
    energies: list[float] = []
    peaks: list[float] = []
    for sx, sy in np.asarray(spots, dtype=float):
        ix = int(np.clip(np.round(sx), 0, n - 1))
        iy = int(np.clip(np.round(sy), 0, n - 1))
        i0 = max(0, iy - window_radius_px)
        i1 = min(n, iy + window_radius_px + 1)
        j0 = max(0, ix - window_radius_px)
        j1 = min(n, ix + window_radius_px + 1)
        energies.append(float(intensity[i0:i1, j0:j1].sum()))
        peaks.append(float(intensity[iy, ix]))
    return np.asarray(energies, dtype=float), np.asarray(peaks, dtype=float)


def clip01(value: float) -> float:
    return float(np.clip(float(value), 0.0, 1.0))


# --------------------------------------------------------------------------
# candidate inputs / validator outputs
# --------------------------------------------------------------------------


def pack_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def pack_npz(**arrays: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(buf, **{k: np.asarray(v) for k, v in arrays.items()})
    return buf.getvalue()


def write_summary(output_dir: Path, summary: dict[str, Any]) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "metrics.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path


def invalid_summary(task: str, reason: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A summary that scores the run as unusable.

    ``benchmarks/Optics/frontier_eval/parse_result.py`` maps ``valid == 0`` onto
    the harness-wide INVALID_COMBINED_SCORE sentinel, so a rejected candidate
    cannot land anywhere on the feasible range.
    """
    summary: dict[str, Any] = {
        "task": task,
        "valid": False,
        "candidate_error": reason,
        "baseline": {"score_pct": 0.0, "score": 0.0},
    }
    if extra:
        summary.update(extra)
    return summary


def numeric_only(metrics: dict[str, Any], skip: Iterable[str] = ()) -> dict[str, float]:
    skip_set = set(skip)
    return {
        k: float(v)
        for k, v in metrics.items()
        if k not in skip_set and isinstance(v, (int, float)) and not isinstance(v, bool)
    }
