from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import unittest

from simulator import ActionValidationError, EdgeServiceSimulator, SCENARIOS, ScenarioTrace, make_scenario, run_policy


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preserve_action(simulator: EdgeServiceSimulator) -> dict:
    replicas = [
        {"service_id": service, "node_id": node, "count": count}
        for (service, node), count in sorted(simulator.active.items())
    ]
    return {"replicas": replicas, "routes": []}


class ScenarioTests(unittest.TestCase):
    def test_generation_is_deterministic(self) -> None:
        first = make_scenario("regional_burst", 4118, feedback=True)
        second = make_scenario("regional_burst", 4118, feedback=True)
        self.assertEqual(first, second)
        self.assertEqual(len(first.workloads), 24)

    def test_five_scenario_families_have_two_variants(self) -> None:
        self.assertEqual(len(SCENARIOS), 10)
        self.assertEqual(len({scenario.family for scenario in SCENARIOS}), 5)


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.simulator = EdgeServiceSimulator(SCENARIOS[0])
        self.simulator._activate_pending_and_apply_failures()

    def assert_code(self, action: dict, code: str) -> None:
        with self.assertRaises(ActionValidationError) as caught:
            self.simulator._validate_action(action)
        self.assertEqual(caught.exception.code, code)

    def test_bool_cannot_impersonate_integer(self) -> None:
        action = preserve_action(self.simulator)
        action["replicas"][0]["count"] = True
        self.assert_code(action, "type")

    def test_negative_and_noninteger_replica_counts_are_rejected(self) -> None:
        for value, code in [(-1, "range"), (1.5, "type")]:
            with self.subTest(value=value):
                action = preserve_action(self.simulator)
                action["replicas"][0]["count"] = value
                self.assert_code(action, code)

    def test_unknown_id_is_rejected(self) -> None:
        action = preserve_action(self.simulator)
        action["replicas"][0]["node_id"] = "missing-node"
        self.assert_code(action, "unknown_id")

    def test_exact_top_level_schema_is_enforced(self) -> None:
        action = preserve_action(self.simulator)
        action["reported_score"] = 100.0
        self.assert_code(action, "schema")

    def test_nan_route_is_rejected(self) -> None:
        action = preserve_action(self.simulator)
        action["routes"] = [{"service_id": "api", "source_region": "edge-a", "node_id": "a-1", "fraction": math.nan}]
        self.assert_code(action, "non_finite")

    def test_route_fraction_out_of_range_is_rejected(self) -> None:
        action = preserve_action(self.simulator)
        action["routes"] = [{"service_id": "api", "source_region": "edge-a", "node_id": "a-1", "fraction": 1.01}]
        self.assert_code(action, "range")

    def test_extreme_route_float_is_rejected(self) -> None:
        action = preserve_action(self.simulator)
        action["routes"] = [{"service_id": "api", "source_region": "edge-a", "node_id": "a-1", "fraction": 1e308}]
        self.assert_code(action, "range")

    def test_huge_replica_count_is_rejected_by_capacity(self) -> None:
        action = preserve_action(self.simulator)
        action["replicas"] = [{"service_id": "api", "node_id": "a-1", "count": 10**100}]
        self.assert_code(action, "capacity")

    def test_malformed_nested_route_is_rejected(self) -> None:
        action = preserve_action(self.simulator)
        action["routes"] = [{"service_id": "api", "source_region": "edge-a", "fraction": 1.0}]
        self.assert_code(action, "schema")

    def test_capacity_is_checked(self) -> None:
        action = preserve_action(self.simulator)
        action["replicas"] = [{"service_id": "api", "node_id": "a-1", "count": 6}]
        self.assert_code(action, "capacity")

    def test_duplicate_placement_is_rejected(self) -> None:
        action = preserve_action(self.simulator)
        action["replicas"].append(dict(action["replicas"][0]))
        self.assert_code(action, "duplicate")

    def test_route_sum_above_one_is_rejected(self) -> None:
        action = preserve_action(self.simulator)
        action["routes"] = [
            {"service_id": "api", "source_region": "edge-a", "node_id": "a-1", "fraction": 0.6},
            {"service_id": "api", "source_region": "edge-a", "node_id": "b-1", "fraction": 0.5},
        ]
        self.assert_code(action, "route_sum")

    def test_route_sum_tolerance_has_a_strict_boundary(self) -> None:
        within = preserve_action(self.simulator)
        within["routes"] = [
            {"service_id": "api", "source_region": "edge-a", "node_id": "a-1", "fraction": 0.5},
            {"service_id": "api", "source_region": "edge-a", "node_id": "b-1", "fraction": 0.500000005},
        ]
        self.simulator._validate_action(within)
        outside = preserve_action(self.simulator)
        outside["routes"] = [
            {"service_id": "api", "source_region": "edge-a", "node_id": "a-1", "fraction": 0.5},
            {"service_id": "api", "source_region": "edge-a", "node_id": "b-1", "fraction": 0.50000002},
        ]
        self.assert_code(outside, "route_sum")

    def test_duplicate_route_is_rejected(self) -> None:
        action = preserve_action(self.simulator)
        route = {"service_id": "api", "source_region": "edge-a", "node_id": "a-1", "fraction": 0.4}
        action["routes"] = [route, dict(route)]
        self.assert_code(action, "duplicate")

    def test_pending_replica_cannot_receive_traffic(self) -> None:
        action = preserve_action(self.simulator)
        action["replicas"].append({"service_id": "api", "node_id": "a-2", "count": 1})
        action["routes"] = [{"service_id": "api", "source_region": "edge-a", "node_id": "a-2", "fraction": 1.0}]
        self.assert_code(action, "inactive_route")

    def test_failed_node_cannot_receive_placement(self) -> None:
        scenario = next(item for item in SCENARIOS if item.family == "node_failure_burst")
        simulator = EdgeServiceSimulator(scenario)
        simulator.step_index = 8
        simulator._activate_pending_and_apply_failures()
        failed_node = next(iter(scenario.failed_nodes[8]))
        action = preserve_action(simulator)
        action["replicas"].append({"service_id": "api", "node_id": failed_node, "count": 1})
        with self.assertRaises(ActionValidationError) as caught:
            simulator._validate_action(action)
        self.assertEqual(caught.exception.code, "failed_node")

    def test_failed_node_cannot_receive_route(self) -> None:
        scenario = next(item for item in SCENARIOS if item.family == "node_failure_burst")
        simulator = EdgeServiceSimulator(scenario)
        simulator.step_index = 8
        simulator._activate_pending_and_apply_failures()
        failed_node = next(iter(scenario.failed_nodes[8]))
        action = preserve_action(simulator)
        action["routes"] = [{"service_id": "api", "source_region": "edge-a", "node_id": failed_node, "fraction": 0.5}]
        with self.assertRaises(ActionValidationError) as caught:
            simulator._validate_action(action)
        self.assertEqual(caught.exception.code, "failed_node")


class MetricTests(unittest.TestCase):
    def test_static_policy_produces_finite_metrics(self) -> None:
        weak = load_module("weak_policy", ROOT / "calibration" / "weak.py")
        metrics = run_policy(weak, SCENARIOS[0])
        self.assertGreater(float(metrics["request_availability"]), 0.95)
        for key, value in metrics.items():
            if key != "scenario_family":
                self.assertTrue(math.isfinite(float(value)), key)

    def test_tiny_routing_case_matches_capacity_and_bandwidth_oracle(self) -> None:
        zero = {region: {service: 0.0 for service in ("api", "search", "media")} for region in ("edge-a", "edge-b", "edge-c")}
        zero["edge-a"]["api"] = 150.0
        scenario = ScenarioTrace(
            name="tiny-oracle",
            family="tiny-oracle",
            seed=0,
            feedback=True,
            workloads=(zero,),
            failed_nodes=(frozenset(),),
            link_factors=({},),
            recovery_start=None,
        )
        best_served = 0.0
        for first in (0.0, 0.5, 1.0):
            for second in (0.0, 0.5, 1.0):
                if first + second > 1.0:
                    continue
                simulator = EdgeServiceSimulator(scenario)
                routes = [
                    {"service_id": "api", "source_region": "edge-a", "node_id": "a-1", "fraction": first},
                    {"service_id": "api", "source_region": "edge-a", "node_id": "b-1", "fraction": second},
                ]
                best_served = max(best_served, simulator._simulate_period(routes)["served"])
        local_served = min(75.0, 90.0)
        cross_region_link_rps = 360.0 / (0.025 * 5.0 * 60.0)
        remote_served = min(75.0, 90.0, cross_region_link_rps)
        exact_capacity_bound = local_served + remote_served
        self.assertAlmostEqual(best_served, exact_capacity_bound, places=9)


if __name__ == "__main__":
    unittest.main()
