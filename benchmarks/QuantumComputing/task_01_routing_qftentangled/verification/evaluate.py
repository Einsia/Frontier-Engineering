from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import mean
from typing import Any

from qiskit import transpile

TASK_DIR = Path(__file__).resolve().parent.parent

from utils import (
    compose_candidate_layout,
    compute_metrics,
    create_run_dir,
    dump_json,
    load_cases,
    rejected_case_result,
    run_candidate_circuit,
    save_circuit_artifacts,
    timed_call,
    verify_circuit_equivalence,
)
from mqt.bench import BenchmarkLevel, get_benchmark
from mqt.bench.targets.devices import get_device

# Wall-clock budget for one candidate invocation, enforced in the child process.
CANDIDATE_TIMEOUT_S = 900.0

# Functional-equivalence gate. The cost function below rewards *fewer* gates, so
# without this gate the optimal strategy is to return the empty circuit
# (cost 0, score > 3.0) -- which is exactly what the archived top submissions
# did. `sampled` mode evolves |0...0> plus random input states through both
# circuits and compares, so a candidate that throws away fidelity (e.g. via
# `approximation_degree`) or replaces the algorithm with a cheap preparation of
# its one output state fails.
EQUIVALENCE_MODE = "sampled"
EQUIVALENCE_THRESHOLD = 1.0 - 1e-9
EQUIVALENCE_SAMPLES = 4
# 9/11/13-qubit inputs routed onto a 27-qubit device: an honest candidate keeps
# the active set near the input width. This bounds the verifier's statevector.
MAX_ACTIVE_QUBITS = 22


def routing_cost(depth: int, two_qubit_count: int) -> float:
    return two_qubit_count + 0.2 * depth


def normalize_score_0_to_3(cost: float, opt0_cost: float, opt3_cost: float) -> float:
    if abs(opt0_cost - opt3_cost) < 1e-12:
        return 0.0
    return 3.0 * (opt0_cost - cost) / (opt0_cost - opt3_cost)


def evaluate_case(case: dict[str, Any], task_dir: Path, artifact_root: Path) -> dict[str, Any]:
    benchmark = case["benchmark"]
    num_qubits = case["num_qubits"]
    target_name = case["target"]
    target = get_device(target_name)
    case_id = case["case_id"]
    case_dir = artifact_root / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    input_qc = get_benchmark(
        benchmark=benchmark,
        level=BenchmarkLevel.INDEP,
        circuit_size=num_qubits,
        opt_level=case.get("input_opt_level", 0),
    )
    save_circuit_artifacts(input_qc, case_dir, "input")

    # The candidate runs in its own interpreter and hands back OpenQASM 3 text,
    # which is re-parsed here. Nothing it returns is a live Python object, so a
    # QuantumCircuit subclass with an overridden count_ops()/depth() cannot
    # reach the metric code below.
    run = run_candidate_circuit(
        task_dir,
        input_circuit=input_qc,
        case=case,
        target_spec={"kind": "device", "name": target_name},
        timeout_s=CANDIDATE_TIMEOUT_S,
    )
    if not run.ok:
        return rejected_case_result(
            case_id,
            run.error or "candidate produced no circuit",
            {"stderr_tail": run.stderr_tail, "artifacts_dir": str(case_dir)},
        )

    candidate_raw = run.circuit
    save_circuit_artifacts(candidate_raw, case_dir, "candidate_raw")

    try:
        candidate_canon, canon_time = timed_call(
            transpile,
            candidate_raw,
            target=target,
            optimization_level=0,
            seed_transpiler=10,
        )
    except Exception as exc:
        return rejected_case_result(
            case_id,
            f"candidate circuit could not be canonicalized for {target_name}: {exc}",
            {"artifacts_dir": str(case_dir)},
        )
    save_circuit_artifacts(candidate_canon, case_dir, "candidate_canonical", save_image=False)

    # Metrics are measured on the canonical circuit, so equivalence must be
    # checked on that same circuit -- with the candidate's declared qubit
    # permutation pushed through the canonicalizing transpile.
    equivalence = verify_circuit_equivalence(
        input_qc,
        candidate_canon,
        meta=compose_candidate_layout(candidate_canon, run.meta, input_qc.num_qubits),
        mode=EQUIVALENCE_MODE,
        threshold=EQUIVALENCE_THRESHOLD,
        num_samples=EQUIVALENCE_SAMPLES,
        max_active_qubits=MAX_ACTIVE_QUBITS,
    )
    if not equivalence.ok:
        return rejected_case_result(
            case_id,
            f"candidate circuit is not equivalent to the input circuit: {equivalence.reason}",
            {"equivalence": equivalence.to_dict(), "artifacts_dir": str(case_dir)},
        )

    candidate_metrics = compute_metrics(candidate_canon)
    candidate_cost = routing_cost(candidate_metrics.depth, candidate_metrics.two_qubit_count)

    bench_rows: dict[str, Any] = {}
    for opt_level in (0, 1, 2, 3):
        bench_qc, bench_time = timed_call(
            get_benchmark,
            benchmark,
            BenchmarkLevel.MAPPED,
            num_qubits,
            target=target,
            opt_level=opt_level,
        )
        save_circuit_artifacts(bench_qc, case_dir, f"reference_opt_{opt_level}", save_image=False)
        metrics = compute_metrics(bench_qc)
        cost = routing_cost(metrics.depth, metrics.two_qubit_count)
        bench_rows[f"opt_{opt_level}"] = {
            "runtime_s": bench_time,
            "cost": cost,
            "metrics": metrics.to_dict(),
        }

    opt0_cost = bench_rows["opt_0"]["cost"]
    opt3_cost = bench_rows["opt_3"]["cost"]

    for opt_level in (0, 1, 2, 3):
        key = f"opt_{opt_level}"
        bench_rows[key]["score_0_to_3"] = normalize_score_0_to_3(bench_rows[key]["cost"], opt0_cost, opt3_cost)
    bench_rows["opt_0"]["score_0_to_3"] = 0.0
    bench_rows["opt_3"]["score_0_to_3"] = 3.0

    candidate_score = normalize_score_0_to_3(candidate_cost, opt0_cost, opt3_cost)
    improvement_vs_opt0 = (opt0_cost - candidate_cost) / opt0_cost if opt0_cost else 0.0
    gap_vs_opt3 = (candidate_cost - opt3_cost) / opt3_cost if opt3_cost else 0.0

    return {
        "case_id": case_id,
        "valid": True,
        "equivalence": equivalence.to_dict(),
        "candidate": {
            "solve_runtime_s": run.runtime_s,
            "canonicalize_runtime_s": canon_time,
            "total_runtime_s": run.runtime_s + canon_time,
            "cost": candidate_cost,
            "score_0_to_3": candidate_score,
            "metrics": candidate_metrics.to_dict(),
        },
        "references": bench_rows,
        "improvement_vs_opt0": improvement_vs_opt0,
        "gap_vs_opt3": gap_vs_opt3,
        "artifacts_dir": str(case_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Task 01 candidate solver.")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional path to store a JSON report.")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Optional artifact output directory. Default: task_01_routing_qftentangled/runs/eval_<timestamp>",
    )
    args = parser.parse_args()

    artifact_root = args.artifact_dir if args.artifact_dir is not None else create_run_dir(TASK_DIR, prefix="eval")
    artifact_root.mkdir(parents=True, exist_ok=True)

    cases = load_cases(TASK_DIR)
    results = [evaluate_case(case, TASK_DIR, artifact_root) for case in cases]
    rejected = [r for r in results if not r.get("valid")]

    if rejected:
        # A candidate that fails the equivalence gate is not scored at all: the
        # run exits non-zero so the harness records combined_score = invalid,
        # instead of handing an empty circuit a cost of 0.
        print("Task 01 Evaluation: REJECTED")
        for row in rejected:
            print(f"  {row['case_id']}: {row['rejection_reason']}")
        if args.json_out is not None:
            dump_json(
                args.json_out,
                {
                    "task": "task_01_routing_qftentangled",
                    "summary": {
                        "cases": len(results),
                        "valid": False,
                        "rejected_cases": [r["case_id"] for r in rejected],
                        "artifacts_dir": str(artifact_root),
                    },
                    "results": results,
                },
            )
            print(f"\nJSON report saved to {args.json_out}")
        sys.exit(1)

    avg_candidate_cost = mean(r["candidate"]["cost"] for r in results)
    avg_candidate_score = mean(r["candidate"]["score_0_to_3"] for r in results)
    avg_opt0_cost = mean(r["references"]["opt_0"]["cost"] for r in results)
    avg_opt3_cost = mean(r["references"]["opt_3"]["cost"] for r in results)

    print("Task 01 Evaluation Summary")
    print(f"cases={len(results)}")
    print(f"avg_candidate_cost={avg_candidate_cost:.4f}")
    print(f"avg_candidate_score_0_to_3={avg_candidate_score:.4f}")
    print(f"avg_opt0_cost={avg_opt0_cost:.4f}")
    print(f"avg_opt3_cost={avg_opt3_cost:.4f}")
    print(f"artifacts_dir={artifact_root}")
    print("")

    for row in results:
        print(
            f"{row['case_id']}: candidate_cost={row['candidate']['cost']:.4f}, "
            f"candidate_score={row['candidate']['score_0_to_3']:.4f}, "
            f"equivalence_fidelity={row['equivalence']['fidelity']:.12f}, "
            f"opt0={row['references']['opt_0']['cost']:.4f}, "
            f"opt3={row['references']['opt_3']['cost']:.4f}"
        )
        for opt_level in (0, 1, 2, 3):
            ref = row["references"][f"opt_{opt_level}"]
            print(
                f"  opt{opt_level}: cost={ref['cost']:.4f}, "
                f"score_0_to_3={ref['score_0_to_3']:.4f}, "
                f"runtime_s={ref['runtime_s']:.6f}"
            )

    if args.json_out is not None:
        payload = {
            "task": "task_01_routing_qftentangled",
            "summary": {
                "cases": len(results),
                "valid": True,
                "avg_candidate_cost": avg_candidate_cost,
                "avg_candidate_score_0_to_3": avg_candidate_score,
                "avg_opt0_cost": avg_opt0_cost,
                "avg_opt3_cost": avg_opt3_cost,
                "artifacts_dir": str(artifact_root),
            },
            "results": results,
        }
        dump_json(args.json_out, payload)
        print(f"\nJSON report saved to {args.json_out}")


if __name__ == "__main__":
    main()
