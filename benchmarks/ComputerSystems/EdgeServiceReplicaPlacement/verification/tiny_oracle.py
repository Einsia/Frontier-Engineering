"""Independent brute-force oracle for a three-period, two-node control case."""

from __future__ import annotations

from itertools import product
import json
import math
from typing import Any, Iterable

try:
    from .simulator import ScenarioTrace, load_config
except ImportError:
    from simulator import ScenarioTrace, load_config


NODES = ("n1", "n2")
ROUTE_GRID = (0.0, 0.5, 1.0)
TINY_CONFIG: dict[str, Any] = {
    "model_version": "tiny-oracle-v1",
    "period_minutes": 5,
    "regions": ["tiny"],
    "nodes": [
        {"id": "n1", "region": "tiny", "failure_domain": "rack-1", "cpu_capacity": 1.0},
        {"id": "n2", "region": "tiny", "failure_domain": "rack-2", "cpu_capacity": 1.0},
    ],
    "services": [
        {
            "id": "svc",
            "cpu_per_replica": 1.0,
            "service_rate_rps": 2.0,
            "base_latency_ms": 10.0,
            "p99_slo_ms": 50.0,
            "response_mb": 0.01,
            "reliability_class": "critical",
        }
    ],
    "network_rtt_ms": {"tiny": {"tiny": 5.0}},
    "cross_region_bandwidth_mb_per_period": 1000.0,
    "compute_cost_per_replica_period": 0.1,
    "pending_replica_cost_factor": 0.5,
    "cross_region_cost_per_gb": 0.08,
}
TINY_SCENARIO = ScenarioTrace(
    name="tiny-three-period-control",
    family="tiny_oracle",
    seed=0,
    feedback=True,
    workloads=(
        {"tiny": {"svc": 1.0}},
        {"tiny": {"svc": 3.0}},
        {"tiny": {"svc": 3.0}},
    ),
    failed_nodes=(frozenset(), frozenset(), frozenset()),
    link_factors=({}, {}, {}),
    recovery_start=None,
)


def _target_nodes(action: dict[str, Any]) -> frozenset[str]:
    return frozenset(item["node_id"] for item in action["replicas"] if item["count"] == 1)


def _placement_options() -> Iterable[frozenset[str]]:
    for mask in range(1 << len(NODES)):
        yield frozenset(node for index, node in enumerate(NODES) if mask & (1 << index))


def action_options(active: frozenset[str]) -> list[dict[str, Any]]:
    """Enumerate the complete discrete action set used by this oracle.

    Placement is binary per node. Route fractions use the declared {0, 0.5, 1} grid;
    therefore "all feasible" in this oracle means all hard-valid trajectories on that
    finite grid, not every real-valued route fraction.
    """

    actions: list[dict[str, Any]] = []
    for target in _placement_options():
        retained = tuple(sorted(active & target))
        route_vectors = product(ROUTE_GRID, repeat=len(retained)) if retained else [()]
        for vector in route_vectors:
            if sum(vector) > 1.0:
                continue
            actions.append(
                {
                    "replicas": [
                        {"service_id": "svc", "node_id": node, "count": 1}
                        for node in sorted(target)
                    ],
                    "routes": [
                        {
                            "service_id": "svc",
                            "source_region": "tiny",
                            "node_id": node,
                            "fraction": fraction,
                        }
                        for node, fraction in zip(retained, vector)
                        if fraction > 0.0
                    ],
                }
            )
    return actions


def enumerate_action_sequences() -> list[list[dict[str, Any]]]:
    sequences: list[list[dict[str, Any]]] = []

    def visit(step: int, active: frozenset[str], prefix: list[dict[str, Any]]) -> None:
        if step == len(TINY_SCENARIO.workloads):
            sequences.append(prefix)
            return
        for action in action_options(active):
            # With no failures and a one-period cold start, every desired replica is
            # active at the beginning of the next period.
            visit(step + 1, _target_nodes(action), [*prefix, action])

    visit(0, frozenset({"n1"}), [])
    return sequences


def independent_metrics(actions: list[dict[str, Any]]) -> dict[str, float | str]:
    """Recompute the tiny trajectory without calling EdgeServiceSimulator."""

    if len(actions) != 3:
        raise ValueError("tiny oracle requires exactly three actions")
    active = frozenset({"n1"})
    rows: list[dict[str, float]] = []
    demands = (1.0, 3.0, 3.0)
    for demand, action in zip(demands, actions):
        target = _target_nodes(action)
        retained = active & target
        pending = target - active
        requested_by_node = {node: 0.0 for node in retained}
        for route in action["routes"]:
            node = route["node_id"]
            if node not in retained:
                raise ValueError("oracle sequence routes to a non-active target")
            requested_by_node[node] += demand * float(route["fraction"])
        if sum(requested_by_node.values()) > demand + 1e-12:
            raise ValueError("oracle route sum exceeds one")

        served_total = 0.0
        p95_weighted = 0.0
        p99_weighted = 0.0
        served_slo_violations = 0.0
        for requested in requested_by_node.values():
            capacity = 2.0
            served = min(requested, capacity)
            utilization = min(0.995, min(1.25, requested / capacity))
            pressure = utilization * utilization / max(0.08, 1.0 - utilization)
            p95 = 5.0 + 10.0 * (1.0 + 0.85 * pressure)
            p99 = 5.0 + 10.0 * (1.0 + 1.35 * pressure)
            served_total += served
            p95_weighted += served * p95
            p99_weighted += served * p99
            if p99 > 50.0:
                served_slo_violations += served
        unserved = demand - served_total
        rows.append(
            {
                "demand": demand,
                "served": served_total,
                "slo_violations": unserved + served_slo_violations,
                "p95_weighted": p95_weighted,
                "p99_weighted": p99_weighted,
                "compute_cost": 0.1 * len(retained) + 0.05 * len(pending),
            }
        )
        active = target

    total_demand = sum(row["demand"] for row in rows)
    total_served = sum(row["served"] for row in rows)
    return {
        "scenario_family": "tiny_oracle",
        "request_availability": total_served / total_demand,
        "unserved_rate": 1.0 - total_served / total_demand,
        "request_weighted_p95_ms": sum(row["p95_weighted"] for row in rows) / max(total_served, 1e-12),
        "request_weighted_p99_ms": sum(row["p99_weighted"] for row in rows) / max(total_served, 1e-12),
        "p99_slo_violation_rate": sum(row["slo_violations"] for row in rows) / total_demand,
        "compute_cost": sum(row["compute_cost"] for row in rows),
        "cross_region_gb": 0.0,
        "cross_region_cost": 0.0,
        "failure_recovery_steps": 0.0,
    }


def independent_score(metrics: dict[str, float | str]) -> tuple[float, dict[str, float]]:
    """Independent transcription of the current production scoring equation."""

    budgets = load_config()["score_budgets"]

    def ratio(value: float, budget: float, maximum: float = 3.0) -> float:
        return min(maximum, max(0.0, value) / max(budget, 1e-12))

    latency_reference_ms = 180.0  # median P99 SLO in the production task configuration
    components = {
        "reliability": ratio(float(metrics["unserved_rate"]), float(budgets["unserved_rate"])),
        "sla": ratio(float(metrics["p99_slo_violation_rate"]), float(budgets["slo_violation_rate"])),
        "tail_latency": ratio(float(metrics["request_weighted_p99_ms"]), latency_reference_ms, 2.0),
        "compute": ratio(float(metrics["compute_cost"]), float(budgets["compute_cost"])),
        "bandwidth": ratio(float(metrics["cross_region_gb"]), float(budgets["cross_region_gb"])),
        "recovery": ratio(float(metrics["failure_recovery_steps"]), float(budgets["recovery_steps"]), 2.0),
    }
    loss = (
        0.40 * components["reliability"]
        + 0.30 * components["sla"]
        + 0.10 * components["tail_latency"]
        + 0.12 * components["compute"]
        + 0.04 * components["bandwidth"]
        + 0.04 * components["recovery"]
    )
    return 100.0 * math.exp(-loss), components


def brute_force_oracle() -> dict[str, Any]:
    rows: list[tuple[float, str, list[dict[str, Any]], dict[str, float | str], dict[str, float]]] = []
    for actions in enumerate_action_sequences():
        metrics = independent_metrics(actions)
        score, components = independent_score(metrics)
        canonical = json.dumps(actions, sort_keys=True, separators=(",", ":"))
        rows.append((score, canonical, actions, metrics, components))
    best = min(rows, key=lambda row: (-row[0], row[1]))
    return {
        "enumerated_trajectories": len(rows),
        "best_action_sequence": best[2],
        "raw_metrics": best[3],
        "combined_score": best[0],
        "normalized_loss_components": best[4],
    }


if __name__ == "__main__":
    print(json.dumps(brute_force_oracle(), indent=2, ensure_ascii=False, allow_nan=False))
