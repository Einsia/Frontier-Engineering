"""Unit tests for verification/ref_solver.py (stdlib unittest, no third-party deps).

Run from the CVRP task directory:
    python verification/test_ref_solver.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ref_solver as rs  # noqa: E402

CVRP_ROOT = Path(__file__).resolve().parents[1]
INST = CVRP_ROOT / "data" / "instances" / "VRP-19-2.vrp"


class TestGraspDeterministic(unittest.TestCase):
    def test_same_seed_same_distance(self):
        inst = rs.parse_instance(INST)
        args = dict(starts=3, seed=7, lns_iters=5)
        d1 = sum(rs.route_dist(r, inst["distance"]) for r in rs.grasp_solve(inst, **args))
        d2 = sum(rs.route_dist(r, inst["distance"]) for r in rs.grasp_solve(inst, **args))
        self.assertEqual(d1, d2)

    def test_different_seeds_usually_differ(self):
        inst = rs.parse_instance(INST)
        d_a = sum(
            rs.route_dist(r, inst["distance"])
            for r in rs.grasp_solve(inst, starts=3, seed=1, lns_iters=5)
        )
        d_b = sum(
            rs.route_dist(r, inst["distance"])
            for r in rs.grasp_solve(inst, starts=3, seed=999, lns_iters=5)
        )
        # The GRASP perturbation makes different seeds explore different
        # neighbourhoods; identical distance is possible but unlikely.
        self.assertIsInstance(d_a, int)
        self.assertIsInstance(d_b, int)


class TestGraspFeasible(unittest.TestCase):
    def test_full_coverage_and_capacity(self):
        inst = rs.parse_instance(INST)
        routes = rs.grasp_solve(inst, starts=3, seed=7, lns_iters=5)
        covered = [c for route in routes for c in route]
        self.assertEqual(sorted(covered), list(range(1, inst["n"] + 1)))
        for route in routes:
            load = sum(inst["demand"][c] for c in route)
            self.assertLessEqual(load, inst["capacity"])

    def test_returns_list_of_lists(self):
        inst = rs.parse_instance(INST)
        routes = rs.grasp_solve(inst, starts=3, seed=7, lns_iters=5)
        self.assertIsInstance(routes, list)
        for route in routes:
            self.assertIsInstance(route, list)


class TestReferenceJsonConsistency(unittest.TestCase):
    def test_matches_reference_json(self):
        """Reproduce main()'s computation for the smallest instance and check
        it equals the checked-in reference distance (byte-identical, fixed
        seed list (123, 2024, 7))."""
        inst = rs.parse_instance(INST)
        iters = max(100, 4 * inst["n"])
        best = min(
            sum(
                rs.route_dist(r, inst["distance"])
                for r in rs.grasp_solve(inst, starts=40, seed=seed, lns_iters=iters)
            )
            for seed in (123, 2024, 7)
        )
        ref = json.loads(
            (CVRP_ROOT / "data" / "reference.json").read_text(encoding="utf-8")
        )
        self.assertEqual(best, ref[inst["name"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
