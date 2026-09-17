# CANDIDATE-PROTOCOL: FE-BATCH-JSON-STDIO-V1
# Cache replacement policy submission (Python 3, standard library only).
# The evaluator runs: python policy.py <instance.json>   (stdin is CLOSED)
# Print EXACTLY ONE JSON object on stdout and exit 0, nothing else:
#   {"runs": [{"name": <str>, "evictions": [<key>|null, ...]}, ...]}
# evictions[i] = the key you evict on access i, or null when nothing is evicted.
# One victim per access, one run per entry of instance["runs"], in that order.
# Only the region between the EVOLVE-BLOCK markers below may be edited.
import json
import sys
from collections import OrderedDict


# EVOLVE-BLOCK-START
class Policy:
    """LRU - evict the least recently used resident key.

    This is CacheLib's default DRAM eviction policy (`LruAllocator`, see the
    CacheLib user guide: "Variety of caching algorithms like LRU, TinyLFU,
    LRU2Q with TTL support") and it is the baseline this task has to beat.
    """

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
# EVOLVE-BLOCK-END


def main():
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        instance = json.load(handle)
    out = []
    for run in instance["runs"]:
        policy = Policy(run["cache_size"])
        evictions = [policy.access(key) for key in run["keys"]]
        out.append({"name": run["name"], "evictions": evictions})
    print(json.dumps({"runs": out}))


if __name__ == "__main__":
    main()
