import json
import math
import os
import selectors
import subprocess
import sys
import tempfile
from pathlib import Path

import wntr
from wntr.epanet.toolkit import ENepanet
from wntr.epanet.util import EN, FlowUnits, HydParam, to_si

PUMPS = ("10", "335")
TANKS = ("1", "2", "3")
_SERVICE_CONTRACT = json.loads(
    (Path(__file__).parents[1] / "references" / "service_nodes.json").read_text(
        encoding="utf-8"
    )
)
SERVICE_NODES = tuple(_SERVICE_CONTRACT["service_nodes"])
MINIMUM_PRESSURE_M = float(_SERVICE_CONTRACT["minimum_pressure_m"])
HOUR_S = 3600
DURATION_S = 24 * HOUR_S
HYDRAULIC_STEP_S = 300


def load_controller(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"candidate not found: {path}")
    return path


class IsolatedController:
    """Run a controller with only a JSON observation/action interface."""

    def __init__(self, source, timeout_s):
        self.temp = tempfile.TemporaryDirectory(prefix="wntr-controller-")
        candidate = Path(self.temp.name) / "candidate.py"
        candidate.write_bytes(Path(source).read_bytes())
        worker = Path(__file__).with_name("controller_worker.py")
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0"}
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-S", str(worker), str(candidate)],
            cwd=self.temp.name,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        ready = self._read(timeout_s)
        if not ready.get("ready"):
            error = ready.get("error", "candidate failed to load")
            self.close()
            raise ValueError(error)

    def _read(self, timeout_s):
        selector = selectors.DefaultSelector()
        try:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if not selector.select(timeout_s):
                raise TimeoutError("control call timed out")
            line = self.process.stdout.readline()
        finally:
            selector.close()
        if not line:
            raise ValueError("controller process exited")
        return json.loads(line)

    def call(self, observation, timeout_s):
        self.process.stdin.write(json.dumps(observation, allow_nan=False) + "\n")
        self.process.stdin.flush()
        response = self._read(timeout_s)
        if not response.get("ok"):
            raise ValueError(response.get("error", "controller call failed"))
        return response.get("action")

    def close(self):
        if getattr(self, "process", None) is not None:
            self.process.kill()
            self.process.wait(timeout=2)
            self.process = None
        self.temp.cleanup()


def _network(scenario):
    """Construct one continuous 24-hour Net3 model for a scenario."""
    wn = wntr.network.WaterNetworkModel("Net3")
    for name in list(wn.control_name_list):
        wn.remove_control(name)
    wn.options.time.duration = DURATION_S
    wn.options.time.hydraulic_timestep = HYDRAULIC_STEP_S
    wn.options.time.report_timestep = HYDRAULIC_STEP_S
    wn.options.time.pattern_timestep = HOUR_S
    wn.options.time.pattern_start = 0
    wn.options.hydraulic.demand_multiplier = 1.0

    multipliers = scenario["demand_multipliers"]
    for _, pattern in wn.patterns():
        original = list(pattern.multipliers)
        pattern.multipliers = [
            original[hour % len(original)] * multipliers[hour]
            for hour in range(24)
        ]

    for name in TANKS:
        tank = wn.get_node(name)
        tank.init_level += scenario["initial_tank_offsets_m"].get(name, 0.0)

    leak = scenario.get("leak")
    if leak:
        wn.get_node(leak["junction"]).add_leak(
            wn,
            area=leak["area_m2"],
            start_time=leak["start_hour"] * HOUR_S,
            end_time=leak["end_hour"] * HOUR_S,
        )
    return wn


class ContinuousHydraulics:
    """Small EPANET toolkit adapter retaining one hydraulic session."""

    def __init__(self, wn, directory):
        self.wn = wn
        self.directory = Path(directory)
        self.inp = self.directory / "network.inp"
        wntr.network.write_inpfile(wn, str(self.inp), version=2.2)
        self.toolkit = ENepanet(
            str(self.inp),
            str(self.directory / "network.rpt"),
            str(self.directory / "network.bin"),
            version=2.2,
        )
        self.toolkit.ENopen()
        self.units = FlowUnits(self.toolkit.ENgetflowunits())
        self.node_index = {
            name: self.toolkit.ENgetnodeindex(name)
            for name in set(TANKS + SERVICE_NODES)
        }
        self.tank_elevation = {
            name: wn.get_node(name).elevation for name in TANKS
        }
        self.link_index = {
            name: self.toolkit.ENgetlinkindex(name)
            for name in PUMPS + ("330",)
        }
        self.pump_nodes = {
            name: (
                self.toolkit.ENgetnodeindex(wn.get_link(name).start_node_name),
                self.toolkit.ENgetnodeindex(wn.get_link(name).end_node_name),
            )
            for name in PUMPS
        }
        self.toolkit.ENopenH()
        self.toolkit.ENinitH(0)
        self.hydraulics_open = True

    def close(self):
        if getattr(self, "toolkit", None) is None:
            return
        if getattr(self, "hydraulics_open", False):
            self.toolkit.ENcloseH()
            self.hydraulics_open = False
        self.toolkit.ENclose()
        self.toolkit = None

    def tank_levels(self):
        return {
            name: float(
                to_si(
                    self.units,
                    self.toolkit.ENgetnodevalue(index, EN.HEAD),
                    HydParam.HydraulicHead,
                )
            ) - self.tank_elevation[name]
            for name, index in self.node_index.items()
            if name in TANKS
        }

    def pressures(self):
        return {
            name: float(to_si(self.units, self.toolkit.ENgetnodevalue(self.node_index[name], EN.PRESSURE), HydParam.Pressure))
            for name in SERVICE_NODES
        }

    def apply_action(self, action):
        for name in PUMPS:
            index = self.link_index[name]
            speed = action[name]
            self.toolkit.ENsetlinkvalue(index, EN.SETTING, max(speed, 0.01))
            self.toolkit.ENsetlinkvalue(index, EN.STATUS, 1.0 if speed > 0.01 else 0.0)
        self.toolkit.ENsetlinkvalue(
            self.link_index["330"], EN.STATUS, 0.0 if action["335"] > 0.01 else 1.0
        )

    def run(self, expected_time):
        actual = self.toolkit.ENrunH()
        if actual != expected_time:
            raise RuntimeError(f"unexpected hydraulic time {actual}, expected {expected_time}")

    def next_step(self):
        return self.toolkit.ENnextH()

    def pump_power_kw(self):
        total = 0.0
        for name in PUMPS:
            flow = float(to_si(self.units, self.toolkit.ENgetlinkvalue(self.link_index[name], EN.FLOW), HydParam.Flow))
            start, end = self.pump_nodes[name]
            start_head = float(to_si(self.units, self.toolkit.ENgetnodevalue(start, EN.HEAD), HydParam.HydraulicHead))
            end_head = float(to_si(self.units, self.toolkit.ENgetnodevalue(end, EN.HEAD), HydParam.HydraulicHead))
            total += 1000.0 * 9.80665 * max(flow, 0.0) * max(end_head - start_head, 0.0) / 0.75 / 1000.0
        return total


def rollout(controller_path, scenario, call_timeout_s=1.0):
    controller = None
    hydraulics = None
    try:
        wn = _network(scenario)
        initial = {name: wn.get_node(name).init_level for name in TANKS}
        tank_bounds = {
            name: (wn.get_node(name).min_level, wn.get_node(name).max_level)
            for name in TANKS
        }
        previous = {name: 0.0 for name in PUMPS}
        switching = 0.0
        minimum_pressure = float("inf")
        hourly_energy_kwh = [0.0] * 24
        controller_calls = 0

        controller = IsolatedController(controller_path, call_timeout_s)
        with tempfile.TemporaryDirectory(prefix="wntr-pump-") as temp_dir:
            hydraulics = ContinuousHydraulics(wn, temp_dir)
            current_time = 0
            final_levels = dict(initial)
            while current_time <= DURATION_S:
                if current_time < DURATION_S and current_time % HOUR_S == 0:
                    hour = current_time // HOUR_S
                    levels = hydraulics.tank_levels()
                    observation = {
                        "hour": hour,
                        "tank_levels_m": levels,
                        "tariff": scenario["tariff"][hour],
                        "demand_multiplier": scenario["demand_multipliers"][hour],
                        "previous_action": dict(previous),
                    }
                    action = controller.call(observation, call_timeout_s)
                    controller_calls += 1
                    if not isinstance(action, dict) or set(action) != set(PUMPS):
                        raise ValueError("invalid or timed-out action")
                    action = {name: float(action[name]) for name in PUMPS}
                    if any(not math.isfinite(value) or value < 0 or value > 1 for value in action.values()):
                        raise ValueError("pump speeds must be finite and in [0,1]")
                    switching += sum(abs(action[name] - previous[name]) for name in PUMPS)
                    hydraulics.apply_action(action)
                    previous = action

                hydraulics.run(current_time)
                pressures = hydraulics.pressures()
                minimum_pressure = min(minimum_pressure, min(pressures.values()))
                final_levels = hydraulics.tank_levels()
                for name, level in final_levels.items():
                    lower, upper = tank_bounds[name]
                    if level < lower - 1e-4 or level > upper + 1e-4:
                        raise ValueError("tank bound violation")

                step_s = hydraulics.next_step()
                if step_s == 0:
                    break
                if step_s > HYDRAULIC_STEP_S:
                    raise RuntimeError(f"hydraulic step {step_s} exceeds {HYDRAULIC_STEP_S}")
                if current_time < DURATION_S:
                    hour = min(current_time // HOUR_S, 23)
                    hourly_energy_kwh[hour] += hydraulics.pump_power_kw() * step_s / HOUR_S
                current_time += step_s

            if current_time != DURATION_S:
                raise RuntimeError(f"incomplete hydraulic simulation at {current_time}s")
            if controller_calls != 24:
                raise RuntimeError(f"controller called {controller_calls} times, expected 24")

        hourly_power_kw = hourly_energy_kwh
        energy_cost = sum(
            hourly_power_kw[hour] * scenario["tariff"][hour]
            for hour in range(24)
        )
        terminal_deficit = sum(max(0.0, initial[name] - final_levels[name]) for name in TANKS)
        valid = minimum_pressure >= MINIMUM_PRESSURE_M and all(
            final_levels[name] >= initial[name] - 0.25 for name in TANKS
        )
        return {
            "valid": valid,
            "energy_cost": energy_cost,
            "peak_power_kw": max(hourly_power_kw),
            "switching": max(switching, 0.01),
            "terminal_deficit_m": max(terminal_deficit, 0.01),
            "minimum_pressure_m": minimum_pressure,
            "final_tank_levels_m": final_levels,
        }
    except Exception as exc:
        return {"valid": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if hydraulics is not None:
            try:
                hydraulics.close()
            except Exception:
                pass
        if controller is not None:
            controller.close()
