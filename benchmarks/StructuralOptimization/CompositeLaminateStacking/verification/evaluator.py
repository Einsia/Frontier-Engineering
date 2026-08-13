"""Evaluator for the CompositeLaminateStacking benchmark."""

from __future__ import annotations

import argparse
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import numpy as np

try:
    from .design_runtime import DesignRuntime
    from .mechanics import (
        evaluate_base_angles,
        load_config,
        normalize_base_angles,
        public_cases,
    )
except ImportError:  # Direct execution: python verification/evaluator.py ...
    from design_runtime import DesignRuntime
    from mechanics import (
        evaluate_base_angles,
        load_config,
        normalize_base_angles,
        public_cases,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "scripts" / "init.py"


@lru_cache(maxsize=1)
def _anchor_rows() -> dict[str, dict[str, float]]:
    config = load_config()
    anchor = list(config["anchor_base_angles_deg"])
    return {
        str(case["case_id"]): evaluate_base_angles(anchor, case, config)
        for case in public_cases(config)
    }


def _case_score(reserve_factor: float, anchor_reserve: float) -> float:
    if reserve_factor <= 0.0 or anchor_reserve <= 0.0:
        return 0.0
    ratio = reserve_factor / anchor_reserve
    return float(np.clip(50.0 + 50.0 * math.tanh(math.log(ratio) / 0.5), 0.0, 100.0))


def _robust_score(scores: list[float]) -> float:
    if not scores:
        return 0.0
    values = np.asarray(scores, dtype=float)
    return float(0.75 * np.mean(values) + 0.25 * np.quantile(values, 0.20))


def _schema_rows(
    designs: Any, cases: list[dict[str, Any]], config: Mapping[str, Any]
) -> tuple[dict[str, list[int]], dict[str, str]]:
    if not isinstance(designs, dict):
        return {}, {str(case["case_id"]): "candidate result must be a JSON object" for case in cases}
    expected_ids = {str(case["case_id"]) for case in cases}
    returned_ids = {str(key) for key in designs}
    extra = sorted(returned_ids - expected_ids)
    global_error = f"unexpected case ids: {extra}" if extra else None
    normalized: dict[str, list[int]] = {}
    errors: dict[str, str] = {}
    for case in cases:
        case_id = str(case["case_id"])
        if case_id not in designs:
            errors[case_id] = f"missing design for case {case_id}"
            continue
        angles, error = normalize_base_angles(designs[case_id], config)
        if error is not None:
            errors[case_id] = error
        elif global_error is not None:
            errors[case_id] = global_error
        else:
            assert angles is not None
            normalized[case_id] = angles
    return normalized, errors


def evaluate(candidate_path: Path, *, timeout_s: float = 12.0) -> dict[str, Any]:
    config = load_config()
    cases = public_cases(config)
    rows: list[dict[str, Any]] = []
    try:
        with DesignRuntime(
            candidate_path,
            startup_timeout_s=min(3.0, timeout_s),
            call_timeout_s=max(0.05, timeout_s - min(3.0, timeout_s) + 0.25),
            total_timeout_s=timeout_s,
        ) as runtime:
            designs = runtime.design_laminates(cases)
        normalized, schema_errors = _schema_rows(designs, cases, config)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        normalized = {}
        schema_errors = {str(case["case_id"]): message for case in cases}

    anchors = _anchor_rows()
    for case in cases:
        case_id = str(case["case_id"])
        if case_id in schema_errors:
            rows.append(
                {
                    "case_id": case_id,
                    "aspect_ratio": float(case["aspect_ratio"]),
                    "load_type": "biaxial" if float(case["Ny_N_per_mm"]) < 0.0 else "uniaxial",
                    "score": 0.0,
                    "feasible": False,
                    "error": schema_errors[case_id],
                }
            )
            continue
        try:
            candidate = evaluate_base_angles(normalized[case_id], case, config)
            anchor = anchors[case_id]
            score = _case_score(candidate["reserve_factor"], anchor["reserve_factor"])
            rows.append(
                {
                    "case_id": case_id,
                    "aspect_ratio": float(case["aspect_ratio"]),
                    "load_type": "biaxial" if float(case["Ny_N_per_mm"]) < 0.0 else "uniaxial",
                    "score": score,
                    "feasible": True,
                    "base_angles_deg": normalized[case_id],
                    "candidate": candidate,
                    "anchor": anchor,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "case_id": case_id,
                    "aspect_ratio": float(case["aspect_ratio"]),
                    "load_type": "biaxial" if float(case["Ny_N_per_mm"]) < 0.0 else "uniaxial",
                    "score": 0.0,
                    "feasible": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    scores = [float(row["score"]) for row in rows]
    diagnostic_score = _robust_score(scores)
    valid = all(bool(row["feasible"]) and "error" not in row for row in rows)
    return {
        "combined_score": diagnostic_score if valid else 0.0,
        "diagnostic_score": diagnostic_score,
        "valid": float(valid),
        "feasible_cases": float(sum(bool(row["feasible"]) for row in rows)),
        "rows": rows,
    }


def _write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _artifacts(result: dict[str, Any], candidate_path: Path) -> dict[str, Any]:
    try:
        label = candidate_path.relative_to(ROOT).as_posix()
    except ValueError:
        label = candidate_path.name
    return {
        "candidate_path": label,
        "source_doi": load_config()["source"]["doi"],
        "rows": result["rows"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate balanced symmetric laminate designs")
    parser.add_argument("candidate", nargs="?", default=str(DEFAULT_CANDIDATE))
    parser.add_argument("--timeout-s", type=float, default=12.0)
    parser.add_argument("--metrics-out", default=None)
    parser.add_argument("--artifacts-out", default=None)
    args = parser.parse_args()
    if args.timeout_s <= 0.0:
        parser.error("--timeout-s must be positive")

    candidate_path = Path(args.candidate).expanduser().resolve()
    result = evaluate(candidate_path, timeout_s=float(args.timeout_s))
    print("=== Composite Laminate Stacking ===")
    for row in result["rows"]:
        if "error" in row:
            print(f"case={row['case_id']} score=0.00 feasible=false error={row['error']}")
        else:
            candidate = row["candidate"]
            print(
                f"case={row['case_id']} score={row['score']:.2f} feasible=true "
                f"buckling={candidate['buckling_load_factor']:.3f} "
                f"failure={candidate['failure_load_factor']:.3f} "
                f"reserve={candidate['reserve_factor']:.3f}"
            )
    print("---")
    print(f"feasible_cases: {result['feasible_cases']:.0f}/{len(result['rows'])}")
    print(f"diagnostic_score: {result['diagnostic_score']:.4f}")
    print(f"combined_score: {result['combined_score']:.4f}")

    metrics = {
        "combined_score": float(result["combined_score"]),
        "diagnostic_score": float(result["diagnostic_score"]),
        "valid": float(result["valid"]),
        "feasible_cases": float(result["feasible_cases"]),
        "num_cases": float(len(result["rows"])),
    }
    _write_json(args.metrics_out, metrics)
    _write_json(args.artifacts_out, _artifacts(result, candidate_path))


if __name__ == "__main__":
    main()
