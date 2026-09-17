"""Independent BSM1 plant model used by the aeration-control benchmark.

The equations follow the IWA Benchmark Simulation Model No. 1: five ASM1
reactors and a ten-layer Takacs secondary settler.  The implementation was
cross-checked against ``fau-evt/bsm2-python`` and is adapted from its
BSD-3-Clause implementation; the retained license is in ``references/``.

Units are days, m3, g/m3, and kWh/day unless stated otherwise.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from scipy.integrate import odeint


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "references" / "config.json"

SI, SS, XI, XS, XBH, XBA, XP, SO, SNO, SNH, SND, XND, SALK = range(13)
TSS, Q, TEMP = 13, 14, 15
N_COMPONENTS = 16

ASM1_PARAMETERS = np.array(
    [
        4.0, 10.0, 0.2, 0.5, 0.3, 0.5, 1.0, 0.4, 0.05, 0.8,
        0.05, 3.0, 0.1, 0.8, 0.67, 0.24, 0.08, 0.08, 0.06,
        0.75, 0.75, 0.75, 0.75, 0.75,
    ],
    dtype=float,
)
VOLUMES = np.array([1000.0, 1000.0, 1333.0, 1333.0, 1333.0])
OXYGEN_SATURATION = 8.0
RETURN_FLOW = 18446.0
WASTE_FLOW = 385.0
SETTLER_AREA = 1500.0
SETTLER_HEIGHT = 4.0
SETTLER_LAYERS = 10
SETTLER_FEED_LAYER = 5
SETTLER_PARAMETERS = np.array([250.0, 474.0, 0.000576, 0.00286, 0.00228, 3000.0, 3000.0])

_REACTOR_INITIAL = np.array(
    [
        [30.0, 2.696169337, 1149.16340146, 79.78436831, 2553.45921988, 151.75632721, 449.22675116, 0.018822826, 8.310656768, 7.108011983, 1.228022799, 5.127002559, 4.659811087],
        [30.0, 1.402154895, 1149.16340144, 73.67182578, 2555.28394130, 151.67460865, 449.89826272, 0.000279954, 6.570406004, 7.536848342, 0.896501365, 4.847841192, 4.814745881],
        [30.0, 1.113091672, 1149.16340141, 62.63753037, 2558.68270986, 152.32053441, 450.79460391, 2.0, 9.544077377, 4.687308245, 0.822255969, 4.244269898, 4.398802205],
        [30.0, 0.967558516, 1149.16340138, 54.01878920, 2560.36433241, 152.85355533, 451.69155922, 2.0, 12.068200287, 2.322898686, 0.751729972, 3.767047773, 4.049621314],
        [30.0, 0.857137129, 1149.16340135, 47.36389426, 2560.70622587, 153.17106513, 452.58865148, 2.0, 13.711131912, 0.866431079, 0.690377137, 3.394128545, 3.828235655],
    ],
    dtype=float,
)
_SETTLER_TSS_INITIAL = np.array(
    [12.50109702, 18.11774069, 29.54712298, 68.99884217, 356.2589969,
     356.25899691, 356.2589969, 356.25899691, 356.2589969, 6398.69776357],
    dtype=float,
)


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _tss(components: np.ndarray) -> float:
    return float(0.75 * np.sum(components[[XI, XS, XBH, XBA, XP]]))


def _stream(components: np.ndarray, flow: float, temperature: float = 15.0) -> np.ndarray:
    result = np.zeros(N_COMPONENTS, dtype=float)
    result[:13] = components
    result[TSS] = _tss(components)
    result[Q] = float(flow)
    result[TEMP] = float(temperature)
    return result


def combine_streams(*streams: np.ndarray) -> np.ndarray:
    total_flow = float(sum(max(0.0, stream[Q]) for stream in streams))
    if total_flow <= 0.0:
        raise ValueError("cannot combine zero-flow streams")
    result = np.zeros(N_COMPONENTS, dtype=float)
    for stream in streams:
        result[:14] += stream[:14] * stream[Q]
        result[TEMP] += stream[TEMP] * stream[Q]
    result[:14] /= total_flow
    result[TEMP] /= total_flow
    result[Q] = total_flow
    return result


def _asm1_rhs(y: np.ndarray, influent: np.ndarray, kla: float, volume: float) -> np.ndarray:
    y = np.maximum(np.asarray(y, dtype=float), 1e-12)
    p = ASM1_PARAMETERS
    mu_h, k_s, k_oh, k_no, b_h, mu_a, k_nh, k_oa, b_a = p[:9]
    ny_g, k_a, k_h, k_x, ny_h, y_h, y_a, f_p, i_xb, i_xp = p[9:19]
    temp = float(influent[TEMP])
    mu_h *= math.exp((math.log(mu_h / 3.0) / 5.0) * (temp - 15.0))
    b_h *= math.exp((math.log(b_h / 0.2) / 5.0) * (temp - 15.0))
    mu_a *= math.exp((math.log(mu_a / 0.3) / 5.0) * (temp - 15.0))
    b_a *= math.exp((math.log(b_a / 0.03) / 5.0) * (temp - 15.0))
    k_h *= math.exp((math.log(k_h / 2.5) / 5.0) * (temp - 15.0))
    k_a *= math.exp((math.log(k_a / 0.04) / 5.0) * (temp - 15.0))
    kla_temp = kla * 1.024 ** (temp - 15.0)

    proc1 = mu_h * y[SS] / (k_s + y[SS]) * y[SO] / (k_oh + y[SO]) * y[XBH]
    proc2 = mu_h * y[SS] / (k_s + y[SS]) * k_oh / (k_oh + y[SO]) * y[SNO] / (k_no + y[SNO]) * ny_g * y[XBH]
    proc3 = mu_a * y[SNH] / (k_nh + y[SNH]) * y[SO] / (k_oa + y[SO]) * y[XBA]
    proc4 = b_h * y[XBH]
    proc5 = b_a * y[XBA]
    proc6 = k_a * y[SND] * y[XBH]
    ratio_xs = y[XS] / max(y[XBH], 1e-12)
    proc7 = k_h * ratio_xs / (k_x + ratio_xs) * (
        y[SO] / (k_oh + y[SO]) + ny_h * k_oh / (k_oh + y[SO]) * y[SNO] / (k_no + y[SNO])
    ) * y[XBH]
    proc8 = proc7 * y[XND] / max(y[XS], 1e-12)

    reaction = np.zeros(13, dtype=float)
    reaction[SS] = (-proc1 - proc2) / y_h + proc7
    reaction[XS] = (1.0 - f_p) * (proc4 + proc5) - proc7
    reaction[XBH] = proc1 + proc2 - proc4
    reaction[XBA] = proc3 - proc5
    reaction[XP] = f_p * (proc4 + proc5)
    reaction[SO] = -(1.0 - y_h) / y_h * proc1 - (4.57 - y_a) / y_a * proc3
    reaction[SNO] = -(1.0 - y_h) / (2.86 * y_h) * proc2 + proc3 / y_a
    reaction[SNH] = -i_xb * (proc1 + proc2) - (i_xb + 1.0 / y_a) * proc3 + proc6
    reaction[SND] = -proc6 + proc8
    reaction[XND] = (i_xb - f_p * i_xp) * (proc4 + proc5) - proc8
    reaction[SALK] = (
        -i_xb / 14.0 * proc1
        + ((1.0 - y_h) / (14.0 * 2.86 * y_h) - i_xb / 14.0) * proc2
        - (i_xb / 14.0 + 1.0 / (7.0 * y_a)) * proc3
        + proc6 / 14.0
    )
    derivative = influent[Q] / volume * (influent[:13] - y) + reaction
    derivative[SO] += kla_temp * (OXYGEN_SATURATION - y[SO])
    return derivative


def _integrate_reactor(state: np.ndarray, influent: np.ndarray, kla: float, volume: float, dt: float) -> np.ndarray:
    result = odeint(
        lambda y, _: _asm1_rhs(y, influent, kla, volume),
        state,
        np.array([0.0, dt]),
        rtol=1e-4,
        atol=1e-6,
        mxstep=500,
    )[-1]
    if not np.all(np.isfinite(result)):
        raise FloatingPointError("ASM1 integration produced non-finite state")
    return np.maximum(result, 0.0)


def _settler_rhs(state: np.ndarray, feed: np.ndarray) -> np.ndarray:
    layers = SETTLER_LAYERS
    feed_layer = SETTLER_FEED_LAYER
    height = SETTLER_HEIGHT / layers
    state = np.maximum(np.asarray(state, dtype=float), 1e-8)
    q_under = RETURN_FLOW + WASTE_FLOW
    q_effluent = feed[Q] - q_under
    if q_effluent <= 0.0:
        raise ValueError("settler effluent flow is non-positive")
    v_in = feed[Q] / SETTLER_AREA
    v_up = q_effluent / SETTLER_AREA
    v_down = q_under / SETTLER_AREA

    tss = state[7 * layers : 8 * layers]
    v0_max, v0, r_h, r_p, f_ns, x_threshold, _ = SETTLER_PARAMETERS
    velocity = v0 * (
        np.exp(-r_h * (tss - f_ns * feed[TSS]))
        - np.exp(-r_p * (tss - f_ns * feed[TSS]))
    )
    velocity = np.clip(velocity, 0.0, v0_max)
    raw_flux = velocity * tss
    flux = np.zeros(layers + 1, dtype=float)
    for index in range(layers - 1):
        if index < feed_layer - 1 and tss[index + 1] <= x_threshold:
            flux[index + 1] = raw_flux[index]
        else:
            flux[index + 1] = min(raw_flux[index], raw_flux[index + 1])

    derivative = np.zeros_like(state)
    soluble_indices = [SI, SS, SO, SNO, SNH, SND, SALK]
    for block, component in enumerate(soluble_indices):
        values = state[block * layers : (block + 1) * layers]
        out = derivative[block * layers : (block + 1) * layers]
        for index in range(feed_layer - 1):
            out[index] = v_up * (values[index + 1] - values[index]) / height
        f = feed_layer - 1
        out[f] = (v_in * feed[component] - (v_up + v_down) * values[f]) / height
        for index in range(feed_layer, layers):
            out[index] = v_down * (values[index - 1] - values[index]) / height

    out_tss = derivative[7 * layers : 8 * layers]
    for index in range(feed_layer - 1):
        out_tss[index] = (v_up * (tss[index + 1] - tss[index]) - flux[index + 1] + flux[index]) / height
    f = feed_layer - 1
    out_tss[f] = (v_in * feed[TSS] - (v_up + v_down) * tss[f] - flux[f + 1] + flux[f]) / height
    for index in range(feed_layer, layers):
        out_tss[index] = (v_down * (tss[index - 1] - tss[index]) - flux[index + 1] + flux[index]) / height
    return derivative


def _settler_outputs(state: np.ndarray, feed: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    layers = SETTLER_LAYERS
    state = np.maximum(state, 0.0)
    soluble_indices = [SI, SS, SO, SNO, SNH, SND, SALK]
    effluent = np.zeros(13, dtype=float)
    return_sludge = np.zeros(13, dtype=float)
    for block, component in enumerate(soluble_indices):
        values = state[block * layers : (block + 1) * layers]
        effluent[component] = values[0]
        return_sludge[component] = values[-1]
    top_tss = state[7 * layers]
    bottom_tss = state[8 * layers - 1]
    particulate = [XI, XS, XBH, XBA, XP, XND]
    if feed[TSS] > 1e-12:
        for component in particulate:
            effluent[component] = top_tss / feed[TSS] * feed[component]
            return_sludge[component] = bottom_tss / feed[TSS] * feed[component]
    return _stream(effluent, feed[Q] - RETURN_FLOW - WASTE_FLOW), _stream(return_sludge, RETURN_FLOW)


def influent_at(time_day: float, weather: str) -> np.ndarray:
    """Generate a deterministic BSM1 influent at a 15-minute timestamp.

    The dry profile uses the published BSM1 dynamic-load averages. Rain and
    storm add dilution water over the event windows described by the IWA
    report; pollutant mass flow is conserved during the dilution event.
    """

    phase = 2.0 * math.pi * (time_day % 1.0)
    weekend = 0.82 if int(time_day) % 7 in (5, 6) else 1.0
    flow = 18446.0 * weekend * (1.0 + 0.31 * math.sin(phase - 1.0) + 0.08 * math.sin(2.0 * phase - 0.4))
    flow = max(9000.0, flow)
    concentration_scale = 1.0 + 0.12 * math.sin(phase + 0.55) + 0.04 * math.sin(2.0 * phase)
    components = np.array(
        [30.0, 69.50, 51.20, 202.32, 28.17, 0.0, 0.0, 0.0, 0.0, 31.56, 6.95, 10.59, 7.0],
        dtype=float,
    )
    variable = [SS, XI, XS, XBH, SNH, SND, XND]
    components[variable] *= concentration_scale

    extra_water = 0.0
    if weather == "rain" and 8.35 <= time_day <= 10.44:
        edge = min((time_day - 8.35) / 0.08, (10.44 - time_day) / 0.08, 1.0)
        extra_water = 20000.0 * max(0.0, edge)
    elif weather == "storm":
        extra_water = 42000.0 * math.exp(-0.5 * ((time_day - 8.87) / 0.075) ** 2)
        extra_water += 45000.0 * math.exp(-0.5 * ((time_day - 11.18) / 0.16) ** 2)
    if extra_water > 0.0:
        dilution = flow / (flow + extra_water)
        # Added water dilutes every soluble and particulate concentration,
        # including alkalinity.  The corresponding component mass flow is
        # conserved while the hydraulic load increases.
        components[:13] *= dilution
        flow += extra_water
    return _stream(components, flow)


def advanced_quantities(effluent: np.ndarray) -> dict[str, float]:
    p = ASM1_PARAMETERS
    kjeldahl = (
        effluent[SNH] + effluent[SND] + effluent[XND]
        + p[17] * (effluent[XBH] + effluent[XBA])
        + p[18] * (effluent[XP] + effluent[XI])
    )
    cod = float(np.sum(effluent[[SI, SS, XI, XS, XBH, XBA, XP]]))
    bod5 = 0.25 * (effluent[SS] + effluent[XS] + (1.0 - p[16]) * (effluent[XBH] + effluent[XBA]))
    return {
        "total_nitrogen": float(kjeldahl + effluent[SNO]),
        "cod": cod,
        "bod5": float(bod5),
        "tss": float(effluent[TSS]),
    }


def effluent_quality_index(effluent: np.ndarray) -> float:
    advanced = advanced_quantities(effluent)
    kjeldahl = advanced["total_nitrogen"] - effluent[SNO]
    weighted = (
        2.0 * effluent[TSS]
        + advanced["cod"]
        + 30.0 * kjeldahl
        + 10.0 * effluent[SNO]
        + 2.0 * advanced["bod5"]
    )
    return float(weighted * effluent[Q] / 1000.0)


class BSM1Plant:
    """Stateful five-reactor BSM1 plant with a ten-layer settler."""

    def __init__(self) -> None:
        self.reactors = _REACTOR_INITIAL.copy()
        soluble_initial = np.array([30.0, 0.857137129, 2.0, 13.711131912, 0.866431079, 0.690377137, 3.828235655])
        self.settler = np.concatenate([np.full(SETTLER_LAYERS, value) for value in soluble_initial] + [_SETTLER_TSS_INITIAL.copy()])
        return_components = np.array([30.0, 0.857137129, 2247.12680338, 92.61753044, 5007.32236075, 299.51772354, 885.01259999, 2.0, 13.711131912, 0.866431079, 0.690377137, 6.637034575, 3.828235655])
        self.return_sludge = _stream(return_components, RETURN_FLOW)
        self.internal_recycle = _stream(self.reactors[-1], 55338.0)
        effluent_components = np.array([30.0, 0.857137129, 4.390198009, 0.180946308, 9.782775332, 0.585165960, 1.729043750, 2.0, 13.711131912, 0.866431079, 0.690377137, 0.012966734, 3.828235655])
        self.effluent = _stream(effluent_components, 18061.0)

    def step(self, influent: np.ndarray, action: Mapping[str, float], dt_days: float) -> np.ndarray:
        qintr = float(action["internal_recycle_m3_per_day"])
        self.internal_recycle[Q] = qintr
        inlet = combine_streams(influent, self.return_sludge, self.internal_recycle)
        klas = [0.0, 0.0, float(action["kla3_per_day"]), float(action["kla4_per_day"]), float(action["kla5_per_day"])]
        stream = inlet
        for index, (kla, volume) in enumerate(zip(klas, VOLUMES)):
            self.reactors[index] = _integrate_reactor(self.reactors[index], stream, kla, float(volume), dt_days)
            stream = _stream(self.reactors[index], inlet[Q], influent[TEMP])

        settler_feed = _stream(self.reactors[-1], max(stream[Q] - qintr, 1.0), influent[TEMP])
        self.internal_recycle = _stream(self.reactors[-1], qintr, influent[TEMP])
        self.settler = odeint(
            lambda y, _: _settler_rhs(y, settler_feed),
            self.settler,
            np.array([0.0, dt_days]),
            rtol=1e-4,
            atol=1e-6,
            mxstep=1000,
        )[-1]
        if not np.all(np.isfinite(self.settler)):
            raise FloatingPointError("settler integration produced non-finite state")
        self.settler = np.maximum(self.settler, 0.0)
        self.effluent, self.return_sludge = _settler_outputs(self.settler, settler_feed)
        return self.effluent.copy()


def action_energy(action: Mapping[str, float]) -> dict[str, float]:
    klas = np.array([0.0, 0.0, action["kla3_per_day"], action["kla4_per_day"], action["kla5_per_day"]], dtype=float)
    aeration = float(np.sum(OXYGEN_SATURATION * VOLUMES * klas) / (1.8 * 1000.0))
    pumping = float(0.004 * action["internal_recycle_m3_per_day"] + 0.008 * RETURN_FLOW + 0.05 * WASTE_FLOW)
    mixing = float(24.0 * 0.005 * np.sum(VOLUMES[klas < 20.0]))
    return {"aeration": aeration, "pumping": pumping, "mixing": mixing}
