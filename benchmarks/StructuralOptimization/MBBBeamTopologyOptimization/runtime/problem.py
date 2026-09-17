from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np
import pymoto as pym
from scipy.sparse import SparseEfficiencyWarning


warnings.filterwarnings("ignore", category=SparseEfficiencyWarning)

PROBLEM = {
    "geometry": "mbb_half",
    "nx": 48,
    "ny": 16,
    "volume_fraction": 0.5,
    "minimum_density": 0.001,
    "filter_radius": 1.5,
    "penalty_power": 3.0,
    "move_limit": 0.2,
    "max_iterations": 30,
    "load_scale": 1.0
}
SAMPLE_INSTANCE = {
    "title": "MBB Beam Topology Optimization",
    "geometry": PROBLEM["geometry"],
    "domain_shape": [PROBLEM["nx"], PROBLEM["ny"]],
    "volume_fraction": PROBLEM["volume_fraction"],
    "filter_radius": PROBLEM["filter_radius"],
    "penalty_power": PROBLEM["penalty_power"],
    "max_iterations": PROBLEM["max_iterations"],
}


def load_instance() -> dict[str, Any]:
    return dict(SAMPLE_INSTANCE)


def _passive_masks(domain: pym.VoxelDomain) -> tuple[np.ndarray, np.ndarray]:
    solid = np.zeros(domain.nel, dtype=bool)
    void = np.zeros(domain.nel, dtype=bool)
    top_rows = int(PROBLEM.get("passive_solid_top_rows", 0))
    for offset in range(top_rows):
        y = PROBLEM["ny"] - 1 - offset
        solid[domain.elements[:, y, 0].reshape(-1)] = True
    return solid, void


def _initial_density(domain: pym.VoxelDomain, solid_mask: np.ndarray, void_mask: np.ndarray) -> np.ndarray:
    target_sum = PROBLEM["volume_fraction"] * domain.nel
    fixed_sum = float(np.sum(solid_mask)) + PROBLEM["minimum_density"] * float(np.sum(void_mask))
    free_mask = ~(solid_mask | void_mask)
    free_count = int(np.sum(free_mask))
    if free_count == 0:
        raise ValueError("no free design variables remain")
    free_density = (target_sum - fixed_sum) / free_count
    if not (PROBLEM["minimum_density"] <= free_density <= 1.0):
        raise ValueError("target volume is infeasible for the chosen passive masks")
    density = np.full(domain.nel, free_density, dtype=float)
    density[solid_mask] = 1.0
    density[void_mask] = PROBLEM["minimum_density"]
    return density


def _fixed_dofs(domain: pym.VoxelDomain) -> np.ndarray:
    geometry = PROBLEM["geometry"]
    if geometry == "cantilever":
        left_nodes = domain.nodes[0, :].flatten()
        return domain.get_dofnumber(left_nodes, [0, 1], 2).flatten()
    if geometry in {"mbb_half", "bridge_half"}:
        left_nodes = domain.nodes[0, :].flatten()
        left_x = domain.get_dofnumber(left_nodes, 0, 2).flatten()
        right_bottom = int(domain.nodes[PROBLEM["nx"], 0, 0])
        return np.concatenate([left_x, np.array([2 * right_bottom + 1], dtype=int)])
    raise ValueError(f"unsupported geometry: {geometry}")


def _force_vector(domain: pym.VoxelDomain) -> np.ndarray:
    f = np.zeros(domain.nnodes * 2, dtype=float)
    geometry = PROBLEM["geometry"]
    load = float(PROBLEM["load_scale"])
    if geometry == "cantilever":
        force_node = int(domain.nodes[PROBLEM["nx"], PROBLEM["ny"] // 2, 0])
        f[2 * force_node + 1] = load
        return f
    if geometry == "mbb_half":
        force_node = int(domain.nodes[0, PROBLEM["ny"], 0])
        f[2 * force_node + 1] = -load
        return f
    if geometry == "bridge_half":
        deck_nodes = domain.nodes[:, PROBLEM["ny"], 0].flatten()
        f[2 * deck_nodes + 1] = -load / len(deck_nodes)
        return f
    raise ValueError(f"unsupported geometry: {geometry}")


def _build_context() -> dict[str, Any]:
    domain = pym.VoxelDomain(PROBLEM["nx"], PROBLEM["ny"])
    fixed_dofs = _fixed_dofs(domain)
    force = _force_vector(domain)
    passive_solid_mask, passive_void_mask = _passive_masks(domain)
    x0 = _initial_density(domain, passive_solid_mask, passive_void_mask)
    signal = pym.Signal("x", state=x0.copy())
    with pym.Network() as network:
        filtered = pym.DensityFilter(domain=domain, radius=PROBLEM["filter_radius"])(signal)
        penalized = pym.MathExpression(
            expression=f"{PROBLEM['minimum_density']} + {1.0 - PROBLEM['minimum_density']}*inp0^{PROBLEM['penalty_power']}"
        )(filtered)
        stiffness = pym.AssembleStiffness(domain=domain, bc=fixed_dofs)(penalized)
        displacement = pym.LinSolve(symmetric=True, positive_definite=True)(stiffness, force)
        compliance = pym.EinSum(expression="i,i->")(displacement, force)
    network.response()
    return {
        "domain": domain,
        "fixed_dofs": fixed_dofs,
        "force": force,
        "signal": signal,
        "network": network,
        "compliance_signal": compliance,
        "passive_solid_mask": passive_solid_mask,
        "passive_void_mask": passive_void_mask,
    }


def _extract_density(value: Any, expected_size: int) -> np.ndarray:
    if isinstance(value, dict):
        if "density" not in value:
            raise ValueError("missing density key")
        value = value["density"]
    density = np.asarray(value, dtype=float).reshape(-1)
    if density.size != expected_size:
        raise ValueError(f"density must have length {expected_size}, got {density.size}")
    if not np.all(np.isfinite(density)):
        raise ValueError("density contains non-finite values")
    return density


def _target_density_sum(state: dict[str, Any]) -> float:
    return float(state["target_density_sum"])


def density_bounds(previous_density: np.ndarray, state: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    lower = np.maximum(float(state["minimum_density"]), previous_density - float(state["move_limit"]))
    upper = np.minimum(1.0, previous_density + float(state["move_limit"]))
    solid_mask = np.asarray(state["passive_solid_mask"], dtype=bool)
    void_mask = np.asarray(state["passive_void_mask"], dtype=bool)
    if solid_mask.any():
        lower = lower.copy()
        upper = upper.copy()
        lower[solid_mask] = 1.0
        upper[solid_mask] = 1.0
    if void_mask.any():
        lower = lower.copy()
        upper = upper.copy()
        lower[void_mask] = float(state["minimum_density"])
        upper[void_mask] = float(state["minimum_density"])
    return lower, upper


def _project_sum_with_bounds(raw: np.ndarray, lower: np.ndarray, upper: np.ndarray, target_sum: float) -> np.ndarray:
    if float(np.sum(lower)) - 1e-9 > target_sum or float(np.sum(upper)) + 1e-9 < target_sum:
        raise ValueError("target density sum is infeasible under current bounds")
    lam_low = float(np.min(raw - upper))
    lam_high = float(np.max(raw - lower))
    for _ in range(80):
        lam = 0.5 * (lam_low + lam_high)
        candidate = np.clip(raw - lam, lower, upper)
        if float(np.sum(candidate)) > target_sum:
            lam_low = lam
        else:
            lam_high = lam
    return np.clip(raw - lam_high, lower, upper)


def project_density(raw_density: Any, previous_density: np.ndarray, state: dict[str, Any]) -> np.ndarray:
    raw = _extract_density(raw_density, previous_density.size)
    lower, upper = density_bounds(previous_density, state)
    return _project_sum_with_bounds(raw, lower, upper, _target_density_sum(state))


def validate_density(candidate_density: np.ndarray, previous_density: np.ndarray, state: dict[str, Any]) -> None:
    lower, upper = density_bounds(previous_density, state)
    tol = 1e-6
    if np.any(candidate_density < lower - tol) or np.any(candidate_density > upper + tol):
        raise ValueError("density violates bounds, move limit, or passive masks")
    volume_error = abs(float(np.sum(candidate_density)) - _target_density_sum(state))
    if volume_error > 1e-4:
        raise ValueError("density violates target volume")


def oc_update(density: np.ndarray, sensitivity: np.ndarray, state: dict[str, Any]) -> np.ndarray:
    lower, upper = density_bounds(density, state)
    sens = np.asarray(sensitivity, dtype=float).reshape(-1)
    if sens.shape != density.shape:
        raise ValueError("sensitivity shape mismatch")
    sens = np.minimum(sens, -1e-12)
    l1, l2 = 1e-9, 1e9
    for _ in range(80):
        lam = 0.5 * (l1 + l2)
        candidate = np.clip(density * np.sqrt(np.maximum(1e-12, -sens / lam)), lower, upper)
        if float(np.sum(candidate)) > _target_density_sum(state):
            l1 = lam
        else:
            l2 = lam
    return np.clip(density * np.sqrt(np.maximum(1e-12, -sens / l2)), lower, upper)


def run_optimization(update_density, max_iterations: int | None = None) -> dict[str, Any]:
    context = _build_context()
    signal = context["signal"]
    network = context["network"]
    compliance_signal = context["compliance_signal"]

    history: list[float] = [float(compliance_signal.state)]
    iterations = int(PROBLEM["max_iterations"] if max_iterations is None else max_iterations)
    for iteration in range(iterations):
        network.reset()
        compliance_signal.sensitivity = 1.0
        network.sensitivity()
        density = np.asarray(signal.state, dtype=float).reshape(-1).copy()
        sensitivity = np.asarray(signal.sensitivity, dtype=float).reshape(-1).copy()
        state = {
            "iteration": iteration,
            "domain_shape": (PROBLEM["nx"], PROBLEM["ny"]),
            "volume_fraction": PROBLEM["volume_fraction"],
            "target_density_sum": PROBLEM["volume_fraction"] * context["domain"].nel,
            "minimum_density": PROBLEM["minimum_density"],
            "move_limit": PROBLEM["move_limit"],
            "current_compliance": float(compliance_signal.state),
            "history": tuple(history),
            "passive_solid_mask": context["passive_solid_mask"].copy(),
            "passive_void_mask": context["passive_void_mask"].copy(),
        }
        candidate = update_density(density.copy(), sensitivity.copy(), state)
        density_next = _extract_density(candidate, density.size)
        validate_density(density_next, density, state)
        signal.state = density_next
        network.response()
        history.append(float(compliance_signal.state))

    final_density = np.asarray(signal.state, dtype=float).reshape(-1)
    return {
        "valid": True,
        "compliance": float(compliance_signal.state),
        "history": history,
        "iterations": iterations,
        "final_volume_fraction": float(np.mean(final_density)),
        "volume_fraction_error": abs(float(np.mean(final_density)) - PROBLEM["volume_fraction"]),
    }
