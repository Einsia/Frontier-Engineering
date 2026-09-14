from __future__ import annotations

import argparse
import hmac
import json
import math
from pathlib import Path
from typing import Any


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Parse MallocLab mdriver output to metrics.json.")
    p.add_argument("--result-file", type=str, required=True)
    p.add_argument("--expected-token", type=str, required=True)
    p.add_argument("--stdout-file", type=str, required=True)
    p.add_argument("--stderr-file", type=str, required=True)
    p.add_argument("--mdriver-returncode", type=int, required=True)
    p.add_argument("--metrics-out", type=str, required=True)
    return p.parse_args()


def _finite(value: Any) -> float | None:
    """Accept only a real, finite number. Rejects bool, NaN and +-Inf."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def read_result(result_text: str, expected_token: str) -> tuple[dict[str, float] | None, str]:
    """Validate the record mdriver wrote and return its fields.

    The score is never taken from stdout. mm.c is linked into mdriver, so it can
    print whatever it likes there -- and the old parser scanned stdout for the
    last "Score = ... = N/100" line, which made a single extra printf a perfect
    score. A record only counts if it carries the token the grader handed
    mdriver on stdin.
    """
    if not result_text.strip():
        return None, "mdriver wrote no result record"
    try:
        record = json.loads(result_text)
    except Exception as exc:
        return None, f"result record is not valid JSON: {exc}"
    if not isinstance(record, dict):
        return None, "result record must be a JSON object"

    token = record.get("run_token")
    if not isinstance(token, str) or not hmac.compare_digest(token, expected_token):
        return None, "result record does not carry this run's token"

    score = _finite(record.get("score_100"))
    if score is None:
        return None, "result record has no finite score_100"
    if not 0.0 <= score <= 100.0:
        return None, f"score_100 out of range: {score}"

    passed = _finite(record.get("testcases_passed"))
    total = _finite(record.get("testcases_total"))
    errors = _finite(record.get("errors"))
    if passed is None or total is None or total <= 0 or not 0.0 <= passed <= total:
        return None, "result record has an implausible testcase count"
    if errors is None or errors < 0:
        return None, "result record has an implausible error count"
    # A failing trace is a normal outcome, not an invalid run: mdriver already
    # prices it in by scaling the score by numcorrect/num_tracefiles. The
    # shipped baseline fails 5 of 11 and scores ~28.

    metrics = {
        "score_100": score,
        "score_ratio": score / 100.0,
        "testcases_passed": passed,
        "testcases_total": total,
        "testcase_pass_rate": passed / total,
        "errors": errors,
    }
    for key in ("util_points", "thru_points"):
        value = _finite(record.get(key))
        if value is not None:
            metrics[key] = value
    return metrics, ""


def main() -> int:
    args = _parse_args()
    result_text = _read_text(Path(args.result_file).expanduser().resolve())

    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "mdriver_returncode": float(args.mdriver_returncode),
    }

    parsed, error_message = read_result(result_text, args.expected_token)
    if parsed is None:
        metrics["error_message"] = error_message
    elif int(args.mdriver_returncode) != 0:
        metrics["error_message"] = f"mdriver exited {args.mdriver_returncode}"
    else:
        metrics.update(parsed)
        metrics["valid"] = 1.0
        metrics["combined_score"] = parsed["score_100"]

    _write_json(Path(args.metrics_out).expanduser().resolve(), metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
