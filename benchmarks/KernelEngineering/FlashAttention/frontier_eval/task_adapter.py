"""Task-specific glue between FlashAttention and the isolated kernel harness.

Loaded by ``benchmarks/_shared/kernel_worker.py`` in both worker roles. It is
the only place that knows the shape of this task's input, output and
correctness check; the orchestration in ``kernel_isolation.py`` stays generic.

Everything here is benchmark-owned code: ``generate_input`` and
``check_implementation`` come from the pristine ``baseline/reference.py``, so
the tolerances (rtol=2e-2, atol=8e-3) and the reference kernel are exactly the
ones the benchmark shipped. What changed is *where* they run -- in the trusted
process, never in the candidate's.
"""

from __future__ import annotations

import dataclasses
import json

import torch

from baseline.reference import check_implementation, generate_input

TASK_NAME = "FlashAttention"


def _device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def make_state(args: dict, seed: int) -> dict:
    """Trusted worker only: build the authoritative input for one case."""
    call = dict(args)
    call["seed"] = int(seed)
    config, q, k, v = generate_input(**call)
    return {"config": config, "Q": q, "K": k, "V": v}


def save_state(state: dict, path: str) -> None:
    """Serialize the input for the candidate worker. Plain tensors plus a JSON
    header, so the other side never has to unpickle a custom class."""
    payload = {
        "__meta__": json.dumps({
            "config": dataclasses.asdict(state["config"]),
            "device": state["Q"].device.type,
        }),
        "Q": state["Q"].detach().cpu(),
        "K": state["K"].detach().cpu(),
        "V": state["V"].detach().cpu(),
    }
    torch.save(payload, path)


def load_state(path: str) -> dict:
    from baseline.task import Config

    raw = torch.load(path, weights_only=True)
    meta = json.loads(raw["__meta__"])
    dev = meta["device"] if (meta["device"] != "cuda" or torch.cuda.is_available()) else "cpu"
    return {
        "config": Config(**meta["config"]),
        "Q": raw["Q"].to(dev),
        "K": raw["K"].to(dev),
        "V": raw["V"].to(dev),
    }


def apply_round(state: dict, alpha: float):
    """Build this round's input.

    ``alpha`` is chosen by the evaluator and differs for every timed rep, so an
    answer cached from an earlier rep is wrong for this one. The base tensors are
    never modified, and K/V are copied, so a kernel that writes through its
    arguments cannot corrupt later rounds (it would only fail its own checks).
    Both workers run this same function on the same bytes, so the trusted side
    verifies against exactly the input the kernel saw.
    """
    # V is the tensor to perturb: the output is a convex combination of V's rows
    # (softmax weights sum to 1), so shifting V by alpha shifts every output
    # element by about alpha -- far outside the benchmark's own atol of 8e-3.
    # Perturbing Q instead is not enough: a uniform shift of the logits is
    # largely absorbed by the softmax, and a replayed answer still passed.
    return (
        state["config"],
        state["Q"].clone(),
        state["K"].clone(),
        state["V"] + alpha,
    )


def save_output(out, path: str) -> None:
    if not isinstance(out, torch.Tensor):
        raise TypeError(f"custom_kernel must return a tensor, got {type(out).__name__}")
    torch.save({"out": out.detach().cpu()}, path)


def load_output(path: str):
    # weights_only=True: this file was written by the candidate's process, and
    # this is the process that must stay clean.
    raw = torch.load(path, weights_only=True)
    out = raw["out"]
    if not isinstance(out, torch.Tensor):
        raise TypeError("candidate output is not a tensor")
    return out.to(_device())


def check(data, out) -> str:
    result = check_implementation(data, out)
    if isinstance(result, tuple):
        good, message = result
        return "" if good else str(message)
    return str(result or "")
