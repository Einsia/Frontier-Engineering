# Cache Replacement Policy Optimization (real Meta kvcache trace)

## Background

Production key-value caches (memcached/Meta kvcache-style, managed by CacheLib)
are capacity-bound: the DRAM budget is fixed, the key population is far larger
than the cache, and every object that is not resident costs a backend lookup.
CacheLib's own benchmark tool, **CacheBench**, is built around exactly this
question — its documentation describes its first use case as

> "Prototype and evaluation of cache heuristics: CacheBench can be used to
> compare the cache performance (**hit ratio**) of various configuration options
> for existing heuristics and new heuristics. For example, given a cache size
> and workload, comparing LRU vs 2Q vs FIFO vs new heuristic added to
> CacheLib."

This task is that experiment: the same real trace, the same cache capacity, the
same request order — only the **eviction policy** changes.

## Engineering Value

At Meta's cache scale a few points of hit ratio translate into a
proportional cut in backend QPS, network traffic and tail latency, without any
extra DRAM. Replacement policy is the classic place where that gain is won:
SIEVE (NSDI'24), S3-FIFO (SOSP'23), ARC (FAST'03) and 2Q are all published
eviction policies whose entire claim is a lower miss ratio than LRU on real
production traces at a fixed cache size. A service that moves from LRU to a
better policy gets the improvement on every host it runs on.

## Objective

Given one candidate program (`policy.py`), implement an **online cache
replacement policy**: for a full-associativity cache of fixed capacity C, decide
which resident object to evict when a lookup misses and the cache is full.
Because every lookup on a missing object loads that object, the eviction
decision at each miss is what determines the hit rate.

Your policy is scored on **hit rate on a real production trace you never
receive** at a fixed capacity. You *do* get one real trace (see `README.md`) to
develop and measure against locally.

## Submission Contract

`policy.py` is the submission. Only the region between the EVOLVE-BLOCK markers
may be edited:

```python
class Policy:
    def __init__(self, capacity): ...
    def access(self, key):
        """Return the key to evict on this access, or None if nothing is evicted."""
```

**Runtime execution contract** (`FE-BATCH-JSON-STDIO-V1`): the frozen evaluator
runs

```
python policy.py <instance.json>      # stdin is CLOSED
```

and your program must print **exactly one JSON object on stdout** and exit 0:

```json
{"runs": [{"name": "<the run name>", "evictions": ["<key>", null, ...]}]}
```

* one entry per element of `instance["runs"]`, in that order, with the same
  `name`;
* `evictions[i]` is the key you evict at access `i` of that run, or `null` when
  nothing is evicted;
* a hit must never evict; a miss on a full cache must name one **resident** key;
* the evaluator does the replay itself and counts the hits — your program never
  reports hits or misses, so it cannot report a hit rate.

The instance carries `runs[i]["cache_size"]` (the fixed capacity) and
`runs[i]["keys"]` (the real request stream, in replay order).

## What is fixed (and checked)

* the workload, the cache capacity, the reference model, the evaluator, the
  baseline and `frontier_eval/constraints.txt` — all frozen;
* the graded trace is a *different* real trace of the same family, delivered to
  your program only as the `keys` list of the instance at run time;
* your policy must be **online**: the evaluator replays you again on the first
  half of the same run with the same capacity; an online policy makes exactly
  the same decisions, so reading ahead (an offline/Belady-style oracle) is
  detected and rejected;
* your hit rate may not exceed the offline optimum (Belady 1966), which is the
  literature's reference bound and is not reachable by a legal online policy.

## Scoring

`combined_score` is the **hit rate** on the held-out trace at the fixed
capacity: `hits / lookups`. No weights, no bonuses, no penalties. For reference
the same evaluator reports the frozen LRU baseline hit rate and the offline
optimum, and the evaluator's own reference replays are: LRU 0.2663, FIFO 0.2640,
LRU-2Q 0.2835, offline optimum 0.4325 at the graded capacity. The baseline
(LRU) is a legal, valid submission — beating it is where the score comes from.

Rejected submissions (protocol, legality, causality, or exceeding the optimum)
report `combined_score = -1e18`, the frozen "no score" sentinel.

## Evaluator output (the frozen reporting contract)

The evaluator prints exactly one JSON object on stdout and always exits 0:

```json
{"valid": <bool>, "combined_score": <float>, "metrics": {...}}
```

`valid` means "legal online policy, graded and reproducible" — it is not
"good": the quality is `combined_score`. A rejected submission also carries
`error`, and `combined_score` is `-1e18`. A fully graded submission reports
exactly these `metrics` keys — integer counts:

`capacity_objects`, `lookups`, `working_set_objects`, `hits`, `misses`,
`causality_probe_lookups`

and floats:

`capacity_fraction`, `baseline_hit_rate_lru`, `baseline_hit_rate_fifo`,
`baseline_hit_rate_lru_2q`, `offline_optimum_hit_rate`, `hit_rate`,
`miss_ratio`, `improvement_over_lru`, `fraction_of_offline_optimum`,
`candidate_runtime_seconds`, `causality_probe_runtime_seconds`

Only the last two are measured wall-clock timings; every other reported value
is a frozen constant or a deterministic function of the submission's decisions.
