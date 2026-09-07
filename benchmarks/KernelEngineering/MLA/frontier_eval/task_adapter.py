"""Task-specific glue between MLA and the isolated kernel harness.

See ``benchmarks/_shared/kernel_isolation.py`` for the contract. The reference
implementation, the KV-cache semantics and the tolerances (rtol=2e-2, atol=8e-3)
are the benchmark's own, taken from the pristine ``baseline/reference.py``; only
the process they run in has changed.

One measurement bug is fixed here as a side effect. The old benchmark loop ran
``benchmark(test, recheck=False, ...)``: it reused a single KV cache across all
100 timed reps while ``custom_kernel`` appends a row and advances ``seq_len``
on every call, so rep 100 was measured on a sequence 99 tokens longer than rep 1
-- and only the very first rep was ever checked for correctness. Here every rep
starts from the same restored cache state, and every rep is verified.
"""

from __future__ import annotations

import json

import torch

from baseline.reference import KVCache, check_implementation, generate_input

TASK_NAME = "MLA"

# Rows past the prefill that a single decode step may touch; restored between
# reps so each rep starts from the same cache state.
_RESTORE_GUARD = 8

_SCALAR_FIELDS = (
    "batch_size", "dim", "n_heads", "q_lora_rank", "kv_lora_rank",
    "qk_nope_head_dim", "qk_rope_head_dim", "v_head_dim", "seq_len", "max_seq_len",
)
_WEIGHTS = (
    "Q_proj_down_weight", "Q_proj_up_weight",
    "KV_proj_down_weight", "KV_proj_up_weight", "wo_weight",
)


def _device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def make_state(args: dict, seed: int) -> dict:
    call = dict(args)
    call["seed"] = int(seed)
    config, x, kv_cache = generate_input(**call)
    prefill = int(kv_cache.seq_len)
    return {"config": config, "x": x, "kv": kv_cache, "prefill": prefill,
            "kv_base": kv_cache.get_data()[:, :prefill].clone()}


def save_state(state: dict, path: str) -> None:
    config = state["config"]
    prefill = state["prefill"]
    payload = {
        "__meta__": json.dumps({
            "scalars": {name: getattr(config, name) for name in _SCALAR_FIELDS},
            "kv_cache_shape": list(config.kv_cache_shape),
            "prefill": prefill,
            "device": state["x"].device.type,
        }),
        "x": state["x"].detach().cpu(),
        # Only the filled prefix travels: the rest of the cache is zeros.
        "kv_prefill": state["kv"].get_data()[:, :prefill].detach().cpu(),
    }
    for name in _WEIGHTS:
        payload[name] = getattr(config, name).detach().cpu()
    torch.save(payload, path)


def load_state(path: str) -> dict:
    from baseline.reference import Config

    raw = torch.load(path, weights_only=True)
    meta = json.loads(raw["__meta__"])
    dev = meta["device"] if (meta["device"] != "cuda" or torch.cuda.is_available()) else "cpu"
    kwargs = dict(meta["scalars"])
    kwargs["kv_cache_shape"] = tuple(meta["kv_cache_shape"])
    for name in _WEIGHTS:
        kwargs[name] = raw[name].to(dev)
    config = Config(**kwargs)

    kv = KVCache(tuple(meta["kv_cache_shape"])).to(dev)
    kv(raw["kv_prefill"].to(dev))  # refills and sets seq_len exactly as generate_input did
    prefill = int(meta["prefill"])
    return {"config": config, "x": raw["x"].to(dev), "kv": kv, "prefill": prefill,
            "kv_base": kv.get_data()[:, :prefill].clone()}


def apply_round(state: dict, alpha: float):
    """Restore the cache and build this round's input.

    Restoring is O(1) plus a few zeroed rows, so it stays far below the kernel's
    own cost -- which matters, because the evaluator's wall-clock bound on the
    reported latency is only as tight as this overhead is small.
    """
    kv = state["kv"]
    prefill = state["prefill"]
    data = kv.get_data()
    # Restore the cache, then perturb the *cached* latents. Perturbing only x
    # would barely move the output: x is one of prefill+1 attended positions, so
    # its attention weight is ~1/prefill and a replayed answer would still pass
    # the tolerance check. The cached latents feed every key and value.
    data[:, :prefill].copy_(state["kv_base"])
    data[:, :prefill] += alpha
    end = min(prefill + _RESTORE_GUARD, data.size(1))
    data[:, prefill:end].zero_()
    kv.seq_len = prefill
    return (state["config"], state["x"] + alpha, kv)


def save_output(out, path: str) -> None:
    if not (isinstance(out, (tuple, list)) and len(out) == 2):
        raise TypeError(f"custom_kernel must return (output, kv_cache_data), got {type(out).__name__}")
    mla_out, kv_out = out
    if not isinstance(mla_out, torch.Tensor) or not isinstance(kv_out, torch.Tensor):
        raise TypeError("both elements of the MLA output must be tensors")
    torch.save({"out": mla_out.detach().cpu(), "kv": kv_out.detach().cpu()}, path)


def load_output(path: str):
    raw = torch.load(path, weights_only=True)
    dev = _device()
    return (raw["out"].to(dev), raw["kv"].to(dev))


def check(data, out) -> str:
    result = check_implementation(data, out)
    if isinstance(result, tuple):
        good, message = result
        return "" if good else str(message)
    return str(result or "")
