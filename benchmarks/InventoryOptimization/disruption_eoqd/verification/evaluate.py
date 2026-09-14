#!/usr/bin/env python3
"""Evaluate baseline(init) vs reference(stockpyl) for Task 05."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from stockpyl.supply_uncertainty import eoq_with_disruptions_cost

TASK_DIR = Path(__file__).resolve().parents[1]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

# The candidate now runs in its own subprocess and writes submission.json, so
# we never exec_module/import it into this process. Bring in the isolation
# helper from the shared location; it sits outside any benchmark dir so a
# copy_files.txt of "." cannot drag it into the sandbox. The repo root is
# located via the env var the harness sets, falling back to walking up.
def _find_repo_root() -> Path:
    env_root = (__import__("os").environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    raise RuntimeError("could not locate repo root for disruption_eoqd evaluator")


_REPO = _find_repo_root()
if str(_REPO / "benchmarks" / "_shared") not in sys.path:
    sys.path.insert(0, str(_REPO / "benchmarks" / "_shared"))
import candidate_sandbox as sandbox  # noqa: E402

from verification.reference import solve as solve_reference  # noqa: E402


def clip(x: float) -> float:
    """NaN-safe clip to [0, 1] (max/min with NaN silently pass NaN through)."""
    xf = float(x)
    if not math.isfinite(xf):
        return 0.0
    return max(0.0, min(1.0, xf))


def classic_eoq(fixed_cost: float, holding_cost: float, demand_rate: float) -> float:
    return math.sqrt(2.0 * fixed_cost * demand_rate / holding_cost)


def simulate_q_policy(
    order_quantity: float,
    demand_rate: float,
    disruption_rate: float,
    recovery_rate: float,
    seed: int,
    periods: int,
):
    rng = np.random.default_rng(seed)
    alpha = 1.0 - math.exp(-disruption_rate)
    beta = 1.0 - math.exp(-recovery_rate)

    inv = float(order_quantity)
    disrupted = False
    total_demand = 0.0
    total_fill = 0.0
    stockout_events = 0
    avg_on_hand = 0.0

    for _ in range(periods):
        if disrupted:
            disrupted = not (rng.random() < beta)
        else:
            disrupted = rng.random() < alpha

        if inv <= 0 and not disrupted:
            inv += order_quantity

        demand = float(rng.poisson(demand_rate))
        fill = min(max(inv, 0.0), demand)

        total_demand += demand
        total_fill += fill
        if fill < demand:
            stockout_events += 1

        inv -= demand
        avg_on_hand += max(inv, 0.0)

    return {
        "fill_rate": total_fill / max(total_demand, 1e-9),
        "stockout_event_rate": stockout_events / periods,
        "avg_on_hand": avg_on_hand / periods,
    }


def score_solution(solution_q: float, q_baseline: float, cfg: dict):
    baseline_model_cost = float(
        eoq_with_disruptions_cost(
            q_baseline,
            cfg["fixed_cost"],
            cfg["holding_cost"],
            cfg["stockout_cost"],
            cfg["demand_rate"],
            cfg["disruption_rate"],
            cfg["recovery_rate"],
            approximate=False,
        )
    )

    solution_model_cost = float(
        eoq_with_disruptions_cost(
            solution_q,
            cfg["fixed_cost"],
            cfg["holding_cost"],
            cfg["stockout_cost"],
            cfg["demand_rate"],
            cfg["disruption_rate"],
            cfg["recovery_rate"],
            approximate=False,
        )
    )

    baseline_sim = simulate_q_policy(
        order_quantity=q_baseline,
        demand_rate=cfg["demand_rate"],
        disruption_rate=cfg["disruption_rate"],
        recovery_rate=cfg["recovery_rate"],
        seed=2026,
        periods=720,
    )

    solution_sim = simulate_q_policy(
        order_quantity=solution_q,
        demand_rate=cfg["demand_rate"],
        disruption_rate=cfg["disruption_rate"],
        recovery_rate=cfg["recovery_rate"],
        seed=2026,
        periods=720,
    )

    cost_score = clip(
        (baseline_model_cost - solution_model_cost)
        / (baseline_model_cost - baseline_model_cost * 0.985)
    )
    service_score = clip((solution_sim["fill_rate"] - 0.25) / (0.60 - 0.25))
    risk_score = clip(
        (baseline_sim["stockout_event_rate"] - solution_sim["stockout_event_rate"])
        / (baseline_sim["stockout_event_rate"] - baseline_sim["stockout_event_rate"] * 0.85)
    )
    capital_score = clip((10.0 - solution_sim["avg_on_hand"]) / (10.0 - 2.0))

    final_score = (
        0.35 * cost_score
        + 0.35 * service_score
        + 0.25 * risk_score
        + 0.05 * capital_score
    )

    return {
        "baseline": {
            "order_quantity": q_baseline,
            "model_cost": baseline_model_cost,
            "simulation": baseline_sim,
        },
        "solution": {
            "order_quantity": solution_q,
            "model_cost": solution_model_cost,
            "simulation": solution_sim,
        },
        "metrics": {
            "cost_score": cost_score,
            "service_score": service_score,
            "risk_score": risk_score,
            "capital_score": capital_score,
        },
        "weights": {
            "cost_score": 0.35,
            "service_score": 0.35,
            "risk_score": 0.25,
            "capital_score": 0.05,
        },
        "final_score": final_score,
    }


class _Validation:
    """Validate the candidate's reported order quantity.

    The scorer computes ``q_classic``, the cost and risk normalization anchor, from
    the fixed configuration. Candidate output does not supply that reference value.
    """

    MAX_Q = 1.0e6

    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def validate(self, solution: dict) -> bool:
        if not isinstance(solution, dict):
            self.fail("submission must be a JSON object")
            return False

        q = solution.get("order_quantity")
        if isinstance(q, bool) or not isinstance(q, (int, float)):
            self.fail("order_quantity must be a number")
            return False
        qf = float(q)
        if not math.isfinite(qf):
            self.fail("order_quantity must be finite")
            return False
        if qf <= 0.0:
            self.fail(f"order_quantity must be positive, got {qf}")
            return False
        if qf > self.MAX_Q:
            self.fail(f"order_quantity too large: {qf} > {self.MAX_Q}")
            return False

        return not self.errors


def run_candidate(candidate_path: Path, cfg: dict) -> tuple[float | None, str]:
    """Run the candidate in a subprocess and return (order_quantity, error)."""
    try:
        run = sandbox.run_inventory_candidate(
            candidate_path, 'disruption_eoqd',
            inputs={"config.json": json.dumps(cfg).encode("utf-8")},
            expected_outputs=("submission.json",),
            timeout_s=60,
            # Copy the candidate into the sandbox and run it from there, so
            # sys.path[0] and __file__ both stay inside the throwaway workdir.
            # Running in place would leave __file__ pointing at
            # <task>/baseline/init.py, from which an archived candidate walked
            # up to read ../verification/reference.py.
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

    return float(submission["order_quantity"]), None


def main() -> None:
    output_dir = TASK_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "fixed_cost": 120.0,
        "holding_cost": 1.8,
        "stockout_cost": 14.0,
        "demand_rate": 80.0,
        "disruption_rate": 0.08,
        "recovery_rate": 0.35,
    }

    # Compute the scoring anchor from the evaluator's configuration.
    q_classic = classic_eoq(cfg["fixed_cost"], cfg["holding_cost"], cfg["demand_rate"])

    candidate_path = TASK_DIR / "baseline" / "init.py"
    q_manual, error_message = run_candidate(candidate_path, cfg)

    if q_manual is None:
        comparison = {
            "task": "disruption_eoqd",
            "baseline_final_score": 0.0,
            "reference_final_score": 0.0,
            "gap_reference_minus_baseline": 0.0,
            "winner": "reference",
            "candidate_error": error_message,
            "valid": False,
        }
        (output_dir / "comparison.json").write_text(
            json.dumps(comparison, indent=2), encoding="utf-8"
        )
        print(f"Candidate rejected: {error_message}")
        return

    q_reference = solve_reference(cfg)

    baseline_result = {
        "task": "disruption_eoqd",
        "method": "baseline",
        "algorithm": "classic EOQ with manual disruption multiplier",
        "safety_multiplier": q_manual / q_classic,
        **score_solution(q_manual, q_classic, cfg),
    }
    reference_result = {
        "task": "disruption_eoqd",
        "method": "reference",
        "algorithm": "stockpyl EOQD optimization",
        **score_solution(q_reference, q_classic, cfg),
    }

    comparison = {
        "task": "disruption_eoqd",
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
