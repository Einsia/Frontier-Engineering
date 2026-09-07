"""Hardening tests for benchmarks/EngDesign/frontier_eval/evaluate_submission.py.

The EngDesign suite bundles seven independent sub-tasks behind one leaderboard
row. Its orchestrator loads the candidate file, spawns one child per sub-task,
collects their results and writes metrics.json. These tests pin the three
properties that keep that pipeline trustworthy:

A. the orchestrator process never executes candidate-supplied code;
B. the candidate file is read as data (literals), not run;
C. per-task results travel through an authenticated file, not child stdout.

Every case builds a throwaway benchmark directory with seven stub task folders,
so the suite is fast and needs none of EngDesign's scientific dependencies.
The real benchmark data is never touched.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGDESIGN_DIR = REPO_ROOT / "benchmarks" / "EngDesign"
EVAL_SCRIPT = ENGDESIGN_DIR / "frontier_eval" / "evaluate_submission.py"
RUN_EVAL_SH = ENGDESIGN_DIR / "frontier_eval" / "run_eval.sh"

sys.path.insert(0, str(ENGDESIGN_DIR / "frontier_eval"))

import evaluate_submission as es  # noqa: E402

TASK_IDS = es.TASK_IDS

# A stub task pair that mirrors the real contract: `Response_structure` accepts
# `reasoning` + `config`, and `evaluate_llm_response` returns the 4-tuple.
STUB_OUTPUT_STRUCTURE = textwrap.dedent(
    """
    class Response_structure:
        def __init__(self, reasoning="", config=None):
            self.reasoning = reasoning
            self.config = config or {}
    """
).strip()

STUB_EVALUATE = textwrap.dedent(
    """
    def evaluate_llm_response(llm_response):
        score = float(llm_response.config.get("score", 0.0))
        return score >= 100.0, {"echo": llm_response.config}, score, 100.0
    """
).strip()


def _make_benchmark(root: Path, evaluate_src: dict[str, str] | None = None) -> Path:
    """Create a benchmark dir with the seven stub sub-tasks."""
    bench = root / "bench"
    for task_id in TASK_IDS:
        task_dir = bench / task_id
        task_dir.mkdir(parents=True)
        (task_dir / "output_structure.py").write_text(STUB_OUTPUT_STRUCTURE, encoding="utf-8")
        src = (evaluate_src or {}).get(task_id, STUB_EVALUATE)
        (task_dir / "evaluate.py").write_text(src, encoding="utf-8")
    return bench


def _submission_literal(score: float = 0.0, prelude: str = "") -> str:
    body = ",\n".join(
        f'    "{t}": {{"reasoning": "r", "config": {{"score": {score}}}}}' for t in TASK_IDS
    )
    return f"{prelude}\nSUBMISSION = {{\n{body},\n}}\n"


def _run_eval(bench: Path, candidate: Path, tmp_path: Path, timeout_s: float = 60.0):
    metrics = tmp_path / "metrics.json"
    artifacts = tmp_path / "artifacts.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(EVAL_SCRIPT),
            "--candidate",
            str(candidate),
            "--benchmark-dir",
            str(bench),
            "--metrics-out",
            str(metrics),
            "--artifacts-out",
            str(artifacts),
            "--task-timeout-s",
            str(timeout_s),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    metrics_obj = json.loads(metrics.read_text()) if metrics.is_file() else {}
    artifacts_obj = json.loads(artifacts.read_text()) if artifacts.is_file() else {}
    return proc, metrics_obj, artifacts_obj


class TestHonestSubmissionStillScores:
    def test_full_run_scores_and_is_valid(self, tmp_path: Path) -> None:
        bench = _make_benchmark(tmp_path)
        candidate = tmp_path / "engdesign_submission.py"
        candidate.write_text(_submission_literal(score=42.0), encoding="utf-8")

        _, metrics, artifacts = _run_eval(bench, candidate, tmp_path)

        assert metrics["valid"] == 1.0
        assert metrics["hard_failures"] == 0.0
        assert metrics["combined_score"] == pytest.approx(42.0)
        assert metrics["task_valid_rate"] == 1.0
        for task_id in TASK_IDS:
            assert metrics[f"{task_id.lower()}_score"] == pytest.approx(42.0)
            assert artifacts["task_results"][task_id]["task_valid"] == 1.0

    def test_module_level_string_constants_are_resolved(self, tmp_path: Path) -> None:
        """The `CODE = "..."` then `{"vioblk_read": CODE}` idiom must keep working."""
        bench = _make_benchmark(tmp_path)
        candidate = tmp_path / "engdesign_submission.py"
        prelude = 'SHARED = 77.0\nCODE = "def denoise_image(x):\\n    return x"'
        body = ",\n".join(
            f'    "{t}": {{"reasoning": "r", "config": {{"score": SHARED, "code": CODE}}}}'
            for t in TASK_IDS
        )
        candidate.write_text(f"{prelude}\nSUBMISSION = {{\n{body},\n}}\n", encoding="utf-8")

        _, metrics, _ = _run_eval(bench, candidate, tmp_path)

        assert metrics["valid"] == 1.0
        assert metrics["combined_score"] == pytest.approx(77.0)

    def test_json_candidate_is_accepted(self, tmp_path: Path) -> None:
        """`.json` candidates work, so switching candidate_destination stays cheap."""
        bench = _make_benchmark(tmp_path)
        candidate = tmp_path / "engdesign_submission.json"
        candidate.write_text(
            json.dumps({t: {"reasoning": "r", "config": {"score": 5.0}} for t in TASK_IDS}),
            encoding="utf-8",
        )

        _, metrics, _ = _run_eval(bench, candidate, tmp_path)

        assert metrics["valid"] == 1.0
        assert metrics["combined_score"] == pytest.approx(5.0)


class TestCandidateCodeIsNeverExecuted:
    """Problem A + B: neither the orchestrator nor the children run the file."""

    def test_module_level_side_effect_does_not_happen(self, tmp_path: Path) -> None:
        bench = _make_benchmark(tmp_path)
        marker = tmp_path / "PWNED.txt"
        candidate = tmp_path / "engdesign_submission.py"
        prelude = textwrap.dedent(
            f"""
            from pathlib import Path
            Path({str(marker)!r}).write_text("candidate code executed")
            """
        ).strip()
        candidate.write_text(_submission_literal(score=3.0, prelude=prelude), encoding="utf-8")

        _, metrics, _ = _run_eval(bench, candidate, tmp_path)

        # The import + write are dead text: no side effect anywhere in the run
        # (orchestrator process or any of the seven children).
        assert not marker.exists()
        # ...and the literal payload is still read correctly.
        assert metrics["combined_score"] == pytest.approx(3.0)
        assert metrics["valid"] == 1.0

    def test_orchestrator_survives_candidate_that_would_hijack_it(self, tmp_path: Path) -> None:
        """The pre-check at load time must not hand the orchestrator to the candidate."""
        bench = _make_benchmark(tmp_path)
        candidate = tmp_path / "engdesign_submission.py"
        prelude = textwrap.dedent(
            """
            import json, os, subprocess, sys

            # Under runpy this replaced the orchestrator's own machinery so the
            # seven children never had to run.
            subprocess.run = lambda *a, **k: None
            sys.modules["__main__"].TASK_IDS = ()
            print(json.dumps({"combined_score": 100.0, "valid": 1.0}))
            os._exit(0)
            """
        ).strip()
        candidate.write_text(_submission_literal(score=1.0, prelude=prelude), encoding="utf-8")

        proc, metrics, artifacts = _run_eval(bench, candidate, tmp_path)

        assert proc.returncode == 0
        assert metrics["combined_score"] == pytest.approx(1.0)
        assert metrics["total_tasks"] == float(len(TASK_IDS))
        # All seven children really ran.
        assert sorted(artifacts["task_results"]) == sorted(TASK_IDS)

    def test_non_literal_submission_is_invalid_with_a_clear_error(self, tmp_path: Path) -> None:
        bench = _make_benchmark(tmp_path)
        candidate = tmp_path / "engdesign_submission.py"
        candidate.write_text(
            "def build():\n    return {}\n\nSUBMISSION = build()\n", encoding="utf-8"
        )

        _, metrics, artifacts = _run_eval(bench, candidate, tmp_path)

        assert metrics["valid"] == 0.0
        assert metrics["combined_score"] == 0.0
        assert "Unsupported expression `Call`" in artifacts["error_message"]

    def test_missing_task_key_is_invalid(self, tmp_path: Path) -> None:
        bench = _make_benchmark(tmp_path)
        candidate = tmp_path / "engdesign_submission.py"
        candidate.write_text('SUBMISSION = {"AM_02": {"config": {}}}\n', encoding="utf-8")

        _, metrics, artifacts = _run_eval(bench, candidate, tmp_path)

        assert metrics["valid"] == 0.0
        assert "missing required task keys" in artifacts["error_message"]

    @pytest.mark.parametrize(
        "source",
        [
            'SUBMISSION = {"AM_02": __import__("os").name}',
            'SUBMISSION = {"AM_02": [i for i in range(3)]}',
            'X = 1\nSUBMISSION = {"AM_02": f"{X}"}',
            'SUBMISSION = {"AM_02": open("/etc/passwd").read()}',
        ],
    )
    def test_execution_shaped_expressions_are_rejected(self, tmp_path: Path, source: str) -> None:
        candidate = tmp_path / "c.py"
        candidate.write_text(source + "\n", encoding="utf-8")
        with pytest.raises(es.SubmissionFormatError):
            es._load_submission(candidate)

    def test_loader_uses_no_execution_primitive(self) -> None:
        """Guard against a future `runpy` -> `exec_module` sideways move."""
        import re

        src = EVAL_SCRIPT.read_text(encoding="utf-8")
        loader = src[src.index("def _load_submission("):]
        loader = loader[: loader.index("\ndef _normalize_payload(")]
        for primitive in ("runpy", "exec", "eval", "compile", "exec_module", "__import__"):
            assert not re.search(rf"(?<![\w.]){re.escape(primitive)}\s*\(", loader), (
                f"{primitive}() reintroduced into _load_submission"
            )


class TestResultChannelCannotBeForged:
    """Problem C: results come from an authenticated file, not from stdout."""

    def test_stdout_forgery_is_ignored(self, tmp_path: Path) -> None:
        forger = textwrap.dedent(
            """
            import json, sys

            def evaluate_llm_response(llm_response):
                # Printed straight to the child's real stdout, which the old
                # orchestrator scanned for "the last JSON object".
                print(json.dumps({
                    "task_id": "AM_02", "passed": True, "score": 100.0,
                    "confidence": 100.0, "task_valid": 1.0, "details": {},
                }), file=sys.__stdout__, flush=True)
                return False, {}, 0.0, 0.0
            """
        ).strip()
        bench = _make_benchmark(tmp_path, evaluate_src={t: forger for t in TASK_IDS})
        candidate = tmp_path / "engdesign_submission.py"
        candidate.write_text(_submission_literal(score=0.0), encoding="utf-8")

        _, metrics, _ = _run_eval(bench, candidate, tmp_path)

        assert metrics["combined_score"] == 0.0
        assert metrics["pass_rate"] == 0.0
        for task_id in TASK_IDS:
            assert metrics[f"{task_id.lower()}_score"] == 0.0

    def test_forged_result_file_plus_early_exit_is_rejected(self, tmp_path: Path) -> None:
        """Writing --result-out directly and exiting 0 must not be believed."""
        forger = textwrap.dedent(
            """
            import json, os, sys

            def evaluate_llm_response(llm_response):
                out = sys.argv[sys.argv.index("--result-out") + 1]
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump({"token": "guess", "result": {
                        "passed": True, "score": 100.0, "confidence": 100.0,
                        "task_valid": 1.0, "details": {},
                    }}, fh)
                os._exit(0)
            """
        ).strip()
        bench = _make_benchmark(tmp_path, evaluate_src={t: forger for t in TASK_IDS})
        candidate = tmp_path / "engdesign_submission.py"
        candidate.write_text(_submission_literal(), encoding="utf-8")

        _, metrics, artifacts = _run_eval(bench, candidate, tmp_path)

        assert metrics["combined_score"] == 0.0
        assert metrics["valid"] == 0.0
        assert metrics["hard_failures"] == float(len(TASK_IDS))
        assert "token mismatch" in artifacts["task_results"]["AM_02"]["error"]

    def test_launch_token_is_absent_from_argv_and_environ(self, tmp_path: Path) -> None:
        """The token must not be recoverable by code running inside the child."""
        snooper = textwrap.dedent(
            """
            import os, sys

            def evaluate_llm_response(llm_response):
                seen = " ".join(sys.argv)
                try:
                    with open("/proc/self/environ", "rb") as fh:
                        seen += fh.read().decode("utf-8", "replace")
                except OSError:
                    pass
                seen += "".join(f"{k}={v}" for k, v in os.environ.items())
                try:
                    seen += sys.stdin.read()
                except Exception:
                    pass
                return False, {"seen": seen}, 0.0, 0.0
            """
        ).strip()
        bench = _make_benchmark(tmp_path, evaluate_src={t: snooper for t in TASK_IDS})
        candidate = tmp_path / "engdesign_submission.py"
        candidate.write_text(_submission_literal(), encoding="utf-8")

        _, metrics, artifacts = _run_eval(bench, candidate, tmp_path)

        assert metrics["valid"] == 1.0  # honest children still report normally
        seen = artifacts["task_results"]["AM_02"]["details"]["seen"]
        assert "--result-out" in seen  # the snooper really did read argv
        # The token is 64 hex chars handed over stdin, which the child consumed
        # and closed before importing this module. Nothing the child can still
        # read (argv, environ, /proc/self/environ, stdin) contains it.
        assert not re.search(r"\b[0-9a-f]{64}\b", seen)

    def test_absurd_score_is_clamped(self, tmp_path: Path) -> None:
        """A task-local compromise cannot inflate combined_score past its share."""
        cheater = textwrap.dedent(
            """
            def evaluate_llm_response(llm_response):
                return True, {}, 1e12, 1e12
            """
        ).strip()
        bench = _make_benchmark(tmp_path, evaluate_src={"CY_03": cheater})
        candidate = tmp_path / "engdesign_submission.py"
        candidate.write_text(_submission_literal(score=0.0), encoding="utf-8")

        _, metrics, _ = _run_eval(bench, candidate, tmp_path)

        assert metrics["cy_03_score"] == 100.0
        assert metrics["combined_score"] == pytest.approx(100.0 / len(TASK_IDS))

    def test_child_crash_fails_closed(self, tmp_path: Path) -> None:
        crasher = 'def evaluate_llm_response(llm_response):\n    import os; os._exit(0)\n'
        bench = _make_benchmark(tmp_path, evaluate_src={"WJ_01": crasher})
        candidate = tmp_path / "engdesign_submission.py"
        candidate.write_text(_submission_literal(score=50.0), encoding="utf-8")

        _, metrics, artifacts = _run_eval(bench, candidate, tmp_path)

        assert metrics["valid"] == 0.0
        assert metrics["combined_score"] == 0.0
        assert metrics["hard_failures"] == 1.0
        assert "no result file" in artifacts["task_results"]["WJ_01"]["error"]


class TestRunEvalReturnCode:
    """run_eval.sh must stop laundering harness failures into rc=0."""

    def test_nonzero_evaluator_rc_is_propagated(self, tmp_path: Path) -> None:
        bench = tmp_path / "bench"
        (bench / "frontier_eval").mkdir(parents=True)
        (bench / "frontier_eval" / "evaluate_submission.py").write_text(
            "import sys\nsys.exit(3)\n", encoding="utf-8"
        )
        candidate = bench / "cand.py"
        candidate.write_text("SUBMISSION = {}\n", encoding="utf-8")

        proc = subprocess.run(
            ["bash", str(RUN_EVAL_SH), sys.executable, str(bench), str(candidate)],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "ENGDESIGN_EVAL_MODE": "local"},
            timeout=120,
        )

        assert proc.returncode == 3
        metrics = json.loads((bench / "metrics.json").read_text())
        assert metrics["valid"] == 0.0
        assert metrics["combined_score"] == 0.0
        assert metrics["eval_returncode"] == 3.0

    def test_successful_run_keeps_rc_zero(self, tmp_path: Path) -> None:
        bench = tmp_path / "bench"
        (bench / "frontier_eval").mkdir(parents=True)
        (bench / "frontier_eval" / "evaluate_submission.py").write_text(
            textwrap.dedent(
                """
                import json, sys
                out = sys.argv[sys.argv.index("--metrics-out") + 1]
                with open(out, "w") as fh:
                    json.dump({"combined_score": 1.5, "valid": 1.0}, fh)
                """
            ).strip(),
            encoding="utf-8",
        )
        candidate = bench / "cand.py"
        candidate.write_text("SUBMISSION = {}\n", encoding="utf-8")

        proc = subprocess.run(
            ["bash", str(RUN_EVAL_SH), sys.executable, str(bench), str(candidate)],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "ENGDESIGN_EVAL_MODE": "local"},
            timeout=120,
        )

        assert proc.returncode == 0
        metrics = json.loads((bench / "metrics.json").read_text())
        assert metrics["valid"] == 1.0
        assert metrics["combined_score"] == 1.5


class TestShippedBaselineStaysReadable:
    def test_repo_baseline_parses_as_literal_data(self) -> None:
        baseline = ENGDESIGN_DIR / "submission" / "engdesign_submission.py"
        payload = es._load_submission(baseline)
        assert sorted(payload) == sorted(TASK_IDS)
        assert len(payload["AM_02"]["config"]["robot_trajectory1"]) == 20
        assert len(payload["AM_03"]["config"]["robot_trajectory"]) == 30
        assert payload["CY_03"]["config"]["vioblk_read"].startswith("def vioblk_read(")
        assert payload["WJ_01"]["config"]["function_code"].startswith("def denoise_image(")
