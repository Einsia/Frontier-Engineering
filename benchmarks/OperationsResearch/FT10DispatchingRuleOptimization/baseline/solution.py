from __future__ import annotations


def score_operation(operation, state):
    return (
        -float(operation["duration"]),
        -float(operation["remaining_job_work"]),
        -float(operation["job_id"]),
    )
