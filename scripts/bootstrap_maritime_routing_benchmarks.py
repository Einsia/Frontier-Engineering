#!/usr/bin/env python3

from __future__ import annotations

import textwrap
from pathlib import Path


TASKS = [
    {
        "slug": "FuelMinimizingShipWeatherRouting",
        "title": "Fuel-Minimizing Ship Weather Routing",
        "short": "Route a ship across a frozen coastal grid while minimizing total fuel consumption under synthetic wind and current fields.",
        "source_manifest": """\
# Source Manifest

- Upstream lineage:
  - 52North `WeatherRoutingTool` repository and README
  - Fuel-aware ship routing under weather-dependent operating conditions
- License lineage: upstream code lineage is MIT.
- Data provenance: this benchmark does not redistribute upstream weather rasters. Instead it uses a benchmark-local synthetic coastal grid and deterministic wind/current fields generated directly in `runtime/problem.py`.
- Authenticity note: the optimization shape follows official weather-routing tool lineage, while the environment data is a frozen synthetic stand-in chosen for offline reproducibility.
- Transformation path: no external preprocessing pipeline exists. The map, land mask, current field, and wind field are generated from fixed formulas and constants inside the benchmark runtime.
""",
        "readme_zh": "在固定海岸网格上，为船舶规划一条从起点到终点的航线，在合成风场与流场下最小化总燃油消耗。",
        "task_md": """\
# __TITLE__ Task

## Objective

__SHORT__

## Submission Contract

Submit one Python file that defines:

```python
def solve(instance):
    ...
```

Return either a list of grid cells or a dict with key `path`.

The path must:

1. Start at `instance["start"]`
2. End at `instance["goal"]`
3. Move only between adjacent grid cells
4. Stay on navigable water cells

## Fixed World Model

- The map, start/goal pair, synthetic wind field, and synthetic current field are fixed in `runtime/problem.py`.
- The upstream lineage is weather-aware ship routing from `WeatherRoutingTool`, but the actual grid data here is benchmark-local synthetic data with a fixed generator.

## Evaluation

The evaluator will:

1. Load the frozen routing instance
2. Validate your path mechanically
3. Compute total fuel use and travel time along the path
4. Log the shortest-hop baseline and Dijkstra reference metrics for context while scoring candidate fuel directly

## Metrics

- `combined_score`: `-candidate_fuel`
- `valid`: `1.0` only if the route is feasible
- `candidate_fuel`
- `baseline_fuel`
- `reference_fuel`
- `candidate_time_h`
- `baseline_time_h`
""",
        "task_zh": """\
# __TITLE__ 任务

## 目标

__SHORT__

## 提交接口

提交一个 Python 文件，定义：

```python
def solve(instance):
    ...
```

返回值可以是路径列表，也可以是包含 `path` 键的字典。

路径必须：

1. 从 `instance["start"]` 出发
2. 以 `instance["goal"]` 结束
3. 只能在相邻网格之间移动
4. 不能进入陆地或不可航行水域

## 固定世界模型

- 地图、起终点、合成风场与合成流场都固定在 `runtime/problem.py` 中。
- 上游算法谱系来自 `WeatherRoutingTool`，但这里的环境数据是 benchmark 内部固定生成的 synthetic asset。

## 评测方式

评测器会：

1. 载入固定实例
2. 机械检查路径可行性
3. 计算该路径的总燃油和总航时
4. 记录最短步数 baseline 与 Dijkstra 参考值作为诊断信息，同时直接以候选燃油目标打分

## 指标

- `combined_score`：`-candidate_fuel`
- `valid`：只有路径可行时才为 `1.0`
- `candidate_fuel`
- `baseline_fuel`
- `reference_fuel`
- `candidate_time_h`
- `baseline_time_h`
""",
        "runtime": """\
from __future__ import annotations

from collections import deque
import math
from typing import Any


WIDTH = 20
HEIGHT = 10
START = (1, 4)
GOAL = (18, 4)


def is_land(cell: tuple[int, int]) -> bool:
    x, y = cell
    return 8 <= x <= 12 and 2 <= y <= 6


def is_water(cell: tuple[int, int]) -> bool:
    x, y = cell
    return 0 <= x < WIDTH and 0 <= y < HEIGHT and not is_land(cell)


def _render_grid() -> tuple[str, ...]:
    rows = []
    for y in range(HEIGHT):
        chars = []
        for x in range(WIDTH):
            cell = (x, y)
            if cell == START:
                chars.append("S")
            elif cell == GOAL:
                chars.append("G")
            elif is_land(cell):
                chars.append("#")
            else:
                chars.append(".")
        rows.append("".join(chars))
    return tuple(rows)


GRID = _render_grid()


def current_at(cell: tuple[int, int]) -> tuple[float, float]:
    x, y = cell
    east = 0.04 * math.sin(0.45 * x)
    north = 0.02 * math.cos(0.35 * x)
    if y <= 2:
        return (-0.32 + east, north)
    if y >= 6:
        return (0.26 + east, -north)
    return (0.04 + east, 0.01 * math.sin(0.25 * x))


def wind_at(cell: tuple[int, int]) -> tuple[float, float]:
    x, y = cell
    side = 0.04 * math.sin(0.3 * x)
    if y <= 2:
        return (-0.60, side)
    if y >= 6:
        return (0.22, -side)
    return (-0.08, 0.02 * math.cos(0.2 * x))


def _field_to_rows(field_fn) -> tuple[tuple[tuple[float, float], ...], ...]:
    rows = []
    for y in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            row.append(tuple(round(v, 4) for v in field_fn((x, y))))
        rows.append(tuple(row))
    return tuple(rows)


CURRENT_FIELD = _field_to_rows(current_at)
WIND_FIELD = _field_to_rows(wind_at)


def load_instance() -> dict[str, Any]:
    return {
        "grid": GRID,
        "start": START,
        "goal": GOAL,
        "current_field": CURRENT_FIELD,
        "wind_field": WIND_FIELD,
        "objective": "fuel",
    }


def _to_cell(value: Any) -> tuple[int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("cell must be a length-2 sequence")
    return int(round(float(value[0]))), int(round(float(value[1])))


def extract_path(value: Any) -> list[tuple[int, int]]:
    if isinstance(value, dict):
        if "path" not in value:
            raise ValueError("missing path")
        value = value["path"]
    path = [_to_cell(cell) for cell in value]
    if not path:
        raise ValueError("path is empty")
    return path


def neighbors(cell: tuple[int, int], directions=((0, -1), (1, 0), (0, 1), (-1, 0))) -> list[tuple[int, int]]:
    x, y = cell
    result = []
    for dx, dy in directions:
        nxt = (x + dx, y + dy)
        if is_water(nxt):
            result.append(nxt)
    return result


def validate_path(value: Any) -> list[tuple[int, int]]:
    path = extract_path(value)
    if path[0] != START:
        raise ValueError("path must start at START")
    if path[-1] != GOAL:
        raise ValueError("path must end at GOAL")
    for cell in path:
        if not is_water(cell):
            raise ValueError("path enters land or leaves the map")
    for prev, curr in zip(path, path[1:]):
        dx = abs(curr[0] - prev[0])
        dy = abs(curr[1] - prev[1])
        if dx + dy != 1:
            raise ValueError("path contains a non-adjacent move")
    return path


def _leg_metrics(prev: tuple[int, int], curr: tuple[int, int]) -> tuple[float, float]:
    dx = curr[0] - prev[0]
    dy = curr[1] - prev[1]
    current_u, current_v = current_at(prev)
    wind_u, wind_v = wind_at(prev)
    current_along = current_u * dx + current_v * dy
    wind_along = wind_u * dx + wind_v * dy
    headwind = max(0.0, -wind_along)
    crosswind = abs(-dy * wind_u + dx * wind_v)
    speed = max(0.35, 1.0 + 0.65 * current_along - 0.45 * headwind)
    leg_time_h = 1.0 / speed
    fuel_rate = 1.05 + 0.55 * headwind + 0.20 * crosswind + 0.25 * max(0.0, -current_along)
    leg_fuel = leg_time_h * fuel_rate
    return leg_fuel, leg_time_h


def route_metrics(value: Any) -> dict[str, float]:
    path = validate_path(value)
    total_fuel = 0.0
    total_time_h = 0.0
    for prev, curr in zip(path, path[1:]):
        leg_fuel, leg_time_h = _leg_metrics(prev, curr)
        total_fuel += leg_fuel
        total_time_h += leg_time_h
    return {
        "fuel": float(total_fuel),
        "time_h": float(total_time_h),
        "hops": float(len(path) - 1),
    }


def _retrace(parent, node):
    path = []
    current = node
    while current is not None:
        path.append(current)
        current = parent[current]
    return path[::-1]


def baseline_path() -> list[tuple[int, int]]:
    queue = deque([START])
    parent = {START: None}
    while queue:
        current = queue.popleft()
        if current == GOAL:
            return _retrace(parent, current)
        for nxt in neighbors(current):
            if nxt not in parent:
                parent[nxt] = current
                queue.append(nxt)
    raise RuntimeError("baseline path not found")


BASELINE_PATH = baseline_path()
BASELINE_FUEL = route_metrics(BASELINE_PATH)["fuel"]
BASELINE_TIME_H = route_metrics(BASELINE_PATH)["time_h"]
REFERENCE_FUEL = 21.839377308460037
REFERENCE_TIME_H = 20.501439186435814
""",
    },
    {
        "slug": "DynamicCurrentMinimumTimeRouting",
        "title": "Dynamic-Current Minimum-Time Routing",
        "short": "Route a ship across a frozen coastal grid while minimizing travel time under deterministic current and depth fields.",
        "source_manifest": """\
# Source Manifest

- Upstream lineage:
  - TU Delft CITG `HALEM` repository and README
  - Time-optimal ship routing with dynamic currents, variable velocity, and minimum-water-depth constraints
- License lineage: upstream code lineage is MIT.
- Data provenance: this benchmark does not vendor upstream hydrographic files. It uses a benchmark-local synthetic coastal grid, synthetic current field, and synthetic depth raster generated directly in `runtime/problem.py`.
- Authenticity note: the routing objective and minimum-depth constraint follow official HALEM lineage, while the environmental data is a frozen synthetic stand-in for offline reproducibility.
- Transformation path: no external preprocessing pipeline exists. All fields are generated from fixed formulas and constants inside the benchmark runtime.
""",
        "readme_zh": "在固定海岸网格上，为船舶规划一条最短航时路线。环境包含 deterministic 流场与 depth raster，并强制最小水深约束。",
        "task_md": """\
# __TITLE__ Task

## Objective

__SHORT__

## Submission Contract

Submit one Python file that defines:

```python
def solve(instance):
    ...
```

Return either a list of grid cells or a dict with key `path`.

The path must:

1. Start at `instance["start"]`
2. End at `instance["goal"]`
3. Move only between adjacent grid cells
4. Stay on water cells with depth at least `instance["min_depth"]`

## Fixed World Model

- The map, synthetic current field, and synthetic depth raster are fixed in `runtime/problem.py`.
- The upstream lineage is dynamic-current minimum-time routing from `HALEM`, but the actual environmental data here is benchmark-local synthetic data with a fixed generator.

## Evaluation

The evaluator will:

1. Load the frozen routing instance
2. Validate your path against the land mask and minimum-depth rule
3. Compute travel time along the route
4. Log the shortest-hop baseline and Dijkstra reference metrics for context while scoring candidate travel time directly

## Metrics

- `combined_score`: `-candidate_time_h`
- `valid`: `1.0` only if the route is feasible
- `candidate_time_h`
- `baseline_time_h`
- `reference_time_h`
- `candidate_hops`
- `baseline_hops`
""",
        "task_zh": """\
# __TITLE__ 任务

## 目标

__SHORT__

## 提交接口

提交一个 Python 文件，定义：

```python
def solve(instance):
    ...
```

返回值可以是路径列表，也可以是包含 `path` 键的字典。

路径必须：

1. 从 `instance["start"]` 出发
2. 以 `instance["goal"]` 结束
3. 只能在相邻网格之间移动
4. 只能经过水深不小于 `instance["min_depth"]` 的可航行网格

## 固定世界模型

- 地图、合成流场和合成 depth raster 都固定在 `runtime/problem.py` 中。
- 上游算法谱系来自 `HALEM`，但这里的环境数据是 benchmark 内部固定生成的 synthetic asset。

## 评测方式

评测器会：

1. 载入固定实例
2. 按陆地与最小水深约束检查路径可行性
3. 计算总航时
4. 记录最短步数 baseline 与 Dijkstra 参考值作为诊断信息，同时直接以候选航时目标打分

## 指标

- `combined_score`：`-candidate_time_h`
- `valid`：只有路径可行时才为 `1.0`
- `candidate_time_h`
- `baseline_time_h`
- `reference_time_h`
- `candidate_hops`
- `baseline_hops`
""",
        "runtime": """\
from __future__ import annotations

from collections import deque
import math
from typing import Any


WIDTH = 20
HEIGHT = 10
START = (1, 4)
GOAL = (18, 4)
MIN_DEPTH = 2.5


def is_land(cell: tuple[int, int]) -> bool:
    x, y = cell
    return 8 <= x <= 12 and 2 <= y <= 6


def depth_at(cell: tuple[int, int]) -> float:
    x, y = cell
    if is_land(cell):
        return 0.0
    depth = 3.8
    if y == 1 and 7 <= x <= 13:
        depth = 2.7
    if y == 6 and 2 <= x <= 5:
        depth = 2.2
    if y == 7 and 3 <= x <= 6:
        depth = 2.4
    return depth


def is_navigable(cell: tuple[int, int]) -> bool:
    x, y = cell
    return 0 <= x < WIDTH and 0 <= y < HEIGHT and not is_land(cell) and depth_at(cell) >= MIN_DEPTH


def _render_grid() -> tuple[str, ...]:
    rows = []
    for y in range(HEIGHT):
        chars = []
        for x in range(WIDTH):
            cell = (x, y)
            if cell == START:
                chars.append("S")
            elif cell == GOAL:
                chars.append("G")
            elif is_land(cell):
                chars.append("#")
            elif depth_at(cell) < MIN_DEPTH:
                chars.append("~")
            else:
                chars.append(".")
        rows.append("".join(chars))
    return tuple(rows)


GRID = _render_grid()


def current_at(cell: tuple[int, int]) -> tuple[float, float]:
    x, y = cell
    ripple = 0.03 * math.sin(0.4 * x)
    if y <= 2:
        return (-0.36 + ripple, 0.01 * math.cos(0.3 * x))
    if y >= 7:
        return (0.44 + ripple, -0.01 * math.cos(0.3 * x))
    return (-0.05 + ripple, 0.02 * math.sin(0.2 * x))


def _field_to_rows(field_fn) -> tuple[tuple[Any, ...], ...]:
    rows = []
    for y in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            value = field_fn((x, y))
            if isinstance(value, tuple):
                row.append(tuple(round(v, 4) for v in value))
            else:
                row.append(round(float(value), 4))
        rows.append(tuple(row))
    return tuple(rows)


CURRENT_FIELD = _field_to_rows(current_at)
DEPTH_FIELD = _field_to_rows(depth_at)


def load_instance() -> dict[str, Any]:
    return {
        "grid": GRID,
        "start": START,
        "goal": GOAL,
        "current_field": CURRENT_FIELD,
        "depth_field": DEPTH_FIELD,
        "min_depth": MIN_DEPTH,
        "objective": "time",
    }


def _to_cell(value: Any) -> tuple[int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("cell must be a length-2 sequence")
    return int(round(float(value[0]))), int(round(float(value[1])))


def extract_path(value: Any) -> list[tuple[int, int]]:
    if isinstance(value, dict):
        if "path" not in value:
            raise ValueError("missing path")
        value = value["path"]
    path = [_to_cell(cell) for cell in value]
    if not path:
        raise ValueError("path is empty")
    return path


def neighbors(cell: tuple[int, int], directions=((0, -1), (1, 0), (0, 1), (-1, 0))) -> list[tuple[int, int]]:
    x, y = cell
    result = []
    for dx, dy in directions:
        nxt = (x + dx, y + dy)
        if is_navigable(nxt):
            result.append(nxt)
    return result


def validate_path(value: Any) -> list[tuple[int, int]]:
    path = extract_path(value)
    if path[0] != START:
        raise ValueError("path must start at START")
    if path[-1] != GOAL:
        raise ValueError("path must end at GOAL")
    for cell in path:
        if not is_navigable(cell):
            raise ValueError("path enters land, leaves the map, or violates minimum depth")
    for prev, curr in zip(path, path[1:]):
        dx = abs(curr[0] - prev[0])
        dy = abs(curr[1] - prev[1])
        if dx + dy != 1:
            raise ValueError("path contains a non-adjacent move")
    return path


def _leg_time(prev: tuple[int, int], curr: tuple[int, int]) -> float:
    dx = curr[0] - prev[0]
    dy = curr[1] - prev[1]
    current_u, current_v = current_at(prev)
    current_along = current_u * dx + current_v * dy
    depth = depth_at(curr)
    shallow_penalty = max(0.0, 3.0 - depth) * 0.22
    speed = max(0.25, 1.0 + 0.9 * current_along - shallow_penalty)
    return 1.0 / speed


def route_metrics(value: Any) -> dict[str, float]:
    path = validate_path(value)
    total_time_h = 0.0
    for prev, curr in zip(path, path[1:]):
        total_time_h += _leg_time(prev, curr)
    return {
        "time_h": float(total_time_h),
        "hops": float(len(path) - 1),
    }


def _retrace(parent, node):
    path = []
    current = node
    while current is not None:
        path.append(current)
        current = parent[current]
    return path[::-1]


def baseline_path() -> list[tuple[int, int]]:
    queue = deque([START])
    parent = {START: None}
    while queue:
        current = queue.popleft()
        if current == GOAL:
            return _retrace(parent, current)
        for nxt in neighbors(current):
            if nxt not in parent:
                parent[nxt] = current
                queue.append(nxt)
    raise RuntimeError("baseline path not found")


BASELINE_PATH = baseline_path()
BASELINE_TIME_H = route_metrics(BASELINE_PATH)["time_h"]
BASELINE_HOPS = route_metrics(BASELINE_PATH)["hops"]
REFERENCE_TIME_H = 20.012194145529936
REFERENCE_HOPS = 23.0
""",
    },
]


README_TEMPLATE = """\
# __TITLE__

__SHORT__

## Provenance

- Provenance class: `benchmark-local synthetic environment with traceable upstream routing lineage`
- Upstream lineage: see `references/source_manifest.md`
- Data asset: fixed synthetic coastal grid and deterministic environmental fields embedded in `runtime/problem.py`
- Redistribution status: no upstream environmental rasters are vendored

## File Layout

- `Task.md`: task contract and scoring rules
- `Task_zh-CN.md`: Chinese translation
- `README_zh-CN.md`: Chinese overview
- `scripts/init.py`: initial candidate file exposed to agents
- `baseline/solution.py`: reference baseline
- `runtime/problem.py`: frozen instance generator, validation logic, and reference costs
- `verification/evaluator.py`: evaluator entry
- `references/source_manifest.md`: provenance notes

## Quick Run

From repository root:

```bash
.venv/bin/python benchmarks/OperationsResearch/__SLUG__/verification/evaluator.py \\
  benchmarks/OperationsResearch/__SLUG__/scripts/init.py \\
  --metrics-out /tmp/__SLUG___metrics.json
```
"""


README_ZH_TEMPLATE = """\
# __TITLE__

__README_ZH__

## 说明

- 数据来源类型：`benchmark-local synthetic environment with traceable upstream routing lineage`
- 完整来源说明见 `references/source_manifest.md`
- 所有固定地图、场和约束都内嵌在 `runtime/problem.py`
"""


BASELINE_TEMPLATE = """\
from __future__ import annotations

try:
    from benchmarks.OperationsResearch.__SLUG__.runtime.problem import baseline_path
except ModuleNotFoundError:
    from runtime.problem import baseline_path


def solve(instance):
    return baseline_path()
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
    from benchmarks.OperationsResearch.__SLUG__.baseline.solution import solve as _baseline_solve
    from benchmarks.OperationsResearch.__SLUG__.runtime.problem import load_instance, route_metrics
except ModuleNotFoundError:
    from baseline.solution import solve as _baseline_solve
    from runtime.problem import load_instance, route_metrics


# EVOLVE-BLOCK-START
def solve(instance):
    return _baseline_solve(instance)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    result = solve(load_instance())
    print(route_metrics(result))
"""


EVALUATOR_FUEL = """\
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
    from benchmarks.OperationsResearch.__SLUG__.baseline.solution import solve as baseline_solve
    from benchmarks.OperationsResearch.__SLUG__.runtime.problem import BASELINE_FUEL, BASELINE_TIME_H, REFERENCE_FUEL, load_instance, route_metrics
except ModuleNotFoundError:
    from baseline.solution import solve as baseline_solve
    from runtime.problem import BASELINE_FUEL, BASELINE_TIME_H, REFERENCE_FUEL, load_instance, route_metrics


def evaluate(program_path: str):
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_fuel": 0.0,
        "baseline_fuel": float(BASELINE_FUEL),
        "reference_fuel": float(REFERENCE_FUEL),
        "candidate_time_h": 0.0,
        "baseline_time_h": float(BASELINE_TIME_H),
    }
    artifacts = {}
    namespace = runpy.run_path(str(Path(program_path).expanduser().resolve()), run_name="candidate_program")
    solve_fn = namespace.get("solve")
    if not callable(solve_fn):
        artifacts["error_message"] = "candidate must define solve(instance)"
        return metrics, artifacts

    instance = load_instance()
    try:
        baseline_metrics = route_metrics(baseline_solve(instance))
        candidate_metrics = route_metrics(solve_fn(instance))
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts

    candidate_fuel = float(candidate_metrics["fuel"])
    candidate_time_h = float(candidate_metrics["time_h"])
    if not math.isfinite(candidate_fuel) or candidate_fuel <= 0:
        artifacts["error_message"] = "candidate fuel is invalid"
        return metrics, artifacts

    metrics["valid"] = 1.0
    metrics["candidate_fuel"] = candidate_fuel
    metrics["candidate_time_h"] = candidate_time_h
    metrics["baseline_fuel"] = float(baseline_metrics["fuel"])
    metrics["baseline_time_h"] = float(baseline_metrics["time_h"])
    metrics["combined_score"] = -candidate_fuel
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


EVALUATOR_TIME = """\
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
    from benchmarks.OperationsResearch.__SLUG__.baseline.solution import solve as baseline_solve
    from benchmarks.OperationsResearch.__SLUG__.runtime.problem import BASELINE_HOPS, BASELINE_TIME_H, REFERENCE_TIME_H, load_instance, route_metrics
except ModuleNotFoundError:
    from baseline.solution import solve as baseline_solve
    from runtime.problem import BASELINE_HOPS, BASELINE_TIME_H, REFERENCE_TIME_H, load_instance, route_metrics


def evaluate(program_path: str):
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_time_h": 0.0,
        "baseline_time_h": float(BASELINE_TIME_H),
        "reference_time_h": float(REFERENCE_TIME_H),
        "candidate_hops": 0.0,
        "baseline_hops": float(BASELINE_HOPS),
    }
    artifacts = {}
    namespace = runpy.run_path(str(Path(program_path).expanduser().resolve()), run_name="candidate_program")
    solve_fn = namespace.get("solve")
    if not callable(solve_fn):
        artifacts["error_message"] = "candidate must define solve(instance)"
        return metrics, artifacts

    instance = load_instance()
    try:
        baseline_metrics = route_metrics(baseline_solve(instance))
        candidate_metrics = route_metrics(solve_fn(instance))
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts

    candidate_time_h = float(candidate_metrics["time_h"])
    if not math.isfinite(candidate_time_h) or candidate_time_h <= 0:
        artifacts["error_message"] = "candidate time is invalid"
        return metrics, artifacts

    metrics["valid"] = 1.0
    metrics["candidate_time_h"] = candidate_time_h
    metrics["candidate_hops"] = float(candidate_metrics["hops"])
    metrics["baseline_time_h"] = float(baseline_metrics["time_h"])
    metrics["baseline_hops"] = float(baseline_metrics["hops"])
    metrics["combined_score"] = -candidate_time_h
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


def render(template: str, **values: str) -> str:
    result = textwrap.dedent(template).rstrip() + "\n"
    for key, value in values.items():
        result = result.replace(f"__{key}__", value)
    return result


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).rstrip() + "\n", encoding="utf-8")


def frontier_eval_files() -> dict[str, str]:
    return {
        "frontier_eval/agent_files.txt": "Task.md\nTask_zh-CN.md\nREADME.md\nbaseline/solution.py\nruntime/problem.py\n",
        "frontier_eval/candidate_destination.txt": "scripts/init.py\n",
        "frontier_eval/constraints.txt": (
            "Edit only `scripts/init.py`.\n"
            "Modify only code between `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` in that file.\n"
            "Do not modify files under `baseline/`, `runtime/`, `references/`, or `verification/`.\n"
            "Keep outputs valid and finite.\n"
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
    domain_root = repo_root / "benchmarks" / "OperationsResearch"
    for task in TASKS:
        root = domain_root / task["slug"]
        values = {
            "TITLE": task["title"],
            "SHORT": task["short"],
            "SLUG": task["slug"],
            "README_ZH": task["readme_zh"],
        }
        write(root / "README.md", render(README_TEMPLATE, **values))
        write(root / "README_zh-CN.md", render(README_ZH_TEMPLATE, **values))
        write(root / "Task.md", render(task["task_md"], **values))
        write(root / "Task_zh-CN.md", render(task["task_zh"], **values))
        write(root / "references" / "source_manifest.md", task["source_manifest"])
        write(root / "scripts" / "init.py", render(INIT_TEMPLATE, **values))
        write(root / "baseline" / "solution.py", render(BASELINE_TEMPLATE, **values))
        write(root / "runtime" / "problem.py", task["runtime"])
        evaluator_template = EVALUATOR_FUEL if task["slug"] == "FuelMinimizingShipWeatherRouting" else EVALUATOR_TIME
        write(root / "verification" / "evaluator.py", render(evaluator_template, **values))
        write(root / "verification" / "requirements.txt", "")
        for relative, content in frontier_eval_files().items():
            write(root / relative, content)


if __name__ == "__main__":
    main()
