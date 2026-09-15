# Agent notes - cache replacement task

## The cache model (frozen)

* full associativity, unit-size objects, no admission control;
* the cache holds at most `cache_size` resident keys; the access stream is the
  instance's `keys` list, in order;
* a request whose key is resident is a **hit**; the accessed key is then the
  most recently used one, and nothing is evicted;
* a request whose key is **not** resident is a miss: the object is loaded (this
  is CacheBench's lookaside semantics, "follow get misses with a set",
  `cachelib/cachebench/util/Config.h:271`), and if the cache was already full
  exactly ONE resident key is evicted - the one your `access(key)` returns on
  that same call;
* the evaluator replays the stream with its own model and counts the hits. You
  only choose victims, so you cannot report a hit rate - and you cannot fake
  one: an eviction that is not a resident key, or an eviction on a hit, makes
  the whole run invalid.

## Protocol (`FE-BATCH-JSON-STDIO-V1`)

```
python policy.py <instance.json>       # stdin is CLOSED
```
`instance.json`:
```json
{"protocol": "FE-BATCH-JSON-STDIO-V1",
 "runs": [{"name": "graded", "cache_size": 417, "keys": ["k1", "k2", ...]}]}
```
stdout must be exactly one JSON object, one entry per run, in order:
```json
{"runs": [{"name": "graded", "evictions": ["k1", null, ...]}]}
```
`evictions[i]` = the key you evict at access `i` (or `null` if nothing is
evicted). Length must equal `len(keys)`.

## The trace you have

`traces/kvcache_202206_traces_1.csv` is a verbatim prefix of a real Meta kvcache
trace that CacheLib publishes for CacheBench:

* columns (CacheLib's own replay format, `KVReplayGenerator.h`: "Default order is
  key,op,size,op_count,key_size,ttl"): `key,op,size,op_count,key_size`;
* 44,379 rows -> 43,957 lookups, 21,143 distinct keys;
* `op_count` is CacheLib's repeat counter; this benchmark replays one row as one
  reference (`ignoreOpCount` semantics, see `docs/PROVENANCE.md`);
* `DELETE` rows are not part of the reference stream (the frozen protocol has no
  delete channel); their count is recorded in `references/constants.json`.

## Measuring locally

The graded capacity is 2% of the *graded* workload's distinct-object working
set. The same rule on the visible trace gives 422 objects
(`int(0.02 * 21143)`), which is the capacity you should develop against:

```python
import json, sys, pathlib
sys.path.insert(0, "verification"); import reference_cache as R
keys, stats = R.load_reference_stream("traces/kvcache_202206_traces_1.csv")
cap = int(0.02 * stats["distinct_keys"])           # 422
# your policy, replayed by the frozen model:
from policy import Policy
print(R.replay(Policy(cap), keys, cap)["hit_rate"])  # LRU baseline: 0.2642
```

Reference numbers on the *visible* trace at capacity 422 (frozen, reproducible):
LRU 0.2642, FIFO 0.2627, LRU-2Q 0.2786, offline optimum 0.4288. On the graded
trace the same policies score LRU 0.2663, LRU-2Q 0.2835, offline optimum 0.4325 -
so a policy that helps on the visible trace helps on the graded one, and the
gap to the offline optimum is where the score is.

## Rules the evaluator enforces

1. protocol shape (one object, one entry per run, one victim per access, exit 0);
2. legality (a hit never evicts; a miss must name one resident victim);
3. **online causality**: the same policy is replayed on the first half of the
   same run with the same capacity and must make exactly the same decisions, so
   a policy that reads ahead in `keys` is rejected;
4. hit rate <= offline optimum (Belady 1966), the literature's reference bound;
5. the workload file, the capacity and the reference baselines are checked
   against frozen values before and after your program runs.

Rejected submissions get `combined_score = -1e18`.
