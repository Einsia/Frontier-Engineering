#!/usr/bin/env python3
"""Evaluate baseline(init) vs reference(stockpyl) for Task 02."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from stockpyl.sim import simulation
from stockpyl.supply_chain_network import network_from_edges

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
    raise RuntimeError("could not locate repo root for general_meio evaluator")


_REPO = _find_repo_root()
if str(_REPO / "benchmarks" / "_shared") not in sys.path:
    sys.path.insert(0, str(_REPO / "benchmarks" / "_shared"))
import candidate_sandbox as sandbox  # noqa: E402

from verification.reference import solve as solve_reference  # noqa: E402

SINK_NODES = [40, 50]
STOCKOUT_COST = {10: 0.0, 20: 0.0, 30: 0.0, 40: 10.0, 50: 9.0}
NODE_IDS = (10, 20, 30, 40, 50)
MAX_BASE_STOCK = 100_000


def clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def build_network(demand_scale: float = 1.0):
    return network_from_edges(
        edges=[(10, 20), (10, 30), (20, 40), (30, 40), (20, 50), (30, 50)],
        node_order_in_lists=[10, 20, 30, 40, 50],
        shipment_lead_time={10: 1, 20: 1, 30: 1, 40: 0, 50: 0},
        local_holding_cost={10: 0.2, 20: 0.4, 30: 0.4, 40: 0.9, 50: 0.9},
        stockout_cost=STOCKOUT_COST,
        policy_type="BS",
        base_stock_level={10: 30, 20: 18, 30: 18, 40: 20, 50: 20},
        demand_type={40: "P", 50: "P"},
        mean={40: 8 * demand_scale, 50: 7 * demand_scale},
        standard_deviation={40: 3 * demand_scale, 50: 2.5 * demand_scale},
        supply_type={10: "U"},
    )


def evaluate_policy(base_stock_levels: dict[int, int], demand_scale: float, periods: int, seed: int):
    net = build_network(demand_scale)
    for n in net.nodes:
        n.inventory_policy.base_stock_level = base_stock_levels[n.index]

    simulation(net, num_periods=periods, rand_seed=seed, progress_bar=False)

    total_cost = 0.0
    holding_cost = 0.0
    stockout_cost = 0.0
    shortage_units = {k: 0.0 for k in SINK_NODES}

    expected_demand = {
        40: 8 * demand_scale * periods,
        50: 7 * demand_scale * periods,
    }

    for idx in net.node_indices:
        node = net.nodes_by_index[idx]
        for sv in node.state_vars[:periods]:
            total_cost += float(sv.total_cost_incurred)
            holding_cost += float(sv.holding_cost_incurred)
            stockout_cost += float(sv.stockout_cost_incurred)
            if idx in SINK_NODES and STOCKOUT_COST[idx] > 0:
                shortage_units[idx] += float(sv.stockout_cost_incurred) / STOCKOUT_COST[idx]

    fill_by_sink = {
        idx: clip(1.0 - shortage_units[idx] / max(expected_demand[idx], 1e-9)) for idx in SINK_NODES
    }
    weighted_fill = (
        fill_by_sink[40] * expected_demand[40] + fill_by_sink[50] * expected_demand[50]
    ) / (expected_demand[40] + expected_demand[50])

    return {
        "cost_per_period": total_cost / periods,
        "holding_per_period": holding_cost / periods,
        "stockout_per_period": stockout_cost / periods,
        "fill_rate": weighted_fill,
        "fill_by_sink": fill_by_sink,
    }


def score_solution(solution_s: dict[int, int]):
    baseline = {10: 30, 20: 18, 30: 18, 40: 20, 50: 20}

    base_nom = evaluate_policy(baseline, 1.0, 160, 11)
    sol_nom = evaluate_policy(solution_s, 1.0, 160, 11)
    base_stress = evaluate_policy(baseline, 1.2, 160, 17)
    sol_stress = evaluate_policy(solution_s, 1.2, 160, 17)

    cost_score = clip(
        (base_nom["cost_per_period"] - sol_nom["cost_per_period"])
        / (base_nom["cost_per_period"] - base_nom["cost_per_period"] * 0.65)
    )
    service_score = clip((sol_nom["fill_rate"] - 0.98) / (0.995 - 0.98))
    robustness_score = clip(
        (base_stress["cost_per_period"] - sol_stress["cost_per_period"])
        / (base_stress["cost_per_period"] - base_stress["cost_per_period"] * 0.85)
    )
    fill_gap = abs(sol_nom["fill_by_sink"][40] - sol_nom["fill_by_sink"][50])
    balance_score = clip(1.0 - fill_gap / 0.05)

    final_score = (
        0.30 * cost_score
        + 0.35 * service_score
        + 0.25 * robustness_score
        + 0.10 * balance_score
    )

    return {
        "solution_base_stock": solution_s,
        "nominal": {"baseline": base_nom, "solution": sol_nom},
        "stress": {"baseline": base_stress, "solution": sol_stress},
        "metrics": {
            "cost_score": cost_score,
            "service_score": service_score,
            "robustness_score": robustness_score,
            "balance_score": balance_score,
        },
        "weights": {
            "cost_score": 0.30,
            "service_score": 0.35,
            "robustness_score": 0.25,
            "balance_score": 0.10,
        },
        "final_score": final_score,
    }


class _Validation:
    """Strict, scorer-owned checks on the candidate's reported base-stock policy."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def validate_and_normalize(self, submission: dict) -> dict[int, int] | None:
        if not isinstance(submission, dict):
            self.fail("submission must be a JSON object")
            return None

        raw = submission.get("base_stock")
        if not isinstance(raw, dict):
            self.fail("submission['base_stock'] must be a JSON object")
            return None

        normalized: dict[int, int] = {}
        for key, value in raw.items():
            try:
                node_id = int(key)
            except (TypeError, ValueError):
                self.fail(f"base_stock key {key!r} is not an integer node id")
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                self.fail(f"base_stock[{key!r}] must be an integer, got {value!r}")
                continue
            if value < 0 or value > MAX_BASE_STOCK:
                self.fail(f"base_stock[{key!r}]={value} out of range [0, {MAX_BASE_STOCK}]")
                continue
            normalized[node_id] = int(value)

        if self.errors:
            return None

        if set(normalized) != set(NODE_IDS):
            self.fail(f"base_stock must have exactly keys {sorted(NODE_IDS)}, got {sorted(normalized)}")
            return None

        return normalized


def run_candidate(candidate_path: Path) -> tuple[dict[int, int] | None, str]:
    """Run the candidate in a subprocess and return (base_stock, error_message)."""
    try:
        run = sandbox.run_inventory_candidate(
            candidate_path, 'general_meio',
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
    base_stock = validator.validate_and_normalize(submission)
    if base_stock is None:
        return None, "; ".join(validator.errors)

    return base_stock, None


def main() -> None:
    output_dir = TASK_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_path = TASK_DIR / "baseline" / "init.py"
    baseline_solution, error_message = run_candidate(candidate_path)

    if baseline_solution is None:
        comparison = {
            "task": "general_meio",
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

    reference_solution = solve_reference()

    baseline_result = {
        "task": "general_meio",
        "method": "baseline",
        "algorithm": "manual demand-coverage rule",
        **score_solution(baseline_solution),
    }
    reference_result = {
        "task": "general_meio",
        "method": "reference",
        "algorithm": "stockpyl MEIO enumeration",
        **score_solution(reference_solution),
    }

    comparison = {
        "task": "general_meio",
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
