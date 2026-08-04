from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from generator import SCENARIO_SPECS, generate_scenario
from problem_view import candidate_view
from scoring import score_selection


TASK_ROOT = Path(__file__).resolve().parents[1]
ANCHOR_PATH = (
    TASK_ROOT
    / "references"
    / "anchor_solutions_v1.json"
)


def write_json(
    path: str,
    payload: dict[str, Any],
) -> None:
    Path(path).write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def percentile(
    values: list[float],
    fraction: float,
) -> float:
    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = fraction * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))

    if lower == upper:
        return ordered[lower]

    weight = position - lower

    return (
        ordered[lower] * (1.0 - weight)
        + ordered[upper] * weight
    )


def run_candidate(
    candidate_path: Path,
    problem: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        problem_path = directory_path / "problem.json"
        output_path = directory_path / "solution.json"

        problem_path.write_text(
            json.dumps(candidate_view(problem), indent=2),
            encoding="utf-8",
        )

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(candidate_path),
                    "--problem",
                    str(problem_path),
                    "--output",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return [], {
                "runtime_error": "候选程序运行超时"
            }

        if result.returncode != 0:
            return [], {
                "runtime_error": "候选程序运行失败",
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        try:
            solution = json.loads(
                output_path.read_text(
                    encoding="utf-8",
                )
            )
            selected_ids = solution["selected_ids"]
        except Exception as error:
            return [], {
                "runtime_error": (
                    f"无法读取候选输出：{error}"
                ),
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

    return selected_ids, {}


def scenario_score(
    candidate_objective: float,
    anchor_objective: float,
) -> float:
    difference = (
        candidate_objective
        - anchor_objective
    )

    # 与固定初始答案相同为50分；
    # 优于它超过50，差于它低于50。
    return max(
        0.0,
        min(
            100.0,
            50.0
            + 45.0
            * math.tanh(difference / 0.08),
        ),
    )


def evaluate(
    candidate_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    anchor_solutions = json.loads(
        ANCHOR_PATH.read_text(encoding="utf-8")
    )

    rows: list[dict[str, Any]] = []

    for scenario_name, scenario_spec in (
        SCENARIO_SPECS.items()
    ):
        problem = generate_scenario(scenario_name)

        selected_ids, runtime_details = run_candidate(
            candidate_path,
            problem,
        )

        candidate_result = score_selection(
            problem,
            selected_ids,
        )

        if runtime_details:
            candidate_result["valid"] = False
            candidate_result["errors"].append(
                runtime_details["runtime_error"]
            )

        anchor_result = score_selection(
            problem,
            anchor_solutions[scenario_name],
        )

        formal_score = (
            scenario_score(
                candidate_result["objective"],
                anchor_result["objective"],
            )
            if candidate_result["valid"]
            else 0.0
        )

        diagnostic_score = max(
            0.0,
            scenario_score(
                candidate_result["objective"],
                anchor_result["objective"],
            )
            - 8.0
            * len(candidate_result["errors"])
        )

        row: dict[str, Any] = {
            "scenario": scenario_name,
            "feedback": scenario_spec["feedback"],
            "valid": candidate_result["valid"],
            "score": formal_score,
            "diagnostic_score": diagnostic_score,
            "errors": candidate_result["errors"],
        }

        if scenario_spec["feedback"]:
            row["candidate"] = candidate_result
            row["anchor"] = anchor_result
        else:
            row["candidate_summary"] = {
                "objective": round(
                    candidate_result["objective"],
                    6,
                ),
                "selected_count": (
                    candidate_result[
                        "selected_count"
                    ]
                ),
                "total_time": (
                    candidate_result["total_time"]
                ),
                "mean_dif": round(
                    candidate_result["mean_dif"],
                    6,
                ),
                "mean_exposure": round(
                    candidate_result[
                        "mean_exposure"
                    ],
                    6,
                ),
            }

        rows.append(row)

    formal_scores = [
        float(row["score"])
        for row in rows
    ]

    diagnostic_scores = [
        float(row["diagnostic_score"])
        for row in rows
    ]

    all_valid = all(
        bool(row["valid"])
        for row in rows
    )

    mean_formal = (
        sum(formal_scores) / len(formal_scores)
    )
    p20_formal = percentile(
        formal_scores,
        0.20,
    )

    mean_diagnostic = (
        sum(diagnostic_scores)
        / len(diagnostic_scores)
    )
    p20_diagnostic = percentile(
        diagnostic_scores,
        0.20,
    )

    robust_formal = (
        0.75 * mean_formal
        + 0.25 * p20_formal
    )

    robust_diagnostic = (
        0.75 * mean_diagnostic
        + 0.25 * p20_diagnostic
    )

    metrics = {
        "combined_score": (
            round(robust_formal, 6)
            if all_valid
            else 0.0
        ),
        "diagnostic_score": round(
            robust_diagnostic,
            6,
        ),
        "valid": 1.0 if all_valid else 0.0,
        "feasible_scenarios": float(
            sum(bool(row["valid"]) for row in rows)
        ),
        "num_scenarios": float(len(rows)),
        "mean_scenario_score": round(
            mean_formal,
            6,
        ),
        "p20_scenario_score": round(
            p20_formal,
            6,
        ),
    }

    artifacts = {
        "candidate_path": str(candidate_path),
        "feedback_rows": rows,
    }

    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate")
    parser.add_argument(
        "--metrics-out",
        default="metrics.json",
    )
    parser.add_argument(
        "--artifacts-out",
        default="artifacts.json",
    )
    args = parser.parse_args()

    metrics, artifacts = evaluate(
        Path(args.candidate).resolve()
    )

    write_json(args.metrics_out, metrics)
    write_json(args.artifacts_out, artifacts)


if __name__ == "__main__":
    main()
