"""Isolated execution for the importance-sampling ("sampler") benchmark family.

Four benchmarks share one shape:

  * LDPCErrorFloor        -> class ``TrappingSetSampler``
  * PMDSimulation         -> class ``PMDSampler``
  * RayleighFadingBER     -> class ``DeepFadeSampler``
  * HighReliableSimulation-> class ``MySampler``

The candidate supplies an importance-sampling algorithm invoked by the
simulation loop. Candidate execution runs in a subprocess; the parent validates
returned records and computes the final score.

What this module provides
-------------------------
``run_sampler_repeats`` runs a scorer-owned *driver* in a subprocess (via
``candidate_sandbox.run_candidate_isolated``). The driver is the only thing that
ever executes the candidate. It hands back **numbers only** -- one record per
repeat -- as JSON. The parent process then validates every field and computes
the score itself.

Contract (``sampler_run.v1``)::

    {
      "schema": "frontier_eval.sampler_run.v1",
      "task": "<task key>",
      "repeats": [
        {
          "repeat": 0,
          "runtime_s": 1.23,
          "raw": {                       # the 6-tuple, encoded (see _enc)
            "a": ..., "b": ..., "c": ...,
            "total_samples": ..., "actual_std": ..., "converged": true
          },
          "audit": {                     # observations about the proposal
            "sample_calls": 3,
            "rows": 15000,
            "nonfinite_proposal_calls": 0,
            "nonfinite_logq_calls": 0,
            "bad_shape_calls": 0,
            "proposal_ndim": 2
          }
        }
      ]
    }

``raw.a``/``raw.b``/``raw.c`` are the first three slots of the benchmark's
6-tuple. They are deliberately unnamed here because the four tasks name them
differently (``errors_log``/``outages_log``; ``err_ratio``/``outage_prob``);
each evaluator maps them back.

Design notes / deliberate choices
---------------------------------
* The driver source is a **string constant in this module**, materialised into a
  scorer-owned temporary directory outside the benchmark tree. Filesystem
  protection depends on the selected sandbox mode.
* The runtime modules are imported in the child *before* the candidate is
  executed, so ``sys.modules`` already holds the trusted copies (invariant 1 of
  ``candidate_sandbox``).
* Aggregation (medians, convergence rate, validity, score) is **not** done here
  and is never read from the child. Each evaluator recomputes it from the
  validated per-repeat numbers.
* ``RLIMIT_AS`` and ``RLIMIT_CPU`` are omitted because the workloads use
  multiple BLAS threads and their associated address-space allocations.
  Wall-clock ``timeout_s``, ``RLIMIT_FSIZE`` and ``RLIMIT_NOFILE`` are enforced.

Who computes the aggregates (``call_mode``)
-------------------------------------------
``call_mode="canonical"`` runs the *benchmark-owned* simulation loop and ignores
whatever ``simulate_variance_controlled`` the candidate defines. The candidate
then contributes only ``sample()``, and every aggregate -- the log weights, the
sample count, the standard error, the convergence flag -- is produced by trusted
code. This is used by LDPCErrorFloor, RayleighFadingBER and
HighReliableSimulation. The candidate and simulation loop still share the child
interpreter, so this separation alone does not protect every child-side binding.

``call_mode="candidate"`` keeps the older contract where the candidate owns the
loop and reports the 6-tuple itself.

Candidate-owned aggregates
--------------------------
PMDSimulation uses ``call_mode="candidate"`` and its candidate owns the simulation
loop, including log-weight clipping and adaptive bias updates. The returned
aggregates are checked for finite, in-domain values and sample counts consistent
with observed proposal calls. These checks do not independently recompute the
reported outage probability, so fabricated aggregates can still pass them.
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import candidate_sandbox as sandbox  # noqa: E402

#: The parent's wall clock bounds what the child may claim it spent. Slack
#: covers interpreter startup and result serialisation; the floor fraction is
#: deliberately loose so a slow import or a GC pause cannot fail an honest run.
WALL_CLOCK_SLACK_S = 5.0
WALL_CLOCK_STARTUP_S = 5.0
WALL_CLOCK_MIN_FRACTION = 0.5

__all__ = [
    "InvalidSubmissionError",
    "SamplerRunError",
    "run_sampler_repeats",
    "decode_special",
    "validate_common_repeat",
]

InvalidSubmissionError = sandbox.InvalidSubmissionError


class SamplerRunError(RuntimeError):
    """The candidate could not be run, or produced an unusable result."""


SCHEMA = "frontier_eval.sampler_run.v1"

# Wall-clock ceiling per benchmark run (all repeats). Honest baselines finish in
# well under a minute; this only stops a runaway candidate.
DEFAULT_TIMEOUT_S = 1800.0

# Environment the child may see. Anything not listed is dropped, so a candidate
# cannot be handed PYTHONPATH/PYTHONSTARTUP-style injection points from the
# harness environment.
ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TEMP",
    "TMP",
    "FRONTIER_ENGINEERING_ROOT",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)

RLIMITS = {
    "FSIZE": 1 << 30,  # 1 GiB: a candidate cannot fill the disk
    "NOFILE": 4096,
}


# --------------------------------------------------------------------------
# special-float codec (JSON has no -inf / nan)
# --------------------------------------------------------------------------

def decode_special(value: Any) -> float:
    """Decode a value produced by the driver's ``_enc``."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        table = {"-inf": float("-inf"), "inf": float("inf"), "nan": float("nan")}
        if value in table:
            return table[value]
    raise InvalidSubmissionError(f"unencodable numeric field: {value!r}")


# --------------------------------------------------------------------------
# driver (runs in the child process; never imported by the scorer)
# --------------------------------------------------------------------------

_DRIVER_SOURCE = r'''
"""Scorer-owned driver. Runs a candidate sampler and reports numbers only.

This file is written by benchmarks/_shared/sampler_isolation.py into a
scorer-owned temporary directory. It is the *only* place a candidate program is
executed. It never computes or reports a score.
"""

from __future__ import annotations

import argparse
import json
import math
import runpy
import sys
import time
import traceback
from pathlib import Path


def _enc(x):
    """Encode a float so JSON can carry -inf / +inf / nan."""
    if isinstance(x, bool):
        return bool(x)
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "nan"
    if math.isnan(v):
        return "nan"
    if math.isinf(v):
        return "-inf" if v < 0 else "inf"
    return v


class _Recorder:
    """Wraps sampler.sample() to observe the proposal without trusting it."""

    def __init__(self, fn):
        self._fn = fn
        self.sample_calls = 0
        self.rows = 0
        self.nonfinite_proposal_calls = 0
        self.nonfinite_logq_calls = 0
        self.bad_shape_calls = 0
        self.proposal_ndim = 0

    def __call__(self, *args, **kwargs):
        import numpy as np

        out = self._fn(*args, **kwargs)
        self.sample_calls += 1
        try:
            proposal, log_q = out[0], out[1]
            parr = np.asarray(proposal)
            qarr = np.asarray(log_q)
            self.proposal_ndim = int(parr.ndim)
            if parr.ndim < 1 or qarr.ndim != 1 or parr.shape[0] != qarr.shape[0]:
                self.bad_shape_calls += 1
            else:
                self.rows += int(parr.shape[0])
            if not np.all(np.isfinite(parr)):
                self.nonfinite_proposal_calls += 1
            if not np.all(np.isfinite(qarr)):
                self.nonfinite_logq_calls += 1
        except Exception:
            self.bad_shape_calls += 1
        return out

    def audit(self):
        return {
            "sample_calls": self.sample_calls,
            "rows": self.rows,
            "nonfinite_proposal_calls": self.nonfinite_proposal_calls,
            "nonfinite_logq_calls": self.nonfinite_logq_calls,
            "bad_shape_calls": self.bad_shape_calls,
            "proposal_ndim": self.proposal_ndim,
        }


def _import_runtime(task, repo_root):
    """Import the benchmark's trusted runtime BEFORE the candidate executes."""
    if task == "ldpc":
        from benchmarks.CommunicationEngineering.LDPCErrorFloor.runtime.sampler import SamplerBase
        from benchmarks.CommunicationEngineering.LDPCErrorFloor.runtime.ldpc_code import LDPCCode
        return {"SamplerBase": SamplerBase, "LDPCCode": LDPCCode}
    if task == "pmd":
        from benchmarks.CommunicationEngineering.PMDSimulation.runtime.sampler import SamplerBase
        from benchmarks.CommunicationEngineering.PMDSimulation.runtime.fiber_model import PMDFiberModel
        return {"SamplerBase": SamplerBase, "PMDFiberModel": PMDFiberModel}
    if task == "rayleigh":
        from benchmarks.CommunicationEngineering.RayleighFadingBER.runtime.sampler import SamplerBase
        from benchmarks.CommunicationEngineering.RayleighFadingBER.runtime.channel_model import (
            RayleighFadingChannel,
        )
        return {"SamplerBase": SamplerBase, "RayleighFadingChannel": RayleighFadingChannel}
    if task == "hrs":
        from benchmarks.WirelessChannelSimulation.HighReliableSimulation.runtime.sampler import SamplerBase
        from benchmarks.WirelessChannelSimulation.HighReliableSimulation.runtime.chase import ChaseDecoder
        from benchmarks.WirelessChannelSimulation.HighReliableSimulation.runtime.code_linear import (
            HammingCode,
        )
        return {"SamplerBase": SamplerBase, "ChaseDecoder": ChaseDecoder, "HammingCode": HammingCode}
    raise SystemExit("unknown task: %s" % task)


def _build_model(task, rt, const, seed):
    from numpy.random import Generator, Philox

    if task == "ldpc":
        code = rt["LDPCCode"].create_regular_ldpc(
            n=int(const["n"]), dv=int(const["dv"]), dc=int(const["dc"]), seed=seed
        )
        code.rng = Generator(Philox(seed))
        return code
    if task == "pmd":
        return rt["PMDFiberModel"](
            length_km=float(const["fiber_length_km"]),
            pmd_coefficient=float(const["pmd_coefficient"]),
            num_segments=int(const["num_segments"]),
        )
    if task == "rayleigh":
        return rt["RayleighFadingChannel"](
            num_branches=int(const["num_branches"]), sigma_h=float(const["sigma_h"])
        )
    if task == "hrs":
        code = rt["HammingCode"](r=int(const["r"]), decoder="binary")
        code.rng = Generator(Philox(seed))
        code.set_decoder(rt["ChaseDecoder"](code=code, t=int(const["chase_t"])))
        return code
    raise SystemExit("unknown task: %s" % task)


def _make_sampler(task, cls, model, seed):
    if task == "ldpc":
        return cls(code=model, seed=seed)
    if task == "pmd":
        return cls(fiber_model=model, seed=seed)
    if task == "rayleigh":
        return cls(channel_model=model, seed=seed)
    if task == "hrs":
        return cls(code=model, seed=seed)
    raise SystemExit("unknown task: %s" % task)


def _run_simulation(task, spec, model, sampler):
    """Run the simulation.

    ``call_mode == "canonical"`` drives the benchmark-owned loop directly and
    ignores any ``simulate_variance_controlled`` the candidate defines, so every
    aggregate is produced by trusted code and only ``sample()`` comes from the
    candidate. ``call_mode == "candidate"`` preserves the older contract where
    the candidate owns the loop; its numbers are then validated by the parent.
    """
    const = spec["constants"]
    canonical = spec.get("call_mode", "candidate") == "canonical"

    if task == "ldpc":
        if canonical:
            return model.simulate_variance_controlled(
                noise_std=float(const["sigma"]),
                target_std=float(const["target_std"]),
                max_samples=int(const["max_samples"]),
                sampler=sampler,
                batch_size=int(const["batch_size"]),
                fix_tx=True,
                min_errors=int(const["min_errors"]),
            )
        return sampler.simulate_variance_controlled(
            code=model,
            sigma=float(const["sigma"]),
            target_std=float(const["target_std"]),
            max_samples=int(const["max_samples"]),
            batch_size=int(const["batch_size"]),
            fix_tx=True,
            min_errors=int(const["min_errors"]),
        )
    if task == "pmd":
        if canonical:
            return model.simulate_variance_controlled(
                dgd_threshold=float(const["dgd_threshold"]),
                target_std=float(const["target_std"]),
                max_samples=int(const["max_samples"]),
                sampler=sampler,
                batch_size=int(const["batch_size"]),
                min_outages=int(const["min_outages"]),
            )
        return sampler.simulate_variance_controlled(
            fiber_model=model,
            dgd_threshold=float(const["dgd_threshold"]),
            target_std=float(const["target_std"]),
            max_samples=int(const["max_samples"]),
            batch_size=int(const["batch_size"]),
            min_outages=int(const["min_outages"]),
        )
    if task == "rayleigh":
        if canonical:
            return model.simulate_variance_controlled(
                diversity_type=str(const["diversity_type"]),
                modulation=str(const["modulation"]),
                snr_db=float(const["snr_db"]),
                target_std=float(const["target_std"]),
                max_samples=int(const["max_samples"]),
                sampler=sampler,
                batch_size=int(const["batch_size"]),
                min_errors=int(const["min_errors"]),
            )
        return sampler.simulate_variance_controlled(
            channel_model=model,
            diversity_type=str(const["diversity_type"]),
            modulation=str(const["modulation"]),
            snr_db=float(const["snr_db"]),
            target_std=float(const["target_std"]),
            max_samples=int(const["max_samples"]),
            batch_size=int(const["batch_size"]),
            min_errors=int(const["min_errors"]),
        )
    if task == "hrs":
        # Benchmark-owned loop: the candidate only supplies sample().
        return model.simulate_variance_controlled(
            noise_std=float(const["sigma"]),
            target_std=float(const["target_std"]),
            max_samples=int(const["max_samples"]),
            sampler=sampler,
            batch_size=int(const["batch_size"]),
            fix_tx=True,
            min_errors=int(const["min_errors"]),
        )
    raise SystemExit("unknown task: %s" % task)


def _normalize(task, result):
    """Flatten the benchmark 6-tuple/dict into positional slots. No judgement."""
    dict_keys = {
        "ldpc": ("errors_log", "weights_log", "err_ratio"),
        "pmd": ("outages_log", "weights_log", "outage_prob"),
        "rayleigh": ("errors_log", "weights_log", "err_ratio"),
        "hrs": ("errors_log", "weights_log", "err_ratio"),
    }[task]

    if isinstance(result, dict):
        missing = [k for k in dict_keys[:2] if k not in result]
        if missing:
            raise ValueError("simulate_variance_controlled result missing %s" % missing)
        a = result[dict_keys[0]]
        b = result[dict_keys[1]]
        c = result.get(dict_keys[2], float("nan"))
        total_samples = result.get("total_samples", float("nan"))
        actual_std = result.get("actual_std", float("nan"))
        converged = result.get("converged", False)
    elif isinstance(result, (tuple, list)) and len(result) >= 6:
        a, b, c, total_samples, actual_std, converged = result[:6]
    else:
        raise ValueError("simulate_variance_controlled result format unsupported")

    # `converged` must be a plain truth value. Report *how* it was expressed so
    # the parent can enforce the original "bool or 0/1" rule instead of silently
    # accepting anything truthy.
    import numpy as np

    if isinstance(converged, (bool, np.bool_)):
        kind = "bool"
    elif isinstance(converged, (int, float, np.integer, np.floating)) and float(converged) in (0.0, 1.0):
        kind = "int01"
    else:
        kind = "other"
    try:
        conv = bool(converged)
    except Exception:
        raise ValueError("converged is not a truth value")

    return {
        "a": _enc(a),
        "b": _enc(b),
        "c": _enc(c),
        "total_samples": _enc(total_samples),
        "actual_std": _enc(actual_std),
        "converged": conv,
        "converged_kind": kind,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    task = spec["task"]
    repo_root = spec["repo_root"]
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    # 1. Trusted runtime first -- it is resident before any candidate code runs.
    rt = _import_runtime(task, repo_root)

    # Capture the monotonic clock before candidate execution so later module
    # attribute changes do not replace this local reference.
    _clock = time.monotonic

    # 2. Now the candidate. Executing it here is the point: this process is the
    #    sandbox. Module-level statements run exactly as they always did, but
    #    they can no longer touch the scoring process.
    namespace = runpy.run_path(spec["candidate"], run_name="candidate_program")

    class_name = spec["class_name"]
    if class_name not in namespace:
        raise SystemExit("candidate does not define %s" % class_name)
    cls = namespace[class_name]
    if not isinstance(cls, type) or not issubclass(cls, rt["SamplerBase"]):
        raise SystemExit("%s must be a subclass of SamplerBase" % class_name)

    from numpy.random import Generator, Philox

    repeats = []
    for rep in range(int(spec["repeats"])):
        seed = rep
        model = _build_model(task, rt, spec["constants"], seed)
        sampler = _make_sampler(task, cls, model, seed)
        if spec.get("reset_rng") and hasattr(sampler, "rng"):
            sampler.rng = Generator(Philox(seed))
        if not hasattr(sampler, "simulate_variance_controlled"):
            raise SystemExit("%s lacks simulate_variance_controlled" % class_name)

        recorder = _Recorder(sampler.sample)
        sampler.sample = recorder

        t0 = _clock()
        result = _run_simulation(task, spec, model, sampler)
        dt = _clock() - t0

        repeats.append(
            {
                "repeat": rep,
                "runtime_s": _enc(dt),
                "raw": _normalize(task, result),
                "audit": recorder.audit(),
            }
        )

    payload = {
        "schema": "frontier_eval.sampler_run.v1",
        "task": task,
        "repeats": repeats,
    }
    Path(args.out).write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    # Always leave a result.json behind, even on failure. The parent declares it
    # as an expected output, and without it a crash surfaces as the useless
    # "expected output not produced" instead of the candidate's own traceback.
    _out = None
    for _i, _a in enumerate(sys.argv):
        if _a == "--out" and _i + 1 < len(sys.argv):
            _out = sys.argv[_i + 1]
    try:
        main()
    except BaseException as _exc:  # noqa: BLE001 - re-raised below
        _detail = traceback.format_exc()
        traceback.print_exc()
        if _out:
            try:
                Path(_out).write_text(
                    json.dumps(
                        {
                            "schema": "frontier_eval.sampler_run.v1",
                            "error": str(_exc),
                            "traceback": _detail[-4000:],
                        }
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass
        raise SystemExit(1)
'''


# --------------------------------------------------------------------------
# parent side
# --------------------------------------------------------------------------

def _write_driver(root: Path) -> Path:
    path = root / "sampler_driver.py"
    path.write_text(_DRIVER_SOURCE, encoding="utf-8")
    return path


def run_sampler_repeats(
    *,
    task: str,
    candidate_path: Path,
    repo_root: Path,
    class_name: str,
    repeats: int,
    constants: dict[str, Any],
    reset_rng: bool,
    call_mode: str = "candidate",
    timeout_s: float = DEFAULT_TIMEOUT_S,
    python: str = sys.executable,
) -> list[dict[str, Any]]:
    """Run the candidate's sampler in a subprocess; return raw per-repeat records.

    Raises ``SamplerRunError`` on any failure. The returned records contain only
    numbers -- never a score, never a callable. Every field still has to be
    validated by the caller (see ``validate_common_repeat``).
    """
    candidate_path = Path(candidate_path)
    if not candidate_path.is_file():
        raise SamplerRunError(f"candidate program not found: {candidate_path}")

    spec = {
        "task": task,
        "repo_root": str(Path(repo_root).resolve()),
        "candidate": str(candidate_path.resolve()),
        "class_name": class_name,
        "repeats": int(repeats),
        "constants": constants,
        "reset_rng": bool(reset_rng),
        "call_mode": str(call_mode),
    }

    # The driver lives in a scorer-owned directory, outside both the benchmark
    # tree and the candidate's sandbox workdir.
    driver_root = Path(tempfile.mkdtemp(prefix="fe_sampler_driver_")).resolve()
    try:
        driver = _write_driver(driver_root)
        try:
            run = sandbox.run_candidate_isolated(
                driver,
                inputs={"spec.json": json.dumps(spec).encode("utf-8")},
                expected_outputs=("result.json",),
                timeout_s=timeout_s,
                argv=("--spec", "spec.json", "--out", "result.json"),
                copy_into_workdir=False,
                env_allowlist=ENV_ALLOWLIST,
                rlimits=RLIMITS,
                python=python,
            )
        except InvalidSubmissionError as exc:
            raise SamplerRunError(f"candidate produced no usable result: {exc}") from exc
        run_wall_s = run.runtime_s

        if run.timed_out:
            raise SamplerRunError(f"candidate timed out after {timeout_s}s")
        if run.returncode != 0:
            tail = (run.stderr_tail or "").strip()[-1500:]
            raise SamplerRunError(
                f"candidate subprocess exited with code {run.returncode}: {tail}"
            )

        try:
            payload = sandbox.load_json_output(run, "result.json")
        except InvalidSubmissionError as exc:
            raise SamplerRunError(str(exc)) from exc
    finally:
        shutil.rmtree(driver_root, ignore_errors=True)

    if payload.get("schema") != SCHEMA:
        raise SamplerRunError(f"unexpected result schema: {payload.get('schema')!r}")
    if payload.get("task") != task:
        raise SamplerRunError("result is for a different task")

    records = payload.get("repeats")
    if not isinstance(records, list) or len(records) != int(repeats):
        raise SamplerRunError(
            f"expected {repeats} repeat record(s), got "
            f"{len(records) if isinstance(records, list) else type(records).__name__}"
        )
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise SamplerRunError(f"repeat {i} is not an object")
        if rec.get("repeat") != i:
            raise SamplerRunError(f"repeat records out of order at index {i}")
        for key in ("runtime_s", "raw", "audit"):
            if key not in rec:
                raise SamplerRunError(f"repeat {i} missing '{key}'")
        if not isinstance(rec["raw"], dict) or not isinstance(rec["audit"], dict):
            raise SamplerRunError(f"repeat {i} has a malformed record")

    # Bound child-reported runtimes against elapsed time measured by the
    # parent. This rejects implausible values but does not prevent a candidate
    # from understating its runtime within the permitted window.
    reported_total = 0.0
    for i, rec in enumerate(records):
        value = decode_special(rec["runtime_s"])
        if not math.isfinite(value) or value < 0.0:
            raise SamplerRunError(f"repeat {i} reported a nonsensical runtime: {value!r}")
        reported_total += value

    wall_s = float(run_wall_s)
    if reported_total > wall_s + WALL_CLOCK_SLACK_S:
        raise SamplerRunError(
            f"self-reported runtime {reported_total:.3f}s exceeds the "
            f"{wall_s:.3f}s the subprocess was alive"
        )
    floor_s = WALL_CLOCK_MIN_FRACTION * (wall_s - WALL_CLOCK_STARTUP_S)
    if floor_s > 0.0 and reported_total < floor_s:
        raise SamplerRunError(
            f"self-reported runtime {reported_total:.3f}s is implausibly small "
            f"against a {wall_s:.3f}s subprocess (floor {floor_s:.3f}s); the "
            "candidate may be forging its clock"
        )
    return records


def validate_common_repeat(
    record: dict[str, Any],
    *,
    max_samples: int,
    integer_tol: float = 1e-6,
    require_bool_converged: bool = False,
) -> dict[str, Any]:
    """Domain-check one repeat record and return decoded values.

    Checks that hold for all four benchmarks. Anything task-specific (the
    err_ratio/log identity, the converged/target_std relationship) stays in the
    task's own evaluator.
    """
    raw = record["raw"]
    for key in ("a", "b", "c", "total_samples", "actual_std", "converged"):
        if key not in raw:
            raise InvalidSubmissionError(f"result missing field '{key}'")

    a = decode_special(raw["a"])
    b = decode_special(raw["b"])
    c = decode_special(raw["c"])
    total_samples = decode_special(raw["total_samples"])
    actual_std = decode_special(raw["actual_std"])
    if not isinstance(raw["converged"], bool):
        raise InvalidSubmissionError("converged must be a JSON boolean")
    converged = bool(raw["converged"])
    if require_bool_converged and raw.get("converged_kind") == "other":
        raise InvalidSubmissionError("converged must be a boolean or 0/1")
    runtime_s = decode_special(record["runtime_s"])

    # b is log(total weight): must be an ordinary finite number.
    if not math.isfinite(b):
        raise InvalidSubmissionError("weights_log must be finite")
    # a is log(error weight): finite, or -inf meaning "no event observed".
    if math.isnan(a) or a == float("inf"):
        raise InvalidSubmissionError("errors_log must be finite or -inf")
    if math.isfinite(a) and a > b + 1e-9:
        raise InvalidSubmissionError("errors_log cannot exceed weights_log")

    if not math.isfinite(total_samples) or total_samples <= 0:
        raise InvalidSubmissionError("total_samples must be a positive finite number")
    rounded = int(round(total_samples))
    if abs(total_samples - rounded) > integer_tol:
        raise InvalidSubmissionError("total_samples must be an integer")
    if rounded > int(max_samples):
        raise InvalidSubmissionError(
            f"total_samples={rounded} exceeds max_samples={int(max_samples)}"
        )

    if math.isnan(actual_std) or actual_std < 0.0:
        raise InvalidSubmissionError("actual_std must be non-negative (inf allowed)")

    if not math.isfinite(runtime_s) or runtime_s < 0.0:
        raise InvalidSubmissionError("runtime_s must be a non-negative finite number")

    audit = record["audit"]
    for key in (
        "sample_calls",
        "rows",
        "nonfinite_proposal_calls",
        "nonfinite_logq_calls",
        "bad_shape_calls",
    ):
        value = audit.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise InvalidSubmissionError(f"audit.{key} must be a non-negative integer")
    if audit["bad_shape_calls"]:
        raise InvalidSubmissionError(
            "sampler returned a malformed proposal "
            "(expected (samples, log_pdf) with matching leading dimension)"
        )
    if audit["nonfinite_proposal_calls"]:
        raise InvalidSubmissionError("sampler produced non-finite proposal samples")
    if audit["nonfinite_logq_calls"]:
        raise InvalidSubmissionError("sampler produced non-finite proposal log-densities")
    if audit["sample_calls"] <= 0:
        raise InvalidSubmissionError("sampler.sample() was never called")
    # A run cannot have consumed more samples than the proposal actually
    # produced. This is the one cheap forgery check available without re-running
    # the decoder in this process: the sample count is observed by the driver's
    # recorder, not reported by the candidate.
    if rounded > audit["rows"]:
        raise InvalidSubmissionError(
            f"total_samples={rounded} exceeds the {audit['rows']} sample(s) the "
            "proposal actually produced"
        )

    return {
        "a": a,
        "b": b,
        "c": c,
        "total_samples": float(rounded),
        "actual_std": actual_std,
        "converged": converged,
        "runtime_s": runtime_s,
        "audit": dict(audit),
    }
