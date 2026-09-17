from __future__ import annotations

try:
    from benchmarks.OperationsResearch.FuelMinimizingShipWeatherRouting.runtime.problem import baseline_path
except ModuleNotFoundError:
    from runtime.problem import baseline_path


def solve(instance):
    return baseline_path()
