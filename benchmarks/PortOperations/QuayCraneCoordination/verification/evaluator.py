from pathlib import Path
import json, os, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "environment/data"
CANDIDATE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "scripts/init.py"
with tempfile.TemporaryDirectory(prefix="frontier-candidate-") as tmp:
    out = Path(tmp)
    env = os.environ.copy()
    env["FRONTIER_DATA_DIR"] = str(DATA)
    env["FRONTIER_DATA_FILE"] = str(DATA / ("operations_input.xlsx" if "PortOperations" in str(ROOT) else "planning_input.xlsx"))
    env["FRONTIER_OUTPUT_FILE"] = str(out / "solution.json")
    subprocess.run([sys.executable, str(CANDIDATE), str(out)], cwd=str(ROOT), env=env, check=True, timeout=1800)
    sys.path.insert(0, str(ROOT / "verification"))
    from evaluator_engine import evaluate
    plan = out / "solution.json" if "PortOperations" in str(ROOT) else out
    result = evaluate(str(plan), str(DATA))
    if not isinstance(result, dict):
        result = {"raw_score": float(result)}
    score = result.get("raw_score", result.get("score", result.get("combined_score", 0)))
    valid = bool(result.get("valid", result.get("validity_score", 0)))
    result["valid"] = valid
    result["combined_score"] = float(score) if isinstance(score, (int, float)) else 0.0
    Path(ROOT / "metrics.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if valid else 1)
