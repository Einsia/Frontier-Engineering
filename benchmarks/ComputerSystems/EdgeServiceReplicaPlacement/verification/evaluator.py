from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import fmean, median
from typing import Any

try:
    from .policy_runtime import PolicyRuntime
    from .simulator import SCENARIOS, EdgeServiceSimulator, load_config
except ImportError:
    from policy_runtime import PolicyRuntime
    from simulator import SCENARIOS, EdgeServiceSimulator, load_config


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "scripts" / "init.py"
POLICY_STARTUP_TIMEOUT_S = 3.0
POLICY_CALL_TIMEOUT_S = 0.35
POLICY_SCENARIO_TIMEOUT_S = 12.0


def _run_candidate(candidate_path: Path, scenario: Any) -> dict[str, Any]:
    with PolicyRuntime(
        candidate_path,
        startup_timeout_s=POLICY_STARTUP_TIMEOUT_S,
        call_timeout_s=POLICY_CALL_TIMEOUT_S,
        total_timeout_s=POLICY_SCENARIO_TIMEOUT_S,
    ) as policy:
        policy.reset_policy()
        simulator = EdgeServiceSimulator(scenario)
        simulator._activate_pending_and_apply_failures()
        while not simulator.done:
            simulator.step(policy.decide(simulator.observation()))
        return simulator.metrics()


def _bounded_ratio(value: float, budget: float, maximum: float = 3.0) -> float:
    return min(maximum, max(0.0, value) / max(budget, 1e-12))


def scenario_score(metrics: dict[str, Any]) -> tuple[float, dict[str, float]]:
    """Calibratable engineering loss; raw metrics remain the primary explanation."""

    budgets = load_config()["score_budgets"]
    # Normalize latency against a task-defined reference instead of clipping every
    # below-SLO result to zero. The median service P99 SLO is 180 ms in the MVP.
    latency_reference_ms = median(
        float(service["p99_slo_ms"]) for service in load_config()["services"]
    )
    components = {
        "reliability": _bounded_ratio(float(metrics["unserved_rate"]), float(budgets["unserved_rate"])),
        "sla": _bounded_ratio(float(metrics["p99_slo_violation_rate"]), float(budgets["slo_violation_rate"])),
        "tail_latency": _bounded_ratio(
            float(metrics["request_weighted_p99_ms"]), latency_reference_ms, 2.0
        ),
        "compute": _bounded_ratio(float(metrics["compute_cost"]), float(budgets["compute_cost"])),
        "bandwidth": _bounded_ratio(float(metrics["cross_region_gb"]), float(budgets["cross_region_gb"])),
        "recovery": _bounded_ratio(float(metrics["failure_recovery_steps"]), float(budgets["recovery_steps"]), 2.0),
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


def evaluate_action_sequence(
    actions: list[dict[str, Any]], scenario: Any, config: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate a fixed tiny action trajectory through the production state machine.

    This test hook deliberately reuses the real simulator and scoring function. The
    independent oracle in ``tiny_oracle.py`` does not call this function when searching.
    """

    if len(actions) != len(scenario.workloads):
        raise ValueError("action count must match scenario length")
    simulator = EdgeServiceSimulator(scenario, config=config)
    simulator._activate_pending_and_apply_failures()
    for action in actions:
        simulator.step(action)
    raw_metrics = simulator.metrics()
    score, components = scenario_score(raw_metrics)
    return {
        "raw_metrics": raw_metrics,
        "combined_score": score,
        "normalized_loss_components": components,
    }


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def evaluate(candidate_path: Path) -> dict[str, Any]:
    candidate_path = candidate_path.expanduser().resolve()
    rows: list[dict[str, Any]] = []
    for scenario_index, scenario in enumerate(SCENARIOS):
        try:
            raw = _run_candidate(candidate_path, scenario)
            score, components = scenario_score(raw)
            rows.append(
                {
                    "scenario": scenario.name,
                    "family": scenario.family,
                    "seed": scenario.seed,
                    "feedback": scenario.feedback,
                    "score": score,
                    "raw_metrics": raw,
                    "normalized_loss_components": components,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "scenario": scenario.name,
                    "family": scenario.family,
                    "seed": scenario.seed,
                    "feedback": scenario.feedback,
                    "score": 0.0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            for remaining in SCENARIOS[scenario_index + 1 :]:
                rows.append(
                    {
                        "scenario": remaining.name,
                        "family": remaining.family,
                        "seed": remaining.seed,
                        "feedback": remaining.feedback,
                        "score": 0.0,
                        "error": "not evaluated after prior candidate failure",
                    }
                )
            break

    scores = [float(row["score"]) for row in rows]
    diagnostic_score = 0.75 * fmean(scores) + 0.25 * _quantile(scores, 0.20) if scores else 0.0
    valid = all("error" not in row for row in rows)
    successful = [row["raw_metrics"] for row in rows if "raw_metrics" in row]

    def mean_metric(name: str) -> float:
        return fmean(float(metrics[name]) for metrics in successful) if successful else 0.0

    return {
        "combined_score": diagnostic_score if valid else 0.0,
        "diagnostic_score": diagnostic_score,
        "valid": float(valid),
        "evaluated_scenarios": float(len(successful)),
        "mean_request_availability": mean_metric("request_availability"),
        "mean_request_weighted_p95_ms": mean_metric("request_weighted_p95_ms"),
        "mean_request_weighted_p99_ms": mean_metric("request_weighted_p99_ms"),
        "mean_p99_slo_violation_rate": mean_metric("p99_slo_violation_rate"),
        "mean_compute_cost": mean_metric("compute_cost"),
        "mean_cross_region_gb": mean_metric("cross_region_gb"),
        "mean_failure_recovery_steps": mean_metric("failure_recovery_steps"),
        "rows": rows,
    }


def _write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def _public_artifacts(result: dict[str, Any], candidate_label: str) -> dict[str, Any]:
    feedback_rows = [row for row in result["rows"] if bool(row.get("feedback"))]
    validation_rows = [row for row in result["rows"] if not bool(row.get("feedback"))]
    return {
        "candidate_path": candidate_label,
        "feedback_rows": feedback_rows,
        "validation_summary": {
            "num_scenarios": len(validation_rows),
            "mean_score": fmean(float(row["score"]) for row in validation_rows) if validation_rows else 0.0,
            "failed_scenarios": sum("error" in row for row in validation_rows),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an edge replica-placement and routing policy")
    parser.add_argument("candidate", nargs="?", default=str(DEFAULT_CANDIDATE))
    parser.add_argument("--metrics-out", default=None)
    parser.add_argument("--artifacts-out", default=None)
    args = parser.parse_args()
    candidate_path = Path(args.candidate).expanduser().resolve()
    result = evaluate(candidate_path)
    print("=== Edge Service Replica Placement MVP ===")
    for row in result["rows"]:
        if not row["feedback"]:
            continue
        if "error" in row:
            print(f"scenario={row['scenario']} score=0.00 error={row['error']}")
        else:
            raw = row["raw_metrics"]
            print(
                f"scenario={row['scenario']} score={row['score']:.2f} "
                f"availability={raw['request_availability']:.4f} "
                f"p99_ms={raw['request_weighted_p99_ms']:.1f} "
                f"sla_violation={raw['p99_slo_violation_rate']:.4f} "
                f"compute_cost={raw['compute_cost']:.3f} cross_region_gb={raw['cross_region_gb']:.3f}"
            )
    print("---")
    print(f"valid: {bool(result['valid'])}")
    print(f"diagnostic_score: {result['diagnostic_score']:.4f}")
    print(f"combined_score: {result['combined_score']:.4f}")

    metrics = {key: value for key, value in result.items() if key != "rows"}
    try:
        candidate_label = candidate_path.relative_to(ROOT).as_posix()
    except ValueError:
        candidate_label = candidate_path.name
    _write_json(args.metrics_out, metrics)
    _write_json(args.artifacts_out, _public_artifacts(result, candidate_label))


if __name__ == "__main__":
    main()
