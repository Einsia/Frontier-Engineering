"""Isolation and ground-truth regressions for five physics / ML benchmarks.

All five score a candidate by running an expensive forward model, and all five
used to let the candidate reach the thing that produces the number:

* Aerodynamics/CarAerodynamicsSensing   -- imported torch and unpickled the
  checkpoint *after* the candidate subprocess had exited.
* Astrodynamics/MannedLunarLanding      -- ran the Octave validator in the same
  working directory the candidate had just written to, through `bash -lc`.
* ParticlePhysics/MuonTomography        -- exec'd verification/evaluator.py as a
  subprocess after the candidate ran and read the score off its stdout.
* SingleCellAnalysis/predict_modality   -- handed the candidate the directory
  holding `test_mod2.h5ad`, the held-out ground truth, and ran the scorer with
  PYTHONPATH=<repo_root> afterwards.
* WirelessChannelSimulation/HighReliableSimulation -- already isolated, but the
  per-repeat runtime that divides into the score was measured with a
  monkeypatchable `time.time` inside the candidate's own process.

Every test builds its candidate (and, where an attack writes to the benchmark
tree, a throwaway copy of the repository) under `tmp_path`. No repository file is
ever modified by this module, and nothing under `baseline_archive/` is executed:
the historical attacks are re-implemented here from a reading of that source.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks"

CAR_DIR = BENCHMARKS / "Aerodynamics" / "CarAerodynamicsSensing"
MLL_DIR = BENCHMARKS / "Astrodynamics" / "MannedLunarLanding"
MUON_DIR = BENCHMARKS / "ParticlePhysics" / "MuonTomography"
PM_DIR = BENCHMARKS / "SingleCellAnalysis" / "predict_modality"
HRS_DIR = BENCHMARKS / "WirelessChannelSimulation" / "HighReliableSimulation"

# Published honest scores. Hardening must not move them.
MLL_BASELINE_SCORE = 4577.437043
MUON_BASELINE_SCORE = 199.32012533144325

PASS_BANNER = "=====结果文件全部检验通过====="


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _have(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _load_evaluator(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _metrics(result) -> dict:
    if isinstance(result, dict):
        return dict(result.get("metrics", result))
    return dict(result.metrics)


def _stage_repo(tmp_path: Path, *benchmark_dirs: Path) -> Path:
    """A throwaway repo root, so an attack that rewrites a scorer cannot touch
    the real checkout."""
    root = tmp_path / "repo"
    (root / "frontier_eval").mkdir(parents=True)
    shared = root / "benchmarks" / "_shared"
    shared.mkdir(parents=True)
    shutil.copy2(BENCHMARKS / "_shared" / "candidate_sandbox.py", shared / "candidate_sandbox.py")
    for src in benchmark_dirs:
        dst = root / src.relative_to(REPO_ROOT)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pdf", "*.pyc", "resources_cache", "resources_truth"))
    return root


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


# ==========================================================================
# 1. Astrodynamics/MannedLunarLanding
# ==========================================================================

octave_missing = shutil.which("octave-cli") is None and shutil.which("octave") is None
pytest_mll = pytest.mark.skipif(
    octave_missing or not _have("scipy") or not _have("numpy"),
    reason="MannedLunarLanding needs octave plus numpy/scipy",
)

_MLL_RESULTS_STUB = '\n'.join(' '.join(['0'] * 10) for _ in range(6)) + '\n'


def _mll_eval(tmp_path: Path):
    return _load_evaluator(MLL_DIR / "frontier_eval" / "evaluator.py", "mll_eval")


@pytest_mll
@pytest.mark.slow
def test_mll_honest_baseline_score_is_unchanged(tmp_path):
    module = _mll_eval(tmp_path)
    metrics = _metrics(module.evaluate(str(MLL_DIR / "scripts" / "init.py"), repo_root=REPO_ROOT))
    assert metrics["valid"] == 1.0, metrics
    assert metrics["combined_score"] == pytest.approx(MLL_BASELINE_SCORE, abs=1e-6)


@pytest_mll
def test_mll_candidate_cannot_shadow_the_octave_validator(tmp_path):
    """Octave resolves function names against the cwd before the addpath'd
    validator dir. Sharing a working directory let the candidate supply its own
    `aerodynamics_check_octave_full.m` (measured pre-fix payload: 999999 kg)."""
    candidate = _write(
        tmp_path / "shadow.py",
        f'''
        from pathlib import Path
        Path("results.txt").write_text({_MLL_RESULTS_STUB!r})
        Path("aerodynamics_check_octave_full.m").write_text(
            "function aerodynamics_check_octave_full()\\n"
            "fid = fopen('outputlog.txt','w');\\n"
            "fputs(fid,'{PASS_BANNER}\\\\n');\\n"
            "fputs(fid,'飞船运载质量：999999.000000 kg\\\\n');\\n"
            "fclose(fid);\\n"
            "end\\n", encoding="utf-8")
        ''',
    )
    metrics = _metrics(_mll_eval(tmp_path).evaluate(str(candidate), repo_root=REPO_ROOT))
    assert metrics["valid"] == 0.0, metrics
    assert metrics["combined_score"] == 0.0, metrics


@pytest_mll
def test_mll_candidate_cannot_plant_an_octaverc(tmp_path):
    """Octave sources `.octaverc` from the cwd at startup, before the validator
    is ever called (measured pre-fix payload: 888888 kg)."""
    candidate = _write(
        tmp_path / "octaverc.py",
        f'''
        from pathlib import Path
        Path("results.txt").write_text({_MLL_RESULTS_STUB!r})
        Path(".octaverc").write_text(
            "fid = fopen('outputlog.txt','w');\\n"
            "fputs(fid,'{PASS_BANNER}\\\\n');\\n"
            "fputs(fid,'飞船运载质量：888888.000000 kg\\\\n');\\n"
            "fclose(fid);\\n"
            "exit(0);\\n", encoding="utf-8")
        ''',
    )
    metrics = _metrics(_mll_eval(tmp_path).evaluate(str(candidate), repo_root=REPO_ROOT))
    assert metrics["valid"] == 0.0, metrics
    assert metrics["combined_score"] == 0.0, metrics


@pytest_mll
def test_mll_octave_is_not_run_through_a_login_shell():
    source = (MLL_DIR / "frontier_eval" / "evaluator.py").read_text(encoding="utf-8")
    assert '"-lc"' not in source and "'-lc'" not in source
    assert "--norc" in source


# ==========================================================================
# 2. ParticlePhysics/MuonTomography
# ==========================================================================

pytest_muon = pytest.mark.skipif(not _have("numpy"), reason="MuonTomography needs numpy")


@pytest_muon
def test_muon_honest_baseline_score_is_unchanged(tmp_path):
    root = _stage_repo(tmp_path, MUON_DIR)
    bench = root / MUON_DIR.relative_to(REPO_ROOT)
    module = _load_evaluator(bench / "frontier_eval" / "evaluator.py", "muon_eval_honest")
    metrics = _metrics(module.evaluate(str(bench / "baseline" / "solution.py"), repo_root=root))
    assert metrics["valid"] == 1.0, metrics
    assert metrics["combined_score"] == pytest.approx(MUON_BASELINE_SCORE, rel=0, abs=1e-12)


@pytest_muon
def test_muon_rewriting_the_scorer_no_longer_moves_the_score(tmp_path):
    """The scorer used to be exec'd as a subprocess *after* the candidate ran,
    with its score read off stdout (measured pre-fix: 987654.0). It is now
    imported before the candidate starts, so a rewrite lands too late."""
    root = _stage_repo(tmp_path, MUON_DIR)
    bench = root / MUON_DIR.relative_to(REPO_ROOT)
    scorer = bench / "verification" / "evaluator.py"
    honest_detectors = json.loads((bench / "baseline" / "solution.json").read_text())

    candidate = _write(
        tmp_path / "overwrite.py",
        f'''
        import json
        from pathlib import Path
        Path("solution.json").write_text({json.dumps(json.dumps(honest_detectors))})
        try:
            Path({str(scorer)!r}).write_text(
                "import json\\n"
                "print(json.dumps({{'score': 987654.0, 'status': 'success',\\n"
                "                  'metrics': {{'total_signal': 987654.0,\\n"
                "                              'total_cost': 0.0,\\n"
                "                              'valid_detectors': 1}}}}))\\n")
        except Exception as exc:
            print("rewrite failed:", exc)
        ''',
    )
    module = _load_evaluator(bench / "frontier_eval" / "evaluator.py", "muon_eval_attack")
    metrics = _metrics(module.evaluate(str(candidate), repo_root=root))

    # The rewrite really happened; it just no longer matters.
    assert "987654" in scorer.read_text(encoding="utf-8")
    assert metrics["combined_score"] == pytest.approx(MUON_BASELINE_SCORE, abs=1e-12), metrics


@pytest_muon
@pytest.mark.parametrize(
    "payload, needle",
    [
        ({"detectors": [{"x": 0.0, "y": 0.0, "z": -1.0, "theta": 0.0}]}, "missing 'phi'"),
        ({"detectors": [{"x": float("inf"), "y": 0.0, "z": -1.0, "theta": 0.0, "phi": 0.0}]}, "finite"),
        ({"detectors": [{"x": 0.0, "y": 0.0, "z": -1.0, "theta": 0.0, "phi": 0.0}] * 16}, "too many"),
        ({"detectors": []}, "empty"),
    ],
)
def test_muon_malformed_submissions_are_rejected(tmp_path, payload, needle):
    """`verification/evaluator.py` reads each field with `.get(field, 0.0)`, so a
    missing or non-finite field used to be silently replaced by a zero."""
    root = _stage_repo(tmp_path, MUON_DIR)
    bench = root / MUON_DIR.relative_to(REPO_ROOT)
    candidate = _write(
        tmp_path / "bad.py",
        f'''
        from pathlib import Path
        Path("solution.json").write_text({json.dumps(json.dumps(payload))})
        ''',
    )
    module = _load_evaluator(bench / "frontier_eval" / "evaluator.py", "muon_eval_bad")
    result = module.evaluate(str(candidate), repo_root=root)
    metrics = _metrics(result)
    artifacts = result["artifacts"] if isinstance(result, dict) else result.artifacts
    assert metrics["valid"] == 0.0, metrics
    assert needle in artifacts.get("error_message", ""), artifacts.get("error_message")


# ==========================================================================
# 3. SingleCellAnalysis/predict_modality
# ==========================================================================

pytest_pm = pytest.mark.skipif(
    not (_have("anndata") and _have("numpy") and _have("scipy")),
    reason="predict_modality needs anndata/numpy/scipy",
)

PM_CACHE_REL = Path("resources_cache") / "openproblems_neurips2021__bmmc_cite__normal__log_cp10k"
PM_TRUTH_REL = Path("resources_truth") / "openproblems_neurips2021__bmmc_cite__normal__log_cp10k"


def _make_pm_dataset(dest: Path) -> None:
    """A tiny dataset with the real schema. The genuine OpenProblems files are a
    large download; this keeps the test hermetic and offline."""
    import anndata as ad
    import numpy as np
    import pandas as pd
    from scipy.sparse import csr_matrix

    dest.mkdir(parents=True, exist_ok=True)
    dataset_id = "openproblems_neurips2021/bmmc_cite/normal/log_cp10k"
    rng = np.random.default_rng(7)
    n_tr, n_te, p1, p2 = 120, 60, 40, 14
    w = rng.normal(size=(p1, p2))

    def build(n: int, tag: str):
        x1 = np.abs(rng.normal(size=(n, p1))).astype(np.float32)
        x2 = np.maximum(x1 @ w + rng.normal(scale=0.3, size=(n, p2)), 0).astype(np.float32)
        obs = pd.DataFrame(index=[f"{tag}_cell{i}" for i in range(n)])
        pair = []
        for mat, names in ((x1, "gene"), (x2, "prot")):
            var = pd.DataFrame(index=[f"{names}{i}" for i in range(mat.shape[1])])
            adata = ad.AnnData(layers={"normalized": csr_matrix(mat)}, shape=mat.shape,
                               obs=obs, var=var, uns={"dataset_id": dataset_id})
            adata.X = csr_matrix(mat)
            pair.append(adata)
        return pair

    train1, train2 = build(n_tr, "train")
    test1, test2 = build(n_te, "test")
    for name, adata in (("train_mod1", train1), ("train_mod2", train2),
                        ("test_mod1", test1), ("test_mod2", test2)):
        adata.write_h5ad(str(dest / f"{name}.h5ad"), compression="gzip")


def _stage_pm(tmp_path: Path) -> tuple[Path, Path]:
    root = _stage_repo(tmp_path, PM_DIR)
    bench = root / PM_DIR.relative_to(REPO_ROOT)
    _make_pm_dataset(bench / PM_CACHE_REL)
    return root, bench


@pytest_pm
@pytest.mark.slow
def test_pm_ground_truth_is_quarantined_and_honest_score_survives(tmp_path):
    root, bench = _stage_pm(tmp_path)
    module = _load_evaluator(bench / "frontier_eval" / "evaluator.py", "pm_eval_honest")
    metrics = _metrics(
        module.evaluate(str(bench / "baseline" / "run_mean_per_gene.py"), repo_root=root)
    )
    assert metrics["valid"] == 1.0, metrics
    assert 0.0 < metrics["combined_score"] < 1.0
    assert metrics["exact_truth_match"] == 0.0

    # The held-out target is gone from the directory the candidate is handed and
    # now lives in a scorer-private one.
    assert not (bench / PM_CACHE_REL / "test_mod2.h5ad").exists()
    assert (bench / PM_TRUTH_REL / "test_mod2.h5ad").is_file()


@pytest_pm
@pytest.mark.slow
@pytest.mark.parametrize("truth_expression", [
    "a.dataset_dir / 'test_mod2.h5ad'",
    "a.dataset_dir.parents[1] / 'resources_truth' / a.dataset_dir.name / 'test_mod2.h5ad'",
])
def test_pm_candidate_cannot_read_the_ground_truth(tmp_path, truth_expression):
    """The exploit in baseline_archive/experiment1/openevolve/gpt-5.4: read
    test_mod2.h5ad out of --dataset-dir and submit it verbatim (measured pre-fix:
    combined_score 0.9958 with rmse 0.0, against an honest 0.6079)."""
    root, bench = _stage_pm(tmp_path)
    candidate = _write(
        tmp_path / "truth_copy.py",
        '''
        import argparse
        from pathlib import Path
        import anndata as ad
        import numpy as np
        from scipy.sparse import csc_matrix, issparse

        p = argparse.ArgumentParser()
        p.add_argument("--output", type=Path, default=Path("prediction.h5ad"))
        p.add_argument("--dataset-dir", type=Path, required=True)
        a = p.parse_args()

        test_mod1 = ad.read_h5ad(str(a.dataset_dir / "test_mod1.h5ad"))
        train_mod2 = ad.read_h5ad(str(a.dataset_dir / "train_mod2.h5ad"))
        truth = ad.read_h5ad(str(__TRUTH_EXPRESSION__))
        y = truth.layers["normalized"]
        y = y.tocsc() if issparse(y) else csc_matrix(np.asarray(y, dtype=np.float32))
        ad.AnnData(layers={"normalized": y}, shape=y.shape, obs=test_mod1.obs,
                   var=train_mod2.var,
                   uns={"dataset_id": test_mod1.uns.get("dataset_id"),
                        "method_id": "cached_test_mod2"}).write_h5ad(str(a.output))
        '''.replace('__TRUTH_EXPRESSION__', truth_expression),
    )
    module = _load_evaluator(bench / "frontier_eval" / "evaluator.py", "pm_eval_truth")
    metrics = _metrics(module.evaluate(str(candidate), repo_root=root))
    assert metrics["valid"] == 0.0, metrics
    assert metrics["combined_score"] == 0.0, metrics


@pytest_pm
def test_pm_scorer_is_not_run_with_repo_root_on_pythonpath():
    module = _load_evaluator(PM_DIR / "frontier_eval" / "evaluator.py", "pm_eval_env")
    assert "PYTHONPATH" not in module.CANDIDATE_ENV_ALLOWLIST
    source = (PM_DIR / "frontier_eval" / "evaluator.py").read_text(encoding="utf-8")
    # No assignment into a child environment anywhere in the module body.
    assert 'env["PYTHONPATH"]' not in source
    assert "os.environ.copy()" not in source


# ==========================================================================
# 4. WirelessChannelSimulation/HighReliableSimulation
# ==========================================================================

pytest_hrs = pytest.mark.skipif(
    not (_have("numpy") and _have("scipy")), reason="HighReliableSimulation needs numpy/scipy"
)


@pytest_hrs
@pytest.mark.slow
def test_hrs_honest_baseline_is_valid(tmp_path):
    """The score is `T0 / (runtime_median * err_log_ratio)`, so it is wall-clock
    dependent and deliberately not asserted to a fixed value; observed spread on
    one machine was 261-273 both before and after the hardening."""
    module = _load_evaluator(HRS_DIR / "verification" / "evaluator.py", "hrs_eval_honest")
    metrics = _metrics(module.evaluate(str(HRS_DIR / "scripts" / "init.py"), repo_root=REPO_ROOT))
    assert metrics["valid"] == 1.0, metrics
    assert metrics["combined_score"] > 0.0
    assert metrics["self_reported_total_s"] <= metrics["candidate_wall_s"] + 1.0


@pytest_hrs
@pytest.mark.slow
def test_hrs_candidate_cannot_forge_its_runtime(tmp_path):
    """The isolation driver times each repeat with `time.time()`, resolved on the
    shared `time` module at call time, and runpy executes the candidate inside
    that same process. Rebinding it reported runtime_s = 0 and scored
    10_400_103.73 against an honest ~262."""
    root = _stage_repo(tmp_path, HRS_DIR)
    bench = root / HRS_DIR.relative_to(REPO_ROOT)
    honest = (HRS_DIR / "scripts" / "init.py").read_text(encoding="utf-8")
    candidate = bench / "scripts" / "attack.py"
    candidate.write_text(
        honest + "\n\nimport time as _t\n_t.time = lambda: 0.0\n", encoding="utf-8"
    )
    module = _load_evaluator(bench / "verification" / "evaluator.py", "hrs_eval_attack")
    metrics = _metrics(module.evaluate(str(candidate), repo_root=root))
    assert metrics["valid"] == 0.0, metrics
    assert metrics["combined_score"] == pytest.approx(-1e18), metrics


# ==========================================================================
# 5. Aerodynamics/CarAerodynamicsSensing
# ==========================================================================
#
# The real evaluator needs the PhySense checkpoint, the pressure-field dataset,
# a PhySense checkout and a CUDA device; none is present in CI, so the honest
# score cannot be reproduced here. What *is* testable without any of them is the
# ordering invariant the fix is about: the model must be resident before the
# candidate is allowed to run.

pytest_car = pytest.mark.skipif(not _have("numpy"), reason="CarAerodynamicsSensing needs numpy")


@pytest_car
def test_car_model_is_loaded_before_the_candidate_runs(tmp_path, monkeypatch):
    import numpy as np

    module = _load_evaluator(CAR_DIR / "frontier_eval" / "evaluator.py", "car_eval_order")

    sentinel = tmp_path / "candidate_ran.marker"
    candidate = _write(
        tmp_path / "cand.py",
        f'''
        import json
        from pathlib import Path
        Path({str(sentinel)!r}).write_text("ran")
        Path("submission.json").write_text(json.dumps({{"indices": list(range(30))}}))
        ''',
    )

    monkeypatch.setattr(module, "_ensure_reference_points", lambda *a, **k: np.zeros((64, 3), np.float32))

    fake_torch = type(sys)("torch")
    fake_torch.cuda = type(sys)("torch.cuda")
    fake_torch.cuda.is_available = lambda: True
    fake_torch.device = lambda name: name
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    calls: list[str] = []

    def _boom(*args, **kwargs):
        calls.append("model")
        raise RuntimeError("checkpoint unavailable in CI")

    monkeypatch.setattr(module, "_load_model", _boom)

    result = module.evaluate(str(candidate), repo_root=REPO_ROOT)
    metrics = _metrics(result)
    artifacts = result["artifacts"] if isinstance(result, dict) else result.artifacts

    assert calls == ["model"], "the scorer never tried to load the model"
    assert "failed to load model" in artifacts.get("error_message", "")
    assert metrics["valid"] == 0.0
    # The decisive assertion: the candidate was never started.
    assert not sentinel.exists(), "candidate ran before the model was resident"


@pytest_car
def test_car_checkpoint_is_unpickled_with_weights_only():
    source = (CAR_DIR / "frontier_eval" / "evaluator.py").read_text(encoding="utf-8")
    assert "weights_only=True" in source
    assert 'env["PYTHONPATH"]' not in source
