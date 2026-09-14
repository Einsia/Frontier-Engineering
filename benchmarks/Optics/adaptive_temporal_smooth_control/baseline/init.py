# EVOLVE-BLOCK-START
import numpy as np


def compute_dm_commands(
    slopes: np.ndarray,
    reconstructor: np.ndarray,
    control_model: dict,
    prev_commands: np.ndarray,
    max_voltage: float = 0.25,
) -> np.ndarray:
    """
    Baseline: frame-wise independent control.

    Ignores temporal smoothness and command slew limits.
    """
    u = reconstructor @ slopes
    return np.clip(u, -max_voltage, max_voltage)
# EVOLVE-BLOCK-END


# --------------------------------------------------------------------------- #
# Evaluation entry point. `verification/evaluate.py` runs this file as its own
# process in a scratch directory: it reads the episodic slope stream from
# `problem.npz`, replays the documented rate limiter + actuator lag to rebuild
# `prev_commands`, and writes the command matrix to `submission.npz`. The
# evaluator re-simulates the plant from those commands and scores it itself.
#
# Keep this block: without a valid `submission.npz` the run scores as invalid.
# --------------------------------------------------------------------------- #
def _load_problem():
    data = np.load("problem.npz", allow_pickle=False)
    try:
        problem = {key: data[key] for key in data.files}
    finally:
        data.close()
    control_model = {
        key[len("cm__"):]: (value if value.ndim else value.item())
        for key, value in problem.items()
        if key.startswith("cm__")
    }
    return problem, control_model


def _main() -> None:
    problem, control_model = _load_problem()
    slopes_stream = problem["slopes"]
    reconstructor = problem["reconstructor"]
    max_voltage = float(problem["max_voltage"])
    actuator_lag = float(problem["actuator_lag"])
    rate_limit = float(problem["rate_limit"])
    episode_length = int(problem["episode_length"])
    n_act = int(problem["n_act"])

    commands = np.zeros((len(slopes_stream), n_act), dtype=np.float64)
    prev_applied = np.zeros(n_act, dtype=np.float64)

    for i, slopes in enumerate(slopes_stream):
        if i % episode_length == 0:
            # Each episode restarts from a flat mirror.
            prev_applied = np.zeros(n_act, dtype=np.float64)

        cmd = np.asarray(
            compute_dm_commands(
                slopes, reconstructor, control_model, prev_applied, max_voltage=max_voltage
            ),
            dtype=np.float64,
        )
        commands[i] = cmd

        delta_cmd = np.clip(cmd - prev_applied, -rate_limit, rate_limit)
        limited_cmd = prev_applied + delta_cmd
        prev_applied = actuator_lag * prev_applied + (1.0 - actuator_lag) * limited_cmd

    np.savez("submission.npz", commands=commands)


if __name__ == "__main__":
    _main()
