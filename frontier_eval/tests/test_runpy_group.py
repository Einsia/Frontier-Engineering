"""Isolation tests for the four ``runpy.run_path`` benchmarks.

The group
---------
==============================  ======================  =====================
benchmark                       candidate class         evaluator
==============================  ======================  =====================
LDPCErrorFloor                  TrappingSetSampler      verification/evaluator.py
PMDSimulation                   PMDSampler              verification/evaluator.py
RayleighFadingBER               DeepFadeSampler         verification/evaluator.py
HighReliableSimulation          MySampler               verification/evaluator.py
==============================  ======================  =====================

Code or data?
-------------
All four are **code**, and the tests below encode why. Each evaluator pulls a
*class* out of the candidate namespace, checks ``issubclass(cls, SamplerBase)``
(which needs a live class object, not a literal), instantiates it against a
benchmark-owned model, and then a simulation loop calls the instance's
``sample()`` **once per batch**, handing it arrays and consuming the arrays it
returns. There is no constant or array in the namespace that the scorer merely
reads, so ``ast.literal_eval`` cannot express the contract: the candidate's
deliverable is an algorithm (an importance-sampling proposal distribution).
``test_candidate_contract_requires_a_live_callable`` pins that down, so if a
future refactor ever turns one of these into a pure data drop the test will say
so and the cheaper ``literal_eval`` fix becomes available.

Consequently every one of the four goes through a subprocess plus a JSON
contract (``benchmarks/_shared/sampler_isolation.py``), and the score is
recomputed by the evaluator from validated numbers.
"""

from __future__ import annotations

import ast
import importlib.util
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED = REPO_ROOT / "benchmarks" / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

import sampler_isolation as iso  # noqa: E402


# ---------------------------------------------------------------------------
# task table
# ---------------------------------------------------------------------------

class Task:
    def __init__(self, key, rel, cls_name, base_import, invalid_score, golden):
        self.key = key
        self.dir = REPO_ROOT / "benchmarks" / rel
        self.cls_name = cls_name
        self.base_import = base_import
        self.invalid_score = invalid_score
        self.golden = golden

    @property
    def evaluator_path(self) -> Path:
        return self.dir / "verification" / "evaluator.py"

    @property
    def init_program(self) -> Path:
        return self.dir / "scripts" / "init.py"

    def load(self):
        name = f"_fe_eval_{self.key}"
        spec = importlib.util.spec_from_file_location(name, str(self.evaluator_path))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


# Golden values captured from the *pre-isolation* evaluators running the shipped
# scripts/init.py. combined_score / runtime_s are excluded on purpose: they are
# derived from wall-clock time and are not reproducible between runs, on any
# version of these evaluators.
LDPC = Task(
    "ldpc",
    "CommunicationEngineering/LDPCErrorFloor",
    "TrappingSetSampler",
    "benchmarks.CommunicationEngineering.LDPCErrorFloor.runtime.sampler",
    0.0,
    {
        "error_log_ratio": 0.829518162971624,
        "valid": 1.0,
        "err_rate_log_median": -129.7742833706382,
        "err_ratio_median": 1.0,
        "actual_samples_median": 50.0,
        "actual_std_median": 8.63748429028626e-69,
        "converged_rate": 1.0,
    },
)
PMD = Task(
    "pmd",
    "CommunicationEngineering/PMDSimulation",
    "PMDSampler",
    "benchmarks.CommunicationEngineering.PMDSimulation.runtime.sampler",
    0.0,
    {
        "outage_log_ratio": 1.6951446015454437,
        "valid": 1.0,
        "outage_prob_log_median": -19.028121235400967,
        "outage_prob_median": 5.447433615583205e-09,
        "actual_samples_median": 50000.0,
        "actual_std_median": 2.790233939824344e-05,
        "converged_rate": 0.0,
    },
)
RAYLEIGH = Task(
    "rayleigh",
    "CommunicationEngineering/RayleighFadingBER",
    "DeepFadeSampler",
    "benchmarks.CommunicationEngineering.RayleighFadingBER.runtime.sampler",
    0.0,
    {
        "error_log_ratio": 0.17839462627324743,
        "valid": 1.0,
        "err_rate_log_median": -11.334530838696981,
        "err_ratio_median": 1.1952969237457515e-05,
        "actual_samples_median": 10000.0,
        "actual_std_median": 4.605779964523731e-05,
        "converged_rate": 1.0,
    },
)
HRS = Task(
    "hrs",
    "WirelessChannelSimulation/HighReliableSimulation",
    "MySampler",
    "benchmarks.WirelessChannelSimulation.HighReliableSimulation.runtime.sampler",
    -1e18,
    {
        "error_log_ratio": 0.014479127573890693,
        "valid": 1.0,
        "err_rate_log_median": -14.121059331144622,
        "err_ratio_median": 0.0767,
        "actual_samples_median": 100000.0,
        "actual_std_median": 0.0,
        "target_std_attainment_rate": 1.0,
        "converged_rate": 0.0,
    },
)
ALL_TASKS = [LDPC, PMD, RAYLEIGH, HRS]
# LDPC's honest run costs ~25s of BLAS; the matrix below uses the cheap tasks.
FAST_TASKS = [PMD, RAYLEIGH]
# LDPCErrorFloor, RayleighFadingBER and HighReliableSimulation now run the
# *benchmark-owned* loop and ignore any simulate_variance_controlled the
# candidate defines, so aggregate forgery is structurally impossible there.
CANONICAL_TASKS = [LDPC, RAYLEIGH, HRS]
# PMDSimulation is the exception: its shipped baseline reimplements the loop
# (weight clipping + adaptive bias), so forcing the canonical loop would change
# the honest score. Its aggregates are validated rather than trusted.
FORGEABLE_TASKS = [PMD]


def _metrics(result):
    return result.metrics if hasattr(result, "metrics") else result


def _write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "candidate.py"
    path.write_text(source, encoding="utf-8")
    return path


def _preamble(task: Task) -> str:
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import numpy as np\n"
        f"from {task.base_import} import SamplerBase, NaiveSampler\n"
    )


def _forging_candidate(task: Task, returns: str, *, sample_body: str = "") -> str:
    """A candidate that does one honest batch, then reports whatever it likes."""
    body = sample_body or "        return super().sample(*args, **kwargs)\n"
    return (
        _preamble(task)
        + f"class {task.cls_name}(NaiveSampler):\n"
        "    def sample(self, *args, **kwargs):\n"
        + body
        + "    def simulate_variance_controlled(self, **kwargs):\n"
        + _first_batch_call(task)
        + f"        return {returns}\n"
    )


def _first_batch_call(task: Task) -> str:
    """Call sample() once so the run is not rejected for never sampling."""
    if task is PMD:
        return "        self.sample(num_segments=100, batch_size=5000)\n"
    if task is RAYLEIGH:
        return "        self.sample(num_branches=4, batch_size=5000, sigma_h=1.0)\n"
    if task is LDPC:
        return "        self.sample(0.6, np.zeros(1008, dtype=int), 50)\n"
    raise AssertionError("HRS never calls the candidate's own loop")


# ---------------------------------------------------------------------------
# 1. honest candidate: score unchanged
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task", ALL_TASKS, ids=lambda t: t.key)
def test_honest_candidate_metrics_unchanged(task: Task) -> None:
    """The shipped init.py still produces exactly the pre-isolation numbers."""
    module = task.load()
    metrics = _metrics(module.evaluate(str(task.init_program), repo_root=REPO_ROOT))

    assert metrics["valid"] == 1.0, metrics
    for key, expected in task.golden.items():
        actual = metrics[key]
        assert actual == pytest.approx(expected, rel=1e-12, abs=1e-300), (
            f"{task.key}.{key}: {actual!r} != {expected!r}"
        )

    # combined_score is T0 / (runtime_median * ratio + 1e-6): it moves with
    # wall-clock time, so only its sign/finiteness is stable.
    assert math.isfinite(metrics["combined_score"])
    assert metrics["combined_score"] > 0.0
    # ... and it is recomputed here from the validated numbers, not reported.
    assert metrics["isolated_candidate"] == 1.0


# ---------------------------------------------------------------------------
# 2. illegal outputs are rejected
#
# Two layers, because an end-to-end test alone is easy to make vacuous: a forged
# tuple that is merely *off-target* already scores valid=0 without any
# validation running at all. So:
#
#   (a) the domain rules are unit-tested straight against validate_common_repeat
#       with synthetic records -- non-vacuous by construction; and
#   (b) end-to-end, every rejection case starts from an ON-TARGET forgery (one
#       that really does reach valid=1.0 -- see the positive control) and mutates
#       exactly one field, so a rejection can only come from the new check.
# ---------------------------------------------------------------------------

# A forged 6-tuple whose err/outage log ratio lands on the task's reference
# value, i.e. the best case a liar could hope for.
ON_TARGET = {
    "pmd": "(-21.72326583694641, -1.0, 1e-9, 5000.0, 0.0, True)",
    "rayleigh": (
        "(-12.512925464970229, -1.0, "
        "float(np.exp(-11.512925464970229)), 5000.0, 0.0, True)"
    ),
}


def _mutated(task: Task, **overrides: str) -> str:
    """The on-target tuple with individual slots replaced."""
    slots = ["a", "b", "c", "total_samples", "actual_std", "converged"]
    base = {
        "pmd": ["-21.72326583694641", "-1.0", "1e-9", "5000.0", "0.0", "True"],
        "rayleigh": [
            "-12.512925464970229",
            "-1.0",
            "float(np.exp(-11.512925464970229))",
            "5000.0",
            "0.0",
            "True",
        ],
    }[task.key][:]
    for key, value in overrides.items():
        base[slots.index(key)] = value
    return "(" + ", ".join(base) + ")"


def _record(**overrides):
    """A synthetic driver record that passes every check unless overridden."""
    raw = {
        "a": -12.0,
        "b": -1.0,
        "c": 1e-5,
        "total_samples": 5000.0,
        "actual_std": 0.0,
        "converged": True,
        "converged_kind": "bool",
    }
    audit = {
        "sample_calls": 1,
        "rows": 5000,
        "nonfinite_proposal_calls": 0,
        "nonfinite_logq_calls": 0,
        "bad_shape_calls": 0,
        "proposal_ndim": 2,
    }
    raw.update({k: v for k, v in overrides.items() if k in raw})
    audit.update({k: v for k, v in overrides.items() if k in audit})
    return {"repeat": 0, "runtime_s": overrides.get("runtime_s", 1.0), "raw": raw, "audit": audit}


def test_validator_accepts_a_well_formed_record() -> None:
    """Control: without a mutation the synthetic record passes."""
    out = iso.validate_common_repeat(_record(), max_samples=50_000)
    assert out["total_samples"] == 5000.0
    assert out["converged"] is True


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"total_samples": 1e12}, "total_samples above max_samples"),
        ({"b": "nan"}, "weights_log is NaN"),
        ({"b": "inf"}, "weights_log is +inf"),
        ({"b": "-inf"}, "weights_log is -inf"),
        ({"a": "inf"}, "errors_log is +inf"),
        ({"a": "nan"}, "errors_log is NaN"),
        ({"a": -0.5}, "errors_log exceeds weights_log"),
        ({"total_samples": 0.0}, "total_samples is zero"),
        ({"total_samples": -5.0}, "total_samples is negative"),
        ({"total_samples": 5000.5}, "total_samples is not an integer"),
        ({"total_samples": "nan"}, "total_samples is NaN"),
        ({"total_samples": 20000.0}, "more samples than the proposal produced"),
        ({"actual_std": -1.0}, "actual_std is negative"),
        ({"actual_std": "nan"}, "actual_std is NaN"),
        ({"runtime_s": -1.0}, "runtime is negative"),
        ({"runtime_s": "inf"}, "runtime is not finite"),
        ({"nonfinite_proposal_calls": 1}, "proposal contained inf/NaN"),
        ({"nonfinite_logq_calls": 1}, "proposal log-density contained inf/NaN"),
        ({"bad_shape_calls": 1}, "proposal shape did not match its log-density"),
        ({"sample_calls": 0, "rows": 0}, "sample() was never called"),
        ({"rows": -1}, "audit counter is negative"),
    ],
)
def test_validator_rejects_illegal_field(overrides, reason) -> None:
    with pytest.raises(iso.InvalidSubmissionError):
        iso.validate_common_repeat(_record(**overrides), max_samples=50_000)
    # ...and it really was the mutation that did it.
    iso.validate_common_repeat(_record(), max_samples=50_000)


def test_validator_rejects_non_boolean_converged() -> None:
    rec = _record()
    rec["raw"]["converged_kind"] = "other"
    with pytest.raises(iso.InvalidSubmissionError):
        iso.validate_common_repeat(rec, max_samples=50_000, require_bool_converged=True)
    # The rule is opt-in: only RayleighFadingBER enforced it historically.
    iso.validate_common_repeat(rec, max_samples=50_000)


@pytest.mark.parametrize("task", FORGEABLE_TASKS, ids=lambda t: t.key)
def test_on_target_forgery_positive_control(task: Task, tmp_path: Path) -> None:
    """The forging harness can reach valid=1.0.

    Without this, every rejection test below could pass for the wrong reason.
    """
    module = task.load()
    program = _write(tmp_path, _forging_candidate(task, ON_TARGET[task.key]))
    metrics = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))
    assert metrics["valid"] == 1.0, metrics


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"total_samples": "1e12"}, "total_samples above max_samples"),
        ({"b": "float('nan')"}, "weights_log is NaN"),
        ({"a": "float('inf')"}, "errors_log is +inf"),
        ({"total_samples": "0.0"}, "total_samples is zero"),
        ({"total_samples": "5000.5"}, "total_samples is not an integer"),
        ({"actual_std": "-1.0"}, "actual_std is negative"),
        ({"actual_std": "float('nan')"}, "actual_std is NaN"),
        ({"total_samples": "50000.0"}, "more samples than were drawn"),
    ],
)
@pytest.mark.parametrize("task", FORGEABLE_TASKS, ids=lambda t: t.key)
def test_illegal_result_is_rejected(task: Task, tmp_path: Path, overrides, reason) -> None:
    module = task.load()
    program = _write(tmp_path, _forging_candidate(task, _mutated(task, **overrides)))
    metrics = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))

    assert metrics["valid"] == 0.0, f"{reason}: {metrics}"
    assert metrics["combined_score"] == task.invalid_score, f"{reason}: {metrics}"


@pytest.mark.parametrize("task", FORGEABLE_TASKS, ids=lambda t: t.key)
def test_unrecognised_result_shape_is_rejected(task: Task, tmp_path: Path) -> None:
    module = task.load()
    program = _write(tmp_path, _forging_candidate(task, "{'nope': 1}"))
    metrics = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == task.invalid_score


def test_out_of_range_probability_is_rejected(tmp_path: Path) -> None:
    """A probability outside [0, 1] is rejected even though it is finite."""
    module = PMD.load()
    program = _write(tmp_path, _forging_candidate(PMD, _mutated(PMD, c="5.0")))
    metrics = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == PMD.invalid_score


def _rayleigh_repeat(**overrides):
    base = {
        "a": -12.512925464970229,
        "b": -1.0,
        "c": math.exp(-11.512925464970229),
        "total_samples": 5000.0,
        "actual_std": 0.0,
        "converged": True,
    }
    base.update(overrides)
    return base


def test_rayleigh_identity_control_accepts_a_consistent_triple() -> None:
    """Control for the two rejection tests below."""
    module = RAYLEIGH.load()
    out = module._validate_result(_rayleigh_repeat())
    assert out["err_rate_log"] == pytest.approx(-11.512925464970229)


def test_inconsistent_err_ratio_is_rejected() -> None:
    """err_ratio must equal exp(errors_log - weights_log).

    RayleighFadingBER now runs the benchmark-owned loop, so this identity can no
    longer be violated by a candidate end to end -- but the check still guards
    the contract, so it is tested directly.
    """
    module = RAYLEIGH.load()
    with pytest.raises(ValueError, match="不一致"):
        module._validate_result(_rayleigh_repeat(c=0.5))


def test_converged_without_meeting_target_std_is_rejected() -> None:
    module = RAYLEIGH.load()
    # 0.099 <= TARGET_STD (0.1): accepted, so the pair below is meaningful.
    module._validate_result(_rayleigh_repeat(actual_std=0.099))
    with pytest.raises(ValueError, match="target_std"):
        module._validate_result(_rayleigh_repeat(actual_std=99.0))


def test_no_errors_observed_cannot_claim_convergence() -> None:
    module = RAYLEIGH.load()
    module._validate_result(
        _rayleigh_repeat(a=float("-inf"), c=0.0, converged=False)
    )
    with pytest.raises(ValueError):
        module._validate_result(
            _rayleigh_repeat(a=float("-inf"), c=0.0, converged=True)
        )
    with pytest.raises(ValueError):
        module._validate_result(
            _rayleigh_repeat(a=float("-inf"), c=0.5, converged=False)
        )


@pytest.mark.parametrize("task", FAST_TASKS, ids=lambda t: t.key)
def test_nonfinite_proposal_is_rejected(task: Task, tmp_path: Path) -> None:
    """A proposal containing inf/NaN poisons the importance weights."""
    sample_body = (
        "        x, logq = super().sample(*args, **kwargs)\n"
        "        x = np.asarray(x, dtype=float).copy()\n"
        "        x.reshape(-1)[0] = np.inf\n"
        "        return x, logq\n"
    )
    module = task.load()
    program = _write(
        tmp_path,
        _forging_candidate(task, ON_TARGET[task.key], sample_body=sample_body),
    )
    metrics = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == task.invalid_score


@pytest.mark.parametrize("task", FAST_TASKS, ids=lambda t: t.key)
def test_nonfinite_log_density_is_rejected(task: Task, tmp_path: Path) -> None:
    sample_body = (
        "        x, logq = super().sample(*args, **kwargs)\n"
        "        logq = np.asarray(logq, dtype=float).copy()\n"
        "        logq[0] = -np.inf\n"
        "        return x, logq\n"
    )
    module = task.load()
    program = _write(
        tmp_path,
        _forging_candidate(task, ON_TARGET[task.key], sample_body=sample_body),
    )
    metrics = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == task.invalid_score


@pytest.mark.parametrize("task", FORGEABLE_TASKS, ids=lambda t: t.key)
def test_never_sampling_is_rejected(task: Task, tmp_path: Path) -> None:
    """A candidate that reports an on-target result without drawing a sample."""
    module = task.load()
    source = (
        _preamble(task)
        + f"class {task.cls_name}(NaiveSampler):\n"
        "    def simulate_variance_controlled(self, **kwargs):\n"
        f"        return {ON_TARGET[task.key]}\n"
    )
    program = _write(tmp_path, source)
    metrics = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == task.invalid_score


# ---------------------------------------------------------------------------
# 2b. the canonical-loop tasks cannot be lied to at all
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task", CANONICAL_TASKS, ids=lambda t: t.key)
def test_canonical_loop_ignores_candidate_self_report(task: Task, tmp_path: Path) -> None:
    """The candidate's own simulate_variance_controlled() is never called.

    The candidate below is the shipped baseline plus an override that returns a
    perfect, converged, on-reference result without doing any work. Because the
    benchmark-owned loop drives the run, the override is dead code: the metrics
    must match the honest baseline exactly.
    """
    module = task.load()
    honest = _metrics(module.evaluate(str(task.init_program), repo_root=REPO_ROOT))

    forged_source = (
        task.init_program.read_text(encoding="utf-8")
        + "\n\n"
        f"def _forged(self, **kwargs):\n"
        "    return (-1.0, -1.0, 1.0, 1.0, 0.0, True)\n"
        f"{task.cls_name}.simulate_variance_controlled = _forged\n"
    )
    program = _write(tmp_path, forged_source)
    forged = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))

    for key, expected in task.golden.items():
        assert forged[key] == pytest.approx(expected, rel=1e-12, abs=1e-300), (
            f"{task.key}.{key} moved when the candidate forged a result"
        )
    assert forged["valid"] == honest["valid"] == 1.0
    # The forged tuple claimed 1 sample; the real loop drew the full budget.
    assert forged["actual_samples_median"] > 1.0


@pytest.mark.parametrize("task", ALL_TASKS, ids=lambda t: t.key)
def test_missing_class_is_rejected(task: Task, tmp_path: Path) -> None:
    program = _write(tmp_path, "VALUE = 1\n")
    module = task.load()
    metrics = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == task.invalid_score


@pytest.mark.parametrize("task", ALL_TASKS, ids=lambda t: t.key)
def test_crashing_candidate_is_rejected(task: Task, tmp_path: Path) -> None:
    program = _write(tmp_path, "raise SystemExit('boom')\n")
    module = task.load()
    metrics = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == task.invalid_score


def test_wrong_base_class_is_rejected(tmp_path: Path) -> None:
    program = _write(
        tmp_path,
        "class PMDSampler:\n"
        "    def __init__(self, **kwargs):\n"
        "        pass\n"
        "    def simulate_variance_controlled(self, **kwargs):\n"
        "        return (-5.0, -1.0, 0.5, 5000.0, 0.0, True)\n",
    )
    module = PMD.load()
    metrics = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))
    assert metrics["valid"] == 0.0


def test_hanging_candidate_hits_the_timeout(tmp_path: Path) -> None:
    """A runaway candidate cannot stall the evaluation."""
    program = _write(tmp_path, "while True:\n    pass\n")
    with pytest.raises(iso.SamplerRunError, match="timed out"):
        iso.run_sampler_repeats(
            task="pmd",
            candidate_path=program,
            repo_root=REPO_ROOT,
            class_name="PMDSampler",
            repeats=1,
            constants={
                "fiber_length_km": 100.0,
                "pmd_coefficient": 0.5,
                "num_segments": 100,
                "dgd_threshold": 30.0,
                "target_std": 0.1,
                "max_samples": 50_000,
                "batch_size": 5_000,
                "min_outages": 20,
            },
            reset_rng=False,
            timeout_s=5.0,
            python=sys.executable,
        )


# ---------------------------------------------------------------------------
# 3. the candidate cannot reach the scoring process
#
# These stand in for the "executable statements are no longer executed" test the
# literal_eval route would get. That route does not apply to this family (see the
# module docstring), so the property actually available is the one that matters:
# whatever the candidate executes, it executes somewhere else.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task", FAST_TASKS, ids=lambda t: t.key)
def test_module_level_side_effect_cannot_touch_the_scorer(task: Task, tmp_path: Path) -> None:
    """Import-time code in the candidate runs in the child, not in the scorer.

    The candidate rebinds numpy's aggregation functions and writes a marker file
    into the scorer's cwd. Under the old in-process ``runpy.run_path`` the first
    would have corrupted every median the evaluator computes. Both effects must
    now be confined to the subprocess.
    """
    marker = tmp_path / "candidate_ran_here.txt"
    source = (
        "import numpy\n"
        "numpy.median = lambda *a, **k: 12345.0\n"
        "numpy.nanmedian = lambda *a, **k: 12345.0\n"
        "numpy.mean = lambda *a, **k: 12345.0\n"
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        + _preamble(task)
        + f"class {task.cls_name}(NaiveSampler):\n    pass\n"
    )
    program = _write(tmp_path, source)

    import numpy as np

    module = task.load()
    metrics = _metrics(module.evaluate(str(program), repo_root=REPO_ROOT))

    # The scorer's own numpy is untouched...
    assert float(np.median([1.0, 2.0, 3.0])) == 2.0
    assert float(np.mean([1.0, 2.0, 3.0])) == 2.0
    # ... and no metric carries the poisoned constant.
    for key, value in metrics.items():
        assert value != 12345.0, f"{key} was poisoned by the candidate"

    # The candidate really did execute -- in the child process.
    assert marker.is_file()


@pytest.mark.parametrize("task", ALL_TASKS, ids=lambda t: t.key)
def test_evaluator_no_longer_executes_candidates_in_process(task: Task) -> None:
    """No in-process execution primitive is left in any of the four evaluators.

    This inspects the parsed AST, not the raw text: these files are expected to
    *discuss* runpy in comments explaining why the candidate no longer runs here,
    and a substring scan would forbid documenting the fix.
    """
    tree = ast.parse(task.evaluator_path.read_text(encoding="utf-8"))

    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported |= {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "runpy" not in imported, f"{task.evaluator_path} imports runpy"

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not (called & {"eval", "exec", "compile"}), (
        f"{task.evaluator_path} calls an execution builtin"
    )

    attr_called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    banned = {"run_path", "run_module", "exec_module", "spec_from_file_location"}
    assert not (attr_called & banned), (
        f"{task.evaluator_path} calls {sorted(attr_called & banned)}"
    )


# ---------------------------------------------------------------------------
# 4. the code-vs-data judgement, pinned
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task", ALL_TASKS, ids=lambda t: t.key)
def test_candidate_contract_requires_a_live_callable(task: Task) -> None:
    """These benchmarks consume a callable, so literal_eval cannot serve them.

    If this ever fails because a task stopped needing ``sample()``, that task has
    become a data drop and should move to ``ast.literal_eval`` instead of a
    subprocess.
    """
    sampler_module = task.dir / "runtime" / "sampler.py"
    source = sampler_module.read_text(encoding="utf-8")
    assert "def sample(" in source
    assert "class SamplerBase" in source
    # The task metadata asks the candidate for a class, not for constants.
    constraints = (task.dir / "frontier_eval" / "constraints.txt").read_text(encoding="utf-8")
    assert task.cls_name in constraints or task.key == "hrs"


def test_run_sampler_repeats_rejects_a_missing_candidate() -> None:
    with pytest.raises(iso.SamplerRunError, match="not found"):
        iso.run_sampler_repeats(
            task="pmd",
            candidate_path=REPO_ROOT / "does" / "not" / "exist.py",
            repo_root=REPO_ROOT,
            class_name="PMDSampler",
            repeats=1,
            constants={},
            reset_rng=False,
            timeout_s=10.0,
        )


def test_decode_special_round_trips_infinities() -> None:
    assert iso.decode_special("-inf") == float("-inf")
    assert iso.decode_special("inf") == float("inf")
    assert math.isnan(iso.decode_special("nan"))
    assert iso.decode_special(1.5) == 1.5
    with pytest.raises(iso.InvalidSubmissionError):
        iso.decode_special("not-a-number")
