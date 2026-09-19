from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

CHECKPOINT_VERSION = "3.0"


def _atomic_torch_save(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f"{path.stem}.", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    temp = Path(temp_name)
    try:
        torch.save(payload, temp)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _atomic_json_write(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        temp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False, default=str),
            encoding="utf-8",
        )
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _move_optimizer_state_to_device(optimizer: torch.optim.Optimizer, device: torch.device) -> None:
    def move(value: Any) -> Any:
        if isinstance(value, torch.Tensor):
            return value.to(device=device, non_blocking=True)
        if isinstance(value, dict):
            return {key: move(item) for key, item in value.items()}
        if isinstance(value, list):
            return [move(item) for item in value]
        if isinstance(value, tuple):
            return tuple(move(item) for item in value)
        return value

    for state in optimizer.state.values():
        for key, value in list(state.items()):
            state[key] = move(value)


def save_checkpoint(
    path: str | Path,
    *,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer | None = None,
    scheduler: Any | None = None,
    scaler: Any | None = None,
    epoch: int = 0,
    global_step: int = 0,
    best_metric: float | None = None,
    config: dict[str, Any] | None = None,
    rng_state: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    if epoch < 0 or global_step < 0:
        raise ValueError("epoch and global_step must be >= 0")
    checkpoint_path = Path(path)
    payload: dict[str, Any] = {
        "checkpoint_version": CHECKPOINT_VERSION,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "epoch": int(epoch),
        "global_step": int(global_step),
        "best_metric": None if best_metric is None else float(best_metric),
        "model_state_dict": model.state_dict(),
        "config": dict(config or {}),
        "extra": dict(extra or {}),
    }
    if optimizer is not None:
        payload["optimizer_state_dict"] = optimizer.state_dict()
    if scheduler is not None:
        payload["scheduler_state_dict"] = scheduler.state_dict()
    if scaler is not None:
        payload["scaler_state_dict"] = scaler.state_dict()
    if rng_state is not None:
        payload["rng_state"] = rng_state
    _atomic_torch_save(payload, checkpoint_path)
    return checkpoint_path


def load_checkpoint(
    path: str | Path,
    *,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer | None = None,
    scheduler: Any | None = None,
    scaler: Any | None = None,
    map_location: str | torch.device = "cpu",
    strict: bool = True,
) -> dict[str, Any]:
    checkpoint_path = Path(path)
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"Checkpoint not found:\n{checkpoint_path.resolve()}")
    payload = torch.load(checkpoint_path, map_location=map_location, weights_only=False)
    if not isinstance(payload, dict):
        raise ValueError("Checkpoint must contain a dictionary.")
    version = payload.get("checkpoint_version")
    if version != CHECKPOINT_VERSION:
        raise ValueError(f"Unsupported checkpoint version {version!r}; expected {CHECKPOINT_VERSION!r}.")
    state_dict = payload.get("model_state_dict")
    if not isinstance(state_dict, dict):
        raise ValueError("Checkpoint is missing model_state_dict.")

    result = model.load_state_dict(state_dict, strict=strict)
    missing = list(getattr(result, "missing_keys", []))
    unexpected = list(getattr(result, "unexpected_keys", []))
    if strict and (missing or unexpected):
        raise RuntimeError(f"Strict checkpoint load reported missing={missing}, unexpected={unexpected}")

    model_device = next(model.parameters()).device
    if optimizer is not None:
        state = payload.get("optimizer_state_dict")
        if state is None:
            raise ValueError("Checkpoint has no optimizer_state_dict.")
        optimizer.load_state_dict(state)
        _move_optimizer_state_to_device(optimizer, model_device)
    if scheduler is not None:
        state = payload.get("scheduler_state_dict")
        if state is None:
            raise ValueError("Checkpoint has no scheduler_state_dict.")
        scheduler.load_state_dict(state)
    if scaler is not None:
        state = payload.get("scaler_state_dict")
        if state is None:
            raise ValueError("Checkpoint has no scaler_state_dict.")
        scaler.load_state_dict(state)

    metadata = {
        key: value
        for key, value in payload.items()
        if key not in {"model_state_dict", "optimizer_state_dict", "scheduler_state_dict", "scaler_state_dict"}
    }
    if not strict and (missing or unexpected):
        metadata["missing_keys"] = missing
        metadata["unexpected_keys"] = unexpected
    return metadata


def save_checkpoint_metadata(checkpoint_path: str | Path, metadata: dict[str, Any]) -> Path:
    checkpoint_path = Path(checkpoint_path)
    metadata_path = checkpoint_path.with_suffix(".json")
    payload = {
        "checkpoint_version": CHECKPOINT_VERSION,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        **metadata,
    }
    _atomic_json_write(payload, metadata_path)
    return metadata_path


def checkpoint_summary(path: str | Path) -> dict[str, Any]:
    checkpoint_path = Path(path)
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"Checkpoint not found:\n{checkpoint_path.resolve()}")
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if not isinstance(payload, dict):
        raise ValueError("Checkpoint must contain a dictionary.")
    state = payload.get("model_state_dict", {})
    parameter_count = sum(value.numel() for value in state.values() if isinstance(value, torch.Tensor))
    return {
        "checkpoint_version": payload.get("checkpoint_version"),
        "saved_at_utc": payload.get("saved_at_utc"),
        "epoch": payload.get("epoch"),
        "global_step": payload.get("global_step"),
        "best_metric": payload.get("best_metric"),
        "parameter_count": int(parameter_count),
        "has_optimizer": "optimizer_state_dict" in payload,
        "has_scheduler": "scheduler_state_dict" in payload,
        "has_scaler": "scaler_state_dict" in payload,
        "has_rng_state": "rng_state" in payload,
        "extra": payload.get("extra", {}),
        "config": payload.get("config", {}),
    }


__all__ = [
    "CHECKPOINT_VERSION",
    "checkpoint_summary",
    "load_checkpoint",
    "save_checkpoint",
    "save_checkpoint_metadata",
]
