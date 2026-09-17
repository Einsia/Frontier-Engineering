#!/usr/bin/env python3

from __future__ import annotations

import json
import textwrap
from pathlib import Path


TASKS = [
    {
        "domain": "StructuralOptimization",
        "slug": "CantileverComplianceTopologyOptimization",
        "title": "Cantilever Compliance Topology Optimization",
        "short": "Minimize compliance on a frozen cantilever beam using pyMOTO's SIMP formulation and a fixed material budget.",
        "geometry": "cantilever",
        "provenance_class": "official-example-derived",
        "problem": {
            "geometry": "cantilever",
            "nx": 36,
            "ny": 12,
            "volume_fraction": 0.45,
            "minimum_density": 0.001,
            "filter_radius": 1.5,
            "penalty_power": 3.0,
            "move_limit": 0.2,
            "max_iterations": 30,
            "load_scale": 1.0,
        },
        "source_manifest": """\
# Source Manifest

- Upstream solver/formulation: `pyMOTO`
- Upstream files:
  - `examples/topology_optimization/ex_compliance.py`
  - `examples/topology_optimization/ex_compliance_69line.py`
- Geometry provenance: clamped-left cantilever with a point load at the free side, directly aligned with the official pyMOTO compliance examples.
- Frozen benchmark status: this repository vendors only a reduced-size local instance and fixed solver settings; there is no external data file.
- License lineage: pyMOTO is released under the MIT License.
- Provenance class: official-example-derived frozen instance.
""",
    },
    {
        "domain": "StructuralOptimization",
        "slug": "MBBBeamTopologyOptimization",
        "title": "MBB Beam Topology Optimization",
        "short": "Minimize compliance on a frozen half-MBB beam using pyMOTO's SIMP formulation and a fixed material budget.",
        "geometry": "mbb_half",
        "provenance_class": "literature-derived canonical geometry",
        "problem": {
            "geometry": "mbb_half",
            "nx": 48,
            "ny": 16,
            "volume_fraction": 0.50,
            "minimum_density": 0.001,
            "filter_radius": 1.5,
            "penalty_power": 3.0,
            "move_limit": 0.2,
            "max_iterations": 30,
            "load_scale": 1.0,
        },
        "source_manifest": """\
# Source Manifest

- Upstream solver/formulation: `pyMOTO`
- Upstream files:
  - `examples/topology_optimization/ex_compliance.py`
  - `examples/topology_optimization/ex_self_weight.py` (`bc == 2` names the MBB-beam support style)
- Geometry provenance: the standard half-MBB beam benchmark lineage used in density-based topology optimization, including Sigmund (2001), "A 99 line topology optimization code written in Matlab".
- Frozen benchmark status: this repository vendors a reduced-size local half-MBB instance with fixed symmetry/support conditions and a fixed point load.
- License lineage: pyMOTO is released under the MIT License.
- Provenance class: literature-derived canonical geometry, locally frozen.
""",
    },
    {
        "domain": "StructuralOptimization",
        "slug": "BridgeTopologyOptimization",
        "title": "Bridge Topology Optimization",
        "short": "Minimize compliance on a frozen bridge-like topology optimization case with a passive-solid deck and distributed load.",
        "geometry": "bridge_half",
        "provenance_class": "traceable literature-derived local instance",
        "problem": {
            "geometry": "bridge_half",
            "nx": 48,
            "ny": 16,
            "volume_fraction": 0.45,
            "minimum_density": 0.001,
            "filter_radius": 1.5,
            "penalty_power": 3.0,
            "move_limit": 0.2,
            "max_iterations": 30,
            "load_scale": 1.0,
            "passive_solid_top_rows": 1,
        },
        "source_manifest": """\
# Source Manifest

- Upstream solver/formulation: `pyMOTO`
- Upstream files:
  - `examples/topology_optimization/ex_compliance.py`
  - `examples/topology_optimization/ex_compliance_69line.py`
- Geometry provenance: a frozen bridge-like case derived from the standard bridge-structure topology-optimization literature, including the "symmetric half of a bridge structure" discussion in Couri et al. (2024), *One-shot procedures for topology optimization: a comparative study*, with a passive-solid deck row added so the distributed load has an explicit load-bearing support region.
- Frozen benchmark status: this repository vendors a traceable local instance; it is not claimed to be an official upstream data file.
- License lineage: pyMOTO is released under the MIT License.
- Provenance class: traceable literature-derived local instance.
""",
    },
]


README_TEMPLATE = """\
# {title}

{short}

## Provenance

- Provenance class: `{provenance_class}`
- Frozen geometry: `{geometry}`
- Solver lineage: `pyMOTO` compliance + SIMP density optimization
- Full provenance note: see `references/source_manifest.md`

## File Layout

- `Task.md`: task contract and scoring rules.
- `Task_zh-CN.md`: Chinese translation.
- `scripts/init.py`: initial candidate file exposed to agents.
- `baseline/solution.py`: OC-style baseline update rule.
- `runtime/problem.py`: frozen physics, constraints, and optimization loop.
- `verification/evaluator.py`: evaluator entry.
- `references/source_manifest.md`: source and provenance notes.

## Quick Run

From repository root:

```bash
/mnt/shared-storage-user/p1-shared/luotianwei/Frontier-Engineering/.venv/bin/python \\
  benchmarks/{domain}/{slug}/verification/evaluator.py \\
  benchmarks/{domain}/{slug}/scripts/init.py \\
  --metrics-out /tmp/{slug}_metrics.json
```

Run with `frontier_eval`:

```bash
python -m frontier_eval \\
  task=unified \\
  task.benchmark={domain}/{slug} \\
  task.runtime.use_conda_run=false \\
  task.runtime.python_path=/mnt/shared-storage-user/p1-shared/luotianwei/Frontier-Engineering/.venv/bin/python \\
  algorithm.iterations=0
```
"""


TASK_TEMPLATE = """\
# {title} Task

## Objective

{short}

The benchmark freezes one pyMOTO-based structural optimization case in `runtime/problem.py`.

## Submission Contract

Submit one Python file that defines:

```python
def update_density(density, sensitivity, state):
    ...
```

Inputs:

- `density`: current density vector as a NumPy array of shape `(nel,)`
- `sensitivity`: current compliance sensitivity with respect to the design vector
- `state`: a dict containing:
  - `iteration`
  - `domain_shape`
  - `volume_fraction`
  - `target_density_sum`
  - `minimum_density`
  - `move_limit`
  - `current_compliance`
  - `history`
  - `passive_solid_mask`
  - `passive_void_mask`

The function must return the next feasible density vector. A dict with key `density` is also accepted.

You may import `project_density` from `runtime.problem` if you want a helper that projects a raw proposal back onto the feasible set.

## Evaluation

The evaluator will:

1. Build the frozen pyMOTO finite-element model.
2. Run 30 fixed optimization iterations.
3. Compare the baseline OC update rule against your `update_density(...)`.
4. Reject non-finite or infeasible density updates.
5. Expose the final candidate compliance directly as the optimization score.

## Metrics

- `combined_score`: `-candidate_compliance`
- `valid`: `1.0` only if every density update is finite and feasible
- `candidate_compliance`
- `baseline_compliance`
- `final_volume_fraction`
- `volume_fraction_error`

## Failure Cases

The submission is marked invalid and receives a very low score if:

- `update_density()` is missing
- any proposed density is non-finite
- any density violates bounds, move limits, passive masks, or volume budget
- the pyMOTO solve fails
"""


TASK_ZH_TEMPLATE = """\
# {title} 任务

## 目标

{short}

评测在 `runtime/problem.py` 中冻结了一个基于 pyMOTO 的结构拓扑优化实例。

## 提交接口

提交一个 Python 文件，定义：

```python
def update_density(density, sensitivity, state):
    ...
```

输入参数：

- `density`：当前密度向量，NumPy 数组，形状为 `(nel,)`
- `sensitivity`：当前目标函数相对于设计变量的灵敏度
- `state`：字典，包含：
  - `iteration`
  - `domain_shape`
  - `volume_fraction`
  - `target_density_sum`
  - `minimum_density`
  - `move_limit`
  - `current_compliance`
  - `history`
  - `passive_solid_mask`
  - `passive_void_mask`

返回值必须是下一步的可行密度向量。也接受包含 `density` 字段的字典。

如果你只想先产生一个原始提案，可以从 `runtime.problem` 导入 `project_density`，把原始提案投影回可行域。

## 评测方式

评测器会：

1. 构建固定的 pyMOTO 有限元模型。
2. 运行固定 30 次优化迭代。
3. 对比 baseline 的 OC 更新规则与你的 `update_density(...)`。
4. 拒绝任何非有限或不可行的密度更新。
5. 直接以最终 candidate compliance 作为优化分数。

## 指标

- `combined_score`：`-candidate_compliance`
- `valid`：所有密度更新都有限且可行时为 `1.0`
- `candidate_compliance`
- `baseline_compliance`
- `final_volume_fraction`
- `volume_fraction_error`
"""


INIT_TEMPLATE = """\
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
            ps = str(parent)
            if ps not in sys.path:
                sys.path.insert(0, ps)
            return
    benchmark_root = here.parents[1]
    ps = str(benchmark_root)
    if ps not in sys.path:
        sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.{domain}.{slug}.baseline.solution import update_density as _baseline_update_density
except ModuleNotFoundError:
    from baseline.solution import update_density as _baseline_update_density


# EVOLVE-BLOCK-START
def update_density(density, sensitivity, state):
    return _baseline_update_density(density, sensitivity, state)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    try:
        from benchmarks.{domain}.{slug}.runtime.problem import run_optimization
    except ModuleNotFoundError:
        from runtime.problem import run_optimization

    result = run_optimization(update_density)
    print(result["compliance"])
"""


BASELINE_TEMPLATE = """\
from __future__ import annotations

try:
    from benchmarks.{domain}.{slug}.runtime.problem import oc_update
except ModuleNotFoundError:
    from runtime.problem import oc_update


def update_density(density, sensitivity, state):
    return oc_update(density, sensitivity, state)
"""


RUNTIME_TEMPLATE = """\
from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np
import pymoto as pym
from scipy.sparse import SparseEfficiencyWarning


warnings.filterwarnings("ignore", category=SparseEfficiencyWarning)

PROBLEM = {problem_json}
SAMPLE_INSTANCE = {{
    "title": "{title}",
    "geometry": PROBLEM["geometry"],
    "domain_shape": [PROBLEM["nx"], PROBLEM["ny"]],
    "volume_fraction": PROBLEM["volume_fraction"],
    "filter_radius": PROBLEM["filter_radius"],
    "penalty_power": PROBLEM["penalty_power"],
    "max_iterations": PROBLEM["max_iterations"],
}}


def load_instance() -> dict[str, Any]:
    return dict(SAMPLE_INSTANCE)


def _passive_masks(domain: pym.VoxelDomain) -> tuple[np.ndarray, np.ndarray]:
    solid = np.zeros(domain.nel, dtype=bool)
    void = np.zeros(domain.nel, dtype=bool)
    top_rows = int(PROBLEM.get("passive_solid_top_rows", 0))
    for offset in range(top_rows):
        y = PROBLEM["ny"] - 1 - offset
        solid[domain.elements[:, y, 0].reshape(-1)] = True
    return solid, void


def _initial_density(domain: pym.VoxelDomain, solid_mask: np.ndarray, void_mask: np.ndarray) -> np.ndarray:
    target_sum = PROBLEM["volume_fraction"] * domain.nel
    fixed_sum = float(np.sum(solid_mask)) + PROBLEM["minimum_density"] * float(np.sum(void_mask))
    free_mask = ~(solid_mask | void_mask)
    free_count = int(np.sum(free_mask))
    if free_count == 0:
        raise ValueError("no free design variables remain")
    free_density = (target_sum - fixed_sum) / free_count
    if not (PROBLEM["minimum_density"] <= free_density <= 1.0):
        raise ValueError("target volume is infeasible for the chosen passive masks")
    density = np.full(domain.nel, free_density, dtype=float)
    density[solid_mask] = 1.0
    density[void_mask] = PROBLEM["minimum_density"]
    return density


def _fixed_dofs(domain: pym.VoxelDomain) -> np.ndarray:
    geometry = PROBLEM["geometry"]
    if geometry == "cantilever":
        left_nodes = domain.nodes[0, :].flatten()
        return domain.get_dofnumber(left_nodes, [0, 1], 2).flatten()
    if geometry in {{"mbb_half", "bridge_half"}}:
        left_nodes = domain.nodes[0, :].flatten()
        left_x = domain.get_dofnumber(left_nodes, 0, 2).flatten()
        right_bottom = int(domain.nodes[PROBLEM["nx"], 0, 0])
        return np.concatenate([left_x, np.array([2 * right_bottom + 1], dtype=int)])
    raise ValueError(f"unsupported geometry: {{geometry}}")


def _force_vector(domain: pym.VoxelDomain) -> np.ndarray:
    f = np.zeros(domain.nnodes * 2, dtype=float)
    geometry = PROBLEM["geometry"]
    load = float(PROBLEM["load_scale"])
    if geometry == "cantilever":
        force_node = int(domain.nodes[PROBLEM["nx"], PROBLEM["ny"] // 2, 0])
        f[2 * force_node + 1] = load
        return f
    if geometry == "mbb_half":
        force_node = int(domain.nodes[0, PROBLEM["ny"], 0])
        f[2 * force_node + 1] = -load
        return f
    if geometry == "bridge_half":
        deck_nodes = domain.nodes[:, PROBLEM["ny"], 0].flatten()
        f[2 * deck_nodes + 1] = -load / len(deck_nodes)
        return f
    raise ValueError(f"unsupported geometry: {{geometry}}")


def _build_context() -> dict[str, Any]:
    domain = pym.VoxelDomain(PROBLEM["nx"], PROBLEM["ny"])
    fixed_dofs = _fixed_dofs(domain)
    force = _force_vector(domain)
    passive_solid_mask, passive_void_mask = _passive_masks(domain)
    x0 = _initial_density(domain, passive_solid_mask, passive_void_mask)
    signal = pym.Signal("x", state=x0.copy())
    with pym.Network() as network:
        filtered = pym.DensityFilter(domain=domain, radius=PROBLEM["filter_radius"])(signal)
        penalized = pym.MathExpression(
            expression=f"{{PROBLEM['minimum_density']}} + {{1.0 - PROBLEM['minimum_density']}}*inp0^{{PROBLEM['penalty_power']}}"
        )(filtered)
        stiffness = pym.AssembleStiffness(domain=domain, bc=fixed_dofs)(penalized)
        displacement = pym.LinSolve(symmetric=True, positive_definite=True)(stiffness, force)
        compliance = pym.EinSum(expression="i,i->")(displacement, force)
    network.response()
    return {{
        "domain": domain,
        "fixed_dofs": fixed_dofs,
        "force": force,
        "signal": signal,
        "network": network,
        "compliance_signal": compliance,
        "passive_solid_mask": passive_solid_mask,
        "passive_void_mask": passive_void_mask,
    }}


def _extract_density(value: Any, expected_size: int) -> np.ndarray:
    if isinstance(value, dict):
        if "density" not in value:
            raise ValueError("missing density key")
        value = value["density"]
    density = np.asarray(value, dtype=float).reshape(-1)
    if density.size != expected_size:
        raise ValueError(f"density must have length {{expected_size}}, got {{density.size}}")
    if not np.all(np.isfinite(density)):
        raise ValueError("density contains non-finite values")
    return density


def _target_density_sum(state: dict[str, Any]) -> float:
    return float(state["target_density_sum"])


def density_bounds(previous_density: np.ndarray, state: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    lower = np.maximum(float(state["minimum_density"]), previous_density - float(state["move_limit"]))
    upper = np.minimum(1.0, previous_density + float(state["move_limit"]))
    solid_mask = np.asarray(state["passive_solid_mask"], dtype=bool)
    void_mask = np.asarray(state["passive_void_mask"], dtype=bool)
    if solid_mask.any():
        lower = lower.copy()
        upper = upper.copy()
        lower[solid_mask] = 1.0
        upper[solid_mask] = 1.0
    if void_mask.any():
        lower = lower.copy()
        upper = upper.copy()
        lower[void_mask] = float(state["minimum_density"])
        upper[void_mask] = float(state["minimum_density"])
    return lower, upper


def _project_sum_with_bounds(raw: np.ndarray, lower: np.ndarray, upper: np.ndarray, target_sum: float) -> np.ndarray:
    if float(np.sum(lower)) - 1e-9 > target_sum or float(np.sum(upper)) + 1e-9 < target_sum:
        raise ValueError("target density sum is infeasible under current bounds")
    lam_low = float(np.min(raw - upper))
    lam_high = float(np.max(raw - lower))
    for _ in range(80):
        lam = 0.5 * (lam_low + lam_high)
        candidate = np.clip(raw - lam, lower, upper)
        if float(np.sum(candidate)) > target_sum:
            lam_low = lam
        else:
            lam_high = lam
    return np.clip(raw - lam_high, lower, upper)


def project_density(raw_density: Any, previous_density: np.ndarray, state: dict[str, Any]) -> np.ndarray:
    raw = _extract_density(raw_density, previous_density.size)
    lower, upper = density_bounds(previous_density, state)
    return _project_sum_with_bounds(raw, lower, upper, _target_density_sum(state))


def validate_density(candidate_density: np.ndarray, previous_density: np.ndarray, state: dict[str, Any]) -> None:
    lower, upper = density_bounds(previous_density, state)
    tol = 1e-6
    if np.any(candidate_density < lower - tol) or np.any(candidate_density > upper + tol):
        raise ValueError("density violates bounds, move limit, or passive masks")
    volume_error = abs(float(np.sum(candidate_density)) - _target_density_sum(state))
    if volume_error > 1e-4:
        raise ValueError("density violates target volume")


def oc_update(density: np.ndarray, sensitivity: np.ndarray, state: dict[str, Any]) -> np.ndarray:
    lower, upper = density_bounds(density, state)
    sens = np.asarray(sensitivity, dtype=float).reshape(-1)
    if sens.shape != density.shape:
        raise ValueError("sensitivity shape mismatch")
    sens = np.minimum(sens, -1e-12)
    l1, l2 = 1e-9, 1e9
    for _ in range(80):
        lam = 0.5 * (l1 + l2)
        candidate = np.clip(density * np.sqrt(np.maximum(1e-12, -sens / lam)), lower, upper)
        if float(np.sum(candidate)) > _target_density_sum(state):
            l1 = lam
        else:
            l2 = lam
    return np.clip(density * np.sqrt(np.maximum(1e-12, -sens / l2)), lower, upper)


def run_optimization(update_density, max_iterations: int | None = None) -> dict[str, Any]:
    context = _build_context()
    signal = context["signal"]
    network = context["network"]
    compliance_signal = context["compliance_signal"]

    history: list[float] = [float(compliance_signal.state)]
    iterations = int(PROBLEM["max_iterations"] if max_iterations is None else max_iterations)
    for iteration in range(iterations):
        network.reset()
        compliance_signal.sensitivity = 1.0
        network.sensitivity()
        density = np.asarray(signal.state, dtype=float).reshape(-1).copy()
        sensitivity = np.asarray(signal.sensitivity, dtype=float).reshape(-1).copy()
        state = {{
            "iteration": iteration,
            "domain_shape": (PROBLEM["nx"], PROBLEM["ny"]),
            "volume_fraction": PROBLEM["volume_fraction"],
            "target_density_sum": PROBLEM["volume_fraction"] * context["domain"].nel,
            "minimum_density": PROBLEM["minimum_density"],
            "move_limit": PROBLEM["move_limit"],
            "current_compliance": float(compliance_signal.state),
            "history": tuple(history),
            "passive_solid_mask": context["passive_solid_mask"].copy(),
            "passive_void_mask": context["passive_void_mask"].copy(),
        }}
        candidate = update_density(density.copy(), sensitivity.copy(), state)
        density_next = _extract_density(candidate, density.size)
        validate_density(density_next, density, state)
        signal.state = density_next
        network.response()
        history.append(float(compliance_signal.state))

    final_density = np.asarray(signal.state, dtype=float).reshape(-1)
    return {{
        "valid": True,
        "compliance": float(compliance_signal.state),
        "history": history,
        "iterations": iterations,
        "final_volume_fraction": float(np.mean(final_density)),
        "volume_fraction_error": abs(float(np.mean(final_density)) - PROBLEM["volume_fraction"]),
    }}
"""


EVALUATOR_TEMPLATE = """\
from __future__ import annotations

import argparse
import json
import math
import runpy
import traceback
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    return Path.cwd().resolve()


def _benchmark_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_path() -> None:
    import sys

    for p in (_repo_root(), _benchmark_root()):
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.{domain}.{slug}.baseline.solution import update_density as baseline_update_density
    from benchmarks.{domain}.{slug}.runtime.problem import run_optimization
except ModuleNotFoundError:
    from baseline.solution import update_density as baseline_update_density
    from runtime.problem import run_optimization


def evaluate(program_path: str) -> tuple[dict[str, float], dict[str, str]]:
    metrics = {{
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_compliance": 0.0,
        "baseline_compliance": 0.0,
        "final_volume_fraction": 0.0,
        "volume_fraction_error": 0.0,
    }}
    artifacts: dict[str, str] = {{}}

    program = Path(program_path).expanduser().resolve()
    namespace = runpy.run_path(str(program), run_name="candidate_program")
    update_density = namespace.get("update_density")
    if not callable(update_density):
        artifacts["error_message"] = "candidate must define update_density(density, sensitivity, state)"
        return metrics, artifacts

    try:
        baseline = run_optimization(baseline_update_density)
        candidate = run_optimization(update_density)
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts

    baseline_compliance = float(baseline["compliance"])
    candidate_compliance = float(candidate["compliance"])
    if not math.isfinite(baseline_compliance) or baseline_compliance <= 0:
        artifacts["error_message"] = "internal baseline produced an invalid compliance value"
        return metrics, artifacts
    if not math.isfinite(candidate_compliance) or candidate_compliance <= 0:
        artifacts["error_message"] = "candidate produced an invalid compliance value"
        return metrics, artifacts

    metrics["valid"] = 1.0
    metrics["candidate_compliance"] = candidate_compliance
    metrics["baseline_compliance"] = baseline_compliance
    metrics["final_volume_fraction"] = float(candidate["final_volume_fraction"])
    metrics["volume_fraction_error"] = float(candidate["volume_fraction_error"])
    metrics["combined_score"] = -candidate_compliance
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program")
    parser.add_argument("--metrics-out", default="metrics.json")
    args = parser.parse_args()
    metrics, artifacts = evaluate(args.program)
    Path(args.metrics_out).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if artifacts:
        Path("artifacts.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
"""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).rstrip() + "\n", encoding="utf-8")


def benchmark_files(domain: str, slug: str) -> dict[str, str]:
    return {
        "frontier_eval/agent_files.txt": "Task.md\nTask_zh-CN.md\nREADME.md\nbaseline/solution.py\nruntime/problem.py\n",
        "frontier_eval/candidate_destination.txt": "scripts/init.py\n",
        "frontier_eval/constraints.txt": (
            "Edit only `scripts/init.py`.\n"
            "Modify only code between `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` in that file.\n"
            "Do not modify files under `baseline/`, `runtime/`, `references/`, or `verification/`.\n"
            "Keep every density update finite and feasible.\n"
        ),
        "frontier_eval/eval_command.txt": "{python} verification/evaluator.py {candidate} --metrics-out metrics.json\n",
        "frontier_eval/eval_cwd.txt": ".\n",
        "frontier_eval/initial_program.txt": "scripts/init.py\n",
        "frontier_eval/readonly_files.txt": (
            "baseline/solution.py\n"
            "runtime/problem.py\n"
            "verification/evaluator.py\n"
            "references/source_manifest.md\n"
        ),
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for task in TASKS:
        domain = task["domain"]
        slug = task["slug"]
        root = repo_root / "benchmarks" / domain / slug
        root.mkdir(parents=True, exist_ok=True)

        problem_json = json.dumps(task["problem"], indent=4)
        write(
            root / "README.md",
            README_TEMPLATE.format(
                title=task["title"],
                short=task["short"],
                provenance_class=task["provenance_class"],
                geometry=task["problem"]["geometry"],
                domain=domain,
                slug=slug,
            ),
        )
        write(root / "Task.md", TASK_TEMPLATE.format(title=task["title"], short=task["short"]))
        write(root / "Task_zh-CN.md", TASK_ZH_TEMPLATE.format(title=task["title"], short=task["short"]))
        write(root / "references" / "source_manifest.md", task["source_manifest"])
        write(root / "scripts" / "init.py", INIT_TEMPLATE.format(domain=domain, slug=slug))
        write(root / "baseline" / "solution.py", BASELINE_TEMPLATE.format(domain=domain, slug=slug))
        write(
            root / "runtime" / "problem.py",
            RUNTIME_TEMPLATE.format(problem_json=problem_json, title=task["title"]),
        )
        write(
            root / "verification" / "evaluator.py",
            EVALUATOR_TEMPLATE.format(domain=domain, slug=slug),
        )
        write(root / "verification" / "requirements.txt", "numpy\nscipy\npymoto\n")
        for relative, content in benchmark_files(domain, slug).items():
            write(root / relative, content)


if __name__ == "__main__":
    main()
