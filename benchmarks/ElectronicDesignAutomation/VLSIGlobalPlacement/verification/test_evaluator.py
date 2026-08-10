# -*- coding: utf-8 -*-
"""Unit tests for the VLSI Global Placement evaluator.

Run with:  python verification/test_evaluator.py
or:        python -m unittest verification.test_evaluator
Uses only the Python standard library (unittest).
"""
import gzip
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
BENCHMARK_DIR = HERE.parent
REAL_INIT = BENCHMARK_DIR / "scripts" / "init.py"
sys.path.insert(0, str(HERE))

import evaluator  # noqa: E402


def _cells():
    return {
        "f1": {"width": 10.0, "height": 10.0},
        "f2": {"width": 10.0, "height": 10.0},
        "a": {"width": 10.0, "height": 10.0},
        "b": {"width": 20.0, "height": 10.0},
        "c": {"width": 10.0, "height": 10.0},
    }


def _die():
    return {"width": 100.0, "height": 100.0, "row_height": 10.0,
            "min_x": 0.0, "min_y": 0.0}


def _tiny_benchmark_data():
    return {
        "benchmark_name": "tiny",
        "num_nodes": 5,
        "num_terminals": 2,
        "num_nets": 3,
        "num_pins": 8,
        "die": _die(),
        "cells": _cells(),
        "fixed_cells": ["f1", "f2"],
        "movable_cells": ["a", "b", "c"],
        "initial_placement": {
            "f1": {"x": 0.0, "y": 0.0, "orientation": "N"},
            "f2": {"x": 0.0, "y": 80.0, "orientation": "N"},
            "a": {"x": 0.0, "y": 10.0, "orientation": "N"},
            "b": {"x": 0.0, "y": 30.0, "orientation": "N"},
            "c": {"x": 0.0, "y": 50.0, "orientation": "N"},
        },
        "netlist": [
            [0, 2],      # f1 - a
            [1, 3],      # f2 - b
            [2, 3, 4],   # a - b - c
        ],
    }


def _netlist_verbose(data):
    names = list(data["cells"].keys())
    out = []
    for net in data["netlist"]:
        out.append([{"cell": names[i], "x_offset": 0.0, "y_offset": 0.0} for i in net])
    return out


class TestComputeHpwl(unittest.TestCase):
    def test_single_net_known_value(self):
        cells = _cells()
        net = [
            {"cell": "a", "x_offset": 0.0, "y_offset": 0.0},
            {"cell": "b", "x_offset": 0.0, "y_offset": 0.0},
        ]
        placement = {"a": [0.0, 0.0], "b": [30.0, 40.0]}
        # a center: (5,5); b center: (40,45) -> HPWL = (40-5)+(45-5) = 75
        self.assertAlmostEqual(evaluator.compute_hpwl(placement, [net], cells), 75.0)

    def test_empty_net_contributes_zero(self):
        cells = _cells()
        placement = {"a": [0.0, 0.0]}
        net = []
        self.assertEqual(evaluator.compute_hpwl(placement, [net], cells), 0.0)

    def test_missing_cell_skipped(self):
        cells = _cells()
        net = [
            {"cell": "a", "x_offset": 0.0, "y_offset": 0.0},
            {"cell": "b", "x_offset": 0.0, "y_offset": 0.0},
        ]
        placement = {"a": [0.0, 0.0]}  # b missing -> only a's span = 0
        self.assertEqual(evaluator.compute_hpwl(placement, [net], cells), 0.0)

    def test_pin_offsets_included(self):
        cells = _cells()
        net = [
            {"cell": "a", "x_offset": 5.0, "y_offset": 0.0},
            {"cell": "b", "x_offset": 0.0, "y_offset": 0.0},
        ]
        placement = {"a": [0.0, 0.0], "b": [30.0, 0.0]}
        # a pin center: 5+5=10; b pin center: 30+10=40 -> HPWL = 30
        self.assertAlmostEqual(evaluator.compute_hpwl(placement, [net], cells), 30.0)


class TestCheckLegality(unittest.TestCase):
    def _placement(self, **overrides):
        p = {
            "f1": [0.0, 0.0],
            "f2": [0.0, 80.0],
            "a": [0.0, 10.0],
            "b": [20.0, 30.0],
            "c": [0.0, 50.0],
        }
        p.update(overrides)
        return p

    def test_valid_placement(self):
        res = evaluator.check_legality(
            self._placement(), _cells(), _die(),
            ["f1", "f2"], ["a", "b", "c"], _tiny_benchmark_data()["initial_placement"],
        )
        self.assertTrue(res.valid)
        self.assertEqual(len(res.moved_fixed), 0)
        self.assertEqual(len(res.out_of_bounds), 0)
        self.assertEqual(len(res.overlapping_pairs), 0)
        self.assertEqual(len(res.missing), 0)

    def test_fixed_cell_moved(self):
        res = evaluator.check_legality(
            self._placement(f1=[50.0, 50.0]), _cells(), _die(),
            ["f1", "f2"], ["a", "b", "c"], _tiny_benchmark_data()["initial_placement"],
        )
        self.assertFalse(res.valid)
        self.assertIn("f1", res.moved_fixed)

    def test_out_of_bounds(self):
        res = evaluator.check_legality(
            self._placement(c=[90.0, 95.0]), _cells(), _die(),
            ["f1", "f2"], ["a", "b", "c"], _tiny_benchmark_data()["initial_placement"],
        )
        self.assertFalse(res.valid)
        self.assertIn("c", res.out_of_bounds)

    def test_overlap_detected(self):
        res = evaluator.check_legality(
            self._placement(a=[0.0, 0.0]), _cells(), _die(),
            ["f1", "f2"], ["a", "b", "c"], _tiny_benchmark_data()["initial_placement"],
        )
        self.assertFalse(res.valid)
        self.assertTrue(len(res.overlapping_pairs) >= 1)

    def test_missing_cell(self):
        placement = {
            "f1": [0.0, 0.0], "f2": [0.0, 80.0],
            "a": [0.0, 10.0], "b": [20.0, 30.0],
        }  # c missing
        res = evaluator.check_legality(
            placement, _cells(), _die(),
            ["f1", "f2"], ["a", "b", "c"], _tiny_benchmark_data()["initial_placement"],
        )
        self.assertFalse(res.valid)
        self.assertIn("c", res.missing)


class TestEvolveBoundary(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _modified_init(self, mode):
        text = REAL_INIT.read_text(encoding="utf-8")
        if mode == "violation":
            # Change code AFTER the EVOLVE-BLOCK (inside main()).
            text = text.replace('    print("=" * 60)\n', '    print("!" * 60)\n', 1)
        elif mode == "legit":
            # Replace only the interior of the EVOLVE-BLOCK with a tiny
            # deterministic row-based placer.
            start = text.find("# EVOLVE-BLOCK-START")
            end = text.find("# EVOLVE-BLOCK-END")
            interior = '''def place_components(
    die, cells, fixed_cells, movable_cells, netlist, initial_placement,
):
    placement = {}
    for c in fixed_cells:
        placement[c] = [initial_placement[c]["x"], initial_placement[c]["y"]]
    x = 0.0
    y = 20.0  # start below fixed cells in row 0
    row_h = die["row_height"]
    die_w = die["width"]
    for c in movable_cells:
        w = cells[c]["width"]
        h = cells[c]["height"]
        if x + w > die_w:
            x = 0.0
            y += row_h
        placement[c] = [x, y]
        x += w
    return placement
'''
            text = text[:start] + "# EVOLVE-BLOCK-START\n" + interior + "# EVOLVE-BLOCK-END" + text[end + len("# EVOLVE-BLOCK-END"):]
        return text

    def test_boundary_violation_rejected(self):
        cand = self.tmp / "init_violation.py"
        cand.write_text(self._modified_init("violation"), encoding="utf-8")
        err = evaluator.check_evolve_boundary(cand, REAL_INIT)
        self.assertIsNotNone(err)
        self.assertIn("EVOLVE-BLOCK", err)

    def test_legit_change_accepted(self):
        cand = self.tmp / "init_legit.py"
        cand.write_text(self._modified_init("legit"), encoding="utf-8")
        err = evaluator.check_evolve_boundary(cand, REAL_INIT)
        self.assertIsNone(err)

    def test_missing_markers_rejected(self):
        cand = self.tmp / "init_no_markers.py"
        text = REAL_INIT.read_text(encoding="utf-8")
        text = text.replace("# EVOLVE-BLOCK-START", "")
        cand.write_text(text, encoding="utf-8")
        err = evaluator.check_evolve_boundary(cand, REAL_INIT)
        self.assertIsNotNone(err)


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self._tmp.name)
        self.bench_dir = self.repo / "benchmarks" / "ElectronicDesignAutomation" / "VLSIGlobalPlacement"
        self.ref_dir = self.bench_dir / "references"
        self.scripts_dir = self.bench_dir / "scripts"
        self.ref_dir.mkdir(parents=True)
        self.scripts_dir.mkdir(parents=True)
        # tiny benchmark data as gzip
        data = _tiny_benchmark_data()
        with gzip.open(self.ref_dir / "tiny.json.gz", "wt", encoding="utf-8") as f:
            json.dump(data, f)
        (self.ref_dir / "tiny_difficulty.json").write_text(
            json.dumps({"difficulty": "Easy", "benchmark": "tiny"}), encoding="utf-8"
        )
        # reference init.py in the fake repo
        self.ref_init = self.scripts_dir / "init.py"
        shutil.copy2(REAL_INIT, self.ref_init)

    def tearDown(self):
        self._tmp.cleanup()

    def test_e2e_valid_baseline(self):
        result = evaluator.evaluate(
            str(self.ref_init), repo_root=self.repo, benchmark_name="tiny"
        )
        metrics = result.metrics if hasattr(result, "metrics") else result
        self.assertEqual(metrics["valid"], 1.0)
        self.assertGreater(metrics["hpwl"], 0.0)
        self.assertEqual(metrics["n_overlaps"], 0.0)
        self.assertEqual(metrics["n_out_of_bounds"], 0.0)
        self.assertEqual(metrics["n_fixed_moved"], 0.0)
        self.assertNotEqual(metrics["combined_score"], evaluator.INVALID_COMBINED_SCORE)

    def test_e2e_boundary_violation_fails(self):
        cand = self.scripts_dir / "init_violation.py"
        text = REAL_INIT.read_text(encoding="utf-8")
        text = text.replace('    print("=" * 60)\n', '    print("!" * 60)\n', 1)
        cand.write_text(text, encoding="utf-8")
        result = evaluator.evaluate(
            str(cand), repo_root=self.repo, benchmark_name="tiny"
        )
        metrics = result.metrics if hasattr(result, "metrics") else result
        self.assertEqual(metrics["valid"], 0.0)
        self.assertEqual(metrics["combined_score"], evaluator.INVALID_COMBINED_SCORE)

    def test_e2e_legit_modification_runs(self):
        cand = self.scripts_dir / "init_legit.py"
        text = REAL_INIT.read_text(encoding="utf-8")
        start = text.find("# EVOLVE-BLOCK-START")
        end = text.find("# EVOLVE-BLOCK-END")
        interior = '''def place_components(
    die, cells, fixed_cells, movable_cells, netlist, initial_placement,
):
    placement = {}
    for c in fixed_cells:
        placement[c] = [initial_placement[c]["x"], initial_placement[c]["y"]]
    x = 0.0
    y = 20.0  # start below fixed cells in row 0
    row_h = die["row_height"]
    die_w = die["width"]
    for c in movable_cells:
        w = cells[c]["width"]
        h = cells[c]["height"]
        if x + w > die_w:
            x = 0.0
            y += row_h
        placement[c] = [x, y]
        x += w
    return placement
'''
        text = text[:start] + "# EVOLVE-BLOCK-START\n" + interior + "# EVOLVE-BLOCK-END" + text[end + len("# EVOLVE-BLOCK-END"):]
        cand.write_text(text, encoding="utf-8")
        result = evaluator.evaluate(
            str(cand), repo_root=self.repo, benchmark_name="tiny"
        )
        metrics = result.metrics if hasattr(result, "metrics") else result
        artifacts = result.artifacts if hasattr(result, "artifacts") else {}
        self.assertNotIn("evolve_boundary_error", artifacts)
        self.assertEqual(metrics["valid"], 1.0)
        self.assertGreater(metrics["hpwl"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
