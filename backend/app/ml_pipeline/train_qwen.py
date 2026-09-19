from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import signal
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any
from collections.abc import Mapping

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer
from torch.optim import AdamW
from torch.optim.lr_scheduler import LambdaLR

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = next(
    (
        candidate
        for candidate in [BASE_DIR, *BASE_DIR.parents]
        if (candidate / "backend" / "app" / "ml_pipeline").is_dir()
    ),
    BASE_DIR,
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.ml_pipeline.training_utils.checkpoint import (
    CHECKPOINT_VERSION,
    load_checkpoint,
    save_checkpoint,
    save_checkpoint_metadata,
)
from backend.app.ml_pipeline.training_utils.dataset import (
    ALLOWED_HN_TYPES,
    MiraPairDataset,
    MiraTripletDataset,
    collate_pairs,
    collate_triplets,
    create_split_dataset,
    dataframe_to_triplet_records,
    load_pairs_dataframe,
    normalize_pair_type,
)
from backend.app.ml_pipeline.training_utils.loss import (
    MIRAHardNegativeLoss,
    MIRATripletHardNegativeLoss,
)
from backend.app.ml_pipeline.training_utils.metrics import (
    find_best_threshold,
    hard_negative_metrics,
    to_serializable,
)
from backend.app.ml_pipeline.training_utils.seed import (
    DEFAULT_SEED,
    get_rng_state,
    restore_rng_state,
    seed_everything,
)

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
TRAINER_VERSION = "6.0-all-hn-triplet-production"
DATA_PATH = BASE_DIR / "train_data" / "training" / "Training_Pairs_MIRA_FINAL.csv"
TRIPLET_DATA_PATH = BASE_DIR / "results" / "epoch2" / "Training_Triplets_MIRA_ALL_HN.csv"
TRIPLET_SUMMARY_PATH = BASE_DIR / "results" / "epoch2" / "epoch2_triplet_build_all_hn_summary.json"
MODEL_ROOT = BASE_DIR / "qwen_models"
INITIAL_MODEL_DIR = MODEL_ROOT / "epoch1_frozen" / "best"
FINETUNED_DIR = MODEL_ROOT / "epoch2_finetuned"
CHECKPOINT_DIR = FINETUNED_DIR / "checkpoints"
RESULTS_DIR = BASE_DIR / "results" / "epoch2_training"
LATEST_CHECKPOINT_PATH = CHECKPOINT_DIR / "latest.pt"
BEST_CHECKPOINT_PATH = CHECKPOINT_DIR / "best.pt"

MAX_SEQ_LENGTH = 256
MICRO_BATCH_SIZE = 2
TRIPLET_BATCH_SIZE = 2
ENCODER_MICRO_BATCH_SIZE = 4
GRADIENT_ACCUMULATION_STEPS = 4
NUM_EPOCHS = 1
LEARNING_RATE = 5e-6
WEIGHT_DECAY = 0.01
WARMUP_RATIO = 0.05
MAX_GRAD_NORM = 1.0
HN_EVALUATION_THRESHOLD = 0.85
MARGIN = 0.30
POSITIVE_WEIGHT = 1.0
NEGATIVE_WEIGHT = 1.0
HARD_NEGATIVE_WEIGHT = 8.0
HARD_NEGATIVE_MARGIN = 0.85
HARD_NEGATIVE_POWER = 2.0
TRIPLET_MARGIN = 0.25
TRIPLET_WEIGHT = 2.5
TRIPLET_HARD_NEGATIVE_WEIGHT = 10.0
TRIPLET_HARD_NEGATIVE_POWER = 2.0
PAIR_LOSS_WEIGHT = 1.0
TRIPLET_LOSS_WEIGHT = 1.0
EVAL_EVERY_STEPS = 250
CHECKPOINT_EVERY_STEPS = 250
LOG_EVERY_STEPS = 10
HEARTBEAT_SECONDS = 30.0
COOLDOWN_MS = 0
EVAL_BATCH_SIZE = 8
TARGET_DEV_F1 = 0.95
TARGET_HN_FHC = 0.20
FALLBACK_DEV_F1_FLOOR = 0.92
THRESHOLD_OBJECTIVE = "f1"
PAIR_SEED_OFFSET = 1009
TRIPLET_SEED_OFFSET = 2003
CYCLE_SEED_STRIDE = 104729
DEFAULT_SMOKE_STEPS = 2
MIN_TRIPLET_ROWS = 50_000
MIN_UNIQUE_TRIPLET_HNS = 10_000
MAX_CONSECUTIVE_FP16_OVERFLOWS = 10


class EpochBatchPlanner:
    def __init__(self, dataset: MiraPairDataset, batch_size: int, seed: int, stream_id: int) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if len(dataset) == 0:
            raise ValueError("dataset must not be empty")
        self.dataset = dataset
        self.batch_size = int(batch_size)
        self.seed = int(seed)
        self.stream_id = int(stream_id)
        self.permutation = self._make_permutation()

    def _make_permutation(self) -> list[int]:
        generator = torch.Generator(device="cpu")
        generator.manual_seed((self.seed + self.stream_id) % (2**63 - 1))
        return torch.randperm(len(self.dataset), generator=generator).tolist()

    @property
    def num_batches(self) -> int:
        return math.ceil(len(self.dataset) / self.batch_size)

    def get(self, batch_index: int) -> list[dict[str, Any]]:
        if not 0 <= batch_index < self.num_batches:
            raise IndexError(f"batch_index {batch_index} outside valid range")
        start = batch_index * self.batch_size
        indices = self.permutation[start : start + self.batch_size]
        return [self.dataset[index] for index in indices]


class CyclingTripletPlanner:
    def __init__(self, dataset: MiraTripletDataset, batch_size: int, seed: int) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if len(dataset) == 0:
            raise ValueError("dataset must not be empty")
        self.dataset = dataset
        self.batch_size = int(batch_size)
        self.seed = int(seed)
        self.batches_per_cycle = math.ceil(len(dataset) / self.batch_size)
        self._cached_cycle = -1
        self._cached_permutation: list[int] | None = None

    def _permutation_for_cycle(self, cycle: int) -> list[int]:
        if cycle == self._cached_cycle and self._cached_permutation is not None:
            return self._cached_permutation
        generator = torch.Generator(device="cpu")
        cycle_seed = (
            self.seed + TRIPLET_SEED_OFFSET + cycle * CYCLE_SEED_STRIDE
        ) % (2**63 - 1)
        generator.manual_seed(cycle_seed)
        permutation = torch.randperm(len(self.dataset), generator=generator).tolist()
        self._cached_cycle = cycle
        self._cached_permutation = permutation
        return permutation

    def get(self, global_batch_index: int) -> list[dict[str, Any]]:
        if global_batch_index < 0:
            raise ValueError("global_batch_index must be >= 0")
        cycle, local_batch = divmod(global_batch_index, self.batches_per_cycle)
        permutation = self._permutation_for_cycle(cycle)
        start = local_batch * self.batch_size
        indices = permutation[start : start + self.batch_size]
        if len(indices) < self.batch_size:
            indices.extend(permutation[: self.batch_size - len(indices)])
        return [self.dataset[index] for index in indices]


class TrainingHeartbeat:
    def __init__(self, interval_seconds: float) -> None:
        self.interval_seconds = float(interval_seconds)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "phase": "initializing",
            "epoch": 0,
            "optimizer_step": 0,
            "target_step": 1,
            "batch_index": 0,
            "total_batches": 0,
        }
        self._thread: threading.Thread | None = None

    def update(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)

    def start(self) -> None:
        if self.interval_seconds <= 0:
            return
        self._thread = threading.Thread(target=self._run, name="mira-heartbeat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.interval_seconds + 1.0, 2.0))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            with self._lock:
                state = dict(self._state)
            print(
                "[heartbeat] "
                f"phase={state['phase']} "
                f"epoch={state['epoch'] + 1} "
                f"target_step={state['target_step']:,} "
                f"completed_step={state['optimizer_step']:,} "
                f"batch={state['batch_index']:,}/{state['total_batches']:,}",
                flush=True,
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MIRA Epoch-2 Qwen3 embedding fine-tuning with full TRAIN hard-negative coverage."
    )
    parser.add_argument("--data-path", type=Path, default=DATA_PATH)
    parser.add_argument("--triplet-path", type=Path, default=TRIPLET_DATA_PATH)
    parser.add_argument("--triplet-summary", type=Path, default=TRIPLET_SUMMARY_PATH)
    parser.add_argument("--initial-model", type=Path, default=INITIAL_MODEL_DIR)
    parser.add_argument("--output-root", type=Path, default=FINETUNED_DIR)
    parser.add_argument("--results-root", type=Path, default=RESULTS_DIR)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--resume", nargs="?", const="latest", default=None)
    parser.add_argument("--warm-start", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=NUM_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=MICRO_BATCH_SIZE)
    parser.add_argument("--triplet-batch-size", type=int, default=TRIPLET_BATCH_SIZE)
    parser.add_argument("--encoder-micro-batch-size", type=int, default=ENCODER_MICRO_BATCH_SIZE)
    parser.add_argument("--grad-accumulation", type=int, default=GRADIENT_ACCUMULATION_STEPS)
    parser.add_argument("--learning-rate", type=float, default=LEARNING_RATE)
    parser.add_argument("--eval-every", type=int, default=EVAL_EVERY_STEPS)
    parser.add_argument("--checkpoint-every", type=int, default=CHECKPOINT_EVERY_STEPS)
    parser.add_argument("--log-every", type=int, default=LOG_EVERY_STEPS)
    parser.add_argument("--heartbeat-seconds", type=float, default=HEARTBEAT_SECONDS)
    parser.add_argument("--cooldown-ms", type=int, default=COOLDOWN_MS)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--pair-loss-weight", type=float, default=PAIR_LOSS_WEIGHT)
    parser.add_argument("--triplet-loss-weight", type=float, default=TRIPLET_LOSS_WEIGHT)
    parser.add_argument("--no-gradient-checkpointing", action="store_true")
    parser.add_argument("--deterministic", action="store_true")
    parser.add_argument("--overwrite-run", action="store_true")
    return parser.parse_args()


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_runtime_args(args: argparse.Namespace) -> None:
    if args.resume is not None and args.warm_start is not None:
        raise ValueError("--resume and --warm-start are mutually exclusive")
    if args.smoke_test and (args.resume is not None or args.warm_start is not None):
        raise ValueError("--smoke-test cannot be combined with resume or warm-start")
    if args.warm_start is not None and args.max_steps is not None:
        raise ValueError("--warm-start cannot be combined with --max-steps")
    if args.resume is not None and args.max_steps is not None:
        raise ValueError("--resume cannot be combined with --max-steps; resume uses the full training schedule")
    if args.validate_only and (args.resume is not None or args.warm_start is not None or args.smoke_test):
        raise ValueError("--validate-only cannot be combined with training modes")
    if args.epochs <= 0:
        raise ValueError("--epochs must be > 0")
    if args.batch_size <= 0 or args.triplet_batch_size <= 0 or args.encoder_micro_batch_size <= 0:
        raise ValueError("batch sizes must be > 0")
    if args.grad_accumulation <= 0:
        raise ValueError("--grad-accumulation must be > 0")
    if not math.isfinite(args.learning_rate) or args.learning_rate <= 0:
        raise ValueError("--learning-rate must be finite and > 0")
    if args.eval_every <= 0 or args.checkpoint_every <= 0 or args.log_every <= 0:
        raise ValueError("eval/checkpoint/log intervals must be > 0")
    if not math.isfinite(args.heartbeat_seconds) or args.heartbeat_seconds < 0:
        raise ValueError("--heartbeat-seconds must be finite and >= 0")
    if args.cooldown_ms < 0:
        raise ValueError("--cooldown-ms must be >= 0")
    if args.max_steps is not None and args.max_steps <= 0:
        raise ValueError("--max-steps must be > 0")
    if not math.isfinite(args.pair_loss_weight) or args.pair_loss_weight <= 0:
        raise ValueError("--pair-loss-weight must be finite and > 0")
    if args.overwrite_run and args.resume is not None:
        raise ValueError("--overwrite-run cannot be combined with --resume")
    if not math.isfinite(args.triplet_loss_weight) or args.triplet_loss_weight <= 0:
        raise ValueError("--triplet-loss-weight must be finite and > 0")
    if args.seed < 0:
        raise ValueError("--seed must be >= 0")


def prepare_output_state(args: argparse.Namespace) -> None:
    if args.validate_only:
        return
    output_root = args.output_root.resolve()
    results_root = args.results_root.resolve()
    production_checkpoint_dir = output_root / "checkpoints"
    stale_paths = [
        production_checkpoint_dir / "latest.pt",
        production_checkpoint_dir / "best.pt",
        output_root / "best",
        output_root / ".best_export_tmp",
        results_root / "training_result.json",
        results_root / "training_manifest.json",
    ]
    if (args.smoke_test or args.max_steps is not None) and args.resume is None and args.warm_start is None:
        diagnostics_root = results_root / "diagnostics"
        if diagnostics_root.exists():
            shutil.rmtree(diagnostics_root)
    has_stale = any(path.exists() for path in stale_paths)
    if args.resume is not None and args.overwrite_run:
        raise ValueError("--resume cannot be combined with --overwrite-run")
    if args.warm_start is not None and has_stale and not args.overwrite_run:
        raise RuntimeError(
            "Existing training outputs detected for warm-start. Use --overwrite-run for a clean run."
        )
    if args.resume is None and args.warm_start is None and has_stale and not args.overwrite_run:
        raise RuntimeError(
            "Existing training outputs detected. Use --resume latest to continue, "
            "or explicitly pass --overwrite-run for a fresh run."
        )
    if args.overwrite_run and args.resume is None:
        for path in (
            production_checkpoint_dir,
            output_root / "best",
            output_root / ".best_export_tmp",
            results_root / "diagnostics",
        ):
            if path.exists():
                shutil.rmtree(path)
        for path in (
            results_root / "training_result.json",
            results_root / "training_manifest.json",
        ):
            path.unlink(missing_ok=True)
        for path in results_root.glob("dev_step_*.json"):
            path.unlink(missing_ok=True)


def validate_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path, Path, Path]:
    data_path = args.data_path.resolve()
    triplet_path = args.triplet_path.resolve()
    triplet_summary_path = args.triplet_summary.resolve()
    initial_model = args.initial_model.resolve()
    output_root = args.output_root.resolve()
    results_root = args.results_root.resolve()
    if not data_path.is_file():
        raise FileNotFoundError(f"Training dataset not found:\n{data_path}")
    if not triplet_path.is_file():
        raise FileNotFoundError(f"Triplet dataset not found:\n{triplet_path}")
    if not triplet_summary_path.is_file():
        raise FileNotFoundError(f"Triplet summary not found:\n{triplet_summary_path}")
    if not args.validate_only and not initial_model.is_dir():
        raise FileNotFoundError(f"Initial model directory not found:\n{initial_model}")
    output_root.mkdir(parents=True, exist_ok=True)
    results_root.mkdir(parents=True, exist_ok=True)
    return data_path, triplet_path, triplet_summary_path, initial_model, output_root, results_root


def configure_cuda_runtime() -> None:
    if not torch.cuda.is_available():
        return
    try:
        torch.backends.cuda.enable_mem_efficient_sdp(False)
        torch.backends.cuda.enable_flash_sdp(True)
        torch.backends.cuda.enable_math_sdp(True)
    except AttributeError:
        pass
    try:
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    except AttributeError:
        pass
    try:
        torch.set_float32_matmul_precision("high")
    except Exception:
        pass


def validate_cuda() -> torch.device:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; MIRA training requires an NVIDIA GPU")
    device = torch.device("cuda")
    props = torch.cuda.get_device_properties(0)
    print(f"GPU:                         {torch.cuda.get_device_name(0)}")
    print(f"VRAM:                        {props.total_memory / (1024**3):.2f} GB")
    print(f"PyTorch:                     {torch.__version__}")
    print(f"CUDA runtime:                {torch.version.cuda}")
    print(f"BF16 supported:              {torch.cuda.is_bf16_supported()}")
    print("Memory-efficient SDP:        disabled")
    print("Flash SDP:                   enabled when supported")
    return device


def select_amp_configuration() -> dict[str, Any]:
    if torch.cuda.is_bf16_supported():
        return {"enabled": True, "dtype": torch.bfloat16, "name": "bf16", "use_scaler": False}
    return {"enabled": True, "dtype": torch.float16, "name": "fp16", "use_scaler": True}


def create_grad_scaler(amp_config: dict[str, Any]) -> Any:
    if not amp_config["use_scaler"]:
        return None
    try:
        return torch.amp.GradScaler("cuda", enabled=True)
    except (AttributeError, TypeError):
        return torch.cuda.amp.GradScaler(enabled=True)


def load_model(initial_model: Path, device: torch.device, gradient_checkpointing: bool) -> SentenceTransformer:
    configure_cuda_runtime()
    print(f"Loading frozen Epoch-1 model: {initial_model}")
    model = SentenceTransformer(str(initial_model), device=str(device))
    model.max_seq_length = MAX_SEQ_LENGTH
    if gradient_checkpointing:
        transformer = model[0].auto_model
        if not hasattr(transformer, "gradient_checkpointing_enable"):
            raise RuntimeError("Underlying transformer does not support gradient checkpointing")
        transformer.gradient_checkpointing_enable()
        if hasattr(transformer, "config"):
            transformer.config.use_cache = False
        print("Gradient checkpointing:       enabled")
    else:
        print("Gradient checkpointing:       disabled")
    return model


def _move_value_to_device(value: Any, device: torch.device) -> Any:
    if isinstance(value, torch.Tensor):
        return value.to(device=device, non_blocking=True)
    if isinstance(value, dict):
        return {key: _move_value_to_device(item, device) for key, item in value.items()}
    if isinstance(value, list):
        return [_move_value_to_device(item, device) for item in value]
    if isinstance(value, tuple):
        return tuple(_move_value_to_device(item, device) for item in value)
    return value


def move_features_to_device(features: Mapping[str, Any], device: torch.device) -> dict[str, Any]:
    if not isinstance(features, Mapping):
        raise TypeError(f"Model preprocessing must return a mapping, got {type(features).__name__}")
    return {key: _move_value_to_device(value, device) for key, value in features.items()}


def prepare_model_inputs(model: SentenceTransformer, texts: list[str]) -> dict[str, Any]:
    if not texts:
        raise ValueError("prepare_model_inputs received an empty text list")
    preprocess = getattr(model, "preprocess", None)
    if callable(preprocess):
        try:
            features = preprocess(texts)
        except TypeError:
            features = None
        if features is not None:
            if not isinstance(features, Mapping):
                raise TypeError(
                    f"SentenceTransformer preprocess returned {type(features).__name__}, expected mapping"
                )
            return dict(features)
    first_module = model[0]
    module_tokenize = getattr(first_module, "tokenize", None)
    if callable(module_tokenize):
        features = module_tokenize(texts)
        if not isinstance(features, Mapping):
            raise TypeError(
                f"Transformer tokenize returned {type(features).__name__}, expected mapping"
            )
        return dict(features)
    tokenize = getattr(model, "tokenize", None)
    if callable(tokenize):
        features = tokenize(texts)
        if not isinstance(features, Mapping):
            raise TypeError(
                f"SentenceTransformer tokenize returned {type(features).__name__}, expected mapping"
            )
        return dict(features)
    raise RuntimeError("SentenceTransformer exposes no supported text preprocessing method")


def encode_batch(
    model: SentenceTransformer,
    texts: list[str],
    device: torch.device,
    amp_config: dict[str, Any],
) -> torch.Tensor:
    if not texts:
        raise ValueError("encode_batch received an empty text list")
    features = prepare_model_inputs(model, texts)
    features = move_features_to_device(features, device)
    with torch.autocast(
        device_type="cuda",
        dtype=amp_config["dtype"],
        enabled=amp_config["enabled"],
    ):
        output = model(features)
    embeddings = output.get("sentence_embedding") if isinstance(output, dict) else None
    if not isinstance(embeddings, torch.Tensor):
        raise RuntimeError("SentenceTransformer did not produce sentence_embedding")
    if embeddings.ndim != 2 or embeddings.shape[0] != len(texts):
        raise RuntimeError(f"Unexpected embedding shape: {tuple(embeddings.shape)}")
    if not torch.isfinite(embeddings.float()).all():
        raise FloatingPointError("Model produced non-finite embeddings")
    return embeddings


def encode_texts_in_chunks(
    model: SentenceTransformer,
    texts: list[str],
    device: torch.device,
    amp_config: dict[str, Any],
    chunk_size: int,
) -> dict[str, torch.Tensor]:
    unique_texts = list(dict.fromkeys(str(text) for text in texts if str(text).strip()))
    if not unique_texts:
        raise ValueError("No non-empty texts supplied for encoding")
    mapping: dict[str, torch.Tensor] = {}
    for start in range(0, len(unique_texts), chunk_size):
        chunk = unique_texts[start : start + chunk_size]
        embeddings = encode_batch(model, chunk, device, amp_config)
        for text, embedding in zip(chunk, embeddings):
            mapping[text] = embedding
    return mapping


def extract_hard_negative_mask(pair_batch: dict[str, Any], device: torch.device) -> torch.Tensor:
    normalized = [normalize_pair_type(value) for value in pair_batch["pair_type"]]
    return torch.tensor(
        [value in ALLOWED_HN_TYPES for value in normalized],
        dtype=torch.bool,
        device=device,
    )


def backward_pair_and_triplet(
    model: SentenceTransformer,
    pair_criterion: MIRAHardNegativeLoss,
    triplet_criterion: MIRATripletHardNegativeLoss,
    pair_batch: dict[str, Any],
    triplet_batch: dict[str, Any],
    device: torch.device,
    amp_config: dict[str, Any],
    pair_loss_weight: float,
    triplet_loss_weight: float,
    pair_scale: float,
    triplet_scale: float,
    scaler: Any,
    encoder_micro_batch_size: int,
) -> tuple[float, float, float]:
    pair_mapping = encode_texts_in_chunks(
        model,
        pair_batch["text_a"] + pair_batch["text_b"],
        device,
        amp_config,
        encoder_micro_batch_size,
    )
    pair_a = torch.stack([pair_mapping[text] for text in pair_batch["text_a"]])
    pair_b = torch.stack([pair_mapping[text] for text in pair_batch["text_b"]])
    labels = pair_batch["label"].to(device=device, non_blocking=True)
    hard_mask = extract_hard_negative_mask(pair_batch, device)
    with torch.autocast(
        device_type="cuda",
        dtype=amp_config["dtype"],
        enabled=amp_config["enabled"],
    ):
        pair_loss = pair_criterion(pair_a, pair_b, labels, hard_mask)
    if not torch.isfinite(pair_loss):
        raise FloatingPointError(f"pair_loss is non-finite: {pair_loss.item()}")
    scaled_pair = pair_loss * pair_loss_weight * pair_scale
    if scaler is not None:
        scaler.scale(scaled_pair).backward()
    else:
        scaled_pair.backward()
    pair_value = float(pair_loss.detach().float().item())
    del pair_mapping, pair_a, pair_b, labels, hard_mask, pair_loss, scaled_pair

    triplet_mapping = encode_texts_in_chunks(
        model,
        triplet_batch["anchor"] + triplet_batch["positive"] + triplet_batch["hard_negative"],
        device,
        amp_config,
        encoder_micro_batch_size,
    )
    triplet_a = torch.stack([triplet_mapping[text] for text in triplet_batch["anchor"]])
    triplet_p = torch.stack([triplet_mapping[text] for text in triplet_batch["positive"]])
    triplet_n = torch.stack([triplet_mapping[text] for text in triplet_batch["hard_negative"]])
    with torch.autocast(
        device_type="cuda",
        dtype=amp_config["dtype"],
        enabled=amp_config["enabled"],
    ):
        triplet_loss = triplet_criterion(triplet_a, triplet_p, triplet_n)
    if not torch.isfinite(triplet_loss):
        raise FloatingPointError(f"triplet_loss is non-finite: {triplet_loss.item()}")
    scaled_triplet = triplet_loss * triplet_loss_weight * triplet_scale
    if scaler is not None:
        scaler.scale(scaled_triplet).backward()
    else:
        scaled_triplet.backward()
    triplet_value = float(triplet_loss.detach().float().item())
    total_value = pair_loss_weight * pair_value + triplet_loss_weight * triplet_value
    del triplet_mapping, triplet_a, triplet_p, triplet_n, triplet_loss, scaled_triplet
    return total_value, pair_value, triplet_value


@torch.inference_mode()
def evaluate_split(model: SentenceTransformer, dataframe: pd.DataFrame, split: str) -> dict[str, Any]:
    frame = dataframe[dataframe["split"] == split].copy()
    if frame.empty:
        raise RuntimeError(f"{split.upper()} split is empty")
    unique_texts = list(
        pd.unique(pd.concat([frame["desc_a"], frame["desc_b"]], ignore_index=True))
    )
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    started = time.perf_counter()
    embeddings = model.encode(
        unique_texts,
        batch_size=EVAL_BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)
    if embeddings.ndim != 2 or embeddings.shape[0] != len(unique_texts) or not np.isfinite(embeddings).all():
        raise RuntimeError("Invalid evaluation embeddings")
    embedding_map = dict(zip(unique_texts, embeddings))
    scores = np.fromiter(
        (
            float(np.dot(embedding_map[row.desc_a], embedding_map[row.desc_b]))
            for row in frame.itertuples(index=False)
        ),
        dtype=np.float32,
        count=len(frame),
    )
    labels = frame["label"].to_numpy(dtype=np.int64)
    threshold_result = find_best_threshold(scores, labels, objective=THRESHOLD_OBJECTIVE)
    hard_mask = frame["pair_type"].map(normalize_pair_type).isin(ALLOWED_HN_TYPES).to_numpy()
    if hard_mask.any():
        fixed_hn = hard_negative_metrics(
            scores[hard_mask], labels[hard_mask], HN_EVALUATION_THRESHOLD
        )
        selected_hn = hard_negative_metrics(
            scores[hard_mask], labels[hard_mask], threshold_result.threshold
        )
    else:
        fixed_hn = {"rows": 0, "status": "NO_HARD_NEGATIVES", "false_high_confidence_rate": None}
        selected_hn = {"rows": 0, "status": "NO_HARD_NEGATIVES", "false_high_confidence_rate": None}
    result = {
        "split": split,
        "rows": int(len(frame)),
        "encoding_seconds": float(time.perf_counter() - started),
        "threshold_selection": {
            "objective": THRESHOLD_OBJECTIVE,
            "threshold": float(threshold_result.threshold),
        },
        "metrics": to_serializable(threshold_result),
        "hard_negative_metrics": {
            "at_085": fixed_hn,
            "at_selected_threshold": selected_hn,
        },
    }
    print(f"{split.upper()} threshold:          {threshold_result.threshold:.3f}")
    print(f"{split.upper()} F1:                 {threshold_result.f1:.4f}")
    print(f"{split.upper()} precision:           {threshold_result.precision:.4f}")
    print(f"{split.upper()} recall:              {threshold_result.recall:.4f}")
    print(
        f"{split.upper()} HN-FHC @ 0.85:       "
        f"{fixed_hn.get('false_high_confidence_rate')}"
    )
    return result


def build_scheduler(optimizer: torch.optim.Optimizer, total_steps: int, warmup_ratio: float) -> LambdaLR:
    total_steps = max(int(total_steps), 1)
    warmup_steps = min(int(round(total_steps * warmup_ratio)), max(total_steps - 1, 0))

    def lr_lambda(current_step: int) -> float:
        if warmup_steps > 0 and current_step < warmup_steps:
            return float(current_step + 1) / float(warmup_steps)
        if total_steps <= warmup_steps + 1:
            return 1.0
        progress = (current_step - warmup_steps) / float(total_steps - warmup_steps)
        progress = min(max(progress, 0.0), 1.0)
        return 0.5 * (1.0 + math.cos(math.pi * progress))

    return LambdaLR(optimizer, lr_lambda)


def candidate_key(dev_f1: float, hn_fhc: float | None) -> tuple[int, float, float]:
    hn = float(hn_fhc) if hn_fhc is not None and np.isfinite(hn_fhc) else 1.0
    if dev_f1 >= TARGET_DEV_F1 and hn <= TARGET_HN_FHC:
        return (3, dev_f1, -hn)
    if dev_f1 >= TARGET_DEV_F1:
        return (2, dev_f1, -hn)
    if dev_f1 >= FALLBACK_DEV_F1_FLOOR:
        return (1, dev_f1, -hn)
    return (0, dev_f1, -hn)


def is_better_candidate(
    dev_f1: float,
    hn_fhc: float | None,
    best_f1: float,
    best_hn: float | None,
) -> bool:
    return candidate_key(dev_f1, hn_fhc) > candidate_key(best_f1, best_hn)


def load_triplet_artifact(
    triplet_path: Path,
    summary_path: Path,
    base_dataframe: pd.DataFrame,
) -> tuple[MiraTripletDataset, pd.DataFrame, dict[str, Any], str]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("validation") != "PASS":
        raise RuntimeError("Triplet build summary is not validated")
    if summary.get("source_mode") != "base_train_all_hard_negatives":
        raise RuntimeError("Triplet artifact was not built from all TRAIN hard negatives")

    train_hn = base_dataframe[
        (base_dataframe["split"] == "train")
        & (base_dataframe["label"] == 0)
        & base_dataframe["pair_type"].isin(ALLOWED_HN_TYPES)
    ].copy()
    source_hn_rows = int(len(train_hn))
    expected_source_hns = int(summary.get("source_hn_rows", -1))
    expected_rows = int(summary.get("triplet_rows", -1))
    expected_unique_hns = int(summary.get("unique_source_hns_used", -1))
    if expected_source_hns != source_hn_rows:
        raise RuntimeError(
            f"Triplet summary source HN count {expected_source_hns} != current TRAIN HN count {source_hn_rows}"
        )
    if expected_rows < MIN_TRIPLET_ROWS or expected_unique_hns < MIN_UNIQUE_TRIPLET_HNS:
        raise RuntimeError(
            f"Triplet artifact failed viability gate: rows={expected_rows}, unique_hns={expected_unique_hns}"
        )
    actual_hash = sha256_file(triplet_path)
    if actual_hash != summary.get("output_sha256"):
        raise RuntimeError("Triplet artifact SHA256 does not match its validated summary")

    triplet_df = pd.read_csv(triplet_path, low_memory=False)
    if len(triplet_df) != expected_rows:
        raise RuntimeError(f"Triplet row count mismatch: summary={expected_rows}, file={len(triplet_df)}")
    required = {
        "triplet_id",
        "source_pair_id",
        "anchor",
        "positive",
        "hard_negative",
        "tmk",
        "hn_type",
        "hard_negative_field",
        "split",
    }
    missing = required - set(triplet_df.columns)
    if missing:
        raise RuntimeError("Triplet artifact missing columns: " + ", ".join(sorted(missing)))

    split = triplet_df["split"].astype(str).str.strip().str.lower()
    if not split.eq("train").all():
        raise RuntimeError("Triplet artifact contains non-TRAIN rows")
    if not triplet_df["hn_type"].isin(ALLOWED_HN_TYPES).all():
        raise RuntimeError("Triplet artifact contains unsupported HN types")
    if triplet_df[["anchor", "positive", "hard_negative"]].isna().any().any():
        raise RuntimeError("Triplet artifact contains missing triplet text")
    if (triplet_df["anchor"].astype(str).str.strip() == "").any():
        raise RuntimeError("Triplet artifact contains empty anchors")
    if (triplet_df["positive"].astype(str).str.strip() == "").any():
        raise RuntimeError("Triplet artifact contains empty positives")
    if (triplet_df["hard_negative"].astype(str).str.strip() == "").any():
        raise RuntimeError("Triplet artifact contains empty hard negatives")
    if int(triplet_df.duplicated(["anchor", "positive", "hard_negative", "tmk", "hn_type"]).sum()) != 0:
        raise RuntimeError("Triplet artifact contains duplicate semantic triplets")
    source_ids = set(triplet_df["source_pair_id"].astype(str).str.strip())
    train_hn_ids = set(train_hn["pair_id"].astype(str).str.strip())
    if not source_ids.issubset(train_hn_ids):
        raise RuntimeError("Triplet artifact references an HN outside current TRAIN")
    actual_unique_hns = int(triplet_df["source_pair_id"].nunique())
    if actual_unique_hns != expected_unique_hns:
        raise RuntimeError(
            f"Triplet unique HN mismatch: summary={expected_unique_hns}, file={actual_unique_hns}"
        )

    records = dataframe_to_triplet_records(triplet_df)
    dataset = MiraTripletDataset(records)
    print(f"Triplet rows:               {len(dataset):,}")
    print(f"Unique source HNs used:     {actual_unique_hns:,}")
    print(f"Available source HNs:       {source_hn_rows:,}")
    print(f"Triplet types:              {triplet_df['hn_type'].value_counts().to_dict()}")
    return dataset, triplet_df, summary, actual_hash


def validate_pair_dataset(dataframe: pd.DataFrame) -> None:
    for split in ("train", "dev", "heldout"):
        if int((dataframe["split"] == split).sum()) == 0:
            raise RuntimeError(f"Missing {split} rows")
    train = dataframe[dataframe["split"] == "train"]
    hns = train[(train["label"] == 0) & train["pair_type"].isin(ALLOWED_HN_TYPES)]
    if hns.empty:
        raise RuntimeError("TRAIN contains no hard negatives")
    print(f"Pair rows:                  {len(dataframe):,}")
    print(f"TRAIN rows:                 {len(train):,}")
    print(f"TRAIN positives:            {(train['label'] == 1).sum():,}")
    print(f"TRAIN negatives:            {(train['label'] == 0).sum():,}")
    print(f"TRAIN hard negatives:       {len(hns):,}")
    print(f"HN types:                   {hns['pair_type'].value_counts().to_dict()}")


def checkpoint_position(metadata: dict[str, Any], batches_per_epoch: int, epochs: int) -> tuple[int, int]:
    extra = metadata.get("extra")
    if not isinstance(extra, dict):
        raise RuntimeError("Checkpoint extra metadata is missing")
    epoch = int(extra.get("resume_epoch", metadata.get("epoch", 0)))
    batch = int(extra.get("resume_batch_index", 0))
    if not 0 <= epoch <= epochs:
        raise RuntimeError(f"Invalid resume epoch {epoch}")
    if epoch == epochs:
        if batch != 0:
            raise RuntimeError("Completed checkpoint must use resume_batch_index=0")
        return epochs, 0
    if not 0 <= batch <= batches_per_epoch:
        raise RuntimeError(f"Invalid resume batch index {batch}")
    if batch == batches_per_epoch:
        return epoch + 1, 0
    return epoch, batch


def next_checkpoint_position(epoch: int, batch_index: int, batches_per_epoch: int) -> tuple[int, int]:
    if not 0 <= batch_index <= batches_per_epoch:
        raise ValueError("batch_index outside current epoch")
    if batch_index == batches_per_epoch:
        return epoch + 1, 0
    return epoch, batch_index


def save_training_checkpoint(
    checkpoint_path: Path,
    model: SentenceTransformer,
    optimizer: torch.optim.Optimizer,
    scheduler: LambdaLR,
    scaler: Any,
    *,
    current_epoch: int,
    resume_epoch: int,
    resume_batch_index: int,
    global_step: int,
    best_dev_f1: float,
    best_hn_fhc: float | None,
    config: dict[str, Any],
    rng_state: dict[str, Any],
    include_optimizer_state: bool = True,
) -> None:
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    save_checkpoint(
        checkpoint_path,
        model=model,
        optimizer=optimizer if include_optimizer_state else None,
        scheduler=scheduler if include_optimizer_state else None,
        scaler=scaler if include_optimizer_state else None,
        epoch=int(current_epoch),
        global_step=int(global_step),
        best_metric=None if not np.isfinite(best_dev_f1) else float(best_dev_f1),
        config=config,
        rng_state=rng_state,
        extra={
            "resume_epoch": int(resume_epoch),
            "resume_batch_index": int(resume_batch_index),
            "best_dev_f1": None if not np.isfinite(best_dev_f1) else float(best_dev_f1),
            "best_hn_fhc_at_085": None if best_hn_fhc is None else float(best_hn_fhc),
        },
    )
    save_checkpoint_metadata(
        checkpoint_path,
        {
            "epoch": int(current_epoch),
            "global_step": int(global_step),
            "resume_epoch": int(resume_epoch),
            "resume_batch_index": int(resume_batch_index),
            "best_dev_f1": None if not np.isfinite(best_dev_f1) else float(best_dev_f1),
            "best_hn_fhc_at_085": None if best_hn_fhc is None else float(best_hn_fhc),
        },
    )


class GracefulStopController:
    def __init__(self) -> None:
        self.requested = threading.Event()
        self._previous_handler = None
        self._installed = False
        self._lock = threading.Lock()
        self._message_printed = False

    def install(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        try:
            self._previous_handler = signal.signal(signal.SIGINT, self._handle_sigint)
            self._installed = True
        except (ValueError, OSError):
            self._installed = False

    def restore(self) -> None:
        if not self._installed:
            return
        try:
            signal.signal(signal.SIGINT, self._previous_handler)
        finally:
            self._installed = False

    def _handle_sigint(self, signum: int, frame: Any) -> None:
        del signum, frame
        with self._lock:
            first_request = not self.requested.is_set()
            self.requested.set()
            if first_request and not self._message_printed:
                print(
                    "\n[signal] Stop requested. Finishing the current optimizer group, then saving a safe checkpoint...",
                    flush=True,
                )
                self._message_printed = True
            elif not first_request:
                print(
                    "[signal] Stop already requested; checkpointing will proceed at the safe boundary.",
                    flush=True,
                )


def load_warm_start(model: SentenceTransformer, checkpoint: Path) -> None:
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    if not isinstance(payload, dict) or not isinstance(payload.get("model_state_dict"), dict):
        raise ValueError("Warm-start checkpoint does not contain model_state_dict")
    model.load_state_dict(payload["model_state_dict"], strict=True)
    print(f"Warm-started from:           {checkpoint}")


def export_best_model(best_checkpoint: Path, initial_model: Path, output_root: Path) -> Path:
    export_dir = output_root / "best"
    temp_dir = output_root / ".best_export_tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    model = SentenceTransformer(str(initial_model), device="cpu")
    model.max_seq_length = MAX_SEQ_LENGTH
    load_checkpoint(
        best_checkpoint,
        model=model,
        map_location="cpu",
        optimizer=None,
        scheduler=None,
        scaler=None,
    )
    model.eval()
    model.save(str(temp_dir))
    if export_dir.exists():
        shutil.rmtree(export_dir)
    os.replace(temp_dir, export_dir)
    del model
    gc.collect()
    print(f"Best model exported to:      {export_dir}")
    return export_dir


def create_training_config(
    args: argparse.Namespace,
    amp_config: dict[str, Any],
    *,
    data_path: Path,
    triplet_path: Path,
    initial_model: Path,
    dataset_hash: str,
    triplet_hash: str,
) -> dict[str, Any]:
    return {
        "trainer_version": TRAINER_VERSION,
        "checkpoint_version": CHECKPOINT_VERSION,
        "model_name": MODEL_NAME,
        "initial_model_dir": str(initial_model),
        "dataset_path": str(data_path),
        "dataset_sha256": dataset_hash,
        "triplet_dataset_path": str(triplet_path),
        "triplet_dataset_sha256": triplet_hash,
        "max_seq_length": MAX_SEQ_LENGTH,
        "run_mode": "full" if args.max_steps is None else "bounded",
        "micro_batch_size": args.batch_size,
        "triplet_batch_size": args.triplet_batch_size,
        "encoder_micro_batch_size": args.encoder_micro_batch_size,
        "gradient_accumulation_steps": args.grad_accumulation,
        "epochs": args.epochs,
        "max_steps": args.max_steps,
        "learning_rate": args.learning_rate,
        "weight_decay": WEIGHT_DECAY,
        "warmup_ratio": WARMUP_RATIO,
        "max_grad_norm": MAX_GRAD_NORM,
        "margin": MARGIN,
        "positive_weight": POSITIVE_WEIGHT,
        "negative_weight": NEGATIVE_WEIGHT,
        "hard_negative_weight": HARD_NEGATIVE_WEIGHT,
        "hard_negative_margin": HARD_NEGATIVE_MARGIN,
        "hard_negative_power": HARD_NEGATIVE_POWER,
        "triplet_margin": TRIPLET_MARGIN,
        "triplet_weight": TRIPLET_WEIGHT,
        "triplet_hard_negative_weight": TRIPLET_HARD_NEGATIVE_WEIGHT,
        "triplet_hard_negative_power": TRIPLET_HARD_NEGATIVE_POWER,
        "pair_loss_weight": args.pair_loss_weight,
        "triplet_loss_weight": args.triplet_loss_weight,
        "threshold_objective": THRESHOLD_OBJECTIVE,
        "hn_evaluation_threshold": HN_EVALUATION_THRESHOLD,
        "target_dev_f1": TARGET_DEV_F1,
        "target_hn_fhc": TARGET_HN_FHC,
        "fallback_dev_f1_floor": FALLBACK_DEV_F1_FLOOR,
        "eval_every_steps": args.eval_every,
        "checkpoint_every_steps": args.checkpoint_every,
        "log_every_steps": args.log_every,
        "heartbeat_seconds": args.heartbeat_seconds,
        "cooldown_ms": args.cooldown_ms,
        "seed": args.seed,
        "deterministic": bool(args.deterministic),
        "gradient_checkpointing": not args.no_gradient_checkpointing,
        "amp": {"enabled": bool(amp_config["enabled"]), "dtype": amp_config["name"]},
    }


RESUME_LOCKED_CONFIG_KEYS = {
    "trainer_version",
    "checkpoint_version",
    "model_name",
    "initial_model_dir",
    "dataset_path",
    "dataset_sha256",
    "triplet_dataset_path",
    "triplet_dataset_sha256",
    "max_seq_length",
    "micro_batch_size",
    "triplet_batch_size",
    "encoder_micro_batch_size",
    "gradient_accumulation_steps",
    "epochs",
    "learning_rate",
    "weight_decay",
    "warmup_ratio",
    "max_grad_norm",
    "margin",
    "positive_weight",
    "negative_weight",
    "hard_negative_weight",
    "hard_negative_margin",
    "hard_negative_power",
    "triplet_margin",
    "triplet_weight",
    "triplet_hard_negative_weight",
    "triplet_hard_negative_power",
    "pair_loss_weight",
    "triplet_loss_weight",
    "threshold_objective",
    "hn_evaluation_threshold",
    "target_dev_f1",
    "target_hn_fhc",
    "fallback_dev_f1_floor",
    "seed",
    "deterministic",
    "gradient_checkpointing",
    "amp",
}

def config_mismatches(current: dict[str, Any], saved: dict[str, Any]) -> list[str]:
    return [
        key
        for key in sorted(RESUME_LOCKED_CONFIG_KEYS)
        if current.get(key) != saved.get(key)
    ]


def run_validation_only(
    dataframe: pd.DataFrame,
    triplet_dataset: MiraTripletDataset,
    triplet_df: pd.DataFrame,
) -> dict[str, Any]:
    validate_pair_dataset(dataframe)
    if len(triplet_dataset) < MIN_TRIPLET_ROWS:
        raise RuntimeError("Triplet artifact is below minimum viability rows")
    result = {
        "status": "validation_only",
        "train_pairs": int((dataframe["split"] == "train").sum()),
        "dev_pairs": int((dataframe["split"] == "dev").sum()),
        "heldout_pairs": int((dataframe["split"] == "heldout").sum()),
        "triplets": int(len(triplet_dataset)),
        "unique_triplet_hns": int(triplet_df["source_pair_id"].nunique()),
    }
    print("VALIDATION ONLY: PASS")
    print(f"TRAIN pairs:                {result['train_pairs']:,}")
    print(f"DEV pairs:                  {result['dev_pairs']:,}")
    print(f"HELD-OUT pairs:             {result['heldout_pairs']:,}")
    print(f"Triplets:                   {result['triplets']:,}")
    print(f"Unique triplet HNs:         {result['unique_triplet_hns']:,}")
    return result


def train(args: argparse.Namespace) -> dict[str, Any]:
    validate_runtime_args(args)
    prepare_output_state(args)
    (
        data_path,
        triplet_path,
        triplet_summary_path,
        initial_model,
        output_root,
        results_root,
    ) = validate_paths(args)

    seed_everything(args.seed, deterministic=args.deterministic)
    configure_cuda_runtime()

    dataframe = load_pairs_dataframe(data_path, require_unique_pair_ids=True)
    validate_pair_dataset(dataframe)
    triplet_dataset, triplet_df, triplet_summary, triplet_hash = load_triplet_artifact(
        triplet_path,
        triplet_summary_path,
        dataframe,
    )
    dataset_hash = sha256_file(data_path)

    if args.validate_only:
        return run_validation_only(dataframe, triplet_dataset, triplet_df)

    device = validate_cuda()
    amp_config = select_amp_configuration()
    train_dataset = create_split_dataset(dataframe, "train")

    pair_batches_per_epoch = math.ceil(len(train_dataset) / args.batch_size)
    optimizer_steps_per_epoch = math.ceil(pair_batches_per_epoch / args.grad_accumulation)
    planned_total_steps = optimizer_steps_per_epoch * args.epochs
    triplet_batches_per_cycle = math.ceil(len(triplet_dataset) / args.triplet_batch_size)
    triplet_rows_drawn_per_epoch = pair_batches_per_epoch * args.triplet_batch_size

    print(f"Micro-batches/epoch:        {pair_batches_per_epoch:,}")
    print(f"Optimizer steps/epoch:      {optimizer_steps_per_epoch:,}")
    print(f"Planned optimizer steps:    {planned_total_steps:,}")
    print(f"Triplet batches/cycle:      {triplet_batches_per_cycle:,}")
    print(f"Triplet rows available:     {len(triplet_dataset):,}")
    print(f"Triplet rows drawn/epoch:   {triplet_rows_drawn_per_epoch:,}")
    print(f"Effective pair examples/step: {args.batch_size * args.grad_accumulation:,}")
    print(f"Effective triplets/step:      {args.triplet_batch_size * args.grad_accumulation:,}")
    print(f"Encoder micro-batch:         {args.encoder_micro_batch_size}")
    print(f"AMP:                         {amp_config['name']}")
    print(f"Cooldown per optimizer step: {args.cooldown_ms} ms")

    model = load_model(initial_model, device, not args.no_gradient_checkpointing)
    model.train()

    pair_criterion = MIRAHardNegativeLoss(
        margin=MARGIN,
        positive_weight=POSITIVE_WEIGHT,
        negative_weight=NEGATIVE_WEIGHT,
        hard_negative_weight=HARD_NEGATIVE_WEIGHT,
        hard_negative_margin=HARD_NEGATIVE_MARGIN,
        hard_negative_power=HARD_NEGATIVE_POWER,
        reduction="mean",
    )
    triplet_criterion = MIRATripletHardNegativeLoss(
        triplet_margin=TRIPLET_MARGIN,
        triplet_weight=TRIPLET_WEIGHT,
        triplet_abs_margin=HN_EVALUATION_THRESHOLD,
        hard_negative_weight=TRIPLET_HARD_NEGATIVE_WEIGHT,
        hard_negative_power=TRIPLET_HARD_NEGATIVE_POWER,
        positive_weight=1.0,
        reduction="mean",
    )
    optimizer = AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=WEIGHT_DECAY,
        betas=(0.9, 0.999),
        eps=1e-8,
    )
    scheduler = build_scheduler(optimizer, planned_total_steps, WARMUP_RATIO)
    scaler = create_grad_scaler(amp_config)

    config = create_training_config(
        args,
        amp_config,
        data_path=data_path,
        triplet_path=triplet_path,
        initial_model=initial_model,
        dataset_hash=dataset_hash,
        triplet_hash=triplet_hash,
    )

    results_root.mkdir(parents=True, exist_ok=True)
    diagnostic_mode = args.smoke_test or args.max_steps is not None
    run_root = results_root / "diagnostics" if diagnostic_mode else output_root
    checkpoint_dir = run_root / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    latest_checkpoint = checkpoint_dir / "latest.pt"
    best_checkpoint = checkpoint_dir / "best.pt"
    smoke_latest = latest_checkpoint

    pair_planners: dict[int, EpochBatchPlanner] = {}
    triplet_planner = CyclingTripletPlanner(
        triplet_dataset,
        args.triplet_batch_size,
        args.seed,
    )

    start_epoch = 0
    start_batch_index = 0
    global_step = 0
    best_dev_f1 = -float("inf")
    best_hn_fhc: float | None = None
    best_checkpoint_created = best_checkpoint.is_file()
    warm_started = False

    if args.warm_start is not None:
        if diagnostic_mode:
            raise RuntimeError("--warm-start is only supported for a full training run")
        warm_start_path = args.warm_start.resolve()
        if not warm_start_path.is_file():
            raise FileNotFoundError(f"Warm-start checkpoint not found:\n{warm_start_path}")
        load_warm_start(model, warm_start_path)
        warm_started = True
        model.eval()
        initial_dev = evaluate_split(model, dataframe, "dev")
        model.train()
        best_dev_f1 = float(initial_dev["metrics"]["f1"])
        initial_hn = initial_dev["hard_negative_metrics"]["at_085"].get(
            "false_high_confidence_rate"
        )
        best_hn_fhc = float(initial_hn) if initial_hn is not None else None
        save_training_checkpoint(
            best_checkpoint,
            model,
            optimizer,
            scheduler,
            scaler,
            current_epoch=0,
            resume_epoch=0,
            resume_batch_index=0,
            global_step=0,
            best_dev_f1=best_dev_f1,
            best_hn_fhc=best_hn_fhc,
            config=config,
            rng_state=get_rng_state(),
            include_optimizer_state=False,
        )
        best_checkpoint_created = True
        atomic_json_write(
            results_root / "dev_step_0.json",
            {
                "global_step": 0,
                "epoch": 0,
                "dev": initial_dev,
                "best_dev_f1": best_dev_f1,
                "best_hn_fhc_at_085": best_hn_fhc,
                "source": "warm_start_baseline",
            },
        )
    elif args.resume is not None:
        resume_path = latest_checkpoint if args.resume == "latest" else Path(args.resume).resolve()
        if not resume_path.is_file():
            raise FileNotFoundError(f"Resume checkpoint not found:\n{resume_path}")
        metadata = load_checkpoint(
            resume_path,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=scaler,
            map_location=device,
        )
        if metadata.get("checkpoint_version") != CHECKPOINT_VERSION:
            raise RuntimeError("Checkpoint version mismatch")
        saved_config = metadata.get("config", {})
        mismatches = config_mismatches(config, saved_config if isinstance(saved_config, dict) else {})
        if mismatches:
            raise RuntimeError("Resume configuration mismatch: " + ", ".join(mismatches))
        saved_run_mode = saved_config.get("run_mode") if isinstance(saved_config, dict) else None
        current_run_mode = "full" if args.max_steps is None else "bounded"
        if saved_run_mode == "bounded" and current_run_mode == "full":
            raise RuntimeError(
                "A bounded/diagnostic checkpoint cannot be resumed as a full training run. "
                "Start a fresh full run instead."
            )
        start_epoch, start_batch_index = checkpoint_position(
            metadata,
            pair_batches_per_epoch,
            args.epochs,
        )
        global_step = int(metadata.get("global_step", 0))
        if global_step < 0 or global_step > planned_total_steps:
            raise RuntimeError(
                f"Checkpoint global_step={global_step} is outside planned range 0..{planned_total_steps}"
            )
        best_metric = metadata.get("best_metric")
        best_dev_f1 = float(best_metric) if best_metric is not None else -float("inf")
        extra = metadata.get("extra", {})
        if isinstance(extra, dict) and extra.get("best_hn_fhc_at_085") is not None:
            best_hn_fhc = float(extra["best_hn_fhc_at_085"])
        rng_state = metadata.get("rng_state")
        if rng_state is not None:
            restore_rng_state(rng_state)
        best_checkpoint_created = best_checkpoint.is_file()
        if not best_checkpoint_created and not diagnostic_mode:
            raise RuntimeError(
                "Resume checkpoint found but best.pt is missing. Refusing to finish without a valid best-model reference."
            )
        print(f"Resumed optimizer step:    {global_step:,}")
        print(f"Resumed epoch/batch:        {start_epoch}/{start_batch_index}")
    else:
        if not diagnostic_mode:
            model.eval()
            initial_dev = evaluate_split(model, dataframe, "dev")
            model.train()
            best_dev_f1 = float(initial_dev["metrics"]["f1"])
            initial_hn = initial_dev["hard_negative_metrics"]["at_085"].get(
                "false_high_confidence_rate"
            )
            best_hn_fhc = float(initial_hn) if initial_hn is not None else None

    max_steps = args.max_steps
    if args.smoke_test:
        max_steps = min(
            args.max_steps if args.max_steps is not None else DEFAULT_SMOKE_STEPS,
            planned_total_steps,
        )
        smoke_latest.parent.mkdir(parents=True, exist_ok=True)

    training_manifest = {
        "status": "started",
        "trainer_version": TRAINER_VERSION,
        "config": config,
        "dataset": {
            "path": str(data_path),
            "sha256": dataset_hash,
            "rows": int(len(dataframe)),
        },
        "triplets": {
            "path": str(triplet_path),
            "sha256": triplet_hash,
            "rows": int(len(triplet_dataset)),
            "unique_source_hns": int(triplet_df["source_pair_id"].nunique()),
            "available_source_hns": int(triplet_summary["source_hn_rows"]),
        },
        "environment": {
            "python": sys.version,
            "pytorch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "amp": amp_config["name"],
        },
    }
    run_manifest_path = results_root / "diagnostics" / "training_manifest.json" if diagnostic_mode else results_root / "training_manifest.json"
    atomic_json_write(run_manifest_path, training_manifest)

    if (
        not diagnostic_mode
        and best_dev_f1 > -float("inf")
        and not args.resume
        and not warm_started
    ):
        save_training_checkpoint(
            best_checkpoint,
            model,
            optimizer,
            scheduler,
            scaler,
            current_epoch=0,
            resume_epoch=0,
            resume_batch_index=0,
            global_step=0,
            best_dev_f1=best_dev_f1,
            best_hn_fhc=best_hn_fhc,
            config=config,
            rng_state=get_rng_state(),
            include_optimizer_state=False,
        )
        best_checkpoint_created = True
        atomic_json_write(
            results_root / "dev_step_0.json",
            {
                "global_step": 0,
                "epoch": 0,
                "dev": initial_dev,
                "best_dev_f1": best_dev_f1,
                "best_hn_fhc_at_085": best_hn_fhc,
                "source": "warm_start_baseline" if warm_started else "frozen_epoch1_baseline",
            },
        )

    heartbeat = TrainingHeartbeat(args.heartbeat_seconds)
    heartbeat.start()
    stop_controller = GracefulStopController()
    stop_controller.install()

    interrupted = False
    safe_resume_epoch = start_epoch
    safe_resume_batch = start_batch_index
    safe_rng_state = get_rng_state()
    if args.resume is not None:
        safe_rng_state = get_rng_state()

    run_start = time.perf_counter()
    last_log_time = run_start
    running_total = 0.0
    running_pair = 0.0
    running_triplet = 0.0
    running_micro = 0
    consecutive_overflows = 0
    stop_checkpoint_saved = False

    try:
        for epoch in range(start_epoch, args.epochs):
            planner = pair_planners.setdefault(
                epoch,
                EpochBatchPlanner(
                    train_dataset,
                    args.batch_size,
                    args.seed,
                    PAIR_SEED_OFFSET + epoch * CYCLE_SEED_STRIDE,
                ),
            )
            batch_index = start_batch_index if epoch == start_epoch else 0

            while batch_index < pair_batches_per_epoch:
                if max_steps is not None and global_step >= max_steps:
                    break
                if stop_controller.requested.is_set():
                    break

                group_size = min(args.grad_accumulation, pair_batches_per_epoch - batch_index)
                group_start_batch = batch_index
                group_rng_state = get_rng_state()
                pair_batches: list[dict[str, Any]] = []
                triplet_batches: list[dict[str, Any]] = []
                total_pair_examples = 0
                total_triplet_examples = 0

                for offset in range(group_size):
                    current_batch = batch_index + offset
                    pair_batch = collate_pairs(planner.get(current_batch))
                    triplet_global_batch = epoch * pair_batches_per_epoch + current_batch
                    triplet_batch = collate_triplets(triplet_planner.get(triplet_global_batch))
                    pair_batches.append(pair_batch)
                    triplet_batches.append(triplet_batch)
                    total_pair_examples += len(pair_batch["text_a"])
                    total_triplet_examples += len(triplet_batch["anchor"])

                optimizer.zero_grad(set_to_none=True)
                heartbeat.update(
                    phase="backward",
                    epoch=epoch,
                    optimizer_step=global_step,
                    target_step=global_step + 1,
                    batch_index=group_start_batch,
                    total_batches=pair_batches_per_epoch,
                )
                group_start_time = time.perf_counter()
                group_total = 0.0
                group_pair = 0.0
                group_triplet = 0.0

                try:
                    for pair_batch, triplet_batch in zip(pair_batches, triplet_batches):
                        pair_scale = len(pair_batch["text_a"]) / float(total_pair_examples)
                        triplet_scale = len(triplet_batch["anchor"]) / float(total_triplet_examples)
                        total_value, pair_value, triplet_value = backward_pair_and_triplet(
                            model,
                            pair_criterion,
                            triplet_criterion,
                            pair_batch,
                            triplet_batch,
                            device,
                            amp_config,
                            args.pair_loss_weight,
                            args.triplet_loss_weight,
                            pair_scale,
                            triplet_scale,
                            scaler,
                            args.encoder_micro_batch_size,
                        )
                        group_total += total_value
                        group_pair += pair_value
                        group_triplet += triplet_value
                        running_micro += 1

                    if scaler is not None:
                        scaler.unscale_(optimizer)
                    grad_norm = torch.nn.utils.clip_grad_norm_(
                        model.parameters(),
                        MAX_GRAD_NORM,
                    )
                    if not torch.isfinite(torch.as_tensor(grad_norm, device=device)).all():
                        raise FloatingPointError("Non-finite gradient norm detected")

                    optimizer_step_applied = True
                    old_scale = scaler.get_scale() if scaler is not None else None
                    if scaler is not None:
                        scaler.step(optimizer)
                        scaler.update()
                        optimizer_step_applied = scaler.get_scale() >= old_scale
                    else:
                        optimizer.step()

                    optimizer.zero_grad(set_to_none=True)

                    if not optimizer_step_applied:
                        consecutive_overflows += 1
                        restore_rng_state(group_rng_state)
                        if consecutive_overflows > MAX_CONSECUTIVE_FP16_OVERFLOWS:
                            raise RuntimeError(
                                f"Exceeded {MAX_CONSECUTIVE_FP16_OVERFLOWS} consecutive FP16 overflows"
                            )
                        print(
                            f"[amp] optimizer step skipped due to overflow; retrying "
                            f"batch group {group_start_batch:,}:{group_start_batch + group_size:,} "
                            f"scale={scaler.get_scale():.1f}",
                            flush=True,
                        )
                        continue

                    consecutive_overflows = 0
                    scheduler.step()
                    global_step += 1
                    batch_index += group_size
                    safe_resume_epoch, safe_resume_batch = next_checkpoint_position(
                        epoch,
                        batch_index,
                        pair_batches_per_epoch,
                    )
                    safe_rng_state = get_rng_state()

                    running_total += group_total / float(group_size)
                    running_pair += group_pair / float(group_size)
                    running_triplet += group_triplet / float(group_size)

                    if args.cooldown_ms > 0:
                        time.sleep(args.cooldown_ms / 1000.0)

                    if global_step == 1 or global_step % args.log_every == 0:
                        if torch.cuda.is_available():
                            torch.cuda.synchronize(device)
                        elapsed = time.perf_counter() - last_log_time
                        allocated = (
                            torch.cuda.memory_allocated(0) / (1024**3)
                            if torch.cuda.is_available()
                            else 0.0
                        )
                        reserved = (
                            torch.cuda.memory_reserved(0) / (1024**3)
                            if torch.cuda.is_available()
                            else 0.0
                        )
                        avg_total = running_total / max(args.log_every if global_step > args.log_every else global_step, 1)
                        avg_pair = running_pair / max(args.log_every if global_step > args.log_every else global_step, 1)
                        avg_triplet = running_triplet / max(args.log_every if global_step > args.log_every else global_step, 1)
                        print(
                            f"step={global_step:,} "
                            f"total={avg_total:.6f} "
                            f"pair={avg_pair:.6f} "
                            f"triplet={avg_triplet:.6f} "
                            f"lr={optimizer.param_groups[0]['lr']:.3e} "
                            f"grad_norm={float(grad_norm):.4f} "
                            f"GPU_alloc={allocated:.2f}GB "
                            f"GPU_reserved={reserved:.2f}GB "
                            f"dt={elapsed:.1f}s "
                            f"batch={batch_index:,}/{pair_batches_per_epoch:,}",
                            flush=True,
                        )
                        running_total = 0.0
                        running_pair = 0.0
                        running_triplet = 0.0
                        last_log_time = time.perf_counter()

                    stop_requested = stop_controller.requested.is_set()
                    checkpoint_due = global_step % args.checkpoint_every == 0
                    if stop_requested:
                        checkpoint_due = True
                    if max_steps is not None and global_step >= max_steps:
                        checkpoint_due = True
                    if checkpoint_due and not args.smoke_test:
                        heartbeat.update(phase="checkpoint", optimizer_step=global_step, batch_index=batch_index)
                        save_training_checkpoint(
                            latest_checkpoint,
                            model,
                            optimizer,
                            scheduler,
                            scaler,
                            current_epoch=epoch,
                            resume_epoch=safe_resume_epoch,
                            resume_batch_index=safe_resume_batch,
                            global_step=global_step,
                            best_dev_f1=best_dev_f1,
                            best_hn_fhc=best_hn_fhc,
                            config=config,
                            rng_state=safe_rng_state,
                        )
                        heartbeat.update(phase="backward", optimizer_step=global_step, batch_index=batch_index)
                        if stop_controller.requested.is_set():
                            stop_checkpoint_saved = True

                    stop_requested = stop_controller.requested.is_set()
                    if (
                        not diagnostic_mode
                        and not stop_requested
                        and global_step > 0
                        and global_step % args.eval_every == 0
                    ):
                        heartbeat.update(phase="evaluation", optimizer_step=global_step, batch_index=batch_index)
                        if torch.cuda.is_available():
                            torch.cuda.synchronize(device)
                        model.eval()
                        dev_result = evaluate_split(model, dataframe, "dev")
                        dev_f1 = float(dev_result["metrics"]["f1"])
                        hn_value_raw = dev_result["hard_negative_metrics"]["at_085"].get(
                            "false_high_confidence_rate"
                        )
                        hn_value = float(hn_value_raw) if hn_value_raw is not None else None
                        improved = is_better_candidate(
                            dev_f1,
                            hn_value,
                            best_dev_f1,
                            best_hn_fhc,
                        )
                        if improved:
                            best_dev_f1 = dev_f1
                            best_hn_fhc = hn_value
                            save_training_checkpoint(
                                best_checkpoint,
                                model,
                                optimizer,
                                scheduler,
                                scaler,
                                current_epoch=epoch,
                                resume_epoch=safe_resume_epoch,
                                resume_batch_index=safe_resume_batch,
                                global_step=global_step,
                                best_dev_f1=best_dev_f1,
                                best_hn_fhc=best_hn_fhc,
                                config=config,
                                rng_state=safe_rng_state,
                                include_optimizer_state=False,
                            )
                            best_checkpoint_created = True
                            print(
                                f"NEW BEST DEV candidate: F1={best_dev_f1:.4f} "
                                f"HN-FHC@0.85={best_hn_fhc}",
                                flush=True,
                            )
                        atomic_json_write(
                            results_root / f"dev_step_{global_step}.json",
                            {
                                "global_step": global_step,
                                "epoch": epoch,
                                "dev": dev_result,
                                "candidate_key": candidate_key(dev_f1, hn_value),
                                "best_dev_f1": None if not np.isfinite(best_dev_f1) else float(best_dev_f1),
                                "best_hn_fhc_at_085": best_hn_fhc,
                                "improved": bool(improved),
                            },
                        )
                        model.train()
                        heartbeat.update(phase="backward", optimizer_step=global_step, batch_index=batch_index)

                    if max_steps is not None and global_step >= max_steps:
                        break

                except Exception:
                    optimizer.zero_grad(set_to_none=True)
                    raise

            if stop_controller.requested.is_set():
                interrupted = True
                break
            start_batch_index = 0
            if max_steps is not None and global_step >= max_steps:
                break

    except KeyboardInterrupt:
        interrupted = True
        stop_controller.requested.set()
        optimizer.zero_grad(set_to_none=True)
        heartbeat.update(phase="interrupt-checkpoint")
        if not diagnostic_mode:
            print("TRAINING INTERRUPTED BY USER; saving safe checkpoint...", flush=True)
            save_training_checkpoint(
                latest_checkpoint,
                model,
                optimizer,
                scheduler,
                scaler,
                current_epoch=max(safe_resume_epoch - 1, 0),
                resume_epoch=safe_resume_epoch,
                resume_batch_index=safe_resume_batch,
                global_step=global_step,
                best_dev_f1=best_dev_f1,
                best_hn_fhc=best_hn_fhc,
                config=config,
                rng_state=safe_rng_state,
            )
            print(f"Checkpoint saved:           {latest_checkpoint}", flush=True)
            print("Resume with: --resume latest", flush=True)
            stop_checkpoint_saved = True
    finally:
        stop_controller.restore()
        heartbeat.stop()
        optimizer.zero_grad(set_to_none=True)
        if torch.cuda.is_available():
            torch.cuda.synchronize(device)
            torch.cuda.empty_cache()
        gc.collect()

    if stop_controller.requested.is_set() and not stop_checkpoint_saved and not diagnostic_mode:
        interrupted = True
        heartbeat.update(phase="interrupt-checkpoint")
        save_training_checkpoint(
            latest_checkpoint,
            model,
            optimizer,
            scheduler,
            scaler,
            current_epoch=max(safe_resume_epoch - 1, 0),
            resume_epoch=safe_resume_epoch,
            resume_batch_index=safe_resume_batch,
            global_step=global_step,
            best_dev_f1=best_dev_f1,
            best_hn_fhc=best_hn_fhc,
            config=config,
            rng_state=safe_rng_state,
        )
        stop_checkpoint_saved = True

    if stop_controller.requested.is_set() and not interrupted:
        interrupted = True

    bounded_run_completed = (
        not interrupted
        and max_steps is not None
        and global_step >= max_steps
    )
    full_training_completed = (
        not interrupted
        and max_steps is None
        and safe_resume_epoch >= args.epochs
    )
    training_finished = bounded_run_completed or full_training_completed

    if not args.smoke_test and training_finished:
        save_training_checkpoint(
            latest_checkpoint,
            model,
            optimizer,
            scheduler,
            scaler,
            current_epoch=max(safe_resume_epoch - 1, 0),
            resume_epoch=safe_resume_epoch,
            resume_batch_index=safe_resume_batch,
            global_step=global_step,
            best_dev_f1=best_dev_f1,
            best_hn_fhc=best_hn_fhc,
            config=config,
            rng_state=safe_rng_state,
        )

    best_model_dir = None
    heldout_result = None
    if (
        full_training_completed
        and best_checkpoint_created
        and best_checkpoint.is_file()
    ):
        heartbeat = TrainingHeartbeat(0)
        best_model_dir = export_best_model(best_checkpoint, initial_model, output_root)
        load_checkpoint(
            best_checkpoint,
            model=model,
            map_location=device,
            optimizer=None,
            scheduler=None,
            scaler=None,
        )
        model.to(device)
        model.eval()
        heldout_result = evaluate_split(model, dataframe, "heldout")
        model.train()

    total_seconds = time.perf_counter() - run_start
    status = (
        "interrupted"
        if interrupted
        else "smoke_test_complete"
        if args.smoke_test
        else "completed"
        if full_training_completed
        else "step_limit_reached"
        if max_steps is not None and training_finished
        else "incomplete"
    )
    result = {
        "status": status,
        "completed": bool(full_training_completed),
        "trainer_version": TRAINER_VERSION,
        "model_name": MODEL_NAME,
        "dataset": {
            "path": str(data_path),
            "sha256": dataset_hash,
            "rows": int(len(dataframe)),
            "train_rows": int((dataframe["split"] == "train").sum()),
            "dev_rows": int((dataframe["split"] == "dev").sum()),
            "heldout_rows": int((dataframe["split"] == "heldout").sum()),
        },
        "triplets": {
            "path": str(triplet_path),
            "sha256": triplet_hash,
            "rows": int(len(triplet_dataset)),
            "unique_source_hns": int(triplet_df["source_pair_id"].nunique()),
            "available_source_hns": int(triplet_summary["source_hn_rows"]),
            "pairwise_only_hns": int(triplet_summary["source_hn_rows"] - triplet_df["source_pair_id"].nunique()),
            "batches_per_cycle": int(triplet_batches_per_cycle),
            "rows_drawn_per_epoch": int(triplet_rows_drawn_per_epoch),
        },
        "training": {
            "epochs_requested": args.epochs,
            "global_steps_completed": int(global_step),
            "micro_batch_size": args.batch_size,
            "triplet_batch_size": args.triplet_batch_size,
            "encoder_micro_batch_size": args.encoder_micro_batch_size,
            "gradient_accumulation": args.grad_accumulation,
            "learning_rate": args.learning_rate,
            "pair_loss_weight": args.pair_loss_weight,
            "triplet_loss_weight": args.triplet_loss_weight,
            "target_dev_f1": TARGET_DEV_F1,
            "target_hn_fhc_at_085": TARGET_HN_FHC,
            "best_dev_f1": None if not np.isfinite(best_dev_f1) else float(best_dev_f1),
            "best_hn_fhc_at_085": best_hn_fhc,
            "warm_started": warm_started,
            "deterministic": bool(args.deterministic),
            "cooldown_ms": args.cooldown_ms,
            "stop_requested": bool(stop_controller.requested.is_set()),
        },
        "environment": {
            "python": sys.version,
            "pytorch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "amp": amp_config["name"],
        },
        "checkpoint": {
            "latest": str(latest_checkpoint),
            "best": str(best_checkpoint) if best_checkpoint.is_file() else None,
            "best_model_dir": str(best_model_dir) if best_model_dir else None,
        },
        "final_heldout": heldout_result,
        "runtime": {
            "seconds": float(total_seconds),
            "minutes": float(total_seconds / 60.0),
            "hours": float(total_seconds / 3600.0),
        },
    }

    if args.smoke_test:
        atomic_json_write(results_root / "diagnostics" / "smoke_result.json", result)
    else:
        result_path = results_root / "diagnostics" / "training_result.json" if diagnostic_mode else results_root / "training_result.json"
        manifest_path = results_root / "diagnostics" / "training_manifest.json" if diagnostic_mode else results_root / "training_manifest.json"
        atomic_json_write(result_path, result)
        atomic_json_write(
            manifest_path,
            {
                "status": status,
                "trainer_version": TRAINER_VERSION,
                "global_step": global_step,
                "safe_resume_epoch": safe_resume_epoch,
                "safe_resume_batch_index": safe_resume_batch,
                "best_dev_f1": result["training"]["best_dev_f1"],
                "best_hn_fhc_at_085": best_hn_fhc,
                "final_heldout": heldout_result,
                "runtime": result["runtime"],
                "config": config,
            },
        )

    print("=" * 82)
    print("MIRA EPOCH-2 TRAINING FINISHED")
    print("=" * 82)
    print(f"Status:                      {status}")
    print(f"Optimizer steps:             {global_step:,}")
    print(f"Best DEV F1:                 {result['training']['best_dev_f1']}")
    print(f"Best HN-FHC @ 0.85:          {result['training']['best_hn_fhc_at_085']}")
    if heldout_result is not None:
        print(f"Best HELD-OUT F1:            {heldout_result['metrics']['f1']:.4f}")
        print(
            "Best HELD-OUT HN-FHC @ 0.85: "
            f"{heldout_result['hard_negative_metrics']['at_085'].get('false_high_confidence_rate')}"
        )
    print(f"Runtime hours:               {total_seconds / 3600.0:.2f}")
    print("=" * 82)
    return result


def main() -> None:
    train(parse_args())


if __name__ == "__main__":
    main()
