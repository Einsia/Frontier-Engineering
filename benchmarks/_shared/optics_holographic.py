"""Shared plumbing for the four Optics ``holographic_*`` diffractive-design tasks.

Historically each of those four evaluators asked the *candidate* for everything
it needed to produce a score::

    spec   = baseline_module.make_default_spec()      # the problem definition
    out    = result["system"].measure_at_z(...)       # the forward physics
    target = result["target_field"]                   # the thing to match

The candidate was therefore simultaneously the author of the problem, the
simulator, and (transitively) the judge. An archived submission exploited this
by returning a system whose ``measure_at_z`` was a lookup table::

    class _LookupSystem:
        def measure_at_z(self, input_field, z):
            return self.outputs[z]      # == the target field it also returned

"predicted" and "target" then agreed to machine precision and the run scored
0.9999999999 while the runner-up scored 0.72.

The fix is a contract change, not a sandbox: *no callable ever crosses the
boundary.* The scorer owns the problem specification (``verification/problem_spec.py``
in each task), owns the optical model, and owns the metrics. The candidate runs
alone in a subprocess and hands back one thing -- the decision variables, i.e.
the real-valued phase/thickness maps of the modulator stack -- as plain arrays in
an ``.npz``. The scorer then builds the modulators itself, propagates the field
itself, and computes every number itself.

A ``_LookupSystem`` cannot be expressed in that contract: an ``.npz`` holds
arrays, ``allow_pickle=False`` rejects anything else, and ``measure_at_z`` is a
method on an object the scorer constructs after the candidate is already dead.

Invariants callers must preserve (mirrors ``candidate_sandbox``):

1. Import this module, ``torch``/``torchoptics``, the task's ``problem_spec`` and
   the reference solver *before* running the candidate. The candidate shares a
   filesystem with the scorer; anything imported afterwards could be code it
   just wrote.
2. Never read a score, metric, loss or field out of the candidate's submission.
   Only the decision variables are consumed, and only after ``validate_array``.
3. A crash, a timeout, a missing/unreadable ``submission.npz`` or an array that
   fails validation is a hard rejection: the evaluator must not write
   ``summary.json`` and must exit non-zero, so ``frontier_eval/parse_result.py``
   records ``combined_score = -1e18`` / ``valid = 0``.
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

__all__ = [
    "CandidateRejected",
    "INVALID_COMBINED_SCORE",
    "PROBLEM_NAME",
    "SUBMISSION_NAME",
    "ArraySpec",
    "add_common_cli_args",
    "build_phase_system",
    "build_target_field",
    "clip01",
    "configure_torchoptics",
    "cosine_similarity",
    "find_repo_root",
    "gaussian_input_field",
    "jones_from_phase",
    "polarization_forward",
    "polarized_gaussian_inputs",
    "normalized_gaussian_map",
    "ratio_weighted_map",
    "roi_powers",
    "run_candidate_arrays",
    "validate_array",
    "write_rejection",
]

INVALID_COMBINED_SCORE = -1e18

#: File the scorer stages into the candidate's throwaway cwd (plain JSON data).
PROBLEM_NAME = "problem.json"
#: File the candidate subprocess must produce in its cwd.
SUBMISSION_NAME = "submission.npz"

# Hard cap on anything the candidate writes; exceeding it kills the child with
# SIGXFSZ, which surfaces as a non-zero return code (a rejection) rather than
# the scorer trying to read a multi-gigabyte "submission" into memory.
_CANDIDATE_FSIZE_BYTES = 256 * 1024 * 1024

# Environment handed to the candidate. Deliberately narrow: the FRONTIER_EVAL_*
# variables the harness exports name the sandbox benchmark directory, and a
# candidate that knows that path could try to overwrite the scorer on disk.
# (Invariant 1 already makes such a write ineffective for the current run, and
# the harness fingerprints readonly paths afterwards -- this just removes the
# hint.)
CANDIDATE_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LD_LIBRARY_PATH",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "CUDA_VISIBLE_DEVICES",
    "PYTHONHASHSEED",
    "PYTHONDONTWRITEBYTECODE",
    "MPLCONFIGDIR",
)


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
# Submission validation.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ArraySpec:
    """What one decision-variable array in ``submission.npz`` must look like.

    ``max_abs`` is a finiteness/sanity bound, not a physical constraint: a phase
    is only ever consumed through ``exp(1j * phase)``, but an unbounded magnitude
    destroys the precision of that exponential and lets a candidate smuggle
    inf-adjacent values past a naive check.
    """

    shape: tuple[int, ...]
    max_abs: float
    min_value: float | None = None
    max_value: float | None = None


def validate_array(raw: Any, name: str, spec: ArraySpec) -> np.ndarray:
    """Scorer-owned checks on one submitted array. Raises ``CandidateRejected``."""
    arr = np.asarray(raw)
    if arr.dtype.kind not in "fiub":
        raise CandidateRejected(f"'{name}' must be a real numeric array, got dtype {arr.dtype}")
    if arr.dtype.kind == "b":
        raise CandidateRejected(f"'{name}' must be a real numeric array, got booleans")
    arr = arr.astype(np.float64, copy=False)
    if arr.shape != tuple(spec.shape):
        raise CandidateRejected(
            f"'{name}' must have shape {tuple(spec.shape)}, got {arr.shape}"
        )
    if not np.all(np.isfinite(arr)):
        raise CandidateRejected(f"'{name}' contains NaN/Inf")
    worst = float(np.max(np.abs(arr))) if arr.size else 0.0
    if worst > float(spec.max_abs):
        raise CandidateRejected(
            f"'{name}' out of range: max|v| = {worst:.6g} > {spec.max_abs:.6g}"
        )
    if spec.min_value is not None and float(np.min(arr)) < float(spec.min_value) - 1e-12:
        raise CandidateRejected(
            f"'{name}' below lower bound: min = {float(np.min(arr)):.6g} < {spec.min_value:.6g}"
        )
    if spec.max_value is not None and float(np.max(arr)) > float(spec.max_value) + 1e-12:
        raise CandidateRejected(
            f"'{name}' above upper bound: max = {float(np.max(arr)):.6g} > {spec.max_value:.6g}"
        )
    return arr


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"cannot serialise {type(obj)!r} into problem.json")


def run_candidate_arrays(
    candidate_path: Path,
    *,
    problem: dict[str, Any],
    arrays: dict[str, ArraySpec],
    timeout_s: float,
    optional_arrays: Sequence[str] = (),
) -> dict[str, np.ndarray]:
    """Run the candidate alone in a scratch directory and return validated arrays.

    ``problem`` is serialised to ``problem.json`` in the candidate's throwaway
    cwd. It is *data only* -- the scorer keeps its own in-memory copy and scores
    against that, so a candidate rewriting its input file changes nothing.

    ``copy_into_workdir=True`` puts ``sys.path[0]`` inside the scratch directory,
    so the candidate cannot import ``verification.problem_spec``, the reference
    solver, or any other task-tree module.

    ``optional_arrays`` names purely diagnostic 1-D arrays (a self-reported loss
    curve for the figures). They are checked for finiteness and dropped when
    absent or malformed -- and they are never scored, so nothing a candidate puts
    there can move its number.
    """
    blob = json.dumps(problem, indent=2, default=_json_default, allow_nan=False).encode("utf-8")

    try:
        run = sandbox.run_candidate_isolated(
            Path(candidate_path),
            inputs={PROBLEM_NAME: blob},
            expected_outputs=(SUBMISSION_NAME,),
            timeout_s=timeout_s,
            copy_into_workdir=True,
            env_allowlist=CANDIDATE_ENV_ALLOWLIST,
            rlimits={"FSIZE": _CANDIDATE_FSIZE_BYTES},
        )
    except sandbox.InvalidSubmissionError as exc:
        raise CandidateRejected(str(exc)) from exc

    if run.timed_out:
        raise CandidateRejected(f"candidate timed out after {timeout_s}s")
    if run.returncode != 0:
        tail = [ln for ln in (run.stderr_tail or "").strip().splitlines() if ln.strip()][-5:]
        raise CandidateRejected(
            f"candidate exited non-zero ({run.returncode}): {' | '.join(tail)}"
        )

    try:
        # allow_pickle=False is the structural half of the fix: an object array
        # (a "system", a lambda, a pickled callable) cannot survive this load.
        with np.load(io.BytesIO(run.read_output_bytes(SUBMISSION_NAME)), allow_pickle=False) as data:
            present = set(data.files)
            missing = [k for k in arrays if k not in present]
            if missing:
                raise CandidateRejected(
                    f"{SUBMISSION_NAME} missing required array(s) {missing}; got {sorted(present)}"
                )
            raw = {name: data[name] for name in arrays}
            extra = {name: data[name] for name in optional_arrays if name in present}
    except CandidateRejected:
        raise
    except Exception as exc:  # unreadable / pickled / truncated npz
        raise CandidateRejected(f"failed to read {SUBMISSION_NAME}: {exc}") from exc

    out = {name: validate_array(raw[name], name, spec) for name, spec in arrays.items()}
    for name, value in extra.items():
        diag = _sanitize_diagnostic(value)
        if diag is not None:
            out[name] = diag
    return out


def _sanitize_diagnostic(value: Any, limit: int = 100_000) -> np.ndarray | None:
    """Coerce an optional diagnostic array, or drop it. Never raises."""
    try:
        arr = np.asarray(value)
        if arr.dtype.kind not in "fiu":
            return None
        arr = np.ravel(arr.astype(np.float64, copy=False))[:limit]
        if arr.size == 0 or not np.all(np.isfinite(arr)):
            return None
        return arr
    except Exception:
        return None


def write_rejection(artifacts_dir: Path, task: str, candidate_path: Path, error: str) -> None:
    """Record why the candidate was rejected, without writing ``summary.json``.

    ``summary.json`` staying absent, together with a non-zero exit code, is what
    ``benchmarks/Optics/frontier_eval/parse_result.py`` turns into
    ``valid = 0`` / ``combined_score = -1e18``.
    """
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "task": task,
        "candidate_module": str(Path(candidate_path).resolve()),
        "candidate_execution": "isolated_subprocess",
        "valid": 0.0,
        "combined_score": INVALID_COMBINED_SCORE,
        "candidate_error": error,
    }
    (artifacts_dir / "candidate_rejected.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Scorer-owned optical model.
#
# Every function below runs in the *evaluator's* process, on arrays the
# candidate submitted. None of it is reachable from the candidate's sandbox.
# --------------------------------------------------------------------------- #
def configure_torchoptics(spacing: float, wavelength: float) -> None:
    import torchoptics  # noqa: PLC0415

    torchoptics.set_default_spacing(float(spacing))
    torchoptics.set_default_wavelength(float(wavelength))


def gaussian_input_field(
    shape: int,
    waist_radius: float,
    *,
    device: str,
    wavelength: float | None = None,
    z: float = 0.0,
):
    """Unit-power Gaussian source. Identical to what every baseline used to build."""
    import torch  # noqa: PLC0415
    from torchoptics import Field  # noqa: PLC0415
    from torchoptics.profiles import gaussian  # noqa: PLC0415

    del torch
    profile = gaussian(int(shape), float(waist_radius))
    if wavelength is None:
        field = Field(profile, z=z)
    else:
        field = Field(profile, wavelength=float(wavelength), z=z)
    return field.normalize(1.0).to(device)


def build_phase_system(phases: np.ndarray, layer_z: Sequence[float], device: str):
    """Build the modulator stack *from the submitted phase maps*.

    This is the heart of the contract change: the ``System`` is constructed here,
    by the scorer, from plain numbers. ``measure_at_z`` is therefore torchoptics'
    real propagation, never a candidate-supplied method.
    """
    import torch  # noqa: PLC0415
    from torchoptics import System  # noqa: PLC0415
    from torchoptics.elements import PhaseModulator  # noqa: PLC0415

    if len(phases) != len(layer_z):
        raise CandidateRejected(
            f"expected {len(layer_z)} phase layers, got {len(phases)}"
        )
    layers = [
        PhaseModulator(torch.as_tensor(np.asarray(p), dtype=torch.double), z=float(z))
        for p, z in zip(phases, layer_z)
    ]
    return System(*layers).to(device)


def build_thickness_system(
    thickness: np.ndarray,
    layer_z: Sequence[float],
    refractive_index: float,
    device: str,
):
    """Polychromatic (dispersive) modulator stack built from submitted thickness maps.

    A single physical thickness profile produces a *wavelength-dependent* phase
    ``2*pi/lambda * (n - 1) * t``, which is exactly what makes the multispectral
    task a shared-hardware problem rather than four independent ones.
    """
    import torch  # noqa: PLC0415
    from torchoptics import System  # noqa: PLC0415
    from torchoptics.elements import PolychromaticPhaseModulator  # noqa: PLC0415

    if len(thickness) != len(layer_z):
        raise CandidateRejected(
            f"expected {len(layer_z)} thickness layers, got {len(thickness)}"
        )
    layers = [
        PolychromaticPhaseModulator(
            torch.as_tensor(np.asarray(t), dtype=torch.double),
            float(refractive_index),
            z=float(z),
        )
        for t, z in zip(thickness, layer_z)
    ]
    return System(*layers).to(device)


def build_target_field(
    shape: int,
    waist_radius: float,
    centers: Sequence[Sequence[float]],
    ratios: Sequence[float],
    z: float,
    device: str,
):
    """Amplitude-domain target: sum of ``sqrt(ratio) * gaussian(offset=center)``.

    Kept numerically identical to the ``_build_target_field`` bodies it replaces,
    so scores stay comparable with the historical leaderboard -- the only change
    is *who* calls it.
    """
    import torch  # noqa: PLC0415
    from torchoptics import Field  # noqa: PLC0415
    from torchoptics.profiles import gaussian  # noqa: PLC0415

    shape = int(shape)
    target = torch.zeros((shape, shape), dtype=torch.double, device=device)
    ratio_t = torch.tensor(list(ratios), dtype=torch.double, device=device)
    ratio_t = ratio_t / ratio_t.sum()
    for ratio, center in zip(ratio_t, centers):
        target += torch.sqrt(ratio) * gaussian(
            shape, float(waist_radius), offset=tuple(center)
        ).real.to(device)
    return Field(target.to(torch.cdouble), z=float(z)).normalize(1.0)


def normalized_gaussian_map(shape: int, waist_radius: float, center, device: str):
    """Sum-normalised single-spot intensity template (multispectral shape term)."""
    from torchoptics.profiles import gaussian  # noqa: PLC0415

    target = gaussian(int(shape), float(waist_radius), offset=tuple(center)).real.to(device)
    return target / (target.sum() + 1e-12)


def ratio_weighted_map(
    shape: int,
    waist_radius: float,
    centers: Sequence[Sequence[float]],
    ratios: Sequence[float],
    device: str,
):
    """Intensity-domain target: sum of ``ratio * gaussian``, sum-normalised.

    Note the ``ratio *`` (not ``sqrt(ratio) *``): the polarization task's target
    lives in the intensity domain. Preserved verbatim from the original.
    """
    import torch  # noqa: PLC0415
    from torchoptics.profiles import gaussian  # noqa: PLC0415

    shape = int(shape)
    target = torch.zeros((shape, shape), dtype=torch.double, device=device)
    ratio_t = torch.tensor(list(ratios), dtype=torch.double, device=device)
    ratio_t = ratio_t / ratio_t.sum()
    for ratio, center in zip(ratio_t, centers):
        target += ratio * gaussian(shape, float(waist_radius), offset=tuple(center)).real.to(device)
    return target / (target.sum() + 1e-12)


def polarized_gaussian_inputs(shape: int, waist_radius: float, wavelength: float, device: str):
    """The x- and y-polarised unit-power Gaussian sources (3-component fields)."""
    import torch  # noqa: PLC0415
    from torchoptics import Field  # noqa: PLC0415
    from torchoptics.profiles import gaussian  # noqa: PLC0415

    shape = int(shape)
    base = gaussian(shape, float(waist_radius))

    data_x = torch.zeros((3, shape, shape), dtype=torch.cdouble)
    data_y = torch.zeros((3, shape, shape), dtype=torch.cdouble)
    data_x[0] = base.to(torch.cdouble)
    data_y[1] = base.to(torch.cdouble)

    field_x = Field(data_x, wavelength=float(wavelength), z=0).normalize(1.0).to(device)
    field_y = Field(data_y, wavelength=float(wavelength), z=0).normalize(1.0).to(device)
    return field_x, field_y


def jones_from_phase(phase_x, phase_y):
    """Diagonal Jones modulation profile for a polarization-sensitive layer."""
    import torch  # noqa: PLC0415

    shape = phase_x.shape
    jones = torch.zeros((3, 3, shape[0], shape[1]), dtype=torch.cdouble, device=phase_x.device)
    jones[0, 0] = torch.exp(1j * phase_x)
    jones[1, 1] = torch.exp(1j * phase_y)
    jones[2, 2] = 1.0 + 0j
    return jones


def polarization_forward(field, layer_z, output_z, phase_x_layers, phase_y_layers):
    """Propagate through the polarization-multiplexed stack. Scorer-owned."""
    out = field
    for z, px, py in zip(layer_z, phase_x_layers, phase_y_layers):
        out = out.propagate_to_z(float(z))
        out = out.polarized_modulate(jones_from_phase(px, py))
    return out.propagate_to_z(float(output_z))


def roi_powers(field, centers: Sequence[Sequence[float]], radius: float):
    """Power inside each circular ROI of the given field's intensity."""
    import torch  # noqa: PLC0415

    x, y = field.meshgrid()
    intensity = field.intensity()
    powers = []
    for cx, cy in centers:
        mask = ((x - float(cx)) ** 2 + (y - float(cy)) ** 2) <= float(radius) ** 2
        powers.append((intensity * mask.to(intensity.dtype)).sum())
    return torch.stack(powers)


def masks_for_centers(x, y, centers: Sequence[Sequence[float]], radius: float, dtype):
    return [
        (((x - float(cx)) ** 2 + (y - float(cy)) ** 2) <= float(radius) ** 2).to(dtype)
        for cx, cy in centers
    ]


def cosine_similarity(a, b) -> float:
    import torch  # noqa: PLC0415

    a_f = a.flatten()
    b_f = b.flatten()
    sim = torch.dot(a_f, b_f) / (torch.norm(a_f) * torch.norm(b_f) + 1e-12)
    return float(sim.item())


def clip01(value: float) -> float:
    if not math.isfinite(float(value)):
        return 0.0
    return float(min(1.0, max(0.0, float(value))))


# --------------------------------------------------------------------------- #
# CLI plumbing shared by the four evaluators.
# --------------------------------------------------------------------------- #
def add_common_cli_args(parser, *, default_artifacts_dir: Path, default_reference_steps: int) -> None:
    parser.add_argument("--device", default="cpu", help="cpu/cuda (default: cpu)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--baseline-steps",
        type=int,
        default=24,
        help="Optimisation-step budget advertised to the candidate in problem.json.",
    )
    parser.add_argument("--reference-steps", type=int, default=default_reference_steps)
    parser.add_argument("--artifacts-dir", default=str(default_artifacts_dir))
    parser.add_argument(
        "--candidate",
        default="",
        help="Candidate program (default: <task>/baseline/init.py). Run as its own process.",
    )
    parser.add_argument(
        "--candidate-timeout",
        type=float,
        default=900.0,
        help="Wall-clock limit for the candidate subprocess.",
    )


def norm_for_plot(x):
    return x / (x.max() + 1e-12)


def use_agg_matplotlib():
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt  # noqa: PLC0415

    return plt
