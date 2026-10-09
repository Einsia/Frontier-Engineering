#!/usr/bin/env python3
"""Evaluator for QuantumComputing/task_04_quantum_error_decoder.

The candidate is a surface-code decoder. For each regime the evaluator builds a
rotated surface-code memory experiment with Stim, samples syndromes with a fixed
seed, recomputes the minimum-weight-perfect-matching (MWPM) reference on the same
shots, and then scores the candidate's logical observable predictions.

Per regime, with logical error rate ``L``::

    score = (log L_trivial - log L_candidate) / (log L_trivial - log L_mwpm)

so a decoder that ignores the syndrome scores 0.0, matching MWPM scores 1.0, and
beating it scores above 1.0 (the score is not clamped above). ``combined_score``
is the mean over the development regimes. Its value is what the search
state sees; the sealed regimes are reported separately as ``robustness_score``
and never enter ``combined_score``.

The candidate runs in a separate interpreter (``verification/candidate_runner.py``)
that receives only the error model and the syndrome batches, so the true
observable flips are never available to it, and ``stim``/``pymatching`` are
refused at import time.

Public entry point::

    python verification/evaluate.py --candidate baseline/solution.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

TASK_NAME = "QuantumComputing/task_04_quantum_error_decoder"

# Instances are generated from a difficulty level rather than hardcoded, so a
# regime that saturates can be answered by turning a knob instead of rebuilding
# the task. The ladder is an explicit measured table, not a formula: below
# threshold a larger code makes the logical error rate fall exponentially, so
# distance alone quickly leaves the MWPM anchor failing too rarely to measure.
# Each level therefore pushes the noise strength toward the circuit-level
# threshold near 1% while the code grows, and shrinks the shot count so the total
# decoding work stays roughly constant (detectors grow as d^2).
#
#   level 1  (3,0.005) (5,0.005) (5,0.010) (7,0.005)   6000 shots
#   level 2  (5,0.008) (7,0.008) (7,0.012) (9,0.008)   2400 shots
#   level 3  (7,0.010) (9,0.010) (9,0.012) (11,0.010)  1200 shots
DIFFICULTY = 1
_DEV_LADDER = {
    1: (((3, 0.005), (5, 0.005), (5, 0.010), (7, 0.005)), 6000),
    2: (((5, 0.008), (7, 0.008), (7, 0.012), (9, 0.008)), 2400),
    3: (((7, 0.010), (9, 0.010), (9, 0.012), (11, 0.010)), 1200),
}
_SEALED_LADDER = {
    1: (((5, 0.007), (7, 0.008)), 4000),
    2: (((7, 0.009), (9, 0.009)), 1700),
    3: (((9, 0.011), (11, 0.011)), 900),
}

# Sample seeds are injectable so an operator can run a genuinely sealed
# evaluation with an unpredictable stream (see README: "Sealing an evaluation").
# The defaults reproduce the measured reference numbers in references/.
DEV_SEED = int(os.environ.get("QEC_DEV_SEED", "20260807"))
SEALED_SEED = int(os.environ.get("QEC_SEALED_SEED", "771103"))

# Wall-clock bound for the candidate subprocess. The harness caps the whole
# evaluation at 300 s by default; leave room for circuit generation and MWPM.
CANDIDATE_TIMEOUT_S = float(os.environ.get("QEC_CANDIDATE_TIMEOUT_S", "240"))

FORBIDDEN_MODULES = ("pymatching", "stim")


def _regimes(level: int, ladder: dict, base_seed: int, prefix: str = "") -> tuple:
    """Build the concrete regimes for a difficulty level from the measured ladder."""
    level = int(level)
    if level not in ladder:
        raise ValueError(
            "difficulty %d has no measured ladder entry; add one and record its"
            " anchor failure counts before use" % level
        )
    shape, shots = ladder[level]
    return tuple(
        {
            "key": "%sd%d_p%.3f" % (prefix, distance, noise),
            "distance": distance,
            "noise": noise,
            "shots": shots,
            "seed": base_seed + index,
        }
        for index, (distance, noise) in enumerate(shape)
    )


def _build_circuit(distance: int, noise: float):
    import stim

    return stim.Circuit.generated(
        "surface_code:rotated_memory_z",
        distance=distance,
        rounds=distance,
        after_clifford_depolarization=noise,
        before_measure_flip_probability=noise,
        after_reset_flip_probability=noise,
        before_round_data_depolarization=noise,
    )


def _graphlike_errors(circuit) -> list:
    """Flatten the decomposed detector error model into graphlike components.

    Each returned component has at most two detectors, which is the
    representation matching decoders consume.
    """
    dem = circuit.detector_error_model(decompose_errors=True).flattened()
    out: list = []
    for inst in dem:
        if inst.type != "error":
            continue
        prob = float(inst.args_copy()[0])
        dets: list = []
        obs: list = []
        groups: list = []
        for target in inst.targets_copy():
            if target.is_separator():
                groups.append((dets, obs))
                dets, obs = [], []
            elif target.is_relative_detector_id():
                dets.append(int(target.val))
            elif target.is_logical_observable_id():
                obs.append(int(target.val))
        groups.append((dets, obs))
        for group_dets, group_obs in groups:
            if not group_dets and not group_obs:
                continue
            out.append(
                {
                    "p": prob,
                    "dets": sorted(group_dets),
                    "obs": sorted(group_obs),
                }
            )
    return out


_CACHE: dict = {}


def _instance_data(spec: dict) -> dict:
    """Build, sample and reference-decode one regime. Cached per process."""
    key = (spec["key"], spec["distance"], spec["noise"], spec["shots"], spec["seed"])
    if key in _CACHE:
        return _CACHE[key]

    import pymatching

    circuit = _build_circuit(spec["distance"], spec["noise"])
    sampler = circuit.compile_detector_sampler(seed=spec["seed"])
    detectors, observables = sampler.sample(spec["shots"], separate_observables=True)
    detectors = np.ascontiguousarray(detectors, dtype=bool)
    observables = np.ascontiguousarray(observables, dtype=bool)

    dem = circuit.detector_error_model(decompose_errors=True)
    matcher = pymatching.Matching.from_detector_error_model(dem)
    mwpm_prediction = np.asarray(matcher.decode_batch(detectors), dtype=bool)

    trivial_ler = float(observables.any(axis=1).mean())
    mwpm_ler = float((mwpm_prediction != observables).any(axis=1).mean())

    data = {
        "key": spec["key"],
        "problem": {
            "num_detectors": int(circuit.num_detectors),
            "num_observables": int(circuit.num_observables),
            "distance": int(spec["distance"]),
            "rounds": int(spec["distance"]),
            "errors": _graphlike_errors(circuit),
        },
        "detectors": detectors,
        "observables": observables,
        "trivial_ler": trivial_ler,
        "mwpm_ler": mwpm_ler,
        "shots": int(spec["shots"]),
    }
    _CACHE[key] = data
    return data


def _log_floor(shots: int) -> float:
    """Resolution floor so a zero-error batch cannot produce an infinite score."""
    return 1.0 / (2.0 * shots)


def _progress(cand_ler: float, trivial_ler: float, mwpm_ler: float, shots: int) -> float:
    floor = _log_floor(shots)
    cand = max(cand_ler, floor)
    trivial = max(trivial_ler, floor)
    mwpm = max(mwpm_ler, floor)
    span = math.log(trivial) - math.log(mwpm)
    if span <= 0.0:
        return 0.0
    progress = (math.log(trivial) - math.log(cand)) / span
    # Uncapped above: beating the MWPM anchor is a real result and must be
    # representable. Floored at 0 below: introducing logical errors scores 0.
    return float(max(0.0, progress))


def _validate_prediction(raw, shots: int, num_obs: int):
    """Return ``(prediction, None)`` or ``(None, reason)``."""
    try:
        pred = np.asarray(raw)
    except Exception as exc:  # noqa: BLE001
        return None, "bad array: %s" % type(exc).__name__
    if pred.ndim == 1 and num_obs == 1:
        pred = pred.reshape(-1, 1)
    if pred.shape != (shots, num_obs):
        return None, "expected %s, got %s" % ((shots, num_obs), tuple(pred.shape))
    if pred.dtype.kind not in "biu":
        if pred.dtype.kind != "f" or not np.all(np.isfinite(pred)):
            return None, "non-binary dtype %s" % pred.dtype
        if not np.all(np.isin(pred, (0.0, 1.0))):
            return None, "float predictions must be exactly 0.0 or 1.0"
    return pred.astype(bool), None


def _run_candidate(candidate: Path, specs: tuple, work_dir: Path):
    """Run the candidate in a separate interpreter over every regime.

    Returns ``(predictions_by_key, error_message, detail)``. On any failure
    ``predictions_by_key`` is ``None`` and the caller marks the run invalid.
    """
    inputs = work_dir / "inputs"
    outputs = work_dir / "outputs"
    inputs.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)

    for spec in specs:
        data = _instance_data(spec)
        (inputs / ("%s.problem.json" % spec["key"])).write_text(
            json.dumps(data["problem"]), encoding="utf-8"
        )
        np.save(inputs / ("%s.detectors.npy" % spec["key"]), data["detectors"])

    runner = Path(__file__).resolve().parent / "candidate_runner.py"
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable,
        str(runner),
        "--candidate",
        str(candidate),
        "--inputs",
        str(inputs),
        "--outputs",
        str(outputs),
    ]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=CANDIDATE_TIMEOUT_S,
            env=env,
            cwd=str(work_dir),
        )
    except subprocess.TimeoutExpired:
        return None, "candidate timed out after %.0f s" % CANDIDATE_TIMEOUT_S, ""
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        return (
            None,
            "candidate runner exited %d" % proc.returncode,
            "\n".join(detail[-12:]),
        )
    return outputs, None, (proc.stdout or "").strip()


def _score_regime(data: dict, prediction_path: Path) -> dict:
    shots, num_obs = data["observables"].shape
    if not prediction_path.is_file():
        error_path = prediction_path.with_name(
            prediction_path.name.replace(".prediction.npy", ".error.txt")
        )
        reason = error_path.read_text(encoding="utf-8") if error_path.is_file() else "no prediction"
        return {"key": data["key"], "valid": False, "reason": reason, "score": 0.0}

    pred, reason = _validate_prediction(np.load(prediction_path), shots, num_obs)
    if pred is None:
        return {"key": data["key"], "valid": False, "reason": reason, "score": 0.0}

    cand_ler = float((pred != data["observables"]).any(axis=1).mean())
    score = _progress(cand_ler, data["trivial_ler"], data["mwpm_ler"], data["shots"])
    return {
        "key": data["key"],
        "valid": True,
        "logical_error_rate": round(cand_ler, 6),
        "trivial_ler": round(data["trivial_ler"], 6),
        "mwpm_ler": round(data["mwpm_ler"], 6),
        "beats_mwpm": bool(cand_ler < data["mwpm_ler"]),
        "score": score,
    }


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, default=str), encoding="utf-8"
    )


def _failure(metrics_path: Path, artifacts_path: Path, report_path: Path, artifacts: dict, message: str) -> int:
    artifacts["error_message"] = message
    # House convention: an invalid submission reports combined_score 0.0 together
    # with valid 0.0, so invalid runs can never outrank a correct one.
    metrics = {
        "combined_score": 0.0,
        "valid": 0.0,
        "feasibility_rate": 0.0,
    }
    _write_json(metrics_path, metrics)
    _write_json(artifacts_path, artifacts)
    _write_json(report_path, {"task": TASK_NAME, "valid": 0.0, "error": message})
    print("[task_04_quantum_error_decoder] FAILURE: %s" % message, file=sys.stderr)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, help="Path to the candidate decoder module.")
    parser.add_argument("--metrics-out", default="metrics.json")
    parser.add_argument("--artifacts-out", default="artifacts.json")
    parser.add_argument("--report-out", default="eval_report.json")
    args = parser.parse_args(argv)

    started = time.time()
    metrics_path = Path(args.metrics_out)
    artifacts_path = Path(args.artifacts_out)
    report_path = Path(args.report_out)
    candidate = Path(args.candidate).expanduser().resolve()

    artifacts = {
        "task_name": TASK_NAME,
        "candidate_path": str(candidate),
        "difficulty": DIFFICULTY,
        "dev_seed": DEV_SEED,
        "sealed_seed": SEALED_SEED,
    }

    if not candidate.is_file():
        return _failure(metrics_path, artifacts_path, report_path, artifacts,
                        "candidate program not found: %s" % candidate)

    try:
        import pymatching  # noqa: F401
        import stim  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(
            "evaluator dependencies are missing (%s); install"
            " verification/requirements.txt into the task runtime" % exc,
            file=sys.stderr,
        )
        return 2

    dev_specs = _regimes(DIFFICULTY, _DEV_LADDER, DEV_SEED)
    sealed_specs = _regimes(DIFFICULTY, _SEALED_LADDER, SEALED_SEED, prefix="sealed_")

    with tempfile.TemporaryDirectory(prefix="qec_eval_") as tmp:
        work_dir = Path(tmp)
        predictions, error, detail = _run_candidate(candidate, dev_specs + sealed_specs, work_dir)
        if detail:
            artifacts["candidate_output_tail"] = detail
        if error is not None:
            return _failure(metrics_path, artifacts_path, report_path, artifacts, error)

        dev_results = [_score_regime(_instance_data(spec), predictions / ("%s.prediction.npy" % spec["key"])) for spec in dev_specs]
        dev_valid = [r for r in dev_results if r.get("valid")]
        all_valid = len(dev_valid) == len(dev_results)

        sealed_results = []
        sealed_score = 0.0
        if all_valid:
            sealed_results = [
                _score_regime(_instance_data(spec), predictions / ("%s.prediction.npy" % spec["key"]))
                for spec in sealed_specs
            ]
            sealed_valid = [r for r in sealed_results if r.get("valid")]
            if sealed_valid:
                sealed_score = float(np.mean([r["score"] for r in sealed_valid]))

    if all_valid and dev_results:
        combined = float(np.mean([r["score"] for r in dev_results]))
    else:
        # One failing regime is a broken decoder, not partial progress: the same
        # decode() runs on all four, so a failure is a correctness bug rather than
        # a weaker solution. Report 0.0 with valid 0.0 and keep the per-regime
        # detail in artifacts for diagnosis.
        combined = 0.0
    runtime_s = time.time() - started

    metrics = {
        "combined_score": combined,
        "valid": 1.0 if all_valid else 0.0,
        "robustness_score": sealed_score,
        "beats_mwpm_count": float(sum(1 for r in dev_results if r.get("beats_mwpm"))),
        "feasibility_rate": float(len(dev_valid) / len(dev_results)) if dev_results else 0.0,
        "runtime_s": float(runtime_s),
    }
    artifacts["per_regime"] = json.dumps(dev_results, indent=2)
    artifacts["sealed_per_regime"] = json.dumps(sealed_results, indent=2)
    artifacts["summary"] = json.dumps({k: v for k, v in metrics.items()}, indent=2)

    report = {
        "task": TASK_NAME,
        "candidate": str(candidate),
        "difficulty": DIFFICULTY,
        "valid": metrics["valid"],
        "combined_score": combined,
        "robustness_score": sealed_score,
        "regimes": dev_results,
        "sealed_regimes": sealed_results,
        "runtime_s": runtime_s,
    }

    _write_json(metrics_path, metrics)
    _write_json(artifacts_path, artifacts)
    _write_json(report_path, report)

    print(
        "[task_04_quantum_error_decoder] combined_score=%.4f valid=%.0f robustness=%.4f (%.1fs)"
        % (combined, metrics["valid"], sealed_score, runtime_s)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())