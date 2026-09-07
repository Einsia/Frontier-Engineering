from __future__ import annotations

import json
import math
import os
import shutil
import sys
import tempfile
import time
import traceback
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any


DATASET_ID = "openproblems_neurips2021/bmmc_cite/normal/log_cp10k"
BASE_URL = (
    "https://openproblems-data.s3.amazonaws.com/"
    "resources/task_predict_modality/datasets/openproblems_neurips2021/bmmc_cite/normal/log_cp10k/"
)

# The three files the candidate is entitled to see. `test_mod2.h5ad` -- the
# ground truth -- is deliberately absent.
CANDIDATE_INPUTS = ("train_mod1.h5ad", "train_mod2.h5ad", "test_mod1.h5ad")
TRUTH_FILE = "test_mod2.h5ad"

CANDIDATE_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TEMP",
    "TMP",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
CANDIDATE_RLIMITS = {"FSIZE": 4 << 30, "NOFILE": 4096}


def _is_repo_root(path: Path) -> bool:
    return (path / "frontier_eval").is_dir() and (path / "benchmarks").is_dir()


def _find_repo_root() -> Path:
    if "FRONTIER_ENGINEERING_ROOT" in os.environ:
        return Path(os.environ["FRONTIER_ENGINEERING_ROOT"]).expanduser().resolve()

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            return parent
    return Path.cwd().resolve()


def _import_isolation(repo_root: Path):
    shared = repo_root / "benchmarks" / "_shared"
    if not (shared / "candidate_sandbox.py").is_file():
        raise RuntimeError(f"shared isolation helper not found under {shared}")
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import candidate_sandbox  # noqa: PLC0415

    return candidate_sandbox


def _load_scorer_module(repo_root: Path) -> Any:
    """Load the benchmark's scorer into *this* process, before the candidate runs.

    The evaluator used to shell out to this file after the candidate had
    finished, with ``PYTHONPATH=<repo_root>`` in the child's environment. Since
    PYTHONPATH precedes site-packages, a candidate could drop
    ``<repo_root>/anndata.py`` and have the scorer import it instead
    (measured: combined_score 1.0 with rmse 0.0, against an honest 0.6079).
    """
    path = (
        repo_root
        / "benchmarks"
        / "SingleCellAnalysis"
        / "predict_modality"
        / "verification"
        / "evaluate_predict_modality.py"
    ).resolve()
    if not path.is_file():
        raise RuntimeError(f"scorer not found: {path}")
    spec = spec_from_file_location("_predict_modality_scorer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load scorer: {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "evaluate"):
        raise RuntimeError(f"scorer defines no evaluate(): {path}")
    return module


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


def _quarantine_truth(dataset_dir: Path, truth_dir: Path) -> str | None:
    """Keep the ground truth out of the directory handed to the candidate.

    Returns a note when a legacy copy had to be moved. Callers of earlier
    versions of this evaluator left `test_mod2.h5ad` sitting in the same cache
    directory that gets passed to the candidate as `--dataset-dir`; an archived
    submission (baseline_archive/experiment1/openevolve/gpt-5.4) read it and
    submitted it verbatim as its prediction.
    """
    truth_dir.mkdir(parents=True, exist_ok=True)
    stale = dataset_dir / TRUTH_FILE
    if not stale.exists():
        return None
    target = truth_dir / TRUTH_FILE
    try:
        if target.exists():
            stale.unlink()
            return "removed a leaked ground-truth copy from the candidate dataset dir"
        shutil.move(str(stale), str(target))
        return "moved a leaked ground-truth copy out of the candidate dataset dir"
    except OSError as exc:
        return f"could not quarantine leaked ground truth: {exc}"


def evaluate(program_path: str, *, repo_root: Path | None = None) -> Any:
    """
    Evaluator for `benchmarks/SingleCellAnalysis/predict_modality`.

    Contract:
    - Runs the candidate in an isolated temp working directory as
      `python <program.py> --output prediction.h5ad --dataset-dir <INPUT_DIR>`.
    - `<INPUT_DIR>` holds train_mod1 / train_mod2 / test_mod1 only. The ground
      truth `test_mod2.h5ad` lives in a scorer-private directory the candidate
      is never told about.
    - The candidate returns a prediction; this process computes the score.
    """
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program_path = str(Path(program_path).expanduser().resolve())

    benchmark_dir = (
        repo_root / "benchmarks" / "SingleCellAnalysis" / "predict_modality"
    ).resolve()
    dataset_dir = (
        benchmark_dir
        / "resources_cache"
        / "openproblems_neurips2021__bmmc_cite__normal__log_cp10k"
    ).resolve()
    truth_dir = (
        benchmark_dir
        / "resources_truth"
        / "openproblems_neurips2021__bmmc_cite__normal__log_cp10k"
    ).resolve()

    artifacts: dict[str, str] = {}
    artifacts["interface_contract"] = (
        "Hard requirements for candidate program (do NOT change these):\n"
        "1) The evaluator will run: python <program.py> --output prediction.h5ad --dataset-dir <INPUT_DIR>\n"
        "2) Your program MUST accept the flags `--output` and `--dataset-dir` (no additional required CLI args).\n"
        "3) Your program MUST write a valid AnnData file at --output, with:\n"
        "   - layers['normalized'] of shape (n_test_cells, n_mod2_features)\n"
        "   - obs matching test_mod1.obs (same cells/order)\n"
        "   - var matching train_mod2.var (same features/order)\n"
        "   - uns['dataset_id'] present (copied from dataset) and uns['method_id']\n"
        "4) <INPUT_DIR> contains train_mod1.h5ad, train_mod2.h5ad and test_mod1.h5ad.\n"
        "   The held-out target `test_mod2.h5ad` is NOT available to your program.\n"
        "If you change the CLI interface, the program will fail and receive valid=0."
    )
    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }

    # Isolation helper and scorer (with anndata/numpy/scipy) resident first.
    try:
        sandbox = _import_isolation(repo_root)
        scorer = _load_scorer_module(repo_root)
    except Exception as e:
        artifacts["error_message"] = str(e)
        artifacts["traceback"] = _tail(traceback.format_exc())
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    timeout_s = int(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "1800") or "1800")
    deadline = start + max(1.0, float(timeout_s) - 2.0)

    dataset_dir.mkdir(parents=True, exist_ok=True)
    note = _quarantine_truth(dataset_dir, truth_dir)
    if note:
        artifacts["ground_truth_quarantine"] = note

    truth_path = truth_dir / TRUTH_FILE
    if truth_path.is_file():
        min_score_reserve_s = min(60, max(10, timeout_s // 5))
    else:
        # First run typically needs to download the ground truth (can be slow).
        min_score_reserve_s = min(max(60, timeout_s // 2), max(1, timeout_s - 1))
    program_timeout_s = max(1, timeout_s - min_score_reserve_s)

    missing = [name for name in CANDIDATE_INPUTS if not (dataset_dir / name).is_file()]
    artifacts["dataset_dir"] = str(dataset_dir)
    if missing:
        artifacts["missing_inputs"] = ", ".join(missing)

    work_dir = Path(tempfile.mkdtemp(prefix="fe_predict_modality_")).resolve()
    try:
        # 1) Run the candidate.
        try:
            run = sandbox.run_candidate_isolated(
                Path(program_path),
                expected_outputs=("prediction.h5ad",),
                timeout_s=max(1.0, min(float(program_timeout_s), deadline - time.time())),
                argv=(
                    "--output",
                    "prediction.h5ad",
                    "--dataset-dir",
                    str(dataset_dir),
                ),
                copy_into_workdir=True,
                env_allowlist=CANDIDATE_ENV_ALLOWLIST,
                rlimits=CANDIDATE_RLIMITS,
                python=sys.executable,
            )
        except sandbox.InvalidSubmissionError as e:
            artifacts["error_message"] = f"prediction.h5ad not generated: {e}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        except Exception as e:
            artifacts["error_message"] = f"failed to run candidate: {e}"
            artifacts["traceback"] = _tail(traceback.format_exc())
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

        pred_bytes = run.read_output_bytes("prediction.h5ad")
        artifacts["prediction_bytes"] = str(len(pred_bytes))
        pred_path = work_dir / "prediction.h5ad"
        pred_path.write_bytes(pred_bytes)

        # 2) Score in this process, against the scorer-private ground truth.
        try:
            result = scorer.evaluate(str(pred_path), dataset_dir=truth_dir)
        except Exception as e:
            artifacts["error_message"] = f"scoring failed: {e}"
            artifacts["traceback"] = _tail(traceback.format_exc())
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        try:
            score_metrics = dict(result.metrics)  # type: ignore[attr-defined]
        except AttributeError:
            score_metrics = dict(result)

        combined = score_metrics.get("combined_score")
        if not isinstance(combined, (int, float)) or isinstance(combined, bool):
            artifacts["error_message"] = "scorer produced no numeric combined_score"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        combined = float(combined)
        if not math.isfinite(combined):
            artifacts["error_message"] = f"scorer produced a non-finite score: {combined}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        metrics["combined_score"] = combined
        metrics["valid"] = float(score_metrics.get("valid", 1.0) or 0.0)
        for key, value in score_metrics.items():
            if key in metrics:
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[key] = float(value)

        # The candidate can no longer read the truth off the local filesystem,
        # but the dataset is public and this process cannot stop an outbound
        # fetch. A bit-exact reproduction of the held-out matrix is not something
        # an honest model does; surface it rather than silently scoring it.
        rmse = score_metrics.get("rmse")
        if isinstance(rmse, (int, float)) and not isinstance(rmse, bool):
            metrics["exact_truth_match"] = 1.0 if float(rmse) == 0.0 else 0.0

        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]):
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)
