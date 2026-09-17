#!/usr/bin/env python3

from __future__ import annotations

import json
import textwrap
from pathlib import Path


TASKS = [
    {
        "slug": "EOQWithMinimumOrderQuantity",
        "title": "EOQ with Minimum Order Quantity",
        "short": "Optimize annual cost for deterministic EOQ instances with a hard minimum order quantity.",
        "kind": "eoq_moq",
        "domain": "OperationsResearch",
        "cases": [
            {"fixed_cost": 8.0, "holding_cost_rate": 0.225, "demand_rate": 1300.0, "minimum_order_quantity": 80.0},
            {"fixed_cost": 14.0, "holding_cost_rate": 0.18, "demand_rate": 1800.0, "minimum_order_quantity": 140.0},
            {"fixed_cost": 11.0, "holding_cost_rate": 0.25, "demand_rate": 950.0, "minimum_order_quantity": 100.0},
            {"fixed_cost": 6.0, "holding_cost_rate": 0.16, "demand_rate": 2200.0, "minimum_order_quantity": 120.0},
        ],
    },
    {
        "slug": "EOQWithAllUnitsDiscounts",
        "title": "EOQ with All-Units Discounts",
        "short": "Choose an order quantity under piecewise all-units discount pricing.",
        "kind": "eoq_all_units",
        "domain": "OperationsResearch",
        "cases": [
            {"fixed_cost": 8.0, "holding_cost_rate": 0.225, "demand_rate": 1300.0, "breakpoints": [0.0, 350.0, 700.0], "unit_costs": [0.50, 0.47, 0.44]},
            {"fixed_cost": 10.0, "holding_cost_rate": 0.18, "demand_rate": 2200.0, "breakpoints": [0.0, 300.0, 900.0], "unit_costs": [0.82, 0.79, 0.73]},
            {"fixed_cost": 12.0, "holding_cost_rate": 0.20, "demand_rate": 1700.0, "breakpoints": [0.0, 500.0, 1000.0], "unit_costs": [1.10, 1.03, 0.98]},
            {"fixed_cost": 6.0, "holding_cost_rate": 0.16, "demand_rate": 2400.0, "breakpoints": [0.0, 250.0, 600.0], "unit_costs": [0.42, 0.39, 0.36]},
        ],
    },
    {
        "slug": "EOQWithIncrementalDiscounts",
        "title": "EOQ with Incremental Discounts",
        "short": "Choose an order quantity under incremental quantity discounts.",
        "kind": "eoq_incremental",
        "domain": "OperationsResearch",
        "cases": [
            {"fixed_cost": 150.0, "holding_cost_rate": 0.25, "demand_rate": 2400.0, "breakpoints": [0.0, 300.0, 600.0], "unit_costs": [100.0, 90.0, 80.0]},
            {"fixed_cost": 60.0, "holding_cost_rate": 0.18, "demand_rate": 3000.0, "breakpoints": [0.0, 200.0, 400.0], "unit_costs": [15.0, 14.0, 12.5]},
            {"fixed_cost": 90.0, "holding_cost_rate": 0.22, "demand_rate": 1600.0, "breakpoints": [0.0, 250.0, 550.0], "unit_costs": [24.0, 22.5, 21.0]},
            {"fixed_cost": 45.0, "holding_cost_rate": 0.15, "demand_rate": 4200.0, "breakpoints": [0.0, 500.0, 1200.0], "unit_costs": [9.0, 8.7, 8.2]},
        ],
    },
    {
        "slug": "PoissonRQServiceLevel",
        "title": "Poisson (r,Q) with Service-Level Constraint",
        "short": "Select reorder point and lot size for Poisson-demand (r,Q) instances with a hard cycle-service-level target.",
        "kind": "rq_poisson",
        "domain": "OperationsResearch",
        "cases": [
            {"holding_cost": 0.18, "stockout_cost": 0.70, "fixed_cost": 4.0, "demand_mean": 1300.0, "lead_time": 0.05, "target_csl": 0.95},
            {"holding_cost": 0.25, "stockout_cost": 0.95, "fixed_cost": 6.0, "demand_mean": 900.0, "lead_time": 0.10, "target_csl": 0.95},
            {"holding_cost": 0.14, "stockout_cost": 0.80, "fixed_cost": 5.0, "demand_mean": 1500.0, "lead_time": 0.04, "target_csl": 0.97},
            {"holding_cost": 0.22, "stockout_cost": 1.10, "fixed_cost": 7.0, "demand_mean": 700.0, "lead_time": 0.12, "target_csl": 0.95},
        ],
    },
    {
        "slug": "NormalRQServiceLevel95",
        "title": "Normal (r,Q) with 95% Service-Level Constraint",
        "short": "Select reorder point and lot size for Normal-demand (r,Q) instances with a hard cycle-service-level target.",
        "kind": "rq_normal",
        "domain": "OperationsResearch",
        "cases": [
            {"holding_cost": 0.18, "stockout_cost": 0.70, "fixed_cost": 4.0, "demand_mean": 1300.0, "demand_sd": 120.0, "lead_time": 0.05, "target_csl": 0.95},
            {"holding_cost": 0.20, "stockout_cost": 0.85, "fixed_cost": 5.5, "demand_mean": 950.0, "demand_sd": 90.0, "lead_time": 0.08, "target_csl": 0.95},
            {"holding_cost": 0.16, "stockout_cost": 0.92, "fixed_cost": 6.0, "demand_mean": 1500.0, "demand_sd": 170.0, "lead_time": 0.04, "target_csl": 0.97},
            {"holding_cost": 0.24, "stockout_cost": 1.25, "fixed_cost": 7.0, "demand_mean": 720.0, "demand_sd": 75.0, "lead_time": 0.12, "target_csl": 0.95},
        ],
    },
]


GENERIC_README = """\
# {title}

{short}

## Provenance

- {provenance_summary}
- Data asset: benchmark-local frozen parameter tables defined in `runtime/problem.py`.
- Full provenance note: see `references/source_manifest.md`.

## File Layout

- `Task.md`: task contract and scoring rules.
- `Task_zh-CN.md`: Chinese translation of the contract.
- `scripts/init.py`: initial candidate file exposed to agents.
- `baseline/solution.py`: reference implementation.
- `runtime/problem.py`: frozen cases, baseline solver, and scoring helpers.
- `verification/evaluator.py`: evaluator entry.
- `verification/requirements.txt`: minimal dependencies for this benchmark.

## Quick Run

From repository root:

```bash
python benchmarks/OperationsResearch/{slug}/verification/evaluator.py \
  benchmarks/OperationsResearch/{slug}/scripts/init.py \
  --metrics-out /tmp/{slug}_metrics.json
```

Run through `frontier_eval` with:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/{slug} \
  algorithm.iterations=0
```
"""


GENERIC_TASK = """\
# {title} Task

## Objective

{short}

{task_source_en}

## Submission Contract

Submit one Python file that defines:

```python
def solve(instance):
    ...
```

The return value must be:

- For EOQ tasks: a dict with `order_quantity`, or a raw numeric quantity.
- For `(r,Q)` tasks: a dict with `reorder_point` and `order_quantity`, or a 2-tuple `(r, Q)`.

## Evaluation

The evaluator will:

1. Load the frozen case set from `runtime/problem.py`.
2. Run the reference baseline for each case.
3. Run your `solve(instance)` implementation for each case.
4. Convert the returned quantity or `(r, Q)` pair into a cost and feasibility result.
5. Compute the average candidate cost and expose it directly as the optimization score.

## Metrics

- `combined_score`: `-avg_cost`
- `valid`: `1.0` only if every case is feasible and every output is finite
- `avg_cost`: average candidate cost
- `avg_cost_ratio`: average `baseline_cost / candidate_cost` for diagnostics only

## Failure Cases

The submission is marked invalid and receives a very low score if:

- `solve()` is missing
- the returned output cannot be parsed
- any case violates feasibility constraints
- any metric becomes non-finite
"""


GENERIC_TASK_ZH = """\
# {title} 任务

## 目标

{short}

{task_source_zh}

## 提交接口

提交一个 Python 文件，定义：

```python
def solve(instance):
    ...
```

返回值要求：

- EOQ 类任务：返回 `order_quantity` 字段的字典，或者直接返回数值型订货批量。
- `(r,Q)` 类任务：返回包含 `reorder_point` 和 `order_quantity` 的字典，或者直接返回二元组 `(r, Q)`。

## 评测方式

评测器会：

1. 读取 `runtime/problem.py` 中的固定样例。
2. 运行 baseline。
3. 运行选手的 `solve(instance)`。
4. 计算成本和可行性。
5. 计算平均候选成本，并将其直接暴露为优化分数。

## 指标

- `combined_score`：`-avg_cost`
- `valid`：所有 case 都可行且数值有限时为 `1.0`
- `avg_cost`：平均候选成本
- `avg_cost_ratio`：仅用于诊断的平均 `baseline_cost / candidate_cost`
"""


GENERIC_INIT = """\
#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _ensure_import_path() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            parent_s = str(parent)
            if parent_s not in sys.path:
                sys.path.insert(0, parent_s)
            return
    benchmark_root = here.parents[1]
    benchmark_root_s = str(benchmark_root)
    if benchmark_root_s not in sys.path:
        sys.path.insert(0, benchmark_root_s)


_ensure_import_path()

try:
    from benchmarks.OperationsResearch.{slug}.baseline.solution import solve as _baseline_solve
except ModuleNotFoundError:
    from baseline.solution import solve as _baseline_solve


# EVOLVE-BLOCK-START
def solve(instance):
    return _baseline_solve(instance)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    try:
        from benchmarks.OperationsResearch.{slug}.runtime.problem import SAMPLE_INSTANCE
    except ModuleNotFoundError:
        from runtime.problem import SAMPLE_INSTANCE
    print(solve(SAMPLE_INSTANCE))
"""


GENERIC_BASELINE = """\
from __future__ import annotations

import sys
from pathlib import Path


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _ensure_import_path() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            parent_s = str(parent)
            if parent_s not in sys.path:
                sys.path.insert(0, parent_s)
            return
    benchmark_root = here.parents[1]
    benchmark_root_s = str(benchmark_root)
    if benchmark_root_s not in sys.path:
        sys.path.insert(0, benchmark_root_s)


_ensure_import_path()

try:
    from benchmarks.OperationsResearch.{slug}.runtime.problem import solve_baseline as solve
except ModuleNotFoundError:
    from runtime.problem import solve_baseline as solve
"""


GENERIC_EVALUATOR = """\
from __future__ import annotations

import argparse
import json
import math
import runpy
import traceback
from pathlib import Path


def _benchmark_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    return Path.cwd().resolve()


def _ensure_import_path() -> None:
    import sys

    repo_root = _repo_root()
    benchmark_root = _benchmark_root()
    for p in (repo_root, benchmark_root):
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.OperationsResearch.{slug}.runtime.problem import CASES, evaluate_solution
    from benchmarks.OperationsResearch.{slug}.baseline.solution import solve as baseline_solve
except ModuleNotFoundError:
    from runtime.problem import CASES, evaluate_solution
    from baseline.solution import solve as baseline_solve


def evaluate(program_path: str) -> tuple[dict[str, float], dict[str, str]]:
    metrics = {{
        "combined_score": -1e18,
        "valid": 0.0,
        "avg_cost": 0.0,
        "avg_cost_ratio": 0.0,
        "num_cases": 0.0,
    }}
    artifacts: dict[str, str] = {{}}

    program = Path(program_path).expanduser().resolve()
    namespace = runpy.run_path(str(program), run_name="candidate_program")
    solve = namespace.get("solve")
    if not callable(solve):
        artifacts["error_message"] = "candidate file must define solve(instance)"
        return metrics, artifacts

    total_cost = 0.0
    total_ratio = 0.0
    for idx, case in enumerate(CASES):
        baseline_solution = baseline_solve(case)
        baseline_eval = evaluate_solution(case, baseline_solution)
        if not baseline_eval["valid"]:
            artifacts["error_message"] = f"internal baseline invalid on case {{idx}}"
            return metrics, artifacts

        try:
            candidate_solution = solve(case)
            candidate_eval = evaluate_solution(case, candidate_solution)
        except Exception:
            artifacts["error_message"] = f"candidate exception on case {{idx}}\\n{{traceback.format_exc()}}"
            return metrics, artifacts

        if not candidate_eval["valid"]:
            artifacts["error_message"] = f"candidate infeasible on case {{idx}}"
            return metrics, artifacts

        ratio = baseline_eval["cost"] / candidate_eval["cost"]
        total_cost += candidate_eval["cost"]
        total_ratio += ratio

    n = float(len(CASES))
    metrics["valid"] = 1.0
    metrics["num_cases"] = n
    metrics["avg_cost"] = total_cost / n
    metrics["avg_cost_ratio"] = total_ratio / n
    metrics["combined_score"] = -metrics["avg_cost"]
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program")
    parser.add_argument("--metrics-out", default="metrics.json")
    args = parser.parse_args()

    metrics, artifacts = evaluate(args.program)
    metrics_path = Path(args.metrics_out)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if artifacts:
        Path("artifacts.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
"""


GENERIC_REQUIREMENTS = """\
stockpyl @ git+https://github.com/LarrySnyder/stockpyl.git
numpy
scipy
"""


GENERIC_CONSTRAINTS = """\
Edit only `scripts/init.py`.
Modify only code between `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` in that file.
Do not modify files under `baseline/`, `runtime/`, or `verification/`.
Return a finite and feasible solution for every frozen case.
"""


def render_problem(task: dict) -> str:
    cases_json = json.dumps(task["cases"], indent=4)
    kind = task["kind"]
    header = """\
from __future__ import annotations

import math
from typing import Any

from scipy.stats import norm, poisson
from stockpyl.eoq import (
    economic_order_quantity,
    economic_order_quantity_with_all_units_discounts,
    economic_order_quantity_with_incremental_discounts,
)
from stockpyl.rq import (
    r_q_cost,
    r_q_cost_poisson,
    r_q_eil_approximation,
    r_q_eoqss_approximation,
    r_q_loss_function_approximation,
    r_q_poisson_exact,
)

CASES = {cases_json}
SAMPLE_INSTANCE = CASES[0]


def _to_float(value: Any) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("non-finite numeric value")
    return value


def _extract_order_quantity(solution: Any) -> float:
    if isinstance(solution, dict):
        if "order_quantity" not in solution:
            raise ValueError("missing order_quantity")
        return _to_float(solution["order_quantity"])
    return _to_float(solution)


def _extract_rq(solution: Any) -> tuple[int, int]:
    if isinstance(solution, dict):
        if "reorder_point" not in solution or "order_quantity" not in solution:
            raise ValueError("missing reorder_point/order_quantity")
        r = int(round(_to_float(solution["reorder_point"])))
        q = int(round(_to_float(solution["order_quantity"])))
        return r, q
    if isinstance(solution, (tuple, list)) and len(solution) == 2:
        r = int(round(_to_float(solution[0])))
        q = int(round(_to_float(solution[1])))
        return r, q
    raise ValueError("solution must be a dict or length-2 tuple/list")
"""

    if kind == "eoq_moq":
        body = """\

def solve_baseline(instance: dict[str, float]) -> dict[str, float]:
    q_star, _ = economic_order_quantity(
        instance["fixed_cost"],
        instance["holding_cost_rate"],
        instance["demand_rate"],
    )
    q = max(q_star, instance["minimum_order_quantity"])
    return {"order_quantity": float(q)}


def evaluate_solution(instance: dict[str, float], solution: Any) -> dict[str, float | bool]:
    try:
        q = _extract_order_quantity(solution)
    except Exception:
        return {"valid": False, "cost": float("inf")}
    if q < instance["minimum_order_quantity"] or q <= 0:
        return {"valid": False, "cost": float("inf")}
    _, cost = economic_order_quantity(
        instance["fixed_cost"],
        instance["holding_cost_rate"],
        instance["demand_rate"],
        order_quantity=q,
    )
    return {"valid": True, "cost": float(cost), "order_quantity": float(q)}
"""
    elif kind == "eoq_all_units":
        body = """\

def _region(instance: dict[str, float], q: float) -> int:
    region = 0
    for idx, bp in enumerate(instance["breakpoints"]):
        if q >= bp:
            region = idx
    return region


def _cost(instance: dict[str, float], q: float) -> float:
    region = _region(instance, q)
    unit_cost = instance["unit_costs"][region]
    return (
        unit_cost * instance["demand_rate"]
        + instance["fixed_cost"] * instance["demand_rate"] / q
        + instance["holding_cost_rate"] * unit_cost * q / 2.0
    )


def solve_baseline(instance: dict[str, float]) -> dict[str, float]:
    q, region, cost = economic_order_quantity_with_all_units_discounts(
        instance["fixed_cost"],
        instance["holding_cost_rate"],
        instance["demand_rate"],
        list(instance["breakpoints"]),
        list(instance["unit_costs"]),
    )
    return {"order_quantity": float(q), "region": int(region), "cost": float(cost)}


def evaluate_solution(instance: dict[str, float], solution: Any) -> dict[str, float | bool]:
    try:
        q = _extract_order_quantity(solution)
    except Exception:
        return {"valid": False, "cost": float("inf")}
    if q <= 0:
        return {"valid": False, "cost": float("inf")}
    return {"valid": True, "cost": float(_cost(instance, q)), "order_quantity": float(q)}
"""
    elif kind == "eoq_incremental":
        body = """\

def _c_bar(instance: dict[str, float], region: int) -> float:
    if region == 0:
        return 0.0
    breakpoints = instance["breakpoints"]
    unit_costs = instance["unit_costs"]
    return sum(unit_costs[i] * (breakpoints[i + 1] - breakpoints[i]) for i in range(region)) - unit_costs[region] * breakpoints[region]


def _region(instance: dict[str, float], q: float) -> int:
    region = 0
    for idx, bp in enumerate(instance["breakpoints"]):
        if q >= bp:
            region = idx
    return region


def _cost(instance: dict[str, float], q: float) -> float:
    region = _region(instance, q)
    unit_cost = instance["unit_costs"][region]
    c_bar = _c_bar(instance, region)
    return (
        unit_cost * instance["demand_rate"]
        + instance["holding_cost_rate"] * c_bar / 2.0
        + (instance["fixed_cost"] + c_bar) * instance["demand_rate"] / q
        + instance["holding_cost_rate"] * unit_cost * q / 2.0
    )


def solve_baseline(instance: dict[str, float]) -> dict[str, float]:
    q, region, cost = economic_order_quantity_with_incremental_discounts(
        instance["fixed_cost"],
        instance["holding_cost_rate"],
        instance["demand_rate"],
        list(instance["breakpoints"]),
        list(instance["unit_costs"]),
    )
    return {"order_quantity": float(q), "region": int(region), "cost": float(cost)}


def evaluate_solution(instance: dict[str, float], solution: Any) -> dict[str, float | bool]:
    try:
        q = _extract_order_quantity(solution)
    except Exception:
        return {"valid": False, "cost": float("inf")}
    if q <= 0:
        return {"valid": False, "cost": float("inf")}
    return {"valid": True, "cost": float(_cost(instance, q)), "order_quantity": float(q)}
"""
    elif kind == "rq_poisson":
        body = """\

def _service_level(instance: dict[str, float], r: int) -> float:
    mean_lt = instance["demand_mean"] * instance["lead_time"]
    return float(poisson.cdf(r, mean_lt))


def solve_baseline(instance: dict[str, float]) -> dict[str, float]:
    r, q, _ = r_q_poisson_exact(
        instance["holding_cost"],
        instance["stockout_cost"],
        instance["fixed_cost"],
        instance["demand_mean"],
        instance["lead_time"],
    )
    r = int(round(r))
    q = max(1, int(round(q)))
    while _service_level(instance, r) < instance["target_csl"]:
        r += 1
    return {"reorder_point": r, "order_quantity": q}


def evaluate_solution(instance: dict[str, float], solution: Any) -> dict[str, float | bool]:
    try:
        r, q = _extract_rq(solution)
    except Exception:
        return {"valid": False, "cost": float("inf")}
    if q <= 0:
        return {"valid": False, "cost": float("inf")}
    csl = _service_level(instance, r)
    if csl < instance["target_csl"]:
        return {"valid": False, "cost": float("inf")}
    cost = r_q_cost_poisson(
        r,
        q,
        instance["holding_cost"],
        instance["stockout_cost"],
        instance["fixed_cost"],
        instance["demand_mean"],
        instance["lead_time"],
    )
    return {"valid": True, "cost": float(cost), "reorder_point": int(r), "order_quantity": int(q), "service_level": float(csl)}
"""
    elif kind == "rq_normal":
        body = """\

def _service_level(instance: dict[str, float], r: int) -> float:
    mean_lt = instance["demand_mean"] * instance["lead_time"]
    sd_lt = instance["demand_sd"] * math.sqrt(instance["lead_time"])
    z = (r - mean_lt) / sd_lt
    return float(norm.cdf(z))


def _candidate_pairs(instance: dict[str, float]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for fn in (r_q_eil_approximation, r_q_eoqss_approximation, r_q_loss_function_approximation):
        result = fn(
            instance["holding_cost"],
            instance["stockout_cost"],
            instance["fixed_cost"],
            instance["demand_mean"],
            instance["demand_sd"],
            instance["lead_time"],
        )
        if len(result) >= 2:
            r = int(round(float(result[0])))
            q = max(1, int(round(float(result[1]))))
            pairs.append((r, q))
    return pairs


def solve_baseline(instance: dict[str, float]) -> dict[str, float]:
    best = None
    for r, q in _candidate_pairs(instance):
        while _service_level(instance, r) < instance["target_csl"]:
            r += 1
        cost = r_q_cost(
            r,
            q,
            instance["holding_cost"],
            instance["stockout_cost"],
            instance["fixed_cost"],
            instance["demand_mean"],
            instance["demand_sd"],
            instance["lead_time"],
        )
        candidate = (float(cost), int(r), int(q))
        if best is None or candidate < best:
            best = candidate
    if best is None:
        raise RuntimeError("no feasible baseline candidate")
    _, r, q = best
    return {"reorder_point": r, "order_quantity": q}


def evaluate_solution(instance: dict[str, float], solution: Any) -> dict[str, float | bool]:
    try:
        r, q = _extract_rq(solution)
    except Exception:
        return {"valid": False, "cost": float("inf")}
    if q <= 0:
        return {"valid": False, "cost": float("inf")}
    csl = _service_level(instance, r)
    if csl < instance["target_csl"]:
        return {"valid": False, "cost": float("inf")}
    cost = r_q_cost(
        r,
        q,
        instance["holding_cost"],
        instance["stockout_cost"],
        instance["fixed_cost"],
        instance["demand_mean"],
        instance["demand_sd"],
        instance["lead_time"],
    )
    return {"valid": True, "cost": float(cost), "reorder_point": int(r), "order_quantity": int(q), "service_level": float(csl)}
"""
    else:
        raise ValueError(f"unknown task kind: {kind}")

    return textwrap.dedent(header.format(cases_json=cases_json) + body)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).rstrip() + "\n", encoding="utf-8")


def provenance_summary(kind: str) -> str:
    if kind == "eoq_moq":
        return "Upstream lineage: `Stockpyl` EOQ routines and the classic deterministic EOQ model family."
    if kind == "eoq_all_units":
        return "Upstream lineage: `Stockpyl` EOQ with all-units discount routines and the standard all-units discount EOQ model family."
    if kind == "eoq_incremental":
        return "Upstream lineage: `Stockpyl` EOQ with incremental discount routines and the standard incremental discount EOQ model family."
    if kind == "rq_poisson":
        return "Upstream lineage: `Stockpyl` single-echelon `(r,Q)` routines for Poisson demand."
    if kind == "rq_normal":
        return "Upstream lineage: `Stockpyl` single-echelon `(r,Q)` routines for Normal demand."
    raise ValueError(f"unknown task kind: {kind}")


def task_source_en(kind: str) -> str:
    if kind == "eoq_moq":
        return "Canonical source lineage comes from `Stockpyl` EOQ routines and standard deterministic EOQ formulas. The benchmark uses frozen benchmark-local cases defined in `runtime/problem.py`."
    if kind == "eoq_all_units":
        return "Canonical source lineage comes from `Stockpyl` all-units discount EOQ routines. The benchmark uses frozen benchmark-local cases defined in `runtime/problem.py`."
    if kind == "eoq_incremental":
        return "Canonical source lineage comes from `Stockpyl` incremental discount EOQ routines. The benchmark uses frozen benchmark-local cases defined in `runtime/problem.py`."
    if kind == "rq_poisson":
        return "Canonical source lineage comes from `Stockpyl` Poisson-demand `(r,Q)` routines. The benchmark uses frozen benchmark-local cases defined in `runtime/problem.py`."
    if kind == "rq_normal":
        return "Canonical source lineage comes from `Stockpyl` Normal-demand `(r,Q)` routines. The benchmark uses frozen benchmark-local cases defined in `runtime/problem.py`."
    raise ValueError(f"unknown task kind: {kind}")


def task_source_zh(kind: str) -> str:
    if kind == "eoq_moq":
        return "规范来源来自 `Stockpyl` 的 EOQ 公式实现与经典确定性 EOQ 模型。固定评测样例定义在 `runtime/problem.py` 中，属于 benchmark 内部冻结参数表。"
    if kind == "eoq_all_units":
        return "规范来源来自 `Stockpyl` 的 all-units discount EOQ 实现。固定评测样例定义在 `runtime/problem.py` 中，属于 benchmark 内部冻结参数表。"
    if kind == "eoq_incremental":
        return "规范来源来自 `Stockpyl` 的 incremental discount EOQ 实现。固定评测样例定义在 `runtime/problem.py` 中，属于 benchmark 内部冻结参数表。"
    if kind == "rq_poisson":
        return "规范来源来自 `Stockpyl` 的 Poisson-demand `(r,Q)` 实现。固定评测样例定义在 `runtime/problem.py` 中，属于 benchmark 内部冻结参数表。"
    if kind == "rq_normal":
        return "规范来源来自 `Stockpyl` 的 Normal-demand `(r,Q)` 实现。固定评测样例定义在 `runtime/problem.py` 中，属于 benchmark 内部冻结参数表。"
    raise ValueError(f"unknown task kind: {kind}")


def source_manifest_text(kind: str) -> str:
    if kind == "eoq_moq":
        upstream = "- `stockpyl.eoq.economic_order_quantity`\n- deterministic EOQ formulas as documented in standard inventory theory references used by Stockpyl"
    elif kind == "eoq_all_units":
        upstream = "- `stockpyl.eoq.economic_order_quantity_with_all_units_discounts`\n- all-units discount EOQ formulas as documented in standard inventory theory references used by Stockpyl"
    elif kind == "eoq_incremental":
        upstream = "- `stockpyl.eoq.economic_order_quantity_with_incremental_discounts`\n- incremental discount EOQ formulas as documented in standard inventory theory references used by Stockpyl"
    elif kind == "rq_poisson":
        upstream = "- `stockpyl.rq.r_q_poisson_exact`\n- single-echelon `(r,Q)` formulas for Poisson demand used in Stockpyl"
    elif kind == "rq_normal":
        upstream = "- `stockpyl.rq.r_q_eil_approximation`\n- `stockpyl.rq.r_q_eoqss_approximation`\n- `stockpyl.rq.r_q_loss_function_approximation`\n- single-echelon `(r,Q)` formulas for Normal demand used in Stockpyl"
    else:
        raise ValueError(f"unknown task kind: {kind}")
    return textwrap.dedent(
        f"""\
        # Source Manifest

        - Upstream library: `Stockpyl`
        - Upstream lineage:
          {upstream}
        - Data provenance: this benchmark does not use an external dataset. It uses benchmark-local frozen numeric instances defined in `runtime/problem.py`.
        - Transformation path: no preprocessing pipeline; the parameter tables are authored directly in the benchmark runtime.
        - License lineage: Stockpyl is released under the MIT License.
        """
    )


def bootstrap_task(repo_root: Path, task: dict) -> None:
    task_dir = repo_root / "benchmarks" / task["domain"] / task["slug"]
    task_values = dict(task)
    task_values["provenance_summary"] = provenance_summary(task["kind"])
    task_values["task_source_en"] = task_source_en(task["kind"])
    task_values["task_source_zh"] = task_source_zh(task["kind"])

    write_text(task_dir / "README.md", GENERIC_README.format(**task_values))
    write_text(task_dir / "Task.md", GENERIC_TASK.format(**task_values))
    write_text(task_dir / "Task_zh-CN.md", GENERIC_TASK_ZH.format(**task_values))
    write_text(task_dir / "references" / "source_manifest.md", source_manifest_text(task["kind"]))
    write_text(task_dir / "scripts" / "init.py", GENERIC_INIT.format(**task_values))
    write_text(task_dir / "baseline" / "solution.py", GENERIC_BASELINE.format(**task_values))
    write_text(task_dir / "runtime" / "problem.py", render_problem(task))
    write_text(task_dir / "verification" / "evaluator.py", GENERIC_EVALUATOR.format(**task_values))
    write_text(task_dir / "verification" / "requirements.txt", GENERIC_REQUIREMENTS)

    write_text(task_dir / "frontier_eval" / "initial_program.txt", "scripts/init.py\n")
    write_text(task_dir / "frontier_eval" / "candidate_destination.txt", "scripts/init.py\n")
    write_text(task_dir / "frontier_eval" / "eval_command.txt", "{python} verification/evaluator.py {candidate} --metrics-out metrics.json\n")
    write_text(task_dir / "frontier_eval" / "eval_cwd.txt", ".\n")
    write_text(task_dir / "frontier_eval" / "agent_files.txt", "Task.md\nTask_zh-CN.md\nREADME.md\nbaseline/solution.py\nruntime/problem.py\n")
    write_text(task_dir / "frontier_eval" / "readonly_files.txt", "baseline/solution.py\nruntime/problem.py\nverification/evaluator.py\nreferences/source_manifest.md\n")
    write_text(task_dir / "frontier_eval" / "constraints.txt", GENERIC_CONSTRAINTS)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for task in TASKS:
        bootstrap_task(repo_root, task)
        print(f"bootstrapped {task['domain']}/{task['slug']}")


if __name__ == "__main__":
    main()
