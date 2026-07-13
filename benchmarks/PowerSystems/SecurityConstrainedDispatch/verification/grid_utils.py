from __future__ import annotations

import contextlib
import copy
import io
from pathlib import Path
from typing import Any

import numpy as np
from matpowercaseframes import CaseFrames
from pypower.api import ppoption, runopf, runpf
from pypower.idx_brch import (
    ANGMAX,
    ANGMIN,
    BR_B,
    BR_R,
    BR_STATUS,
    BR_X,
    F_BUS,
    PF,
    PT,
    QF,
    QT,
    RATE_A,
    SHIFT,
    TAP,
    T_BUS,
)
from pypower.idx_bus import BASE_KV, BUS_I, BUS_TYPE, PD, QD, VA, VM, VMAX, VMIN
from pypower.idx_gen import (
    GEN_BUS,
    GEN_STATUS,
    PG,
    PMAX,
    PMIN,
    QG,
    QMAX,
    QMIN,
    VG,
)
from pypower.totcost import totcost


PF_OPTIONS = ppoption(
    VERBOSE=0,
    OUT_ALL=0,
    PF_ALG=1,
    PF_TOL=1e-9,
    PF_MAX_IT=40,
)
OPF_OPTIONS = ppoption(
    VERBOSE=0,
    OUT_ALL=0,
    OPF_VIOLATION=2e-5,
    PDIPM_FEASTOL=1e-7,
)


def load_case(path: str | Path) -> dict[str, Any]:
    mpc = CaseFrames(str(path)).to_mpc()
    for key in ("bus", "gen", "branch", "gencost"):
        mpc[key] = np.asarray(mpc[key], dtype=float)
    return mpc


def apply_scenario(
    source: dict[str, Any],
    *,
    load_scale: float,
    outage_branch: int | None,
) -> dict[str, Any]:
    mpc = copy.deepcopy(source)
    mpc["bus"][:, PD] *= float(load_scale)
    mpc["bus"][:, QD] *= float(load_scale)
    if outage_branch is not None:
        if outage_branch < 0 or outage_branch >= len(mpc["branch"]):
            raise IndexError(f"outage branch {outage_branch} is out of range")
        mpc["branch"][outage_branch, BR_STATUS] = 0.0
    return mpc


def _quiet_call(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return function(*args, **kwargs)


def run_reference_opf(mpc: dict[str, Any]) -> dict[str, Any]:
    return _quiet_call(runopf, copy.deepcopy(mpc), OPF_OPTIONS)


def run_candidate_pf(
    mpc: dict[str, Any],
    pg_mw: np.ndarray,
    vg_pu: np.ndarray,
) -> dict[str, Any]:
    candidate = copy.deepcopy(mpc)
    candidate["gen"][:, PG] = np.asarray(pg_mw, dtype=float)
    candidate["gen"][:, VG] = np.asarray(vg_pu, dtype=float)
    result, _ = _quiet_call(runpf, candidate, PF_OPTIONS)
    return result


def generation_cost(result: dict[str, Any]) -> float:
    values = totcost(result["gencost"], result["gen"][:, PG])
    return float(np.sum(values))


def assess_result(result: dict[str, Any]) -> tuple[bool, dict[str, float]]:
    if not bool(result.get("success", False)):
        return False, {"converged": 0.0}

    bus = np.asarray(result["bus"], dtype=float)
    gen = np.asarray(result["gen"], dtype=float)
    branch = np.asarray(result["branch"], dtype=float)

    if not all(np.isfinite(array).all() for array in (bus, gen, branch)):
        return False, {"converged": 1.0, "nonfinite": 1.0}

    online_gen = gen[:, GEN_STATUS] > 0
    online_branch = branch[:, BR_STATUS] > 0
    rated_branch = online_branch & (branch[:, RATE_A] > 0)

    voltage_low = float(np.maximum(bus[:, VMIN] - bus[:, VM], 0.0).max(initial=0.0))
    voltage_high = float(np.maximum(bus[:, VM] - bus[:, VMAX], 0.0).max(initial=0.0))
    p_low = float(np.maximum(gen[online_gen, PMIN] - gen[online_gen, PG], 0.0).max(initial=0.0))
    p_high = float(np.maximum(gen[online_gen, PG] - gen[online_gen, PMAX], 0.0).max(initial=0.0))
    q_low = float(np.maximum(gen[online_gen, QMIN] - gen[online_gen, QG], 0.0).max(initial=0.0))
    q_high = float(np.maximum(gen[online_gen, QG] - gen[online_gen, QMAX], 0.0).max(initial=0.0))

    apparent_from = np.hypot(branch[:, PF], branch[:, QF])
    apparent_to = np.hypot(branch[:, PT], branch[:, QT])
    loading = np.zeros(len(branch), dtype=float)
    loading[rated_branch] = (
        100.0
        * np.maximum(apparent_from[rated_branch], apparent_to[rated_branch])
        / branch[rated_branch, RATE_A]
    )
    max_loading = float(loading[rated_branch].max(initial=0.0))
    thermal_violation = max(0.0, max_loading - 100.0)

    bus_rows = {int(bus_id): row for row, bus_id in enumerate(bus[:, BUS_I])}
    angle_difference = np.asarray(
        [
            bus[bus_rows[int(from_bus)], VA] - bus[bus_rows[int(to_bus)], VA]
            for from_bus, to_bus in branch[:, [F_BUS, T_BUS]]
        ],
        dtype=float,
    )
    angle_low = float(
        np.maximum(branch[online_branch, ANGMIN] - angle_difference[online_branch], 0.0).max(initial=0.0)
    )
    angle_high = float(
        np.maximum(angle_difference[online_branch] - branch[online_branch, ANGMAX], 0.0).max(initial=0.0)
    )

    violations = {
        "converged": 1.0,
        "max_loading_percent": max_loading,
        "min_voltage_pu": float(bus[:, VM].min()),
        "max_voltage_pu": float(bus[:, VM].max()),
        "voltage_violation_pu": max(voltage_low, voltage_high),
        "active_power_violation_mw": max(p_low, p_high),
        "reactive_power_violation_mvar": max(q_low, q_high),
        "thermal_violation_percent": thermal_violation,
        "angle_violation_deg": max(angle_low, angle_high),
    }
    valid = (
        violations["voltage_violation_pu"] <= 5e-4
        and violations["active_power_violation_mw"] <= 5e-3
        and violations["reactive_power_violation_mvar"] <= 5e-3
        and violations["thermal_violation_percent"] <= 5e-2
        and violations["angle_violation_deg"] <= 5e-3
    )
    return bool(valid), violations


def public_payload(
    mpc: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    bus = mpc["bus"]
    gen = mpc["gen"]
    branch = mpc["branch"]
    gencost = mpc["gencost"]
    baseline_pg = scenario["baseline_pg_mw"]
    baseline_vg = scenario["baseline_vg_pu"]

    return {
        "case_id": scenario["case_id"],
        "scenario_id": scenario["scenario_id"],
        "base_mva": float(mpc["baseMVA"]),
        "load_scale": float(scenario["load_scale"]),
        "outage_branch": scenario["outage_branch"],
        "total_active_load_mw": float(bus[:, PD].sum()),
        "buses": [
            {
                "bus_id": int(row[BUS_I]),
                "type": int(row[BUS_TYPE]),
                "pd_mw": float(row[PD]),
                "qd_mvar": float(row[QD]),
                "base_kv": float(row[BASE_KV]),
                "vmin_pu": float(row[VMIN]),
                "vmax_pu": float(row[VMAX]),
            }
            for row in bus
        ],
        "generators": [
            {
                "index": int(index),
                "bus_id": int(row[GEN_BUS]),
                "online": bool(row[GEN_STATUS] > 0),
                "pmin_mw": float(row[PMIN]),
                "pmax_mw": float(row[PMAX]),
                "qmin_mvar": float(row[QMIN]),
                "qmax_mvar": float(row[QMAX]),
                "baseline_pg_mw": float(baseline_pg[index]),
                "baseline_vg_pu": float(baseline_vg[index]),
                "cost_model": [float(value) for value in gencost[index].tolist()],
            }
            for index, row in enumerate(gen)
        ],
        "branches": [
            {
                "index": int(index),
                "from_bus": int(row[F_BUS]),
                "to_bus": int(row[T_BUS]),
                "resistance_pu": float(row[BR_R]),
                "reactance_pu": float(row[BR_X]),
                "charging_pu": float(row[BR_B]),
                "rate_a_mva": float(row[RATE_A]),
                "tap_ratio": float(row[TAP]),
                "phase_shift_deg": float(row[SHIFT]),
                "in_service": bool(row[BR_STATUS] > 0),
                "angle_min_deg": float(row[ANGMIN]),
                "angle_max_deg": float(row[ANGMAX]),
            }
            for index, row in enumerate(branch)
        ],
    }
