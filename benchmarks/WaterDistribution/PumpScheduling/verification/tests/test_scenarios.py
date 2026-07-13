import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from scenario_loader import load_hidden, load_public
from rollout import (
    DURATION_S,
    HYDRAULIC_STEP_S,
    MINIMUM_PRESSURE_M,
    SERVICE_NODES,
    _network,
)


def test_scenario_counts_and_lengths():
    cases = load_public() + load_hidden()
    assert len(cases) == 6
    assert len({case["id"] for case in cases}) == 6
    assert all(len(case["tariff"]) == len(case["demand_multipliers"]) == 24 for case in cases)


def test_public_service_node_contract_matches_evaluator():
    task_root = Path(__file__).parents[2]
    declaration = json.loads(
        (task_root / "references" / "service_nodes.json").read_text(encoding="utf-8")
    )
    assert tuple(declaration["service_nodes"]) == SERVICE_NODES
    assert declaration["minimum_pressure_m"] == MINIMUM_PRESSURE_M == 20.0
    for document in (task_root / "Task.md", task_root / "Task_zh-CN.md"):
        text = document.read_text(encoding="utf-8")
        assert all(f"`{node}`" in text for node in SERVICE_NODES)


def test_scenario_builds_one_continuous_day():
    wn = _network(load_public()[0])
    assert wn.options.time.duration == DURATION_S
    assert wn.options.time.hydraulic_timestep == HYDRAULIC_STEP_S
    assert wn.options.time.pattern_timestep == 3600
    assert not wn.control_name_list
