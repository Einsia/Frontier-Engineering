"""Independent CLT and Ritz verifier for balanced, symmetric laminates.

Units are N, mm, MPa, and dimensionless strain throughout this module.
The implementation deliberately does not depend on the candidate process.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "references" / "config.json"


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def public_cases(config: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = load_config() if config is None else config
    return [
        {
            "case_id": str(case["case_id"]),
            "aspect_ratio": float(case["aspect_ratio"]),
            "a_mm": float(case["a_mm"]),
            "b_mm": float(case["b_mm"]),
            "Nx_N_per_mm": float(case["Nx_N_per_mm"]),
            "Ny_N_per_mm": float(case["Ny_N_per_mm"]),
        }
        for case in cfg["cases"]
    ]


def normalize_base_angles(
    value: Any, config: Mapping[str, Any] | None = None
) -> tuple[list[int] | None, str | None]:
    cfg = load_config() if config is None else config
    laminate = cfg["laminate"]
    expected = int(laminate["design_angles"])
    if not isinstance(value, list):
        return None, "design must be a JSON list"
    if len(value) != expected:
        return None, f"design must contain exactly {expected} base angles"

    lower = int(laminate["angle_min_deg"])
    upper = int(laminate["angle_max_deg"])
    normalized: list[int] = []
    for index, raw in enumerate(value):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None, f"angle[{index}] must be a finite integer"
        number = float(raw)
        if not math.isfinite(number) or not number.is_integer():
            return None, f"angle[{index}] must be a finite integer"
        angle = int(number)
        if angle < lower or angle > upper:
            return None, f"angle[{index}]={angle} is outside [{lower}, {upper}]"
        normalized.append(angle)
    return normalized, None


def expand_balanced_symmetric(base_angles: Sequence[int | float]) -> list[float]:
    half: list[float] = []
    for raw in base_angles:
        angle = float(raw)
        half.extend((angle, -angle))
    return half + list(reversed(half))


def _reduced_stiffness(material: Mapping[str, Any]) -> np.ndarray:
    e11 = float(material["E11_MPa"])
    e22 = float(material["E22_MPa"])
    nu12 = float(material["nu12"])
    g12 = float(material["G12_MPa"])
    nu21 = nu12 * e22 / e11
    denominator = 1.0 - nu12 * nu21
    return np.array(
        [
            [e11 / denominator, nu12 * e22 / denominator, 0.0],
            [nu12 * e22 / denominator, e22 / denominator, 0.0],
            [0.0, 0.0, g12],
        ],
        dtype=float,
    )


def transformed_stiffness(angle_deg: float, material: Mapping[str, Any]) -> np.ndarray:
    q = _reduced_stiffness(material)
    q11, q12, q22, q66 = q[0, 0], q[0, 1], q[1, 1], q[2, 2]
    theta = math.radians(float(angle_deg))
    m = math.cos(theta)
    n = math.sin(theta)
    m2, n2 = m * m, n * n
    m4, n4 = m2 * m2, n2 * n2
    m3n, mn3 = m2 * m * n, m * n2 * n
    qbar11 = q11 * m4 + 2.0 * (q12 + 2.0 * q66) * m2 * n2 + q22 * n4
    qbar22 = q11 * n4 + 2.0 * (q12 + 2.0 * q66) * m2 * n2 + q22 * m4
    qbar12 = (q11 + q22 - 4.0 * q66) * m2 * n2 + q12 * (m4 + n4)
    qbar16 = (q11 - q12 - 2.0 * q66) * m3n - (q22 - q12 - 2.0 * q66) * mn3
    qbar26 = (q11 - q12 - 2.0 * q66) * mn3 - (q22 - q12 - 2.0 * q66) * m3n
    qbar66 = (q11 + q22 - 2.0 * q12 - 2.0 * q66) * m2 * n2 + q66 * (m4 + n4)
    return np.array(
        [
            [qbar11, qbar12, qbar16],
            [qbar12, qbar22, qbar26],
            [qbar16, qbar26, qbar66],
        ],
        dtype=float,
    )


def laminate_abd(
    stack_deg: Sequence[float], config: Mapping[str, Any] | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cfg = load_config() if config is None else config
    ply_t = float(cfg["laminate"]["ply_thickness_mm"])
    thickness = ply_t * len(stack_deg)
    z = np.linspace(-0.5 * thickness, 0.5 * thickness, len(stack_deg) + 1)
    a = np.zeros((3, 3), dtype=float)
    b = np.zeros((3, 3), dtype=float)
    d = np.zeros((3, 3), dtype=float)
    for index, angle in enumerate(stack_deg):
        qbar = transformed_stiffness(float(angle), cfg["material"])
        z0, z1 = float(z[index]), float(z[index + 1])
        a += qbar * (z1 - z0)
        b += 0.5 * qbar * (z1 * z1 - z0 * z0)
        d += (1.0 / 3.0) * qbar * (z1**3 - z0**3)
    return a, b, d


def maximum_strain_load_factor(
    stack_deg: Sequence[float],
    case: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> float:
    cfg = load_config() if config is None else config
    a, _, _ = laminate_abd(stack_deg, cfg)
    design_factor = float(cfg["failure"]["design_load_factor"])
    loads = design_factor * np.array(
        [float(case["Nx_N_per_mm"]), float(case["Ny_N_per_mm"]), 0.0],
        dtype=float,
    )
    strain = np.linalg.solve(a, loads)
    allow_1 = float(cfg["failure"]["epsilon_1_allowable"])
    allow_2 = float(cfg["failure"]["epsilon_2_allowable"])
    allow_12 = float(cfg["failure"]["gamma_12_allowable"])
    factors: list[float] = []
    for angle_deg in stack_deg:
        theta = math.radians(float(angle_deg))
        m, n = math.cos(theta), math.sin(theta)
        ex, ey, gxy = (float(item) for item in strain)
        e1 = m * m * ex + n * n * ey + m * n * gxy
        e2 = n * n * ex + m * m * ey - m * n * gxy
        g12 = -2.0 * m * n * ex + 2.0 * m * n * ey + (m * m - n * n) * gxy
        for allowable, actual in ((allow_1, e1), (allow_2, e2), (allow_12, g12)):
            if abs(actual) > 1e-15:
                factors.append(allowable / abs(actual))
    if not factors:
        return float("inf")
    return float(min(factors))


def _ritz_matrices(
    d: np.ndarray,
    case: Mapping[str, Any],
    modes_x: int,
    modes_y: int,
    quadrature_order: int,
) -> tuple[np.ndarray, np.ndarray]:
    a = float(case["a_mm"])
    b = float(case["b_mm"])
    nx = max(0.0, -float(case["Nx_N_per_mm"]))
    ny = max(0.0, -float(case["Ny_N_per_mm"]))
    if nx + ny <= 0.0:
        raise ValueError("buckling requires at least one compressive membrane load")

    nodes, weights = np.polynomial.legendre.leggauss(quadrature_order)
    xs = 0.5 * a * (nodes + 1.0)
    ys = 0.5 * b * (nodes + 1.0)
    scaled_weights = 0.25 * a * b * np.outer(weights, weights)
    basis = [(m, n) for m in range(1, modes_x + 1) for n in range(1, modes_y + 1)]
    size = len(basis)
    stiffness = np.zeros((size, size), dtype=float)
    geometric = np.zeros((size, size), dtype=float)

    for ix, x in enumerate(xs):
        for iy, y in enumerate(ys):
            curvature = np.zeros((3, size), dtype=float)
            grad_x = np.zeros(size, dtype=float)
            grad_y = np.zeros(size, dtype=float)
            for column, (mode_x, mode_y) in enumerate(basis):
                alpha = mode_x * math.pi / a
                beta = mode_y * math.pi / b
                sin_x, cos_x = math.sin(alpha * x), math.cos(alpha * x)
                sin_y, cos_y = math.sin(beta * y), math.cos(beta * y)
                curvature[:, column] = (
                    alpha * alpha * sin_x * sin_y,
                    beta * beta * sin_x * sin_y,
                    -2.0 * alpha * beta * cos_x * cos_y,
                )
                grad_x[column] = alpha * cos_x * sin_y
                grad_y[column] = beta * sin_x * cos_y
            weight = float(scaled_weights[ix, iy])
            stiffness += weight * (curvature.T @ d @ curvature)
            geometric += weight * (
                nx * np.outer(grad_x, grad_x) + ny * np.outer(grad_y, grad_y)
            )
    return 0.5 * (stiffness + stiffness.T), 0.5 * (geometric + geometric.T)


def buckling_load_factor(
    stack_deg: Sequence[float],
    case: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> float:
    cfg = load_config() if config is None else config
    _, _, d = laminate_abd(stack_deg, cfg)
    buckling = cfg["buckling"]
    k, g = _ritz_matrices(
        d,
        case,
        int(buckling["modes_x"]),
        int(buckling["modes_y"]),
        int(buckling["quadrature_order"]),
    )
    eigenvalues_g, vectors_g = np.linalg.eigh(g)
    tolerance = max(1e-12, 1e-10 * float(np.max(eigenvalues_g)))
    keep = eigenvalues_g > tolerance
    if not np.any(keep):
        raise np.linalg.LinAlgError("geometric stiffness is singular")
    transform = vectors_g[:, keep] / np.sqrt(eigenvalues_g[keep])[None, :]
    reduced = transform.T @ k @ transform
    eigenvalues = np.linalg.eigvalsh(0.5 * (reduced + reduced.T))
    positive = eigenvalues[eigenvalues > 1e-9]
    if positive.size == 0:
        raise np.linalg.LinAlgError("no positive buckling eigenvalue")
    return float(positive[0])


def evaluate_base_angles(
    base_angles: Sequence[int | float],
    case: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    cfg = load_config() if config is None else config
    stack = expand_balanced_symmetric(base_angles)
    expected = int(cfg["laminate"]["num_plies"])
    if len(stack) != expected:
        raise ValueError(f"expanded stack has {len(stack)} plies, expected {expected}")
    failure = maximum_strain_load_factor(stack, case, cfg)
    buckling = buckling_load_factor(stack, case, cfg)
    reserve = min(failure, buckling)
    if not all(math.isfinite(value) and value > 0.0 for value in (failure, buckling, reserve)):
        raise ValueError("mechanics produced a non-positive or non-finite load factor")
    return {
        "failure_load_factor": float(failure),
        "buckling_load_factor": float(buckling),
        "reserve_factor": float(reserve),
    }
