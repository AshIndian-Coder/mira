"""Periodic model retraining orchestration (active learning loop).

Wiring:
    export_feedback.py   -> feedback_pairs.csv from the DB feedback table
    train_qwen.py        -> fine-tune Qwen-1B-Embedding (contrastive loss)
    quantize_model.py    -> INT8 checkpoint
    evaluate_model.py    -> baseline vs fine-tune vs INT8 report

``trigger_retraining`` runs these as subprocesses (offline scripts), so a
training crash can never take down the API. It is guarded: without the
heavy ML dependencies installed it returns a clean "skipped" status.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.core.logger import get_logger

logger = get_logger("mira.retrainer")

PIPELINE_STEPS = [
    ("export_feedback", "app.ml_pipeline.export_feedback"),
    ("train_qwen", "app.ml_pipeline.train_qwen"),
    ("quantize_model", "app.ml_pipeline.quantize_model"),
    ("evaluate_model", "app.ml_pipeline.evaluate_model"),
]

_ML_MODULES = ("torch", "transformers")


def _ml_dependencies_available() -> bool:
    return all(importlib.util.find_spec(module) is not None for module in _ML_MODULES)


def _backend_root() -> Path:
    """Repository root (the directory that contains app/)."""
    return Path(__file__).resolve().parents[2]


def trigger_retraining(
    steps: List[str] = None,
    max_timeout: int = 14400,
) -> Dict[str, Any]:
    """Run the offline training pipeline as subprocesses.

    Returns a status report (also useful for /admin endpoints and demos).
    """
    report: Dict[str, Any] = {
        "started_at": datetime.utcnow().isoformat(),
        "steps": [],
        "status": "pending",
    }

    if not _ml_dependencies_available():
        report["status"] = "skipped"
        report["reason"] = (
            "ML training dependencies not installed (torch/transformers). "
            "Install them (see requirements.txt) and re-run."
        )
        logger.warning("Retraining skipped: %s", report["reason"])
        return report

    selected = steps or [name for name, _ in PIPELINE_STEPS]
    for name, module in PIPELINE_STEPS:
        if name not in selected:
            continue
        step_report: Dict[str, Any] = {"step": name, "module": module, "status": "running"}
        try:
            result = subprocess.run(
                [sys.executable, "-m", module, "--output-dir", "app/ml_pipeline/data/training"],
                cwd=str(_backend_root()),
                capture_output=True,
                text=True,
                timeout=max_timeout,
            )
            step_report["status"] = "success" if result.returncode == 0 else "failed"
            step_report["returncode"] = result.returncode
            step_report["stdout_tail"] = (result.stdout or "")[-2000:]
            step_report["stderr_tail"] = (result.stderr or "")[-2000:]
            if result.returncode != 0:
                report["status"] = "failed"
                report["failed_step"] = name
                report["steps"].append(step_report)
                logger.error("Retraining step %s failed: %s", name, step_report["stderr_tail"][-500:])
                break
        except subprocess.TimeoutExpired:
            step_report["status"] = "timeout"
            report["status"] = "failed"
            report["failed_step"] = name
        except Exception as exc:
            step_report["status"] = "error"
            step_report["error"] = str(exc)
            report["status"] = "failed"
            report["failed_step"] = name
        report["steps"].append(step_report)
    else:
        if report["status"] == "pending":
            report["status"] = "success"

    report["finished_at"] = datetime.utcnow().isoformat()
    logger.info("Retraining finished: %s", report["status"])
    return report

