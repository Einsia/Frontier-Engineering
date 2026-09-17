# PROVENANCE - CacheReplacementPolicyOptimization

Every number in this benchmark is derived from a real CacheLib artifact. This
document records the artifact, the exact statement it supports, and what was
*rejected* for lack of support. It is the "before/after" record for the Phase
11.46 revision: the previous LLM-designed scoring standard is documented in
`docs/phase11_46_cache_benchmark_scoring_provenance_audit.md` (executed
evaluator sha256 `e3269db7...c11`, iteration 5) and is NOT carried over.

Scope rule: no score component, weight, threshold or capacity is used unless an
external artifact defines it, or it is derived deterministically from one and
the derivation is written down here.

---

## 1. Primary evidence (opened and read, not inferred from search results)

| # | Artifact | What it establishes |
| --- | --- | --- |
| E1 | CacheBench overview - <https://cachelib.org/docs/Cache_Library_User_Guides/Cachebench_Overview/> | The evaluation paradigm. Verbatim: "Prototype and evaluation of cache heuristics: CacheBench can be used to compare the cache performance (**hit ratio**) of various configuration options for existing hueristics and new heuristics. For example, given a **cache size** and **workload**, comparing **LRU vs 2Q vs FIFO** vs new heuristic added to CacheLib." And: "The results include metrics such as **hit rate**, evictions, write rate to flash cache, latency, etc." |
| E2 | CacheBench parameter reference - <https://cachelib.org/docs/Cache_Library_User_Guides/Configuring_cachebench_parameters> | The configuration vocabulary used below: "You can set `cacheSizeMB` to specify the size of the DRAM cache." / "CacheLib supports LruAllocator and Lru2QAllocator to choose from. You can specify this by setting the allocator to "LRU" or "LRU-2Q"." / "**replay**: Replays a trace file passed in. Tracefile should contain lines with csv separated key, size, and number of accesses." / "To adjust the working set size of the cache, you can increase or decrease the numKeys that the workload picks from." |
| E3 | Meta's published workloads - <https://cachelib.org/docs/Cache_Library_User_Guides/Cachebench_FB_HW_eval/> | The real workloads and their recorded capacities: "Meta is sharing anonymized traces captured from large scale production cache services. These traces are licensed under the same license as CacheLib." - `kvcache/202206`: 5 consecutive days, 500 hosts, "Each host uses (roughly) 42 GB of DRAM and 930 GB of SSD for caching", traffic factor 1/100. It also defines **resource scaling** ("either the cache resource or the trace data needs to be scaled accordingly ... by modifying the `cache_config`"), which is the documented licence for running a reduced trace at a reduced capacity. |
| E4 | CacheLib source, `cachelib/cachebench/workload/KVReplayGenerator.h` | The trace format this benchmark parses: line 82 "Default order is key,op,size,op_count,key_size,ttl"; `GET`/`GET_LEASE` -> get, `SET`/`SET_LEASE` -> set, `DELETE` -> del; `op_count` -> `ReqWrapper::repeats_` (line ~355), with `if (config_.ignoreOpCount) req->repeats_ = 1;` (line 358). |
| E5 | CacheLib source, `cachelib/cachebench/util/Config.h` + `util/Config.cpp` | The two replay knobs this benchmark declares: line 271 `// follow get misses with a set` / `bool enableLookaside{false};`, lines 275-276 `// ignore opCount and does not repeat operations` / `bool ignoreOpCount{false};`, and `Config.cpp:61 JSONSetVal(configJson, ignoreOpCount);` (a real, JSON-settable CacheBench option). |
| E6 | The published CacheBench configuration for this trace family, `s3://cachelib-workload-sharing/pub/kvcache/202206/config_kvcache.json` (1374 bytes) | The real experiment this benchmark mirrors: `"cacheSizeMB": 43000`, `"nvmCacheSizeMB": 952320`, `"enableLookaside": false`, `"onlySetIfMiss": false`, `"repeatTraceReplay": true`, `"prepopulateCache": true`, `"ampFactor": 100`, `"traceFileNames": ["kvcache_traces_1.csv", ... "_5.csv"]`. |
| E7 | CacheLib's own in-repo trace-replay cases, `cachelib/cachebench/test_configs/trace_replay/{kvcache,block_chunk}/` | CacheLib itself ships `config_kvtrace.json` + `kv_traces_{1,2}.csv` (and the block-chunk analogue) with `"cacheSizeMB": 500`, `"generator": "replay"`, `"repeatOpCount": true`, `"numOps": 2000000` - i.e. "one fixed cache size, real trace files, compare policies" is the shape CacheLib uses to exercise this path. |
| E8 | libCacheSim README (CMU; the simulator behind the S3-FIFO/SIEVE evaluation scripts) | The capacity convention for a reduced trace: "Besides absolute cache size, you can also use a **fraction of the working set size**: `./bin/cachesim ../data/cloudPhysicsIO.vscsi vscsi lru 0.001,0.01,0.1,0.2`", and the MRC sweep `plot_mrc_size.py ... --sizes=0.001,0.002,0.005,0.01,0.02,0.05,0.1,0.2,0.3,0.4`. It also states: "the sample traces are **very small** and **should not be used for evaluating different algorithms' miss ratios**". |
| E9 | Belady 1966, *A study of replacement algorithms for a virtual-storage computer*, IBM Systems Journal 5(2):78-101; SIEVE (NSDI'24) Fig. 12 plots `LRU-Belady` / `FIFO-Belady` / `SIEVE-Belady`; ARC (FAST'03) reports miss ratio vs cache size | The metric and the reference bound: policy comparisons are reported as **miss ratio (the complement of hit rate) at a fixed cache size**, with the offline optimum as a bound and LRU as the baseline. |

## 2. Workload

Both shipped files are **verbatim byte prefixes** of the files Meta publishes in
the CacheLib workload-sharing bucket (the same bucket that CacheLib's own
documentation points CacheBench at). Byte range `bytes=0-1048575`, truncated on
a complete-line boundary: no row is edited, reordered, synthesised or dropped.

| role | shipped path | published object | bytes shipped | rows | lookups | distinct keys | DELETE rows | sha256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent-visible | `traces/kvcache_202206_traces_1.csv` | `pub/kvcache/202206/kvcache_traces_1.csv` (4,892,102,575 B, ETag `3841ff06e9706c30e65c72e3b9e38263-292`, 2023-02-09T21:38:58Z) | 1,048,554 | 44,379 | 43,957 | 21,143 | 422 | `5503257dbd9d73c455754c6caebef8409cecf17188dfef2cad195acfdb8715d1` |
| evaluator-only | `verification/heldout/kvcache_202206_traces_2.csv` | `pub/kvcache/202206/kvcache_traces_2.csv` (4,814,294,537 B, ETag `7516698ebd6864fac8cfcdd3ba640071-287`, 2023-02-09T21:38:58Z) | 1,048,570 | 44,414 | 44,045 | 20,881 | 369 | `f2d3b494b166199543ef02aaf98185de5d818d07ce0f0b677f77254003f77bfa` |

Sources (fetched with an HTTP `Range` request, `206 Partial Content`):
`https://cachelib-workload-sharing.s3.amazonaws.com/pub/kvcache/202206/kvcache_traces_1.csv`
and `.../kvcache_traces_2.csv`. The bucket listing
(`https://cachelib-workload-sharing.s3.amazonaws.com/?list-type=2&prefix=pub/kvcache/`)
gives the object sizes, ETags and timestamps above; `pub/` contains
`cdn/`, `kvcache/`, `memcache/`, `storage/`.

Why a **prefix** rather than the whole file: the published object is 4.8 GB, and
a compiled/LLM benchmark cannot replay that inside an execution gate. A
contiguous prefix is a real sample of the same stream (rows are replayed in file
order, exactly as CacheBench reads them), and CacheLib's own documentation
sanctions reducing the trace ("Amplifying the trace data ... Resource scaling or
Trace Amplification"), so the reduction is recorded with its byte range and
digest instead of being hidden. The development and the held-out stream are two
**different published files** (day 1 vs day 2 of the same cluster trace set),
which is what this benchmark uses instead of a synthetic workload.

## 3. Replay semantics (what a "request" means)

* **Format** - the CacheLib KV replay columns, header-mapped exactly as
  CacheBench's `TraceFileStream` does it (E4).
* **`ignoreOpCount = true`** (E5). CacheBench's default *repeats* a row
  `op_count` times; this benchmark declares the documented knob that replays one
  observed request once. Measured consequence on the **same** held-out file:

  | setting | lookups | immediate repeats of the previous key | LRU at capacity 1 | LRU at the graded capacity | LRU-2Q | offline optimum | LRU -> optimum headroom |
  | --- | --- | --- | --- | --- | --- | --- | --- |
  | `ignoreOpCount=true` (declared) | 44,045 | 18.6 % | 0.1857 | **0.2663** | 0.2835 | 0.4325 | **0.1662** |
  | `op_count` expanded (CacheBench default) | 127,893 | 72.0 % | 0.7195 | 0.7473 | 0.7556 | 0.8045 | 0.0572 |

  With the aggregation counter expanded, ~72 % of the graded lookups are an
  immediate repeat of the previous key, so a capacity-1 cache already scores
  0.72 and the total headroom above LRU is 5.7 points. The declared setting
  makes the measured quantity the **eviction decision** (16.6 points of headroom
  above LRU, 44 % relative) instead of the counter's burst structure. Both
  variants are reported here so the choice can be audited; the shipped trace
  bytes are identical either way.
* **Lookups** - every `GET`/`SET` row is a cache reference, and a miss loads the
  object (E5, `enableLookaside`: "follow get misses with a set"). This is also
  the reference-stream model of the classic literature (E9): the object miss
  ratio of a demand-paging cache. It is the model that makes a *replacement*
  decision at every reference.
* **`DELETE` rows are excluded** from the reference stream (422 rows in the
  visible file, 369 in the held-out one), because the frozen canonical protocol
  (`FE-BATCH-JSON-STDIO-V1`) has no delete channel to express one to the
  candidate. They stay in the shipped bytes and their count is frozen in
  `references/constants.json`; the exclusion is deterministic and is re-checked
  by the evaluator on every run.
* **What is NOT modelled**: CacheLib's byte-sized items and its slab allocator
  (`allocFactor`, `minAllocSize`, `maxAllocSize`, `nvmCacheSizeMB`) and therefore
  the object-size column. The framework's canonical protocol fixes a
  unit-object cache (`access(key)`), so the capacity is an object count and the
  `size` column is carried in the shipped data but not used. A byte-capacity
  variant would need a different protocol and is out of scope for this revision;
  it is recorded as a limitation, not claimed as supported.

## 4. Capacity

`cache_size = 417 objects = int(0.02 x 20,881)` - 2 % of the graded workload's
distinct-object working set. It is frozen as an integer in
`verification/evaluator.py` and `references/constants.json`; nothing at run time
can move it.

* The **fraction** comes from the documented cache-size sweeps (E8):
  `0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4`.
* The **selection** is the deterministic criterion "the documented fraction with
  the largest LRU -> offline-optimum headroom on the graded workload", i.e. the
  capacity at which the eviction decision is what is being measured. Full sweep
  on the held-out stream (frozen, reproducible):

  | fraction | capacity | LRU | FIFO | LRU-2Q | offline optimum | headroom |
  | --- | --- | --- | --- | --- | --- | --- |
  | 0.001 | 20 | 0.246362 | 0.246384 | 0.244205 | 0.272449 | 0.026087 |
  | 0.002 | 41 | 0.247043 | 0.247020 | 0.246884 | 0.299035 | 0.051992 |
  | 0.005 | 104 | 0.247724 | 0.247747 | 0.250199 | 0.348167 | 0.100443 |
  | 0.01 | 208 | 0.252356 | 0.251743 | 0.262118 | 0.389079 | 0.136724 |
  | **0.02** | **417** | **0.266296** | **0.263980** | **0.283483** | **0.432467** | **0.166171** |
  | 0.05 | 1044 | 0.340356 | 0.331275 | 0.317516 | 0.490294 | 0.149938 |
  | 0.1 | 2088 | 0.391191 | 0.375888 | 0.366284 | 0.522125 | 0.130934 |
  | 0.2 | 4176 | 0.448019 | 0.429197 | 0.437416 | 0.525917 | 0.077898 |
  | 0.3 | 6264 | 0.478828 | 0.460824 | 0.471064 | 0.525917 | 0.047088 |
  | 0.4 | 8352 | 0.497287 | 0.481076 | 0.489658 | 0.525917 | 0.028630 |

  The visible trace gives the same shape at the same fraction (LRU 0.264167,
  LRU-2Q 0.278636, offline optimum 0.428783, headroom 0.164615), so the
  development capacity 422 = `int(0.02 x 21,143)` is the analogue the agent uses.
* Why `cacheSizeMB` (E6: 43,000 MB for this trace family) is **not** copied
  directly: it is a *byte* capacity for the full amplified 5-day, 500-host
  stream. Neither the amplification (`ampFactor: 100`) nor the byte accounting
  survives a reduced, object-count replay, so transplanting "43000" would be a
  fabricated constant. What *is* reused from E6 is the experiment's shape (one
  fixed capacity, one real trace, policy comparison) and the trace itself; the
  reduction is recorded with its derivation (E3's resource-scaling rule).

## 5. Score

**`combined_score = hit_rate = hits / lookups` on the held-out trace at capacity
417.** One number, no weights, no bonus, no penalty, no normalisation.

| component | definition | external basis | kept |
| --- | --- | --- | --- |
| hit rate | hits / lookups | E1 ("compare the cache performance (hit ratio)"; "metrics such as hit rate") | yes - it *is* the score |
| miss ratio | 1 - hit rate (reported in `metrics`) | E9 (the literature's reporting form) | yes, auxiliary |
| LRU baseline | same replay, CacheLib's default `LruAllocator` (E2, E6) | E1, E2 | yes, reported + frozen |
| FIFO, LRU-2Q | same replay with CacheLib's other policies (E2: LRU / LRU-2Q; E1: "LRU vs 2Q vs FIFO") | E1, E2 | yes, reported |
| offline optimum | Belady 1966 (E9), also the upper bound that rejects cheating | E9 | yes, bound + validity check |
| composite weights (hit rate x %, latency y %, memory z %) | - | none found in E1/E2/E6/E7 or in E9 | **rejected** |
| "headroom" score `(R_BASE - R_policy)/(R_BASE - R_MIN)` | - | none (this is the previous design's formula; the 11.46 audit shows "headroom" occurs 0x in SIEVE NSDI'24 and 0x in ARC FAST'03 and libCacheSim has no such score) | **rejected** |
| penalty / bonus terms, sentinel rescaling, per-run normalisation | - | none | **rejected** |

The evaluator's own reference replays on the held-out stream at capacity 417 are
frozen as exact integers - LRU 11,729 hits, FIFO 11,627, LRU-2Q 12,486, offline
optimum 19,048 - and are re-derived on every run: any drift in the model or the
data is a rejection, not a different score.

## 6. What the revision removed (before -> after)

| item | previous LLM design (Phase 11.39 iter 5/6) | now | why |
| --- | --- | --- | --- |
| score | `round(clip01((R_BASE - R_policy)/(R_BASE - R_MIN)), 12)`, `R_MIN`/`R_BASE` = Belady/LRU on the *fixture* instance | hit rate on a real held-out trace | the composite formula has no external basis (11.46 audit) |
| workload | an LCG `_synthetic_runs()` instance generated by the fixture builder, plus a 1 MB `cloudPhysicsIO` **sample** trace | verbatim prefixes of Meta's published kvcache traces (day 1 visible, day 2 held out) | E8: the sample traces "should not be used for evaluating different algorithms' miss ratios"; a generated workload is not a production workload |
| capacity | 512 / 2048 / 8192 objects, declared in prose | 417 objects = 2 % of the held-out working set, from the documented sweep (E8) with a stated criterion | the old numbers have no source |
| metric plumbing | `score` recomputed from `R_MIN`/`R_BASE` measured on the fixture instance; executed evaluator differed from the one on disk (11.46 audit) | one frozen evaluator, frozen reference hits, digest-checked workload | reproducibility |
| lookahead check | none in the executed evaluator (a policy equal to the optimum scored 1.0 with no reasoning) | causality probe on a truncated instance + hard rejection above the offline optimum | E9 methodology; anti-cheating |
| declarations | `FE-STREAM-JSONL-V2`, `scripts/init.py`, `Dockerfile`, `cffi`, `seccomp`, `libCacheSim`, pinned hashes - claimed but not implemented (11.46 audit / Phase 11.27-11.29) | only what exists: stdlib Python, `FE-BATCH-JSON-STDIO-V1`, the shipped files listed in `README.md` | design/artifact fidelity |

## 7. Honest boundaries (not claimed to be solved here)

1. **Single graded capacity.** The score is one capacity (417 objects). CacheLib
   would also sweep `cacheSizeMB`; the sweep is recorded as design-time evidence
   and the evaluator reports the fixed baseline, but a multi-capacity score is
   not implemented.
2. **Object-count capacity, no byte accounting.** See section 3.
3. **Prefix sampling.** The graded stream is the first ~44k requests of a 4.8 GB
   published file. It is real, unfiltered and reproducible, but it is 0.007 % of
   the published object and is therefore not a claim about the whole cluster.
4. **Held-out data is public by construction.** Meta publishes these traces for
   exactly this purpose, so the guarantee is *"the agent's declared inputs and
   the graded instance do not contain the held-out stream"*, not secrecy. A
   submission that fetched the published file by name and tried to synthesise a
   schedule would still face the legality check, the causality probe and the
   offline-optimum bound - but "memorise the public trace" is a residual risk of
   any evaluation over public data, and it is recorded here rather than denied.
5. **No admission control, no prefetching, no TTL** - the frozen protocol is an
   eviction-only interface (`access(key)`), matching the task's scope decision.

## 8. Reproduction

```bash
# workload bytes (verbatim prefixes, Range requests)
curl -r 0-1048575 -o dev.csv https://cachelib-workload-sharing.s3.amazonaws.com/pub/kvcache/202206/kvcache_traces_1.csv
curl -r 0-1048575 -o held.csv https://cachelib-workload-sharing.s3.amazonaws.com/pub/kvcache/202206/kvcache_traces_2.csv
# digests must equal the digests in references/constants.json

# frozen reference numbers (no network, no LLM)
python -c "import sys;sys.path.insert(0,'verification');import reference_cache as R;k,s=R.load_reference_stream('verification/heldout/kvcache_202206_traces_2.csv');\
print(s);print('LRU',R.replay(R.Lru(417),k,417)['hits'],'2Q',R.replay(R.TwoQ(417),k,417)['hits'],'OPT',R.belady_hits(k,417))"

# the graded score of the frozen baseline
python verification/evaluator.py baseline/solution.py problem.json
```
