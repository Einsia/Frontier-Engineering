# Cache Replacement Policy Optimization

A Frontier-Eng benchmark: an **online cache replacement (eviction) policy** is
optimised against a **real Meta production kvcache trace** published by CacheLib
for CacheBench, and scored by **hit rate** at a fixed cache capacity, compared
against CacheLib's default LRU.

## Layout

| path | role |
| --- | --- |
| `policy.py` | the agent-editable submission (initial program: LRU, `FE-BATCH-JSON-STDIO-V1`) |
| `traces/kvcache_202206_traces_1.csv` | the agent-visible real trace (a verbatim prefix of CacheLib's published `pub/kvcache/202206/kvcache_traces_1.csv`) |
| `verification/evaluator.py` | frozen evaluator: replays the submission on the held-out trace and prints `{"valid":..., "combined_score": hit_rate, "metrics": {...}}` |
| `verification/reference_cache.py` | frozen replay model + reference policies (LRU / FIFO / LRU-2Q) + the offline optimum (Belady 1966) |
| `verification/heldout/` | the evaluator-only real trace (a different published file; never in the agent's manifests) |
| `baseline/solution.py` | frozen baseline = CacheLib's default LRU |
| `references/constants.json` | frozen numbers, sources and the score definition |
| `docs/PROVENANCE.md` | where every number comes from (CacheLib sources, workload, capacity, metric) |
| `docs/agent_notes.md` | notes for the agent (model, protocol, local measurement) |
| `frontier_eval/` | the canonical execution manifests |

## Run it locally

```bash
# the frozen baseline over the agent-visible trace
python - <<'PY'
import json, subprocess, sys, tempfile, pathlib
sys.path.insert(0, "verification")
import reference_cache as R
keys, stats = R.load_reference_stream("traces/kvcache_202206_traces_1.csv")
cap = 422
instance = {"protocol": "FE-BATCH-JSON-STDIO-V1",
            "runs": [{"name": "dev", "cache_size": cap, "keys": keys}]}
with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d) / "i.json"; p.write_text(json.dumps(instance))
    out = subprocess.run([sys.executable, "baseline/solution.py", str(p)], capture_output=True, text=True)
    print("baseline hit rate:", R.replay_evictions(keys, cap, json.loads(out.stdout)["runs"][0]["evictions"])["hit_rate"])
PY
```

## Provenance

Every constant is derived from a real CacheLib artifact — the CacheBench
documentation, the CacheBench configuration schema and the Meta trace files
CacheLib publishes — and the derivation is written down per item in
`docs/PROVENANCE.md`, including what was **rejected** as unsupported (composite
score weights, invented cache sizes, LLM-generated workloads).

## Frontier-Eval onboarding

* unified benchmark id: `ComputerSystems/CacheReplacementPolicyOptimization`
* editable program: `policy.py` (only the `EVOLVE-BLOCK` region is scored)
* validation: `python verification/evaluator.py policy.py`
* structured result: the unified `eval_command` writes the evaluator's single stdout
  JSON object to `metrics.json` in the evaluation cwd, which is the file `task=unified`
  reads (`parse_stdout_json` is disabled repo-wide, so the evaluator's own stdout is
  not consumed by the framework)
* runtime overrides: **none** — Python standard library only; no network, no
  Docker and no third-party or system toolchain requirement
  (see `verification/requirements.txt`)
