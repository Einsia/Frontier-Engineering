"""Child process for the isolated kernel-benchmark harness.

Runs in exactly one of two roles, never both:

``trusted``
    Imports only benchmark-owned code (``baseline/task.py``, ``baseline/utils.py``,
    ``baseline/reference.py``) plus the task adapter. It generates the benchmark
    inputs, keeps the authoritative copy in *its own memory*, and later verifies
    candidate outputs against its own reference implementation. ``submission.py``
    does not exist in this process's working directory, so the candidate is not
    importable here even by accident.

``candidate``
    Imports ``baseline.submission`` (the candidate) and does nothing but run and
    time it. Everything it reports is an *observation* the parent sanity-checks;
    it is never authority. In particular this process never decides whether an
    output is correct and never sees a score.

Protocol: one JSON object per line in on ``--cmd-fd``, one JSON object per line
out on ``--rsp-fd``. Both are pipes the parent created, so stdout/stderr stay
free for whatever the candidate decides to print.

Every response carries the nonce the parent sent in the opening handshake. The
handshake completes before the candidate process is spawned, so the nonce is
never in argv, in the environment, or on disk. A candidate that locates the
trusted worker's pipe through ``/proc/<pid>/fd`` and writes a forged verdict
into it cannot produce a line the parent will accept.

The timed region covers exactly ``custom_kernel(...)`` plus the device sync.
Input preparation, output retention and output serialization all happen outside
it, and the parent separately measures the wall-clock time of the whole batch so
a fabricated duration can be caught.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from typing import Any

# sys.path[0] is this script's directory, which is the role's working directory:
# `import task_adapter` and `from baseline import reference` resolve there and
# nowhere else.
import torch  # noqa: E402

import task_adapter as adapter  # noqa: E402


class _Chan:
    """The parent-facing command/response channel."""

    def __init__(self, cmd_fd: int, rsp_fd: int) -> None:
        self._in = os.fdopen(cmd_fd, "r", encoding="utf-8")
        self._out = os.fdopen(rsp_fd, "w", encoding="utf-8")
        self.nonce = ""

    def read(self) -> dict[str, Any] | None:
        line = self._in.readline()
        if not line:
            return None
        try:
            obj = json.loads(line)
        except Exception:
            return {"cmd": "__bad__"}
        return obj if isinstance(obj, dict) else {"cmd": "__bad__"}

    def send(self, payload: dict[str, Any]) -> None:
        out = dict(payload)
        out["nonce"] = self.nonce
        self._out.write(json.dumps(out, default=str) + "\n")
        self._out.flush()


def _cuda_ready() -> bool:
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


class _Timer:
    """Times one kernel call.

    ``cuda_event`` matches the TriMul benchmark's original methodology and
    ``perf_counter`` matches FlashAttention's and MLA's, so an honest candidate's
    number stays comparable with the published ones. Both fall back to a plain
    synchronized wall clock when there is no CUDA device (CPU stand-in runs).
    """

    def __init__(self, kind: str) -> None:
        self.cuda = _cuda_ready()
        self.kind = kind if (kind == "cuda_event" and self.cuda) else "perf_counter"

    def sync(self) -> None:
        if self.cuda:
            torch.cuda.synchronize()

    def time_call(self, fn, arg):
        if self.kind == "cuda_event":
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            self.sync()
            start.record()
            out = fn(arg)
            end.record()
            self.sync()
            return out, float(start.elapsed_time(end)) * 1e6
        self.sync()
        t0 = time.perf_counter_ns()
        out = fn(arg)
        self.sync()
        t1 = time.perf_counter_ns()
        return out, float(t1 - t0)


class Worker:
    def __init__(self, role: str, chan: _Chan, timer_kind: str) -> None:
        self.role = role
        self.chan = chan
        self.timer = _Timer(timer_kind)
        self.kernel = None
        self.states: dict[int, Any] = {}
        self.pending: list[Any] = []

    # -- trusted -------------------------------------------------------
    def cmd_prepare(self, msg: dict[str, Any]) -> dict[str, Any]:
        case = int(msg["case"])
        args = dict(msg["args"])
        state = adapter.make_state(args, int(msg["seed"]))
        self.states[case] = state
        path = str(msg["path"])
        adapter.save_state(state, path)
        return {"ok": True, "bytes": os.path.getsize(path)}

    def cmd_verify(self, msg: dict[str, Any]) -> dict[str, Any]:
        case = int(msg["case"])
        state = self.states[case]
        results = []
        for item in msg["outputs"]:
            alpha = float(item["alpha"])
            path = str(item["path"])
            try:
                out = adapter.load_output(path)
            except Exception as exc:
                results.append({"round": item["round"], "ok": False,
                                "error": f"unreadable output: {exc}"})
                continue
            # The reference is recomputed here, from this process's own copy of
            # the input, with the benchmark's own tolerances. Nothing the
            # candidate wrote takes part in the decision except `out` itself.
            data = adapter.apply_round(state, alpha)
            try:
                error = adapter.check(data, out)
            except Exception as exc:
                error = f"check raised: {type(exc).__name__}: {exc}"
            results.append({"round": item["round"], "ok": not error,
                            "error": str(error)[:2000],
                            "fingerprint": _fingerprint(out)})
        return {"ok": True, "results": results}

    def cmd_release(self, msg: dict[str, Any]) -> dict[str, Any]:
        self.states.pop(int(msg["case"]), None)
        self.pending = []
        _free_device()
        return {"ok": True}

    # -- candidate -----------------------------------------------------
    def cmd_load(self, msg: dict[str, Any]) -> dict[str, Any]:
        case = int(msg["case"])
        self.states[case] = adapter.load_state(str(msg["path"]))
        return {"ok": True}

    def cmd_warmup(self, msg: dict[str, Any]) -> dict[str, Any]:
        state = self.states[int(msg["case"])]
        seconds = float(msg.get("seconds", 0.2))
        min_iters = int(msg.get("min_iters", 3))
        alpha = float(msg.get("alpha", 0.0))
        iters = 0
        start = time.perf_counter()
        # no_grad matches the benchmarks' own measurement loop: these are
        # forward-only kernels, and autograd bookkeeping is not part of what is
        # being measured.
        with torch.no_grad():
            while iters < min_iters or (time.perf_counter() - start) < seconds:
                data = adapter.apply_round(state, alpha)
                self.kernel(data)
                self.timer.sync()
                iters += 1
        return {"ok": True, "iters": iters}

    def cmd_run(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Time one batch. Every rep in the batch is verified afterwards, so
        there is no such thing here as an unverified timed rep to skip work in."""
        state = self.states[int(msg["case"])]
        alphas = [float(a) for a in msg["alphas"]]
        durations: list[float] = []
        outs: list[Any] = []
        with torch.no_grad():
            for alpha in alphas:
                data = adapter.apply_round(state, alpha)
                out, ns = self.timer.time_call(self.kernel, data)
                durations.append(ns)
                outs.append(out)
        self.pending = outs
        return {"ok": True, "durations_ns": durations}

    def cmd_flush(self, msg: dict[str, Any]) -> dict[str, Any]:
        paths = [str(p) for p in msg["paths"]]
        if len(paths) != len(self.pending):
            return {"ok": False, "error": f"have {len(self.pending)} outputs, asked for {len(paths)}"}
        for out, path in zip(self.pending, paths):
            adapter.save_output(out, path)
        self.pending = []
        _free_device()
        return {"ok": True}


def _fingerprint(out) -> list[float]:
    """A couple of cheap reductions over the candidate's output.

    Two different rounds run on two different inputs, so an honest kernel cannot
    produce the same numbers twice. The parent compares these across rounds to
    catch a result computed once and replayed -- which no tolerance check can
    catch on its own, because a replayed answer is only wrong to the extent the
    perturbation moved the reference.
    """
    tensors = out if isinstance(out, (tuple, list)) else (out,)
    values: list[float] = []
    for tensor in tensors:
        detached = tensor.detach()
        values.append(float(detached.sum(dtype=torch.float64)))
        values.append(float(torch.linalg.vector_norm(detached, ord=2, dtype=torch.float64)))
    return values


def _free_device() -> None:
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=("trusted", "candidate"))
    parser.add_argument("--cmd-fd", type=int, required=True)
    parser.add_argument("--rsp-fd", type=int, required=True)
    parser.add_argument("--timer", default="perf_counter")
    args = parser.parse_args(argv)

    chan = _Chan(args.cmd_fd, args.rsp_fd)
    hello = chan.read()
    if not hello or hello.get("cmd") != "hello":
        return 2
    chan.nonce = str(hello.get("nonce", ""))
    worker = Worker(args.role, chan, args.timer)

    try:
        if args.role == "candidate":
            # Imported only now, after torch and the adapter are resident, so a
            # candidate that rewrites either on import cannot affect this run.
            from baseline.submission import custom_kernel
            worker.kernel = custom_kernel
        chan.send({"ok": True, "role": args.role, "torch": torch.__version__,
                   "cuda": _cuda_ready(), "timer": worker.timer.kind})
    except Exception as exc:
        chan.send({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                   "traceback": traceback.format_exc()[-4000:]})
        return 3

    handlers = {
        "prepare": worker.cmd_prepare,
        "verify": worker.cmd_verify,
        "release": worker.cmd_release,
        "load": worker.cmd_load,
        "warmup": worker.cmd_warmup,
        "run": worker.cmd_run,
        "flush": worker.cmd_flush,
    }
    while True:
        msg = chan.read()
        if msg is None or msg.get("cmd") == "bye":
            return 0
        handler = handlers.get(str(msg.get("cmd")))
        if handler is None:
            chan.send({"ok": False, "error": f"unknown command {msg.get('cmd')!r}"})
            continue
        try:
            chan.send(handler(msg))
        except Exception as exc:
            chan.send({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                       "traceback": traceback.format_exc()[-4000:]})


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
