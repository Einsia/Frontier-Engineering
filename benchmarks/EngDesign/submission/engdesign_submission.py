"""Initial EngDesign unified submission baseline.

This file is DATA, not a program. The evaluator reads it with a non-executing
literal parser (`ast.parse` + a literal-only evaluator), so nothing here is ever
run. Only these constructs are readable:

  * literals: str / bytes / int / float / bool / None
  * list / tuple / set / dict displays of literals
  * unary +/- on numbers
  * references to module-level names that were themselves bound to literals
    earlier in this file (e.g. `CY03_VIOBLK_READ` below)

Function definitions, function calls (including `"...".strip()`), f-strings,
comprehensions, imports and attribute access are NOT evaluated: they will make
the submission unreadable and score `valid=0`. Inline the values instead.

Edit values inside `SUBMISSION` only.
"""

# EVOLVE-BLOCK-START
CY03_VIOBLK_READ = "def vioblk_read(vioblk, pos, buf, len):\n    if vioblk is None or buf is None:\n        return -1\n    if pos < 0 or len < 0 or pos >= vioblk.capacity:\n        return -1\n    return -1"


CY03_VIOBLK_WRITE = "def vioblk_write(vioblk, pos, buf, len):\n    if vioblk is None or buf is None:\n        return -1\n    if pos < 0 or len < 0 or pos >= vioblk.capacity:\n        return -1\n    return -1"


WJ01_FUNCTION_CODE = "def denoise_image(noisy_img):\n    import numpy as np\n    return np.zeros_like(noisy_img)"


SUBMISSION = {
    "AM_02": {
        "reasoning": "Weak baseline with intentionally simple trajectories.",
        "config": {
            "robot_trajectory1": [
                {"t": 0, "x": 0, "y": 0},
                {"t": 1, "x": 0, "y": 0},
                {"t": 2, "x": 0, "y": 0},
                {"t": 3, "x": 0, "y": 0},
                {"t": 4, "x": 0, "y": 0},
                {"t": 5, "x": 0, "y": 0},
                {"t": 6, "x": 0, "y": 0},
                {"t": 7, "x": 0, "y": 0},
                {"t": 8, "x": 0, "y": 0},
                {"t": 9, "x": 0, "y": 0},
                {"t": 10, "x": 0, "y": 0},
                {"t": 11, "x": 0, "y": 0},
                {"t": 12, "x": 0, "y": 0},
                {"t": 13, "x": 0, "y": 0},
                {"t": 14, "x": 0, "y": 0},
                {"t": 15, "x": 0, "y": 0},
                {"t": 16, "x": 0, "y": 0},
                {"t": 17, "x": 0, "y": 0},
                {"t": 18, "x": 0, "y": 0},
                {"t": 19, "x": 0, "y": 0},
            ],
            "robot_trajectory2": [
                {"t": 0, "x": 1, "y": 1},
                {"t": 1, "x": 1, "y": 1},
                {"t": 2, "x": 1, "y": 1},
                {"t": 3, "x": 1, "y": 1},
                {"t": 4, "x": 1, "y": 1},
                {"t": 5, "x": 1, "y": 1},
                {"t": 6, "x": 1, "y": 1},
                {"t": 7, "x": 1, "y": 1},
                {"t": 8, "x": 1, "y": 1},
                {"t": 9, "x": 1, "y": 1},
                {"t": 10, "x": 1, "y": 1},
                {"t": 11, "x": 1, "y": 1},
                {"t": 12, "x": 1, "y": 1},
                {"t": 13, "x": 1, "y": 1},
                {"t": 14, "x": 1, "y": 1},
                {"t": 15, "x": 1, "y": 1},
                {"t": 16, "x": 1, "y": 1},
                {"t": 17, "x": 1, "y": 1},
                {"t": 18, "x": 1, "y": 1},
                {"t": 19, "x": 1, "y": 1},
            ],
        },
    },
    "AM_03": {
        "reasoning": "Weak baseline with intentionally simple trajectories.",
        "config": {
            "robot_trajectory": [
                {"t": 0, "x": 2, "y": 2},
                {"t": 1, "x": 2, "y": 2},
                {"t": 2, "x": 2, "y": 2},
                {"t": 3, "x": 2, "y": 2},
                {"t": 4, "x": 2, "y": 2},
                {"t": 5, "x": 2, "y": 2},
                {"t": 6, "x": 2, "y": 2},
                {"t": 7, "x": 2, "y": 2},
                {"t": 8, "x": 2, "y": 2},
                {"t": 9, "x": 2, "y": 2},
                {"t": 10, "x": 2, "y": 2},
                {"t": 11, "x": 2, "y": 2},
                {"t": 12, "x": 2, "y": 2},
                {"t": 13, "x": 2, "y": 2},
                {"t": 14, "x": 2, "y": 2},
                {"t": 15, "x": 2, "y": 2},
                {"t": 16, "x": 2, "y": 2},
                {"t": 17, "x": 2, "y": 2},
                {"t": 18, "x": 2, "y": 2},
                {"t": 19, "x": 2, "y": 2},
                {"t": 20, "x": 2, "y": 2},
                {"t": 21, "x": 2, "y": 2},
                {"t": 22, "x": 2, "y": 2},
                {"t": 23, "x": 2, "y": 2},
                {"t": 24, "x": 2, "y": 2},
                {"t": 25, "x": 2, "y": 2},
                {"t": 26, "x": 2, "y": 2},
                {"t": 27, "x": 2, "y": 2},
                {"t": 28, "x": 2, "y": 2},
                {"t": 29, "x": 2, "y": 2},
            ],
        },
    },
    "CY_03": {
        "reasoning": "Weak baseline implementation for vioblk read/write.",
        "config": {
            "vioblk_read": CY03_VIOBLK_READ,
            "vioblk_write": CY03_VIOBLK_WRITE,
        },
    },
    "WJ_01": {
        "reasoning": "Weak baseline that returns an all-zero image.",
        "config": {
            "denoising_strategy": "Return a zero image as placeholder baseline.",
            "filter_sequence": [
                "zeros_like(noisy_img)",
            ],
            "function_code": WJ01_FUNCTION_CODE,
        },
    },
    "XY_05": {
        "reasoning": "Weak baseline with empty control table.",
        "config": {
            "ports_table": {},
            "explanation": {},
            "state_transitions": {},
        },
    },
    "YJ_02": {
        "reasoning": "Weak baseline with wrong compliance prediction.",
        "config": {
            "y_hat": [
                [
                    0.0,
                ],
            ],
            "C_y_hat": 0.0,
        },
    },
    "YJ_03": {
        "reasoning": "Weak baseline with wrong stress prediction.",
        "config": {
            "y_hat": [
                [
                    0.0,
                ],
            ],
            "K_y_hat": 0.0,
        },
    },
}
# EVOLVE-BLOCK-END
