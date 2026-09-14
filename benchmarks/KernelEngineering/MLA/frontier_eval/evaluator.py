"""Evaluator for benchmarks/KernelEngineering/MLA.

The scorer reads the benchmark specification and computes the score. A trusted
worker creates inputs and checks outputs against the reference implementation;
a separate candidate worker runs ``custom_kernel``. Scoring uses elapsed time
measured by the scorer through output delivery.

``verification/eval.py`` is a local kernel-checking tool and is not used by this
scoring entrypoint.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


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


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def evaluate(
    program_path: str,
    *,
    repo_root: Path | None = None,
    kernel_python: str | None = None,
):
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()

    benchmark_dir = (repo_root / "benchmarks" / "KernelEngineering" / "MLA").resolve()
    if not benchmark_dir.is_dir():
        benchmark_dir = (repo_root / "KernelEngineering" / "MLA").resolve()
    shared_dir = (repo_root / "benchmarks" / "_shared").resolve()

    if not (benchmark_dir / "baseline").is_dir() or not (benchmark_dir / "verification").is_dir():
        return _wrap(
            {"combined_score": 0.0, "valid": 0.0, "runtime_s": time.time() - start},
            {"error_message": f"MLA benchmark folder missing under {benchmark_dir}"},
        )
    if not (shared_dir / "kernel_isolation.py").is_file():
        return _wrap(
            {"combined_score": 0.0, "valid": 0.0, "runtime_s": time.time() - start},
            {"error_message": f"shared kernel harness missing: {shared_dir / 'kernel_isolation.py'}"},
        )

    # Import the harness before the candidate exists anywhere on disk in this
    # run (candidate_sandbox invariant 1: everything the scorer depends on is
    # resident before the candidate gets to run).
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    import kernel_isolation

    kernel_python = (
        str(kernel_python or "").strip()
        or str(os.environ.get("FRONTIER_EVAL_MLA_PYTHON", "") or "").strip()
        or sys.executable
        or "python"
    )

    evaluator_timeout_s = float(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "1200") or "1200")
    deadline_s = start + max(1.0, evaluator_timeout_s - 5.0)

    cfg = kernel_isolation.KernelTaskConfig(
        task_name="MLA",
        benchmark_dir=benchmark_dir,
        bench_spec_rel="verification/mla_bench.txt",
        timer="perf_counter",
        target_samples=10,
        case_budget_s=120.0,
    )
    metrics, artifacts = kernel_isolation.evaluate_kernel_task(
        cfg,
        program_path,
        kernel_python=kernel_python,
        deadline_s=deadline_s,
        shared_dir=shared_dir,
    )
    artifacts["kernel_python"] = kernel_python
    artifacts["benchmark_spec"] = str(benchmark_dir / "verification/mla_bench.txt")

    task_spec = _read_text(benchmark_dir / "Task_zh-CN.md")
    if task_spec:
        artifacts["task_spec_zh_cn_path"] = str(benchmark_dir / "Task_zh-CN.md")
        artifacts["task_spec_zh_cn"] = task_spec[:120000]
    return _wrap(metrics, artifacts)


def _wrap(metrics: dict, artifacts: dict):
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)
