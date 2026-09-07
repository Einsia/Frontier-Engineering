from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

SENSOR_NUM = 30

CASE_START = 76
CASE_END = 100
SAMPLE_K = 10
SAMPLE_SEED = 2025

SIGMA_CLIP = 3.0
P_MIN = -844.3360
P_MAX = 602.6890

_CACHED_MODEL = None
_CACHED_MODEL_KEY = ""

CANDIDATE_TIMEOUT_S = 900.0

# Environment the candidate subprocess may see. FRONTIER_ENGINEERING_ROOT stays:
# every shipped and archived candidate uses it to locate the read-only
# references/car_surface_points.npy. PYTHONPATH is deliberately gone -- the
# evaluator used to prepend the repo root to the candidate's import path.
CANDIDATE_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TEMP",
    "TMP",
    "FRONTIER_ENGINEERING_ROOT",
    "PHYSENSE_CAR_DATA_DIR",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
CANDIDATE_RLIMITS = {"FSIZE": 1 << 30, "NOFILE": 4096}

ASSET_HELP = (
    "Prepare CarAerodynamicsSensing assets from the repository root with: "
    "python scripts/bootstrap/fetch_task_assets.py --target car-aero"
)


def _is_repo_root(path: Path) -> bool:
    if not (path / "frontier_eval").is_dir():
        return False
    if (path / "benchmarks").is_dir():
        return True
    return (path / "Astrodynamics").is_dir() and (path / "ElectronicDesignAutomation").is_dir()


def _find_repo_root() -> Path:
    if "FRONTIER_ENGINEERING_ROOT" in os.environ:
        return Path(os.environ["FRONTIER_ENGINEERING_ROOT"]).expanduser().resolve()

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            return parent
    return Path.cwd().resolve()


def _import_isolation(repo_root: Path):
    """Import the shared candidate-isolation helper.

    It sits outside every benchmark directory so a ``copy_files.txt`` of ``.``
    cannot drag it into a sandbox the candidate can write to.
    """
    shared = repo_root / "benchmarks" / "_shared"
    if not (shared / "candidate_sandbox.py").is_file():
        raise RuntimeError(f"shared isolation helper not found under {shared}")
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import candidate_sandbox  # noqa: PLC0415

    return candidate_sandbox


def _tail(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _truncate_middle(text: str, limit: int = 200_000) -> str:
    if len(text) <= limit:
        return text
    keep = max(0, (limit - 128) // 2)
    omitted = len(text) - (2 * keep)
    return text[:keep] + f"\n\n[... truncated {omitted} chars ...]\n\n" + text[-keep:]


def _remaining_timeout(deadline_s: float) -> float:
    return max(1.0, float(deadline_s - time.time()))


def _data_dir(benchmark_dir: Path) -> Path:
    override = (os.environ.get("PHYSENSE_CAR_DATA_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (benchmark_dir / "data" / "physense_car_data").resolve()


def _ckpt_path(benchmark_dir: Path) -> Path:
    override = (os.environ.get("PHYSENSE_CAR_CKPT_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()

    ckpt_dir = (benchmark_dir / "data" / "physense_car_ckpt").resolve()
    base = (ckpt_dir / "physense_transolver_car_base.pth").resolve()
    if base.exists():
        return base

    alt = (ckpt_dir / "physense_transolver_car_best_base.pth").resolve()
    if alt.exists():
        return alt

    return base


def _physense_car_dir(repo_root: Path) -> Path:
    candidates: list[Path] = []
    env = (os.environ.get("PHYSENSE_ROOT") or os.environ.get("PHYSENSE_REPO_ROOT") or "").strip()
    if env:
        candidates.append(Path(env).expanduser().resolve())
    candidates += [
        repo_root / "third_party" / "PhySense",
        repo_root.parent / "PhySense",
        repo_root / "PhySense",
    ]

    for base in candidates:
        base = base.expanduser().resolve()
        if base.name == "Car-Aerodynamics" and base.is_dir():
            return base

        car = (base / "Car-Aerodynamics").resolve()
        if car.is_dir():
            return car

    raise RuntimeError(
        "Could not find `PhySense/Car-Aerodynamics`.\n"
        "Fix by cloning the PhySense repo into one of:\n"
        "  <repo>/third_party/PhySense/Car-Aerodynamics\n"
        "  <workspace>/PhySense/Car-Aerodynamics\n"
        "or set env `PHYSENSE_ROOT=/path/to/PhySense` (or to the Car-Aerodynamics folder)."
    )


def _load_case(case_id: int, data_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    pressure_path = data_dir / "pressure_files" / f"case_{case_id}_p_car_patch.raw"
    if not pressure_path.exists():
        raise FileNotFoundError(f"Missing pressure file: {pressure_path}. {ASSET_HELP}")

    arr = np.loadtxt(pressure_path, comments="#", dtype=np.float32)
    coords = arr[:, :3]
    pressures = arr[:, 3]

    mean = pressures.mean()
    std = pressures.std()
    lower = mean - SIGMA_CLIP * std
    upper = mean + SIGMA_CLIP * std
    mask = (pressures >= lower) & (pressures <= upper)

    coords = coords[mask]
    pressures = pressures[mask]
    pressures = (pressures - P_MIN) / (P_MAX - P_MIN)

    return coords, pressures


def _ensure_reference_points(ref_path: Path, data_dir: Path) -> np.ndarray:
    if ref_path.exists():
        points = np.load(ref_path)
    else:
        points, _ = _load_case(1, data_dir)
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(ref_path, points)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("Reference points must have shape (M, 3).")
    return points


def _parse_submission_text(text: str, max_index: int) -> list[int]:
    data = json.loads(text)
    if isinstance(data, list):
        indices = data
    elif isinstance(data, dict) and "indices" in data:
        indices = data["indices"]
    else:
        raise ValueError("Submission must be a list or a dict with key 'indices'.")

    if len(indices) != SENSOR_NUM:
        raise ValueError(f"Expected {SENSOR_NUM} indices, got {len(indices)}")
    if len(set(indices)) != SENSOR_NUM:
        raise ValueError("Indices must be unique.")
    out: list[int] = []
    for idx in indices:
        if not isinstance(idx, int):
            raise ValueError("All indices must be integers.")
        if idx < 0 or idx >= max_index:
            raise ValueError(f"Index out of range: {idx} (max {max_index - 1})")
        out.append(int(idx))
    return out


def _parse_submission(path: Path, max_index: int) -> list[int]:
    if not path.exists():
        raise FileNotFoundError(f"Missing submission file: {path}")
    return _parse_submission_text(path.read_text(encoding="utf-8", errors="replace"), max_index)


def _select_cases() -> list[int]:
    import random

    cases = list(range(CASE_START, CASE_END + 1))
    rng = random.Random(SAMPLE_SEED)
    selected = rng.sample(cases, SAMPLE_K)
    selected.sort()
    return selected


def _patch_physense_car_walk_for_hopper_cublas(
    physense_transolver_car_walk: Any,
) -> None:
    """
    Work around a cuBLAS `cublasSgemmStridedBatched` crash observed on Hopper GPUs
    (e.g., NVIDIA H200) with torch 2.10.0+cu128 for very large N.

    The original PhySense implementation uses two `torch.einsum` calls in
    `Physics_Attention_Irregular_Mesh.forward`, which can lower to
    `cublasSgemmStridedBatched` and fail with `CUBLAS_STATUS_INVALID_VALUE`.

    This patch replaces those contractions with per-(batch,head) `mm` calls.
    """

    cls = getattr(physense_transolver_car_walk, "Physics_Attention_Irregular_Mesh", None)
    if cls is None:
        return
    if getattr(cls, "_frontier_cublas_workaround_applied", False):
        return

    import torch
    import torch.nn.functional as F

    def _safe_forward(self, x: torch.Tensor) -> torch.Tensor:
        B, N, _ = x.shape

        fx_mid = (
            self.in_project_fx(x)
            .reshape(B, N, self.heads, self.dim_head)
            .permute(0, 2, 1, 3)
            .contiguous()
        )  # (B, H, N, C)
        x_mid = (
            self.in_project_x(x)
            .reshape(B, N, self.heads, self.dim_head)
            .permute(0, 2, 1, 3)
            .contiguous()
        )  # (B, H, N, C)

        slice_weights = self.softmax(self.in_project_slice(x_mid) / self.temperature)  # (B, H, N, G)
        slice_norm = slice_weights.sum(2)  # (B, H, G)

        # (B, H, G, C) = (B,H,N,G)^T @ (B,H,N,C), but avoid strided-batched GEMM.
        G = int(slice_weights.shape[-1])
        slice_token = torch.empty(
            (B, self.heads, G, self.dim_head),
            device=x.device,
            dtype=x.dtype,
        )
        for b in range(B):
            for h in range(self.heads):
                w_t = slice_weights[b, h].transpose(0, 1).contiguous()  # (G, N)
                slice_token[b, h] = w_t.mm(fx_mid[b, h])  # (G, C)

        slice_token = slice_token / (slice_norm + 1e-5).unsqueeze(-1)

        q_slice_token = self.to_q(slice_token)
        k_slice_token = self.to_k(slice_token)
        v_slice_token = self.to_v(slice_token)

        out_slice_token = F.scaled_dot_product_attention(
            q_slice_token,
            k_slice_token,
            v_slice_token,
            dropout_p=0.1 if self.training else 0.0,
        )

        # (B, H, N, C) = (B,H,N,G) @ (B,H,G,C), but avoid strided-batched GEMM.
        out_x = torch.empty(
            (B, self.heads, N, self.dim_head),
            device=x.device,
            dtype=x.dtype,
        )
        for b in range(B):
            for h in range(self.heads):
                out_x[b, h] = slice_weights[b, h].mm(out_slice_token[b, h])

        out_x = out_x.permute(0, 2, 1, 3).contiguous().view(B, N, self.heads * self.dim_head)
        return self.to_out(out_x)

    cls.forward = _safe_forward
    cls._frontier_cublas_workaround_applied = True


def _load_model(device, *, repo_root: Path, ckpt_path: Path):
    global _CACHED_MODEL, _CACHED_MODEL_KEY

    physense_car = _physense_car_dir(repo_root)
    key = f"{physense_car}::{ckpt_path}::{device}"
    if _CACHED_MODEL is not None and _CACHED_MODEL_KEY == key:
        return _CACHED_MODEL

    if str(physense_car) not in sys.path:
        sys.path.insert(0, str(physense_car))

    from models import physense_transolver_car_walk

    _patch_physense_car_walk_for_hopper_cublas(physense_transolver_car_walk)

    model = physense_transolver_car_walk.Model(
        n_hidden=374,
        n_layers=12,
        space_dim=3,
        fun_dim=0,
        n_head=8,
        mlp_ratio=2,
        out_dim=1,
        slice_num=32,
        unified_pos=1,
    ).to(device)

    if not ckpt_path.exists():
        raise FileNotFoundError(f"Missing checkpoint: {ckpt_path}. {ASSET_HELP}")

    import torch

    # weights_only=True: the checkpoint path is writable by anything running as
    # this uid, and an unrestricted unpickle of an attacker-supplied file is
    # arbitrary code execution inside the scoring process.
    state = torch.load(ckpt_path, map_location=device, weights_only=True)
    model.load_state_dict(state)
    model.eval()

    _CACHED_MODEL = model
    _CACHED_MODEL_KEY = key
    return model


def evaluate(program_path: str, *, repo_root: Path | None = None) -> Any:
    """
    Frontier Eval evaluator for `benchmarks/Aerodynamics/CarAerodynamicsSensing`.

    Contract for candidate program:
    - Runs `python <program.py>` in an isolated working directory.
    - Candidate MUST write `submission.json` in the working directory.
    - `submission.json` is either:
        - {"indices": [int, ...]} or
        - [int, ...]
      with exactly 30 unique indices in [0, M).
    """
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program_path = str(Path(program_path).expanduser().resolve())

    metrics: dict[str, float] = {
        "combined_score": -1e18,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }
    artifacts: dict[str, str] = {}

    benchmark_dir = (
        repo_root / "benchmarks" / "Aerodynamics" / "CarAerodynamicsSensing"
    ).resolve()
    ref_path = (benchmark_dir / "references" / "car_surface_points.npy").resolve()
    data_dir = _data_dir(benchmark_dir)
    ckpt_path = _ckpt_path(benchmark_dir)

    artifacts["data_dir"] = str(data_dir)
    artifacts["ckpt_path"] = str(ckpt_path)
    artifacts["ref_points_path"] = str(ref_path)

    if not benchmark_dir.is_dir():
        artifacts["error_message"] = f"benchmark directory not found: {benchmark_dir}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    evaluator_timeout_s = float(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "900") or "900")
    deadline_s = start + max(1.0, evaluator_timeout_s - 5.0)

    try:
        ref_points = _ensure_reference_points(ref_path, data_dir)
    except Exception as e:
        artifacts["error_message"] = f"failed to load reference points: {e}"
        artifacts["traceback"] = _tail(traceback.format_exc())
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    # ------------------------------------------------------------------
    # Everything the scorer needs is loaded BEFORE the candidate runs.
    #
    # The evaluator used to import torch and build the model *after* the
    # candidate subprocess had exited. The candidate runs as the same uid and
    # shares the filesystem, so by then it could have rewritten the PhySense
    # `models` package that `_load_model` imports, or replaced the checkpoint
    # that `torch.load` unpickles -- either one is code execution inside the
    # scoring process, after which the reported score means nothing.
    # ------------------------------------------------------------------
    try:
        sandbox = _import_isolation(repo_root)
    except Exception as e:
        artifacts["error_message"] = str(e)
        artifacts["traceback"] = _tail(traceback.format_exc())
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    try:
        import torch
    except Exception as e:
        artifacts["error_message"] = f"torch import failed: {e}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    if not torch.cuda.is_available():
        artifacts["error_message"] = "CUDA is required for this evaluator (torch.cuda.is_available() is false)."
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    try:
        device = torch.device("cuda")
        model = _load_model(device, repo_root=repo_root, ckpt_path=ckpt_path)
    except Exception as e:
        artifacts["error_message"] = f"failed to load model: {e}"
        artifacts["traceback"] = _tail(traceback.format_exc())
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    try:
        # The candidate delivers 30 indices and nothing else.
        try:
            run = sandbox.run_candidate_isolated(
                Path(program_path),
                expected_outputs=("submission.json",),
                timeout_s=min(CANDIDATE_TIMEOUT_S, _remaining_timeout(deadline_s)),
                copy_into_workdir=True,
                env_allowlist=CANDIDATE_ENV_ALLOWLIST,
                rlimits=CANDIDATE_RLIMITS,
                python=sys.executable,
            )
        except sandbox.InvalidSubmissionError as e:
            artifacts["error_message"] = f"submission.json not generated: {e}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        artifacts["program_stdout"] = _tail(run.stdout_tail)
        artifacts["program_stderr"] = _tail(run.stderr_tail)
        artifacts["program_stdout_full"] = _truncate_middle(run.stdout_tail)
        artifacts["program_stderr_full"] = _truncate_middle(run.stderr_tail)
        metrics["program_returncode"] = float(run.returncode)

        if run.timed_out:
            artifacts["error_message"] = "program timeout"
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        if run.returncode != 0:
            artifacts["error_message"] = "candidate program exited non-zero"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        try:
            indices = _parse_submission_text(
                run.read_output_bytes("submission.json").decode("utf-8", errors="replace"),
                int(ref_points.shape[0]),
            )
        except Exception as e:
            artifacts["error_message"] = f"invalid submission.json: {e}"
            artifacts["traceback"] = _tail(traceback.format_exc())
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        selected_ref = ref_points[np.array(indices, dtype=np.int64)]
        cases = _select_cases()

        rel_losses: list[float] = []
        per_case: dict[str, float] = {}

        with torch.no_grad():
            for case_id in cases:
                if time.time() >= deadline_s:
                    artifacts["error_message"] = "evaluation timeout"
                    metrics["timeout"] = 1.0
                    metrics["runtime_s"] = float(time.time() - start)
                    return _wrap(metrics, artifacts)

                torch.manual_seed(SAMPLE_SEED + int(case_id))

                coords, pressures = _load_case(int(case_id), data_dir)
                pos = torch.from_numpy(coords).to(device)
                y = torch.from_numpy(pressures).to(device).unsqueeze(-1)

                ref_t = torch.tensor(selected_ref, device=device, dtype=pos.dtype)
                dist = torch.cdist(ref_t, pos)
                nn_idx = torch.argmin(dist, dim=1)
                sensor_pos = pos[nn_idx]
                model.xyz_sens = torch.nn.Parameter(sensor_pos, requires_grad=False)

                data = SimpleNamespace(
                    pos=pos,
                    y=y,
                    v=torch.tensor(0.0, device=device),
                    angle=torch.tensor(0.0, device=device),
                )
                rel = float(model.sample(data).item())
                rel_losses.append(rel)
                per_case[f"case_{case_id}"] = rel

        mean_rel = float(np.mean(rel_losses)) if rel_losses else float("inf")
        score = 1.0 - mean_rel

        metrics.update(
            {
                "combined_score": float(score),
                "valid": 1.0,
                "mean_rel_l2": float(mean_rel),
            }
        )
        artifacts["per_case_rel_l2"] = json.dumps(per_case, ensure_ascii=False, indent=2)
        artifacts["indices"] = json.dumps(indices)
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    except Exception as e:
        artifacts["error_message"] = str(e)
        artifacts["traceback"] = _tail(traceback.format_exc())
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]) -> Any:
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)
