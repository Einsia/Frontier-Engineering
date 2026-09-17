#!/usr/bin/env python3
# CANDIDATE-PROTOCOL: FE-BATCH-JSON-STDIO-V1
"""baseline/solution.py -- FROZEN baseline (do not edit).

CLI: python baseline/solution.py <instance.json>  (stdin is CLOSED)
prints exactly one JSON object: {"runs": [{"name":..., "evictions":[...]}]}

The baseline is CacheLib's default DRAM eviction policy, LRU
(`LruAllocator`). CacheBench's documented way to compare replacement
heuristics is exactly this: "given a cache size and workload, comparing LRU vs
2Q vs FIFO vs new heuristic added to CacheLib" (CacheLib CacheBench overview).
The evaluator replays this same baseline over the held-out workload; the
frozen hit counts are recorded in references/constants.json.

Only the standard library is used.
"""

import json
import sys
from collections import OrderedDict


class Lru:
    def __init__(self, capacity):
        self.capacity = int(capacity)
        self.resident = OrderedDict()

    def access(self, key):
        if key in self.resident:
            self.resident.move_to_end(key)
            return None
        if len(self.resident) < self.capacity:
            self.resident[key] = True
            return None
        victim, _ = self.resident.popitem(last=False)
        self.resident[key] = True
        return victim


def solve(instance):
    runs = []
    for run in instance["runs"]:
        policy = Lru(run["cache_size"])
        runs.append({
            "name": run["name"],
            "evictions": [policy.access(key) for key in run["keys"]],
        })
    return {"runs": runs}


def main():
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        instance = json.load(handle)
    print(json.dumps(solve(instance)))


if __name__ == "__main__":
    main()
