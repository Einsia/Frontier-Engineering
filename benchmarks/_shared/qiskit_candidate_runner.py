#!/usr/bin/env python3
"""Child-side runner for ``QuantumComputing`` circuit-optimization candidates.

The scorer must never ``exec_module`` a candidate into its own interpreter: a
candidate that runs in the scoring process can hand back a ``QuantumCircuit``
subclass whose ``count_ops()`` / ``depth()`` / ``size()`` lie, monkeypatch
``qiskit.transpile``, or reach into the evaluator's module globals. See
``benchmarks/_shared/candidate_sandbox.py`` for the general pattern.

This module is the *inside* of that process boundary for the three
``benchmarks/QuantumComputing`` tasks. It is executed as::

    python qiskit_candidate_runner.py /abs/path/to/solve.py

with the sandbox working directory as cwd. It expects two staged inputs and
produces two outputs, all of them plain text/JSON:

inputs (written by the scorer)
    ``case.json``   -- ``{"case": {...}, "target": {...}, "options": {...}}``
    ``input.qasm``  -- the input circuit as OpenQASM 3

outputs (read back by the scorer, which then re-parses them in a clean process)
    ``submission.qasm``      -- the candidate's circuit as OpenQASM 3
    ``submission_meta.json`` -- qubit-permutation bookkeeping (see below)

``submission_meta.json`` carries the ``TranspileLayout`` information that
OpenQASM 3 cannot express: which physical qubit each *input* qubit occupies at
the start (``initial_index_layout``) and at the end (``final_index_layout``) of
the returned circuit. A routing pass legitimately permutes qubits, so without
this the scorer could not tell a correctly-routed circuit from a wrong one.

The metadata is a *hint*, never an authority: the scorer verifies the circuit
against the input under the declared permutation, so a candidate that declares
a permutation it did not implement simply fails the equivalence gate.

This file deliberately lives outside every benchmark directory so that a
``copy_files.txt`` of ``.`` cannot drag it into the sandbox where a candidate
could rewrite it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any

CASE_INPUT = "case.json"
CIRCUIT_INPUT = "input.qasm"
CIRCUIT_OUTPUT = "submission.qasm"
META_OUTPUT = "submission_meta.json"
ERROR_OUTPUT = "candidate_error.txt"


def build_target(spec: dict[str, Any]) -> Any:
    """Rebuild the Qiskit ``Target`` inside the child from a JSON description."""
    kind = str(spec.get("kind", "none"))
    if kind == "none":
        return None
    if kind == "device":
        from mqt.bench.targets.devices import get_device  # noqa: PLC0415

        return get_device(str(spec["name"]))
    if kind == "gateset":
        from mqt.bench.targets.gatesets import get_target_for_gateset  # noqa: PLC0415

        return get_target_for_gateset(str(spec["name"]), int(spec["num_qubits"]))
    msg = f"unknown target spec kind: {kind!r}"
    raise ValueError(msg)


def load_optimize_circuit(solve_path: Path):
    """Import the candidate module and return its ``optimize_circuit``."""
    if not solve_path.is_file():
        msg = f"missing solver file: {solve_path}"
        raise FileNotFoundError(msg)

    solver_dir = str(solve_path.parent)
    if solver_dir not in sys.path:
        sys.path.insert(0, solver_dir)

    spec = importlib.util.spec_from_file_location("candidate_solve", solve_path)
    if spec is None or spec.loader is None:
        msg = f"failed to import solver from {solve_path}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["candidate_solve"] = module
    spec.loader.exec_module(module)

    optimize_circuit = getattr(module, "optimize_circuit", None)
    if not callable(optimize_circuit):
        msg = f"{solve_path} must define callable `optimize_circuit(input_circuit, target, case)`."
        raise AttributeError(msg)
    return optimize_circuit


def _index_list(values: Any, length: int | None = None) -> list[int] | None:
    if values is None:
        return None
    try:
        out = [int(v) for v in values]
    except Exception:
        return None
    if length is not None and len(out) != length:
        return None
    return out


def describe_layout(circuit: Any, num_input_qubits: int) -> dict[str, Any]:
    """Extract the input->physical qubit permutations from ``circuit.layout``.

    Returns ``initial_index_layout`` / ``final_index_layout`` as lists of length
    ``num_input_qubits`` (entry ``v`` is the physical qubit index carrying input
    qubit ``v`` at the start / end of the circuit), or ``None`` when the circuit
    carries no layout. A circuit with the same width as the input and no layout
    is treated by the scorer as the identity permutation.
    """
    meta: dict[str, Any] = {
        "num_qubits": int(circuit.num_qubits),
        "num_clbits": int(circuit.num_clbits),
        "initial_index_layout": None,
        "final_index_layout": None,
        "layout_present": False,
    }

    layout = getattr(circuit, "layout", None)
    if layout is None:
        if circuit.num_qubits == num_input_qubits:
            # Same width and no routing record: input qubit v is physical qubit
            # v. Declaring it explicitly lets the scorer compose this with its
            # own canonicalizing transpile, which may still map and route.
            meta["initial_index_layout"] = list(range(num_input_qubits))
            meta["final_index_layout"] = list(range(num_input_qubits))
        return meta
    meta["layout_present"] = True

    try:
        initial = layout.initial_index_layout(filter_ancillas=True)
    except Exception:
        initial = None
    meta["initial_index_layout"] = _index_list(initial, num_input_qubits)

    try:
        final = layout.final_index_layout(filter_ancillas=True)
    except Exception:
        try:
            final = layout.final_index_layout()
        except Exception:
            final = None
    final_list = _index_list(final)
    if final_list is not None and len(final_list) >= num_input_qubits:
        final_list = final_list[:num_input_qubits]
    elif final_list is not None and len(final_list) != num_input_qubits:
        final_list = None
    meta["final_index_layout"] = final_list

    return meta


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: qiskit_candidate_runner.py <path/to/solve.py>\n")
        return 2

    workdir = Path.cwd()
    solve_path = Path(sys.argv[1]).resolve()

    try:
        payload = json.loads((workdir / CASE_INPUT).read_text(encoding="utf-8"))
        case = payload["case"]
        target_spec = payload.get("target") or {"kind": "none"}

        from qiskit import qasm3  # noqa: PLC0415
        from qiskit.circuit import QuantumCircuit  # noqa: PLC0415

        input_qc = qasm3.loads((workdir / CIRCUIT_INPUT).read_text(encoding="utf-8"))
        num_input_qubits = input_qc.num_qubits
        target = build_target(target_spec)

        optimize_circuit = load_optimize_circuit(solve_path)
        result = optimize_circuit(input_qc.copy(), target, case)

        if not isinstance(result, QuantumCircuit):
            msg = f"optimize_circuit must return a QuantumCircuit, got {type(result).__name__}"
            raise TypeError(msg)

        meta = describe_layout(result, num_input_qubits)
        meta["input_num_qubits"] = int(num_input_qubits)

        # Serialize before writing the metadata so a failed export never leaves
        # a half-written submission behind.
        qasm_text = qasm3.dumps(result)
        (workdir / CIRCUIT_OUTPUT).write_text(qasm_text, encoding="utf-8")
        (workdir / META_OUTPUT).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception:
        detail = traceback.format_exc()
        try:
            (workdir / ERROR_OUTPUT).write_text(detail, encoding="utf-8")
        except Exception:
            pass
        sys.stderr.write(detail)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
