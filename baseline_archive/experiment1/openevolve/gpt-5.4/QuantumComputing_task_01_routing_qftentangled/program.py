# EVOLVE-BLOCK-START
from __future__ import annotations

from qiskit import transpile
from qiskit.circuit import QuantumCircuit
from qiskit.transpiler import Target

from structural_optimizer import optimize_by_local_rewrite


def _cost(qc: QuantumCircuit) -> float:
    return sum(inst.operation.num_qubits == 2 for inst in qc.data) + 0.2 * qc.depth()


def optimize_circuit(input_circuit: QuantumCircuit, target: Target, case: dict) -> QuantumCircuit:
    qc = optimize_by_local_rewrite(input_circuit)
    if target is None:
        return qc
    n = case.get("num_qubits", input_circuit.num_qubits)
    try:
        best = transpile(qc, target=target, optimization_level=1)
        best_score = _cost(best)
    except Exception:
        best, best_score = qc, 1e18
    opts = (
        {"optimization_level": 3, "layout_method": "sabre", "routing_method": "sabre"},
        {"optimization_level": 3, "layout_method": "dense", "routing_method": "sabre"},
        {"optimization_level": 3, "layout_method": "lookahead", "routing_method": "sabre"},
        {"optimization_level": 3},
    )
    for s in (n + 1, n + 7, n + 19, n + 31, 13):
        for kw in opts:
            try:
                cand = transpile(qc, target=target, seed_transpiler=s, **kw)
            except Exception:
                continue
            score = _cost(cand)
            if score < best_score:
                best, best_score = cand, score
    return best
# EVOLVE-BLOCK-END
