from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

try:
    from .policy_runtime import PolicyRuntime
    from .simulator import (
        EVALUATION_SCENARIOS,
        MIN_LIQUIDITY_SERVICE,
        MIN_QUOTE_RATE,
        SCENARIOS,
        SYMBOLS,
        DualMarketSimulator,
        ScenarioSpec,
        quoting_objective,
    )
except ImportError:  # Direct execution: python verification/evaluator.py ...
    from policy_runtime import PolicyRuntime
    from simulator import (
        EVALUATION_SCENARIOS,
        MIN_LIQUIDITY_SERVICE,
        MIN_QUOTE_RATE,
        SCENARIOS,
        SYMBOLS,
        DualMarketSimulator,
        ScenarioSpec,
        quoting_objective,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "scripts" / "init.py"
POLICY_STARTUP_TIMEOUT_S = 3.0
POLICY_CALL_TIMEOUT_S = 0.25
POLICY_SCENARIO_TIMEOUT_S = 12.0


class AnchorPolicy:
    """Feasible symmetric reference used only to normalize scenario difficulty."""

    @staticmethod
    def reset_policy() -> None:
        return None

    @staticmethod
    def decide_quotes(observation: dict[str, Any]) -> dict[str, dict[str, float | int]]:
        actions: dict[str, dict[str, float | int]] = {}
        for symbol, asset in observation["assets"].items():
            inventory = int(asset["dual_inventory"])
            mandate = str(asset["desk_mandate"]).lower()
            bid_offset = 18.0
            ask_offset = 18.0
            bid_size = 2 if inventory <= 48 else 0
            ask_size = 2 if inventory >= -48 else 0
            if "adverse-selection alert" in mandate:
                bid_size = min(bid_size, 1)
                ask_size = min(ask_size, 1)
                primary_mid = 0.5 * (float(asset["primary_bid"]) + float(asset["primary_ask"]))
                bid_offset = min(
                    80.0,
                    max(
                        bid_offset,
                        10_000.0 * (1.0 - float(asset["dual_ask"]) / primary_mid) + 0.25,
                    ),
                )
                ask_offset = min(
                    80.0,
                    max(
                        ask_offset,
                        10_000.0 * (float(asset["dual_bid"]) / primary_mid - 1.0) + 0.25,
                    ),
                )
            if "long-inventory recovery" in mandate:
                bid_size = 0 if "liquidity campaign" in mandate else min(bid_size, 1)
                ask_size = max(1, ask_size)
            if "short-inventory recovery" in mandate:
                ask_size = 0 if "liquidity campaign" in mandate else min(ask_size, 1)
                bid_size = max(1, bid_size)
            actions[symbol] = {
                "bid_offset_bps": bid_offset,
                "ask_offset_bps": ask_offset,
                "bid_size": bid_size,
                "ask_size": ask_size,
            }
        return actions


def _run_policy(policy: Any, scenario: ScenarioSpec) -> dict[str, Any]:
    reset = getattr(policy, "reset_policy", None)
    if reset is not None:
        reset()
    simulator = DualMarketSimulator(scenario=scenario, steps=240)
    for _ in range(simulator.steps):
        actions = policy.decide_quotes(simulator.observation())
        if not isinstance(actions, dict):
            raise TypeError("decide_quotes must return a dict")
        simulator.step_quotes(actions)
    metrics = simulator.metrics()
    metrics["objective"] = quoting_objective(metrics)
    return metrics


def _run_candidate(candidate_path: Path, scenario: ScenarioSpec) -> dict[str, Any]:
    # A fresh process per scenario prevents state leakage between fixed evaluation paths.
    with PolicyRuntime(
        candidate_path,
        startup_timeout_s=POLICY_STARTUP_TIMEOUT_S,
        call_timeout_s=POLICY_CALL_TIMEOUT_S,
        total_timeout_s=POLICY_SCENARIO_TIMEOUT_S,
    ) as policy:
        return _run_policy(policy, scenario)


def _is_feasible(metrics: dict[str, Any]) -> bool:
    return bool(
        metrics["violations"] == 0.0
        and metrics["max_abs_inventory"] <= 50.0
        and metrics["quote_rate"] >= MIN_QUOTE_RATE
        and metrics["liquidity_service"] >= MIN_LIQUIDITY_SERVICE
    )


@lru_cache(maxsize=None)
def _anchor_metrics(scenario: ScenarioSpec) -> dict[str, Any]:
    return _run_policy(AnchorPolicy, scenario)


def _scenario_score(candidate: dict[str, Any], anchor: dict[str, Any]) -> float:
    delta = candidate["objective"] - anchor["objective"]
    score_scale = 120.0 + 0.45 * abs(anchor["objective"])
    score = 50.0 + 50.0 * math.tanh(delta / score_scale)
    if candidate["quote_rate"] < MIN_QUOTE_RATE:
        score *= candidate["quote_rate"] / MIN_QUOTE_RATE
    if candidate["liquidity_service"] < MIN_LIQUIDITY_SERVICE:
        score *= candidate["liquidity_service"] / MIN_LIQUIDITY_SERVICE
    if candidate["max_abs_inventory"] > 50.0:
        return 0.0
    score *= max(0.0, 1.0 - min(1.0, candidate["violations"] / 8.0))
    return float(np.clip(score, 0.0, 100.0))


def _robust_diagnostic_score(scores: list[float]) -> float:
    """Reward average performance while retaining pressure on weak regimes."""

    if not scores:
        return 0.0
    values = np.asarray(scores, dtype=float)
    return float(0.75 * np.mean(values) + 0.25 * np.quantile(values, 0.20))


def evaluate(candidate_path: Path) -> dict[str, Any]:
    candidate_path = candidate_path.expanduser().resolve()
    rows: list[dict[str, Any]] = []
    for scenario_index, scenario in enumerate(EVALUATION_SCENARIOS):
        try:
            candidate_metrics = _run_candidate(candidate_path, scenario)
            anchor_metrics = _anchor_metrics(scenario)
            rows.append(
                {
                    "scenario": scenario.name,
                    "seed": scenario.seed,
                    "feedback": scenario.feedback,
                    "score": _scenario_score(candidate_metrics, anchor_metrics),
                    "feasible": _is_feasible(candidate_metrics),
                    "candidate": candidate_metrics,
                    "anchor": anchor_metrics,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "scenario": scenario.name,
                    "seed": scenario.seed,
                    "feedback": scenario.feedback,
                    "score": 0.0,
                    "feasible": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            # A runtime error already makes the candidate invalid. Stop launching more
            # subprocesses so a syntax error or timeout cannot consume the full evaluator budget.
            for remaining in EVALUATION_SCENARIOS[scenario_index + 1 :]:
                rows.append(
                    {
                        "scenario": remaining.name,
                        "seed": remaining.seed,
                        "feedback": remaining.feedback,
                        "score": 0.0,
                        "feasible": False,
                        "error": "not evaluated after prior candidate failure",
                    }
                )
            break

    scores = [float(row["score"]) for row in rows]
    diagnostic_score = _robust_diagnostic_score(scores)
    valid = all("error" not in row and bool(row["feasible"]) for row in rows)
    # combined_score is the ranking metric. Hard constraints are genuinely hard: an invalid
    # candidate keeps continuous diagnostic feedback but cannot outrank a feasible candidate.
    combined_score = diagnostic_score if valid else 0.0
    return {
        "combined_score": combined_score,
        "diagnostic_score": diagnostic_score,
        "valid": float(valid),
        "feasible_scenarios": float(sum(bool(row["feasible"]) for row in rows)),
        "rows": rows,
    }


def _write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _public_artifacts(result: dict[str, Any], candidate_label: str) -> dict[str, Any]:
    feedback_rows = [row for row in result["rows"] if bool(row.get("feedback"))]
    validation_rows = [row for row in result["rows"] if not bool(row.get("feedback"))]
    validation_scores = [float(row["score"]) for row in validation_rows]
    return {
        "candidate_path": candidate_label,
        "feedback_rows": feedback_rows,
        "validation_summary": {
            "num_scenarios": len(validation_rows),
            "feasible_scenarios": sum(bool(row["feasible"]) for row in validation_rows),
            "mean_score": float(np.mean(validation_scores)) if validation_scores else 0.0,
            "worst_score": min(validation_scores, default=0.0),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate inventory-aware DUAL quoting policy")
    parser.add_argument("candidate", nargs="?", default=str(DEFAULT_CANDIDATE))
    parser.add_argument("--metrics-out", default=None)
    parser.add_argument("--artifacts-out", default=None)
    args = parser.parse_args()

    candidate_path = Path(args.candidate).expanduser().resolve()
    result = evaluate(candidate_path)
    print("=== Inventory-Aware Quoting ===")
    for row in result["rows"]:
        if not row["feedback"]:
            continue
        if "error" in row:
            print(
                f"scenario={row['scenario']} score=0.00 feasible=false "
                f"error={row['error']}"
            )
        else:
            metrics = row["candidate"]
            print(
                f"scenario={row['scenario']} score={row['score']:.2f} "
                f"feasible={str(row['feasible']).lower()} pnl={metrics['pnl']:.2f} "
                f"inv_rms={metrics['inventory_rms']:.2f} "
                f"risk_rms={metrics['inventory_risk_rms']:.2f} "
                f"drawdown={metrics['max_drawdown']:.2f} "
                f"service={metrics['liquidity_service']:.3f} "
                f"fills={metrics['fills']:.0f} "
                f"violations={metrics['violation_reasons']}"
            )
    print("---")
    print(f"feasible_scenarios: {result['feasible_scenarios']:.0f}/{len(result['rows'])}")
    print(f"diagnostic_score: {result['diagnostic_score']:.4f}")
    print(f"combined_score: {result['combined_score']:.4f}")

    metrics = {
        "combined_score": result["combined_score"],
        "diagnostic_score": result["diagnostic_score"],
        "valid": result["valid"],
        "feasible_scenarios": result["feasible_scenarios"],
        "num_scenarios": float(len(result["rows"])),
    }
    try:
        candidate_label = candidate_path.relative_to(ROOT).as_posix()
    except ValueError:
        candidate_label = candidate_path.name
    _write_json(args.metrics_out, metrics)
    _write_json(args.artifacts_out, _public_artifacts(result, candidate_label))


if __name__ == "__main__":
    main()
