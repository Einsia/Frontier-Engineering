"""Task-specific glue between TriMul and the isolated kernel harness.

See ``benchmarks/_shared/kernel_isolation.py`` for the contract. ``ref_kernel``
and the tolerances (rtol=2e-2, atol=2e-2) are the benchmark's own; the change is
that they now run in a process the candidate cannot reach.
"""

from __future__ import annotations

import json

import torch

from baseline.reference import check_implementation, generate_input

TASK_NAME = "TriMul"

_WEIGHT_PREFIX = "w::"


def _device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def make_state(args: dict, seed: int) -> dict:
    call = dict(args)
    call["seed"] = int(seed)
    input_tensor, mask, weights, config = generate_input(**call)
    return {"input": input_tensor, "mask": mask, "weights": weights, "config": config}


def save_state(state: dict, path: str) -> None:
    payload = {
        "__meta__": json.dumps({
            "config": state["config"],
            "device": state["input"].device.type,
        }),
        "input": state["input"].detach().cpu(),
        "mask": state["mask"].detach().cpu(),
    }
    for name, tensor in state["weights"].items():
        payload[_WEIGHT_PREFIX + name] = tensor.detach().cpu()
    torch.save(payload, path)


def load_state(path: str) -> dict:
    raw = torch.load(path, weights_only=True)
    meta = json.loads(raw["__meta__"])
    dev = meta["device"] if (meta["device"] != "cuda" or torch.cuda.is_available()) else "cpu"
    weights = {
        key[len(_WEIGHT_PREFIX):]: value.to(dev)
        for key, value in raw.items()
        if isinstance(key, str) and key.startswith(_WEIGHT_PREFIX)
    }
    return {
        "input": raw["input"].to(dev),
        "mask": raw["mask"].to(dev),
        "weights": weights,
        "config": meta["config"],
    }


def apply_round(state: dict, alpha: float):
    """Build this round's input; mask and weights are copied so a kernel that
    writes through its arguments cannot poison a later round."""
    return (
        state["input"] + alpha * torch.sin(
            torch.arange(state["input"].shape[-1], device=state["input"].device,
                         dtype=torch.float32) + 1
        ).to(state["input"].dtype),
        state["mask"].clone(),
        {name: tensor.clone() for name, tensor in state["weights"].items()},
        dict(state["config"]),
    )


def save_output(out, path: str) -> None:
    if not isinstance(out, torch.Tensor):
        raise TypeError(f"custom_kernel must return a tensor, got {type(out).__name__}")
    torch.save({"out": out.detach().cpu()}, path)


def load_output(path: str):
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
