#!/usr/bin/env python3
"""Evaluate baseline(init) vs reference(stockpyl) for Task 03."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[1]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

# The candidate now runs in its own subprocess and writes submission.json, so
# we never exec_module it into this process. Bring in the isolation helper from
# the shared location; it sits outside any benchmark dir so copy_files.txt of "."
# cannot drag it into the sandbox. The repo root is three levels up from this
# file (verification/<benchmark>/<domain>/benchmarks/../). Locate it robustly
# via the env var the harness sets, then fall back to walking up.
def _find_repo_root() -> Path:
    env_root = (__import__("os").environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    raise RuntimeError("could not locate repo root for joint_replenishment evaluator")


_REPO = _find_repo_root()
if str(_REPO / "benchmarks" / "_shared") not in sys.path:
    sys.path.insert(0, str(_REPO / "benchmarks" / "_shared"))
import candidate_sandbox as sandbox  # noqa: E402

from verification.reference import solve as solve_reference  # noqa: E402


class _Validation:
    """Strict, scorer-owned checks on the candidate's reported solution."""

    N_ITEMS = 8
    MAX_CYCLE = 100.0
    MAX_MULTIPLE = 1000

    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def validate(self, solution: dict) -> bool:
        if not isinstance(solution, dict):
            self.fail("submission must be a JSON object")
            return False

        base_cycle = solution.get("base_cycle_time")
        multiples = solution.get("order_multiples")

        if isinstance(base_cycle, bool) or not isinstance(base_cycle, (int, float)):
            self.fail("base_cycle_time must be a number")
        elif not math.isfinite(float(base_cycle)):
            self.fail("base_cycle_time must be finite")
        elif float(base_cycle) <= 0.0:
            self.fail(f"base_cycle_time must be positive, got {base_cycle}")
        elif float(base_cycle) > self.MAX_CYCLE:
            self.fail(f"base_cycle_time too large: {base_cycle} > {self.MAX_CYCLE}")

        if not isinstance(multiples, list) or len(multiples) != self.N_ITEMS:
            self.fail(f"order_multiples must be a list of {self.N_ITEMS} items")
            return False
        for m in multiples:
            if isinstance(m, bool) or not isinstance(m, int):
                self.fail(f"order_multiples entries must be integers, got {m!r}")
                return False
            if m < 1 or m > self.MAX_MULTIPLE:
                self.fail(f"order_multiples entries must be in [1, {self.MAX_MULTIPLE}], got {m}")
                return False

        return not self.errors


def clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def independent_eoq_cost(shared_fixed_cost, individual_fixed_costs, holding_costs, demand_rates):
    qs = []
    cycles = []
    total_cost = 0.0

    for k_i, h_i, d_i in zip(individual_fixed_costs, holding_costs, demand_rates):
        k_total = shared_fixed_cost + k_i
        q_i = math.sqrt(2.0 * k_total * d_i / h_i)
        c_i = k_total * d_i / q_i + h_i * q_i / 2.0
        qs.append(q_i)
        cycles.append(q_i / d_i)
        total_cost += c_i

    return qs, cycles, total_cost


def policy_cost(shared_fixed_cost, individual_fixed_costs, holding_costs, demand_rates, base_cycle, multiples):
    total_cost = shared_fixed_cost / base_cycle
    for k_i, h_i, d_i, m_i in zip(individual_fixed_costs, holding_costs, demand_rates, multiples):
        total_cost += k_i / (m_i * base_cycle) + h_i * d_i * (m_i * base_cycle) / 2.0
    return total_cost


def score_solution(solution: dict):
    shared_fixed_cost = 100.0
    individual_fixed_costs = [40.0, 35.0, 30.0, 28.0, 25.0, 22.0, 20.0, 18.0]
    holding_costs = [1.8, 2.0, 1.6, 1.7, 1.5, 1.9, 2.1, 1.4]
    demand_rates = [120.0, 90.0, 60.0, 40.0, 25.0, 18.0, 12.0, 8.0]

    base_q, base_cycles, baseline_cost = independent_eoq_cost(
        shared_fixed_cost,
        individual_fixed_costs,
        holding_costs,
        demand_rates,
    )

    cycle_times = [m * solution["base_cycle_time"] for m in solution["order_multiples"]]
    sol_cost = policy_cost(
        shared_fixed_cost,
        individual_fixed_costs,
        holding_costs,
        demand_rates,
        solution["base_cycle_time"],
        solution["order_multiples"],
    )

    cost_score = clip((baseline_cost - sol_cost) / (baseline_cost - baseline_cost * 0.50))
    responsiveness_score = clip((2.6 - max(cycle_times)) / (2.6 - 1.8))
    coordination_score = clip((len(demand_rates) - len(set(solution["order_multiples"]))) / (len(demand_rates) - 1))

    final_score = 0.55 * cost_score + 0.30 * responsiveness_score + 0.15 * coordination_score

    return {
        "inputs": {
            "shared_fixed_cost": shared_fixed_cost,
            "individual_fixed_costs": individual_fixed_costs,
            "holding_costs": holding_costs,
            "demand_rates": demand_rates,
        },
        "independent_reference": {
            "order_quantities": base_q,
            "cycle_times": base_cycles,
            "cost": baseline_cost,
        },
        "solution": {
            "base_cycle_time": solution["base_cycle_time"],
            "order_multiples": solution["order_multiples"],
            "order_quantities": solution["order_quantities"],
            "cycle_times": cycle_times,
            "cost": sol_cost,
        },
        "metrics": {
            "cost_score": cost_score,
            "responsiveness_score": responsiveness_score,
            "coordination_score": coordination_score,
        },
        "weights": {
            "cost_score": 0.55,
            "responsiveness_score": 0.30,
            "coordination_score": 0.15,
        },
        "final_score": final_score,
    }


def run_candidate(candidate_path: Path) -> tuple[dict | None, str]:
    """Run the candidate in a subprocess and return (submission, error_message)."""
    try:
        run = sandbox.run_candidate_isolated(
            candidate_path,
            expected_outputs=("submission.json",),
            timeout_s=60,
            # Copy the candidate into the sandbox: running it in place leaves
            # __file__ pointing at the task tree, so ../verification/reference.py
            # stays readable -- the exact path an archived submission used.
            copy_into_workdir=True,
        )
    except sandbox.InvalidSubmissionError as exc:
        return None, str(exc)
    if run.timed_out:
        return None, "candidate timed out"
    if run.returncode != 0:
        return None, f"candidate exited non-zero ({run.returncode})"

    try:
        submission = sandbox.load_json_output(run)
    except sandbox.InvalidSubmissionError as exc:
        return None, str(exc)

    validator = _Validation()
    if not validator.validate(submission):
        return None, "; ".join(validator.errors)

    # The scorer recomputes the quantities it depends on, so a candidate cannot
    # make its own order_quantities / cycle_times disagree with its reported
    # base cycle and multiples.
    submission["order_quantities"] = [
        d * m * float(submission["base_cycle_time"])
        for d, m in zip(
            [120.0, 90.0, 60.0, 40.0, 25.0, 18.0, 12.0, 8.0],
            submission["order_multiples"],
        )
    ]
    return submission, None


def main() -> None:
    output_dir = TASK_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_path = TASK_DIR / "baseline" / "init.py"
    submission, error_message = run_candidate(candidate_path)

    if submission is None:
        # No valid candidate: emit a clearly invalid comparison so the harness
        # scores 0 rather than trusting anything the candidate reported.
        comparison = {
            "task": "joint_replenishment",
            "baseline_final_score": 0.0,
            "reference_final_score": 0.0,
            "gap_reference_minus_baseline": 0.0,
            "winner": "reference",
            "candidate_error": error_message,
        }
        (output_dir / "comparison.json").write_text(
            json.dumps(comparison, indent=2), encoding="utf-8"
        )
        print(f"Candidate rejected: {error_message}")
        return

    baseline_result = {
        "task": "joint_replenishment",
        "method": "baseline",
        "algorithm": "candidate submission",
        **score_solution(submission),
    }

    reference_solution = solve_reference()
    reference_result = {
        "task": "joint_replenishment",
        "method": "reference",
        "algorithm": "stockpyl Silver JRP heuristic",
        **score_solution(reference_solution),
    }

    comparison = {
        "task": "joint_replenishment",
        "baseline_final_score": baseline_result["final_score"],
        "reference_final_score": reference_result["final_score"],
        "gap_reference_minus_baseline": reference_result["final_score"] - baseline_result["final_score"],
        "winner": "reference"
        if reference_result["final_score"] >= baseline_result["final_score"]
        else "baseline",
    }

    (output_dir / "baseline_result.json").write_text(json.dumps(baseline_result, indent=2), encoding="utf-8")
    (output_dir / "reference_result.json").write_text(json.dumps(reference_result, indent=2), encoding="utf-8")
    (output_dir / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    print(f"Baseline score:  {baseline_result['final_score']:.4f}")
    print(f"Reference score: {reference_result['final_score']:.4f}")
    print(f"Gap:             {comparison['gap_reference_minus_baseline']:.4f}")
    print(f"Saved outputs to {output_dir}")


if __name__ == "__main__":
    main()
