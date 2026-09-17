#!/usr/bin/env python3

from __future__ import annotations

import json
import textwrap
from pathlib import Path


TASKS = [
    {
        "slug": "FT10DispatchingRuleOptimization",
        "title": "FT10 Dispatching Rule Optimization",
        "short": "Optimize a greedy dispatching rule on the canonical FT10 Fisher-Thompson 10x10 job shop instance.",
        "instance_name": "ft10",
        "optimum": 930,
        "task_kind": "dispatch",
    },
    {
        "slug": "LA16DispatchingRuleOptimization",
        "title": "LA16 Dispatching Rule Optimization",
        "short": "Optimize a greedy dispatching rule on the canonical LA16 Lawrence 10x10 job shop instance.",
        "instance_name": "la16",
        "optimum": 945,
        "task_kind": "dispatch",
    },
    {
        "slug": "FT10NeighborhoodMoveSelection",
        "title": "FT10 Neighborhood Move Selection",
        "short": "Guide an adjacent-swap local search on the canonical FT10 Fisher-Thompson 10x10 job shop instance.",
        "instance_name": "ft10",
        "optimum": 930,
        "task_kind": "move",
    },
    {
        "slug": "LA16NeighborhoodMoveSelection",
        "title": "LA16 Neighborhood Move Selection",
        "short": "Guide an adjacent-swap local search on the canonical LA16 Lawrence 10x10 job shop instance.",
        "instance_name": "la16",
        "optimum": 945,
        "task_kind": "move",
    },
]


SOURCE_MANIFEST = """\
# Source Manifest

- Canonical instance: `{instance_name}`
- Upstream package: `job_shop_lib`
- Upstream file: `job_shop_lib/benchmarking/benchmark_instances.json`
- Canonical optimum recorded in upstream metadata: `{optimum}`
- Original academic provenance:
  - `ft10`: Fisher and Thompson, *Industrial Scheduling*, 1963.
  - `la16`: Lawrence benchmark set, 1984.

This benchmark vendors only the specific frozen instance JSON required for evaluation.
"""


README_TEMPLATE = """\
# {title}

{short}

## Provenance

The frozen instance is copied from the canonical benchmark set distributed in `job_shop_lib/benchmarking/benchmark_instances.json`.
The instance id is `{instance_name}`, and the published optimum used for scoring reference is `{optimum}`.

## File Layout

- `Task.md`: task contract and scoring rules.
- `Task_zh-CN.md`: Chinese version.
- `scripts/init.py`: initial candidate file exposed to agents.
- `baseline/solution.py`: baseline heuristic.
- `runtime/problem.py`: frozen instance, scheduling runtime, baseline, and evaluator helpers.
- `runtime/instance.json`: vendored canonical benchmark instance.
- `verification/evaluator.py`: evaluator entry.
- `references/source_manifest.md`: instance provenance.

## Quick Run

```bash
python benchmarks/OperationsResearch/{slug}/verification/evaluator.py \
  benchmarks/OperationsResearch/{slug}/scripts/init.py \
  --metrics-out /tmp/{slug}_metrics.json
```

Run with `frontier_eval`:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/{slug} \
  task.runtime.use_conda_run=false \
  task.runtime.python_path=/mnt/shared-storage-user/p1-shared/luotianwei/Frontier-Engineering/.venv/bin/python \
  algorithm.iterations=0
```
"""


TASK_TEMPLATE = """\
# {title} Task

## Objective

{short}

The benchmark uses one frozen canonical instance: `{instance_name}`.
The known optimum for this instance is `{optimum}`.

## Submission Contract

Submit one Python file.

For dispatch-rule tasks, define:

```python
def score_operation(operation, state):
    ...
```

For neighborhood-move tasks, define:

```python
def score_move(move, state):
    ...
```

You may optionally define:

```python
MAX_ITERATIONS = 50
```

## Evaluation

Dispatch-rule tasks:

1. Start from an empty schedule.
2. Repeatedly gather the next unscheduled operation from each job.
3. Among operations with the earliest feasible start time, choose the one with highest `score_operation`.
4. Build a complete feasible schedule and compute makespan.

Neighborhood-move tasks:

1. Start from the baseline SPT dispatch schedule.
2. Repeatedly generate adjacent machine-order swap moves.
3. Rank moves by `score_move`.
4. Apply the first improving move in ranked order.
5. Stop when no improving move exists or `MAX_ITERATIONS` is reached.

## Metrics

- `combined_score`: `-candidate_makespan`
- `valid`: `1.0` only when a complete feasible schedule is produced
- `candidate_makespan`
- `baseline_makespan`
- `relative_gap_to_optimum`

## Failure Cases

The submission is marked invalid and receives a very low score if:

- the required scoring function is missing
- the return value is non-finite
- the induced schedule is infeasible
- the candidate crashes during evaluation
"""


TASK_ZH_TEMPLATE = """\
# {title} 任务

## 目标

{short}

评测使用单个固定的 canonical 实例：`{instance_name}`。
该实例的已知最优 makespan 为 `{optimum}`。

## 提交接口

提交一个 Python 文件。

如果是 dispatch-rule 任务，需要定义：

```python
def score_operation(operation, state):
    ...
```

如果是邻域搜索任务，需要定义：

```python
def score_move(move, state):
    ...
```

你也可以额外定义：

```python
MAX_ITERATIONS = 50
```

## 评测方式

Dispatch-rule 任务：

1. 从空排程开始。
2. 每次收集每个 job 的下一道未排工序。
3. 在“最早可开工时间最小”的工序集合中，选择 `score_operation` 最高者。
4. 构造完整可行排程并计算 makespan。

邻域搜索任务：

1. 从 baseline 的 SPT dispatch 排程开始。
2. 生成机器序列上的相邻交换 move。
3. 用 `score_move` 对 move 排序。
4. 按排序顺序找到第一个真正改进 makespan 的 move 并应用。
5. 当没有改进 move 或达到 `MAX_ITERATIONS` 时停止。

## 指标

- `combined_score`：`-candidate_makespan`
- `valid`：只有生成完整可行排程时才为 `1.0`
- `candidate_makespan`
- `baseline_makespan`
- `relative_gap_to_optimum`

## 失败情况

如果出现以下情况，提交会被判为无效，并得到一个很低的分数：

- 缺少要求的评分函数
- 返回值不是有限标量
- 诱导出的排程不可行
- 候选程序在评测时崩溃
"""


INIT_DISPATCH = """\
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
    from benchmarks.OperationsResearch.{slug}.baseline.solution import score_operation as _baseline_score_operation
except ModuleNotFoundError:
    from baseline.solution import score_operation as _baseline_score_operation


# EVOLVE-BLOCK-START
def score_operation(operation, state):
    return _baseline_score_operation(operation, state)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    try:
        from benchmarks.OperationsResearch.{slug}.runtime.problem import load_instance, schedule_with_dispatch
    except ModuleNotFoundError:
        from runtime.problem import load_instance, schedule_with_dispatch
    instance = load_instance()
    result = schedule_with_dispatch(instance, score_operation)
    print(result["makespan"])
"""


INIT_MOVE = """\
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
    from benchmarks.OperationsResearch.{slug}.baseline.solution import MAX_ITERATIONS as _baseline_MAX_ITERATIONS, score_move as _baseline_score_move
except ModuleNotFoundError:
    from baseline.solution import MAX_ITERATIONS as _baseline_MAX_ITERATIONS, score_move as _baseline_score_move


# EVOLVE-BLOCK-START
MAX_ITERATIONS = _baseline_MAX_ITERATIONS


def score_move(move, state):
    return _baseline_score_move(move, state)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    try:
        from benchmarks.OperationsResearch.{slug}.runtime.problem import load_instance, run_local_search
    except ModuleNotFoundError:
        from runtime.problem import load_instance, run_local_search
    instance = load_instance()
    result = run_local_search(instance, score_move, MAX_ITERATIONS)
    print(result["makespan"])
"""


BASELINE_DISPATCH = """\
from __future__ import annotations


def score_operation(operation, state):
    return (
        -float(operation["duration"]),
        -float(operation["remaining_job_work"]),
        -float(operation["job_id"]),
    )
"""


BASELINE_MOVE = """\
from __future__ import annotations

MAX_ITERATIONS = 50


def score_move(move, state):
    return (
        float(move["delta_duration"]),
        -float(move["machine_position"]),
        -float(move["machine_id"]),
    )
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
    from benchmarks.OperationsResearch.{slug}.runtime.problem import (
        KNOWN_OPTIMUM,
        baseline_dispatch_score,
        baseline_move_score,
        load_instance,
        relative_gap,
        run_local_search,
        schedule_with_dispatch,
    )
except ModuleNotFoundError:
    from runtime.problem import (
        KNOWN_OPTIMUM,
        baseline_dispatch_score,
        baseline_move_score,
        load_instance,
        relative_gap,
        run_local_search,
        schedule_with_dispatch,
    )


TASK_KIND = "{task_kind}"


def evaluate(program_path: str) -> tuple[dict[str, float], dict[str, str]]:
    metrics = {{
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_makespan": 0.0,
        "baseline_makespan": 0.0,
        "relative_gap_to_optimum": 0.0,
    }}
    artifacts: dict[str, str] = {{}}

    program = Path(program_path).expanduser().resolve()
    namespace = runpy.run_path(str(program), run_name="candidate_program")
    instance = load_instance()

    try:
        if TASK_KIND == "dispatch":
            score_fn = namespace.get("score_operation")
            if not callable(score_fn):
                raise RuntimeError("candidate must define score_operation(operation, state)")
            baseline = schedule_with_dispatch(instance, baseline_dispatch_score)
            candidate = schedule_with_dispatch(instance, score_fn)
        else:
            score_fn = namespace.get("score_move")
            if not callable(score_fn):
                raise RuntimeError("candidate must define score_move(move, state)")
            max_iterations = int(namespace.get("MAX_ITERATIONS", 50))
            baseline = run_local_search(instance, baseline_move_score, max_iterations=50)
            candidate = run_local_search(instance, score_fn, max_iterations=max_iterations)
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts

    if not baseline["valid"]:
        artifacts["error_message"] = "internal baseline produced an invalid schedule"
        return metrics, artifacts
    if not candidate["valid"]:
        artifacts["error_message"] = "candidate produced an invalid schedule"
        return metrics, artifacts

    makespan = float(candidate["makespan"])
    baseline_makespan = float(baseline["makespan"])
    if not math.isfinite(makespan) or makespan <= 0:
        artifacts["error_message"] = "candidate makespan is invalid"
        return metrics, artifacts

    metrics["valid"] = 1.0
    metrics["candidate_makespan"] = makespan
    metrics["baseline_makespan"] = baseline_makespan
    metrics["relative_gap_to_optimum"] = relative_gap(makespan, KNOWN_OPTIMUM)
    metrics["combined_score"] = -makespan
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


RUNTIME_TEMPLATE = """\
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any


INSTANCE_PATH = Path(__file__).resolve().with_name("instance.json")
KNOWN_OPTIMUM = {optimum}


def load_instance() -> dict[str, Any]:
    return json.loads(INSTANCE_PATH.read_text(encoding="utf-8"))


def relative_gap(value: float, optimum: float) -> float:
    return float((value - optimum) / optimum)


def baseline_dispatch_score(operation: dict[str, Any], state: dict[str, Any]):
    return (
        -float(operation["duration"]),
        -float(operation["remaining_job_work"]),
        -float(operation["job_id"]),
    )


def baseline_move_score(move: dict[str, Any], state: dict[str, Any]):
    return (
        float(move["delta_duration"]),
        -float(move["machine_position"]),
        -float(move["machine_id"]),
    )


def _build_operation_tables(instance: dict[str, Any]) -> tuple[list[list[int]], list[list[int]], dict[tuple[int, int], tuple[int, int]]]:
    durations = instance["duration_matrix"]
    machines = instance["machines_matrix"]
    op_map: dict[tuple[int, int], tuple[int, int]] = {{}}
    for j, row in enumerate(machines):
        for k, machine in enumerate(row):
            op_map[(j, k)] = (machine, durations[j][k])
    return durations, machines, op_map


def schedule_with_dispatch(instance: dict[str, Any], score_operation) -> dict[str, Any]:
    durations, machines, _ = _build_operation_tables(instance)
    num_jobs = len(durations)
    num_machines = len(durations[0])
    job_next = [0] * num_jobs
    job_ready = [0] * num_jobs
    machine_ready = [0] * num_machines
    scheduled_ops: list[dict[str, Any]] = []

    total_ops = num_jobs * num_machines
    while len(scheduled_ops) < total_ops:
        candidates: list[dict[str, Any]] = []
        for job_id in range(num_jobs):
            op_index = job_next[job_id]
            if op_index >= num_machines:
                continue
            machine_id = machines[job_id][op_index]
            duration = durations[job_id][op_index]
            earliest_start = max(job_ready[job_id], machine_ready[machine_id])
            remaining_job_work = sum(durations[job_id][op_index:])
            remaining_job_ops = num_machines - op_index
            candidates.append(
                {{
                    "job_id": job_id,
                    "op_index": op_index,
                    "machine_id": machine_id,
                    "duration": duration,
                    "earliest_start": earliest_start,
                    "remaining_job_work": remaining_job_work,
                    "remaining_job_ops": remaining_job_ops,
                }}
            )
        min_start = min(op["earliest_start"] for op in candidates)
        ready = [op for op in candidates if op["earliest_start"] == min_start]
        state = {{
            "step": len(scheduled_ops),
            "job_ready_times": tuple(job_ready),
            "machine_ready_times": tuple(machine_ready),
            "current_makespan": max(max(job_ready), max(machine_ready)),
        }}
        scored: list[tuple[Any, dict[str, Any]]] = []
        for op in ready:
            score = score_operation(op, state)
            scored.append((score, op))
        scored.sort(
            key=lambda item: (
                item[0],
                -item[1]["duration"],
                -item[1]["remaining_job_work"],
                -item[1]["job_id"],
            ),
            reverse=True,
        )
        chosen = scored[0][1]
        start = chosen["earliest_start"]
        end = start + chosen["duration"]
        scheduled = dict(chosen)
        scheduled["start"] = start
        scheduled["end"] = end
        scheduled_ops.append(scheduled)
        job_ready[chosen["job_id"]] = end
        machine_ready[chosen["machine_id"]] = end
        job_next[chosen["job_id"]] += 1

    return {{
        "valid": True,
        "schedule": scheduled_ops,
        "makespan": max(op["end"] for op in scheduled_ops),
        "machine_sequences": machine_sequences_from_schedule(instance, scheduled_ops),
    }}


def machine_sequences_from_schedule(instance: dict[str, Any], schedule: list[dict[str, Any]]) -> list[list[tuple[int, int]]]:
    num_machines = len(instance["machines_matrix"][0])
    sequences: list[list[tuple[int, int, int, int]]] = [[] for _ in range(num_machines)]
    for op in schedule:
        sequences[op["machine_id"]].append((op["start"], op["job_id"], op["op_index"], op["end"]))
    out: list[list[tuple[int, int]]] = []
    for machine_ops in sequences:
        machine_ops.sort()
        out.append([(job_id, op_index) for _, job_id, op_index, _ in machine_ops])
    return out


def build_schedule_from_machine_sequences(instance: dict[str, Any], machine_sequences: list[list[tuple[int, int]]]) -> dict[str, Any]:
    durations, machines, op_map = _build_operation_tables(instance)
    num_jobs = len(durations)
    num_machines = len(durations[0])
    machine_pred: dict[tuple[int, int], tuple[int, int] | None] = {{}}
    for seq in machine_sequences:
        for idx, op in enumerate(seq):
            machine_pred[op] = seq[idx - 1] if idx > 0 else None

    scheduled: dict[tuple[int, int], dict[str, Any]] = {{}}
    total_ops = num_jobs * num_machines
    while len(scheduled) < total_ops:
        progress = False
        for job_id in range(num_jobs):
            for op_index in range(num_machines):
                op = (job_id, op_index)
                if op in scheduled:
                    continue
                job_prev = (job_id, op_index - 1) if op_index > 0 else None
                mach_prev = machine_pred.get(op)
                if job_prev is not None and job_prev not in scheduled:
                    continue
                if mach_prev is not None and mach_prev not in scheduled:
                    continue
                machine_id, duration = op_map[op]
                start = 0
                if job_prev is not None:
                    start = max(start, scheduled[job_prev]["end"])
                if mach_prev is not None:
                    start = max(start, scheduled[mach_prev]["end"])
                scheduled[op] = {{
                    "job_id": job_id,
                    "op_index": op_index,
                    "machine_id": machine_id,
                    "duration": duration,
                    "start": start,
                    "end": start + duration,
                }}
                progress = True
        if not progress:
            return {{"valid": False, "schedule": [], "makespan": float("inf"), "machine_sequences": machine_sequences}}

    schedule = list(scheduled.values())
    schedule.sort(key=lambda item: (item["start"], item["machine_id"], item["job_id"], item["op_index"]))
    return {{
        "valid": True,
        "schedule": schedule,
        "makespan": max(op["end"] for op in schedule),
        "machine_sequences": machine_sequences,
    }}


def initial_machine_sequences(instance: dict[str, Any]) -> list[list[tuple[int, int]]]:
    baseline = schedule_with_dispatch(instance, baseline_dispatch_score)
    return baseline["machine_sequences"]


def generate_adjacent_moves(instance: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    durations, machines, _ = _build_operation_tables(instance)
    schedule_by_op = {{
        (op["job_id"], op["op_index"]): op
        for op in current["schedule"]
    }}
    moves: list[dict[str, Any]] = []
    for machine_id, seq in enumerate(current["machine_sequences"]):
        for pos in range(len(seq) - 1):
            a = seq[pos]
            b = seq[pos + 1]
            a_sched = schedule_by_op[a]
            b_sched = schedule_by_op[b]
            moves.append(
                {{
                    "machine_id": machine_id,
                    "machine_position": pos,
                    "op_a": {{
                        "job_id": a[0],
                        "op_index": a[1],
                        "duration": durations[a[0]][a[1]],
                        "start": a_sched["start"],
                        "end": a_sched["end"],
                    }},
                    "op_b": {{
                        "job_id": b[0],
                        "op_index": b[1],
                        "duration": durations[b[0]][b[1]],
                        "start": b_sched["start"],
                        "end": b_sched["end"],
                    }},
                    "delta_duration": durations[a[0]][a[1]] - durations[b[0]][b[1]],
                    "current_makespan": current["makespan"],
                }}
            )
    return moves


def apply_adjacent_swap(machine_sequences: list[list[tuple[int, int]]], machine_id: int, position: int) -> list[list[tuple[int, int]]]:
    new_sequences = copy.deepcopy(machine_sequences)
    new_sequences[machine_id][position], new_sequences[machine_id][position + 1] = (
        new_sequences[machine_id][position + 1],
        new_sequences[machine_id][position],
    )
    return new_sequences


def run_local_search(instance: dict[str, Any], score_move, max_iterations: int = 50) -> dict[str, Any]:
    current = schedule_with_dispatch(instance, baseline_dispatch_score)
    if not current["valid"]:
        return current

    for iteration in range(max_iterations):
        moves = generate_adjacent_moves(instance, current)
        state = {{
            "iteration": iteration,
            "current_makespan": current["makespan"],
        }}
        scored = []
        for move in moves:
            score = score_move(move, state)
            scored.append((score, move))
        scored.sort(
            key=lambda item: (
                item[0],
                item[1]["delta_duration"],
                -item[1]["machine_position"],
            ),
            reverse=True,
        )
        improved = False
        for _, move in scored:
            new_sequences = apply_adjacent_swap(current["machine_sequences"], move["machine_id"], move["machine_position"])
            candidate = build_schedule_from_machine_sequences(instance, new_sequences)
            if candidate["valid"] and candidate["makespan"] < current["makespan"]:
                current = candidate
                improved = True
                break
        if not improved:
            break

    return current
"""


CONSTRAINTS = """\
Edit only `scripts/init.py`.
Modify only code between `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` in that file.
Do not modify files in `runtime/`, `verification/`, `references/`, or `baseline/`.
For dispatch tasks, define `score_operation(operation, state)`.
For neighborhood tasks, define `score_move(move, state)`.
Return only finite scalar scores.
"""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).rstrip() + "\n", encoding="utf-8")


def source_json_path() -> Path:
    candidates = [
        Path("/tmp/benchmark_instances.json"),
        Path("/tmp/job_shop_lib/job_shop_lib/benchmarking/benchmark_instances.json"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Could not locate benchmark_instances.json from job_shop_lib")


def load_instances() -> dict[str, dict]:
    return json.loads(source_json_path().read_text(encoding="utf-8"))


def bootstrap_task(repo_root: Path, task: dict, instance_payload: dict) -> None:
    task_dir = repo_root / "benchmarks" / "OperationsResearch" / task["slug"]
    write_text(task_dir / "README.md", README_TEMPLATE.format(**task))
    write_text(task_dir / "Task.md", TASK_TEMPLATE.format(**task))
    write_text(task_dir / "Task_zh-CN.md", TASK_ZH_TEMPLATE.format(**task))
    write_text(task_dir / "references" / "source_manifest.md", SOURCE_MANIFEST.format(**task))
    write_text(task_dir / "runtime" / "problem.py", RUNTIME_TEMPLATE.format(**task))
    write_text(task_dir / "runtime" / "instance.json", json.dumps(instance_payload, indent=2))
    if task["task_kind"] == "dispatch":
        write_text(task_dir / "scripts" / "init.py", INIT_DISPATCH.format(**task))
        write_text(task_dir / "baseline" / "solution.py", BASELINE_DISPATCH)
    else:
        write_text(task_dir / "scripts" / "init.py", INIT_MOVE.format(**task))
        write_text(task_dir / "baseline" / "solution.py", BASELINE_MOVE)
    write_text(task_dir / "verification" / "evaluator.py", EVALUATOR_TEMPLATE.format(**task))
    write_text(task_dir / "verification" / "requirements.txt", "ortools\n")

    write_text(task_dir / "frontier_eval" / "initial_program.txt", "scripts/init.py\n")
    write_text(task_dir / "frontier_eval" / "candidate_destination.txt", "scripts/init.py\n")
    write_text(task_dir / "frontier_eval" / "eval_command.txt", "{python} verification/evaluator.py {candidate} --metrics-out metrics.json\n")
    write_text(task_dir / "frontier_eval" / "eval_cwd.txt", ".\n")
    write_text(task_dir / "frontier_eval" / "agent_files.txt", "Task.md\nTask_zh-CN.md\nREADME.md\nbaseline/solution.py\nruntime/problem.py\nreferences/source_manifest.md\n")
    write_text(task_dir / "frontier_eval" / "readonly_files.txt", "runtime/problem.py\nruntime/instance.json\nverification/evaluator.py\nbaseline/solution.py\nreferences/source_manifest.md\n")
    write_text(task_dir / "frontier_eval" / "constraints.txt", CONSTRAINTS)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    instances = load_instances()
    for task in TASKS:
        instance_name = task["instance_name"]
        bootstrap_task(repo_root, task, instances[instance_name])
        print(f"bootstrapped OperationsResearch/{task['slug']}")


if __name__ == "__main__":
    main()
