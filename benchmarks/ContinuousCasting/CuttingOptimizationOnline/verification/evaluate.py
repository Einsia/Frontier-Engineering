"""在线切割评测入口（闭环 per-decision 驱动）。

每个实例：评测器在时间线上推进，每到一个切割决策点就：
  1) 用 simulator._make_state 构造"agent 可见状态"（只含已揭示异常，不含 future/hidden）；
  2) 把状态写入临时文件，`subprocess` 调用 `python <agent.py> <state.json>`；
  3) 解析 {"piece_length": L} 作为下一刀长度，落账推进。
直到整根材料切完；最后用完整 defects 表打分（污染/干净规则）。

评分 = 各实例材料利用率均值（0~100，越高越好）。
防作弊/确定性/运行时生成 对齐离线版（见 validator.py）。

环境变量：
    ONLINE_CUT_EVAL_GENERATE_SEED  设置后开启运行时生成实例（防硬编码）
    ONLINE_CUT_EVAL_GENERATE_COUNT 生成实例数（默认 8）

对外接口（供 frontier_eval/evaluator.py 包装）：
    evaluate(program_path, *, time_budget=60.0) -> {"combined_score", "valid", "per_instance"}
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from simulator import load_instance, partition, score  # noqa: E402
from validator import candidate_env, check_candidate  # noqa: E402

INVALID_SCORE = 0.0
DATA_DIR = Path(__file__).resolve().parent / "data" / "instances"
DEFAULT_GENERATE_COUNT = 8
GEN_DIFFS = ("easy", "medium", "hard", "medium", "hard", "medium", "hard", "hard")


def _source_benchmark_dir() -> Path | None:
    raw = os.environ.get("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", "").strip()
    if raw and Path(raw).is_dir():
        return Path(raw)
    return None


class AgentClient:
    """把 agent 子进程封装成 decision_fn(state)->length（每决策一次调用）。"""

    def __init__(self, program_path: Path, python: str, time_budget: float, tmp: Path):
        self.program_path = program_path
        self.python = python
        self.time_budget = time_budget
        self.tmp = tmp

    def decide(self, state: dict[str, Any]) -> float:
        state_path = self.tmp / f"state_{id(state)}.json"
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        try:
            proc = subprocess.run(
                [self.python, str(self.program_path), str(state_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=self.time_budget, cwd=str(self.program_path.parent),
                env=candidate_env(),
            )
        except subprocess.TimeoutExpired:
            return float("nan")
        if proc.returncode != 0:
            return float("nan")
        try:
            obj = json.loads(proc.stdout)
            return float(obj["piece_length"])
        except Exception:
            return float("nan")


def _load_host_module(mod_name: str):
    import importlib.util
    src = os.environ.get("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", "").strip()
    if src and Path(src).is_dir():
        p = Path(src) / "verification" / f"{mod_name}.py"
        if p.is_file():
            spec = importlib.util.spec_from_file_location(f"_oc_{mod_name}", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def _generate_instances(base_seed: int, count: int, out_dir: Path, reveal_lead: float) -> list[Path]:
    gen_mod = _load_host_module("generator") or __import__("generator")
    paths: list[Path] = []
    i = 0
    attempts = 0
    while len(paths) < count and attempts < count * 64:
        inst = gen_mod.generate(base_seed * 1000 + i, GEN_DIFFS[i % len(GEN_DIFFS)], reveal_lead)
        i += 1
        attempts += 1
        if not gen_mod._drivable(inst):
            continue
        p = out_dir / f"gen_{base_seed}_{len(paths) + 1}.json"
        p.write_text(json.dumps(inst, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(p)
    return paths


def check_determinism(python: str, prog: Path, inst_path: Path, time_budget: float,
                      work: Path, reveal_lead: float | None = None) -> tuple[bool, str]:
    """同一探针实例驱动两遍闭环，切段长度序列必须一致。"""
    inst = load_instance(inst_path)
    seqs: list[list[float]] = []
    for _ in range(2):
        client = AgentClient(prog, python, time_budget, work)
        seqs.append(partition(inst, client.decide))
    if seqs[0] != seqs[1]:
        return False, "agent is not deterministic across two closed-loop runs"
    return True, ""


def _run_one(prog: Path, inst_path: Path, time_budget: float, py: str, tmp: Path) -> tuple[float, Any]:
    inst = load_instance(inst_path)
    client = AgentClient(prog, py, time_budget, tmp)
    cuts = partition(inst, client.decide)
    ok, m = score(inst, cuts)
    if not ok:
        return 0.0, {"status": "invalid", "reason": m.get("reason")}
    return m["util"], {"status": "ok", "util": m["util"], "scrap": m["scrap"],
                       "n_cuts": len(cuts)}


def _instances_dir() -> Path:
    """在线版实例目录：只从宿主源 benchmark 目录加载（不复制进沙箱）。

    在线版的关键是"隐藏报废表"——实例文件含完整 defects/anomaly_seed，绝不能进候选可见
    目录（否则候选可读 JSON 拿到全知解作弊）。因此在沙箱内（本地无 data/instances 时）改从
    FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR 加载；直跑（非沙箱）时回退到本地目录。
    """
    src = os.environ.get("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", "").strip()
    if src:
        host = Path(src) / "verification" / "data" / "instances"
        if host.is_dir():
            return host
    return DATA_DIR


def evaluate(program_path: str, *, time_budget: float = 60.0, python: str | None = None,
             data_dir: str | Path | None = None, reveal_lead: float | None = None) -> dict[str, Any]:
    prog = Path(program_path).resolve()
    if not prog.exists():
        return {"combined_score": 0.0, "valid": 0.0, "per_instance": {}, "error": "program not found"}

    violations = check_candidate(prog)

    inst_dir = Path(data_dir).resolve() if data_dir else _instances_dir()
    instances = sorted(inst_dir.glob("instance_*.json")) if inst_dir.is_dir() else []
    if not instances:
        # 若无固定实例集，现场生成一批（便于直接评测；仅宿主，不进沙箱）
        tmp = Path(tempfile.mkdtemp(prefix="oc_inst_"))
        instances = _generate_instances(7, 6, tmp, reveal_lead or 10.0)

    gen_seed_raw = os.environ.get("ONLINE_CUT_EVAL_GENERATE_SEED", "").strip()
    tmp: Path | None = None
    if gen_seed_raw:
        base_seed = 0
        try:
            base_seed = int(gen_seed_raw)
        except ValueError:
            pass
        count = DEFAULT_GENERATE_COUNT
        try:
            count = max(0, int(os.environ.get("ONLINE_CUT_EVAL_GENERATE_COUNT", "").strip()))
        except ValueError:
            pass
        if count > 0:
            tmp = Path(tempfile.mkdtemp(prefix="oc_gen_"))
            instances = instances + _generate_instances(base_seed, count, tmp,
                                                        reveal_lead or 10.0)

    if not instances:
        return {"combined_score": 0.0, "valid": 0.0, "per_instance": {},
                "error": "no instances"}

    py = python or sys.executable

    # 确定性探针：在一个探针实例上跑两遍闭合，切段序列必须一致
    if not violations:
        probe = instances[0]
        work = Path(tempfile.mkdtemp(prefix="oc_probe_"))
        det_ok, det_note = check_determinism(py, prog, probe, time_budget, work)
        shutil.rmtree(work, ignore_errors=True)
        if not det_ok:
            violations = [f"determinism check failed: {det_note}"]

    per_instance: dict[str, Any] = {}
    total = 0.0
    all_valid = True
    work = Path(tempfile.mkdtemp(prefix="oc_run_"))
    try:
        for inst_path in instances:
            if violations:
                per_instance[inst_path.name] = {"status": "preflight_failed", "reasons": violations}
                continue
            util, info = _run_one(prog, inst_path, time_budget, py, work)
            per_instance[inst_path.name] = info
            if util <= 0 and info.get("status") != "ok":
                all_valid = False
            total += util
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)

    combined = total / len(instances) if instances else 0.0
    # 保留 3 位：贴合度惩罚量级 ~1e-3，2 位舍入会把破平项抹掉，故至少 3 位
    return {"combined_score": round(combined, 3), "valid": 1.0 if all_valid and not violations else 0.0,
            "per_instance": per_instance, "num_instances": len(instances),
            "time_budget_s": time_budget, "generate_seed": gen_seed_raw or None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="在线切割评测")
    parser.add_argument("solver")
    parser.add_argument("--time-budget", type=float, default=60.0)
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--reveal-lead", type=float, default=None,
                        help="覆盖实例的 reveal_lead 显式指定（便于多配置对比）")
    args = parser.parse_args(argv)
    result = evaluate(args.solver, time_budget=args.time_budget,
                      data_dir=args.data_dir, reveal_lead=args.reveal_lead)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
