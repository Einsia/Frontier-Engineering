import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from scoring import aggregate, scenario_score


def test_invalid_scores_zero():
    assert scenario_score({"valid": False}, {}) == 0.0
    assert aggregate([100.0, 0.0]) == 0.0


def test_reference_scores_100():
    metrics = {"valid": True, "energy_cost": 2, "peak_power_kw": 3, "switching": 4, "terminal_deficit_m": 5}
    assert scenario_score(metrics, metrics) == 100.0
