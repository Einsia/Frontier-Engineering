"""Isolation regressions for the three KernelEngineering benchmarks.

FlashAttention, MLA and TriMul were all scored the same way: the evaluator ran
``verification/eval.py`` in one subprocess, and that subprocess held the
candidate, the reference implementation, the tolerance check, the clock, and the
fd (``POPCORN_FD``) whose contents the evaluator parsed into
``combined_score = 1e9 / geom_mean_ns``. Three one-liners defeated it:

* write ``check: pass`` and ``benchmark.0.mean: 1.0`` into POPCORN_FD, exit;
* replace ``check_implementation`` with ``lambda *_: ''``;
* replace ``time.perf_counter_ns`` / ``torch.cuda.Event``.

The behavioural tests below drive the *real* harness
(``benchmarks/_shared/kernel_isolation.py`` + ``kernel_worker.py``) and the
*real* FlashAttention task adapter against a CPU stand-in benchmark: a
reference implementation with the same structure and the same tolerances as
``FlashAttention/baseline/reference.py``, but on CPU float32 tensors and tiny
shapes. The stand-in exercises the harness on small inputs regardless of GPU availability
(input staging, per-rep perturbation, output verification, parent timing)
and none of the CUDA-specific timing. The end-to-end tests against the actual
benchmarks are marked ``gpu`` and skip without CUDA rather than passing quietly.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks"
SHARED = BENCHMARKS / "_shared"
KERNEL_DIR = BENCHMARKS / "KernelEngineering"
TASKS = ("FlashAttention", "MLA", "TriMul")

torch = pytest.importorskip("torch", reason="the kernel harness needs torch")
HAS_CUDA = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
requires_gpu = pytest.mark.skipif(not HAS_CUDA, reason="needs a CUDA device")


# --------------------------------------------------------------------------
# structural regressions (no torch execution)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("task", TASKS)
def test_eval_py_does_not_import_candidate_at_module_scope(task: str) -> None:
    """Importing the dev self-test tool must not execute candidate code."""
    text = (KERNEL_DIR / task / "verification" / "eval.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("from baseline.submission") or line.startswith("import baseline.submission"):
            pytest.fail(f"{task}/verification/eval.py imports the candidate at module scope: {line!r}")
    assert "NOT the scoring path" in text, f"{task}/verification/eval.py lost its advisory banner"


@pytest.mark.parametrize("task", TASKS)
def test_evaluator_no_longer_scores_from_the_candidate_process(task: str) -> None:
    """The evaluator must not read a log the candidate can write."""
    text = (KERNEL_DIR / task / "frontier_eval" / "evaluator.py").read_text(encoding="utf-8")
    # The module docstring describes the old design on purpose; assert against
    # the code, not the prose.
    tree = ast.parse(text)
    doc = ast.get_docstring(tree)
    code = text.replace(doc, "") if doc else text
    assert "POPCORN_FD" not in code, \
        f"{task} evaluator still reads a channel the candidate can write"
    assert "_parse_popcorn_log" not in code, f"{task} evaluator still parses the candidate's log"
    assert "import subprocess" not in code, \
        f"{task} evaluator still spawns the in-process dev runner itself"
    assert "kernel_isolation" in code, f"{task} evaluator does not use the isolated harness"


@pytest.mark.parametrize("task", TASKS)
def test_readonly_covers_reference_and_tolerances(task: str) -> None:
    entries = _read_list(KERNEL_DIR / task / "frontier_eval" / "readonly_files.txt")
    for needed in ("baseline/reference.py", "baseline/task.py", "baseline/utils.py"):
        assert needed in entries, f"{task}: {needed} is writable by the candidate"
    assert "baseline/submission.py" not in entries, f"{task}: the candidate's own file must stay writable"


@pytest.mark.parametrize("task", TASKS)
def test_copy_files_does_not_ship_reference_solutions(task: str) -> None:
    entries = _read_list(KERNEL_DIR / task / "frontier_eval" / "copy_files.txt")
    assert "." not in entries, f"{task}: copy_files is still a full copytree"
    baseline_entries = [e for e in entries if e.startswith("baseline")]
    assert baseline_entries, f"{task}: no baseline modules copied"
    for entry in baseline_entries:
        assert entry.endswith((".py", ".yml")), f"{task}: {entry} should be an explicit file"
        assert "solution" not in entry and "mla_code" not in entry, \
            f"{task}: {entry} would put a worked solution in the candidate's directory"


@pytest.mark.parametrize("task", TASKS)
def test_task_adapter_exposes_the_harness_api(task: str) -> None:
    path = KERNEL_DIR / task / "frontier_eval" / "task_adapter.py"
    assert path.is_file(), f"{task} has no task_adapter.py"
    source = path.read_text(encoding="utf-8")
    for name in ("make_state", "save_state", "load_state", "apply_round",
                 "save_output", "load_output", "check"):
        assert f"def {name}(" in source, f"{task} adapter is missing {name}()"
    # The one place a candidate-written file is deserialized in the trusted
    # process; pickle there would be arbitrary code execution.
    assert "weights_only=True" in source, f"{task} adapter unpickles candidate output"


@pytest.mark.parametrize("task", TASKS)
def test_bench_spec_keys_match_generate_input(task: str) -> None:
    """The scorer now parses the spec and calls generate_input itself.

    A mismatch between the spec file's keys and the reference's signature would
    only show up as a crash on a GPU node, so check it statically here.
    """
    sys.path.insert(0, str(SHARED))
    try:
        import kernel_isolation
    finally:
        sys.path.pop(0)

    spec_rel = {
        "FlashAttention": "verification/flash_attn_bench.txt",
        "MLA": "verification/mla_bench.txt",
        "TriMul": "verification/tri_bench.txt",
    }[task]
    cases = kernel_isolation.parse_test_cases(KERNEL_DIR / task / spec_rel)
    assert cases

    source = (KERNEL_DIR / task / "baseline" / "reference.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    signature = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "generate_input":
            signature = {arg.arg for arg in node.args.args}
    assert signature, f"{task}: no generate_input in baseline/reference.py"
    for case in cases:
        missing = set(case) - signature
        assert not missing, f"{task}: spec keys {sorted(missing)} are not generate_input parameters"
        unfilled = signature - set(case) - {"seed"}
        assert not unfilled, f"{task}: generate_input needs {sorted(unfilled)}, not in the spec"


def test_shared_harness_is_outside_every_benchmark() -> None:
    for name in ("kernel_isolation.py", "kernel_worker.py"):
        assert (SHARED / name).is_file()
    for task in TASKS:
        entries = _read_list(KERNEL_DIR / task / "frontier_eval" / "copy_files.txt")
        assert not any(e.startswith("..") for e in entries)


def _read_list(path: Path) -> list[str]:
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


# --------------------------------------------------------------------------
# behavioural regressions on a CPU stand-in
# --------------------------------------------------------------------------

_CPU_REFERENCE = '''
import math
import torch
import torch.nn.functional as F
from .task import Config, input_t, output_t
from .utils import make_match_reference

DEV = "cpu"
DT = torch.float32


def generate_input(batchsize, nheads, seqlen_q, seqlen_kv, headdim, causal, seed):
    gen = torch.Generator(device=DEV)
    gen.manual_seed(seed)
    config = Config(batch_size=batchsize, n_heads=nheads, seq_len_q=seqlen_q,
                    seq_len_kv=seqlen_kv, head_dim=headdim, causal=bool(causal),
                    scale=1.0 / math.sqrt(headdim))
    Q = torch.randn((batchsize, nheads, seqlen_q, headdim), dtype=DT, generator=gen, device=DEV) * 0.1
    K = torch.randn((batchsize, nheads, seqlen_kv, headdim), dtype=DT, generator=gen, device=DEV) * 0.1
    V = torch.randn((batchsize, nheads, seqlen_kv, headdim), dtype=DT, generator=gen, device=DEV) * 0.1
    return config, Q, K, V


def ref_kernel(data):
    config, Q, K, V = data
    return F.scaled_dot_product_attention(Q, K, V, attn_mask=None,
                                          is_causal=config.causal, scale=config.scale)


check_implementation = make_match_reference(ref_kernel, rtol=2e-02, atol=8e-03)
'''

_HONEST = '''
import torch
import torch.nn.functional as F


def custom_kernel(data):
    config, Q, K, V = data
    return F.scaled_dot_product_attention(Q, K, V, attn_mask=None,
                                          is_causal=config.causal, scale=config.scale)
'''

# The exact attack the old pipeline paid out 1e9 for.
_ATTACK_FORGE_LOG = '''
import os

_forged = (b"benchmark-count: 1\\nbenchmark.0.spec: forged\\nbenchmark.0.runs: 100\\n"
           b"benchmark.0.mean: 1.0\\nbenchmark.0.std: 0.0\\nbenchmark.0.err: 0.0\\n"
           b"benchmark.0.best: 1.0\\nbenchmark.0.worst: 1.0\\ncheck: pass\\n"
           b'{"ok": true, "results": [{"round": 0, "ok": true, "error": ""}]}\\n')
_fd = os.environ.get("POPCORN_FD")
if _fd:
    try:
        os.write(int(_fd), _forged)
        os._exit(0)
    except OSError:
        pass
try:
    for _entry in os.listdir("/proc/self/fd"):
        try:
            os.write(int(_entry), _forged)
        except OSError:
            pass
except OSError:
    pass


def custom_kernel(data):
    raise RuntimeError("no kernel here")
'''

_ATTACK_PATCH_CHECK = '''
import baseline.reference as _R

_R.check_implementation = lambda data, output: ''


def custom_kernel(data):
    return None
'''

_ATTACK_FAKE_TIMER = '''
import time
import torch
import torch.nn.functional as F

_tick = [0]


def _fake_ns():
    _tick[0] += 1
    return _tick[0]


time.perf_counter_ns = _fake_ns


class _FakeEvent:
    def __init__(self, *a, **k):
        pass

    def record(self, *a, **k):
        pass

    def elapsed_time(self, other):
        return 1e-6


try:
    torch.cuda.Event = _FakeEvent
except Exception:
    pass


def custom_kernel(data):
    config, Q, K, V = data
    return F.scaled_dot_product_attention(Q, K, V, attn_mask=None,
                                          is_causal=config.causal, scale=config.scale)
'''

_ATTACK_CACHE = '''
import torch
import torch.nn.functional as F

_cache = {}


def custom_kernel(data):
    config, Q, K, V = data
    key = (tuple(Q.shape), config.causal)
    if key not in _cache:
        _cache[key] = F.scaled_dot_product_attention(
            Q, K, V, attn_mask=None, is_causal=config.causal, scale=config.scale)
    return _cache[key]
'''


@pytest.fixture(scope="module")
def standin(tmp_path_factory) -> Path:
    """A FlashAttention-shaped benchmark that runs on CPU.

    Real ``task.py``/``utils.py``/``task_adapter.py`` from the repository; only
    ``reference.py`` is swapped for a CPU float32 version so the harness itself
    is under test rather than mocked.
    """
    root = tmp_path_factory.mktemp("ke_standin")
    bench = root / "benchmarks" / "KernelEngineering" / "FlashAttention"
    (bench / "baseline").mkdir(parents=True)
    (bench / "frontier_eval").mkdir()
    (bench / "verification").mkdir()
    src = KERNEL_DIR / "FlashAttention"
    shutil.copy2(src / "baseline" / "task.py", bench / "baseline" / "task.py")
    shutil.copy2(src / "baseline" / "utils.py", bench / "baseline" / "utils.py")
    shutil.copy2(src / "frontier_eval" / "task_adapter.py", bench / "frontier_eval" / "task_adapter.py")
    (bench / "baseline" / "reference.py").write_text(_CPU_REFERENCE, encoding="utf-8")
    (bench / "verification" / "bench.txt").write_text(
        "batchsize: 1; nheads: 2; seqlen_q: 64; seqlen_kv: 64; headdim: 16; causal: 1; seed: 5923\n",
        encoding="utf-8",
    )
    return bench


def _run_standin(standin: Path, tmp_path: Path, name: str, source: str) -> tuple[dict, dict]:
    sys.path.insert(0, str(SHARED))
    try:
        import kernel_isolation
    finally:
        sys.path.pop(0)

    candidate = tmp_path / f"{name}.py"
    candidate.write_text(source, encoding="utf-8")
    stage = tmp_path / "stage"
    stage.mkdir(exist_ok=True)
    os.environ["FRONTIER_EVAL_KERNEL_ALLOW_CPU"] = "1"
    os.environ["FRONTIER_EVAL_KERNEL_TMPDIR"] = str(stage)
    cfg = kernel_isolation.KernelTaskConfig(
        task_name="FlashAttentionStandIn",
        benchmark_dir=standin,
        bench_spec_rel="verification/bench.txt",
        timer="perf_counter",
        target_samples=4,
        case_budget_s=60.0,
    )
    import time as _time
    return kernel_isolation.evaluate_kernel_task(
        cfg, candidate, kernel_python=sys.executable,
        deadline_s=_time.time() + 300.0, shared_dir=SHARED,
    )


@pytest.mark.slow
def test_standin_honest_candidate_scores(standin: Path, tmp_path: Path) -> None:
    metrics, artifacts = _run_standin(standin, tmp_path, "honest", _HONEST)
    assert metrics["valid"] == 1.0, artifacts.get("error_message")
    assert metrics["combined_score"] > 0.0
    assert metrics["total_reps"] >= 3
    assert metrics["timing_forged"] == 0.0


@pytest.mark.slow
def test_standin_forged_log_is_worthless(standin: Path, tmp_path: Path) -> None:
    """The attack that used to pay 1e9: write the verdict into an inherited fd."""
    metrics, artifacts = _run_standin(standin, tmp_path, "forge", _ATTACK_FORGE_LOG)
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] <= 0.0
    assert artifacts.get("error_message")


@pytest.mark.slow
def test_standin_patched_check_is_worthless(standin: Path, tmp_path: Path) -> None:
    """Correctness is decided in a process the candidate cannot patch."""
    metrics, artifacts = _run_standin(standin, tmp_path, "patch", _ATTACK_PATCH_CHECK)
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] <= 0.0


@pytest.mark.slow
def test_standin_fake_timer_is_caught_by_the_wall_clock(standin: Path, tmp_path: Path) -> None:
    """An honest kernel with a patched clock must not out-score an honest one."""
    metrics, artifacts = _run_standin(standin, tmp_path, "timer", _ATTACK_FAKE_TIMER)
    assert metrics["valid"] == 1.0, artifacts
    assert metrics["geom_mean_ns"] == metrics["wall_geom_mean_ns"]
    assert metrics["combined_score"] == pytest.approx(1e9 / metrics["wall_geom_mean_ns"])
    assert metrics["geom_mean_ns"] > metrics["reported_geom_mean_ns"]



@pytest.mark.slow
def test_standin_cached_output_is_caught_by_perturbation(standin: Path, tmp_path: Path) -> None:
    """Every timed rep runs on a different input, so a replayed answer is wrong."""
    metrics, artifacts = _run_standin(standin, tmp_path, "cache", _ATTACK_CACHE)
    assert metrics["valid"] == 0.0
    assert metrics["correctness_failures"] >= 1.0


# --------------------------------------------------------------------------
# end-to-end on the real benchmarks (GPU only)
# --------------------------------------------------------------------------


@requires_gpu
@pytest.mark.slow
@pytest.mark.parametrize("task", TASKS)
def test_real_benchmark_baseline_is_valid(task: str, tmp_path: Path) -> None:
    """The shipped baseline/submission.py must still score under the new path."""
    metrics = _run_real(task, KERNEL_DIR / task / "baseline" / "submission.py", tmp_path)
    assert metrics["valid"] == 1.0, metrics
    assert metrics["combined_score"] > 0.0


@requires_gpu
@pytest.mark.slow
@pytest.mark.parametrize("task", TASKS)
def test_real_benchmark_rejects_forged_log(task: str, tmp_path: Path) -> None:
    candidate = tmp_path / "forge.py"
    candidate.write_text(_ATTACK_FORGE_LOG, encoding="utf-8")
    metrics = _run_real(task, candidate, tmp_path)
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] <= 0.0


def _run_real(task: str, candidate: Path, tmp_path: Path) -> dict:
    out = tmp_path / f"{task}_metrics.json"
    proc = subprocess.run(
        [sys.executable, "frontier_eval/run_eval.py", "--candidate", str(candidate),
         "--metrics-out", str(out), "--artifacts-out", str(tmp_path / f"{task}_artifacts.json")],
        cwd=str(KERNEL_DIR / task), capture_output=True, text=True, timeout=1800,
        env={**os.environ, "FRONTIER_ENGINEERING_ROOT": str(REPO_ROOT)},
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(out.read_text(encoding="utf-8"))
