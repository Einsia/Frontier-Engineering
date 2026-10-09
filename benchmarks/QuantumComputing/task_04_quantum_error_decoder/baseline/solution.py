# EVOLVE-BLOCK-START
"""Initial program: a decoder for rotated surface-code memory experiments.

The evaluator calls :func:`decode` once per regime. It hands you a graphlike
detector error model and a batch of syndrome (detection-event) bitstrings
sampled from a Stim circuit, and asks for the logical observable flips.

The shipped baseline ignores the syndrome and predicts "no flip" for every
shot. That is legal, costs nothing, and scores 0.0 by construction. Replace it
with a real decoder: minimum-weight perfect matching over the graphlike error
model, union-find, belief propagation, correlated matching, a learned decoder,
or something better.

Only the code between the EVOLVE-BLOCK markers is yours to change. Keep the
signature and the return shape: the evaluator knows nothing else about you.
"""

from __future__ import annotations

import numpy as np


def decode(problem, detection_events):
    """Predict logical observable flips from syndrome data.

    Args:
        problem: dict with
            - ``num_detectors`` (int), ``num_observables`` (int);
            - ``distance`` (int), ``rounds`` (int);
            - ``errors``: the graphlike detector error model, a list of
              independent error mechanisms. Each entry is
              ``{"p": float, "dets": [int, ...], "obs": [int, ...]}`` where ``p``
              is that mechanism's independent firing probability, ``dets`` is
              the set of detectors it flips (at most two, because the model is
              decomposed), and ``obs`` is the set of logical observables it
              flips.
        detection_events: bool array of shape ``(shots, num_detectors)``: for
            each shot, which detectors fired.

    Returns:
        Array of shape ``(shots, num_observables)`` with 0/1 entries: for each
        shot, whether you believe each logical observable was flipped.
    """
    shots = detection_events.shape[0]
    return np.zeros((shots, problem["num_observables"]), dtype=bool)
# EVOLVE-BLOCK-END