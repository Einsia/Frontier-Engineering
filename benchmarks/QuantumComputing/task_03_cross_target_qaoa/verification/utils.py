from __future__ import annotations

import importlib
import importlib.util
import itertools
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np


from qiskit import qasm3
from qiskit.circuit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.qasm2 import dump as dump_qasm2
from qiskit.quantum_info import Operator, Statevector


# --------------------------------------------------------------------------
# Repo-level plumbing: locate benchmarks/_shared so we can run candidates in a
# separate interpreter instead of exec_module-ing them into this one.
# --------------------------------------------------------------------------


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the Frontier-Engineering checkout root."""
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    base = (start or Path(__file__)).resolve()
    for parent in (base, *base.parents):
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    msg = f"could not locate repo root from {base}"
    raise RuntimeError(msg)


def shared_dir() -> Path:
    return find_repo_root() / "benchmarks" / "_shared"


def _import_sandbox():
    shared = str(shared_dir())
    if shared not in sys.path:
        sys.path.insert(0, shared)
    import candidate_sandbox  # noqa: PLC0415

    return candidate_sandbox


CANDIDATE_RUNNER = "qiskit_candidate_runner.py"


# --------------------------------------------------------------------------
# OpenQASM 3 transport normalization.
#
# Qiskit's OpenQASM 3 exporter has to inline a fresh `gate` definition for every
# distinct parameter binding of a gate that is not in `stdgates.inc` (IonQ's
# gpi/gpi2/ms, for instance). Re-importing therefore yields hundreds of opaque
# one-off gates named `gpi2_37`, and the evaluator's canonicalizing transpile
# then re-synthesizes each of them from scratch -- inflating an honest IonQ
# candidate's depth from 163 to 629 purely as a serialization artifact.
#
# So after parsing we put the canonical gate object back, but only when the
# imported definition really is that gate (checked against its matrix). A
# candidate cannot use this to smuggle anything in: a mislabelled block fails
# the matrix check and stays opaque, and an opaque block is unrolled by the
# canonicalizing transpile just as it was before.
# --------------------------------------------------------------------------

_MANGLED_SUFFIX = re.compile(r"_\d+$")


def _gate_class_name(klass: Any) -> str:
    """Best-effort OpenQASM name for a gate class (``GPI2Gate`` -> ``gpi2``)."""
    name = klass.__name__
    if name.endswith("Gate"):
        name = name[: -len("Gate")]
    return name.lower()


def _known_gate_factories() -> dict[str, Any]:
    factories: dict[str, Any] = {}
    try:
        from qiskit.circuit.library.standard_gates import (  # noqa: PLC0415
            get_standard_gate_name_mapping,
        )

        for name, instance in get_standard_gate_name_mapping().items():
            factories[name] = type(instance)
    except Exception:  # pragma: no cover - qiskit always provides this
        pass
    for module_name in ("ionq", "rigetti"):
        try:
            module = importlib.import_module(f"mqt.bench.targets.gatesets.{module_name}")
        except Exception:
            continue
        for attribute in dir(module):
            if not attribute.endswith("Gate"):
                continue
            klass = getattr(module, attribute)
            if isinstance(klass, type):
                factories.setdefault(_gate_class_name(klass), klass)
    return factories


_GATE_FACTORIES: dict[str, Any] | None = None


def gate_factories() -> dict[str, Any]:
    global _GATE_FACTORIES  # noqa: PLW0603
    if _GATE_FACTORIES is None:
        _GATE_FACTORIES = _known_gate_factories()
    return _GATE_FACTORIES


def normalize_transported_circuit(qc: QuantumCircuit) -> QuantumCircuit:
    """Undo the exporter's per-binding gate duplication, matrix-checked."""
    factories = gate_factories()
    replacements: dict[int, Any] = {}

    for position, instruction in enumerate(qc.data):
        op = instruction.operation
        if op.num_qubits > 2 or instruction.clbits or getattr(op, "definition", None) is None:
            continue
        base = _MANGLED_SUFFIX.sub("", op.name)
        for name in (op.name, base):
            factory = factories.get(name)
            if factory is None or isinstance(op, factory):
                continue
            try:
                rebuilt_gate = factory(*op.params)
                if rebuilt_gate.num_qubits != op.num_qubits:
                    continue
                if np.allclose(Operator(rebuilt_gate).data, Operator(op).data, atol=1e-10):
                    replacements[position] = rebuilt_gate
                    break
            except Exception:
                continue

    if not replacements:
        return qc

    # The parsed circuit generally has loose bits rather than registers, so
    # rebuild by index rather than by bit object.
    rebuilt = QuantumCircuit(qc.num_qubits, qc.num_clbits, name=qc.name)
    rebuilt.global_phase = qc.global_phase
    for position, instruction in enumerate(qc.data):
        rebuilt.append(
            replacements.get(position, instruction.operation),
            [qc.find_bit(q).index for q in instruction.qubits],
            [qc.find_bit(c).index for c in instruction.clbits],
        )
    rebuilt._layout = getattr(qc, "_layout", None)
    return rebuilt


@dataclass(frozen=True)
class CircuitMetrics:
    depth: int
    size: int
    two_qubit_count: int
    cx_count: int
    ecr_count: int
    swap_count: int
    t_count: int
    tdg_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_metrics(qc: QuantumCircuit) -> CircuitMetrics:
    ops = qc.count_ops()
    two_qubit_gate_names = {"cx", "cz", "ecr", "swap", "rzz", "zz", "ms"}
    two_qubit_count = sum(int(count) for gate, count in ops.items() if gate.lower() in two_qubit_gate_names)
    return CircuitMetrics(
        depth=qc.depth(),
        size=qc.size(),
        two_qubit_count=two_qubit_count,
        cx_count=int(ops.get("cx", 0)),
        ecr_count=int(ops.get("ecr", 0)),
        swap_count=int(ops.get("swap", 0)),
        t_count=int(ops.get("t", 0)),
        tdg_count=int(ops.get("tdg", 0)),
    )


def timed_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, float]:
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


def load_cases(task_dir: Path) -> list[dict[str, Any]]:
    tests_dir = task_dir / "tests"
    case_paths = sorted(tests_dir.glob("case_*.json"))
    if not case_paths:
        raise FileNotFoundError(f"No test case files found in {tests_dir}.")
    return [json.loads(path.read_text(encoding="utf-8")) for path in case_paths]


# --------------------------------------------------------------------------
# Candidate execution: separate process, text-only result.
# --------------------------------------------------------------------------


class CandidateRejected(ValueError):
    """The candidate produced nothing the scorer is willing to score."""


@dataclass
class CandidateRun:
    """What the scorer is allowed to know about one candidate invocation."""

    circuit: QuantumCircuit | None
    meta: dict[str, Any] = field(default_factory=dict)
    runtime_s: float = 0.0
    error: str | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""

    @property
    def ok(self) -> bool:
        return self.circuit is not None and self.error is None


def candidate_path(task_dir: Path) -> Path:
    return task_dir / "baseline" / "solve.py"


def serializable_input_circuit(qc: QuantumCircuit) -> QuantumCircuit:
    """Rebuild ``qc`` on plain registers so its OpenQASM 3 stays register-based.

    Qiskit's exporter switches to physical-qubit syntax (``$3``) whenever the
    circuit carries a ``layout``, and the importer then produces a circuit with
    loose bits and no ``qregs`` -- which breaks ordinary candidate code such as
    ``QuantumCircuit(*input_circuit.qregs, *input_circuit.cregs)``. The inputs
    for these tasks are algorithm-level circuits whose layout attribute is a
    leftover from how MQT Bench built them and carries no meaning here, so drop
    it before handing the circuit across the process boundary.
    """
    rebuilt = QuantumCircuit(
        QuantumRegister(qc.num_qubits, "q"),
        *([ClassicalRegister(qc.num_clbits, "meas")] if qc.num_clbits else []),
        name=qc.name,
    )
    rebuilt.global_phase = qc.global_phase
    for instruction in qc.data:
        rebuilt.append(
            instruction.operation,
            [qc.find_bit(q).index for q in instruction.qubits],
            [qc.find_bit(c).index for c in instruction.clbits],
        )
    return rebuilt


def run_candidate_circuit(
    task_dir: Path,
    *,
    input_circuit: QuantumCircuit,
    case: dict[str, Any],
    target_spec: dict[str, Any] | None = None,
    timeout_s: float = 600.0,
) -> CandidateRun:
    """Run ``baseline/solve.py`` in its own interpreter and parse back its QASM.

    The candidate never shares a process with the scorer. It receives the input
    circuit as OpenQASM 3 text plus a JSON description of the target, and it
    returns OpenQASM 3 text plus a small JSON layout descriptor. Everything the
    scorer subsequently measures is rebuilt here, in this clean process, from
    that text -- so a ``QuantumCircuit`` subclass with a lying ``count_ops()``
    or ``depth()`` cannot survive the crossing.
    """
    sandbox = _import_sandbox()
    runner = shared_dir() / CANDIDATE_RUNNER
    if not runner.is_file():
        msg = f"missing candidate runner: {runner}"
        raise FileNotFoundError(msg)

    solve_path = candidate_path(task_dir)
    if not solve_path.is_file():
        return CandidateRun(circuit=None, error=f"missing solver file: {solve_path}")

    payload = {
        "case": case,
        "target": target_spec or {"kind": "none"},
    }
    try:
        input_qasm = qasm3.dumps(serializable_input_circuit(input_circuit))
    except Exception as exc:  # pragma: no cover - would be a harness bug
        msg = f"could not export input circuit to OpenQASM 3: {exc}"
        raise RuntimeError(msg) from exc

    start = time.perf_counter()
    try:
        run = sandbox.run_candidate_isolated(
            runner,
            inputs={
                "case.json": json.dumps(payload).encode("utf-8"),
                "input.qasm": input_qasm.encode("utf-8"),
            },
            expected_outputs=("submission.qasm", "submission_meta.json"),
            timeout_s=timeout_s,
            argv=(str(solve_path.resolve()),),
            copy_into_workdir=False,
        )
    except sandbox.InvalidSubmissionError as exc:
        return CandidateRun(circuit=None, runtime_s=time.perf_counter() - start, error=str(exc))

    runtime_s = run.runtime_s
    if run.timed_out:
        return CandidateRun(
            circuit=None,
            runtime_s=runtime_s,
            error=f"candidate timed out after {timeout_s}s",
            stdout_tail=run.stdout_tail,
            stderr_tail=run.stderr_tail,
        )
    if run.returncode != 0:
        return CandidateRun(
            circuit=None,
            runtime_s=runtime_s,
            error=f"candidate exited non-zero ({run.returncode})",
            stdout_tail=run.stdout_tail,
            stderr_tail=run.stderr_tail,
        )

    try:
        qasm_text = run.read_output_bytes("submission.qasm").decode("utf-8")
        meta = json.loads(run.read_output_bytes("submission_meta.json").decode("utf-8"))
    except Exception as exc:
        return CandidateRun(
            circuit=None,
            runtime_s=runtime_s,
            error=f"unreadable candidate output: {exc}",
            stdout_tail=run.stdout_tail,
            stderr_tail=run.stderr_tail,
        )

    if not isinstance(meta, dict):
        return CandidateRun(circuit=None, runtime_s=runtime_s, error="submission_meta.json is not an object")

    try:
        circuit = normalize_transported_circuit(qasm3.loads(qasm_text))
    except Exception as exc:
        return CandidateRun(
            circuit=None,
            runtime_s=runtime_s,
            error=f"submission.qasm is not parseable OpenQASM 3: {exc}",
            stdout_tail=run.stdout_tail,
            stderr_tail=run.stderr_tail,
        )

    return CandidateRun(
        circuit=circuit,
        meta=meta,
        runtime_s=runtime_s,
        stdout_tail=run.stdout_tail,
        stderr_tail=run.stderr_tail,
    )


def load_solver(task_dir: Path) -> Callable[..., QuantumCircuit]:  # pragma: no cover
    """Removed on purpose.

    Loading the candidate with ``exec_module`` put it in the scorer's process,
    where it could return a ``QuantumCircuit`` subclass with an overridden
    ``count_ops`` / ``depth`` / ``size`` and score itself. Use
    :func:`run_candidate_circuit` instead.
    """
    msg = (
        "load_solver() has been removed: candidates must run in a separate "
        "interpreter. Use run_candidate_circuit(task_dir, ...) instead."
    )
    raise RuntimeError(msg)


# --------------------------------------------------------------------------
# Functional-equivalence gate.
#
# Scoring a circuit optimizer on gate counts alone rewards returning the empty
# circuit (cost 0 beats every anchor). Every metric below is therefore gated on
# the candidate actually computing the input circuit's unitary, up to the qubit
# permutation it declares (routing legitimately permutes qubits) and up to a
# global phase.
# --------------------------------------------------------------------------

# Ops that carry no unitary content and can be dropped before comparison.
_TRANSPARENT_OPS = {"barrier", "delay", "id"}
# Ops that make "the circuit implements a unitary" false, so we refuse to score.
_NON_UNITARY_OPS = {
    "reset",
    "initialize",
    "if_else",
    "while_loop",
    "for_loop",
    "switch_case",
    "break_loop",
    "continue_loop",
    "box",
    "store",
}

DEFAULT_FIDELITY_THRESHOLD = 1.0 - 1e-9
DEFAULT_SAMPLES = 4
DEFAULT_MAX_ACTIVE_QUBITS = 24


@dataclass(frozen=True)
class EquivalenceReport:
    ok: bool
    method: str
    fidelity: float
    threshold: float
    samples: int
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _split_measurements(qc: QuantumCircuit) -> tuple[QuantumCircuit, dict[int, int]]:
    """Split into (unitary part on the same qubits, clbit index -> qubit index).

    Raises ``CandidateRejected`` for anything that is not unitary + terminal
    measurement, because the scorer cannot reason about such a circuit.
    """
    unitary = QuantumCircuit(qc.num_qubits, name=f"{qc.name}_u")
    unitary.global_phase = qc.global_phase
    measure_map: dict[int, int] = {}
    measured_qubits: set[int] = set()

    for instruction in qc.data:
        op = instruction.operation
        name = op.name
        if getattr(op, "condition", None) is not None or (instruction.clbits and name != "measure"):
            msg = f"classically-conditioned operation {name!r} cannot be verified"
            raise CandidateRejected(msg)
        qubit_indices = [qc.find_bit(q).index for q in instruction.qubits]
        if name == "measure":
            clbit = qc.find_bit(instruction.clbits[0]).index
            measure_map[clbit] = qubit_indices[0]
            measured_qubits.add(qubit_indices[0])
            continue
        if name in _TRANSPARENT_OPS:
            continue
        if name in _NON_UNITARY_OPS:
            msg = f"non-unitary operation {name!r} cannot be verified"
            raise CandidateRejected(msg)
        if qubit_indices and measured_qubits.intersection(qubit_indices):
            msg = f"operation {name!r} acts on an already-measured qubit; mid-circuit measurement is not supported"
            raise CandidateRejected(msg)
        unitary.append(op.copy(), qubit_indices, [])

    return unitary, measure_map


def _active_qubits(qc: QuantumCircuit) -> set[int]:
    active: set[int] = set()
    for instruction in qc.data:
        if instruction.operation.name in _TRANSPARENT_OPS:
            continue
        for qubit in instruction.qubits:
            active.add(qc.find_bit(qubit).index)
    return active


def _restrict(qc: QuantumCircuit, active: Sequence[int]) -> QuantumCircuit:
    """Relabel ``qc`` onto just its active qubits (idle qubits are identity)."""
    position = {physical: i for i, physical in enumerate(active)}
    reduced = QuantumCircuit(len(active), name=f"{qc.name}_r")
    reduced.global_phase = qc.global_phase
    for instruction in qc.data:
        if instruction.operation.name in _TRANSPARENT_OPS:
            continue
        reduced.append(
            instruction.operation.copy(),
            [position[qc.find_bit(q).index] for q in instruction.qubits],
            [],
        )
    return reduced


def _placement_index(positions: Sequence[int], width: int) -> np.ndarray:
    """Map an ``len(positions)``-qubit basis index to a ``width``-qubit one.

    Qiskit's statevector convention is little-endian: bit ``v`` of the index is
    qubit ``v``. ``positions[v]`` is the wide-circuit qubit holding qubit ``v``;
    every other wide qubit is left in ``|0>``.
    """
    n = len(positions)
    base = np.arange(1 << n, dtype=np.int64)
    idx = np.zeros(1 << n, dtype=np.int64)
    for v, p in enumerate(positions):
        idx |= ((base >> v) & 1) << int(p)
    return idx


def _random_states(n: int, count: int, seed: int) -> list[np.ndarray]:
    """``|0...0>`` first, then Haar-random states.

    ``|0...0>`` is the state these benchmark circuits actually run on, so it is
    always checked; the random states are what make the check a *process*
    check rather than a single-input check, which is what stops a candidate
    from replacing the algorithm with a cheap preparation of its one output
    state.
    """
    rng = np.random.default_rng(seed)
    dim = 1 << n
    states = [np.zeros(dim, dtype=complex)]
    states[0][0] = 1.0
    for _ in range(count):
        vec = rng.normal(size=dim) + 1j * rng.normal(size=dim)
        vec /= np.linalg.norm(vec)
        states.append(vec)
    return states


def _resolve_positions(
    input_qc: QuantumCircuit,
    input_measure_map: dict[int, int],
    candidate_qc: QuantumCircuit,
    candidate_measure_map: dict[int, int],
    meta: dict[str, Any],
) -> tuple[list[int], list[int]]:
    """Work out where each input qubit lives at the start and end of the candidate."""
    n = input_qc.num_qubits
    width = candidate_qc.num_qubits

    def _clean(key: str) -> list[int] | None:
        raw = meta.get(key)
        if raw is None:
            return None
        try:
            values = [int(v) for v in raw]
        except Exception:
            return None
        if len(values) != n or any(v < 0 or v >= width for v in values):
            return None
        if len(set(values)) != n:
            return None
        return values

    initial = _clean("initial_index_layout")
    if initial is None:
        if width < n:
            msg = f"candidate circuit has {width} qubits, fewer than the input's {n}"
            raise CandidateRejected(msg)
        if width != n:
            msg = (
                f"candidate circuit is wider than the input ({width} vs {n} qubits) but declares no "
                "initial layout; return the circuit produced by transpile() (or keep its .layout) so "
                "the scorer can tell which physical qubit holds which input qubit"
            )
            raise CandidateRejected(msg)
        initial = list(range(n))

    # The end of the circuit is pinned by the measurements when there are any:
    # that is the mapping the hardware actually reports, and unlike the declared
    # layout the candidate cannot quietly disagree with it.
    final: list[int] | None = None
    if input_measure_map:
        resolved: list[int | None] = [None] * n
        for clbit, in_qubit in input_measure_map.items():
            if in_qubit >= n:
                continue
            if clbit not in candidate_measure_map:
                msg = (
                    f"candidate never measures classical bit {clbit}; the input circuit measures "
                    f"{len(input_measure_map)} bit(s) and the optimized circuit must measure the same ones"
                )
                raise CandidateRejected(msg)
            resolved[in_qubit] = candidate_measure_map[clbit]
        if all(v is not None for v in resolved) and len(set(resolved)) == n:
            final = [int(v) for v in resolved]  # type: ignore[arg-type]

    if final is None:
        final = _clean("final_index_layout")
    if final is None:
        final = list(initial)

    return initial, final


def _fidelity(expected: np.ndarray, actual: np.ndarray) -> float:
    """Global-phase-invariant state fidelity."""
    overlap = complex(np.vdot(expected, actual))
    return float(min(1.0, abs(overlap) ** 2))


def verify_circuit_equivalence(
    input_circuit: QuantumCircuit,
    candidate_circuit: QuantumCircuit,
    *,
    meta: dict[str, Any] | None = None,
    mode: str = "sampled",
    threshold: float = DEFAULT_FIDELITY_THRESHOLD,
    num_samples: int = DEFAULT_SAMPLES,
    max_active_qubits: int = DEFAULT_MAX_ACTIVE_QUBITS,
    seed: int = 20240917,
    allow_output_permutation: bool = False,
) -> EquivalenceReport:
    """Hard gate: does ``candidate_circuit`` implement ``input_circuit``?

    ``mode="exact"`` builds the candidate's full effective unitary (only viable
    for the small Clifford+T cases) and compares process fidelity.
    ``mode="sampled"`` evolves ``|0...0>`` plus ``num_samples`` Haar-random
    input states through both circuits and takes the worst per-state fidelity.

    Both modes account for the qubit permutation a routing pass introduces, and
    both ignore global phase. ``allow_output_permutation`` additionally accepts
    a circuit that is correct up to an *undeclared* relabelling of the output
    qubits (only affordable when ``n!`` is small); a permutation is free to undo
    in classical post-processing, so it is not an optimization loophole.
    """
    meta = meta or {}
    n = input_circuit.num_qubits
    if n == 0:
        return EquivalenceReport(False, mode, 0.0, threshold, 0, reason="input circuit has no qubits")

    try:
        input_unitary, input_measure_map = _split_measurements(input_circuit)
    except CandidateRejected as exc:  # pragma: no cover - would be a harness bug
        msg = f"input circuit is not verifiable: {exc}"
        raise RuntimeError(msg) from exc

    # Cheap structural pre-checks. These alone reject the empty circuit, which
    # is the exploit that historically topped this leaderboard.
    if candidate_circuit.size() == 0:
        return EquivalenceReport(
            False, mode, 0.0, threshold, 0, reason="candidate circuit is empty (0 operations)"
        )
    if candidate_circuit.num_qubits < n:
        return EquivalenceReport(
            False,
            mode,
            0.0,
            threshold,
            0,
            reason=f"candidate has {candidate_circuit.num_qubits} qubits, fewer than the input's {n}",
        )

    try:
        candidate_unitary, candidate_measure_map = _split_measurements(candidate_circuit)
        initial, final = _resolve_positions(
            input_circuit, input_measure_map, candidate_circuit, candidate_measure_map, meta
        )
    except CandidateRejected as exc:
        return EquivalenceReport(False, mode, 0.0, threshold, 0, reason=str(exc))

    active = sorted(_active_qubits(candidate_unitary) | set(initial) | set(final))
    width = len(active)
    if width > max_active_qubits:
        return EquivalenceReport(
            False,
            mode,
            0.0,
            threshold,
            0,
            reason=(
                f"candidate touches {width} qubits, more than the verifier's limit of "
                f"{max_active_qubits}; the equivalence check would not fit in memory"
            ),
        )

    reduced = _restrict(candidate_unitary, active)
    position = {physical: i for i, physical in enumerate(active)}
    in_positions = [position[p] for p in initial]
    out_positions = [position[p] for p in final]

    in_index = _placement_index(in_positions, width)
    details: dict[str, Any] = {
        "input_num_qubits": n,
        "candidate_num_qubits": candidate_circuit.num_qubits,
        "active_qubits": width,
        "initial_index_layout": list(initial),
        "final_index_layout": list(final),
        "layout_declared": bool(meta.get("layout_present")),
    }

    def _evolve(vec_n: np.ndarray) -> np.ndarray:
        full = np.zeros(1 << width, dtype=complex)
        full[in_index] = vec_n
        return np.asarray(Statevector(full).evolve(reduced).data)

    if mode == "exact":
        if n > 8 or width > 12:
            msg = f"exact mode is not affordable for n={n}, width={width}"
            raise ValueError(msg)
        columns = np.stack([_evolve(col) for col in np.eye(1 << n, dtype=complex)], axis=1)
        target = Operator(input_unitary).data

        def _score(perm: Sequence[int]) -> float:
            out_idx = _placement_index([out_positions[p] for p in perm], width)
            effective = columns[out_idx, :]
            trace = np.trace(target.conj().T @ effective)
            return float(min(1.0, abs(trace) ** 2 / float(1 << (2 * n))))

        identity = tuple(range(n))
        best_perm = identity
        best = _score(identity)
        if best <= threshold and allow_output_permutation:
            for perm in itertools.permutations(range(n)):
                if perm == identity:
                    continue
                value = _score(perm)
                if value > best:
                    best, best_perm = value, perm
                if best > threshold:
                    break
        details["output_permutation"] = list(best_perm)
        details["permutation_searched"] = allow_output_permutation and best_perm != identity
        ok = best > threshold
        reason = None if ok else f"process fidelity {best:.12f} <= threshold {threshold:.12f}"
        return EquivalenceReport(ok, "exact_process_fidelity", best, threshold, 1 << n, reason, details)

    if mode != "sampled":
        msg = f"unknown equivalence mode: {mode!r}"
        raise ValueError(msg)

    out_index = _placement_index(out_positions, width)
    worst = 1.0
    fidelities: list[float] = []
    for vec in _random_states(n, num_samples, seed):
        expected_small = np.asarray(Statevector(vec).evolve(input_unitary).data)
        expected = np.zeros(1 << width, dtype=complex)
        expected[out_index] = expected_small
        value = _fidelity(expected, _evolve(vec))
        fidelities.append(value)
        worst = min(worst, value)

    details["fidelities"] = fidelities
    ok = worst > threshold
    reason = None if ok else f"worst-case state fidelity {worst:.12f} <= threshold {threshold:.12f}"
    return EquivalenceReport(
        ok, "sampled_state_fidelity", worst, threshold, len(fidelities), reason, details
    )


def compose_candidate_layout(
    canonical: QuantumCircuit,
    meta: dict[str, Any],
    num_input_qubits: int,
) -> dict[str, Any]:
    """Push a candidate's declared layout through the evaluator's canonicalization.

    The candidate's raw circuit declares, per input qubit, which of *its* qubits
    holds that input qubit at the start and at the end. The scorer then
    canonicalizes that raw circuit with ``transpile``, which may relabel and
    re-route it a second time; ``canonical.layout`` describes that second
    mapping, from raw qubit index to canonical qubit index. Since the metrics
    are measured on the canonical circuit, the equivalence check must run on it
    too, and therefore needs the composition of the two mappings.
    """
    composed = dict(meta)

    def _clean(key: str) -> list[int] | None:
        raw = meta.get(key)
        if raw is None:
            return None
        try:
            values = [int(v) for v in raw]
        except Exception:
            return None
        return values if len(values) == num_input_qubits else None

    inner_initial = _clean("initial_index_layout")
    inner_final = _clean("final_index_layout")
    if inner_initial is None and inner_final is None:
        # No declaration to carry through. A same-width circuit is treated as
        # the identity by the verifier; a wider one is rejected there.
        return composed
    if inner_initial is None:
        inner_initial = list(inner_final or [])
    if inner_final is None:
        inner_final = list(inner_initial)

    layout = getattr(canonical, "layout", None)
    outer_initial: list[int] | None = None
    outer_final: list[int] | None = None
    if layout is not None:
        try:
            outer_initial = list(layout.initial_index_layout())
        except Exception:
            outer_initial = None
        try:
            outer_final = list(layout.final_index_layout())
        except Exception:
            outer_final = None

    def _apply(mapping: Sequence[int] | None, positions: Sequence[int]) -> list[int]:
        if mapping is None:
            return [int(p) for p in positions]
        return [int(mapping[p]) if 0 <= p < len(mapping) else int(p) for p in positions]

    composed["initial_index_layout"] = _apply(outer_initial, inner_initial)
    composed["final_index_layout"] = _apply(outer_final, inner_final)
    return composed


def rejected_case_result(case_id: str, reason: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Uniform 'this candidate is not scoreable' record."""
    payload: dict[str, Any] = {
        "case_id": case_id,
        "valid": False,
        "rejection_reason": reason,
        "candidate": {
            "cost": None,
            "score_0_to_3": None,
            "metrics": None,
        },
    }
    if extra:
        payload.update(extra)
    return payload


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True, default=str), encoding="utf-8")


def create_run_dir(task_dir: Path, prefix: str = "run") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = task_dir / "runs" / f"{prefix}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_circuit_qasm(qc: QuantumCircuit, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as handle:
            dump_qasm2(qc, handle)
    except Exception as exc:
        path.with_suffix(".qasm_error.txt").write_text(
            f"Failed to export QASM2: {exc}\n",
            encoding="utf-8",
        )


def save_circuit_image(
    qc: QuantumCircuit,
    path: Path,
    *,
    max_qubits: int = 40,
    max_size: int = 4000,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if qc.num_qubits > max_qubits or qc.size() > max_size:
        note = (
            f"Skipped PNG rendering (num_qubits={qc.num_qubits}, size={qc.size()}) "
            f"because it exceeds limits max_qubits={max_qubits}, max_size={max_size}.\n"
        )
        path.with_suffix(".image_skipped.txt").write_text(note, encoding="utf-8")
        return

    try:
        import matplotlib.pyplot as plt  # noqa: PLC0415
    except Exception as exc:
        path.with_suffix(".image_error.txt").write_text(
            f"Failed to import matplotlib for circuit drawing: {exc}\n",
            encoding="utf-8",
        )
        return

    try:
        figure = qc.draw(output="mpl", fold=-1, idle_wires=False)
        figure.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(figure)
    except Exception as exc:
        path.with_suffix(".image_error.txt").write_text(
            f"Failed to render circuit image: {exc}\n",
            encoding="utf-8",
        )


def save_circuit_artifacts(
    qc: QuantumCircuit,
    output_dir: Path,
    stem: str,
    *,
    save_image: bool = True,
    max_qubits_for_image: int = 40,
    max_size_for_image: int = 4000,
) -> None:
    save_circuit_qasm(qc, output_dir / f"{stem}.qasm")
    if save_image:
        save_circuit_image(
            qc,
            output_dir / f"{stem}.png",
            max_qubits=max_qubits_for_image,
            max_size=max_size_for_image,
        )
