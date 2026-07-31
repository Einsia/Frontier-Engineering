from __future__ import annotations

import json
import sys
from typing import Any


# EVOLVE-BLOCK-START
def solve(instance):
    queries = list(instance['queries'])
    allocations = {q['id']: float(q['epsilon_min']) for q in queries}
    remaining = float(instance['epsilon_total']) - sum(allocations.values())
    if remaining <= 0:
        return {'allocations': allocations}

    def error(q, eps):
        return float(q['sensitivity']) / float(eps)

    def group_averages():
        totals = {}
        counts = {}
        for q in queries:
            group = q['group']
            totals[group] = totals.get(group, 0.0) + error(q, allocations[q['id']])
            counts[group] = counts.get(group, 0) + 1
        return {group: totals[group] / counts[group] for group in totals}

    def fairness_ok():
        averages = list(group_averages().values())
        if not averages:
            return True
        smallest = min(averages)
        if smallest <= 0.0:
            return False
        return max(averages) / smallest <= float(instance['fairness']['max_group_error_ratio']) + 1e-09
    while remaining > 1e-12 and (not fairness_ok()):
        averages = group_averages()
        worst_group = max(averages, key=averages.get)
        candidates = []
        for q in queries:
            qid = q['id']
            if q['group'] != worst_group:
                continue
            cap = float(q['epsilon_max']) - allocations[qid]
            if cap > 1e-12:
                reduction = float(q['sensitivity']) / (allocations[qid] * allocations[qid])
                candidates.append((reduction, qid, cap))
        if not candidates:
            break
        _reduction, qid, cap = max(candidates)
        add = min(0.01, remaining, cap)
        allocations[qid] += add
        remaining -= add
    remaining = min(remaining, 0.25 * float(instance['epsilon_total']))
    rounds = 0
    while remaining > 1e-12 and rounds < 10000:
        used = 0.0
        for q in sorted(queries, key=lambda x: x['id']):
            qid = q['id']
            cap = float(q['epsilon_max']) - allocations[qid]
            if cap <= 1e-12:
                continue
            add = min(0.02, cap, remaining)
            allocations[qid] += add
            if fairness_ok():
                remaining -= add
                used += add
            else:
                allocations[qid] -= add
            if remaining <= 1e-12:
                break
        if used <= 1e-12:
            break
        rounds += 1
    return {'allocations': allocations}
# EVOLVE-BLOCK-END


def main() -> int:
    try:
        instance = json.load(sys.stdin)
        if not isinstance(instance, dict):
            raise TypeError("input must be a JSON object")
        solution = solve(instance)
        if not isinstance(solution, dict):
            raise TypeError("solve() must return a JSON object")
        json.dump(solution, sys.stdout, allow_nan=False, separators=(",", ":"))
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        print(f"candidate error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
