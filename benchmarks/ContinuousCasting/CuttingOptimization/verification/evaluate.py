"""连铸切割评测入口。

CLI：python verification/evaluate.py <solver.py> [--time-budget 60] [--data-dir ...]
对每个实例：subprocess 运行候选求解器（超时 = 时间预算），解析输出 cuts，调 simulator 校验打分；
超时/格式错/越界 -> 该实例 0 分。
分数 = 各实例"材料利用率"的平均值（0~100，越高越好）。

利用率 = 100 * (S - (scrap + lambda*penalty)) / S。废弃物越少、成品越贴合目标值，利用率越高；
它等价于"先最小化报废、再最小化贴合度惩罚"，符合赛题的字典序目标，且越高越好、跨实例可比。

完整性 / 防作弊（对齐 CVRP / TelecomBackup 基准的经验）：
  * 评分前静态检查候选（EVOLVE-BLOCK 标记与标记外代码、禁引用评测/生成/参考解模块、
    禁绝对路径、禁按实例名硬编码）——见 verification/validator.py；
  * 候选子进程环境剥离 FRONTIER_*/CUTTING_EVAL_*（candidate_env），封侧信道；
  * 运行时生成实例（CUTTING_EVAL_GENERATE_SEED 设置时，评测现场按种子生成新实例，
    候选无法预先记忆；生成的实例只存在于临时目录，不落仓库/沙箱）。
  * 确定性探针：跨规模选若干实例（小/中/大 + 一个生成实例）各跑两次，输出必须一致。

环境变量：
    CUTTING_EVAL_GENERATE_SEED  设置后开启运行时生成（防硬编码）
    CUTTING_EVAL_GENERATE_COUNT 生成实例数（默认 8）

对外接口（供 frontier_eval/evaluator.py 包装）：
    evaluate(program_path, *, time_budget=60.0) -> {"combined_score": float,
            "valid": float, "per_instance": {...}}
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from simulator import load_instance, score  # noqa: E402
from validator import candidate_env, check_candidate, check_determinism  # noqa: E402

INVALID_SCORE = 0.0
DATA_DIR = Path(__file__).resolve().parent / "data" / "instances"
DEFAULT_GENERATE_COUNT = 8
# 运行时生成实例的难度循环（与 generator 默认一致）
GEN_DIFFS = ("easy", "medium", "hard", "medium", "hard", "medium", "hard", "hard")


def _source_benchmark_dir() -> Path | None:
    raw = os.environ.get("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", "").strip()
    if raw:
        path = Path(raw)
        if path.is_dir():
            return path
    return None


def _parse_cuts(raw: str) -> list[float] | None:
    """解析候选 stdout 为 cuts 列表；非法返回 None。

    格式：{"cuts": [c1, c2, ...]}
    """
    try:
        text = raw.strip()
        if not text:
            return None
        obj = json.loads(text)
        if isinstance(obj, dict):
            obj = obj.get("cuts")
        if not isinstance(obj, list) or not obj:
            return None
        out: list[float] = []
        for c in obj:
            if isinstance(c, bool) or not isinstance(c, (int, float)):
                return None
            if math.isnan(c) or math.isinf(c):
                return None
            out.append(float(c))
        return out
    except Exception:
        return None


def _utilization(inst: dict[str, Any], cuts: list[float]) -> float:
    """给定切段方案 -> 材料利用率（0~100，越高越好）。无效则 0。"""
    ok, m = score(inst, cuts)
    if not ok:
        return 0.0
    S = float(inst["billet"]["total_length"])
    return max(0.0, 100.0 * (S - m["score"]) / S)


def _run_one(program_path: Path, inst_path: Path, time_budget: float,
             python: str) -> tuple[float, dict[str, Any]]:
    inst = load_instance(inst_path)
    started = time.time()
    try:
        proc = subprocess.run(
            [python, str(program_path), str(inst_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=time_budget,
            cwd=str(program_path.parent),
            env=candidate_env(),
        )
        elapsed = time.time() - started
        if proc.returncode != 0:
            return 0.0, {"status": "crash", "stderr_tail": proc.stderr[-500:]}
        cuts = _parse_cuts(proc.stdout)
        if cuts is None:
            return 0.0, {"status": "bad_output", "stdout_tail": proc.stdout[-500:]}
        util = _utilization(inst, cuts)
        return util, {"status": "ok", "cuts": cuts, "utilization": round(util, 2),
                      "elapsed_s": round(elapsed, 2)}
    except subprocess.TimeoutExpired:
        return 0.0, {"status": "timeout", "budget_s": time_budget}
    except Exception as exc:
        return 0.0, {"status": "error", "message": str(exc)}


def _load_host_module(mod_name: str):
    """从宿主 benchmark 目录加载 `verification/<mod>.py`（沙箱内不含该模块时）。"""
    import importlib.util

    src = os.environ.get("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", "").strip()
    if src and Path(src).is_dir():
        path = Path(src) / "verification" / f"{mod_name}.py"
        if path.is_file():
            spec = importlib.util.spec_from_file_location(f"_cc_{mod_name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def _generate_instances(base_seed: int, count: int, out_dir: Path) -> list[Path]:
    """按种子现场生成新实例（防硬编码）。派生种子 base_seed*1000+i，可复现。"""
    gen_mod = _load_host_module("generator")
    if gen_mod is None:
        import generator as gen_mod  # 直跑（非沙箱）时的本地回退

    paths: list[Path] = []
    i = 0
    attempts = 0
    while len(paths) < count and attempts < count * 64:
        inst = gen_mod.generate(base_seed * 1000 + i, GEN_DIFFS[i % len(GEN_DIFFS)])
        i += 1
        attempts += 1
        if not gen_mod._interesting_ok(inst):
            continue
        path = out_dir / f"gen_{base_seed}_{len(paths) + 1}.json"
        path.write_text(json.dumps(inst, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _select_probes(instances: list[Path], n: int = 3) -> list[Path]:
    """跨规模选确定性探针：按排序取 小/中/大 各一（外加一个生成实例，若有）。"""
    if len(instances) <= n:
        return list(instances)
    idxs = sorted({0, len(instances) // 2, len(instances) - 1})
    probes = [instances[i] for i in idxs]
    gen = [p for p in instances if p.name.startswith("gen_")]
    if gen:
        probes.append(gen[0])
    return probes


def evaluate(program_path: str, *, time_budget: float = 60.0,
             data_dir: str | Path | None = None,
             python: str | None = None) -> dict[str, Any]:
    prog = Path(program_path).resolve()
    if not prog.exists():
        return {"combined_score": 0.0, "valid": 0.0, "per_instance": {},
                "error": f"program not found: {prog}"}

    # 静态完整性检查（EVOLVE-BLOCK 标记/只读区比对、禁引用、禁绝对路径、禁硬编码）
    baseline_path = None
    src_dir = _source_benchmark_dir()
    if src_dir is not None:
        candidate_baseline = src_dir / "baseline" / "solver.py"
        if candidate_baseline.is_file():
            baseline_path = candidate_baseline
    violations = check_candidate(prog, baseline_path=baseline_path)

    # 实例池 = 固定实例（本地 data-dir 存在时）+ 运行时生成（设了生成种子时）
    inst_dir = Path(data_dir).resolve() if data_dir else DATA_DIR
    instances: list[Path] = []
    if inst_dir.is_dir():
        instances = sorted(inst_dir.glob("instance_*.json"))

    gen_seed_raw = os.environ.get("CUTTING_EVAL_GENERATE_SEED", "").strip()
    tmp_dir: Path | None = None
    if gen_seed_raw:
        base_seed = 0
        try:
            base_seed = int(gen_seed_raw)
        except ValueError:
            pass
        gen_count = DEFAULT_GENERATE_COUNT
        try:
            gen_count = max(0, int(os.environ.get("CUTTING_EVAL_GENERATE_COUNT", "").strip()))
        except ValueError:
            pass
        if gen_count > 0:
            tmp_dir = Path(tempfile.mkdtemp(prefix="cutting_eval_"))
            instances.extend(_generate_instances(base_seed, gen_count, tmp_dir))

    if not instances:
        return {"combined_score": 0.0, "valid": 0.0, "per_instance": {},
                "error": f"no instances (data_dir={inst_dir}, generate_seed={gen_seed_raw!r})"}

    py = python or sys.executable

    # 确定性探针：跨规模选若干实例各跑两次，输出必须一致。
    if not violations:
        for probe in _select_probes(instances):
            det_ok, det_note = check_determinism(py, prog, probe, time_budget)
            if not det_ok:
                violations = [f"determinism check failed on {probe.name}: {det_note}"]
                break

    per_instance: dict[str, Any] = {}
    total = 0.0
    all_valid = True
    for inst_path in instances:
        if violations:
            per_instance[inst_path.name] = {"status": "preflight_failed",
                                            "reasons": violations}
            continue
        util, info = _run_one(prog, inst_path, time_budget, py)
        per_instance[inst_path.name] = info
        if util <= 0 and info.get("status") != "ok":
            all_valid = False
        total += util

    combined = total / len(instances) if instances else 0.0
    if tmp_dir is not None:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return {
        "combined_score": round(combined, 2),
        "valid": 1.0 if all_valid and not violations else 0.0,
        "per_instance": per_instance,
        "num_instances": len(instances),
        "time_budget_s": time_budget,
        "generate_seed": gen_seed_raw or None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="连铸切割评测")
    parser.add_argument("solver", help="候选求解器脚本路径")
    parser.add_argument("--time-budget", type=float, default=60.0,
                        help="求解时间预算（秒），默认 60")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="实例目录（默认 verification/data/instances）")
    parser.add_argument("--generate-seed", type=int, default=None,
                        help="运行时生成实例的种子（防硬编码；等价于设 CUTTING_EVAL_GENERATE_SEED）")
    args = parser.parse_args(argv)

    if args.generate_seed is not None:
        os.environ["CUTTING_EVAL_GENERATE_SEED"] = str(args.generate_seed)
    result = evaluate(args.solver, time_budget=args.time_budget, data_dir=args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
