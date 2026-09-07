"""Integrity tests for the benchmarks/QuantumComputing evaluators.

Two defects made these three tasks unscoreable, and both are covered here.

1. No functional-equivalence check. ``evaluate_case`` went straight from
   "call the candidate" to "count gates", so the cost function (which rewards
   *fewer* gates) was maximized by returning the empty circuit. The archived
   top submission for task 01 is literally
   ``return QuantumCircuit(*input_circuit.qregs, *input_circuit.cregs)``,
   scoring 6.51 against an anchor of 3.0 for Qiskit's strongest transpiler.
   ``TestEmptyCircuitAttack`` measures that this now fails, end to end.

2. Same-process execution. ``utils.load_solver`` ``exec_module``-ed the
   candidate into the scoring interpreter, where a ``QuantumCircuit`` subclass
   with an overridden ``count_ops``/``depth`` could report whatever it liked.
   ``TestProcessIsolation`` covers the replacement contract.

These run the real evaluators against real MQT Bench circuits; there is no
mocking. Anything needing ``mqt.bench`` is skipped when it is unavailable.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
QC_ROOT = REPO_ROOT / "benchmarks" / "QuantumComputing"
TASK_01 = QC_ROOT / "task_01_routing_qftentangled"
TASK_02 = QC_ROOT / "task_02_clifford_t_synthesis"
TASK_03 = QC_ROOT / "task_03_cross_target_qaoa"

pytest.importorskip("qiskit", reason="qiskit is required for the QuantumComputing benchmarks")
pytest.importorskip("mqt.bench", reason="mqt.bench is required for the QuantumComputing benchmarks")

sys.path.insert(0, str(TASK_01 / "verification"))
sys.path.insert(0, str(REPO_ROOT / "benchmarks" / "_shared"))

import utils  # noqa: E402
from qiskit import qasm3, transpile  # noqa: E402
from qiskit.circuit import QuantumCircuit  # noqa: E402
from qiskit_candidate_runner import describe_layout  # noqa: E402

from mqt.bench import BenchmarkLevel, get_benchmark  # noqa: E402
from mqt.bench.targets.devices import get_device  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


EMPTY_CIRCUIT_SOLVER = '''
from qiskit.circuit import QuantumCircuit


def optimize_circuit(input_circuit, target, case):
    """The archived task-01 gold-medal submission, verbatim in spirit."""
    return QuantumCircuit(*input_circuit.qregs, *input_circuit.cregs)
'''

MEASURE_ONLY_SOLVER = '''
from qiskit.circuit import QuantumCircuit


def optimize_circuit(input_circuit, target, case):
    """Non-empty, but computes nothing: keeps only the measurements."""
    out = QuantumCircuit(*input_circuit.qregs, *input_circuit.cregs)
    for instruction in input_circuit.data:
        if instruction.operation.name == "measure":
            out.append(
                instruction.operation,
                [input_circuit.find_bit(q).index for q in instruction.qubits],
                [input_circuit.find_bit(c).index for c in instruction.clbits],
            )
    return out
'''

HONEST_SOLVER = '''
from qiskit import transpile


def optimize_circuit(input_circuit, target, case):
    if target is None:
        return input_circuit
    return transpile(input_circuit, target=target, optimization_level=3, seed_transpiler=11)
'''

LYING_METRICS_SOLVER = '''
from qiskit import transpile
from qiskit.circuit import QuantumCircuit


class TinyCircuit(QuantumCircuit):
    """Reports a cost of ~0 while carrying a real circuit."""

    def count_ops(self):
        return {}

    def depth(self, *args, **kwargs):
        return 0

    def size(self, *args, **kwargs):
        return 0


def optimize_circuit(input_circuit, target, case):
    real = transpile(input_circuit, target=target, optimization_level=3, seed_transpiler=11)
    fake = TinyCircuit(real.num_qubits, real.num_clbits)
    for instruction in real.data:
        fake.append(
            instruction.operation,
            [real.find_bit(q).index for q in instruction.qubits],
            [real.find_bit(c).index for c in instruction.clbits],
        )
    fake._layout = real._layout
    return fake
'''


def make_task_dir(tmp_path: Path, source_task: Path, solver_source: str) -> Path:
    """A throwaway copy of a task tree with ``baseline/solve.py`` replaced."""
    task_dir = tmp_path / source_task.name
    (task_dir / "baseline").mkdir(parents=True)
    (task_dir / "tests").mkdir(parents=True)
    shutil.copy2(source_task / "baseline" / "structural_optimizer.py", task_dir / "baseline")
    for case in sorted((source_task / "tests").glob("case_*.json")):
        shutil.copy2(case, task_dir / "tests")
    (task_dir / "baseline" / "solve.py").write_text(solver_source, encoding="utf-8")
    return task_dir


def load_evaluator(task_dir: Path):
    """Import a task's ``verification/evaluate.py`` under its own module name."""
    import importlib.util

    verification = task_dir / "verification"
    for entry in (str(verification), str(REPO_ROOT / "benchmarks" / "_shared")):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    spec = importlib.util.spec_from_file_location(
        f"evaluate_{task_dir.name}", verification / "evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def first_case(task_dir: Path) -> dict:
    return json.loads((task_dir / "tests" / "case_01.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def qft_input() -> QuantumCircuit:
    return get_benchmark(
        benchmark="qftentangled", level=BenchmarkLevel.INDEP, circuit_size=9, opt_level=0
    )


@pytest.fixture(scope="module")
def falcon():
    return get_device("ibm_falcon_27")


# ---------------------------------------------------------------------------
# The historical exploit, checked end to end.
# ---------------------------------------------------------------------------


class TestEmptyCircuitAttack:
    def test_empty_circuit_is_rejected_by_the_gate(self, qft_input: QuantumCircuit) -> None:
        empty = QuantumCircuit(*qft_input.qregs, *qft_input.cregs)
        report = utils.verify_circuit_equivalence(qft_input, empty, meta={}, mode="sampled")
        assert not report.ok
        assert "empty" in (report.reason or "")

    def test_measure_only_circuit_is_rejected(self, qft_input: QuantumCircuit) -> None:
        """A non-empty but content-free circuit must not slip past the size check."""
        stub = QuantumCircuit(*qft_input.qregs, *qft_input.cregs)
        stub.measure(range(qft_input.num_qubits), range(qft_input.num_qubits))
        report = utils.verify_circuit_equivalence(qft_input, stub, meta={}, mode="sampled")
        assert not report.ok
        assert report.fidelity < 0.01

    @pytest.mark.parametrize("solver", [EMPTY_CIRCUIT_SOLVER, MEASURE_ONLY_SOLVER])
    def test_task_01_evaluate_case_rejects(self, tmp_path: Path, solver: str) -> None:
        """The full task-01 pipeline: candidate subprocess, canonicalize, gate."""
        task_dir = make_task_dir(tmp_path, TASK_01, solver)
        evaluate = load_evaluator(TASK_01)
        result = evaluate.evaluate_case(first_case(TASK_01), task_dir, tmp_path / "artifacts")
        assert result["valid"] is False
        assert "not equivalent" in result["rejection_reason"]
        assert result["candidate"]["score_0_to_3"] is None

    def test_task_02_evaluate_case_rejects(self, tmp_path: Path) -> None:
        task_dir = make_task_dir(tmp_path, TASK_02, EMPTY_CIRCUIT_SOLVER)
        evaluate = load_evaluator(TASK_02)
        result = evaluate.evaluate_case(first_case(TASK_02), task_dir, tmp_path / "artifacts")
        assert result["valid"] is False
        assert "not equivalent" in result["rejection_reason"]

    def test_task_03_evaluate_case_rejects(self, tmp_path: Path) -> None:
        task_dir = make_task_dir(tmp_path, TASK_03, EMPTY_CIRCUIT_SOLVER)
        evaluate = load_evaluator(TASK_03)
        case = first_case(TASK_03)
        result = evaluate.evaluate_case_target(
            case, case["targets"][0], task_dir, tmp_path / "artifacts"
        )
        assert result["valid"] is False
        assert "not equivalent" in result["rejection_reason"]


# ---------------------------------------------------------------------------
# The gate must not punish honest work.
# ---------------------------------------------------------------------------


class TestHonestOptimizationPasses:
    def test_transpiled_circuit_passes(self, qft_input: QuantumCircuit, falcon) -> None:
        candidate = transpile(
            qft_input.copy(), target=falcon, optimization_level=3, seed_transpiler=7
        )
        meta = describe_layout(candidate, qft_input.num_qubits)
        transported = utils.normalize_transported_circuit(qasm3.loads(qasm3.dumps(candidate)))
        report = utils.verify_circuit_equivalence(
            qft_input, transported, meta=meta, mode="sampled"
        )
        assert report.ok, report.reason
        assert report.fidelity > 1.0 - 1e-9

    def test_task_01_evaluate_case_scores_an_honest_candidate(self, tmp_path: Path) -> None:
        task_dir = make_task_dir(tmp_path, TASK_01, HONEST_SOLVER)
        evaluate = load_evaluator(TASK_01)
        result = evaluate.evaluate_case(first_case(TASK_01), task_dir, tmp_path / "artifacts")
        assert result["valid"] is True, result.get("rejection_reason")
        assert result["candidate"]["cost"] > 0
        assert result["equivalence"]["fidelity"] > 1.0 - 1e-9

    def test_task_02_exact_gate_accepts_qiskit_opt3(self, tmp_path: Path) -> None:
        """Qiskit's own opt-3 anchor must pass, permutation elision included."""
        evaluate = load_evaluator(TASK_02)
        source = get_benchmark(benchmark="qft", level=BenchmarkLevel.ALG, circuit_size=4)
        input_qc = evaluate._strip_non_unitary_ops(source)
        reference = evaluate.transpile_to_clifford_t(input_qc.copy(), 3)
        report = utils.verify_circuit_equivalence(
            input_qc,
            reference,
            meta=describe_layout(reference, input_qc.num_qubits),
            mode="exact",
            allow_output_permutation=True,
        )
        assert report.ok, report.reason

    def test_transport_does_not_change_metrics(self, qft_input: QuantumCircuit, falcon) -> None:
        """Serializing through OpenQASM 3 must not shift a candidate's cost."""
        candidate = transpile(
            qft_input.copy(), target=falcon, optimization_level=3, seed_transpiler=7
        )
        direct = transpile(candidate, target=falcon, optimization_level=0, seed_transpiler=10)
        transported = utils.normalize_transported_circuit(qasm3.loads(qasm3.dumps(candidate)))
        through_qasm = transpile(
            transported, target=falcon, optimization_level=0, seed_transpiler=10
        )
        assert utils.compute_metrics(direct).to_dict() == utils.compute_metrics(through_qasm).to_dict()


# ---------------------------------------------------------------------------
# The gate must actually bite.
# ---------------------------------------------------------------------------


class TestGateIsEffective:
    def test_approximation_degree_is_rejected(self, qft_input: QuantumCircuit, falcon) -> None:
        """20 of 21 archived submissions traded fidelity for gate count this way."""
        lossy = transpile(
            qft_input.copy(),
            target=falcon,
            optimization_level=3,
            seed_transpiler=7,
            approximation_degree=0.9,
        )
        report = utils.verify_circuit_equivalence(
            qft_input, lossy, meta=describe_layout(lossy, qft_input.num_qubits), mode="sampled"
        )
        assert not report.ok
        assert report.fidelity < 0.99

    def test_a_declared_layout_cannot_be_a_lie(self, qft_input: QuantumCircuit, falcon) -> None:
        candidate = transpile(
            qft_input.copy(), target=falcon, optimization_level=3, seed_transpiler=7
        )
        honest = describe_layout(candidate, qft_input.num_qubits)
        lying = dict(honest)
        lying["initial_index_layout"] = list(reversed(honest["initial_index_layout"]))
        assert utils.verify_circuit_equivalence(
            qft_input, candidate, meta=honest, mode="sampled"
        ).ok
        assert not utils.verify_circuit_equivalence(
            qft_input, candidate, meta=lying, mode="sampled"
        ).ok

    def test_dropping_one_gate_is_caught(self, qft_input: QuantumCircuit, falcon) -> None:
        candidate = transpile(
            qft_input.copy(), target=falcon, optimization_level=3, seed_transpiler=7
        )
        meta = describe_layout(candidate, qft_input.num_qubits)
        maimed = QuantumCircuit(candidate.num_qubits, candidate.num_clbits)
        dropped = False
        for instruction in candidate.data:
            if not dropped and instruction.operation.name == "cx":
                dropped = True
                continue
            maimed.append(
                instruction.operation,
                [candidate.find_bit(q).index for q in instruction.qubits],
                [candidate.find_bit(c).index for c in instruction.clbits],
            )
        assert dropped
        report = utils.verify_circuit_equivalence(qft_input, maimed, meta=meta, mode="sampled")
        assert not report.ok

    def test_random_states_defeat_a_state_preparation_shortcut(
        self, qft_input: QuantumCircuit
    ) -> None:
        """A circuit that only reproduces the |0...0> output must still fail.

        Checking just the benchmark's own input state would let a candidate
        precompute the single output state and prepare it cheaply; the Haar
        random samples are what close that.
        """
        from qiskit.quantum_info import Statevector

        n = qft_input.num_qubits
        unitary_part, measure_map = utils._split_measurements(qft_input)
        target_state = Statevector.from_int(0, 2**n).evolve(unitary_part)

        shortcut = QuantumCircuit(n, qft_input.num_clbits)
        shortcut.prepare_state(target_state, list(range(n)))
        for clbit, qubit in measure_map.items():
            shortcut.measure(qubit, clbit)

        zero_only = utils.verify_circuit_equivalence(
            qft_input, shortcut, meta={}, mode="sampled", num_samples=0
        )
        with_randoms = utils.verify_circuit_equivalence(
            qft_input, shortcut, meta={}, mode="sampled", num_samples=4
        )
        assert zero_only.ok, "the |0...0> sample alone cannot tell these apart"
        assert not with_randoms.ok, "random input states must expose the shortcut"

    def test_exact_mode_rejects_a_wrong_small_circuit(self) -> None:
        source = get_benchmark(benchmark="qft", level=BenchmarkLevel.ALG, circuit_size=3)
        evaluate = load_evaluator(TASK_02)
        input_qc = evaluate._strip_non_unitary_ops(source)
        wrong = QuantumCircuit(3)
        wrong.h(0)
        wrong.cx(0, 1)
        report = utils.verify_circuit_equivalence(
            input_qc, wrong, meta={}, mode="exact", allow_output_permutation=True
        )
        assert not report.ok


# ---------------------------------------------------------------------------
# Process isolation.
# ---------------------------------------------------------------------------


class TestProcessIsolation:
    def test_load_solver_is_gone(self) -> None:
        with pytest.raises(RuntimeError, match="separate interpreter"):
            utils.load_solver(TASK_01)

    def test_candidate_runs_in_another_process(self, tmp_path: Path) -> None:
        task_dir = make_task_dir(tmp_path, TASK_01, HONEST_SOLVER)
        probe = (
            "import os\nfrom qiskit import transpile\n"
            "def optimize_circuit(input_circuit, target, case):\n"
            "    print('CHILD_PID', os.getpid())\n"
            "    return transpile(input_circuit, target=target, optimization_level=1)\n"
        )
        (task_dir / "baseline" / "solve.py").write_text(probe, encoding="utf-8")
        source = get_benchmark(
            benchmark="qftentangled", level=BenchmarkLevel.INDEP, circuit_size=9, opt_level=0
        )
        run = utils.run_candidate_circuit(
            task_dir,
            input_circuit=source,
            case=first_case(TASK_01),
            target_spec={"kind": "device", "name": "ibm_falcon_27"},
            timeout_s=600,
        )
        assert run.ok, run.error
        child_pid = int(run.stdout_tail.split("CHILD_PID")[1].split()[0])
        assert child_pid != os.getpid()

    def test_lying_count_ops_cannot_reach_the_scorer(self, tmp_path: Path) -> None:
        """Metrics come from re-parsed text, so an overridden count_ops is inert."""
        task_dir = make_task_dir(tmp_path, TASK_01, LYING_METRICS_SOLVER)
        evaluate = load_evaluator(TASK_01)
        result = evaluate.evaluate_case(first_case(TASK_01), task_dir, tmp_path / "artifacts")
        assert result["valid"] is True, result.get("rejection_reason")
        metrics = result["candidate"]["metrics"]
        assert metrics["size"] > 0
        assert metrics["depth"] > 0
        assert result["candidate"]["cost"] > 0

    def test_a_crashing_candidate_is_rejected_not_scored(self, tmp_path: Path) -> None:
        task_dir = make_task_dir(
            tmp_path, TASK_01, "def optimize_circuit(a, b, c):\n    raise SystemExit(0)\n"
        )
        evaluate = load_evaluator(TASK_01)
        result = evaluate.evaluate_case(first_case(TASK_01), task_dir, tmp_path / "artifacts")
        assert result["valid"] is False
        assert result["candidate"]["score_0_to_3"] is None

    def test_non_circuit_return_is_rejected(self, tmp_path: Path) -> None:
        task_dir = make_task_dir(
            tmp_path, TASK_01, "def optimize_circuit(a, b, c):\n    return 'not a circuit'\n"
        )
        run = utils.run_candidate_circuit(
            task_dir,
            input_circuit=get_benchmark(
                benchmark="qftentangled", level=BenchmarkLevel.INDEP, circuit_size=9, opt_level=0
            ),
            case=first_case(TASK_01),
            target_spec={"kind": "device", "name": "ibm_falcon_27"},
            timeout_s=600,
        )
        assert not run.ok
        assert run.circuit is None


# ---------------------------------------------------------------------------
# Verifier plumbing.
# ---------------------------------------------------------------------------


class TestVerifierGuards:
    def test_a_wide_circuit_without_a_layout_is_rejected(
        self, qft_input: QuantumCircuit
    ) -> None:
        wide = QuantumCircuit(27, qft_input.num_clbits)
        wide.h(range(27))
        report = utils.verify_circuit_equivalence(qft_input, wide, meta={}, mode="sampled")
        assert not report.ok
        assert "initial layout" in (report.reason or "")

    def test_too_many_active_qubits_is_rejected(self, qft_input: QuantumCircuit) -> None:
        wide = QuantumCircuit(27, qft_input.num_clbits)
        wide.h(range(27))
        for clbit in range(qft_input.num_clbits):
            wide.measure(clbit, clbit)
        report = utils.verify_circuit_equivalence(
            qft_input,
            wide,
            meta={"initial_index_layout": list(range(qft_input.num_qubits))},
            mode="sampled",
            max_active_qubits=22,
        )
        assert not report.ok
        assert "limit" in (report.reason or "")

    def test_reset_makes_a_circuit_unverifiable(self, qft_input: QuantumCircuit) -> None:
        with_reset = QuantumCircuit(*qft_input.qregs, *qft_input.cregs)
        with_reset.h(0)
        with_reset.reset(0)
        report = utils.verify_circuit_equivalence(qft_input, with_reset, meta={}, mode="sampled")
        assert not report.ok
        assert "reset" in (report.reason or "")

    def test_utils_is_identical_across_the_three_tasks(self) -> None:
        import hashlib

        digests = {
            task.name: hashlib.md5(
                (task / "verification" / "utils.py").read_bytes()
            ).hexdigest()
            for task in (TASK_01, TASK_02, TASK_03)
        }
        assert len(set(digests.values())) == 1, digests
