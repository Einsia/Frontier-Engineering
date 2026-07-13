"""Independent evaluator for resource-aware kernel block encodings."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any, Callable


TASK_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = TASK_DIR / "references" / "problem_config.json"
BASELINE_PATH = TASK_DIR / "baseline" / "solution.cpp"
RUNTIME_INCLUDE = TASK_DIR / "verification"
LIMITED_EXEC = RUNTIME_INCLUDE / "limited_exec.py"
START_MARKER = "// EVOLVE-BLOCK-START"
END_MARKER = "// EVOLVE-BLOCK-END"
INTEGER_RE = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")


class EvaluationError(RuntimeError):
    """A deterministic source, process, certificate, or validity failure."""


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


def _power_of_two(value: int) -> bool:
    return value >= 2 and value & (value - 1) == 0


def _validated_config() -> dict[str, Any]:
    config = _strict_json(CONFIG_PATH)
    if config.get("benchmark_id") != "kernel_block_encoding":
        raise ValueError("unexpected benchmark_id")
    matrix_scale = _positive_int(config.get("matrix_scale"), "matrix_scale")
    angle_denominator = _positive_int(
        config.get("angle_denominator"), "angle_denominator"
    )
    if angle_denominator != 1 << 28:
        raise ValueError("angle_denominator does not match the frozen C++ runtime")
    objective = config.get("objective")
    limits = config.get("limits")
    workloads = config.get("workloads")
    if not isinstance(objective, dict) or not isinstance(limits, dict):
        raise ValueError("objective and limits must be objects")
    if not isinstance(workloads, list) or not workloads:
        raise ValueError("workloads must be a non-empty list")
    frozen_weights = {
        "rotation_weight": 16.0,
        "cnot_weight": 1.0,
        "hadamard_weight": 0.25,
        "depth_weight": 0.25,
    }
    for key, frozen_value in frozen_weights.items():
        value = _finite_float(objective.get(key), key)
        if value <= 0.0:
            raise ValueError(f"{key} must be positive")
        if value != frozen_value:
            raise ValueError(f"{key} does not match the frozen C++ runtime")
    normalization_exponent = _finite_float(
        objective.get("normalization_exponent"), "normalization_exponent"
    )
    if normalization_exponent <= 0:
        raise ValueError("normalization_exponent must be positive")
    if normalization_exponent != 1.0:
        raise ValueError("normalization_exponent does not match the frozen runtime")
    for key in (
        "max_candidate_bytes",
        "max_certificate_bytes",
        "max_dimension",
        "max_scale_multiplier",
        "memory_limit_mb",
    ):
        _positive_int(limits.get(key), key)
    if int(limits["max_scale_multiplier"]) != 16:
        raise ValueError("max_scale_multiplier does not match the frozen C++ runtime")
    if _finite_float(limits.get("candidate_timeout_s_per_workload"), "candidate timeout") <= 0:
        raise ValueError("candidate timeout must be positive")
    if _finite_float(limits.get("compile_timeout_s"), "compile timeout") <= 0:
        raise ValueError("compile timeout must be positive")

    ids: set[str] = set()
    supported = {"rbf", "multiscale_rbf", "polynomial", "rational_quadratic", "walk_gram"}
    for index, spec in enumerate(workloads):
        if not isinstance(spec, dict):
            raise ValueError(f"workloads[{index}] must be an object")
        workload_id = str(spec.get("id", ""))
        kind = str(spec.get("kind", ""))
        dimension = _positive_int(spec.get("dimension"), f"{workload_id}.dimension")
        if (
            not workload_id
            or workload_id in ids
            or not re.fullmatch(r"[a-z0-9_]+", workload_id)
            or kind not in supported
            or not _power_of_two(dimension)
            or dimension > int(limits["max_dimension"])
        ):
            raise ValueError(f"invalid workload at index {index}")
        relative_error_ppm = _positive_int(
            spec.get("relative_error_ppm"), f"{workload_id}.relative_error_ppm"
        )
        if relative_error_ppm >= 1_000_000:
            raise ValueError("relative error must be below one")
        expected = str(spec.get("expected_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"invalid expected_sha256 for {workload_id}")
        ids.add(workload_id)
    if matrix_scale > 1 << 30:
        raise ValueError("matrix_scale is unexpectedly large")
    return config


class Lcg:
    """Tiny specified PRNG used only to build deterministic integer features."""

    def __init__(self, seed: int) -> None:
        self.state = seed & ((1 << 64) - 1)

    def next_u64(self) -> int:
        self.state = (
            6364136223846793005 * self.state + 1442695040888963407
        ) & ((1 << 64) - 1)
        return self.state

    def bounded(self, low: int, high: int) -> int:
        if low > high:
            raise ValueError("invalid PRNG range")
        return low + self.next_u64() % (high - low + 1)


def _clustered_features(spec: dict[str, Any]) -> list[list[int]]:
    dimension = _positive_int(spec.get("dimension"), "dimension")
    feature_dimensions = _positive_int(
        spec.get("feature_dimensions"), "feature_dimensions"
    )
    clusters = _positive_int(spec.get("clusters"), "clusters")
    separation = _positive_int(spec.get("cluster_separation"), "cluster_separation")
    jitter = _positive_int(spec.get("jitter"), "jitter")
    seed = _positive_int(spec.get("seed"), "seed")
    if dimension % clusters != 0 or clusters > dimension:
        raise ValueError("clusters must evenly divide the kernel dimension")
    random = Lcg(seed)
    centers: list[list[int]] = []
    for cluster in range(clusters):
        center: list[int] = []
        for axis in range(feature_dimensions):
            permutation = (cluster * (2 * axis + 1) + 3 * axis) % clusters
            center.append((2 * permutation - clusters + 1) * separation)
        centers.append(center)
    features: list[list[int]] = []
    per_cluster = dimension // clusters
    for row in range(dimension):
        cluster = row // per_cluster
        features.append(
            [
                centers[cluster][axis] + random.bounded(-jitter, jitter)
                for axis in range(feature_dimensions)
            ]
        )
    return features


def _decimal_exp_ticks(exponent: Decimal, matrix_scale: int) -> int:
    with localcontext() as context:
        context.prec = 60
        value = exponent.exp() * Decimal(matrix_scale)
        return int(value.to_integral_value(rounding=ROUND_HALF_EVEN))


def _rbf_matrix(spec: dict[str, Any], matrix_scale: int) -> list[int]:
    features = _clustered_features(spec)
    dimension = len(features)
    bandwidth_squared = _positive_int(
        spec.get("bandwidth_squared"), "bandwidth_squared"
    )
    result = [0] * (dimension * dimension)
    for row in range(dimension):
        result[row * dimension + row] = matrix_scale
        for column in range(row):
            distance_squared = sum(
                (axis + 1) * (features[row][axis] - features[column][axis]) ** 2
                for axis in range(len(features[row]))
            )
            exponent = -Decimal(distance_squared) / Decimal(2 * bandwidth_squared)
            ticks = _decimal_exp_ticks(exponent, matrix_scale)
            result[row * dimension + column] = ticks
            result[column * dimension + row] = ticks
    return result


def _multiscale_rbf_matrix(spec: dict[str, Any], matrix_scale: int) -> list[int]:
    features = _clustered_features(spec)
    dimension = len(features)
    small = _positive_int(
        spec.get("bandwidth_squared_small"), "bandwidth_squared_small"
    )
    large = _positive_int(
        spec.get("bandwidth_squared_large"), "bandwidth_squared_large"
    )
    weight_num = _positive_int(
        spec.get("small_weight_numerator"), "small_weight_numerator"
    )
    weight_den = _positive_int(spec.get("weight_denominator"), "weight_denominator")
    if weight_num >= weight_den:
        raise ValueError("small kernel weight must lie strictly between zero and one")
    result = [0] * (dimension * dimension)
    with localcontext() as context:
        context.prec = 60
        weight = Decimal(weight_num) / Decimal(weight_den)
        for row in range(dimension):
            result[row * dimension + row] = matrix_scale
            for column in range(row):
                distance_squared = sum(
                    (axis + 1) * (features[row][axis] - features[column][axis]) ** 2
                    for axis in range(len(features[row]))
                )
                fine = (-Decimal(distance_squared) / Decimal(2 * small)).exp()
                coarse = (-Decimal(distance_squared) / Decimal(2 * large)).exp()
                value = (weight * fine + (Decimal(1) - weight) * coarse) * Decimal(
                    matrix_scale
                )
                ticks = int(value.to_integral_value(rounding=ROUND_HALF_EVEN))
                result[row * dimension + column] = ticks
                result[column * dimension + row] = ticks
    return result


def _round_ratio(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("ratio denominator must be positive")
    sign = -1 if numerator < 0 else 1
    magnitude = abs(numerator)
    quotient, remainder = divmod(magnitude, denominator)
    if 2 * remainder > denominator or (
        2 * remainder == denominator and quotient % 2 == 1
    ):
        quotient += 1
    return sign * quotient


def _polynomial_matrix(spec: dict[str, Any], matrix_scale: int) -> list[int]:
    dimension = _positive_int(spec.get("dimension"), "dimension")
    feature_dimensions = _positive_int(
        spec.get("feature_dimensions"), "feature_dimensions"
    )
    feature_bound = _positive_int(spec.get("feature_bound"), "feature_bound")
    bias = _positive_int(spec.get("bias"), "bias")
    degree = _positive_int(spec.get("degree"), "degree")
    seed = _positive_int(spec.get("seed"), "seed")
    random = Lcg(seed)
    features = [
        [random.bounded(-feature_bound, feature_bound) for _ in range(feature_dimensions)]
        for _ in range(dimension)
    ]
    raw: list[int] = []
    for row in range(dimension):
        for column in range(dimension):
            inner = bias + sum(
                features[row][axis] * features[column][axis]
                for axis in range(feature_dimensions)
            )
            raw.append(inner**degree)
    normalization = max(raw[index * dimension + index] for index in range(dimension))
    if normalization <= 0:
        raise ValueError("polynomial Gram matrix has invalid diagonal")
    return [_round_ratio(value * matrix_scale, normalization) for value in raw]


def _rational_quadratic_matrix(
    spec: dict[str, Any], matrix_scale: int
) -> list[int]:
    dimension = _positive_int(spec.get("dimension"), "dimension")
    feature_dimensions = _positive_int(
        spec.get("feature_dimensions"), "feature_dimensions"
    )
    feature_bound = _positive_int(spec.get("feature_bound"), "feature_bound")
    length_squared = _positive_int(spec.get("length_squared"), "length_squared")
    seed = _positive_int(spec.get("seed"), "seed")
    random = Lcg(seed)
    features = [
        [random.bounded(-feature_bound, feature_bound) for _ in range(feature_dimensions)]
        for _ in range(dimension)
    ]
    result: list[int] = []
    for row in range(dimension):
        for column in range(dimension):
            distance_squared = sum(
                (features[row][axis] - features[column][axis]) ** 2
                for axis in range(feature_dimensions)
            )
            result.append(
                _round_ratio(
                    matrix_scale * 2 * length_squared,
                    2 * length_squared + distance_squared,
                )
            )
    return result


def _matrix_multiply(lhs: list[list[int]], rhs: list[list[int]]) -> list[list[int]]:
    size = len(lhs)
    return [
        [
            sum(lhs[row][inner] * rhs[inner][column] for inner in range(size))
            for column in range(size)
        ]
        for row in range(size)
    ]


def _walk_gram_matrix(spec: dict[str, Any], matrix_scale: int) -> list[int]:
    dimension = _positive_int(spec.get("dimension"), "dimension")
    shortcut = _positive_int(spec.get("shortcut_stride"), "shortcut_stride")
    walk_steps = _positive_int(spec.get("walk_steps"), "walk_steps")
    self_weight = _positive_int(spec.get("self_weight"), "self_weight")
    transition = [[0] * dimension for _ in range(dimension)]
    for row in range(dimension):
        transition[row][row] += self_weight
        transition[row][(row - 1) % dimension] += 1
        transition[row][(row + 1) % dimension] += 1
        transition[row][(row + shortcut) % dimension] += 1
        transition[row][(row - shortcut) % dimension] += 1
    current = [[int(row == column) for column in range(dimension)] for row in range(dimension)]
    gram = [[0] * dimension for _ in range(dimension)]
    for _ in range(walk_steps + 1):
        for row in range(dimension):
            for column in range(dimension):
                gram[row][column] += sum(
                    current[row][feature] * current[column][feature]
                    for feature in range(dimension)
                )
        current = _matrix_multiply(current, transition)
    normalization = max(gram[index][index] for index in range(dimension))
    return [
        _round_ratio(gram[row][column] * matrix_scale, normalization)
        for row in range(dimension)
        for column in range(dimension)
    ]


MATRIX_GENERATORS: dict[str, Callable[[dict[str, Any], int], list[int]]] = {
    "rbf": _rbf_matrix,
    "multiscale_rbf": _multiscale_rbf_matrix,
    "polynomial": _polynomial_matrix,
    "rational_quadratic": _rational_quadratic_matrix,
    "walk_gram": _walk_gram_matrix,
}


@dataclass(frozen=True)
class Workload:
    workload_id: str
    dimension: int
    matrix_scale: int
    epsilon_numerator: int
    matrix: tuple[int, ...]
    input_bytes: bytes
    sha256: str

    @property
    def epsilon(self) -> float:
        return self.epsilon_numerator / self.matrix_scale


def _build_workload(spec: dict[str, Any], matrix_scale: int) -> Workload:
    workload_id = str(spec["id"])
    dimension = int(spec["dimension"])
    generator = MATRIX_GENERATORS[str(spec["kind"])]
    matrix = generator(spec, matrix_scale)
    if len(matrix) != dimension * dimension:
        raise ValueError(f"generator returned wrong matrix size for {workload_id}")
    if any(abs(value) > matrix_scale for value in matrix):
        raise ValueError(f"kernel entry exceeds fixed-point range for {workload_id}")
    for row in range(dimension):
        for column in range(dimension):
            if matrix[row * dimension + column] != matrix[column * dimension + row]:
                raise ValueError(f"kernel is not symmetric for {workload_id}")
    squared_norm = sum(value * value for value in matrix)
    with localcontext() as context:
        context.prec = 60
        epsilon_numerator = int(
            (
                Decimal(squared_norm).sqrt()
                * Decimal(int(spec["relative_error_ppm"]))
                / Decimal(1_000_000)
            ).to_integral_value(rounding=ROUND_CEILING)
        )
    lines = [
        "KBE_INPUT_V1",
        f"workload {workload_id}",
        f"dimension {dimension}",
        f"matrix_scale {matrix_scale}",
        f"epsilon_numerator {epsilon_numerator}",
        "matrix",
    ]
    for row in range(dimension):
        lines.append(
            " ".join(
                str(matrix[row * dimension + column])
                for column in range(dimension)
            )
        )
    lines.append("end")
    input_bytes = ("\n".join(lines) + "\n").encode("ascii")
    digest = hashlib.sha256(input_bytes).hexdigest()
    expected = str(spec.get("expected_sha256", ""))
    if digest != expected:
        raise EvaluationError(f"frozen workload digest mismatch for {workload_id}")
    return Workload(
        workload_id=workload_id,
        dimension=dimension,
        matrix_scale=matrix_scale,
        epsilon_numerator=epsilon_numerator,
        matrix=tuple(matrix),
        input_bytes=input_bytes,
        sha256=digest,
    )


def _basis_transform(
    matrix: tuple[int, ...] | list[int], dimension: int, mask: int
) -> tuple[list[int], int]:
    values = list(matrix)
    denominator_multiplier = 1
    qubits = dimension.bit_length() - 1
    for bit in range(qubits):
        if mask & (1 << bit) == 0:
            continue
        stride = 1 << bit
        block = 2 * stride
        for base in range(0, dimension, block):
            for offset in range(stride):
                row0 = base + offset
                row1 = row0 + stride
                for column in range(dimension):
                    index0 = row0 * dimension + column
                    index1 = row1 * dimension + column
                    lhs, rhs = values[index0], values[index1]
                    values[index0], values[index1] = lhs + rhs, lhs - rhs
        for row in range(dimension):
            for base in range(0, dimension, block):
                for offset in range(stride):
                    column0 = base + offset
                    column1 = column0 + stride
                    index0 = row * dimension + column0
                    index1 = row * dimension + column1
                    lhs, rhs = values[index0], values[index1]
                    values[index0], values[index1] = lhs + rhs, lhs - rhs
        denominator_multiplier *= 2
    return values, denominator_multiplier


def _gray_code(value: int) -> int:
    return value ^ (value >> 1)


def _inverse_angle_transform(angle_ticks: list[int]) -> list[int]:
    values = [0] * len(angle_ticks)
    for index, tick in enumerate(angle_ticks):
        values[_gray_code(index)] = tick
    stride = 1
    while stride < len(values):
        for base in range(0, len(values), 2 * stride):
            for offset in range(stride):
                lhs = values[base + offset]
                rhs = values[base + offset + stride]
                values[base + offset] = lhs + rhs
                values[base + offset + stride] = lhs - rhs
        stride *= 2
    return values


@dataclass(frozen=True)
class Certificate:
    basis_mask: int
    scale_numerator: int
    angle_ticks: tuple[int, ...]
    sha256: str
    byte_count: int


def _parse_integer(token: str, label: str) -> int:
    if INTEGER_RE.fullmatch(token) is None or token == "-0":
        raise EvaluationError(f"{label} is not a canonical decimal integer")
    return int(token)


def _parse_certificate(
    certificate_bytes: bytes,
    workload: Workload,
    config: dict[str, Any],
) -> Certificate:
    try:
        text = certificate_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise EvaluationError("certificate is not ASCII") from exc
    tokens = text.split()
    cursor = 0

    def take(expected: str | None = None) -> str:
        nonlocal cursor
        if cursor >= len(tokens):
            raise EvaluationError("truncated construction certificate")
        token = tokens[cursor]
        cursor += 1
        if expected is not None and token != expected:
            raise EvaluationError(f"expected certificate token {expected}")
        return token

    take("KBE_CERTIFICATE_V1")
    take("dimension")
    dimension = _parse_integer(take(), "dimension")
    take("basis_mask")
    basis_mask = _parse_integer(take(), "basis_mask")
    take("scale_numerator")
    scale_numerator = _parse_integer(take(), "scale_numerator")
    take("angle_denominator")
    angle_denominator = _parse_integer(take(), "angle_denominator")
    take("nonzero_count")
    nonzero_count = _parse_integer(take(), "nonzero_count")
    take("angles")
    if dimension != workload.dimension:
        raise EvaluationError("certificate dimension does not match workload")
    if basis_mask < 0 or basis_mask >= dimension:
        raise EvaluationError("basis mask addresses a nonexistent system qubit")
    if angle_denominator != int(config["angle_denominator"]):
        raise EvaluationError("certificate angle denominator is not frozen value")
    coefficient_count = dimension * dimension
    if nonzero_count < 0 or nonzero_count > coefficient_count:
        raise EvaluationError("invalid nonzero angle count")
    angle_ticks = [0] * coefficient_count
    previous_index = -1
    maximum_tick = 4 * angle_denominator
    for _ in range(nonzero_count):
        index = _parse_integer(take(), "angle index")
        tick = _parse_integer(take(), "angle tick")
        if index <= previous_index or index >= coefficient_count:
            raise EvaluationError("angle indices must be strictly increasing and in range")
        if tick == 0 or abs(tick) > maximum_tick:
            raise EvaluationError("invalid nonzero angle tick")
        angle_ticks[index] = tick
        previous_index = index
    take("end")
    if cursor != len(tokens):
        raise EvaluationError("trailing construction certificate data")
    basis_values, _ = _basis_transform(workload.matrix, dimension, basis_mask)
    minimum_scale = max(abs(value) for value in basis_values)
    maximum_scale = minimum_scale * int(config["limits"]["max_scale_multiplier"])
    if scale_numerator < minimum_scale or scale_numerator > maximum_scale:
        raise EvaluationError("normalization scale is outside the public range")
    return Certificate(
        basis_mask=basis_mask,
        scale_numerator=scale_numerator,
        angle_ticks=tuple(angle_ticks),
        sha256=hashlib.sha256(certificate_bytes).hexdigest(),
        byte_count=len(certificate_bytes),
    )


@dataclass(frozen=True)
class CheckedConstruction:
    frobenius_error: float
    error_upper_bound: float
    relative_error: float
    alpha: float
    rotations: int
    oracle_cnots: int
    cnots: int
    hadamards: int
    depth: int
    qubits: int
    compiled_cost: float
    objective: float
    basis_denominator_multiplier: int
    minimum_scale_numerator: int


def _check_construction(
    certificate: Certificate,
    workload: Workload,
    config: dict[str, Any],
) -> CheckedConstruction:
    dimension = workload.dimension
    basis_values, denominator_multiplier = _basis_transform(
        workload.matrix, dimension, certificate.basis_mask
    )
    minimum_scale = max(abs(value) for value in basis_values)
    entry_angle_ticks = _inverse_angle_transform(list(certificate.angle_ticks))
    angle_denominator = int(config["angle_denominator"])
    denominator = workload.matrix_scale * denominator_multiplier
    scale = certificate.scale_numerator / denominator
    residuals: list[float] = []
    for target_numerator, theta_tick in zip(basis_values, entry_angle_ticks):
        approximate_numerator = certificate.scale_numerator * math.cos(
            math.pi * theta_tick / (2.0 * angle_denominator)
        )
        residuals.append((target_numerator - approximate_numerator) / denominator)
    squared_error = math.fsum(value * value for value in residuals)
    frobenius_error = math.sqrt(max(0.0, squared_error))
    numerical_guard = max(
        1e-12,
        dimension * max(1.0, abs(scale)) * 32.0 * math.ulp(1.0),
    )
    error_upper_bound = frobenius_error + numerical_guard
    if error_upper_bound > workload.epsilon:
        raise EvaluationError(
            f"block error {error_upper_bound:.9g} exceeds epsilon {workload.epsilon:.9g}"
        )

    count = dimension * dimension
    controls = 2 * (dimension.bit_length() - 1)
    rotations = 0
    oracle_cnots = 0
    index = 0
    while index < count:
        parity = 0
        if certificate.angle_ticks[index] != 0:
            rotations += 1
        while True:
            if index + 1 == count:
                bit = controls - 1
            else:
                transition = _gray_code(index) ^ _gray_code(index + 1)
                bit = (transition & -transition).bit_length() - 1
            parity ^= 1 << bit
            index += 1
            if index >= count or certificate.angle_ticks[index] != 0:
                break
        oracle_cnots += parity.bit_count()

    qubits = dimension.bit_length() - 1
    cnots = oracle_cnots + 3 * qubits
    hadamards = 2 * qubits + 2 * certificate.basis_mask.bit_count()
    depth = rotations + oracle_cnots + 5 + (2 if certificate.basis_mask else 0)
    alpha = dimension * scale
    objective_config = config["objective"]
    compiled_cost = (
        float(objective_config["rotation_weight"]) * rotations
        + float(objective_config["cnot_weight"]) * cnots
        + float(objective_config["hadamard_weight"]) * hadamards
        + float(objective_config["depth_weight"]) * depth
    )
    objective = alpha ** float(objective_config["normalization_exponent"]) * compiled_cost
    if not math.isfinite(objective) or objective <= 0.0:
        raise EvaluationError("construction has a non-positive or non-finite objective")
    target_norm = math.sqrt(
        math.fsum((value / workload.matrix_scale) ** 2 for value in workload.matrix)
    )
    return CheckedConstruction(
        frobenius_error=frobenius_error,
        error_upper_bound=error_upper_bound,
        relative_error=error_upper_bound / target_norm,
        alpha=alpha,
        rotations=rotations,
        oracle_cnots=oracle_cnots,
        cnots=cnots,
        hadamards=hadamards,
        depth=depth,
        qubits=2 * qubits + 1,
        compiled_cost=compiled_cost,
        objective=objective,
        basis_denominator_multiplier=denominator_multiplier,
        minimum_scale_numerator=minimum_scale,
    )


def _split_source(source: bytes) -> tuple[bytes, bytes, bytes]:
    if source.count(START_MARKER.encode()) != 1 or source.count(END_MARKER.encode()) != 1:
        raise EvaluationError("candidate must contain exactly one pair of EVOLVE markers")
    start = source.index(START_MARKER.encode())
    end = source.index(END_MARKER.encode(), start)
    end += len(END_MARKER)
    return source[:start], source[start:end], source[end:]


def _validate_candidate_shell(candidate_path: Path, maximum_bytes: int) -> bytes:
    if not candidate_path.is_file():
        raise EvaluationError("candidate C++ source does not exist")
    source = candidate_path.read_bytes()
    if not source or len(source) > maximum_bytes:
        raise EvaluationError("candidate source is empty or exceeds size limit")
    baseline = BASELINE_PATH.read_bytes()
    candidate_prefix, _, candidate_suffix = _split_source(source)
    baseline_prefix, _, baseline_suffix = _split_source(baseline)
    if candidate_prefix != baseline_prefix or candidate_suffix != baseline_suffix:
        raise EvaluationError("candidate changed code outside the EVOLVE block")
    return source


def _tail(path: Path, maximum: int = 4000) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    return data[-maximum:].decode("utf-8", errors="replace")


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
        "-pipe",
        "-Wall",
        "-Wextra",
        "-I",
        str(RUNTIME_INCLUDE),
        str(source),
        "-o",
        str(output),
    ]
    with log_path.open("wb") as log:
        try:
            completed = subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout_s,
                check=False,
                env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"},
            )
        except subprocess.TimeoutExpired as exc:
            raise EvaluationError(f"compilation timed out after {timeout_s:.1f}s") from exc
    if completed.returncode != 0:
        raise EvaluationError(f"compilation failed: {_tail(log_path)}")


@dataclass(frozen=True)
class ProgramRun:
    certificate: bytes
    stdout_tail: str
    elapsed_s: float


def _run_program(
    executable: Path,
    workload: Workload,
    run_dir: Path,
    timeout_s: float,
    maximum_certificate_bytes: int,
    memory_mb: int,
) -> ProgramRun:
    run_dir.mkdir(parents=True, exist_ok=False)
    input_path = run_dir / "kernel.kbe"
    certificate_path = run_dir / "construction.kbc"
    log_path = run_dir / "candidate.log"
    input_path.write_bytes(workload.input_bytes)
    cpu_seconds = max(1, int(math.ceil(timeout_s)) + 1)
    file_limit = max(maximum_certificate_bytes, 64 * 1024)
    command = [
        sys.executable,
        str(LIMITED_EXEC),
        str(memory_mb),
        str(cpu_seconds),
        str(file_limit),
        str(run_dir),
        "--",
        str(executable),
        "--input",
        str(input_path),
        "--certificate",
        str(certificate_path),
    ]
    started = time.perf_counter()
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=False,
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
    try:
        # The candidate is session leader. Remove any descendants it left behind
        # before inspecting the supposedly frozen input and certificate.
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    elapsed = time.perf_counter() - started
    if returncode != 0:
        raise EvaluationError(f"candidate exited with code {returncode}: {_tail(log_path)}")
    if input_path.read_bytes() != workload.input_bytes:
        raise EvaluationError("candidate modified the frozen kernel input")
    if not certificate_path.is_file():
        raise EvaluationError("candidate did not produce a construction certificate")
    if certificate_path.stat().st_size > maximum_certificate_bytes:
        raise EvaluationError("construction certificate exceeds size limit")
    return ProgramRun(
        certificate=certificate_path.read_bytes(),
        stdout_tail=_tail(log_path),
        elapsed_s=elapsed,
    )


def _construction_artifact(
    certificate: Certificate,
    checked: CheckedConstruction,
    run: ProgramRun,
) -> dict[str, Any]:
    return {
        "basis_mask": certificate.basis_mask,
        "scale_numerator": certificate.scale_numerator,
        "minimum_scale_numerator": checked.minimum_scale_numerator,
        "basis_denominator_multiplier": checked.basis_denominator_multiplier,
        "alpha": checked.alpha,
        "frobenius_error": checked.frobenius_error,
        "error_upper_bound": checked.error_upper_bound,
        "relative_error": checked.relative_error,
        "rotations": checked.rotations,
        "oracle_cnots": checked.oracle_cnots,
        "cnots": checked.cnots,
        "hadamards": checked.hadamards,
        "depth": checked.depth,
        "qubits": checked.qubits,
        "compiled_cost": checked.compiled_cost,
        "objective": checked.objective,
        "nonzero_angles": sum(tick != 0 for tick in certificate.angle_ticks),
        "certificate_bytes": certificate.byte_count,
        "certificate_sha256": certificate.sha256,
        "runtime_s": run.elapsed_s,
        "stdout_tail": run.stdout_tail,
    }


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
        "benchmark_id": "kernel_block_encoding",
        "checker": "independent analytic FABLE block reconstruction",
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
            else float(limits["candidate_timeout_s_per_workload"])
        )
        if timeout_s <= 0.0:
            raise EvaluationError("candidate timeout must be positive")
        compile_timeout = float(limits["compile_timeout_s"])
        matrix_scale = int(config["matrix_scale"])
        workloads = [_build_workload(spec, matrix_scale) for spec in config["workloads"]]
        artifacts["workload_manifest"] = [
            {
                "id": workload.workload_id,
                "dimension": workload.dimension,
                "epsilon": workload.epsilon,
                "input_bytes": len(workload.input_bytes),
                "sha256": workload.sha256,
            }
            for workload in workloads
        ]

        with tempfile.TemporaryDirectory(prefix="kernel_block_encoding_eval_") as temporary:
            temp = Path(temporary)
            candidate_copy = temp / "candidate.cpp"
            candidate_copy.write_bytes(source)
            candidate_executable = temp / "candidate"
            baseline_executable = temp / "baseline"
            baseline_compile_log = temp / "baseline_compile.log"
            candidate_compile_log = temp / "candidate_compile.log"
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

            scores: list[float] = []
            minimum_score = math.inf
            total_candidate_rotations = 0
            total_candidate_cnots = 0
            total_baseline_rotations = 0
            total_baseline_cnots = 0
            total_checked_entries = 0
            candidate_alpha_sum = 0.0
            results: dict[str, Any] = {}
            for index, workload in enumerate(workloads):
                baseline_run = _run_program(
                    baseline_executable,
                    workload,
                    temp / f"baseline_{index}",
                    timeout_s,
                    int(limits["max_certificate_bytes"]),
                    int(limits["memory_limit_mb"]),
                )
                candidate_run = _run_program(
                    candidate_executable,
                    workload,
                    temp / f"candidate_{index}",
                    timeout_s,
                    int(limits["max_certificate_bytes"]),
                    int(limits["memory_limit_mb"]),
                )
                baseline_certificate = _parse_certificate(
                    baseline_run.certificate, workload, config
                )
                candidate_certificate = _parse_certificate(
                    candidate_run.certificate, workload, config
                )
                baseline_checked = _check_construction(
                    baseline_certificate, workload, config
                )
                candidate_checked = _check_construction(
                    candidate_certificate, workload, config
                )
                score = baseline_checked.objective / candidate_checked.objective
                if not math.isfinite(score) or score <= 0.0:
                    raise EvaluationError("scenario score is non-positive or non-finite")
                scores.append(score)
                minimum_score = min(minimum_score, score)
                total_candidate_rotations += candidate_checked.rotations
                total_candidate_cnots += candidate_checked.cnots
                total_baseline_rotations += baseline_checked.rotations
                total_baseline_cnots += baseline_checked.cnots
                total_checked_entries += workload.dimension * workload.dimension
                candidate_alpha_sum += candidate_checked.alpha
                results[workload.workload_id] = {
                    "score": score,
                    "epsilon": workload.epsilon,
                    "input_sha256": workload.sha256,
                    "baseline": _construction_artifact(
                        baseline_certificate, baseline_checked, baseline_run
                    ),
                    "candidate": _construction_artifact(
                        candidate_certificate, candidate_checked, candidate_run
                    ),
                }

            combined_score = math.exp(
                math.fsum(math.log(score) for score in scores) / len(scores)
            )
            runtime_s = time.perf_counter() - started
            metrics = {
                "combined_score": combined_score,
                "valid": 1.0,
                "timeout": 0.0,
                "runtime_s": runtime_s,
                "scenario_count": float(len(scores)),
                "mean_score": math.fsum(scores) / len(scores),
                "min_score": minimum_score,
                "baseline_total_rotations": float(total_baseline_rotations),
                "candidate_total_rotations": float(total_candidate_rotations),
                "baseline_total_cnots": float(total_baseline_cnots),
                "candidate_total_cnots": float(total_candidate_cnots),
                "candidate_mean_alpha": candidate_alpha_sum / len(scores),
                "checked_matrix_entries": float(total_checked_entries),
            }
            artifacts["compiler"] = compiler
            artifacts["compile"] = {
                "baseline_s": baseline_compile_s,
                "candidate_s": candidate_compile_s,
            }
            artifacts["objective"] = config["objective"]
            artifacts["limits"] = limits
            artifacts["workloads"] = results
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
