from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from verification.evaluator import _case_score, evaluate
except ModuleNotFoundError:
    from evaluator import _case_score, evaluate


class EvaluatorTests(unittest.TestCase):
    def _candidate(self, source: str) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="laminate_candidate_test_"))
        path = directory / "candidate.py"
        path.write_text(source, encoding="utf-8")
        self.addCleanup(lambda: shutil.rmtree(directory, ignore_errors=True))
        return path

    def test_anchor_candidate_is_valid_and_scores_fifty(self) -> None:
        candidate = self._candidate(
            "def design_laminates(cases):\n"
            "    x=[90,45,45,90,45,90,45,45,45,45,45,45]\n"
            "    return {c['case_id']: list(x) for c in cases}\n"
        )
        result = evaluate(candidate)
        self.assertEqual(result["valid"], 1.0)
        self.assertAlmostEqual(result["combined_score"], 50.0, places=8)
        self.assertTrue(all(abs(row["score"] - 50.0) < 1e-8 for row in result["rows"]))

    def test_load_aware_design_has_measurable_improvement_space(self) -> None:
        candidate = self._candidate(
            "def design_laminates(cases):\n"
            "    anchor=[90,45,45,90,45,90,45,45,45,45,45,45]\n"
            "    mixed=[0,45,90,30,60,45,0,30,60,90,45,15]\n"
            "    out={}\n"
            "    for c in cases:\n"
            "        if c['Ny_N_per_mm'] == 0 and c['aspect_ratio'] <= 1:\n"
            "            out[c['case_id']] = [0]*12\n"
            "        elif c['Ny_N_per_mm'] == 0:\n"
            "            out[c['case_id']] = list(mixed)\n"
            "        else:\n"
            "            out[c['case_id']] = list(anchor)\n"
            "    return out\n"
        )
        result = evaluate(candidate)
        self.assertEqual(result["valid"], 1.0)
        self.assertGreater(result["combined_score"], 60.0)

    def test_missing_case_is_invalid_with_actionable_feedback(self) -> None:
        candidate = self._candidate("def design_laminates(cases): return {}\n")
        result = evaluate(candidate)
        self.assertEqual(result["valid"], 0.0)
        self.assertEqual(result["combined_score"], 0.0)
        self.assertIn("missing design for case", result["rows"][0]["error"])

    def test_out_of_range_angle_is_invalid(self) -> None:
        candidate = self._candidate(
            "def design_laminates(cases):\n"
            "    return {c['case_id']: [91]*12 for c in cases}\n"
        )
        result = evaluate(candidate)
        self.assertEqual(result["valid"], 0.0)
        self.assertIn("outside [0, 90]", result["rows"][0]["error"])

    def test_candidate_stdout_does_not_break_protocol(self) -> None:
        candidate = self._candidate(
            "print('noise during import')\n"
            "def design_laminates(cases):\n"
            "    print('noise during call')\n"
            "    x=[90,45,45,90,45,90,45,45,45,45,45,45]\n"
            "    return {c['case_id']: x for c in cases}\n"
        )
        result = evaluate(candidate)
        self.assertEqual(result["valid"], 1.0)

    def test_candidate_cannot_monkeypatch_parent_score(self) -> None:
        candidate = self._candidate(
            "import sys\n"
            "setattr(sys.modules['__main__'], '_case_score', lambda *a: 100.0)\n"
            "def design_laminates(cases):\n"
            "    return {c['case_id']: [90]*12 for c in cases}\n"
        )
        result = evaluate(candidate)
        self.assertNotEqual(result["combined_score"], 100.0)

    def test_syntax_error_returns_invalid_result(self) -> None:
        candidate = self._candidate("def broken(:\n")
        result = evaluate(candidate)
        self.assertEqual(result["valid"], 0.0)
        self.assertEqual(result["combined_score"], 0.0)
        self.assertIn("candidate import failed", result["rows"][0]["error"])

    def test_score_is_monotone_and_anchor_is_fifty(self) -> None:
        self.assertLess(_case_score(9.0, 10.0), 50.0)
        self.assertAlmostEqual(_case_score(10.0, 10.0), 50.0)
        self.assertGreater(_case_score(11.0, 10.0), 50.0)


if __name__ == "__main__":
    unittest.main()
