from __future__ import annotations

MAX_ITERATIONS = 50


def score_move(move, state):
    return (
        float(move["delta_duration"]),
        -float(move["machine_position"]),
        -float(move["machine_id"]),
    )
