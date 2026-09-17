"""多运行（多种子/多轮）agent 分数统计：对一组框架运行目录取 combined_score 的 mean±std。

用法：
    python verification/multiseed_stat.py --runs-dir runs/unified__ContinuousCasting__CuttingOptimization/openevolve
    python verification/multiseed_stat.py --runs-dir "runs/**/openevolve/deepseek-v4-flash"   # glob
    python verification/multiseed_stat.py --runs-dir <dir> --pattern "*openevolve*"

从每个运行目录下读 `<framework>/best/best_program_info.json` 的 `metrics.combined_score`
（框架统一保存的 best 程序分数），对多次运行做 mean / std / min / max，
并给出"相对 reference 的余量"（gap = reference_util - mean）。

对齐 CVRP 评审点：agent 分数需多轮均值±std（而非单次），衡量稳定性与真实水平。
纯标准库。
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import statistics
from pathlib import Path

DEFAULT_REFERENCE = 88.72  # 全知参考解利用率（verification/ref_solver.py），可 --reference 覆盖


def _best_score(run_dir: Path) -> float | None:
    for rel in ("openevolve/best/best_program_info.json",
                "shinkaevolve/best/best_program_info.json",
                "abmcts/best/best_program_info.json",
                "best/best_program_info.json"):
        p = run_dir / rel
        if p.is_file():
            try:
                return float(json.loads(p.read_text(encoding="utf-8"))["metrics"]["combined_score"])
            except Exception:
                return None
    return None


def collect(runs_dir: str | Path, pattern: str | None = None) -> list[tuple[Path, float]]:
    base = Path(runs_dir)
    if pattern:
        bests = sorted(Path(p) for p in glob.glob(str(base / pattern), recursive=True))
    else:
        bests = sorted(base.rglob("best/best_program_info.json"))
    out: list[tuple[Path, float]] = []
    seen: set[Path] = set()
    for best in bests:
        # best_program_info.json 位于 <run>/<framework>/best/ 下
        run_dir = best.parent.parent.parent
        if run_dir in seen:
            continue
        score = _best_score(run_dir)
        if score is not None:
            out.append((run_dir, score))
            seen.add(run_dir)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="多运行 agent 分数统计")
    parser.add_argument("--runs-dir", required=True, help="运行目录或 glob 模式")
    parser.add_argument("--pattern", default=None, help="追加的子 glob 模式")
    parser.add_argument("--reference", type=float, default=DEFAULT_REFERENCE,
                        help="参考解利用率（默认 88.72）")
    args = parser.parse_args()

    pairs = collect(args.runs_dir, args.pattern)
    if not pairs:
        print("no runs found under", args.runs_dir)
        return 1

    scores = [s for _, s in pairs]
    mean = statistics.mean(scores)
    std = statistics.stdev(scores) if len(scores) > 1 else 0.0
    print(f"runs: {len(scores)}")
    for run_dir, s in pairs:
        print(f"  {run_dir.name}: {s}")
    print(f"mean={mean:.2f}  std={std:.2f}  min={min(scores):.2f}  max={max(scores):.2f}")
    print(f"gap to reference ({args.reference}): {args.reference - mean:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
