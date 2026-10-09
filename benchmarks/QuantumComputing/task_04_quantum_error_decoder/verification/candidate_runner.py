"""Run a candidate decoder in its own interpreter.

The evaluator launches this process and hands it only the error model and the
syndrome batches -- never the true logical-observable flips. Keeping the
candidate out of the evaluator's address space is what turns that into a
guarantee instead of a convention: there is no parent frame to walk for the
answers, and ``stim``/``pymatching`` are refused at import time so the reference
decoder cannot be called instead of implemented.

Protocol
--------
Inputs  (``--inputs``):  ``<key>.problem.json`` + ``<key>.detectors.npy``
Outputs (``--outputs``): ``<key>.prediction.npy`` on success, otherwise
                         ``<key>.error.txt`` with the failure message.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
import types
from pathlib import Path

import numpy as np

FORBIDDEN_MODULES = ("pymatching", "stim")


class _ImportBlocker:
    """Raise on any attempt to import a forbidden module while the candidate runs."""

    def find_module(self, fullname, path=None):  # legacy hook, kept for older loaders
        return self.find_spec(fullname, path)

    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".", 1)[0]
        if root in FORBIDDEN_MODULES:
            raise ImportError(
                "import of %r is not permitted in a candidate decoder" % fullname
            )
        return None


def _preloaded_forbidden(module) -> list:
    """Catch a forbidden module that was already bound before the blocker went in."""
    found = set()
    for value in vars(module).values():
        if isinstance(value, types.ModuleType):
            root = getattr(value, "__name__", "").split(".", 1)[0]
            if root in FORBIDDEN_MODULES:
                found.add(root)
    return sorted(found)


def _load_candidate(path: Path):
    spec = importlib.util.spec_from_file_location("candidate_solution", path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load a Python module from %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["candidate_solution"] = module
    spec.loader.exec_module(module)
    decode = getattr(module, "decode", None)
    if not callable(decode):
        raise AttributeError(
            "candidate must define a callable decode(problem, detection_events)"
        )
    return module, decode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--outputs", required=True)
    args = parser.parse_args(argv)

    candidate = Path(args.candidate).resolve()
    inputs = Path(args.inputs).resolve()
    outputs = Path(args.outputs).resolve()
    outputs.mkdir(parents=True, exist_ok=True)

    if not candidate.is_file():
        print("candidate not found: %s" % candidate, file=sys.stderr)
        return 2

    # Install the blocker before the candidate module is executed, so a top-level
    # ``import pymatching`` fails at its own import site.
    sys.meta_path.insert(0, _ImportBlocker())
    try:
        module, decode = _load_candidate(candidate)
    except Exception:
        print(traceback.format_exc(), file=sys.stderr)
        return 3

    preloaded = _preloaded_forbidden(module)
    if preloaded:
        print(
            "forbidden module bound in candidate: %s" % ",".join(preloaded),
            file=sys.stderr,
        )
        return 4

    regimes = sorted(p.name[: -len(".detectors.npy")] for p in inputs.glob("*.detectors.npy"))
    if not regimes:
        print("no input regimes found in %s" % inputs, file=sys.stderr)
        return 5

    for key in regimes:
        problem = json.loads((inputs / ("%s.problem.json" % key)).read_text(encoding="utf-8"))
        detectors = np.load(inputs / ("%s.detectors.npy" % key))
        try:
            raw = decode(problem, detectors)
            prediction = np.asarray(raw)
        except Exception as exc:  # noqa: BLE001 - candidate faults are scored, not raised
            (outputs / ("%s.error.txt" % key)).write_text(
                "raised: %s" % type(exc).__name__, encoding="utf-8"
            )
            continue
        np.save(outputs / ("%s.prediction.npy" % key), prediction)

    print("decoded %d regime(s)" % len(regimes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())