#!/usr/bin/env python3
"""Evaluate baseline(init) vs reference(stockpyl) for Task 04."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

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
    raise RuntimeError("could not locate repo root for finite_horizon_dp evaluator")


_REPO = _find_repo_root()
if str(_REPO / "benchmarks" / "_shared") not in sys.path:
    sys.path.insert(0, str(_REPO / "benchmarks" / "_shared"))
import candidate_sandbox as sandbox  # noqa: E402

from verification.reference import solve as solve_reference  # noqa: E402

MAX_LEVEL = 1.0e6


def clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def run_monte_carlo(policy_kind: str, cfg: dict, seed: int, trials: int, s_levels=None, S_levels=None):
    rng = np.random.default_rng(seed)

    total_costs = []
    fill_rates = []
    order_counts = []

    for _ in range(trials):
        inv = float(cfg["initial_inventory_level"])
        total_cost = 0.0
        total_demand = 0.0
        total_fulfilled = 0.0
        placed_orders = 0

        for t in range(cfg["num_periods"]):
            if policy_kind == "baseline":
                order_qty = max(0.0, float(cfg["baseline_order_up_to"]) - inv)
            elif policy_kind == "manual":
                s_t = float(s_levels[t])
                S_t = float(S_levels[t])
                order_qty = max(0.0, S_t - inv) if inv <= s_t else 0.0
            else:  # dp
                s_t = float(s_levels[t + 1])
                S_t = float(S_levels[t + 1])
                order_qty = max(0.0, S_t - inv) if inv <= s_t else 0.0

            if order_qty > 0:
                total_cost += cfg["fixed_cost"]
                placed_orders += 1

            total_cost += cfg["purchase_cost"] * order_qty
            inv += order_qty

            demand = max(0.0, float(rng.normal(cfg["demand_mean"][t], cfg["demand_sd"][t])))
            fulfilled = min(max(inv, 0.0), demand)
            total_demand += demand
            total_fulfilled += fulfilled

            inv -= demand

            if inv >= 0:
                total_cost += cfg["holding_cost"] * inv
            else:
                total_cost += cfg["stockout_cost"] * (-inv)

        if inv >= 0:
            total_cost += cfg["terminal_holding_cost"] * inv
        else:
            total_cost += cfg["terminal_stockout_cost"] * (-inv)

        total_costs.append(total_cost)
        fill_rates.append(total_fulfilled / max(total_demand, 1e-9))
        order_counts.append(placed_orders)

    return {
        "avg_total_cost": float(np.mean(total_costs)),
        "avg_fill_rate": float(np.mean(fill_rates)),
        "avg_order_count": float(np.mean(order_counts)),
    }


def score_solution(policy_kind: str, cfg: dict, s_levels, S_levels):
    baseline_eval = run_monte_carlo("baseline", cfg, seed=42, trials=1500)

    if policy_kind == "manual":
        sol_eval = run_monte_carlo("manual", cfg, seed=42, trials=1500, s_levels=s_levels, S_levels=S_levels)
    else:
        sol_eval = run_monte_carlo("dp", cfg, seed=42, trials=1500, s_levels=s_levels, S_levels=S_levels)

    cost_score = clip(
        (baseline_eval["avg_total_cost"] - sol_eval["avg_total_cost"])
        / (baseline_eval["avg_total_cost"] - baseline_eval["avg_total_cost"] * 0.82)
    )
    service_score = clip((sol_eval["avg_fill_rate"] - 0.94) / (0.975 - 0.94))
    cadence_score = clip(
        (baseline_eval["avg_order_count"] - sol_eval["avg_order_count"])
        / (baseline_eval["avg_order_count"] - baseline_eval["avg_order_count"] * 0.60)
    )

    final_score = 0.55 * cost_score + 0.40 * service_score + 0.05 * cadence_score

    return {
        "baseline_eval": baseline_eval,
        "solution_eval": sol_eval,
        "metrics": {
            "cost_score": cost_score,
            "service_score": service_score,
            "cadence_score": cadence_score,
        },
        "weights": {
            "cost_score": 0.55,
            "service_score": 0.40,
            "cadence_score": 0.05,
        },
        "final_score": final_score,
    }


class _Validation:
    """Strict, scorer-owned checks on the candidate's reported (s, S) policy."""

    def __init__(self, num_periods: int) -> None:
        self.num_periods = num_periods
        self.errors: list[str] = []

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def _validate_level_list(self, name: str, values) -> list[float] | None:
        """Validate a level list, returning the entries with their original
        numeric types (an int stays an int) so the echoed policy in the result
        JSON matches what the candidate actually submitted."""
        if not isinstance(values, list) or len(values) != self.num_periods:
            self.fail(f"{name} must be a list of {self.num_periods} numbers")
            return None
        out = []
        for v in values:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                self.fail(f"{name} entries must be numbers, got {v!r}")
                return None
            vf = float(v)
            if not math.isfinite(vf):
                self.fail(f"{name} entries must be finite, got {v!r}")
                return None
            if vf < 0.0 or vf > MAX_LEVEL:
                self.fail(f"{name} entries must be in [0, {MAX_LEVEL}], got {vf}")
                return None
            out.append(v)
        return out

    def validate(self, submission: dict) -> tuple[list[float], list[float]] | None:
        if not isinstance(submission, dict):
            self.fail("submission must be a JSON object")
            return None

        s_levels = self._validate_level_list("reorder_points", submission.get("reorder_points"))
        S_levels = self._validate_level_list("order_up_to_levels", submission.get("order_up_to_levels"))
        if s_levels is None or S_levels is None:
            return None

        for t, (s_t, S_t) in enumerate(zip(s_levels, S_levels)):
            if s_t > S_t:
                self.fail(f"reorder_points[{t}]={s_t} must be <= order_up_to_levels[{t}]={S_t}")
                return None

        return s_levels, S_levels


def run_candidate(candidate_path: Path, cfg: dict) -> tuple[tuple[list[float], list[float]] | None, str]:
    """Run the candidate in a subprocess and return ((s, S), error_message)."""
    candidate_cfg = {
        "num_periods": cfg["num_periods"],
        "demand_mean": cfg["demand_mean"],
        "demand_sd": cfg["demand_sd"],
    }
    try:
        run = sandbox.run_inventory_candidate(
            candidate_path, 'finite_horizon_dp',
            inputs={"config.json": json.dumps(candidate_cfg).encode("utf-8")},
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

    validator = _Validation(cfg["num_periods"])
    policy = validator.validate(submission)
    if policy is None:
        return None, "; ".join(validator.errors)

    return policy, None


def main() -> None:
    output_dir = TASK_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "num_periods": 8,
        "holding_cost": 1.2,
        "stockout_cost": 8.0,
        "terminal_holding_cost": 0.8,
        "terminal_stockout_cost": 10.0,
        "purchase_cost": 3.5,
        "fixed_cost": 120.0,
        "demand_mean": [40, 45, 55, 80, 95, 70, 50, 45],
        "demand_sd": [8, 9, 12, 15, 18, 14, 10, 9],
        "initial_inventory_level": 30.0,
        "baseline_order_up_to": 85.0,
    }

    candidate_path = TASK_DIR / "baseline" / "init.py"
    policy, error_message = run_candidate(candidate_path, cfg)

    if policy is None:
        comparison = {
            "task": "finite_horizon_dp",
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

    s_manual, S_manual = policy
    s_ref, S_ref, dp_expected_cost = solve_reference(cfg)

    baseline_result = {
        "task": "finite_horizon_dp",
        "method": "baseline",
        "algorithm": "manual moment-based policy",
        "policy": {
            "reorder_points": s_manual,
            "order_up_to_levels": S_manual,
        },
        **score_solution("manual", cfg, s_manual, S_manual),
    }
    reference_result = {
        "task": "finite_horizon_dp",
        "method": "reference",
        "algorithm": "stockpyl finite-horizon DP",
        "policy": {
            "reorder_points": [float(x) for x in s_ref],
            "order_up_to_levels": [float(x) for x in S_ref],
            "dp_expected_cost": dp_expected_cost,
        },
        **score_solution("dp", cfg, s_ref, S_ref),
    }

    comparison = {
        "task": "finite_horizon_dp",
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
