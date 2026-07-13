"""Independent evaluator for proof-carrying AIG resynthesis candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TASK_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = TASK_DIR / "references" / "problem_config.json"
BASELINE_PATH = TASK_DIR / "baseline" / "solution.cpp"
START_MARKER = "// EVOLVE-BLOCK-START"
END_MARKER = "// EVOLVE-BLOCK-END"


class EvaluationError(RuntimeError):
    """A deterministic candidate, certificate, or benchmark validation failure."""


def _strict_json(path: Path) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is not allowed: {value}")

    data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    if not isinstance(data, dict):
        raise ValueError("configuration root must be an object")
    return data


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _validated_config() -> dict[str, Any]:
    config = _strict_json(CONFIG_PATH)
    if config.get("benchmark_id") != "certified_aig_resynthesis":
        raise ValueError("unexpected benchmark_id")
    objective = config.get("objective")
    limits = config.get("limits")
    workloads = config.get("workloads")
    if not isinstance(objective, dict) or not isinstance(limits, dict):
        raise ValueError("objective and limits must be objects")
    if not isinstance(workloads, list) or not workloads:
        raise ValueError("workloads must be a non-empty list")
    area_weight = _finite_float(objective.get("area_weight"), "area_weight")
    depth_weight = _finite_float(objective.get("depth_weight"), "depth_weight")
    if area_weight <= 0.0 or depth_weight <= 0.0:
        raise ValueError("objective weights must be positive")
    if not math.isclose(area_weight + depth_weight, 1.0, abs_tol=1e-12):
        raise ValueError("objective weights must sum to one")
    for key in (
        "max_candidate_bytes",
        "max_certificate_bytes",
        "max_cut_leaves",
        "max_divisors",
        "max_local_ands",
        "max_rewrites",
        "max_total_nodes",
    ):
        _positive_int(limits.get(key), key)
    _finite_float(limits.get("candidate_timeout_s_per_workload"), "candidate timeout")
    _finite_float(limits.get("compile_timeout_s"), "compile timeout")
    ids: set[str] = set()
    for index, workload in enumerate(workloads):
        if not isinstance(workload, dict):
            raise ValueError(f"workloads[{index}] must be an object")
        workload_id = str(workload.get("id", "")).strip()
        kind = str(workload.get("kind", "")).strip()
        if not workload_id or workload_id in ids or not kind:
            raise ValueError(f"invalid or duplicate workload at index {index}")
        ids.add(workload_id)
    return config


class AigBuilder:
    """Small deterministic Boolean front end that emits raw ASCII AIGER."""

    def __init__(self, input_count: int) -> None:
        if input_count <= 0:
            raise ValueError("an AIG workload needs at least one input")
        self.input_count = input_count
        self.inputs = [2 * node_id for node_id in range(1, input_count + 1)]
        self.ands: list[tuple[int, int]] = []
        self.outputs: list[int] = []
        self._lowering_index = 0

    @staticmethod
    def inv(literal: int) -> int:
        return literal ^ 1

    def and_gate(self, lhs: int, rhs: int) -> int:
        node_id = self.input_count + len(self.ands) + 1
        self.ands.append((lhs, rhs))
        return node_id * 2

    def or_gate(self, lhs: int, rhs: int) -> int:
        return self.inv(self.and_gate(self.inv(lhs), self.inv(rhs)))

    def xor_gate(self, lhs: int, rhs: int) -> int:
        lhs_only = self.and_gate(lhs, self.inv(rhs))
        rhs_only = self.and_gate(self.inv(lhs), rhs)
        return self.or_gate(lhs_only, rhs_only)

    def mux(self, select: int, when_true: int, when_false: int) -> int:
        selected_true = self.and_gate(select, when_true)
        selected_false = self.and_gate(self.inv(select), when_false)
        return self.or_gate(selected_true, selected_false)

    def lower_equivalent(self, literal: int, guard: int, period: int) -> int:
        """Model common front-end lowering patterns without changing semantics."""
        index = self._lowering_index
        self._lowering_index += 1
        if period <= 0 or index % period != 0:
            return literal
        mode = (index // period) % 6
        if mode == 0:
            return self.and_gate(literal, 1)  # x & true
        if mode == 1:
            return self.or_gate(literal, 0)  # x | false
        if mode == 2:
            return self.mux(guard, literal, literal)
        if mode == 3:
            return self.or_gate(literal, self.and_gate(literal, guard))
        if mode == 4:
            return self.and_gate(literal, self.or_gate(literal, guard))
        true_arm = self.and_gate(literal, 1)
        false_arm = self.or_gate(literal, 0)
        return self.mux(guard, true_arm, false_arm)

    def to_aag(self) -> bytes:
        if not self.outputs:
            raise ValueError("AIG workload has no outputs")
        maximum = self.input_count + len(self.ands)
        lines = [
            f"aag {maximum} {self.input_count} 0 {len(self.outputs)} {len(self.ands)}"
        ]
        lines.extend(str(literal) for literal in self.inputs)
        lines.extend(str(literal) for literal in self.outputs)
        for index, (lhs, rhs) in enumerate(self.ands):
            node_id = self.input_count + index + 1
            lines.append(f"{2 * node_id} {lhs} {rhs}")
        lines.append("c")
        lines.append("generated deterministically by CertifiedAIGResynthesis")
        return ("\n".join(lines) + "\n").encode("ascii")


def _ripple_adder(spec: dict[str, Any]) -> bytes:
    width = _positive_int(spec.get("width"), "ripple_adder.width")
    period = _positive_int(spec.get("lowering_period"), "lowering_period")
    builder = AigBuilder(2 * width + 1)
    lhs = builder.inputs[:width]
    rhs = builder.inputs[width : 2 * width]
    carry = builder.inputs[-1]
    sums: list[int] = []
    for bit in range(width):
        guard = lhs[(bit + 11) % width]
        propagate = builder.xor_gate(lhs[bit], rhs[bit])
        propagate = builder.lower_equivalent(propagate, guard, period)
        result = builder.xor_gate(propagate, carry)
        result = builder.lower_equivalent(result, rhs[(bit + 7) % width], period)
        generate = builder.and_gate(lhs[bit], rhs[bit])
        carry_prop = builder.and_gate(propagate, carry)
        carry = builder.or_gate(generate, carry_prop)
        carry = builder.lower_equivalent(carry, guard, period)
        sums.append(result)
    builder.outputs = sums + [carry]
    return builder.to_aag()


def _barrel_shifter(spec: dict[str, Any]) -> bytes:
    width = _positive_int(spec.get("width"), "barrel_shifter.width")
    if width & (width - 1):
        raise ValueError("barrel_shifter.width must be a power of two")
    stages = width.bit_length() - 1
    period = _positive_int(spec.get("lowering_period"), "lowering_period")
    builder = AigBuilder(width + stages)
    data = builder.inputs[:width]
    shift = builder.inputs[width:]
    current = data
    for stage, select in enumerate(shift):
        distance = 1 << stage
        next_stage: list[int] = []
        for bit in range(width):
            shifted = current[bit - distance] if bit >= distance else 0
            value = builder.mux(select, shifted, current[bit])
            guard = data[(bit + 3 * stage + 1) % width]
            next_stage.append(builder.lower_equivalent(value, guard, period))
        current = next_stage
    builder.outputs = current
    return builder.to_aag()


def _priority_arbiter(spec: dict[str, Any]) -> bytes:
    width = _positive_int(spec.get("width"), "priority_arbiter.width")
    period = _positive_int(spec.get("lowering_period"), "lowering_period")
    builder = AigBuilder(width)
    requests = builder.inputs
    seen = 0
    grants: list[int] = []
    for index, request in enumerate(requests):
        grant = builder.and_gate(request, builder.inv(seen))
        grant = builder.lower_equivalent(
            grant, requests[(index + 17) % width], period
        )
        grants.append(grant)
        seen = builder.or_gate(seen, request)
        seen = builder.lower_equivalent(seen, requests[(index + 29) % width], period)
    builder.outputs = grants + [seen]
    return builder.to_aag()


def _packet_classifier(spec: dict[str, Any]) -> bytes:
    header_bits = _positive_int(spec.get("header_bits"), "header_bits")
    rule_count = _positive_int(spec.get("rules"), "rules")
    bits_per_rule = _positive_int(spec.get("bits_per_rule"), "bits_per_rule")
    period = _positive_int(spec.get("lowering_period"), "lowering_period")
    if bits_per_rule > header_bits:
        raise ValueError("bits_per_rule exceeds header_bits")
    builder = AigBuilder(header_bits)
    header = builder.inputs
    matched = 0
    hits: list[int] = []
    for rule in range(rule_count):
        selected: list[int] = []
        used: set[int] = set()
        cursor = (rule * 7 + 3) % header_bits
        while len(selected) < bits_per_rule:
            if cursor not in used:
                used.add(cursor)
                literal = header[cursor]
                if ((rule * 13 + cursor * 5) >> 1) & 1:
                    literal = builder.inv(literal)
                selected.append(literal)
            cursor = (cursor + 5) % header_bits
        condition = selected[0]
        for position, literal in enumerate(selected[1:], start=1):
            condition = builder.and_gate(condition, literal)
            condition = builder.lower_equivalent(
                condition, header[(rule + position * 3) % header_bits], period
            )
        hit = builder.and_gate(condition, builder.inv(matched))
        hit = builder.lower_equivalent(hit, header[(rule + 19) % header_bits], period)
        hits.append(hit)
        matched = builder.or_gate(matched, condition)
        matched = builder.lower_equivalent(
            matched, header[(rule + 23) % header_bits], period
        )
    builder.outputs = hits + [matched]
    return builder.to_aag()


def _crc_update(spec: dict[str, Any]) -> bytes:
    state_bits = _positive_int(spec.get("state_bits"), "state_bits")
    data_bits = _positive_int(spec.get("data_bits"), "data_bits")
    polynomial = _positive_int(spec.get("polynomial"), "polynomial")
    period = _positive_int(spec.get("lowering_period"), "lowering_period")
    if polynomial >= (1 << state_bits):
        raise ValueError("CRC polynomial does not fit state width")
    builder = AigBuilder(state_bits + data_bits)
    state = builder.inputs[:state_bits]
    data = builder.inputs[state_bits:]
    for data_index, data_literal in enumerate(data):
        feedback = builder.xor_gate(state[-1], data_literal)
        next_state = [feedback]
        for bit in range(1, state_bits):
            value = state[bit - 1]
            if (polynomial >> bit) & 1:
                value = builder.xor_gate(value, feedback)
            guard = data[(data_index + bit * 7) % data_bits]
            value = builder.lower_equivalent(value, guard, period)
            next_state.append(value)
        state = next_state
    builder.outputs = state
    return builder.to_aag()


WORKLOAD_GENERATORS = {
    "ripple_adder": _ripple_adder,
    "barrel_shifter": _barrel_shifter,
    "priority_arbiter": _priority_arbiter,
    "packet_classifier": _packet_classifier,
    "crc_update": _crc_update,
}


def _generate_workload(spec: dict[str, Any]) -> bytes:
    kind = str(spec.get("kind", ""))
    generator = WORKLOAD_GENERATORS.get(kind)
    if generator is None:
        raise ValueError(f"unknown workload kind: {kind}")
    return generator(spec)


@dataclass(frozen=True)
class AigStats:
    live_ands: int
    depth: int


@dataclass(frozen=True)
class ReplayResult:
    stats: AigStats
    rewrites: int
    checked_rows: int
    appended_ands: int
    certificate_sha256: str


class ProofChecker:
    """A checker intentionally independent from the candidate's C++ engine."""

    KIND_UNUSED = 0
    KIND_INPUT = 1
    KIND_AND = 2

    def __init__(self, aag: bytes, limits: dict[str, Any]) -> None:
        self.limits = limits
        self.nodes: list[tuple[int, int] | None]
        self.kinds: list[int]
        self.outputs: list[int]
        self.redirect: list[int]
        self.first_and_id: int
        self.input_count: int
        self._parse_aag(aag)

    @staticmethod
    def _numbers(line: str, expected: int | None = None) -> list[int]:
        fields = line.split()
        if expected is not None and len(fields) != expected:
            raise EvaluationError("malformed AAG field count")
        if not fields or any(not field.isascii() or not field.isdecimal() for field in fields):
            raise EvaluationError("AAG numeric fields must be unsigned decimal integers")
        return [int(field) for field in fields]

    def _parse_aag(self, aag: bytes) -> None:
        try:
            text = aag.decode("ascii")
        except UnicodeDecodeError as exc:
            raise EvaluationError(f"AAG is not ASCII: {exc}") from exc
        lines = text.splitlines()
        if not lines:
            raise EvaluationError("empty AAG")
        header = lines[0].split()
        if len(header) != 6 or header[0] != "aag":
            raise EvaluationError("unsupported AAG header")
        values = self._numbers(" ".join(header[1:]), expected=5)
        maximum, inputs, latches, outputs, ands = values
        if latches != 0 or inputs <= 0 or outputs <= 0 or maximum != inputs + ands:
            raise EvaluationError("only dense combinational AAGs are supported")
        if maximum > int(self.limits["max_total_nodes"]):
            raise EvaluationError("input AAG exceeds node limit")
        required = 1 + inputs + outputs + ands
        if len(lines) < required:
            raise EvaluationError("truncated AAG")
        self.input_count = inputs
        self.first_and_id = inputs + 1
        self.nodes = [None] * (maximum + 1)
        self.kinds = [self.KIND_UNUSED] * (maximum + 1)
        for index in range(inputs):
            literal = self._numbers(lines[1 + index], expected=1)[0]
            node_id = index + 1
            if literal != 2 * node_id:
                raise EvaluationError("AAG inputs are not dense positive literals")
            self.kinds[node_id] = self.KIND_INPUT
        output_start = 1 + inputs
        self.outputs = []
        for index in range(outputs):
            literal = self._numbers(lines[output_start + index], expected=1)[0]
            if literal > 2 * maximum + 1:
                raise EvaluationError("AAG output references an unknown node")
            self.outputs.append(literal)
        and_start = output_start + outputs
        for index in range(ands):
            lhs, rhs0, rhs1 = self._numbers(lines[and_start + index], expected=3)
            node_id = self.first_and_id + index
            if lhs != 2 * node_id or rhs0 >= lhs or rhs1 >= lhs:
                raise EvaluationError("AAG ANDs are not dense and topological")
            self.nodes[node_id] = (rhs0, rhs1)
            self.kinds[node_id] = self.KIND_AND
        self.redirect = [2 * node_id for node_id in range(maximum + 1)]

    def resolve(self, literal: int) -> int:
        node_id = literal >> 1
        inverted = literal & 1
        if node_id >= len(self.redirect):
            raise EvaluationError("global literal references an unknown node")
        for _ in range(len(self.redirect) + 1):
            mapped = self.redirect[node_id]
            if mapped == 2 * node_id:
                return 2 * node_id + inverted
            inverted ^= mapped & 1
            node_id = mapped >> 1
            if node_id >= len(self.redirect):
                raise EvaluationError("rewrite redirect references an unknown node")
        raise EvaluationError("cycle in rewrite redirects")

    def is_active(self, node_id: int) -> bool:
        return 0 <= node_id < len(self.redirect) and self.redirect[node_id] == 2 * node_id

    @staticmethod
    def _variable_pattern(index: int, assignments: int) -> int:
        pattern = 0
        for assignment in range(assignments):
            if (assignment >> index) & 1:
                pattern |= 1 << assignment
        return pattern

    def _evaluate_cut(
        self,
        literal: int,
        leaves: list[int],
        *,
        forbidden_root: int | None,
        require_all_leaves: bool,
    ) -> int:
        leaf_positions = {leaf: index for index, leaf in enumerate(leaves)}
        if len(leaf_positions) != len(leaves):
            raise EvaluationError("cut leaves are not unique")
        assignments = 1 << len(leaves)
        mask = (1 << assignments) - 1
        used: set[int] = set()
        memo: dict[int, int] = {}
        visiting: set[int] = set()

        def evaluate_literal(current: int) -> int:
            current = self.resolve(current)
            value = evaluate_node(current >> 1)
            return mask ^ value if current & 1 else value

        def evaluate_node(node_id: int) -> int:
            leaf_index = leaf_positions.get(node_id)
            if leaf_index is not None:
                used.add(node_id)
                return self._variable_pattern(leaf_index, assignments)
            if node_id == 0:
                return 0
            if forbidden_root is not None and node_id == forbidden_root:
                raise EvaluationError("a divisor depends on the rewritten root")
            if node_id >= len(self.kinds):
                raise EvaluationError("cut traversal left the AIG")
            if self.kinds[node_id] == self.KIND_INPUT:
                raise EvaluationError("cut does not cover a primary-input path")
            if self.kinds[node_id] != self.KIND_AND or self.nodes[node_id] is None:
                raise EvaluationError("cut contains an invalid node")
            if node_id in memo:
                return memo[node_id]
            if node_id in visiting:
                raise EvaluationError("cycle in cut cone")
            visiting.add(node_id)
            lhs, rhs = self.nodes[node_id]
            value = evaluate_literal(lhs) & evaluate_literal(rhs)
            visiting.remove(node_id)
            memo[node_id] = value
            return value

        result = evaluate_literal(literal)
        if require_all_leaves and used != set(leaves):
            raise EvaluationError("cut includes a leaf outside the root cone")
        return result

    @staticmethod
    def _local_value(literal: int, values: list[int], mask: int) -> int:
        reference = literal >> 1
        if reference >= len(values):
            raise EvaluationError("local literal is forward or out of range")
        value = values[reference]
        return mask ^ value if literal & 1 else value

    def apply_rewrite(
        self,
        root: int,
        leaves: list[int],
        divisors: list[int],
        local_ands: list[tuple[int, int]],
        local_output: int,
    ) -> tuple[int, int]:
        max_cut = int(self.limits["max_cut_leaves"])
        max_divisors = int(self.limits["max_divisors"])
        max_local_ands = int(self.limits["max_local_ands"])
        if (
            len(leaves) > max_cut
            or len(divisors) > max_divisors
            or len(local_ands) > max_local_ands
            or root < self.first_and_id
            or root >= len(self.nodes)
            or self.kinds[root] != self.KIND_AND
            or not self.is_active(root)
        ):
            raise EvaluationError("rewrite root or resource limits are invalid")
        if len(self.nodes) + len(local_ands) > int(self.limits["max_total_nodes"]):
            raise EvaluationError("certificate exceeds total node limit")
        if any(
            leaf <= 0
            or leaf == root
            or leaf >= len(self.nodes)
            or not self.is_active(leaf)
            for leaf in leaves
        ):
            raise EvaluationError("invalid cut leaf")
        if len(set(leaves)) != len(leaves):
            raise EvaluationError("duplicate cut leaf")

        old_function = self._evaluate_cut(
            2 * root,
            leaves,
            forbidden_root=None,
            require_all_leaves=True,
        )
        assignments = 1 << len(leaves)
        mask = (1 << assignments) - 1
        values = [0]
        values.extend(
            self._variable_pattern(index, assignments) for index in range(len(leaves))
        )
        normalized_divisors: list[int] = []
        for divisor in divisors:
            if divisor < 0 or divisor >> 1 >= len(self.nodes):
                raise EvaluationError("invalid divisor literal")
            normalized = self.resolve(divisor)
            if normalized >> 1 == root:
                raise EvaluationError("divisor resolves to rewritten root")
            value = self._evaluate_cut(
                normalized,
                leaves,
                forbidden_root=root,
                require_all_leaves=False,
            )
            normalized_divisors.append(normalized)
            values.append(value)
        if normalized_divisors != divisors:
            raise EvaluationError("certificate divisor is not normalized")

        for lhs, rhs in local_ands:
            lhs_value = self._local_value(lhs, values, mask)
            rhs_value = self._local_value(rhs, values, mask)
            values.append(lhs_value & rhs_value)
        replacement = self._local_value(local_output, values, mask)
        if replacement != old_function:
            raise EvaluationError("local replacement truth table is not equivalent")

        global_values = [0]
        global_values.extend(2 * leaf for leaf in leaves)
        global_values.extend(normalized_divisors)

        def translate(local_literal: int) -> int:
            reference = local_literal >> 1
            if reference >= len(global_values):
                raise EvaluationError("local-to-global translation failed")
            return global_values[reference] ^ (local_literal & 1)

        for lhs, rhs in local_ands:
            global_lhs = translate(lhs)
            global_rhs = translate(rhs)
            new_id = len(self.nodes)
            self.nodes.append((global_lhs, global_rhs))
            self.kinds.append(self.KIND_AND)
            self.redirect.append(2 * new_id)
            global_values.append(2 * new_id)
        self.redirect[root] = translate(local_output)
        checked_rows = assignments * (1 + len(divisors))
        return checked_rows, len(local_ands)

    def stats(self) -> AigStats:
        reachable: set[int] = set()
        depths: dict[int, int] = {}
        visiting: set[int] = set()

        def depth_literal(literal: int) -> int:
            literal = self.resolve(literal)
            node_id = literal >> 1
            if node_id == 0 or self.kinds[node_id] == self.KIND_INPUT:
                return 0
            if self.kinds[node_id] != self.KIND_AND or self.nodes[node_id] is None:
                raise EvaluationError("live graph contains an invalid node")
            if node_id in depths:
                return depths[node_id]
            if node_id in visiting:
                raise EvaluationError("live graph is cyclic")
            visiting.add(node_id)
            reachable.add(node_id)
            lhs, rhs = self.nodes[node_id]
            result = 1 + max(depth_literal(lhs), depth_literal(rhs))
            visiting.remove(node_id)
            depths[node_id] = result
            return result

        maximum_depth = max(depth_literal(output) for output in self.outputs)
        return AigStats(live_ands=len(reachable), depth=maximum_depth)

    def replay(self, certificate: bytes) -> ReplayResult:
        digest = hashlib.sha256(certificate).hexdigest()
        try:
            text = certificate.decode("ascii")
        except UnicodeDecodeError as exc:
            raise EvaluationError(f"certificate is not ASCII: {exc}") from exc
        lines = text.splitlines()
        if not lines or lines[0] != "CERT1":
            raise EvaluationError("missing CERT1 header")
        rewrites = 0
        checked_rows = 0
        appended_ands = 0
        max_rewrites = int(self.limits["max_rewrites"])
        for line_number, line in enumerate(lines[1:], start=2):
            if not line:
                raise EvaluationError(f"blank certificate line {line_number}")
            fields = line.split()
            if len(fields) < 6 or fields[0] != "R":
                raise EvaluationError(f"malformed certificate line {line_number}")
            if any(not field.isascii() or not field.isdecimal() for field in fields[1:]):
                raise EvaluationError(f"non-decimal certificate token on line {line_number}")
            values = [int(field) for field in fields[1:]]
            root, cut_count, divisor_count, and_count = values[:4]
            expected = 4 + cut_count + divisor_count + 2 * and_count + 1
            if len(values) != expected:
                raise EvaluationError(f"wrong field count on certificate line {line_number}")
            if rewrites >= max_rewrites:
                raise EvaluationError("certificate exceeds rewrite limit")
            cursor = 4
            leaves = values[cursor : cursor + cut_count]
            cursor += cut_count
            divisors = values[cursor : cursor + divisor_count]
            cursor += divisor_count
            local_ands = [
                (values[cursor + 2 * index], values[cursor + 2 * index + 1])
                for index in range(and_count)
            ]
            cursor += 2 * and_count
            local_output = values[cursor]
            rows, appended = self.apply_rewrite(
                root, leaves, divisors, local_ands, local_output
            )
            rewrites += 1
            checked_rows += rows
            appended_ands += appended
        return ReplayResult(
            stats=self.stats(),
            rewrites=rewrites,
            checked_rows=checked_rows,
            appended_ands=appended_ands,
            certificate_sha256=digest,
        )


def _immutable_parts(source: str) -> tuple[str, str]:
    if source.count(START_MARKER) != 1 or source.count(END_MARKER) != 1:
        raise EvaluationError("candidate must contain exactly one marker pair")
    start = source.index(START_MARKER)
    start_end = source.index("\n", start) + 1
    end = source.index(END_MARKER, start_end)
    if end <= start_end:
        raise EvaluationError("EVOLVE markers are out of order")
    return source[:start_end], source[end:]


def _validate_candidate_shell(candidate_path: Path, max_bytes: int) -> bytes:
    if not candidate_path.is_file():
        raise EvaluationError(f"candidate not found: {candidate_path}")
    if candidate_path.stat().st_size > max_bytes:
        raise EvaluationError("candidate exceeds source-size limit")
    candidate = candidate_path.read_bytes()
    baseline = BASELINE_PATH.read_bytes()
    try:
        candidate_text = candidate.decode("utf-8")
        baseline_text = baseline.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvaluationError(f"candidate source is not UTF-8: {exc}") from exc
    if _immutable_parts(candidate_text) != _immutable_parts(baseline_text):
        raise EvaluationError("code outside the EVOLVE block differs from the frozen shell")
    return candidate


def _tail(path: Path, limit: int = 8000) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    return data[-limit:].decode("utf-8", errors="replace")


def _compile(
    compiler: str,
    source: Path,
    output: Path,
    timeout_s: float,
    log_path: Path,
) -> None:
    command = [
        compiler,
        "-std=c++17",
        "-O2",
        "-DNDEBUG",
        "-pipe",
        "-Wall",
        "-Wextra",
        "-pedantic",
        "-I",
        str(TASK_DIR / "verification"),
        str(source),
        "-o",
        str(output),
    ]
    with log_path.open("wb") as log:
        try:
            process = subprocess.run(
                command,
                cwd=TASK_DIR,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout_s,
                check=False,
                env={**os.environ, "LC_ALL": "C"},
            )
        except subprocess.TimeoutExpired as exc:
            raise EvaluationError(f"compilation timed out after {timeout_s:.1f}s") from exc
    if process.returncode != 0 or not output.is_file():
        raise EvaluationError(
            f"compilation failed with code {process.returncode}: {_tail(log_path)}"
        )


def _resource_limits(cpu_s: float, file_bytes: int) -> None:
    cpu_limit = max(2, int(math.ceil(cpu_s)) + 1)
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))
    memory = 2 * 1024 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


@dataclass(frozen=True)
class ProgramRun:
    certificate: bytes
    stdout_tail: str
    elapsed_s: float


def _run_program(
    executable: Path,
    aag: bytes,
    run_dir: Path,
    timeout_s: float,
    max_certificate_bytes: int,
) -> ProgramRun:
    run_dir.mkdir(parents=True, exist_ok=False)
    input_path = run_dir / "input.aag"
    certificate_path = run_dir / "rewrites.cert"
    log_path = run_dir / "candidate.log"
    input_path.write_bytes(aag)
    started = time.perf_counter()
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [
                str(executable),
                "--input",
                str(input_path),
                "--certificate",
                str(certificate_path),
            ],
            cwd=run_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            preexec_fn=lambda: _resource_limits(timeout_s, max_certificate_bytes),
            env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"},
        )
        try:
            returncode = process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise EvaluationError(f"candidate timed out after {timeout_s:.1f}s") from exc
    elapsed = time.perf_counter() - started
    if returncode != 0:
        raise EvaluationError(
            f"candidate exited with code {returncode}: {_tail(log_path)}"
        )
    if input_path.read_bytes() != aag:
        raise EvaluationError("candidate modified the frozen input AAG")
    if not certificate_path.is_file():
        raise EvaluationError("candidate did not produce a certificate")
    if certificate_path.stat().st_size > max_certificate_bytes:
        raise EvaluationError("candidate certificate exceeds size limit")
    return ProgramRun(
        certificate=certificate_path.read_bytes(),
        stdout_tail=_tail(log_path),
        elapsed_s=elapsed,
    )


def _invalid_metrics(runtime_s: float, *, timeout: bool = False) -> dict[str, float]:
    return {
        "combined_score": 0.0,
        "valid": 0.0,
        "timeout": 1.0 if timeout else 0.0,
        "runtime_s": float(runtime_s),
    }


def evaluate(
    candidate_path: Path,
    *,
    timeout_override_s: float | None = None,
) -> tuple[dict[str, float], dict[str, Any]]:
    started = time.perf_counter()
    artifacts: dict[str, Any] = {
        "benchmark_id": "certified_aig_resynthesis",
        "checker": "independent exhaustive truth-table replay",
    }
    try:
        config = _validated_config()
        limits = config["limits"]
        source = _validate_candidate_shell(
            candidate_path, int(limits["max_candidate_bytes"])
        )
        compiler = shutil.which("g++")
        if compiler is None:
            raise EvaluationError("g++ is required but was not found on PATH")
        timeout_s = (
            float(timeout_override_s)
            if timeout_override_s is not None
            else _finite_float(
                limits["candidate_timeout_s_per_workload"], "candidate timeout"
            )
        )
        if timeout_s <= 0.0:
            raise EvaluationError("candidate timeout must be positive")
        compile_timeout = _finite_float(limits["compile_timeout_s"], "compile timeout")
        workloads: list[tuple[str, bytes]] = []
        workload_manifest: list[dict[str, Any]] = []
        for spec in config["workloads"]:
            workload_id = str(spec["id"])
            aag = _generate_workload(spec)
            original_stats = ProofChecker(aag, limits).stats()
            digest = hashlib.sha256(aag).hexdigest()
            if digest != str(spec.get("expected_sha256", "")):
                raise EvaluationError(
                    f"frozen workload digest mismatch for {workload_id}"
                )
            if original_stats.live_ands != _positive_int(
                spec.get("expected_live_ands"), f"{workload_id}.expected_live_ands"
            ) or original_stats.depth != _positive_int(
                spec.get("expected_depth"), f"{workload_id}.expected_depth"
            ):
                raise EvaluationError(
                    f"frozen workload topology mismatch for {workload_id}"
                )
            workloads.append((workload_id, aag))
            workload_manifest.append(
                {
                    "id": workload_id,
                    "sha256": digest,
                    "bytes": len(aag),
                    "input_live_ands": original_stats.live_ands,
                    "input_depth": original_stats.depth,
                }
            )
        artifacts["workload_manifest"] = workload_manifest

        with tempfile.TemporaryDirectory(prefix="certified_aig_eval_") as temporary:
            temp = Path(temporary)
            candidate_copy = temp / "candidate.cpp"
            candidate_copy.write_bytes(source)
            candidate_executable = temp / "candidate"
            baseline_executable = temp / "baseline"
            candidate_compile_log = temp / "candidate_compile.log"
            baseline_compile_log = temp / "baseline_compile.log"
            compile_started = time.perf_counter()
            _compile(
                compiler,
                BASELINE_PATH,
                baseline_executable,
                compile_timeout,
                baseline_compile_log,
            )
            baseline_compile_s = time.perf_counter() - compile_started
            compile_started = time.perf_counter()
            _compile(
                compiler,
                candidate_copy,
                candidate_executable,
                compile_timeout,
                candidate_compile_log,
            )
            candidate_compile_s = time.perf_counter() - compile_started

            area_weight = float(config["objective"]["area_weight"])
            depth_weight = float(config["objective"]["depth_weight"])
            scenario_scores: list[float] = []
            baseline_total_area = 0
            candidate_total_area = 0
            baseline_depth_sum = 0
            candidate_depth_sum = 0
            total_checked_rows = 0
            workload_results: dict[str, Any] = {}
            for index, (workload_id, aag) in enumerate(workloads):
                baseline_run = _run_program(
                    baseline_executable,
                    aag,
                    temp / f"baseline_{index}",
                    timeout_s,
                    int(limits["max_certificate_bytes"]),
                )
                candidate_run = _run_program(
                    candidate_executable,
                    aag,
                    temp / f"candidate_{index}",
                    timeout_s,
                    int(limits["max_certificate_bytes"]),
                )
                baseline_result = ProofChecker(aag, limits).replay(
                    baseline_run.certificate
                )
                candidate_result = ProofChecker(aag, limits).replay(
                    candidate_run.certificate
                )
                baseline_stats = baseline_result.stats
                candidate_stats = candidate_result.stats
                if (
                    baseline_stats.live_ands <= 0
                    or baseline_stats.depth <= 0
                    or candidate_stats.live_ands <= 0
                    or candidate_stats.depth <= 0
                ):
                    raise EvaluationError("a workload produced a degenerate scored graph")
                area_ratio = baseline_stats.live_ands / candidate_stats.live_ands
                depth_ratio = baseline_stats.depth / candidate_stats.depth
                scenario_score = (area_ratio**area_weight) * (
                    depth_ratio**depth_weight
                )
                if not math.isfinite(scenario_score) or scenario_score <= 0.0:
                    raise EvaluationError("non-finite workload score")
                scenario_scores.append(scenario_score)
                baseline_total_area += baseline_stats.live_ands
                candidate_total_area += candidate_stats.live_ands
                baseline_depth_sum += baseline_stats.depth
                candidate_depth_sum += candidate_stats.depth
                total_checked_rows += candidate_result.checked_rows
                workload_results[workload_id] = {
                    "score": scenario_score,
                    "area_ratio": area_ratio,
                    "depth_ratio": depth_ratio,
                    "baseline": {
                        "live_ands": baseline_stats.live_ands,
                        "depth": baseline_stats.depth,
                        "accepted_rewrites": baseline_result.rewrites,
                        "checked_truth_rows": baseline_result.checked_rows,
                        "appended_ands": baseline_result.appended_ands,
                        "certificate_sha256": baseline_result.certificate_sha256,
                        "runtime_s": baseline_run.elapsed_s,
                        "stdout_tail": baseline_run.stdout_tail,
                    },
                    "candidate": {
                        "live_ands": candidate_stats.live_ands,
                        "depth": candidate_stats.depth,
                        "accepted_rewrites": candidate_result.rewrites,
                        "checked_truth_rows": candidate_result.checked_rows,
                        "appended_ands": candidate_result.appended_ands,
                        "certificate_sha256": candidate_result.certificate_sha256,
                        "runtime_s": candidate_run.elapsed_s,
                        "stdout_tail": candidate_run.stdout_tail,
                    },
                }

            combined_score = math.exp(
                sum(math.log(score) for score in scenario_scores)
                / len(scenario_scores)
            )
            runtime_s = time.perf_counter() - started
            metrics = {
                "combined_score": combined_score,
                "valid": 1.0,
                "timeout": 0.0,
                "runtime_s": runtime_s,
                "scenario_count": float(len(scenario_scores)),
                "mean_score": sum(scenario_scores) / len(scenario_scores),
                "min_score": min(scenario_scores),
                "baseline_total_area": float(baseline_total_area),
                "candidate_total_area": float(candidate_total_area),
                "baseline_mean_depth": baseline_depth_sum / len(scenario_scores),
                "candidate_mean_depth": candidate_depth_sum / len(scenario_scores),
                "checked_truth_rows": float(total_checked_rows),
            }
            artifacts["compiler"] = compiler
            artifacts["compile"] = {
                "baseline_s": baseline_compile_s,
                "candidate_s": candidate_compile_s,
            }
            artifacts["objective"] = config["objective"]
            artifacts["limits"] = limits
            artifacts["workloads"] = workload_results
            return metrics, artifacts
    except Exception as exc:
        message = str(exc)
        artifacts["error_message"] = message
        timed_out = "timed out" in message.lower()
        return _invalid_metrics(time.perf_counter() - started, timeout=timed_out), artifacts


def _write_json(path_text: str | None, payload: dict[str, Any]) -> None:
    if not path_text:
        return
    path = Path(path_text).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", help="candidate C++ source")
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=None,
        help="optional per-workload execution timeout override",
    )
    parser.add_argument("--metrics-out", default=None)
    parser.add_argument("--artifacts-out", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timeout = None if args.timeout_s is None else max(0.1, float(args.timeout_s))
    metrics, artifacts = evaluate(
        Path(args.candidate).expanduser().resolve(), timeout_override_s=timeout
    )
    _write_json(args.metrics_out, metrics)
    _write_json(args.artifacts_out, artifacts)
    print(json.dumps(metrics, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
