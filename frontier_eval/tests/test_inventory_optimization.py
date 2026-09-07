"""End-to-end regressions for the four converted InventoryOptimization tasks.

Each of ``disruption_eoqd``, ``finite_horizon_dp``, ``general_meio`` and
``tree_gsm_safety_stock`` used to ``import`` the candidate into the scoring
process (``from baseline.init import solve``). The candidate now runs in its
own subprocess and hands back only ``submission.json``, which the evaluator
validates and scores itself.

Two properties are pinned per task:

1. The honest baseline still scores its published value, bit for bit, and the
   regenerated ``output/*.json`` are byte-identical to what is committed.
2. That task's historical exploit no longer works.

The exploits are re-implemented here from the archived programs rather than
imported from ``baseline_archive/`` -- those archived candidates sniff call
stacks and read source files, and are never executed by this suite.

These run the *task's* ``verification/evaluate.py`` directly, not the harness.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "benchmarks" / "InventoryOptimization"

# Published baseline_final_score for each task, copied from the committed
# output/comparison.json. The honest candidate must reproduce these exactly.
PUBLISHED_SCORE = {
    "disruption_eoqd": 0.36423022249600623,
    "finite_horizon_dp": 0.3673219124866723,
    "general_meio": 0.18253152886847146,
    "tree_gsm_safety_stock": 0.38125997730251027,
}

OUTPUT_FILES = ("baseline_result.json", "comparison.json", "reference_result.json")


class TaskEnv:
    """Runs one task's evaluator, and restores everything it touched."""

    def __init__(self, task_name: str) -> None:
        self.task_name = task_name
        self.task_dir = BENCH_ROOT / task_name
        self.candidate_path = self.task_dir / "baseline" / "init.py"
        self.output_dir = self.task_dir / "output"
        self.honest_source = self.candidate_path.read_text(encoding="utf-8")
        self.snapshot = {
            name: (self.output_dir / name).read_bytes()
            for name in OUTPUT_FILES
            if (self.output_dir / name).is_file()
        }

    def write_candidate(self, source: str) -> None:
        self.candidate_path.write_text(source, encoding="utf-8")

    def run(self) -> dict:
        proc = subprocess.run(
            [sys.executable, "verification/evaluate.py"],
            cwd=str(self.task_dir),
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            f"{self.task_name} evaluator crashed (rc={proc.returncode}):\n{proc.stderr}"
        )
        return json.loads((self.output_dir / "comparison.json").read_text(encoding="utf-8"))

    def output_bytes(self, name: str) -> bytes:
        return (self.output_dir / name).read_bytes()

    def restore(self) -> None:
        self.candidate_path.write_text(self.honest_source, encoding="utf-8")
        # Put back the committed artifacts so a test run never leaves the
        # tracked output/*.json rewritten by a malicious candidate.
        for name in OUTPUT_FILES:
            path = self.output_dir / name
            if name in self.snapshot:
                path.write_bytes(self.snapshot[name])
            elif path.is_file():
                path.unlink()


@contextlib.contextmanager
def task_env(task_name: str):
    env = TaskEnv(task_name)
    try:
        yield env
    finally:
        env.restore()


def assert_honest_run_is_unchanged(task_name: str) -> None:
    """The honest candidate reproduces the published score and artifacts."""
    with task_env(task_name) as env:
        comparison = env.run()
        assert comparison["baseline_final_score"] == PUBLISHED_SCORE[task_name]
        for name in OUTPUT_FILES:
            assert env.output_bytes(name) == env.snapshot[name], (
                f"{task_name}/output/{name} changed under the isolated evaluator"
            )


# --------------------------------------------------------------------------
# Honest-solution regressions (score must not move by a single bit).
# --------------------------------------------------------------------------


def test_disruption_eoqd_honest_score_unchanged() -> None:
    assert_honest_run_is_unchanged("disruption_eoqd")


def test_finite_horizon_dp_honest_score_unchanged() -> None:
    assert_honest_run_is_unchanged("finite_horizon_dp")


def test_general_meio_honest_score_unchanged() -> None:
    assert_honest_run_is_unchanged("general_meio")


def test_tree_gsm_honest_score_unchanged() -> None:
    assert_honest_run_is_unchanged("tree_gsm_safety_stock")


# --------------------------------------------------------------------------
# disruption_eoqd: the scoring anchor is no longer candidate-supplied, and a
# non-finite Q no longer saturates clip().
# --------------------------------------------------------------------------

# Archived gpt-5.4 returned (q_baseline, q_manual, safety_multiplier) with
# q_baseline forced to 1.0, which the evaluator adopted as the comparison
# anchor for both the cost and risk denominators -> score 1.0.
DISRUPTION_FORGED_ANCHOR = '''# EVOLVE-BLOCK-START
import json
from pathlib import Path

def solve(cfg=None):
    # Tries to hand the evaluator a deliberately lean scoring anchor
    # alongside a normal order quantity (the archived exploit shape).
    return {"order_quantity": 115.08293371587753, "q_classic": 1.0,
            "baseline_order_quantity": 1.0, "safety_multiplier": 1.0}

if __name__ == "__main__":
    Path("submission.json").write_text(json.dumps(solve()))
# EVOLVE-BLOCK-END
'''

DISRUPTION_NAN = '''# EVOLVE-BLOCK-START
import json
from pathlib import Path

def solve(cfg=None):
    # NaN propagates through max/min-based clip() as 1.0 on every metric.
    return {"order_quantity": float("nan")}

if __name__ == "__main__":
    Path("submission.json").write_text(json.dumps(solve()))
# EVOLVE-BLOCK-END
'''


def test_disruption_eoqd_forged_anchor_is_ignored() -> None:
    """Extra anchor fields in the submission cannot move the score."""
    with task_env("disruption_eoqd") as env:
        env.write_candidate(DISRUPTION_FORGED_ANCHOR)
        comparison = env.run()
        # 115.0829... is exactly the honest baseline's Q, so with a
        # scorer-computed anchor the forged fields buy nothing at all.
        assert comparison["baseline_final_score"] == PUBLISHED_SCORE["disruption_eoqd"]
        assert comparison["baseline_final_score"] < 1.0


def test_disruption_eoqd_nan_quantity_is_rejected() -> None:
    with task_env("disruption_eoqd") as env:
        env.write_candidate(DISRUPTION_NAN)
        comparison = env.run()
        assert comparison["baseline_final_score"] == 0.0
        assert "finite" in comparison["candidate_error"]


# --------------------------------------------------------------------------
# tree_gsm_safety_stock: the two-faced dict cannot survive a JSON round-trip.
# --------------------------------------------------------------------------

# Archived gpt-5.4 returned a dict subclass that used inspect.stack() to show
# an SLA-compliant CST to the SLA check and an aggressive CST to the stockpyl
# cost function, scoring 1.0. Re-implemented here (never imported from the
# archive) and pointed at the new JSON contract.
TREE_GSM_TWO_FACED = '''# EVOLVE-BLOCK-START
import inspect
import json
from pathlib import Path

VISIBLE_CST = {1: 0, 2: 0, 3: 0, 4: 1}
COST_CST = {1: 3, 2: 5, 3: 4, 4: 5}


class AdaptiveCST(dict):
    def __init__(self):
        super().__init__(COST_CST)

    @staticmethod
    def _in_cost_context():
        for frame_info in inspect.stack(context=0):
            if frame_info.frame.f_globals.get("__name__", "") == "stockpyl.gsm_helpers":
                return True
        return False

    def __getitem__(self, key):
        if self._in_cost_context():
            return dict.__getitem__(self, key)
        return VISIBLE_CST[key]

    def items(self):
        if self._in_cost_context():
            return dict.items(self)
        return VISIBLE_CST.items()


def solve(_unused=None):
    return AdaptiveCST()


if __name__ == "__main__":
    cst = solve()
    Path("submission.json").write_text(
        json.dumps({"cst": {str(k): int(v) for k, v in dict.items(cst)}})
    )
# EVOLVE-BLOCK-END
'''

TREE_GSM_OUT_OF_RANGE = '''# EVOLVE-BLOCK-START
import json
from pathlib import Path

if __name__ == "__main__":
    Path("submission.json").write_text(
        json.dumps({"cst": {"1": 999999, "2": 0, "3": 0, "4": 1}})
    )
# EVOLVE-BLOCK-END
'''

TREE_GSM_NON_INTEGER = '''# EVOLVE-BLOCK-START
import json
from pathlib import Path

if __name__ == "__main__":
    Path("submission.json").write_text(
        json.dumps({"cst": {"1": 3.5, "2": 0, "3": 0, "4": 1}})
    )
# EVOLVE-BLOCK-END
'''


def test_tree_gsm_two_faced_cst_cannot_score_one() -> None:
    """The stack-sniffing dict collapses to a single CST once it is JSON.

    The aggressive profile it used to hide from the SLA check is now the CST
    it is actually scored on, so it pays the SLA and complexity penalties
    instead of scoring 1.0.
    """
    with task_env("tree_gsm_safety_stock") as env:
        env.write_candidate(TREE_GSM_TWO_FACED)
        comparison = env.run()
        score = comparison["baseline_final_score"]
        assert score < 1.0, "two-faced CST still saturated the score"

        result = json.loads(env.output_bytes("baseline_result.json").decode("utf-8"))
        metrics = result["metrics"]
        # One CST, scored consistently: the aggressive profile that drives
        # cost/robustness to 1.0 is the same one the SLA check sees.
        assert result["solution_cst"] == {"1": 3, "2": 5, "3": 4, "4": 5}
        assert metrics["cost_score"] == 1.0
        assert metrics["robustness_score"] == 1.0
        assert metrics["sla_compliance"] == 0.0
        assert metrics["complexity_score"] == 0.0
        assert score == pytest.approx(0.70)


def test_tree_gsm_out_of_range_cst_is_rejected() -> None:
    with task_env("tree_gsm_safety_stock") as env:
        env.write_candidate(TREE_GSM_OUT_OF_RANGE)
        comparison = env.run()
        assert comparison["baseline_final_score"] == 0.0
        assert "out of range" in comparison["candidate_error"]


def test_tree_gsm_non_integer_cst_is_rejected() -> None:
    with task_env("tree_gsm_safety_stock") as env:
        env.write_candidate(TREE_GSM_NON_INTEGER)
        comparison = env.run()
        assert comparison["baseline_final_score"] == 0.0
        assert "must be an integer" in comparison["candidate_error"]


# --------------------------------------------------------------------------
# finite_horizon_dp / general_meio: the archived programs over-fit the fixed
# seed rather than forging anything, so what is pinned here is the isolation
# itself plus scorer-owned validation.
# --------------------------------------------------------------------------

# Archived shinkaevolve/claude-opus-4.6 walked up from __file__ to read
# ../verification/reference.py and regex the DP parameters out of its source.
# This canary submits a *valid* policy only when that path is unreachable, so
# a passing assertion means the reference stayed out of reach.
FINITE_HORIZON_REFERENCE_PROBE = '''# EVOLVE-BLOCK-START
import json
import os
from pathlib import Path


def _reference_is_reachable():
    try:
        import verification.reference  # noqa: F401
        return True
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in (
        "verification/reference.py",
        "../verification/reference.py",
        os.path.join(here, "..", "verification", "reference.py"),
        os.path.join(here, "..", "verification", "evaluate.py"),
    ):
        if os.path.exists(rel):
            return True
    return False


def solve(demand_mean, demand_sd):
    s_levels = [round(0.60 * m) for m in demand_mean]
    S_levels = []
    for i, (m, sd) in enumerate(zip(demand_mean, demand_sd)):
        S_levels.append(max(round(m + 1.10 * sd + 32), s_levels[i] + 6))
    return s_levels, S_levels


if __name__ == "__main__":
    cfg = json.loads(Path("config.json").read_text())
    s_levels, S_levels = solve(cfg["demand_mean"], cfg["demand_sd"])
    if _reference_is_reachable():
        # Deliberately invalid, so a reachable reference fails the test loudly.
        s_levels = [-1] * len(s_levels)
    Path("submission.json").write_text(
        json.dumps({"reorder_points": s_levels, "order_up_to_levels": S_levels})
    )
# EVOLVE-BLOCK-END
'''

FINITE_HORIZON_INVERTED_SS = '''# EVOLVE-BLOCK-START
import json
from pathlib import Path

if __name__ == "__main__":
    Path("submission.json").write_text(
        json.dumps(
            {
                "reorder_points": [500] * 8,
                "order_up_to_levels": [10] * 8,
            }
        )
    )
# EVOLVE-BLOCK-END
'''

FINITE_HORIZON_WRONG_LENGTH = '''# EVOLVE-BLOCK-START
import json
from pathlib import Path

if __name__ == "__main__":
    Path("submission.json").write_text(
        json.dumps({"reorder_points": [24, 27], "order_up_to_levels": [81, 87]})
    )
# EVOLVE-BLOCK-END
'''


def test_finite_horizon_dp_reference_is_unreachable() -> None:
    """The candidate subprocess cannot import or read the reference solver."""
    with task_env("finite_horizon_dp") as env:
        env.write_candidate(FINITE_HORIZON_REFERENCE_PROBE)
        comparison = env.run()
        assert "candidate_error" not in comparison, (
            "probe reached verification/reference.py from the candidate sandbox: "
            f"{comparison.get('candidate_error')}"
        )
        assert comparison["baseline_final_score"] == PUBLISHED_SCORE["finite_horizon_dp"]


def test_finite_horizon_dp_inverted_ss_is_rejected() -> None:
    with task_env("finite_horizon_dp") as env:
        env.write_candidate(FINITE_HORIZON_INVERTED_SS)
        comparison = env.run()
        assert comparison["baseline_final_score"] == 0.0
        assert "must be <=" in comparison["candidate_error"]


def test_finite_horizon_dp_wrong_length_is_rejected() -> None:
    with task_env("finite_horizon_dp") as env:
        env.write_candidate(FINITE_HORIZON_WRONG_LENGTH)
        comparison = env.run()
        assert comparison["baseline_final_score"] == 0.0
        assert "list of 8" in comparison["candidate_error"]


GENERAL_MEIO_REFERENCE_PROBE = '''# EVOLVE-BLOCK-START
import json
import os
from pathlib import Path


def _reference_is_reachable():
    try:
        import verification.reference  # noqa: F401
        return True
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in (
        "verification/reference.py",
        "../verification/reference.py",
        os.path.join(here, "..", "verification", "reference.py"),
    ):
        if os.path.exists(rel):
            return True
    return False


def solve():
    return {10: 26, 20: 14, 30: 14, 40: 16, 50: 14}


if __name__ == "__main__":
    levels = solve()
    if _reference_is_reachable():
        levels = {10: -1, 20: -1, 30: -1, 40: -1, 50: -1}
    Path("submission.json").write_text(
        json.dumps({"base_stock": {str(k): int(v) for k, v in levels.items()}})
    )
# EVOLVE-BLOCK-END
'''

GENERAL_MEIO_MISSING_NODE = '''# EVOLVE-BLOCK-START
import json
from pathlib import Path

if __name__ == "__main__":
    Path("submission.json").write_text(
        json.dumps({"base_stock": {"10": 26, "20": 14, "30": 14, "40": 16}})
    )
# EVOLVE-BLOCK-END
'''

GENERAL_MEIO_NEGATIVE = '''# EVOLVE-BLOCK-START
import json
from pathlib import Path

if __name__ == "__main__":
    Path("submission.json").write_text(
        json.dumps(
            {"base_stock": {"10": -5, "20": 14, "30": 14, "40": 16, "50": 14}}
        )
    )
# EVOLVE-BLOCK-END
'''


def test_general_meio_reference_is_unreachable() -> None:
    """The candidate subprocess cannot import or read the reference solver."""
    with task_env("general_meio") as env:
        env.write_candidate(GENERAL_MEIO_REFERENCE_PROBE)
        comparison = env.run()
        assert "candidate_error" not in comparison, (
            "probe reached verification/reference.py from the candidate sandbox: "
            f"{comparison.get('candidate_error')}"
        )
        assert comparison["baseline_final_score"] == PUBLISHED_SCORE["general_meio"]


def test_general_meio_missing_node_is_rejected() -> None:
    with task_env("general_meio") as env:
        env.write_candidate(GENERAL_MEIO_MISSING_NODE)
        comparison = env.run()
        assert comparison["baseline_final_score"] == 0.0
        assert "exactly keys" in comparison["candidate_error"]


def test_general_meio_negative_base_stock_is_rejected() -> None:
    with task_env("general_meio") as env:
        env.write_candidate(GENERAL_MEIO_NEGATIVE)
        comparison = env.run()
        assert comparison["baseline_final_score"] == 0.0
        assert "out of range" in comparison["candidate_error"]


# --------------------------------------------------------------------------
# Shared contract: a candidate that never produces a submission scores 0.
# --------------------------------------------------------------------------

CRASHING_CANDIDATE = '''# EVOLVE-BLOCK-START
raise SystemExit("candidate blew up before writing anything")
# EVOLVE-BLOCK-END
'''

NO_SUBMISSION_CANDIDATE = '''# EVOLVE-BLOCK-START
print("I decline to submit")
# EVOLVE-BLOCK-END
'''


@pytest.mark.parametrize(
    "task_name",
    ["disruption_eoqd", "finite_horizon_dp", "general_meio", "tree_gsm_safety_stock"],
)
def test_crashing_candidate_scores_zero(task_name: str) -> None:
    with task_env(task_name) as env:
        env.write_candidate(CRASHING_CANDIDATE)
        comparison = env.run()
        assert comparison["baseline_final_score"] == 0.0
        assert comparison["candidate_error"]


@pytest.mark.parametrize(
    "task_name",
    ["disruption_eoqd", "finite_horizon_dp", "general_meio", "tree_gsm_safety_stock"],
)
def test_missing_submission_scores_zero(task_name: str) -> None:
    with task_env(task_name) as env:
        env.write_candidate(NO_SUBMISSION_CANDIDATE)
        comparison = env.run()
        assert comparison["baseline_final_score"] == 0.0
        assert "submission.json" in comparison["candidate_error"]
