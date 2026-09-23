"""TelecomBackup evaluation entry point.

CLI::

    python verification/evaluate.py <solver.py> [--local] [--generate-seed N]
        [--reference] [--time-budget S] [--data-dir DIR]

For every instance the candidate solver runs in a subprocess (timeout = the
per-instance budget); its stdout is parsed into on-intervals and handed to the
simulator, which returns the backup time. Malformed output / out-of-range
intervals / crash / timeout score 0 for that instance. Score = mean backup time
(minutes) over all scored instances.

Evaluation modes
----------------
``local`` (default; development and smoke tests)
    Scores the committed fixed instances in ``verification/data/instances``.
    Setting ``TELECOM_EVAL_GENERATE_SEED`` additionally scores fresh instances.

``official`` (``TELECOM_EVAL_MODE=official``; set by ``frontier_eval/eval_command.txt``)
    Scores **only** freshly generated instances -- the committed fixed instances
    are never part of the official score, so a candidate cannot memorise them.
    A generation seed is mandatory: if it is missing the evaluator raises
    ``OfficialModeConfigError`` instead of silently falling back to the public
    instances (the reviewer-reported hardcoding hole).

Integrity / anti-cheating (mirrors the CVRP benchmark)
  * static candidate checks (EVOLVE-BLOCK markers + fixed-region byte diff,
    forbidden imports, absolute paths, per-instance hardcoding) -- validator.py;
  * candidate subprocess environment strips ``FRONTIER_*`` / ``TELECOM_EVAL_*``
    (``candidate_env``), closing the host-env side channel;
  * runtime-generated instances (written to a temp dir, never to the repo or the
    sandbox), so a candidate cannot pre-position solutions for them;
  * determinism probe: cross-size instances are each run twice and must agree.
  * ``--reference`` deliberately bypasses the candidate checks so the bundled
    reference solver can be scored; it exists only to reproduce the documented
    reference score and must not be used to score candidates.

Time budget
-----------
The per-instance budget defaults to 60 s. When the unified framework drives the
evaluation it exports ``FRONTIER_EVAL_EVALUATOR_TIMEOUT_S`` (its whole-evaluation
wall-clock cap); the evaluator then shrinks the per-instance budget if needed so
the run cannot be killed by that cap, and records ``budget_shrunk`` / the
effective budget in its result. The official path should raise the cap (see the
README) so the full per-instance budget is available.

Environment variables
    TELECOM_EVAL_MODE            "official" | "local" (default "local")
    TELECOM_EVAL_GENERATE_SEED   generation seed (mandatory in official mode)
    TELECOM_EVAL_GENERATE_COUNT  number of generated instances (default 8)
    TELECOM_EVAL_REFERENCE       non-empty/"1" to bypass candidate checks
    FRONTIER_EVAL_EVALUATOR_TIMEOUT_S  framework-level wall-clock budget (seconds)

Interface used by ``frontier_eval/evaluator.py``::

    evaluate(program_path, *, time_budget=60.0) -> {"combined_score": float,
            "valid": float, "per_instance": {...}, ...}
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# 保证无论从哪个 cwd/以何种方式加载，都能 import 到同目录的模块
sys.path.insert(0, str(Path(__file__).resolve().parent))

from simulator import simulate, load_instance  # noqa: E402
from validator import candidate_env, check_candidate, check_determinism  # noqa: E402

INVALID_SCORE = 0.0
DATA_DIR = Path(__file__).resolve().parent / "data" / "instances"
DEFAULT_GENERATE_COUNT = 8
# 运行时生成实例的规模循环（与 generator 默认一致）
GEN_SIZES = (20, 24, 28, 32, 36, 40)
# 框架整体超时未知时的保守默认（仅用于自限；不影响独立运行 CLI）
DEFAULT_FRAMEWORK_TIMEOUT_S = 300.0
# 预留给进程启动 / 框架开销、不计入每实例预算的时间（秒）
BUDGET_RESERVE_S = 30.0

MODES = ("official", "local")


class OfficialModeConfigError(RuntimeError):
    """official 模式缺少必需配置（如生成种子）时抛出，绝不静默回退到公开实例。"""


def _source_benchmark_dir() -> Path | None:
    """宿主基准目录（unified 沙箱通过该环境变量暴露），用于读取初始 baseline 做比对。"""
    raw = os.environ.get("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", "").strip()
    if raw:
        path = Path(raw)
        if path.is_dir():
            return path
    return None


def _resolve_mode(explicit: str | None = None) -> str:
    raw = (explicit if explicit is not None else os.environ.get("TELECOM_EVAL_MODE", "")).strip().lower()
    if not raw:
        return "local"
    if raw not in MODES:
        raise OfficialModeConfigError(
            f"TELECOM_EVAL_MODE must be one of {MODES}, got {raw!r}"
        )
    return raw


def _reference_mode(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    return os.environ.get("TELECOM_EVAL_REFERENCE", "").strip() not in ("", "0", "false", "False")


def _generate_seed() -> int | None:
    raw = os.environ.get("TELECOM_EVAL_GENERATE_SEED", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise OfficialModeConfigError(
            f"TELECOM_EVAL_GENERATE_SEED must be an integer, got {raw!r}"
        ) from exc


def _generate_count() -> int:
    raw = os.environ.get("TELECOM_EVAL_GENERATE_COUNT", "").strip()
    if not raw:
        return DEFAULT_GENERATE_COUNT
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_GENERATE_COUNT


def _framework_timeout_s() -> float | None:
    """框架整体超时（仅当框架显式设置该变量时返回，独立运行 CLI 时为 None）。"""
    raw = os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _fit_budget(requested: float, n_runs: int) -> tuple[float, bool, float | None]:
    """按框架整体超时收缩每实例预算，保证评测总时长不超过观测到的框架上限。

    仅在框架显式设置 ``FRONTIER_EVAL_EVALUATOR_TIMEOUT_S`` 时收缩（独立 CLI 不受影响）。
    返回 (有效预算, 是否收缩, 框架超时)。不设下限：``n_runs * budget`` 恒 ≤ 上限，
    因此合规求解器即使跑满预算也不会被框架硬杀（超过上限会被判 -1e18，比低分更糟）。
    """
    timeout = _framework_timeout_s()
    if timeout is None or n_runs <= 0:
        return requested, False, timeout
    available = timeout - BUDGET_RESERVE_S
    if available <= 0:
        # 上限比固定开销还小：用上限的一半均摊，仍然不越过该上限。
        available = timeout / 2.0
    fit = available / n_runs
    if fit < requested:
        return fit, True, timeout
    return requested, False, timeout


def _parse_on_intervals(raw: str, k: int, horizon: int) -> list[list[list[int]]] | None:
    """解析候选 stdout 为 on_intervals；非法返回 None。

    格式：{"on": [[[a,b),...], ...]}，on[k] 为电源 k 的开启区间（半开 [a,b)）。
    """
    try:
        text = raw.strip()
        if not text:
            return None
        obj = json.loads(text)
        if isinstance(obj, dict):
            obj = obj.get("on")
        if not isinstance(obj, list) or len(obj) != k:
            return None
        out: list[list[list[int]]] = []
        for ivs in obj:
            if not isinstance(ivs, list):
                return None
            cur: list[list[int]] = []
            for iv in ivs:
                if not isinstance(iv, list) or len(iv) != 2:
                    return None
                a, b = iv
                if isinstance(a, bool) or isinstance(b, bool):
                    return None
                if not isinstance(a, int) or not isinstance(b, int):
                    return None
                if a < 0 or b > horizon or a > b:
                    return None
                cur.append([a, b])
            out.append(cur)
        return out
    except Exception:
        return None


def _run_one(program_path: Path, inst_path: Path, time_budget: float,
             python: str) -> tuple[float, dict[str, Any]]:
    inst = load_instance(inst_path)
    k = len(inst["groups"])
    horizon = int(inst["horizon"])
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
        on = _parse_on_intervals(proc.stdout, k, horizon)
        if on is None:
            return 0.0, {"status": "bad_output", "stdout_tail": proc.stdout[-500:]}
        minutes = simulate(inst, on)
        return minutes, {"status": "ok", "on": on, "minutes": round(minutes, 1),
                         "elapsed_s": round(elapsed, 2)}
    except subprocess.TimeoutExpired:
        return 0.0, {"status": "timeout", "budget_s": round(time_budget, 2)}
    except Exception as exc:
        return 0.0, {"status": "error", "message": str(exc)}


def _load_host_module(mod_name: str):
    """从宿主 benchmark 目录加载 `verification/<mod>.py`（沙箱内不含该模块时）。

    沙箱内不复制 generator.py（候选不可见）；评测器需要生成器时经
    FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR 从宿主加载（CVRP 同款模式）。
    """
    import importlib.util

    src = os.environ.get("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", "").strip()
    if src and Path(src).is_dir():
        path = Path(src) / "verification" / f"{mod_name}.py"
        if path.is_file():
            spec = importlib.util.spec_from_file_location(f"_tb_{mod_name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def _generate_instances(base_seed: int, count: int, out_dir: Path) -> list[Path]:
    """按种子现场生成新实例（防硬编码）。派生种子 base_seed*1000+i，可复现。

    生成器从宿主加载；生成实例逐个过 `_stagger_ok`（错峰 ≥ 全程开启 25%），
    不合格跳过——保证生成实例同样奖励调度（与固定实例的验收一致）。
    """
    gen_mod = _load_host_module("generator")
    if gen_mod is None:
        try:
            import generator as gen_mod  # 直跑（非沙箱）时的本地回退
        except ImportError as exc:
            raise OfficialModeConfigError(
                "runtime instance generation requires verification/generator.py "
                "(loaded from the host benchmark dir via "
                "FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR, or importable locally); "
                "it is intentionally not copied into the sandbox"
            ) from exc

    paths: list[Path] = []
    i = 0
    attempts = 0
    while len(paths) < count and attempts < count * 64:
        inst = gen_mod.generate(base_seed * 1000 + i, GEN_SIZES[i % len(GEN_SIZES)])
        i += 1
        attempts += 1
        if not gen_mod._stagger_ok(inst):
            continue
        path = out_dir / f"gen_{base_seed}_{len(paths) + 1}.json"
        path.write_text(json.dumps(inst, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _select_probes(instances: list[Path], n: int = 3) -> list[Path]:
    """跨规模选确定性探针：按排序取 小/中/大 各一（外加一个生成实例，若有）。

    去重：official 模式下实例本身全是生成实例，`gen[0]` 可能已在探针里，不重复添加。
    """
    if len(instances) <= n:
        return list(instances)
    idxs = sorted({0, len(instances) // 2, len(instances) - 1})
    probes = [instances[i] for i in idxs]
    gen = [p for p in instances if p.name.startswith("gen_")]
    if gen and gen[0] not in probes:
        probes.append(gen[0])
    return probes


def evaluate(program_path: str, *, time_budget: float = 60.0,
             data_dir: str | Path | None = None,
             python: str | None = None,
             mode: str | None = None,
             reference: bool | None = None) -> dict[str, Any]:
    """评测候选求解器：返回 metrics 字典。

    official 模式缺少生成种子时抛 ``OfficialModeConfigError``（不静默回退）。
    """
    resolved_mode = _resolve_mode(mode)
    is_reference = _reference_mode(reference)

    prog = Path(program_path).resolve()
    if not prog.exists():
        return {"combined_score": 0.0, "valid": 0.0, "per_instance": {},
                "mode": resolved_mode, "error": f"program not found: {prog}"}

    gen_seed = _generate_seed()
    gen_count = _generate_count()

    # official 模式：必须要有生成种子；缺失即显式失败，绝不回退到公开固定实例。
    if resolved_mode == "official" and gen_seed is None:
        raise OfficialModeConfigError(
            "official mode requires TELECOM_EVAL_GENERATE_SEED to be set "
            "(the official score must be computed on freshly generated instances, "
            "never on the committed public instances). Set the variable to a "
            "non-public seed, or use `--local` for development scoring."
        )
    if resolved_mode == "official" and gen_count <= 0:
        raise OfficialModeConfigError(
            "official mode requires TELECOM_EVAL_GENERATE_COUNT > 0, got "
            f"{gen_count!r}"
        )

    # 静态完整性检查（EVOLVE-BLOCK 标记/只读区比对、禁引用、禁绝对路径、禁硬编码）。
    # --reference 有意跳过：仅供复现内置参考求解器的分数。
    violations: list[str] = []
    if not is_reference:
        baseline_path = None
        src_dir = _source_benchmark_dir()
        if src_dir is not None:
            candidate_baseline = src_dir / "baseline" / "solver.py"
            if candidate_baseline.is_file():
                baseline_path = candidate_baseline
        violations = check_candidate(prog, baseline_path=baseline_path)

    # 实例池：
    #   official -> 仅运行时生成（不含公开固定实例）
    #   local    -> 固定实例（存在时）+ 可选运行时生成
    n_fixed = 0
    instances: list[Path] = []
    generating = gen_seed is not None and gen_count > 0
    tmp_dir: Path | None = (
        Path(tempfile.mkdtemp(prefix="telecom_eval_"))
        if (resolved_mode == "official" or generating)
        else None
    )
    if resolved_mode == "official":
        # official 模式必须有种子与正数生成量（上面已校验），此处 tmp_dir 必非空
        instances = _generate_instances(int(gen_seed), gen_count, tmp_dir)
    else:
        inst_dir = Path(data_dir).resolve() if data_dir else DATA_DIR
        if inst_dir.is_dir():
            fixed = sorted(inst_dir.glob("instance_*.json"))
            n_fixed = len(fixed)
            instances = list(fixed)
        if generating and tmp_dir is not None:
            instances.extend(_generate_instances(gen_seed, gen_count, tmp_dir))

    if not instances:
        return {"combined_score": 0.0, "valid": 0.0, "per_instance": {},
                "mode": resolved_mode, "generate_seed": gen_seed,
                "num_instances": 0,
                "error": f"no instances (mode={resolved_mode}, generate_seed={gen_seed!r})"}

    py = python or sys.executable

    # 每实例预算：按框架整体超时自限，保证合规求解器用满预算也不会被框架硬杀。
    probes = [] if is_reference else _select_probes(instances)
    n_runs = len(instances) + 2 * len(probes)
    eff_budget, shrunk, fw_timeout = _fit_budget(time_budget, n_runs)

    # 确定性探针：跨规模选若干实例（小/中/大 + 一个生成实例，若有）各跑两次，
    # 输出必须一致（候选不能只在最小实例上确定）。
    if not violations and not is_reference:
        for probe in probes:
            det_ok, det_note = check_determinism(py, prog, probe, eff_budget)
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
        minutes, info = _run_one(prog, inst_path, eff_budget, py)
        per_instance[inst_path.name] = info
        if minutes <= 0 and info.get("status") != "ok":
            all_valid = False
        total += minutes

    score = total / len(instances) if instances else 0.0
    return {
        "combined_score": round(score, 2),
        "valid": 1.0 if all_valid and not violations else 0.0,
        "per_instance": per_instance,
        "mode": resolved_mode,
        "official": resolved_mode == "official",
        "reference": is_reference,
        "preflight_bypassed": is_reference,
        "num_instances": len(instances),
        "num_fixed_instances": n_fixed,
        "num_generated_instances": len(instances) - n_fixed,
        "time_budget_s": time_budget,
        "effective_time_budget_s": round(eff_budget, 2) if shrunk else time_budget,
        "budget_shrunk": shrunk,
        "framework_timeout_s": fw_timeout,
        "generate_seed": gen_seed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="区域备电评测")
    parser.add_argument("solver", help="候选求解器脚本路径")
    parser.add_argument("--time-budget", type=float, default=60.0,
                        help="求解时间预算（秒），默认 60")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="实例目录（默认 verification/data/instances）")
    parser.add_argument("--generate-seed", type=int, default=None,
                        help="运行时生成实例的种子（防硬编码；等价于设 TELECOM_EVAL_GENERATE_SEED）")
    parser.add_argument("--mode", choices=MODES, default=None,
                        help="official：仅用运行时生成实例（需 --generate-seed/环境变量）；"
                             "local（默认）：用固定实例")
    parser.add_argument("--local", dest="mode", action="store_const", const="local",
                        help="等价于 --mode local（开发/冒烟测试）")
    parser.add_argument("--reference", action="store_true",
                        help="跳过候选完整性检查，用于复现内置参考求解器的分数")
    args = parser.parse_args(argv)

    if args.generate_seed is not None:
        os.environ["TELECOM_EVAL_GENERATE_SEED"] = str(args.generate_seed)
    try:
        result = evaluate(args.solver, time_budget=args.time_budget, data_dir=args.data_dir,
                          mode=args.mode, reference=args.reference)
    except OfficialModeConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
