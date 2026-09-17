#!/usr/bin/env python3
"""verification/evaluator.py -- FROZEN grading program (do not edit).

CANDIDATE-PROTOCOL: FE-BATCH-JSON-STDIO-V1

    python verification/evaluator.py <candidate.py> [problem.json]

prints exactly ONE JSON object on stdout and exits 0:

    {"valid": <bool>, "combined_score": <float>, "metrics": {...}[, "error": str]}

`combined_score` is the HIT RATE the submission achieves on the held-out
workload (CacheBench reports hit ratio; see docs/PROVENANCE.md). The sentinel
`-1e18` means "rejected -- no score" (the framework's negative-control score
band). Extra prose never goes to stdout.

What is graded
--------------
The graded input is the EVALUATOR-ONLY workload: a real Meta kvcache trace
prefix published by CacheLib for CacheBench, shipped at
`verification/heldout/kvcache_202206_traces_2.csv`. It is not in the agent's
manifests and is never handed to the submission as content:

* the graded instance is BUILT HERE from the frozen file (the submission never
  receives the trace path and cannot influence the workload):
      {"protocol": "FE-BATCH-JSON-STDIO-V1",
       "runs": [{"name": "graded", "cache_size": 417, "keys": [...]}]}
* `problem.json` (the framework's execution fixture) is a DECLARATION, not the
  graded input: if it carries a `graded_instance` block it must agree with the
  frozen values below, otherwise the run is rejected. Its `runs` are never
  graded - a benchmark whose graded instance is whatever a fixture produced is
  not reproducible, and that is precisely what this evaluator refuses to do.

Strictness (why a submission can be rejected)
---------------------------------------------
* protocol      exit 0, exactly one JSON object on stdout, one entry per run,
                one victim per access (str key or null)
* legality      the frozen model in `reference_cache.py`: a hit never evicts, a
                miss on a full cache evicts exactly one RESIDENT key
* causality     the submission is replayed again on the first half of the same
                run; an ONLINE policy must make identical decisions, so any
                divergence means the submission used future accesses
* optimum       the hit rate may not exceed the offline optimum (Belady 1966,
                the literature's reference bound). It uses future knowledge, so
                exceeding it is impossible for a legal online policy
* trace         the workload file, its row/lookup/key counts and the reference
                baselines are all checked against the frozen values below
                before and after the submission runs

`valid=True` means "legal online policy, graded and reproducible"; it does NOT
mean "good": the quality is `combined_score`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_cache  # noqa: E402  (frozen sibling: the single replay model)

# ---------------------------------------------------------------------------
# frozen declaration (must match docs/PROVENANCE.md + references/constants.json)
# ---------------------------------------------------------------------------

PROTOCOL = "FE-BATCH-JSON-STDIO-V1"
INVALID_SCORE = -1e18

ROOT = Path(__file__).resolve().parent.parent

WORKLOAD_RELATIVE_PATH = "verification/heldout/kvcache_202206_traces_2.csv"
WORKLOAD_SHA256 = "f2d3b494b166199543ef02aaf98185de5d818d07ce0f0b677f77254003f77bfa"
WORKLOAD_SOURCE = (
    "https://cachelib-workload-sharing.s3.amazonaws.com/"
    "pub/kvcache/202206/kvcache_traces_2.csv"
)
WORKLOAD_BYTE_RANGE = "bytes=0-1048575"
WORKLOAD_ROWS = 44414
WORKLOAD_LOOKUPS = 44045
WORKLOAD_DISTINCT_KEYS = 20881
WORKLOAD_SKIPPED_DELETE_OPS = 369

#: CacheBench `ignoreOpCount` = False -> one reference per observed request
#: (docs/PROVENANCE.md, "replay semantics").
REPEAT_OP_COUNT = False

#: cache capacity: 2% of the graded workload's distinct-object working set. The
#: fraction comes from the documented cache-size sweeps (libCacheSim
#: `plot_mrc_size.py --sizes=0.001,...,0.4`; `cachesim ... 0.001,0.01,0.1,0.2`)
#: and it is the fraction with the largest LRU -> offline-optimum headroom on
#: this workload, i.e. the capacity at which the eviction decision is what is
#: being measured. Frozen as an INTEGER so no runtime value can move it.
CAPACITY_FRACTION = 0.02
CAPACITY_OBJECTS = 417

#: reference policies replayed over the same frozen workload and capacity.
#: Exact hit counts (integers), so any drift in the model or the data is a hard
#: rejection instead of a silently different score.
FROZEN_BASELINE_HITS = {"lru": 11729, "fifo": 11627, "lru_2q": 12486, "offline_optimum": 19048}

CANDIDATE_TIMEOUT_SECONDS = 12.0
CAUSALITY_PROBE_TIMEOUT_SECONDS = 6.0
CAUSALITY_PROBE_FRACTION = 0.5
OPTIMUM_TOLERANCE = 1e-9

USAGE = "usage: evaluator.py <candidate.py> [problem.json]"


def _result(valid, score, metrics, error=None):
    payload = {"valid": bool(valid), "combined_score": float(score), "metrics": metrics}
    if error:
        payload["error"] = str(error)
    return payload


def _invalid(metrics, reason):
    return _result(False, INVALID_SCORE, metrics, reason)


def _emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


# ---------------------------------------------------------------------------
# workload / instance
# ---------------------------------------------------------------------------

def load_graded_workload():
    """Load the held-out reference stream and check every frozen figure."""
    path = ROOT / WORKLOAD_RELATIVE_PATH
    if not path.is_file():
        return None, None, "held-out workload is missing: %s" % WORKLOAD_RELATIVE_PATH
    digest = reference_cache.sha256_file(path)
    if digest != WORKLOAD_SHA256:
        return None, None, (
            "held-out workload digest mismatch (expected %s, found %s): the frozen "
            "workload was modified" % (WORKLOAD_SHA256, digest)
        )
    keys, stats = reference_cache.load_reference_stream(path, REPEAT_OP_COUNT)
    drift = []
    if stats["rows"] != WORKLOAD_ROWS:
        drift.append("rows %d != %d" % (stats["rows"], WORKLOAD_ROWS))
    if stats["lookups"] != WORKLOAD_LOOKUPS:
        drift.append("lookups %d != %d" % (stats["lookups"], WORKLOAD_LOOKUPS))
    if stats["distinct_keys"] != WORKLOAD_DISTINCT_KEYS:
        drift.append("distinct keys %d != %d" % (stats["distinct_keys"], WORKLOAD_DISTINCT_KEYS))
    if stats["skipped_ops"] != WORKLOAD_SKIPPED_DELETE_OPS:
        drift.append("skipped ops %d != %d" % (stats["skipped_ops"], WORKLOAD_SKIPPED_DELETE_OPS))
    if drift:
        return None, None, "held-out workload parse drift: " + "; ".join(drift)
    return keys, stats, None


def build_instance(keys, run_name="graded"):
    return {
        "protocol": PROTOCOL,
        "workload": {
            "source": WORKLOAD_SOURCE,
            "byte_range": WORKLOAD_BYTE_RANGE,
            "sha256": WORKLOAD_SHA256,
            "lookups": WORKLOAD_LOOKUPS,
            "distinct_keys": WORKLOAD_DISTINCT_KEYS,
            "replay": "cachebench replay generator, ignoreOpCount=true, lookaside lookups",
        },
        "runs": [{"name": run_name, "cache_size": CAPACITY_OBJECTS, "keys": list(keys)}],
    }


def check_problem_declaration(problem_path):
    """`problem.json` may DECLARE the graded instance; it may not define it."""
    if problem_path is None:
        return None
    path = Path(problem_path)
    if not path.is_file():
        return "problem.json is missing: %s" % problem_path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return "problem.json is unreadable: %s" % exc
    if not isinstance(data, dict):
        return "problem.json is not a JSON object"
    declared = data.get("graded_instance")
    if declared is None:
        # the fixture instance is allowed to exist; it is simply not graded
        return None
    if not isinstance(declared, dict):
        return "problem.json graded_instance is not a JSON object"
    expected = {
        "sha256": WORKLOAD_SHA256,
        "lookups": WORKLOAD_LOOKUPS,
        "cache_size": CAPACITY_OBJECTS,
        "capacity_fraction": CAPACITY_FRACTION,
    }
    for field, value in expected.items():
        if field in declared and declared[field] != value:
            return (
                "problem.json graded_instance.%s is %r but the frozen benchmark "
                "declares %r" % (field, declared[field], value)
            )
    return None


# ---------------------------------------------------------------------------
# running the submission
# ---------------------------------------------------------------------------

def run_candidate(candidate, instance, timeout):
    """Run the submission once. Returns (payload, error, seconds)."""
    with tempfile.TemporaryDirectory(prefix="fe_cache_eval_") as tmp:
        instance_path = Path(tmp) / "instance.json"
        instance_path.write_text(json.dumps(instance), encoding="utf-8")
        started = time.time()
        try:
            completed = subprocess.run(
                [sys.executable, str(candidate), str(instance_path)],
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return None, "submission timed out after %.1fs" % timeout, time.time() - started
        except OSError as exc:
            return None, "submission could not be started: %s" % exc, time.time() - started
        seconds = time.time() - started
    if completed.returncode != 0:
        tail = completed.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        return None, "submission exited %s (stderr: %s)" % (
            completed.returncode, " | ".join(tail) or "<empty>"
        ), seconds
    stdout = completed.stdout.decode("utf-8", "replace").strip()
    if not stdout:
        return None, "submission printed nothing on stdout", seconds
    try:
        payload = json.loads(stdout)
    except ValueError as exc:
        return None, "submission stdout is not one JSON object: %s" % exc, seconds
    if not isinstance(payload, dict):
        return None, "submission stdout is not a JSON object", seconds
    return payload, None, seconds


def extract_evictions(payload, lookups, run_name):
    """Pull the victim list for `run_name` out of a submission payload."""
    runs = payload.get("runs")
    if not isinstance(runs, list):
        return None, "submission payload has no 'runs' list"
    named = [r for r in runs if isinstance(r, dict) and r.get("name") == run_name]
    if len(named) != 1:
        return None, "submission must return exactly one run named %r (got %d)" % (
            run_name, len(named),
        )
    evictions = named[0].get("evictions")
    if not isinstance(evictions, list):
        return None, "run %r has no 'evictions' list" % run_name
    if len(evictions) != lookups:
        return None, "run %r returned %d evictions for %d accesses" % (
            run_name, len(evictions), lookups,
        )
    for value in evictions:
        if value is not None and not isinstance(value, str):
            return None, "evictions must be a key (string) or null"
    return evictions, None


def grade(candidate_path, problem_path):
    metrics = {
        "capacity_objects": CAPACITY_OBJECTS,
        "capacity_fraction": CAPACITY_FRACTION,
    }
    declaration_error = check_problem_declaration(problem_path)
    if declaration_error:
        return _invalid(metrics, declaration_error)

    keys, stats, workload_error = load_graded_workload()
    if workload_error:
        return _invalid(metrics, workload_error)

    metrics.update({
        "lookups": WORKLOAD_LOOKUPS,
        "working_set_objects": WORKLOAD_DISTINCT_KEYS,
        "baseline_hit_rate_lru": FROZEN_BASELINE_HITS["lru"] / WORKLOAD_LOOKUPS,
        "baseline_hit_rate_fifo": FROZEN_BASELINE_HITS["fifo"] / WORKLOAD_LOOKUPS,
        "baseline_hit_rate_lru_2q": FROZEN_BASELINE_HITS["lru_2q"] / WORKLOAD_LOOKUPS,
        "offline_optimum_hit_rate": FROZEN_BASELINE_HITS["offline_optimum"] / WORKLOAD_LOOKUPS,
    })

    candidate = Path(candidate_path)
    if not candidate.is_file():
        return _invalid(metrics, "submission not found: %s" % candidate_path)

    instance = build_instance(keys)
    payload, error, seconds = run_candidate(candidate, instance, CANDIDATE_TIMEOUT_SECONDS)
    metrics["candidate_runtime_seconds"] = seconds
    if error:
        return _invalid(metrics, error)
    evictions, error = extract_evictions(payload, len(keys), "graded")
    if error:
        return _invalid(metrics, error)

    result = reference_cache.replay_evictions(keys, CAPACITY_OBJECTS, evictions)
    metrics["hits"] = result["hits"]
    metrics["misses"] = result["misses"]
    if result["illegal"]:
        return _invalid(
            metrics,
            "illegal eviction at access %(index)s: %(reason)s (victim=%(victim)r)" % result["illegal"],
        )

    probe_keys = keys[: max(1, int(len(keys) * CAUSALITY_PROBE_FRACTION))]
    probe_payload, error, probe_seconds = run_candidate(
        candidate, build_instance(probe_keys), CAUSALITY_PROBE_TIMEOUT_SECONDS,
    )
    metrics["causality_probe_lookups"] = len(probe_keys)
    metrics["causality_probe_runtime_seconds"] = probe_seconds
    if error:
        return _invalid(metrics, "causality probe failed: %s" % error)
    probe_evictions, error = extract_evictions(probe_payload, len(probe_keys), "graded")
    if error:
        return _invalid(metrics, "causality probe failed: %s" % error)
    divergence = next(
        (i for i in range(len(probe_keys)) if probe_evictions[i] != evictions[i]), None,
    )
    if divergence is not None:
        return _invalid(
            metrics,
            "causality violation at access %d: the submission changed a decision "
            "when later accesses were removed (full run said %r, truncated run "
            "said %r), so it is not an online policy"
            % (divergence, evictions[divergence], probe_evictions[divergence]),
        )

    optimum_hits = reference_cache.belady_hits(keys, CAPACITY_OBJECTS)
    if optimum_hits != FROZEN_BASELINE_HITS["offline_optimum"]:
        return _invalid(metrics, "offline-optimum reference drift: %d != %d" % (
            optimum_hits, FROZEN_BASELINE_HITS["offline_optimum"]))

    hit_rate = result["hit_rate"]
    metrics["hit_rate"] = hit_rate
    metrics["miss_ratio"] = result["miss_ratio"]
    metrics["improvement_over_lru"] = hit_rate - metrics["baseline_hit_rate_lru"]
    metrics["fraction_of_offline_optimum"] = (
        hit_rate / metrics["offline_optimum_hit_rate"] if metrics["offline_optimum_hit_rate"] else 0.0
    )
    if hit_rate > metrics["offline_optimum_hit_rate"] + OPTIMUM_TOLERANCE:
        return _invalid(metrics, (
            "hit rate %.6f exceeds the offline optimum %.6f, which no legal online "
            "policy can reach" % (hit_rate, metrics["offline_optimum_hit_rate"])
        ))

    after_digest = reference_cache.sha256_file(ROOT / WORKLOAD_RELATIVE_PATH)
    if after_digest != WORKLOAD_SHA256:
        return _invalid(metrics, "the held-out workload changed while the submission ran")
    return _result(True, hit_rate, metrics)


def main(argv):
    if len(argv) < 2 or len(argv) > 3:
        sys.stderr.write(USAGE + "\n")
        _emit({"valid": False, "combined_score": INVALID_SCORE,
               "metrics": {}, "error": USAGE})
        return 0
    candidate = argv[1]
    problem = argv[2] if len(argv) == 3 else None
    try:
        return _emit(grade(candidate, problem))
    except Exception as exc:  # pragma: no cover - defensive: never crash noisily
        _emit({"valid": False, "combined_score": INVALID_SCORE, "metrics": {},
               "error": "evaluator error: %s: %s" % (type(exc).__name__, exc)})
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
