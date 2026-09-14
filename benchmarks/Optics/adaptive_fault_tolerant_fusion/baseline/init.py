# EVOLVE-BLOCK-START
import numpy as np


def fuse_and_compute_dm_commands(
    slopes_multi: np.ndarray,
    reconstructor: np.ndarray,
    control_model: dict,
    prev_commands: np.ndarray | None = None,
    max_voltage: float = 0.50,
) -> np.ndarray:
    """
    Baseline: naive average over all WFS channels.

    Sensitive to corrupted sensors.
    """
    fused = np.mean(slopes_multi, axis=0)
    u = reconstructor @ fused
    return np.clip(u, -max_voltage, max_voltage)
# EVOLVE-BLOCK-END


# --------------------------------------------------------------------------- #
# Evaluation entry point. `verification/evaluate.py` runs this file as its own
# process in a scratch directory: it reads the multi-sensor slope stream from
# `problem.npz` and writes the resulting command matrix to `submission.npz`. The
# evaluator re-simulates the plant from those commands and scores it itself.
# `prev_commands` is always None here, matching the original evaluation loop
# for this task (single-shot fusion per case, no temporal state).
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
    slopes_multi_stream = problem["slopes_multi"]
    reconstructor = problem["reconstructor"]
    max_voltage = float(problem["max_voltage"])
    n_act = int(problem["n_act"])

    commands = np.zeros((len(slopes_multi_stream), n_act), dtype=np.float64)

    for i, slopes_multi in enumerate(slopes_multi_stream):
        cmd = np.asarray(
            fuse_and_compute_dm_commands(
                slopes_multi, reconstructor, control_model, None, max_voltage=max_voltage
            ),
            dtype=np.float64,
        )
        commands[i] = cmd

    np.savez("submission.npz", commands=commands)


if __name__ == "__main__":
    _main()
