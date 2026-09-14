#!/usr/bin/env python3
"""Evaluate baseline(init) vs reference(stockpyl) for Task 01."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from stockpyl.gsm_helpers import solution_cost_from_cst

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
    raise RuntimeError("could not locate repo root for tree_gsm_safety_stock evaluator")


_REPO = _find_repo_root()
if str(_REPO / "benchmarks" / "_shared") not in sys.path:
    sys.path.insert(0, str(_REPO / "benchmarks" / "_shared"))
import candidate_sandbox as sandbox  # noqa: E402

from verification.reference import build_tree, solve as solve_reference  # noqa: E402

NODE_IDS = (1, 2, 3, 4)
MAX_CST = 50


def clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def score_solution(solution_cst: dict[int, int]):
    nominal = build_tree(1.0)
    stress = build_tree(1.3)
    baseline_cst = {1: 0, 3: 0, 2: 0, 4: 0}

    base_cost_nom = float(solution_cost_from_cst(nominal, baseline_cst))
    sol_cost_nom = float(solution_cost_from_cst(nominal, solution_cst))
    base_cost_stress = float(solution_cost_from_cst(stress, baseline_cst))
    sol_cost_stress = float(solution_cost_from_cst(stress, solution_cst))

    cost_score = clip((base_cost_nom - sol_cost_nom) / (base_cost_nom - base_cost_nom * 0.50))
    robustness_score = clip(
        (base_cost_stress - sol_cost_stress) / (base_cost_stress - base_cost_stress * 0.50)
    )
    sla_compliance = sum(1 for i, m in {2: 0, 4: 1}.items() if solution_cst[i] <= m) / 2.0

    changed_nodes = sum(1 for k in baseline_cst if baseline_cst[k] != solution_cst[k])
    complexity_score = 1.0 if changed_nodes <= 1 else 0.0

    final_score = (
        0.35 * cost_score
        + 0.35 * robustness_score
        + 0.10 * sla_compliance
        + 0.20 * complexity_score
    )

    return {
        "solution_cst": solution_cst,
        "metrics": {
            "baseline_cost_nominal": base_cost_nom,
            "solution_cost_nominal": sol_cost_nom,
            "baseline_cost_stress": base_cost_stress,
            "solution_cost_stress": sol_cost_stress,
            "cost_score": cost_score,
            "robustness_score": robustness_score,
            "sla_compliance": sla_compliance,
            "complexity_score": complexity_score,
        },
        "weights": {
            "cost_score": 0.35,
            "robustness_score": 0.35,
            "sla_compliance": 0.10,
            "complexity_score": 0.20,
        },
        "final_score": final_score,
    }


class _Validation:
    """Strict, scorer-owned checks on the candidate's reported CST.

    The historical exploit here was a ``dict`` subclass that used
    ``inspect.stack()`` to hand back a compliant CST to the SLA check and a
    more aggressive CST to the cost function -- one "solution" wearing two
    faces. Running the candidate in a subprocess and reading back only JSON
    already makes that attack impossible (JSON has no notion of a class or a
    call stack); what remains here is normalizing the parsed JSON into a
    plain ``{int: int}`` dict (JSON object keys are always strings) and
    bounding the values so a candidate cannot smuggle in a CST that blows up
    or dominates ``net_lead_time``.
    """

    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def validate_and_normalize(self, submission: dict) -> dict[int, int] | None:
        if not isinstance(submission, dict):
            self.fail("submission must be a JSON object")
            return None

        raw_cst = submission.get("cst")
        if not isinstance(raw_cst, dict):
            self.fail("submission['cst'] must be a JSON object")
            return None

        normalized: dict[int, int] = {}
        for key, value in raw_cst.items():
            try:
                node_id = int(key)
            except (TypeError, ValueError):
                self.fail(f"cst key {key!r} is not an integer node id")
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                self.fail(f"cst[{key!r}] must be an integer, got {value!r}")
                continue
            if value < 0 or value > MAX_CST:
                self.fail(f"cst[{key!r}]={value} out of range [0, {MAX_CST}]")
                continue
            normalized[node_id] = int(value)

        if self.errors:
            return None

        if set(normalized) != set(NODE_IDS):
            self.fail(f"cst must have exactly keys {sorted(NODE_IDS)}, got {sorted(normalized)}")
            return None

        return normalized


def run_candidate(candidate_path: Path) -> tuple[dict[int, int] | None, str]:
    """Run the candidate in a subprocess and return (cst, error_message)."""
    try:
        run = sandbox.run_inventory_candidate(
            candidate_path, 'tree_gsm_safety_stock',
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
    cst = validator.validate_and_normalize(submission)
    if cst is None:
        return None, "; ".join(validator.errors)

    nominal = build_tree(1.0)
    try:
        solution_cost_from_cst(nominal, cst)
    except Exception as exc:  # infeasible CST (e.g. negative net lead time)
        return None, f"cst is infeasible: {exc}"

    return cst, None


def main() -> None:
    output_dir = TASK_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_path = TASK_DIR / "baseline" / "init.py"
    baseline_solution, error_message = run_candidate(candidate_path)

    if baseline_solution is None:
        comparison = {
            "task": "tree_gsm_safety_stock",
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

    reference_solution = solve_reference(build_tree(1.0))

    baseline_result = {
        "task": "tree_gsm_safety_stock",
        "method": "baseline",
        "algorithm": "rule-based CST assignment",
        **score_solution(baseline_solution),
    }
    reference_result = {
        "task": "tree_gsm_safety_stock",
        "method": "reference",
        "algorithm": "stockpyl GSM tree DP",
        **score_solution(reference_solution),
    }

    comparison = {
        "task": "tree_gsm_safety_stock",
        "baseline_final_score": baseline_result["final_score"],
        "reference_final_score": reference_result["final_score"],
        "gap_reference_minus_baseline": reference_result["final_score"] - baseline_result["final_score"],
        "winner": "reference"
        if reference_result["final_score"] >= baseline_result["final_score"]
        else "baseline",
    }

    (output_dir / "baseline_result.json").write_text(
        json.dumps(baseline_result, indent=2), encoding="utf-8"
    )
    (output_dir / "reference_result.json").write_text(
        json.dumps(reference_result, indent=2), encoding="utf-8"
    )
    (output_dir / "comparison.json").write_text(
        json.dumps(comparison, indent=2), encoding="utf-8"
    )

    print(f"Baseline score:  {baseline_result['final_score']:.4f}")
    print(f"Reference score: {reference_result['final_score']:.4f}")
    print(f"Gap:             {comparison['gap_reference_minus_baseline']:.4f}")
    print(f"Saved outputs to {output_dir}")


if __name__ == "__main__":
    main()
