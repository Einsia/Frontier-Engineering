from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import mean
from typing import Any

from qiskit import transpile
from qiskit.circuit import QuantumCircuit

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
from mqt.bench.targets.gatesets import get_target_for_gateset

CLIFFORD_T_BASIS = ["cx", "h", "x", "y", "z", "s", "sdg", "t", "tdg"]

CANDIDATE_TIMEOUT_S = 900.0

# These cases are 3, 4 and 5 qubits, so the candidate's whole effective unitary
# is at most 32x32 and can be compared exactly. Nothing about the cost function
# (T-count + 0.2 * two-qubit + 0.05 * depth) stops a candidate from returning a
# cheaper circuit that computes something else, so this gate is what makes the
# score mean anything.
EQUIVALENCE_MODE = "exact"
EQUIVALENCE_THRESHOLD = 1.0 - 1e-9
# Optimizers routinely elide the QFT's trailing swaps and record them as a
# layout permutation; when that record is lost we still accept a circuit that
# is right up to relabelling the output qubits, since a relabelling costs
# nothing to undo classically and cannot hide a cheaper wrong circuit.
ALLOW_OUTPUT_PERMUTATION = True


def synthesis_cost(depth: int, two_qubit_count: int, t_count: int, tdg_count: int) -> float:
    t_total = t_count + tdg_count
    return t_total + 0.2 * two_qubit_count + 0.05 * depth


def normalize_score_0_to_3(cost: float, opt0_cost: float, opt3_cost: float) -> float:
    if abs(opt0_cost - opt3_cost) < 1e-12:
        return 0.0
    return 3.0 * (opt0_cost - cost) / (opt0_cost - opt3_cost)


def _strip_non_unitary_ops(qc: QuantumCircuit) -> QuantumCircuit:
    """Drop artifacts that target-gateset synthesis cannot translate."""
    cleaned = QuantumCircuit(qc.num_qubits, name=qc.name)
    cleaned.global_phase = qc.global_phase
    for instruction in qc.data:
        operation = instruction.operation
        if operation.name in {"barrier", "measure"}:
            continue
        qubits = [qc.find_bit(qubit).index for qubit in instruction.qubits]
        cleaned.append(operation.copy(), qubits, [])
    # Keep the transpiler's qubit-permutation record: dropping it used to make
    # even Qiskit's own opt-3 reference look inequivalent to the input.
    cleaned._layout = getattr(qc, "_layout", None)
    return cleaned


def transpile_to_clifford_t(qc: QuantumCircuit, opt_level: int) -> QuantumCircuit:
    transpiled = transpile(
        _strip_non_unitary_ops(qc),
        basis_gates=CLIFFORD_T_BASIS,
        optimization_level=opt_level,
        seed_transpiler=10,
    )
    return _strip_non_unitary_ops(transpiled)


def evaluate_case(case: dict[str, Any], task_dir: Path, artifact_root: Path) -> dict[str, Any]:
    benchmark = case["benchmark"]
    num_qubits = case["num_qubits"]
    gateset_name = case["target_gateset"]
    case_id = case["case_id"]
    case_dir = artifact_root / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    input_qc = _strip_non_unitary_ops(get_benchmark(
        benchmark=benchmark,
        level=BenchmarkLevel.ALG,
        circuit_size=num_qubits,
    ))
    save_circuit_artifacts(input_qc, case_dir, "input")

    run = run_candidate_circuit(
        task_dir,
        input_circuit=input_qc,
        case=case,
        target_spec={"kind": "gateset", "name": gateset_name, "num_qubits": num_qubits},
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
            transpile_to_clifford_t,
            candidate_raw,
            0,
        )
    except Exception as exc:
        return rejected_case_result(
            case_id,
            f"candidate circuit could not be canonicalized into the Clifford+T basis: {exc}",
            {"artifacts_dir": str(case_dir)},
        )
    save_circuit_artifacts(candidate_canon, case_dir, "candidate_canonical", save_image=False)

    equivalence = verify_circuit_equivalence(
        input_qc,
        candidate_canon,
        meta=compose_candidate_layout(candidate_canon, run.meta, input_qc.num_qubits),
        mode=EQUIVALENCE_MODE,
        threshold=EQUIVALENCE_THRESHOLD,
        allow_output_permutation=ALLOW_OUTPUT_PERMUTATION,
    )
    if not equivalence.ok:
        return rejected_case_result(
            case_id,
            f"candidate circuit is not equivalent to the input circuit: {equivalence.reason}",
            {"equivalence": equivalence.to_dict(), "artifacts_dir": str(case_dir)},
        )

    candidate_metrics = compute_metrics(candidate_canon)
    candidate_cost = synthesis_cost(
        candidate_metrics.depth,
        candidate_metrics.two_qubit_count,
        candidate_metrics.t_count,
        candidate_metrics.tdg_count,
    )

    bench_rows: dict[str, Any] = {}
    for opt_level in (0, 1, 2, 3):
        bench_qc, bench_time = timed_call(
            transpile_to_clifford_t,
            input_qc.copy(),
            opt_level,
        )
        save_circuit_artifacts(bench_qc, case_dir, f"reference_opt_{opt_level}", save_image=False)
        metrics = compute_metrics(bench_qc)
        cost = synthesis_cost(metrics.depth, metrics.two_qubit_count, metrics.t_count, metrics.tdg_count)
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
    parser = argparse.ArgumentParser(description="Evaluate Task 02 candidate solver.")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional path to store a JSON report.")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Optional artifact output directory. Default: task_02_clifford_t_synthesis/runs/eval_<timestamp>",
    )
    args = parser.parse_args()

    artifact_root = args.artifact_dir if args.artifact_dir is not None else create_run_dir(TASK_DIR, prefix="eval")
    artifact_root.mkdir(parents=True, exist_ok=True)

    cases = load_cases(TASK_DIR)
    results = [evaluate_case(case, TASK_DIR, artifact_root) for case in cases]
    rejected = [r for r in results if not r.get("valid")]

    if rejected:
        print("Task 02 Evaluation: REJECTED")
        for row in rejected:
            print(f"  {row['case_id']}: {row['rejection_reason']}")
        if args.json_out is not None:
            dump_json(
                args.json_out,
                {
                    "task": "task_02_clifford_t_synthesis",
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

    print("Task 02 Evaluation Summary")
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
            "task": "task_02_clifford_t_synthesis",
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
