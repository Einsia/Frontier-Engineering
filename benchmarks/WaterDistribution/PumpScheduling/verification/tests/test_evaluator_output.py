import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import evaluator


def test_evaluator_uses_frozen_reference_and_explicit_metrics(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate.py"
    candidate.write_text("def control(observation): return {'10': 0, '335': 0}\n", encoding="utf-8")
    metrics_path = tmp_path / "metrics.json"
    artifacts_path = tmp_path / "artifacts.json"
    loaded = []

    def fake_load(path):
        resolved = Path(path).resolve()
        loaded.append(resolved)
        return resolved

    fake_metrics = {
        "valid": True,
        "energy_cost": 1.0,
        "peak_power_kw": 1.0,
        "switching": 1.0,
        "terminal_deficit_m": 1.0,
    }
    monkeypatch.setattr(evaluator, "load_controller", fake_load)
    monkeypatch.setattr(evaluator, "load_public", lambda: [{"id": "case"}])
    monkeypatch.setattr(evaluator, "load_hidden", lambda: [])
    monkeypatch.setattr(evaluator, "rollout", lambda _controller, _scenario: dict(fake_metrics))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluator.py",
            str(candidate),
            "--json-out",
            str(metrics_path),
            "--artifacts-out",
            str(artifacts_path),
        ],
    )

    evaluator.main()
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))

    assert loaded[0] == candidate.resolve()
    assert loaded[1].name == "baseline.py"
    assert loaded[0] != loaded[1]
    assert isinstance(payload["valid"], bool)
    assert isinstance(payload["combined_score"], float)
    assert payload["combined_score"] == 1.0
