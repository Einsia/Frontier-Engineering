import importlib.util
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
from rollout import IsolatedController


def test_baseline_contract():
    path = Path(__file__).parents[2] / "scripts" / "init.py"
    spec = importlib.util.spec_from_file_location("candidate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observation = {"hour": 0, "tank_levels_m": {"1": 4.0, "2": 7.0, "3": 8.8}, "tariff": 0.1, "demand_multiplier": 1.0, "previous_action": {"10": 0.0, "335": 0.0}}
    action = module.control(observation)
    assert set(action) == {"10", "335"}
    assert all(0 <= value <= 1 for value in action.values())


def test_isolated_controller_accepts_baseline():
    path = Path(__file__).parents[2] / "scripts" / "init.py"
    controller = IsolatedController(path, 1.0)
    try:
        observation = {"hour": 0, "tank_levels_m": {"1": 4.0, "2": 7.0, "3": 8.8}, "tariff": 0.1, "demand_multiplier": 1.0, "previous_action": {"10": 0.0, "335": 0.0}}
        assert set(controller.call(observation, 1.0)) == {"10", "335"}
    finally:
        controller.close()


def test_isolated_controller_rejects_file_access(tmp_path):
    candidate = tmp_path / "candidate.py"
    candidate.write_text("open('/etc/passwd').read()\ndef control(observation): return {'10': 0, '335': 0}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="open"):
        IsolatedController(candidate, 1.0)
