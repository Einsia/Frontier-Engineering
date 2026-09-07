"""Scorer-side orchestration for the KernelEngineering benchmarks.

Why this exists
---------------
The three kernel benchmarks used to be scored like this: the evaluator ran
``verification/eval.py`` in a subprocess, that subprocess did
``from baseline.submission import custom_kernel``, and everything that decided
the score -- the reference implementation, the tolerance comparison, the clock,
and the log file the evaluator parsed -- lived in the same process as the
candidate. Three consequences, all of them exploitable with a few lines:

1. ``POPCORN_FD`` names an inherited, writable fd. A candidate could write
   ``check: pass`` and ``benchmark.0.mean: 1.0`` into it at import time and
   ``os._exit(0)`` before a kernel ever ran.
2. ``check_implementation`` was an ordinary module attribute; replacing it with
   ``lambda *_: ''`` made every output correct.
3. ``time.perf_counter_ns`` / ``torch.cuda.Event`` were equally replaceable, so
   the reported latency -- which *is* the score, ``1e9 / geom_mean_ns`` -- was
   whatever the candidate wanted.

The contract implemented here
-----------------------------
Two child processes, started in this order and never merged:

* the **trusted worker** holds only benchmark-owned code. It builds the inputs,
  keeps the authoritative copy in its own memory, and verifies candidate outputs
  against its own reference implementation with the benchmark's own tolerances.
* the **candidate worker** holds the candidate. It receives an input, runs the
  kernel, and hands back an output tensor and a duration. It never decides
  anything.

This process (the scorer) holds the score. It computes it from the trusted
worker's verdict and from durations it cross-checks against its own wall clock.

Two properties are worth stating precisely, because they are what the scores
now rest on:

* **Every timed rep is verified.** A batch of ``k`` reps produces ``k`` outputs
  and all ``k`` are checked. There is no unverified timed rep for a candidate to
  skip the work in, and each rep runs on a different input (a scorer-chosen
  perturbation of the staged base input), so a cached result from an earlier rep
  is wrong for the current one.
* **A fabricated duration is bounded by the scorer's own clock.** The scorer
  times each batch end to end; ``wall_batch / reps`` is an upper bound on the
  true per-rep cost that no in-process patching can lower. A report far below it
  is rejected outright; a report moderately below it is replaced by the scorer's
  own (conservative) number.

What this still does not close is written down in
``candidate_sandbox.py``'s docstring and in the KernelEngineering section of the
audit report: the child runs under the same uid as the scorer, so real isolation
needs ``task.runtime.isolation_mode=docker`` or a uid/mount namespace.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import select
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

INVALID_COMBINED_SCORE = -1e18

__all__ = ["KernelTaskConfig", "evaluate_kernel_task", "parse_test_cases"]


@dataclass
class KernelTaskConfig:
    """Everything task-specific the orchestration needs."""

    task_name: str
    benchmark_dir: Path
    bench_spec_rel: str
    #: modules copied into *both* worker dirs; ``submission.py`` is deliberately
    #: absent so the candidate is not importable from the trusted worker, and
    #: reference *solutions* (TriMul's ``solution.py``, MLA's ``mla_code_*.py``)
    #: are deliberately absent so the candidate cannot read them at eval time.
    baseline_modules: tuple[str, ...] = ("task.py", "utils.py", "reference.py")
    timer: str = "perf_counter"
    #: how many timed+verified reps to aim for per case
    target_samples: int = 10
    min_samples: int = 3
    #: outputs retained simultaneously per batch (disk/device bound)
    max_batch_reps: int = 4
    output_bytes_budget: int = 2 * 1024 ** 3
    warmup_s: float = 0.2
    alpha_scale: float = 0.05
    #: below this ratio of the scorer's own wall-clock bound the report is a
    #: fabrication and the run is invalid
    hard_gate: float = 0.02
    #: below this ratio the report is not trusted and the scorer's own number is
    #: used instead (never the candidate's)
    soft_gate: float = 0.4
    case_budget_s: float = 120.0
    startup_timeout_s: float = 240.0
    request_timeout_s: float = 600.0


# --------------------------------------------------------------------------
# spec files
# --------------------------------------------------------------------------

_SPEC_PART = r"\s*([a-zA-Z_]+):\s*([a-zA-Z]+|[+-]?[0-9]+)\s*"


def parse_test_cases(path: Path) -> list[dict[str, Any]]:
    """Parse a popcorn-style spec file. Same grammar as the upstream eval.py,
    but parsed *here*, in the scorer, from the pristine benchmark tree."""
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case: dict[str, Any] = {}
        for part in line.split(";"):
            if not re.fullmatch(_SPEC_PART, part):
                raise ValueError(f"invalid test case {line!r}: {part!r}")
            key, value = re.match(_SPEC_PART, part).groups()
            try:
                case[key] = int(value)
            except ValueError:
                case[key] = value
        cases.append(case)
    if not cases:
        raise ValueError(f"no test cases in {path}")
    return cases


def _geometric_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    safe = [max(float(v), 1e-30) for v in values]
    return float(math.exp(sum(math.log(v) for v in safe) / len(safe)))


def _tail(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[-limit:]


class WorkerError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# worker handles
# --------------------------------------------------------------------------


class _Worker:
    """A child process addressed over a private pair of pipes."""

    def __init__(self, role: str, python: str, workdir: Path, timer: str,
                 env: dict[str, str], nonce: str) -> None:
        self.role = role
        self.python = python
        self.workdir = workdir
        self.timer = timer
        self.env = env
        self.nonce = nonce
        self.proc: subprocess.Popen | None = None
        self._buf = b""
        self._rfd = -1
        self._wfd = -1
        self.stdout_path = workdir / f"{role}.stdout"
        self.stderr_path = workdir / f"{role}.stderr"

    def start(self, timeout_s: float) -> dict[str, Any]:
        cmd_r, cmd_w = os.pipe()
        rsp_r, rsp_w = os.pipe()
        os.set_inheritable(cmd_r, True)
        os.set_inheritable(rsp_w, True)
        argv = [self.python, "_worker.py", "--role", self.role,
                "--cmd-fd", str(cmd_r), "--rsp-fd", str(rsp_w), "--timer", self.timer]
        self._out_fh = open(self.stdout_path, "wb")
        self._err_fh = open(self.stderr_path, "wb")
        self.proc = subprocess.Popen(
            argv, cwd=str(self.workdir), env=self.env,
            stdin=subprocess.DEVNULL, stdout=self._out_fh, stderr=self._err_fh,
            pass_fds=(cmd_r, rsp_w), preexec_fn=os.setsid,
        )
        os.close(cmd_r)
        os.close(rsp_w)
        self._wfd, self._rfd = cmd_w, rsp_r
        # The handshake carries the nonce over the pipe, so for the trusted
        # worker it never touches argv, the environment or the filesystem --
        # the candidate process does not exist yet when this runs.
        return self.request({"cmd": "hello", "nonce": self.nonce}, timeout_s)

    def request(self, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        if self.proc is None:
            raise WorkerError(f"{self.role} worker is not running")
        try:
            os.write(self._wfd, (json.dumps(payload) + "\n").encode("utf-8"))
        except OSError as exc:
            raise WorkerError(f"{self.role} worker closed its command pipe: {exc}") from exc
        deadline = time.time() + timeout_s
        while True:
            line = self._readline(deadline)
            try:
                obj = json.loads(line)
            except Exception:
                continue
            # Anything that does not carry the nonce is not from the worker we
            # handshook with (a candidate can find the pipe via /proc/<pid>/fd).
            if not isinstance(obj, dict) or obj.get("nonce") != self.nonce:
                continue
            if not obj.get("ok", False):
                raise WorkerError(
                    f"{self.role} worker failed on {payload.get('cmd')}: "
                    f"{obj.get('error')}\n{obj.get('traceback', '')}"
                )
            return obj

    def _readline(self, deadline: float) -> str:
        while True:
            idx = self._buf.find(b"\n")
            if idx >= 0:
                line, self._buf = self._buf[:idx], self._buf[idx + 1:]
                return line.decode("utf-8", "replace")
            remaining = deadline - time.time()
            if remaining <= 0:
                self.kill()
                raise WorkerError(f"{self.role} worker timed out")
            ready, _, _ = select.select([self._rfd], [], [], min(remaining, 5.0))
            if not ready:
                if self.proc is not None and self.proc.poll() is not None:
                    raise WorkerError(
                        f"{self.role} worker exited with code {self.proc.returncode} "
                        f"before answering; stderr: {_tail(self.read_stderr(), 1500)}"
                    )
                continue
            chunk = os.read(self._rfd, 65536)
            if not chunk:
                rc = self.proc.poll() if self.proc else None
                raise WorkerError(
                    f"{self.role} worker closed its response pipe (returncode={rc}); "
                    f"stderr: {_tail(self.read_stderr(), 1500)}"
                )
            self._buf += chunk

    def read_stderr(self) -> str:
        try:
            return self.stderr_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    def read_stdout(self) -> str:
        try:
            return self.stdout_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    def close(self, timeout_s: float = 20.0) -> None:
        if self.proc is None:
            return
        try:
            os.write(self._wfd, (json.dumps({"cmd": "bye"}) + "\n").encode("utf-8"))
        except OSError:
            pass
        try:
            self.proc.wait(timeout=timeout_s)
        except Exception:
            self.kill()
        self._cleanup_fds()

    def pause(self) -> None:
        """Stop this worker's process group.

        Nothing that belongs to the scorer may compete for CPU with the process
        being timed. On a 128-core box each torch process keeps a thread pool of
        that size, and an idle worker's pool still spins: leaving the trusted
        worker runnable during a timed batch inflated the measured per-call cost
        of the CPU stand-in kernel by ~5x. Timing measures the candidate, so the
        other worker is suspended for the duration.
        """
        if self.proc is None:
            return
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGSTOP)
        except Exception:
            pass

    def resume(self) -> None:
        if self.proc is None:
            return
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGCONT)
        except Exception:
            pass

    def kill(self) -> None:
        if self.proc is None:
            return
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        try:
            self.proc.wait(timeout=10)
        except Exception:
            pass
        self._cleanup_fds()

    def _cleanup_fds(self) -> None:
        for fd in (self._wfd, self._rfd):
            try:
                if fd >= 0:
                    os.close(fd)
            except OSError:
                pass
        self._wfd = self._rfd = -1
        for fh in (getattr(self, "_out_fh", None), getattr(self, "_err_fh", None)):
            try:
                if fh is not None:
                    fh.close()
            except Exception:
                pass
        self.proc = None


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------


def _build_env(cfg: KernelTaskConfig, role: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Deliberately NOT set here: OMP_WAIT_POLICY. Making the idle worker's
    # threads sleep instead of spin looks like the right way to keep the two
    # processes from competing, and it is not: measured on the CPU stand-in,
    # OMP_WAIT_POLICY=PASSIVE alone slowed the kernel under test from 182us to
    # 1056us (5.8x), because every parallel region then pays a thread wake-up.
    # Contention is handled by suspending the other worker outright while a
    # batch is timed (see _Worker.pause).
    # POPCORN_FD is what the old design handed the candidate: an inherited,
    # writable fd whose contents were parsed straight into the score. Nothing
    # reads it any more, but it must not be inherited either.
    env.pop("POPCORN_FD", None)
    env.pop("POPCORN_SEED", None)
    if role == "candidate":
        # Do not hand the candidate a pointer to the pristine benchmark tree.
        # (It can still reach it via /proc/<ppid>/cwd -- see the module
        # docstring -- but there is no reason to make it a one-liner.)
        env.pop("FRONTIER_ENGINEERING_ROOT", None)
    return env


def _stage_worker_dirs(cfg: KernelTaskConfig, work_dir: Path, program_path: Path,
                       shared_dir: Path) -> tuple[Path, Path]:
    baseline_src = cfg.benchmark_dir / "baseline"
    adapter_src = cfg.benchmark_dir / "frontier_eval" / "task_adapter.py"
    worker_src = shared_dir / "kernel_worker.py"

    dirs = {}
    for role in ("trusted", "candidate"):
        root = work_dir / role
        (root / "baseline").mkdir(parents=True)
        for name in cfg.baseline_modules:
            shutil.copy2(baseline_src / name, root / "baseline" / name)
        shutil.copy2(adapter_src, root / "task_adapter.py")
        shutil.copy2(worker_src, root / "_worker.py")
        dirs[role] = root
    # Only the candidate dir gets submission.py.
    shutil.copy2(program_path, dirs["candidate"] / "baseline" / "submission.py")
    return dirs["trusted"], dirs["candidate"]


def _alphas(rng: random.Random, scale: float, count: int) -> list[float]:
    seen: set[float] = set()
    out: list[float] = []
    while len(out) < count:
        value = round(rng.uniform(-scale, scale), 6)
        if value in seen or value == 0.0:
            continue
        seen.add(value)
        out.append(value)
    return out


def evaluate_kernel_task(
    cfg: KernelTaskConfig,
    program_path: str | Path,
    *,
    kernel_python: str,
    deadline_s: float,
    shared_dir: Path,
) -> tuple[dict[str, float], dict[str, Any]]:
    start = time.time()
    program_path = Path(program_path).expanduser().resolve()
    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
        "benchmark_count": 0.0,
        "geom_mean_ns": 0.0,
    }
    artifacts: dict[str, Any] = {
        "isolation": (
            "candidate runs in its own process and returns only output tensors "
            "and durations; correctness is decided by a separate trusted process "
            "and the score is computed by the evaluator"
        ),
        "interface_contract": (
            f"Candidate must define custom_kernel(data) for {cfg.task_name}. "
            "It is imported in a dedicated subprocess; the evaluator supplies the "
            "inputs, verifies every output against its own reference "
            "implementation, and times every call with its own clock."
        ),
    }

    spec_path = cfg.benchmark_dir / cfg.bench_spec_rel
    try:
        cases = parse_test_cases(spec_path)
    except Exception as exc:
        artifacts["error_message"] = f"cannot read benchmark spec {spec_path}: {exc}"
        metrics["runtime_s"] = time.time() - start
        return metrics, artifacts

    tmp_root = os.environ.get("FRONTIER_EVAL_KERNEL_TMPDIR") or None
    work_dir = Path(tempfile.mkdtemp(prefix=f"fe_kernel_{cfg.task_name}_", dir=tmp_root)).resolve()
    rng = random.Random()
    nonce_trusted = os.urandom(16).hex()
    nonce_candidate = os.urandom(16).hex()

    trusted: _Worker | None = None
    candidate: _Worker | None = None
    per_case: list[dict[str, Any]] = []
    try:
        trusted_dir, candidate_dir = _stage_worker_dirs(cfg, work_dir, program_path, shared_dir)
        stage = work_dir / "stage"
        stage.mkdir()

        trusted = _Worker("trusted", kernel_python, trusted_dir, cfg.timer,
                          _build_env(cfg, "trusted"), nonce_trusted)
        hello = trusted.start(min(cfg.startup_timeout_s, max(5.0, deadline_s - time.time())))
        artifacts["torch_version"] = hello.get("torch")
        artifacts["cuda_available"] = bool(hello.get("cuda"))
        artifacts["timer"] = hello.get("timer")

        allow_cpu = str(os.environ.get("FRONTIER_EVAL_KERNEL_ALLOW_CPU", "")).strip() == "1"
        if not hello.get("cuda") and not allow_cpu:
            artifacts["error_message"] = (
                "CUDA is unavailable in the kernel runtime. Ensure the benchmark runs "
                "on a GPU node (set FRONTIER_EVAL_KERNEL_ALLOW_CPU=1 only for harness tests)."
            )
            metrics["runtime_s"] = time.time() - start
            return metrics, artifacts

        # The trusted worker has finished every import it will ever do before
        # the candidate process exists (candidate_sandbox invariant 1).
        candidate = _Worker("candidate", kernel_python, candidate_dir, cfg.timer,
                            _build_env(cfg, "candidate"), nonce_candidate)
        candidate.start(min(cfg.startup_timeout_s, max(5.0, deadline_s - time.time())))

        for index, args in enumerate(cases):
            if time.time() > deadline_s:
                artifacts["error_message"] = "evaluation deadline reached"
                metrics["timeout"] = 1.0
                break
            per_case.append(_run_case(cfg, trusted, candidate, stage, index, args, rng, deadline_s))

        metrics, artifacts = _score(cfg, metrics, artifacts, per_case)
    except WorkerError as exc:
        artifacts["error_message"] = str(exc)[:4000]
        metrics["valid"] = 0.0
        metrics["combined_score"] = 0.0
    except Exception as exc:  # noqa: BLE001
        artifacts["error_message"] = f"{type(exc).__name__}: {exc}"
        metrics["valid"] = 0.0
        metrics["combined_score"] = 0.0
    finally:
        for worker in (candidate, trusted):
            if worker is None:
                continue
            try:
                artifacts[f"{worker.role}_stderr"] = _tail(worker.read_stderr())
                stdout = worker.read_stdout()
                if stdout.strip():
                    artifacts[f"{worker.role}_stdout"] = _tail(stdout)
                worker.close()
            except Exception:
                worker.kill()
        shutil.rmtree(work_dir, ignore_errors=True)

    metrics["runtime_s"] = float(time.time() - start)
    return metrics, artifacts


def _run_case(cfg: KernelTaskConfig, trusted: _Worker, candidate: _Worker, stage: Path,
              index: int, args: dict[str, Any], rng: random.Random,
              deadline_s: float) -> dict[str, Any]:
    case_dir = stage / f"case{index}"
    case_dir.mkdir(parents=True, exist_ok=True)
    base_path = case_dir / "input.pt"
    result: dict[str, Any] = {"index": index, "spec": args, "ok": False,
                              "durations_ns": [], "wall_ns": 0.0, "errors": []}
    fingerprints: dict[int, list[float]] = {}
    seed = int(args.get("seed", 0))
    case_start = time.time()
    try:
        info = trusted.request(
            {"cmd": "prepare", "case": index, "args": args, "seed": seed,
             "path": str(base_path)},
            min(cfg.request_timeout_s, max(5.0, deadline_s - time.time())),
        )
        result["input_bytes"] = info.get("bytes", 0)
        candidate.request({"cmd": "load", "case": index, "path": str(base_path)},
                          min(cfg.request_timeout_s, max(5.0, deadline_s - time.time())))
        candidate.request(
            {"cmd": "warmup", "case": index, "seconds": cfg.warmup_s, "min_iters": 3,
             "alpha": round(rng.uniform(-cfg.alpha_scale, cfg.alpha_scale), 6)},
            min(cfg.request_timeout_s, max(5.0, deadline_s - time.time())),
        )

        # Retained outputs per batch are bounded by their own size: an output is
        # kept only until it has been verified, then deleted.
        out_bytes = max(1, int(result.get("input_bytes") or 1))
        batch_reps = max(1, min(cfg.max_batch_reps, cfg.output_bytes_budget // out_bytes))
        done = 0
        while done < cfg.target_samples:
            if time.time() > deadline_s:
                break
            # The per-case budget may cut the sample count short, but never
            # below min_samples: one timing sample is not a measurement.
            if done >= cfg.min_samples and (time.time() - case_start) > cfg.case_budget_s:
                break
            reps = int(min(batch_reps, cfg.target_samples - done))
            alphas = _alphas(rng, cfg.alpha_scale, reps)
            paths = [str(case_dir / f"out_{done + j}.pt") for j in range(reps)]

            trusted.pause()
            try:
                wall0 = time.perf_counter_ns()
                run = candidate.request(
                    {"cmd": "run", "case": index, "alphas": alphas},
                    min(cfg.request_timeout_s, max(5.0, deadline_s - time.time())),
                )
                wall_ns = float(time.perf_counter_ns() - wall0)
            finally:
                trusted.resume()

            durations = [float(d) for d in run.get("durations_ns", [])]
            if len(durations) != reps:
                result["errors"].append(
                    f"candidate reported {len(durations)} durations for {reps} reps")
                return result
            flush0 = time.perf_counter_ns()
            candidate.request({"cmd": "flush", "case": index, "paths": paths},
                              min(cfg.request_timeout_s, max(5.0, deadline_s - time.time())))
            result["flush_wall_ns"] = result.get("flush_wall_ns", 0.0) + float(
                time.perf_counter_ns() - flush0)
            written = sum(os.path.getsize(p) for p in paths if os.path.exists(p))
            if written > 0:
                # An output can be larger than the input it came from (MLA
                # returns the whole KV buffer), so re-size the batch once the
                # real cost is known instead of guessing from the input.
                per_output = max(1, written // len(paths))
                batch_reps = max(1, min(cfg.max_batch_reps,
                                        cfg.output_bytes_budget // per_output))
            verdict = trusted.request(
                {"cmd": "verify", "case": index,
                 "outputs": [{"round": done + j, "alpha": alphas[j], "path": paths[j]}
                             for j in range(reps)]},
                min(cfg.request_timeout_s, max(5.0, deadline_s - time.time())),
            )
            for item in verdict["results"]:
                if not item["ok"]:
                    result["errors"].append(f"case {index} rep {item['round']}: {item['error']}")
                    continue
                # Correct-looking is not enough: each rep ran on a different
                # input, so two reps that produced the same numbers mean the
                # kernel replayed a cached answer (or ignored its input).
                fingerprint = [float(v) for v in item.get("fingerprint", [])]
                twin = _matching_round(fingerprints, fingerprint)
                if twin is not None:
                    result["errors"].append(
                        f"case {index} rep {item['round']}: identical output to rep {twin} "
                        f"although the two reps ran on different inputs "
                        f"(cached or input-independent result)"
                    )
                fingerprints[int(item["round"])] = fingerprint
            for path in paths:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            if result["errors"]:
                return result

            result["durations_ns"].extend(durations)
            result["wall_ns"] += wall_ns
            done += reps

        result["ok"] = bool(result["durations_ns"]) and not result["errors"]
        return result
    finally:
        try:
            trusted.request({"cmd": "release", "case": index}, 120.0)
        except Exception:
            pass
        shutil.rmtree(case_dir, ignore_errors=True)


def _matching_round(seen: dict[int, list[float]], fingerprint: list[float]) -> int | None:
    if not fingerprint:
        return None
    for round_index, other in seen.items():
        if len(other) != len(fingerprint):
            continue
        if all(_close(a, b) for a, b in zip(other, fingerprint)):
            return round_index
    return None


def _close(a: float, b: float) -> bool:
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    return scale > 0 and abs(a - b) <= 1e-9 * scale


def _score(cfg: KernelTaskConfig, metrics: dict[str, float], artifacts: dict[str, Any],
           per_case: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, Any]]:
    if not per_case:
        artifacts.setdefault("error_message", "no benchmark case produced a result")
        return metrics, artifacts

    failures = [msg for case in per_case for msg in case["errors"]]
    metrics["benchmark_count"] = float(len(per_case))
    metrics["correctness_failures"] = float(len(failures))
    if failures:
        artifacts["failure_summary"] = "\n".join(failures[:8])

    if any(not case["ok"] for case in per_case):
        metrics["valid"] = 0.0
        metrics["combined_score"] = 0.0
        artifacts.setdefault("error_message", failures[0] if failures
                             else "a benchmark case produced no timed reps")
        return metrics, artifacts

    reported_means, parent_means, ratios, scored = [], [], [], []
    forged = False
    inconsistent = False
    for case in per_case:
        reported = sum(case["durations_ns"]) / len(case["durations_ns"])
        # wall_ns covers the whole batch round trip, so wall/reps is an upper
        # bound on the true per-rep cost that the candidate cannot lower.
        parent = case["wall_ns"] / len(case["durations_ns"])
        ratio = reported / parent if parent > 0 else 0.0
        reported_means.append(reported)
        parent_means.append(parent)
        ratios.append(ratio)
        if ratio < cfg.hard_gate:
            forged = True
            scored.append(parent)
        elif ratio < cfg.soft_gate:
            inconsistent = True
            scored.append(parent)
        else:
            scored.append(reported)

    metrics["total_reps"] = float(sum(len(c["durations_ns"]) for c in per_case))
    # Raw samples, so an auditor can see the distribution the score came from
    # rather than only its geometric mean.
    artifacts["case_durations_ns"] = json.dumps(
        {str(case["index"]): [round(d, 1) for d in case["durations_ns"][:64]]
         for case in per_case})
    flush_ratio = 0.0
    for case in per_case:
        run_per_rep = case["wall_ns"] / max(1, len(case["durations_ns"]))
        flush_per_rep = case.get("flush_wall_ns", 0.0) / max(1, len(case["durations_ns"]))
        if run_per_rep > 0:
            flush_ratio = max(flush_ratio, flush_per_rep / run_per_rep)
    # Observability, not a gate: a candidate can move work out of the timed
    # window into output serialization, and this is what that would look like.
    metrics["flush_to_run_ratio"] = float(flush_ratio)
    metrics["geom_mean_ns"] = _geometric_mean(scored)
    metrics["reported_geom_mean_ns"] = _geometric_mean(reported_means)
    metrics["wall_geom_mean_ns"] = _geometric_mean(parent_means)
    metrics["timing_ratio_min"] = float(min(ratios)) if ratios else 0.0
    metrics["best_case_ns"] = float(min(scored))
    metrics["worst_case_ns"] = float(max(scored))
    metrics["timing_forged"] = 1.0 if forged else 0.0
    metrics["timing_inconsistent"] = 1.0 if inconsistent else 0.0

    if forged:
        # Reporting a latency tens of times below the scorer's own wall-clock
        # bound is not measurement noise.
        metrics["valid"] = 0.0
        metrics["combined_score"] = 0.0
        artifacts["error_message"] = (
            f"reported latency is physically impossible: min(reported/wall-bound) = "
            f"{min(ratios):.3g} < {cfg.hard_gate}. The candidate's self-reported timings "
            f"were rejected."
        )
        return metrics, artifacts

    if inconsistent:
        artifacts["timing_warning"] = (
            f"reported latency below {cfg.soft_gate} of the evaluator's wall-clock bound "
            f"(min ratio {min(ratios):.3g}); scored with the evaluator's own measurement."
        )

    metrics["valid"] = 1.0
    gmean = metrics["geom_mean_ns"]
    metrics["combined_score"] = float(1e9 / gmean) if gmean > 0 else 0.0
    return metrics, artifacts
