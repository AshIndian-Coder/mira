from __future__ import annotations

import os
import random
from typing import Any

import numpy as np
import torch

DEFAULT_SEED = 42


def seed_everything(seed: int = DEFAULT_SEED, *, deterministic: bool = True) -> int:
    if not isinstance(seed, int):
        raise TypeError("seed must be an int")
    if seed < 0:
        raise ValueError("seed must be >= 0")
    if not isinstance(deterministic, bool):
        raise TypeError("deterministic must be bool")

    if deterministic:
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    torch.backends.cudnn.deterministic = deterministic
    torch.backends.cudnn.benchmark = not deterministic
    if deterministic:
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
    try:
        torch.use_deterministic_algorithms(deterministic, warn_only=True)
    except TypeError:
        torch.use_deterministic_algorithms(deterministic)
    return seed


def get_rng_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "python_random_state": random.getstate(),
        "numpy_random_state": np.random.get_state(),
        "torch_cpu_state": torch.get_rng_state().clone(),
    }
    if torch.cuda.is_available():
        state["torch_cuda_state"] = [value.clone() for value in torch.cuda.get_rng_state_all()]
    return state


def restore_rng_state(state: dict[str, Any]) -> None:
    if not isinstance(state, dict):
        raise TypeError("state must be a dictionary")
    if state.get("python_random_state") is not None:
        random.setstate(state["python_random_state"])
    if state.get("numpy_random_state") is not None:
        np.random.set_state(state["numpy_random_state"])
    cpu_state = state.get("torch_cpu_state")
    if cpu_state is not None:
        if not isinstance(cpu_state, torch.Tensor):
            raise TypeError("torch_cpu_state must be a tensor")
        torch.set_rng_state(cpu_state.detach().cpu().to(torch.uint8).contiguous())
    cuda_state = state.get("torch_cuda_state")
    if cuda_state is None or not torch.cuda.is_available():
        return
    if not isinstance(cuda_state, list) or len(cuda_state) != torch.cuda.device_count():
        raise ValueError("Checkpoint CUDA RNG state count does not match the current device count")
    torch.cuda.set_rng_state_all([
        value.detach().cpu().to(torch.uint8).contiguous() for value in cuda_state
    ])


def describe_seed_configuration(seed: int = DEFAULT_SEED, deterministic: bool = True) -> dict[str, Any]:
    return {
        "seed": int(seed),
        "deterministic_requested": bool(deterministic),
        "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
        "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
        "deterministic_algorithms_enabled": bool(torch.are_deterministic_algorithms_enabled()),
        "cudnn_deterministic": bool(torch.backends.cudnn.deterministic),
        "cudnn_benchmark": bool(torch.backends.cudnn.benchmark),
    }


__all__ = [
    "DEFAULT_SEED",
    "describe_seed_configuration",
    "get_rng_state",
    "restore_rng_state",
    "seed_everything",
]