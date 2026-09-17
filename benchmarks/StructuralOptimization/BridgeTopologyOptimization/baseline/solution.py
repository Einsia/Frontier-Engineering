from __future__ import annotations

try:
    from benchmarks.StructuralOptimization.BridgeTopologyOptimization.runtime.problem import oc_update
except ModuleNotFoundError:
    from runtime.problem import oc_update


def update_density(density, sensitivity, state):
    return oc_update(density, sensitivity, state)
