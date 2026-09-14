"""Released medal scoring handles invalid results and incomplete podiums."""

import csv
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LEADERBOARD = ROOT / "leaderboard"
spec = importlib.util.spec_from_file_location(
    "score_submission", LEADERBOARD / "score_submission.py"
)
scoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoring)


def test_absent_podium_tiers_do_not_award_credit(tmp_path):
    path = tmp_path / "podium.csv"
    path.write_text(
        "Task,Gold,Silver,Bronze\n"
        "one_valid,10, ,\n"
        "two_valid,10,8,\n"
        "none_valid,,,\n"
    )
    podium = scoring.load_podium(path)
    assert podium["one_valid"] == (10.0, None, None)
    assert scoring.tier(9, *podium["one_valid"]) == (0.0, None)
    assert scoring.tier(10, *podium["one_valid"]) == (1.0, "gold")
    assert scoring.tier(7, *podium["two_valid"]) == (0.0, None)
    assert scoring.tier(8, *podium["two_valid"]) == (0.67, "silver")
    assert scoring.tier(1e100, *podium["none_valid"]) == (0.0, None)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_scores_never_earn_medals(value):
    assert scoring.tier(value, 10, 8, 6) == (0.0, None)
    assert scoring.tier(value, None, None, None) == (0.0, None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(10, (1.0, "gold")), (9, (0.67, "silver")),
     (8, (0.33, "bronze")), (7, (0.0, None))],
)
def test_finite_thresholds_keep_existing_credit(value, expected):
    assert scoring.tier(value, 10, 9, 8) == expected


def test_equal_thresholds_award_gold_to_every_tied_submission():
    assert scoring.tier(2.5, 2.5, 2.5, 2.5) == (1.0, "gold")
    assert scoring.tier(2.49, 2.5, 2.5, 2.5) == (0.0, None)


def test_submission_ignores_blank_invalid_and_nonfinite_values(tmp_path):
    path = tmp_path / "submission.csv"
    path.write_text(
        "Task,Score\nvalid,12\nnegative,-5\nblank,\nnot_a_score,invalid\n"
        "nan,nan\npositive_infinity,inf\nnegative_infinity,-inf\n"
        "overflow,1e1000\nincomplete\n"
    )
    assert scoring.load_submission(path) == {"valid": 12.0, "negative": -5.0}


def test_empty_submission_is_missing_all_tasks(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    submission = scoring.load_submission(path)
    assert submission == {}
    podium = {"JobShop_abz": (10, None, None)}
    assert scoring.score(podium, submission) == (0.0, 0.0)


def test_released_example_reproduces_its_leaderboard_line():
    podium = scoring.load_podium(LEADERBOARD / "medal_podium.csv")
    submission = scoring.load_submission(LEADERBOARD / "submission_example.csv")
    with (LEADERBOARD / "medal_leaderboard.csv").open(encoding="utf-8-sig") as f:
        published = next(
            row for row in csv.DictReader(f) if row["Model"] == "claude-opus-4.6"
        )
    full, lite = scoring.score(podium, submission)
    # The released CSV may round aggregate scores to three decimal places.
    assert full == pytest.approx(float(published["Medal_v1"]), abs=0.0005)
    assert lite == pytest.approx(float(published["Medal_v1lite"]), abs=0.0005)
