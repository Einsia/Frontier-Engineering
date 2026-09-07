"""Hardened scorer for benchmarks/Cryptographic/{AES-128,SHA-256,SHA3-256}.

Why this file exists
--------------------
The three Cryptographic benchmarks used to be scored like this:

    compile candidate            -> verification/custom_aes
    compile verification/validate.cpp
    run validate                 (which runs custom_aes; candidate code executes)
    compile verification/evaluate.cpp     <-- AFTER the candidate has run
    run evaluate                 (which runs custom_aes 550x, ignoring its output)
    combined_score = geometric mean of the "Throughput : N Mbps" lines
                     scraped from evaluate's stdout

Three things were wrong with that, and each one was independently sufficient to
make ``combined_score`` a number the candidate chose rather than earned:

1. **evaluate.cpp was compiled after the candidate had already run.** The
   candidate binary runs with its cwd set to the sandbox's ``verification``
   directory, which is exactly where ``evaluate.cpp`` sits waiting to be built.
   A candidate that passed the correctness check and then overwrote that file
   with a program printing ``Throughput : 999999999.00 Mbps`` was scored at
   999999999. Measured, not hypothesised: 1.0e9 versus an honest 21.0.

2. **Nothing checked the candidate's output during the timed phase.**
   ``evaluate.cpp`` only looked at the exit status; for SHA-256 and SHA3-256 it
   sent the digest to ``/dev/null`` outright. The two phases are trivially
   distinguishable (the correctness phase feeds ten short vectors, the timed
   phase feeds exactly 1000 or 1000000 bytes), so a candidate could be honest
   while being checked and return instantly while being timed. Measured: 3.2x
   to 4.0x score inflation with a five-line patch to the shipped baseline.

3. **The correctness verdict was a regex over text the candidate could write
   into.** ``validate.cpp`` echoes the candidate's own output back to stdout,
   and SHA3-256's ``validate.cpp`` additionally ``return 0``s no matter how many
   vectors failed -- so its whole gate was ``re.search`` over a stream the
   candidate contributes to.

What this file does instead
---------------------------
The candidate is a *separate program that answers questions*, and nothing else:

* Everything the scorer needs is imported before any candidate code exists:
  ``crypto_reference`` (self-tested against FIPS-197 / SP 800-38A / FIPS-180-4 /
  FIPS-202 vectors at import) is resident before the compiler is even invoked.
* The candidate is compiled **once**, before it has ever executed. Nothing is
  compiled afterwards, so there is no build input left for it to rewrite.
* No ``verification/*.cpp`` is used at scoring time at all. The scorer generates
  the inputs, holds the plaintext/message bodies in its own memory, computes the
  expected ciphertext/digest itself, spawns the candidate, and times it.
* **Every timed iteration is checked**, against an expectation derived from
  scorer-owned bytes, with the output file removed first so a stale answer
  cannot be replayed. The check happens outside the timing window.
* Each iteration gets a freshly randomised input of the *same length* (a new
  key/IV for AES, a new 64-byte prefix for the hash tasks), so the answer to
  iteration *i* is not the answer to iteration *i-1*.
* ``combined_score`` is computed here from elapsed seconds this process
  measured. No number is ever parsed out of anything the candidate can print.

Preserved on purpose (so honest scores stay comparable)
------------------------------------------------------
Stream sizes (1000 / 1000000 bytes), iteration counts (500 / 50), the
``Mbps = bits/1e6/seconds`` formula, the geometric mean over the two cases, and
the ``/bin/sh -c "./custom_x ..."`` spawn -- the 1000-byte case is dominated by
process startup, and dropping the shell hop alone would have more than doubled
the reported throughput. Measured on the audit host: C++ ``system()`` 1.111s for
500 spawns versus ``subprocess.run(["/bin/sh","-c",...])`` 1.126s, i.e. inside
the ~3% run-to-run noise, while a direct ``exec`` without the shell was 0.513s.

Because the 1000-byte case measures process startup and not cryptography
(~2.3 ms of spawn against ~2 us of hashing), scorer-side overhead in the spawn
path reads as a slower candidate. Three such traps were found and removed by
measuring an honest baseline before and after; see ``_spawn`` and
``_Handler.write_seed`` for the numbers. Anyone touching the spawn path should
re-run that comparison rather than reason about it.

Measured effect of the whole change on the shipped baselines (medians of 9
interleaved runs each, so machine drift hits both arms equally):

    AES-128    20.939 -> 20.632   -1.5%   (1 MB case  +0.1%)
    SHA-256    35.300 -> 34.277   -2.9%   (1 MB case  -0.3%)
    SHA3-256   67.039 -> 74.103  +10.5%   (1 MB case  +3.7%)

SHA3-256 moves because the old harness ran ``./custom_sha3 f > /dev/null`` and
the digest now comes back on a pipe instead; the shell redirect it no longer
performs was worth ~20% of that task's spawn-bound case (3.738 -> 4.495 Mbps in
isolation). That overhead was the scorer's, not the candidate's, so the number
is not being restored artificially.

Known residual risks
--------------------
* **Same-uid observability.** The candidate runs as the same user as the scorer,
  so ``/proc/<ppid>/`` is readable and ptrace_scope is 0 on the audit host. It
  cannot change the score (the score never leaves this process), but it can see
  where this process lives. Closing that needs
  ``task.runtime.isolation_mode=docker`` or a uid/mount namespace.
* **Memoising across iterations.** Per-iteration input variation forces fresh
  work for each *distinct* input, but when the AES reference falls back to the
  pure-Python backend the 1000000-byte case reuses a small cycle of variants
  (see ``_variant_count``) because computing 50 distinct 1 MB keystreams in pure
  Python would cost ~90s. In that configuration a candidate that caches
  ciphertext keyed by input content still gets a speed-up. The active backend is
  reported as ``aes_reference_backend`` / ``throughput_variants_*`` so a
  suspicious score can be checked. With ``cryptography`` installed (the normal
  case) every iteration is distinct and this does not apply.
* **Borrowing a crypto library.** The compile line has no ``-lcrypto``, but a
  candidate could ``dlopen`` libcrypto and let OpenSSL do the work. That is a
  task-intent question, not a score-integrity one -- the output would be
  genuinely correct -- so it is reported (``candidate_dynamic_libs``) rather
  than failed.
* **A runaway candidate can leak a process.** The timed loop keeps CPython's
  vfork path (see ``_spawn``), so the watchdog kills by pid plus a ``/proc``
  child sweep rather than by process group. A process that survives that has no
  channel to the score and belongs to an already-invalid run, but it can
  outlive the evaluation.
* **Unbounded stdout is a scorer-memory problem, not a scoring one.** The two
  hash tasks return their digest on a pipe that this process drains, so a
  candidate that writes without bound can make the scorer allocate until the
  per-invocation deadline. It cannot make the digest right.
* **The scoring code still lives next to the candidate's workspace.** This
  module is deliberately under ``benchmarks/_shared/`` rather than in the task's
  ``frontier_eval/`` directory, so a ``copy_files.txt`` of ``.`` cannot drag it
  into the agent sandbox. The task-local ``evaluator_impl.py`` is a shim that
  loads this file from the repo root.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import crypto_reference as reference

__all__ = ["evaluate", "ALGORITHMS"]


# The benchmark shape, unchanged from verification/evaluate.cpp.
SIZE_8KBITS = 1000
SIZE_8MBITS = 1000000
ITERATIONS_8KBITS = 500
ITERATIONS_8MBITS = 50
CASE_8KBITS = "8 Kbits stream"
CASE_8MBITS = "8 Mbits stream"

CORRECTNESS_VECTORS = 10

#: Bytes of each throughput input that are re-randomised per iteration. Small
#: enough that the rewrite is cheap and the page cache stays warm, large enough
#: that the answer changes completely.
PERTURB_BYTES = 64


def _scorer_fingerprint() -> str:
    """Hash the two files that decide the score.

    Taken once at import -- before any candidate binary exists -- and checked
    again before a valid score is emitted. A candidate runs as the same user as
    the scorer and can reach this directory through
    ``FRONTIER_ENGINEERING_ROOT`` or ``/proc/<ppid>/cwd``; it cannot affect the
    run that is already in memory, but it could poison every later one. We
    cannot stop that write from in here, but we can refuse to report a score
    from the run that made it, and say so loudly.
    """
    h = hashlib.sha256()
    for name in ("crypto_eval.py", "crypto_reference.py"):
        target = Path(__file__).resolve().with_name(name)
        h.update(name.encode("utf-8"))
        try:
            h.update(target.read_bytes())
        except OSError:
            h.update(b"__MISSING__")
    return h.hexdigest()


def _find_repo_root(start: Path) -> Path:
    env_root = os.environ.get("FRONTIER_ENGINEERING_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    for parent in [start, *start.parents]:
        if (parent / "frontier_eval").is_dir() and (parent / "benchmarks").is_dir():
            return parent
    return Path.cwd().resolve()


def _tail(text: str, limit: int = 8000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _truncate_middle(text: str, limit: int = 200_000) -> str:
    if len(text) <= limit:
        return text
    keep = max(0, (limit - 128) // 2)
    omitted = len(text) - (2 * keep)
    return text[:keep] + f"\n\n[... truncated {omitted} chars ...]\n\n" + text[-keep:]


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


#: Captured at import, i.e. before any candidate exists on disk.
_SCORER_FINGERPRINT_AT_IMPORT = _scorer_fingerprint()


def _safe_metric_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower() or "case"


def _remaining(deadline_s: float) -> float:
    return max(1.0, float(deadline_s - time.time()))


# ---------------------------------------------------------------------------
# Per-algorithm I/O contracts
#
# These reproduce exactly what verification/validate.cpp and
# verification/evaluate.cpp asked of the candidate, so an honest program written
# against the shipped task description keeps working unchanged.
# ---------------------------------------------------------------------------


@dataclass
class _Body:
    """The scorer-owned input for one candidate invocation.

    ``payload`` never round-trips through the filesystem: it is written out for
    the candidate to read and kept here for computing the expected answer, so a
    candidate that rewrites its own input file changes only what it reads, not
    what it is graded against.
    """

    payload: Any
    nbytes: int


class _Handler:
    binary_name: str = ""
    #: Shell command, run via /bin/sh -c with cwd=run_dir, matching the
    #: std::system() call the original C++ benchmark used.
    command: str = ""
    #: File the candidate is contracted to write its answer to; empty when the
    #: answer arrives on stdout instead.
    output_file: str = ""
    #: Read the answer off a pipe rather than out of a file. This is what
    #: validate.cpp did (popen), and it matters for the score: routing the
    #: digest to a real file instead cost ~15% of the 1000-byte case's
    #: throughput, which is dominated by process startup. Measured on the audit
    #: host, 500 spawns: `> /dev/null` 3.615 Mbps, pipe 3.426, `> test_out.txt`
    #: 3.020.
    capture_stdout: bool = False

    def new_body(self, rng: "secrets.SystemRandom", nbytes: int) -> _Body:
        raise NotImplementedError

    def new_seed(self, rng: "secrets.SystemRandom") -> Any:
        """A small, scorer-generated value that changes the whole answer."""
        raise NotImplementedError

    def apply_seed(self, body: _Body, seed: Any) -> _Body:
        """``body`` with ``seed`` mixed in. Same length, completely new answer."""
        raise NotImplementedError

    def write_input(self, run_dir: Path, body: _Body) -> None:
        """Write the whole input file. Used once per case, and per vector."""
        raise NotImplementedError

    def write_seed(self, run_dir: Path, seed: Any) -> None:
        """Rewrite only the seed-dependent prefix of an already-staged input.

        The timed loop must not rebuild the whole input file: re-encoding a
        megabyte of plaintext to hex and re-writing it every iteration churned
        several megabytes of allocations and tmpfs pages per round and made the
        candidate's own spawn measurably slower -- 114 ms against 64 ms for the
        identical binary and identical file contents on the audit host, i.e. a
        30% dent in a score that is supposed to be about the candidate. The
        seed sits at a fixed-width offset 0 in every format used here, so this
        is a 64-66 byte pwrite.
        """
        raise NotImplementedError

    def expected(self, body: _Body) -> str:
        raise NotImplementedError

    def read_output(self, run_dir: Path, proc: subprocess.CompletedProcess) -> str:
        if self.capture_stdout:
            raw = proc.stdout or b""
            source = "stdout"
        else:
            path = run_dir / self.output_file
            source = self.output_file
            try:
                raw = path.read_bytes()
            except OSError as exc:
                raise _CandidateError(f"could not read {source}: {exc}") from exc
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _CandidateError(f"{source} is not valid UTF-8: {exc}") from exc
        # Same normalisation validate.cpp applied to the candidate's answer.
        return text.rstrip(" \n\r\t")

    def clear_output(self, run_dir: Path) -> None:
        """Remove a stale answer so a candidate cannot pass by not writing one."""
        if not self.output_file:
            return
        try:
            (run_dir / self.output_file).unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise _CandidateError(f"could not clear {self.output_file}: {exc}") from exc


class _CandidateError(Exception):
    """The candidate produced something the scorer will not accept."""


class _AesHandler(_Handler):
    """AES-128-CTR: triples of hex lines in, one hex ciphertext line each out."""

    binary_name = "custom_aes"
    command = "./custom_aes"
    output_file = "test_out_custom.txt"
    input_file = "test_in.txt"

    def new_body(self, rng, nbytes):
        return _Body(
            payload=[(bytes(rng.randbytes(16)), bytes(rng.randbytes(16)), bytes(rng.randbytes(nbytes)))],
            nbytes=nbytes,
        )

    def batch(self, triples: list[tuple[bytes, bytes, bytes]]) -> _Body:
        return _Body(payload=triples, nbytes=sum(len(pt) for _, _, pt in triples))

    def new_seed(self, rng):
        return (bytes(rng.randbytes(16)), bytes(rng.randbytes(16)))

    def apply_seed(self, body, seed):
        # Same plaintext, fresh key and IV: the input file keeps its length, the
        # rewrite is 66 bytes, and the whole keystream is different. The
        # plaintext object is shared rather than copied.
        key, iv = seed
        return _Body(payload=[(key, iv, pt) for _, _, pt in body.payload], nbytes=body.nbytes)

    def write_input(self, run_dir, body):
        lines = []
        for key, iv, pt in body.payload:
            lines.append(key.hex())
            lines.append(iv.hex())
            lines.append(pt.hex())
        (run_dir / self.input_file).write_bytes(("\n".join(lines) + "\n").encode("ascii"))

    def write_seed(self, run_dir, seed):
        # Layout is "<32 hex key>\n<32 hex iv>\n<plaintext hex>\n", so the key
        # and IV are exactly the first 66 bytes and the plaintext never moves.
        key, iv = seed
        prefix = (key.hex() + "\n" + iv.hex() + "\n").encode("ascii")
        assert len(prefix) == 66
        with open(run_dir / self.input_file, "r+b") as handle:
            handle.write(prefix)

    def expected(self, body):
        return "\n".join(
            reference.aes128_ctr_encrypt(key, iv, pt).hex() for key, iv, pt in body.payload
        )


class _StdinHashHandler(_Handler):
    """SHA-256: message on stdin, 64 hex chars on stdout."""

    binary_name = "custom_sha"
    command = "./custom_sha < test_in.bin"
    capture_stdout = True
    input_file = "test_in.bin"

    def new_body(self, rng, nbytes):
        return _Body(payload=bytes(rng.randbytes(nbytes)), nbytes=nbytes)

    def literal(self, data: bytes) -> _Body:
        return _Body(payload=data, nbytes=len(data))

    def new_seed(self, rng):
        return bytes(rng.randbytes(PERTURB_BYTES))

    def apply_seed(self, body, seed):
        data = body.payload
        n = min(len(seed), len(data))
        if n == 0:
            return body
        return _Body(payload=seed[:n] + data[n:], nbytes=body.nbytes)

    def write_input(self, run_dir, body):
        (run_dir / self.input_file).write_bytes(body.payload)

    def write_seed(self, run_dir, seed):
        if not seed:
            return
        with open(run_dir / self.input_file, "r+b") as handle:
            handle.write(seed)

    def expected(self, body):
        return reference.sha256_hex(body.payload)


class _ArgvHashHandler(_StdinHashHandler):
    """SHA3-256: file path in argv[1], 64 hex chars on stdout."""

    binary_name = "custom_sha3"
    command = "./custom_sha3 test_in.bin"
    capture_stdout = True
    input_file = "test_in.bin"

    def expected(self, body):
        return reference.sha3_256_hex(body.payload)


ALGORITHMS: dict[str, Callable[[], _Handler]] = {
    "AES-128": _AesHandler,
    "SHA-256": _StdinHashHandler,
    "SHA3-256": _ArgvHashHandler,
}


# ---------------------------------------------------------------------------
# Running the candidate
# ---------------------------------------------------------------------------


def _descendants(pid: int) -> list[int]:
    """Best-effort child PIDs of ``pid`` from /proc, deepest last."""
    found: list[int] = []
    stack = [pid]
    while stack:
        current = stack.pop()
        try:
            tasks = list((Path("/proc") / str(current) / "task").iterdir())
        except OSError:
            continue
        for task in tasks:
            try:
                kids = (task / "children").read_text().split()
            except OSError:
                continue
            for kid in kids:
                try:
                    kid_pid = int(kid)
                except ValueError:
                    continue
                found.append(kid_pid)
                stack.append(kid_pid)
    return found


def _spawn(
    handler: _Handler,
    run_dir: Path,
    timeout_s: float,
    *,
    capture_stderr: bool,
    new_session: bool = False,
) -> subprocess.CompletedProcess:
    """Spawn the candidate the way ``std::system()`` did: fork, /bin/sh -c, exec.

    Two things here are deliberate and both were found by comparing an honest
    candidate's score before and against after the hardening. Each cost about a
    fifth of the 1000-byte case, which is process-startup bound (~2.3 ms per
    spawn against ~2 us of actual hashing), so a scorer-side inefficiency there
    reads as a slower candidate.

    * **Not** ``subprocess.run(..., timeout=...)``. Passing a timeout makes
      ``communicate`` wait by *polling* waitpid with a backoff capped at 50 ms
      rather than blocking in it. Measured on the audit host with the identical
      binary and input: 113.7 ms per 1 MB invocation with the timeout against
      64.0 ms without. The deadline is enforced by a watchdog instead.
    * **Not** ``start_new_session=True``. It makes CPython fall back from vfork
      to fork, and forking a ~50 MB scorer costs ~0.47 ms of page-table copying
      per spawn: 2.90 ms against 2.44 ms. It is used only for the ten untimed
      correctness invocations.

    The cost of not having a session of our own is that a runaway candidate is
    killed by pid rather than by process group. ``sh -c '<single command>'``
    execs in place on dash and bash, so the pid we hold is normally the
    candidate itself; ``_descendants`` sweeps up the case where it is not. A
    process that still escapes is a leak, not a score: it has no channel to the
    number, and the run it belonged to is already invalid.

    ``capture_stderr`` is on for the correctness invocations, where the message
    is worth having, and off for the 550 timed ones, where a candidate writing
    without bound to a pipe the scorer must drain is a way to exhaust the
    scorer's memory rather than to earn a score.
    """
    proc = subprocess.Popen(
        ["/bin/sh", "-c", handler.command],
        cwd=str(run_dir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if handler.capture_stdout else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture_stderr else subprocess.DEVNULL,
        start_new_session=new_session,
    )

    expired: list[bool] = []

    def _kill() -> None:
        expired.append(True)
        if new_session:
            try:
                os.killpg(proc.pid, 9)
                return
            except OSError:
                pass
        for pid in _descendants(proc.pid):
            try:
                os.kill(pid, 9)
            except OSError:
                pass
        try:
            proc.kill()
        except OSError:
            pass

    watchdog = threading.Timer(timeout_s, _kill)
    watchdog.daemon = True
    watchdog.start()
    try:
        stdout, stderr = proc.communicate()
    finally:
        watchdog.cancel()
    if expired:
        raise subprocess.TimeoutExpired(handler.command, timeout_s, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(
        args=handler.command, returncode=proc.returncode, stdout=stdout, stderr=stderr
    )


def _run_once(
    handler: _Handler,
    run_dir: Path,
    body: _Body,
    timeout_s: float,
    *,
    capture_stderr: bool = False,
    seed: Any = None,
    new_session: bool = False,
) -> tuple[str, float]:
    """One checked invocation. Returns (candidate output, elapsed seconds).

    The timing window covers exactly the spawn, as ``std::system()`` did.
    Clearing the stale output and checking the answer both happen outside it.
    """
    handler.clear_output(run_dir)
    if seed is None:
        handler.write_input(run_dir, body)
    else:
        handler.write_seed(run_dir, seed)
    start = time.perf_counter()
    proc = _spawn(handler, run_dir, timeout_s, capture_stderr=capture_stderr, new_session=new_session)
    elapsed = time.perf_counter() - start
    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", "replace").strip()
        raise _CandidateError(f"candidate exited {proc.returncode}: {_tail(stderr, 500)}")
    return handler.read_output(run_dir, proc), elapsed


def _variant_count(algorithm: str, size_bytes: int, iterations: int) -> int:
    """How many distinct inputs the timed loop cycles through.

    Normally one per iteration. The exception is AES on the 1 MB case with the
    pure-Python fallback reference, where 50 distinct keystreams would cost
    ~90 seconds of scorer time; there we cycle a small number instead and say so
    in the metrics. See "Known residual risks" in the module docstring.
    """
    if algorithm != "AES-128" or size_bytes < SIZE_8MBITS:
        return iterations
    if reference.aes_backend_name() != "pure-python":
        return iterations
    return 3


def _geometric_mean(values: list[float]) -> float:
    clipped = [max(float(v), 1e-30) for v in values]
    return float(math.exp(sum(math.log(v) for v in clipped) / len(clipped)))


def _dynamic_libs(binary: Path) -> str:
    try:
        proc = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, timeout=20)
    except Exception as exc:
        return f"ldd unavailable: {exc}"
    return _tail((proc.stdout or "") + (proc.stderr or ""), 4000)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _correctness_bodies(algorithm: str, handler: _Handler, rng) -> list[tuple[str, _Body]]:
    """Scorer-chosen vectors: published known answers first, then random ones.

    The published vectors matter because a candidate cannot pass them by
    accident or by agreeing with itself -- they are fixed by FIPS-197 /
    SP 800-38A / FIPS-180-4 / FIPS-202.
    """
    bodies: list[tuple[str, _Body]] = []
    if algorithm == "AES-128":
        assert isinstance(handler, _AesHandler)
        kat = (
            bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c"),
            bytes.fromhex("f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff"),
            bytes.fromhex(
                "6bc1bee22e409f96e93d7e117393172a"
                "ae2d8a571e03ac9c9eb76fac45af8e51"
                "30c81c46a35ce411e5fbc1191a0a52ef"
                "f69f2445df4f9b17ad2b417be66c3710"
            ),
        )
        triples = [kat]
        # Matches validate.cpp: plaintext lengths in [1, 100].
        for _ in range(CORRECTNESS_VECTORS - 1):
            n = rng.randrange(1, 101)
            triples.append(
                (bytes(rng.randbytes(16)), bytes(rng.randbytes(16)), bytes(rng.randbytes(n)))
            )
        # The contract is a batch: one file with every triple, one line out each.
        bodies.append(("batch of %d vectors" % len(triples), handler.batch(triples)))
        return bodies

    # SHA-256 / SHA3-256: one invocation per message.
    max_len = 2000 if algorithm == "SHA-256" else 5000
    literals = [b"", b"abc", b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"]
    for data in literals:
        bodies.append((f"known-answer {len(data)}B", handler.literal(data)))
    for _ in range(CORRECTNESS_VECTORS - len(literals)):
        bodies.append(("random", handler.new_body(rng, rng.randrange(0, max_len + 1))))
    return bodies


def _run_correctness(
    algorithm: str,
    handler: _Handler,
    run_dir: Path,
    rng,
    deadline_s: float,
) -> tuple[int, int, list[str], bool]:
    bodies = _correctness_bodies(algorithm, handler, rng)
    passed = 0
    notes: list[str] = []
    timed_out = False
    for label, body in bodies:
        expected = handler.expected(body)
        try:
            got, _ = _run_once(
                handler,
                run_dir,
                body,
                min(120.0, _remaining(deadline_s)),
                capture_stderr=True,
                new_session=True,
            )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            notes.append(f"[FAIL] {label}: timed out after {exc.timeout:g}s")
            continue
        except _CandidateError as exc:
            notes.append(f"[FAIL] {label}: {exc}")
            continue
        if got == expected:
            passed += 1
            notes.append(f"[PASS] {label}")
        else:
            notes.append(
                f"[FAIL] {label}: expected {expected[:80]}... got {got[:80]}..."
            )
    return passed, len(bodies), notes, timed_out


def _run_case(
    algorithm: str,
    handler: _Handler,
    run_dir: Path,
    rng,
    size_bytes: int,
    iterations: int,
    deadline_s: float,
) -> tuple[float, int]:
    """Time ``iterations`` checked invocations. Returns (Mbps, distinct inputs)."""
    base = handler.new_body(rng, size_bytes)
    variants = _variant_count(algorithm, size_bytes, iterations)
    seeds = [handler.new_seed(rng) for _ in range(variants)]
    # Expected answers are derived from bytes this process generated and are
    # recomputed per iteration; nothing is ever read back from the sandbox to
    # build them. They are only cached when the loop deliberately reuses a
    # variant (the pure-Python AES fallback), where recomputing would cost
    # seconds -- caching all 50 one-megabyte AES answers would otherwise hold
    # ~100 MB of hex in the scorer for no benefit.
    cache: dict[int, str] = {}
    reuse = variants < iterations

    # Stage the full input once; the loop then rewrites only the seed bytes.
    handler.write_input(run_dir, handler.apply_seed(base, seeds[0]))

    total_elapsed = 0.0
    for i in range(iterations):
        slot = i % variants
        body = handler.apply_seed(base, seeds[slot])
        expected = cache.get(slot) if reuse else None
        if expected is None:
            expected = handler.expected(body)
            if reuse:
                cache[slot] = expected
        got, elapsed = _run_once(
            handler, run_dir, body, min(120.0, _remaining(deadline_s)), seed=seeds[slot]
        )
        total_elapsed += elapsed
        if got != expected:
            raise _CandidateError(
                f"wrong output on timed iteration {i + 1}/{iterations} "
                f"of the {size_bytes}-byte case"
            )
    if total_elapsed <= 0.0:
        raise _CandidateError("timed loop measured a non-positive duration")
    return (size_bytes * 8.0 * iterations / 1e6) / total_elapsed, variants


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]) -> Any:
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)


def _extract_pdf_text(pdf_path: Path, *, deadline_s: float) -> tuple[str | None, str | None]:
    try:
        proc = subprocess.run(
            ["pdftotext", "-q", "-layout", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=min(30.0, _remaining(deadline_s)),
        )
    except FileNotFoundError:
        return None, "pdftotext not found"
    except subprocess.TimeoutExpired as exc:
        return None, f"pdftotext timeout: {exc}"
    if proc.returncode != 0:
        return None, f"pdftotext failed (code={proc.returncode}): {(proc.stderr or '').strip()}"
    text = (proc.stdout or "").strip()
    return (text, None) if text else (None, "pdftotext produced empty output")


def evaluate(
    program_path: str,
    *,
    repo_root: Path | None = None,
    spec: Any,
    include_pdf_reference: bool = False,
) -> Any:
    """Score one Cryptographic candidate.

    Ordering is load-bearing and is asserted by
    ``frontier_eval/tests/test_cryptographic.py``:

    1. reference implementations imported and self-tested (module import time),
    2. candidate compiled -- once, and this is the only compilation,
    3. candidate executed.

    Nothing between steps 2 and 3 reads a file the candidate could have written,
    and nothing after step 3 is compiled.
    """
    start = time.time()
    root = _find_repo_root(Path(__file__).resolve()) if repo_root is None else Path(repo_root).expanduser().resolve()
    program = Path(program_path).expanduser().resolve()

    benchmark_dir = spec.benchmark_dir(root)
    algorithm = spec.benchmark_subdir
    reference_pdf_path = (benchmark_dir / "references" / spec.reference_pdf).resolve()

    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }
    artifacts: dict[str, str] = {
        "interface_contract": (
            "Hard requirements for the candidate program (do NOT change these):\n"
            f"1) Candidate must be valid C++ source for baseline/{spec.baseline_source}.\n"
            "2) The scorer compiles it once with `g++ -std=c++17 -O3`, before running it.\n"
            "3) The scorer generates every input, computes every expected answer itself\n"
            "   (FIPS-197 / SP 800-38A / FIPS-180-4 / FIPS-202 references), and checks the\n"
            "   candidate's output on EVERY invocation, including every timed one.\n"
            "4) The scorer measures elapsed time itself; nothing is parsed from candidate output.\n"
            "5) `combined_score` is the geometric mean throughput in Mbps over the\n"
            "   1000-byte and 1000000-byte cases.\n"
            "6) Any wrong answer, non-zero exit, or timeout makes the whole run invalid."
        ),
        "aes_reference_backend": reference.aes_backend_name(),
    }

    task_spec_zh_cn_path = (benchmark_dir / "Task_zh-CN.md").resolve()
    artifacts["task_spec_zh_cn_path"] = str(task_spec_zh_cn_path)
    task_spec_zh_cn = _read_text(task_spec_zh_cn_path)
    if task_spec_zh_cn:
        artifacts["task_spec_zh_cn"] = _truncate_middle(task_spec_zh_cn)

    evaluator_timeout_s = float(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "600") or "600")
    deadline_s = start + max(1.0, evaluator_timeout_s - 5.0)

    if include_pdf_reference:
        artifacts["reference_pdf_path"] = str(reference_pdf_path)
        if reference_pdf_path.is_file():
            pdf_text, pdf_error = _extract_pdf_text(reference_pdf_path, deadline_s=deadline_s)
            if pdf_text:
                artifacts["reference_pdf_text"] = _truncate_middle(pdf_text, limit=150_000)
            elif pdf_error:
                artifacts["reference_pdf_error"] = pdf_error
        else:
            artifacts["reference_pdf_error"] = f"reference PDF not found: {reference_pdf_path}"

    handler_cls = ALGORITHMS.get(algorithm)
    if handler_cls is None:
        artifacts["error_message"] = f"unknown cryptographic benchmark: {algorithm!r}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    if not benchmark_dir.is_dir():
        artifacts["error_message"] = f"cryptographic benchmark folder missing: {benchmark_dir}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    if not program.is_file():
        artifacts["error_message"] = f"candidate program not found: {program}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    # The reference is verified before the candidate has any presence on disk.
    try:
        reference.selftest()
    except Exception as exc:
        artifacts["error_message"] = f"scorer reference self-test failed, refusing to score: {exc}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    handler = handler_cls()
    rng = secrets.SystemRandom()

    work_dir = Path(tempfile.mkdtemp(prefix=f"fe_crypto_{_safe_metric_key(algorithm)}_")).resolve()
    try:
        run_dir = work_dir / "run"
        run_dir.mkdir()
        binary = run_dir / handler.binary_name

        compile_cmd = ["g++", "-std=c++17", "-O3", str(program), "-o", str(binary)]
        artifacts["compile_candidate_cmd"] = " ".join(compile_cmd)
        try:
            proc = subprocess.run(
                compile_cmd, capture_output=True, text=True, timeout=_remaining(deadline_s)
            )
        except subprocess.TimeoutExpired as exc:
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"candidate compile timeout: {exc}"
            return _wrap(metrics, artifacts)
        except FileNotFoundError as exc:
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"compiler unavailable: {exc}"
            return _wrap(metrics, artifacts)

        metrics["compile_candidate_returncode"] = float(proc.returncode)
        artifacts["compile_candidate_stdout"] = _tail(proc.stdout)
        artifacts["compile_candidate_stderr"] = _tail(proc.stderr)
        artifacts["compile_candidate_stderr_full"] = _truncate_middle(proc.stderr)
        if proc.returncode != 0:
            artifacts["error_message"] = "candidate compile failed"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        artifacts["candidate_dynamic_libs"] = _dynamic_libs(binary)

        # --- correctness (scorer owns both the questions and the answers) ---
        try:
            passed, total, notes, timed_out = _run_correctness(
                algorithm, handler, run_dir, rng, deadline_s
            )
        except subprocess.TimeoutExpired as exc:
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"correctness phase timeout: {exc}"
            return _wrap(metrics, artifacts)
        metrics["validate_passed"] = float(passed)
        metrics["validate_total"] = float(total)
        metrics["validate_pass_rate"] = float(passed) / float(total) if total else 0.0
        artifacts["validate_detail"] = "\n".join(notes)
        if timed_out:
            metrics["timeout"] = 1.0
        if passed != total:
            artifacts["error_message"] = f"correctness validation failed ({passed}/{total})"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        # --- throughput (scorer measures, scorer checks every iteration) ---
        cases = (
            (CASE_8KBITS, SIZE_8KBITS, ITERATIONS_8KBITS),
            (CASE_8MBITS, SIZE_8MBITS, ITERATIONS_8MBITS),
        )
        by_case: dict[str, float] = {}
        try:
            for name, size_bytes, iterations in cases:
                mbps, variants = _run_case(
                    algorithm, handler, run_dir, rng, size_bytes, iterations, deadline_s
                )
                by_case[name] = mbps
                metrics[f"throughput_variants_{_safe_metric_key(name)}"] = float(variants)
        except _CandidateError as exc:
            artifacts["error_message"] = f"throughput benchmark rejected: {exc}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        except subprocess.TimeoutExpired as exc:
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"throughput benchmark timeout: {exc}"
            return _wrap(metrics, artifacts)

        values = list(by_case.values())
        metrics["benchmark_count"] = float(len(by_case))
        metrics["throughput_geom_mean_mbps"] = _geometric_mean(values)
        metrics["throughput_mean_mbps"] = float(sum(values) / len(values))
        metrics["combined_score"] = metrics["throughput_geom_mean_mbps"]
        for name, value in by_case.items():
            metrics[f"throughput_{_safe_metric_key(name)}_mbps"] = float(value)
        metrics["throughput_8kbits_mbps"] = float(by_case[CASE_8KBITS])
        metrics["throughput_8mbits_mbps"] = float(by_case[CASE_8MBITS])
        artifacts["throughput_by_case"] = "\n".join(
            f"{name}: {value:.6f} Mbps" for name, value in by_case.items()
        )

        if _scorer_fingerprint() != _SCORER_FINGERPRINT_AT_IMPORT:
            metrics["scorer_tampered"] = 1.0
            metrics["combined_score"] = 0.0
            artifacts["error_message"] = (
                "the shared scorer under benchmarks/_shared changed while this run was "
                "in progress -- this persists across runs; restore the tree before "
                "trusting any later score for this task"
            )
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        metrics["valid"] = 1.0
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    except _CandidateError as exc:
        artifacts["error_message"] = f"candidate rejected: {exc}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
