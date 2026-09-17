import argparse
import json
from pathlib import Path

from rollout import load_controller, rollout
from scenario_loader import load_hidden, load_public
from scoring import aggregate, scenario_score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate")
    parser.add_argument("--json-out", default="metrics.json")
    parser.add_argument("--artifacts-out", default="artifacts.json")
    args = parser.parse_args()
    controller = load_controller(args.candidate)
    scenarios = load_public() + load_hidden()
    baseline = load_controller(str(Path(__file__).with_name("baseline.py")))
    references = {s["id"]: rollout(baseline, s) for s in scenarios}
    details = []
    scores = []
    for scenario in scenarios:
        metrics = rollout(controller, scenario)
        score = scenario_score(metrics, references[scenario["id"]]) if references[scenario["id"]].get("valid") else 0.0
        scores.append(score)
        details.append({"scenario": scenario["id"], "score": score, "metrics": metrics})
    score = aggregate(scores)
    valid = all(x["metrics"].get("valid", False) for x in details)
    payload = {
        "combined_score": score / 100.0 if valid else 0.0,
        "score": score,
        "valid": valid,
        "scenarios": details,
    }
    Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    Path(args.artifacts_out).write_text(json.dumps({"scenario_count": len(details)}, indent=2), encoding="utf-8")
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
