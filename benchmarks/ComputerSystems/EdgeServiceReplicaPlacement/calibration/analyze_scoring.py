"""Reproduce score-pipeline, extreme-policy, and weight-sensitivity checks."""

from __future__ import annotations

import argparse
from collections import OrderedDict
import json
import math
from pathlib import Path
from statistics import fmean, median
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "verification"))

from evaluator import _quantile, evaluate  # noqa: E402
from simulator import load_config  # noqa: E402


NOMINAL_WEIGHTS: dict[str, float] = {
    "reliability": 0.40,
    "sla": 0.30,
    "tail_latency": 0.10,
    "compute": 0.12,
    "bandwidth": 0.04,
    "recovery": 0.04,
}
RELATIVE_PERTURBATIONS = (-0.05, -0.02, 0.0, 0.02, 0.05)


POLICY_TEMPLATE = '''\
from __future__ import annotations
import math

MODE = {mode!r}


def reset_policy():
    return None


def _add(placement, cpu_used, nodes, services, service_id, node_id, count):
    cpu = float(services[service_id]["cpu_per_replica"])
    capacity = float(nodes[node_id]["cpu_capacity"])
    feasible = min(count, int((capacity - cpu_used[node_id] + 1e-12) // cpu))
    if feasible > 0:
        placement[(service_id, node_id)] = placement.get((service_id, node_id), 0) + feasible
        cpu_used[node_id] += feasible * cpu


def decide(observation):
    if MODE == "zero":
        return {{"replicas": [], "routes": []}}

    nodes = {{node["id"]: node for node in observation["nodes"]}}
    services = {{service["id"]: service for service in observation["services"]}}
    alive = sorted(node_id for node_id, node in nodes.items() if node["alive"])
    regions = list(observation["workload_rps"])
    cpu_used = {{node_id: 0.0 for node_id in alive}}
    placement = {{}}

    if MODE in {{"fixed_full", "aggressive_cross"}}:
        mix = {{"api": 1, "search": 1, "media": 3}}
        for node_id in alive:
            for service_id, count in mix.items():
                _add(placement, cpu_used, nodes, services, service_id, node_id, count)
    elif MODE == "sla_first":
        mix = {{"api": 2, "search": 1, "media": 2}}
        for node_id in alive:
            for service_id, count in mix.items():
                _add(placement, cpu_used, nodes, services, service_id, node_id, count)
    elif MODE == "ignore_failure":
        # Fixed preselected nodes; a failed target is omitted, never replaced elsewhere.
        for region_index, region in enumerate(regions):
            fixed_nodes = [f"{{region[-1]}}-1", f"{{region[-1]}}-2"]
            for service_index, service_id in enumerate(services):
                node_id = fixed_nodes[service_index % len(fixed_nodes)]
                if node_id in cpu_used:
                    _add(placement, cpu_used, nodes, services, service_id, node_id, 1)
    elif MODE in {{"minimum", "cost_first"}}:
        for service_index, service_id in enumerate(services):
            if not alive:
                break
            # One global replica per service. Cost-first pins it to edge-a and refuses
            # remote traffic; minimum allows all regions to compete for it.
            preferred = [node_id for node_id in alive if nodes[node_id]["region"] == "edge-a"]
            choices = preferred or alive
            node_id = choices[service_index % len(choices)]
            _add(placement, cpu_used, nodes, services, service_id, node_id, 1)
    elif MODE == "local_only":
        # Workload-responsive placement, but no cross-region recovery routing.
        for service_id in sorted(services):
            cpu = float(services[service_id]["cpu_per_replica"])
            rate = float(services[service_id]["service_rate_rps"])
            for region in regions:
                needed = max(
                    1,
                    math.ceil(
                        1.20 * float(observation["workload_rps"][region][service_id]) / rate
                    ),
                )
                local = sorted(
                    node_id for node_id in alive if nodes[node_id]["region"] == region
                )
                for _ in range(needed):
                    feasible = [
                        node_id
                        for node_id in local
                        if cpu_used[node_id] + cpu <= float(nodes[node_id]["cpu_capacity"]) + 1e-12
                    ]
                    if not feasible:
                        break
                    node_id = min(
                        feasible,
                        key=lambda item: (
                            placement.get((service_id, item), 0), cpu_used[item], item
                        ),
                    )
                    _add(placement, cpu_used, nodes, services, service_id, node_id, 1)
    else:
        raise RuntimeError(f"unknown mode: {{MODE}}")

    replicas = [
        {{"service_id": service_id, "node_id": node_id, "count": count}}
        for (service_id, node_id), count in sorted(placement.items())
    ]
    active = {{
        (row["service_id"], row["node_id"]): int(row["count"])
        for row in observation["active_replicas"]
    }}
    retained = {{
        (service_id, node_id)
        for (service_id, node_id), count in placement.items()
        if count > 0 and active.get((service_id, node_id), 0) > 0
    }}
    routes = []
    for source in regions:
        for service_id in services:
            targets = [
                node_id for candidate_service, node_id in retained
                if candidate_service == service_id
            ]
            if MODE in {{"cost_first"}}:
                targets = [node_id for node_id in targets if nodes[node_id]["region"] == source]
            elif MODE == "aggressive_cross":
                remote = [node_id for node_id in targets if nodes[node_id]["region"] != source]
                if remote:
                    max_rtt = max(
                        observation["network_rtt_ms"][source][nodes[node_id]["region"]]
                        for node_id in remote
                    )
                    targets = [
                        node_id for node_id in remote
                        if observation["network_rtt_ms"][source][nodes[node_id]["region"]] == max_rtt
                    ]
                else:
                    targets = []
            elif MODE in {{"fixed_full", "sla_first", "local_only", "ignore_failure"}}:
                targets = [node_id for node_id in targets if nodes[node_id]["region"] == source]
            else:
                targets.sort(
                    key=lambda node_id: (
                        nodes[node_id]["region"] != source,
                        observation["network_rtt_ms"][source][nodes[node_id]["region"]],
                        node_id,
                    )
                )
                targets = targets[:1]
            if targets:
                fraction = 1.0 / len(targets)
                for node_id in sorted(targets):
                    routes.append(
                        {{
                            "service_id": service_id,
                            "source_region": source,
                            "node_id": node_id,
                            "fraction": fraction,
                        }}
                    )
    return {{"replicas": replicas, "routes": routes}}
'''


def _weights_with_relative_change(component: str, relative_change: float) -> dict[str, float]:
    original = NOMINAL_WEIGHTS[component]
    target = original * (1.0 + relative_change)
    other_scale = (1.0 - target) / (1.0 - original)
    return {
        name: target if name == component else weight * other_scale
        for name, weight in NOMINAL_WEIGHTS.items()
    }


def _score_rows(rows: list[dict[str, Any]], weights: dict[str, float]) -> float:
    scenario_scores = []
    for row in rows:
        components = row["normalized_loss_components"]
        loss = sum(weights[name] * float(components[name]) for name in weights)
        scenario_scores.append(100.0 * math.exp(-loss))
    return 0.75 * fmean(scenario_scores) + 0.25 * _quantile(scenario_scores, 0.20)


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    rows = result["rows"]
    metric_names = (
        "request_availability",
        "unserved_rate",
        "request_weighted_p95_ms",
        "request_weighted_p99_ms",
        "p99_slo_violation_rate",
        "compute_cost",
        "cross_region_gb",
        "cross_region_cost",
        "failure_recovery_steps",
    )
    return {
        "valid": bool(result["valid"]),
        "combined_score": result["combined_score"],
        "mean_raw_metrics": {
            name: fmean(float(row["raw_metrics"][name]) for row in rows)
            for name in metric_names
        },
        "mean_normalized_components": {
            name: fmean(float(row["normalized_loss_components"][name]) for row in rows)
            for name in NOMINAL_WEIGHTS
        },
        "mean_weighted_loss_contributions": {
            name: NOMINAL_WEIGHTS[name]
            * fmean(float(row["normalized_loss_components"][name]) for row in rows)
            for name in NOMINAL_WEIGHTS
        },
        "scenario_rows": [
            {
                "scenario": row["scenario"],
                "family": row["family"],
                "score": row["score"],
                "p95_ms": row["raw_metrics"]["request_weighted_p95_ms"],
                "p99_ms": row["raw_metrics"]["request_weighted_p99_ms"],
                "tail_latency_component": row["normalized_loss_components"]["tail_latency"],
            }
            for row in rows
        ],
    }


def _normalization_spec() -> dict[str, Any]:
    config = load_config()
    budgets = config["score_budgets"]
    latency_reference = median(float(item["p99_slo_ms"]) for item in config["services"])
    return {
        "reliability": {
            "raw": "unserved_rate",
            "unit": "ratio",
            "reference": budgets["unserved_rate"],
            "cap": 3.0,
            "classification": "benchmark operational target / synthetic calibration constant",
        },
        "sla": {
            "raw": "p99_slo_violation_rate",
            "unit": "ratio",
            "reference": budgets["slo_violation_rate"],
            "cap": 3.0,
            "classification": "synthetic calibration constant",
        },
        "tail_latency": {
            "raw": "request_weighted_p99_ms",
            "unit": "milliseconds",
            "reference": latency_reference,
            "reference_derivation": "median configured service P99 SLO",
            "cap": 2.0,
            "classification": "scenario/task-derived reference",
        },
        "compute": {
            "raw": "compute_cost",
            "unit": "abstract cost units/episode",
            "reference": budgets["compute_cost"],
            "cap": 3.0,
            "classification": "baseline-calibrated synthetic constant",
        },
        "bandwidth": {
            "raw": "cross_region_gb",
            "unit": "GB/episode",
            "reference": budgets["cross_region_gb"],
            "cap": 3.0,
            "classification": "baseline-calibrated synthetic constant",
        },
        "recovery": {
            "raw": "failure_recovery_steps",
            "unit": "control periods",
            "reference": budgets["recovery_steps"],
            "cap": 2.0,
            "classification": "scenario-derived failure-duration budget",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    candidate_paths: OrderedDict[str, Path] = OrderedDict(
        (
            ("weak_static", ROOT / "calibration" / "weak.py"),
            ("reasonable", ROOT / "scripts" / "init.py"),
            ("strong", ROOT / "calibration" / "strong.py"),
        )
    )
    modes = OrderedDict(
        (
            ("zero", "zero"),
            ("minimum_replica", "minimum"),
            ("cost_first_underprovision", "cost_first"),
            ("local_routing_only", "local_only"),
            ("fixed_full_capacity", "fixed_full"),
            ("sla_first_overprovision", "sla_first"),
            ("aggressive_cross_region", "aggressive_cross"),
            ("ignore_failure", "ignore_failure"),
        )
    )

    with tempfile.TemporaryDirectory(prefix="edge_score_review_") as tempdir:
        temp_root = Path(tempdir)
        for label, mode in modes.items():
            path = temp_root / f"{label}.py"
            path.write_text(POLICY_TEMPLATE.format(mode=mode), encoding="utf-8")
            candidate_paths[label] = path
        evaluations = {name: evaluate(path) for name, path in candidate_paths.items()}

    policies = {name: _summarize(result) for name, result in evaluations.items()}
    nominal_ranking = sorted(policies, key=lambda name: policies[name]["combined_score"], reverse=True)
    sensitivity: dict[str, Any] = {}
    for component in NOMINAL_WEIGHTS:
        component_rows = []
        for relative_change in RELATIVE_PERTURBATIONS:
            weights = _weights_with_relative_change(component, relative_change)
            scores = {
                name: _score_rows(evaluations[name]["rows"], weights)
                for name in evaluations
            }
            ranking = sorted(scores, key=scores.get, reverse=True)
            component_rows.append(
                {
                    "relative_change": relative_change,
                    "weights": weights,
                    "scores": scores,
                    "ranking_high_to_low": ranking,
                    "rank_reversal_vs_nominal": ranking != nominal_ranking,
                }
            )
        sensitivity[component] = component_rows

    # Retain the previously observed absolute 0.02 SLA-to-bandwidth trade-off as a
    # separate engineering-preference test, not as the systematic relative sweep.
    shifted = dict(NOMINAL_WEIGHTS)
    shifted["sla"] -= 0.02
    shifted["bandwidth"] += 0.02
    pairwise_scores = {
        name: _score_rows(evaluations[name]["rows"], shifted) for name in evaluations
    }
    payload = {
        "normalization": _normalization_spec(),
        "nominal_weights": NOMINAL_WEIGHTS,
        "policies": policies,
        "nominal_ranking_high_to_low": nominal_ranking,
        "relative_weight_sensitivity": sensitivity,
        "absolute_pairwise_shift": {
            "change": "SLA -0.02, bandwidth +0.02",
            "weights": shifted,
            "scores": pairwise_scores,
            "ranking_high_to_low": sorted(pairwise_scores, key=pairwise_scores.get, reverse=True),
        },
        "service_p99_slo_ms": {
            item["id"]: item["p99_slo_ms"] for item in load_config()["services"]
        },
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
