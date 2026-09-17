"""Frozen reference cache model for the CacheLib-aligned cache replacement task.

This file is FROZEN (read-only): the evaluator imports it, and it is the single
source of truth for what a legal replay *means*. It is never imported by a
submission.

Replay semantics
----------------
The workload is a reference stream derived from a REAL published Meta kvcache
trace (CacheLib workload sharing bucket, `pub/kvcache/202206`). The CSV columns
are the ones CacheLib's own replay generator defines -- see
`cachelib/cachebench/workload/KVReplayGenerator.h`:

    Default order is key,op,size,op_count,key_size,ttl

* `op_count` is CacheLib's repeat counter: by default the replay generator
  repeats the same request `op_count` times (`ReqWrapper::repeats_`). This
  benchmark declares CacheBench's `ignoreOpCount` knob
  (`cachelib/cachebench/util/Config.h:275` "ignore opCount and does not repeat
  operations", parsed by `util/Config.cpp:61`), so ONE CSV ROW is ONE reference.
  Rows are never reordered. `REPEAT_OP_COUNT` below is the single switch; the
  provenance document reports the measured consequence of both settings.
* `GET` / `SET` are cache lookups. This benchmark uses CacheBench's documented
  lookaside semantics ("missing keys are set in the cache"), i.e. every lookup
  is a reference to the cache: a miss loads the object (and may evict), which is
  also the reference-stream model of the classic replacement literature
  (Belady 1966; ARC FAST'03; SIEVE NSDI'24; libCacheSim).
* `DELETE` rows are NOT part of the graded reference stream: the frozen
  canonical protocol (`FE-BATCH-JSON-STDIO-V1`) has no delete channel, so a
  delete cannot be expressed to the candidate. The rows stay in the shipped
  trace file and their count is reported; they are excluded deterministically.

Model (unit objects)
--------------------
    capacity            int, the maximum number of resident objects
    policy.access(key)  -> victim key (str) or None
    * on a hit  : nothing may be evicted, access() must return None
    * on a miss : the object is loaded; if the cache was already at capacity,
                  exactly one resident object is evicted, namely the one the
                  policy returns from that same access() call.
    hits                a reference whose key is resident when it is looked up
    hit_rate            hits / lookups

The model is deliberately strict: a victim that is not resident, or a victim
returned on a hit, is a protocol violation -- there is no lenient fallback.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import pathlib

PROTOCOL = "FE-BATCH-JSON-STDIO-V1"

#: CacheLib KV replay columns (KVReplayGenerator.h: "Default order is
#: key,op,size,op_count,key_size,ttl"). Resolution is header-driven, exactly as
#: CacheBench's TraceFileStream does it, with the documented default order as a
#: fallback for a headerless file.
DEFAULT_COLUMNS = ("key", "op", "size", "op_count", "key_size", "ttl")

LOOKUP_OPS = ("GET", "SET")
SKIPPED_OPS = ("DELETE",)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _column_index(header):
    cols = [c.strip() for c in header]
    if "key" in cols and "op" in cols:
        return {c: i for i, c in enumerate(cols)}
    return {c: i for i, c in enumerate(DEFAULT_COLUMNS)}


#: CacheBench `ignoreOpCount`. True would repeat a request `op_count` times.
#: Declared False (see docs/PROVENANCE.md, "replay semantics"), i.e. one
#: reference per observed request.
REPEAT_OP_COUNT = False


def load_reference_stream(path, repeat_op_count=None):
    """Return (keys, stats) for a CacheLib kvcache CSV file.

    `keys` is the graded reference stream: one entry per replayed lookup, in
    file order (`op_count` expanded only when `repeat_op_count` is true).
    `stats` records everything the provenance and the evaluator report.
    """
    if repeat_op_count is None:
        repeat_op_count = REPEAT_OP_COUNT
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="strict")
    lines = text.splitlines()
    if not lines:
        return [], {"rows": 0, "lookups": 0, "distinct_keys": 0, "ops": {}}
    idx = _column_index(lines[0].split(","))
    keys, ops, skipped = [], {}, 0
    rows = 0
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) < 3:
            raise ValueError("malformed trace row: %r" % line[:80])
        key = parts[idx["key"]]
        op = parts[idx["op"]].strip() if "op" in idx else "GET"
        reps = int(parts[idx["op_count"]]) if "op_count" in idx else 1
        if reps <= 0:
            continue
        if not repeat_op_count:
            reps = 1
        rows += 1
        ops[op] = ops.get(op, 0) + reps
        if op in SKIPPED_OPS:
            skipped += reps
            continue
        if op not in LOOKUP_OPS:
            raise ValueError("unsupported op %r" % op)
        keys.extend([key] * reps)
    stats = {
        "rows": rows,
        "lookups": len(keys),
        "skipped_ops": skipped,
        "ops": ops,
        "distinct_keys": len(set(keys)),
    }
    return keys, stats


# ---------------------------------------------------------------------------
# reference policies (CacheLib ships LRU and LRU-2Q; FIFO is the classic
# comparison point and the offline optimum is the literature's reference bound)
# ---------------------------------------------------------------------------

class Lru:
    """CacheLib default DRAM eviction (LruAllocator)."""

    def __init__(self, capacity):
        from collections import OrderedDict

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


class Fifo:
    """First-in first-out eviction."""

    def __init__(self, capacity):
        from collections import deque

        self.capacity = int(capacity)
        self.order = deque()
        self.resident = set()

    def access(self, key):
        if key in self.resident:
            return None
        if len(self.resident) < self.capacity:
            self.resident.add(key)
            self.order.append(key)
            return None
        victim = self.order.popleft()
        self.resident.discard(victim)
        self.resident.add(key)
        self.order.append(key)
        return victim


class TwoQ:
    """The LRU-2Q family: a probation queue plus a protected queue.

    CacheLib exposes this as `allocator: "LRU-2Q"`. This is the standard 2Q
    shape: an object enters probation (a small FIFO/LRU), a second reference
    promotes it to the protected LRU, and eviction takes the probation tail
    before the protected LRU tail. `probation_fraction` is the share of the
    capacity given to the probation queue.
    """

    def __init__(self, capacity, probation_fraction=0.25):
        from collections import OrderedDict

        self.capacity = int(capacity)
        self.probation_cap = max(1, int(self.capacity * probation_fraction))
        self.protected_cap = max(1, self.capacity - self.probation_cap)
        self.probation = OrderedDict()
        self.protected = OrderedDict()

    def _evict(self):
        if self.probation:
            victim, _ = self.probation.popitem(last=False)
            return victim
        victim, _ = self.protected.popitem(last=False)
        return victim

    def access(self, key):
        if key in self.protected:
            self.protected.move_to_end(key)
            return None
        if key in self.probation:
            del self.probation[key]
            if len(self.protected) >= self.protected_cap:
                demoted, _ = self.protected.popitem(last=False)
                self.probation[demoted] = True
            self.protected[key] = True
            return None
        victim = None
        if len(self.probation) + len(self.protected) >= self.capacity:
            victim = self._evict()
        self.probation[key] = True
        if len(self.probation) > self.probation_cap:
            demoted, _ = self.probation.popitem(last=False)
            if len(self.protected) >= self.protected_cap:
                extra = self.protected.popitem(last=False)[0]
                self.probation[demoted] = True
                self.probation[extra] = True
            else:
                self.protected[demoted] = True
        return victim


# ---------------------------------------------------------------------------
# replay + offline bound
# ---------------------------------------------------------------------------

def replay_evictions(keys, capacity, evictions):
    """THE frozen model: replay `keys` with a victim list.

    `evictions[i]` is the victim the submission asked for at access `i` (or
    None). A hit must not evict; a miss on a full cache must name one resident
    victim. Anything else is reported as `illegal` -- there is no lenient
    fallback and no silent second choice.
    """
    cap = int(capacity)
    if len(evictions) != len(keys):
        raise ValueError("evictions must have exactly one entry per access")
    resident = set()
    hits = misses = 0
    illegal = None
    for i, key in enumerate(keys):
        victim = evictions[i]
        hit = key in resident
        if hit:
            hits += 1
            if victim is not None and illegal is None:
                illegal = {"index": i, "reason": "eviction_on_hit", "victim": victim}
            continue
        misses += 1
        if len(resident) >= cap:
            if victim is None or victim not in resident:
                if illegal is None:
                    illegal = {"index": i, "reason": "victim_not_resident", "victim": victim}
            else:
                resident.discard(victim)
        elif victim is not None and illegal is None:
            illegal = {"index": i, "reason": "eviction_below_capacity", "victim": victim}
        resident.add(key)
    total = hits + misses
    return {
        "hits": hits,
        "misses": misses,
        "lookups": total,
        "hit_rate": (hits / total) if total else 0.0,
        "miss_ratio": (misses / total) if total else 0.0,
        "illegal": illegal,
    }


def replay(policy, keys, capacity):
    """Replay `keys` through a policy object (same frozen model)."""
    return replay_evictions(keys, capacity, [policy.access(key) for key in keys])


def belady_hits(keys, capacity):
    """Offline optimum (Belady 1966), computed with next-use chains."""
    cap = int(capacity)
    n = len(keys)
    nxt = [n] * n
    pos = {}
    for i in range(n - 1, -1, -1):
        k = keys[i]
        nxt[i] = pos.get(k, n)
        pos[k] = i
    resident = {}
    heap = []
    hits = 0
    for i in range(n):
        k = keys[i]
        if k in resident:
            hits += 1
            resident[k] = i
            heapq.heappush(heap, (-nxt[i], i, k))
            continue
        if len(resident) >= cap:
            while heap:
                neg, when, cand = heapq.heappop(heap)
                if resident.get(cand) == when:
                    del resident[cand]
                    break
        resident[k] = i
        heapq.heappush(heap, (-nxt[i], i, k))
    return hits
