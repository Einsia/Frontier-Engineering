# EVOLVE-BLOCK-START
import numpy as np


def compute_dm_commands(
    slopes: np.ndarray,
    reconstructor: np.ndarray,
    control_model: dict,
    prev_commands: np.ndarray | None = None,
    max_voltage: float = 0.15,
) -> np.ndarray:
    """
    Baseline: one-shot linear control + hard clipping.

    This intentionally ignores the constrained least-squares structure.
    """
    u = reconstructor @ slopes
    return np.clip(u, -max_voltage, max_voltage)
# EVOLVE-BLOCK-END


# --------------------------------------------------------------------------- #
# Evaluation entry point. `verification/evaluate.py` runs this file as its own
# process in a scratch directory: it reads the slope stream from `problem.npz`,
# replays the documented actuator-lag recurrence to rebuild `prev_commands`, and
# writes the resulting command matrix to `submission.npz`. The evaluator then
# re-simulates the plant from those commands and computes the score itself.
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
    n_act = int(problem["n_act"])

    commands = np.zeros((len(slopes_stream), n_act), dtype=np.float64)
    prev_applied = np.zeros(n_act, dtype=np.float64)

    for i, slopes in enumerate(slopes_stream):
        cmd = np.asarray(
            compute_dm_commands(
                slopes, reconstructor, control_model, prev_applied, max_voltage=max_voltage
            ),
            dtype=np.float64,
        )
        commands[i] = cmd
        prev_applied = actuator_lag * prev_applied + (1.0 - actuator_lag) * cmd

    np.savez("submission.npz", commands=commands)


if __name__ == "__main__":
    _main()
