from __future__ import annotations

import argparse
import dataclasses
import gc
import json
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

LOGGER = logging.getLogger("quantize_model")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE_MODEL = BASE_DIR / "qwen_models" / "epoch2_finetuned" / "best"
DEFAULT_OUTPUT_MODEL = BASE_DIR / "qwen_models" / "qwen_quantized"

EMBEDDING_MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
EXPECTED_EMBEDDING_DIM = 1024
DEFAULT_SOURCE_STEP = 13678

DEFAULT_SAMPLE_TEXTS: tuple[str, ...] = (
    "stainless steel bolt",
    "bearing 6205 2RS",
    "carbon steel pipe 100 NB",
)

RECOMMENDED_MIN_COMPUTE_CAPABILITY = (7, 5)


class QuantizationError(RuntimeError):
    """Raised for any unrecoverable failure in the quantization pipeline."""


@dataclasses.dataclass(frozen=True)
class PipelineConfig:
    """Fully resolved configuration for a single quantization run."""

    source_model: Path
    output_model: Path
    int8_threshold: float
    embedding_dim: int
    sample_texts: tuple[str, ...]
    min_cosine_similarity: float
    reload_similarity_tolerance: float
    force: bool
    skip_baseline_comparison: bool
    device: str
    seed: int


@dataclasses.dataclass
class EncodeResult:
    """Container for an embedding batch plus a human-readable label."""

    label: str
    embeddings: np.ndarray


def parse_args(argv: Sequence[str] | None = None) -> PipelineConfig:
    """Parse and validate CLI arguments into a :class:`PipelineConfig`."""

    parser = argparse.ArgumentParser(
        description="Quantize a SentenceTransformer checkpoint to INT8 "
        "using bitsandbytes LLM.int8().",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_MODEL,
        help="Path to the full-precision source SentenceTransformer model.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_MODEL,
        help="Directory the quantized model will be written to.",
    )
    parser.add_argument(
        "--int8-threshold",
        type=float,
        default=6.0,
        help="Outlier threshold for bitsandbytes LLM.int8() decomposition.",
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=EXPECTED_EMBEDDING_DIM,
        help="Expected embedding dimensionality of the model.",
    )
    parser.add_argument(
        "--min-cosine-similarity",
        type=float,
        default=0.97,
        help="Minimum acceptable mean cosine similarity between the "
        "original and quantized embeddings (quality gate).",
    )
    parser.add_argument(
        "--reload-similarity-tolerance",
        type=float,
        default=1e-3,
        help="Maximum acceptable mean cosine distance (1 - similarity) "
        "between pre-save and post-reload embeddings. Anything above "
        "this indicates the saved checkpoint is not faithful.",
    )
    parser.add_argument(
        "--skip-baseline-comparison",
        action="store_true",
        help="Skip loading the full-precision model to compute a fidelity "
        "comparison. Speeds up the run but disables the quality gate.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove and recreate the output directory if it already "
        "exists and is non-empty.",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        help="CUDA device to load models onto.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    parser.add_argument(
        "--sample-texts-file",
        type=Path,
        default=None,
        help="Optional path to a UTF-8 text file with one sample text per "
        "line, used for validation instead of the built-in defaults.",
    )

    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    sample_texts = DEFAULT_SAMPLE_TEXTS
    if args.sample_texts_file is not None:
        sample_texts = load_sample_texts(args.sample_texts_file)

    if args.int8_threshold <= 0:
        parser.error("--int8-threshold must be a positive number.")
    if not 0.0 <= args.min_cosine_similarity <= 1.0:
        parser.error("--min-cosine-similarity must be within [0, 1].")
    if args.embedding_dim <= 0:
        parser.error("--embedding-dim must be a positive integer.")

    return PipelineConfig(
        source_model=args.source.resolve(),
        output_model=args.output.resolve(),
        int8_threshold=args.int8_threshold,
        embedding_dim=args.embedding_dim,
        sample_texts=tuple(sample_texts),
        min_cosine_similarity=args.min_cosine_similarity,
        reload_similarity_tolerance=args.reload_similarity_tolerance,
        force=args.force,
        skip_baseline_comparison=args.skip_baseline_comparison,
        device=args.device,
        seed=args.seed,
    )


def configure_logging(level: str) -> None:
    """Configure root logging with a single, consistent format."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )


def load_sample_texts(path: Path) -> list[str]:
    """Load newline-delimited validation texts from ``path``."""

    if not path.is_file():
        raise QuantizationError(f"Sample texts file not found: {path}")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    texts = [line for line in lines if line]
    if not texts:
        raise QuantizationError(f"Sample texts file is empty: {path}")
    return texts


def get_directory_size_bytes(path: Path) -> int:
    """Recursively compute the total size in bytes of files under ``path``."""

    if not path.exists():
        raise QuantizationError(f"Path does not exist: {path}")
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError as exc:
            LOGGER.warning("Skipping unreadable path %s (%s)", entry, exc)
    return total


def human_readable_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable string (GiB granularity)."""

    return f"{num_bytes / (1024 ** 3):.2f} GiB"


def ensure_source_model_ready(source: Path) -> None:
    """Validate that the source model directory exists and is non-empty."""

    if not source.exists():
        raise QuantizationError(f"Source model directory not found: {source}")
    if not source.is_dir():
        raise QuantizationError(f"Source model path is not a directory: {source}")
    if not any(source.iterdir()):
        raise QuantizationError(f"Source model directory is empty: {source}")


def ensure_output_dir_ready(output: Path, force: bool) -> None:
    """Prepare an empty output directory, honoring ``--force`` semantics."""

    if output.exists():
        if any(output.rglob("*")):
            if not force:
                raise QuantizationError(
                    f"Output directory is not empty: {output} "
                    "(pass --force to overwrite it)."
                )
            LOGGER.warning("Removing existing non-empty output directory: %s", output)
            shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)


def check_cuda_available(device: str) -> "torch.device":  # noqa: F821 - see import below
    """Verify CUDA is available and return the resolved torch device."""

    import torch

    if device.startswith("cuda") and not torch.cuda.is_available():
        raise QuantizationError(
            "CUDA is not available, but a CUDA device was requested. "
            "INT8 quantization via bitsandbytes requires a GPU."
        )
    resolved = torch.device(device)
    if resolved.type == "cuda":
        index = resolved.index or 0
        name = torch.cuda.get_device_name(index)
        capability = torch.cuda.get_device_capability(index)
        LOGGER.info("GPU: %s (compute capability %s)", name, capability)
        LOGGER.info("CUDA runtime: %s", torch.version.cuda)
        if capability < RECOMMENDED_MIN_COMPUTE_CAPABILITY:
            LOGGER.warning(
                "GPU compute capability %s is below the recommended minimum "
                "%s for bitsandbytes LLM.int8(); quantization may be slower "
                "or less numerically stable.",
                capability,
                RECOMMENDED_MIN_COMPUTE_CAPABILITY,
            )
    return resolved


def build_quantization_config(threshold: float) -> "BitsAndBytesConfig":  # noqa: F821
    """Build the bitsandbytes INT8 quantization configuration."""

    from transformers import BitsAndBytesConfig

    return BitsAndBytesConfig(
        load_in_8bit=True,
        llm_int8_threshold=threshold,
    )


def load_sentence_transformer(
    model_path: Path,
    device: "torch.device",  # noqa: F821
    quantization_config: "BitsAndBytesConfig | None" = None,  # noqa: F821
) -> "SentenceTransformer":  # noqa: F821
    """Load a SentenceTransformer, optionally with bitsandbytes quantization."""

    from sentence_transformers import SentenceTransformer

    model_kwargs: dict = {}
    if quantization_config is not None:
        model_kwargs["quantization_config"] = quantization_config
        model_kwargs["device_map"] = {"": device.index or 0} if device.type == "cuda" else "auto"

    try:
        if quantization_config is not None:
            model = SentenceTransformer(str(model_path), model_kwargs=model_kwargs)
        else:
            model = SentenceTransformer(str(model_path), device=str(device))
    except Exception as exc:  # noqa: BLE001 - re-raise as a domain error with context
        raise QuantizationError(f"Failed to load model from {model_path}: {exc}") from exc

    model.eval()
    return model


def count_int8_linear_layers(model: "SentenceTransformer") -> int:  # noqa: F821
    """Count bitsandbytes Linear8bitLt modules inside ``model``."""

    import bitsandbytes as bnb

    return sum(isinstance(module, bnb.nn.Linear8bitLt) for module in model.modules())


def encode_texts(
    model: "SentenceTransformer",  # noqa: F821
    texts: Sequence[str],
    label: str,
) -> EncodeResult:
    """Encode ``texts`` into normalized embeddings, wrapped with a label."""

    import torch

    with torch.inference_mode():
        embeddings = model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    return EncodeResult(label=label, embeddings=np.asarray(embeddings, dtype=np.float32))


def validate_embedding_shape(result: EncodeResult, expected_rows: int, expected_dim: int) -> None:
    """Raise :class:`QuantizationError` if ``result`` has an unexpected shape."""

    expected = (expected_rows, expected_dim)
    if result.embeddings.shape != expected:
        raise QuantizationError(
            f"[{result.label}] Unexpected embedding shape: "
            f"{result.embeddings.shape}, expected {expected}."
        )


def mean_cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute the mean row-wise cosine similarity between two embedding matrices."""

    if a.shape != b.shape:
        raise QuantizationError(
            f"Cannot compare embeddings with mismatched shapes: {a.shape} vs {b.shape}."
        )
    a_norm = a / np.clip(np.linalg.norm(a, axis=1, keepdims=True), 1e-12, None)
    b_norm = b / np.clip(np.linalg.norm(b, axis=1, keepdims=True), 1e-12, None)
    similarities = np.sum(a_norm * b_norm, axis=1)
    return float(np.mean(similarities))


def release_model(model: object | None) -> None:
    """Best-effort GPU/CPU memory cleanup for a (possibly large) model."""

    import torch

    if model is not None:
        del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


def save_quantized_model(model: "SentenceTransformer", output_path: Path) -> None:  # noqa: F821
    """Persist the quantized model to ``output_path`` using safetensors."""

    try:
        model.save_pretrained(str(output_path), safe_serialization=True)
    except Exception as exc:  # noqa: BLE001
        raise QuantizationError(f"Failed to save quantized model: {exc}") from exc


def write_metadata(
    output_path: Path,
    config: PipelineConfig,
    source_size_bytes: int,
    output_size_bytes: int,
    int8_layer_count: int,
    reload_similarity: float,
    baseline_similarity: float | None,
    elapsed_seconds: float,
) -> None:
    """Write a JSON metadata/report file alongside the quantized model."""

    import torch
    import transformers

    reduction_pct = (
        100.0 * (1.0 - output_size_bytes / source_size_bytes) if source_size_bytes else 0.0
    )

    metadata = {
        "model": EMBEDDING_MODEL_NAME,
        "source_model": str(config.source_model),
        "source_step": DEFAULT_SOURCE_STEP,
        "quantization": "INT8",
        "method": "bitsandbytes LLM.int8()",
        "int8_threshold": config.int8_threshold,
        "int8_linear_layers": int8_layer_count,
        "embedding_dimension": config.embedding_dim,
        "source_size_bytes": source_size_bytes,
        "quantized_size_bytes": output_size_bytes,
        "size_reduction_pct": round(reduction_pct, 2),
        "reload_mean_cosine_similarity": reload_similarity,
        "baseline_mean_cosine_similarity": baseline_similarity,
        "min_cosine_similarity_gate": config.min_cosine_similarity,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "versions": {
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "cuda": torch.version.cuda,
        },
    }

    metadata_path = output_path / "quantization_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    LOGGER.info("Wrote metadata to %s", metadata_path)


def run(config: PipelineConfig) -> int:
    """Execute the full quantize -> save -> validate pipeline.

    Returns:
        0 on success. Raises :class:`QuantizationError` on any failure so
        the caller can log and translate it into a process exit code.
    """

    import torch

    start_time = time.perf_counter()

    torch.manual_seed(config.seed)
    np.random.seed(config.seed)

    LOGGER.info("=" * 70)
    LOGGER.info("QWEN3 EMBEDDING INT8 QUANTIZATION")
    LOGGER.info("=" * 70)
    LOGGER.info("Source: %s", config.source_model)
    LOGGER.info("Output: %s", config.output_model)

    ensure_source_model_ready(config.source_model)
    source_size_bytes = get_directory_size_bytes(config.source_model)
    LOGGER.info("Source size: %s", human_readable_size(source_size_bytes))

    device = check_cuda_available(config.device)
    ensure_output_dir_ready(config.output_model, config.force)

    baseline_result: EncodeResult | None = None
    if not config.skip_baseline_comparison:
        LOGGER.info("Loading full-precision baseline model for fidelity comparison...")
        baseline_model = None
        try:
            baseline_model = load_sentence_transformer(config.source_model, device)
            baseline_result = encode_texts(baseline_model, config.sample_texts, "baseline-fp32")
            validate_embedding_shape(
                baseline_result, len(config.sample_texts), config.embedding_dim
            )
        finally:
            release_model(baseline_model)
        LOGGER.info("Baseline embedding shape: %s", baseline_result.embeddings.shape)

    LOGGER.info("Loading source model with INT8 quantization (threshold=%.1f)...",
                config.int8_threshold)
    quant_config = build_quantization_config(config.int8_threshold)
    quantized_model = None
    try:
        quantized_model = load_sentence_transformer(
            config.source_model, device, quantization_config=quant_config
        )

        int8_layers = count_int8_linear_layers(quantized_model)
        LOGGER.info("INT8 Linear8bitLt layers: %d", int8_layers)
        if int8_layers == 0:
            raise QuantizationError("INT8 quantization did not activate (0 quantized layers).")

        pre_save_result = encode_texts(quantized_model, config.sample_texts, "quantized-pre-save")
        validate_embedding_shape(pre_save_result, len(config.sample_texts), config.embedding_dim)
        LOGGER.info("Quantized embedding shape: %s", pre_save_result.embeddings.shape)

        baseline_similarity: float | None = None
        if baseline_result is not None:
            baseline_similarity = mean_cosine_similarity(
                baseline_result.embeddings, pre_save_result.embeddings
            )
            LOGGER.info(
                "Mean cosine similarity (fp32 baseline vs INT8): %.6f", baseline_similarity
            )
            if baseline_similarity < config.min_cosine_similarity:
                raise QuantizationError(
                    "Quantization quality gate failed: mean cosine similarity "
                    f"{baseline_similarity:.6f} is below the required minimum "
                    f"{config.min_cosine_similarity:.6f}."
                )

        LOGGER.info("Saving quantized model to %s ...", config.output_model)
        save_quantized_model(quantized_model, config.output_model)
    finally:
        release_model(quantized_model)

    output_size_bytes = get_directory_size_bytes(config.output_model)

    LOGGER.info("Reloading saved model from disk to verify round-trip integrity...")
    reloaded_model = None
    try:
        reload_quant_config = build_quantization_config(config.int8_threshold)
        reloaded_model = load_sentence_transformer(
            config.output_model, device, quantization_config=reload_quant_config
        )
        post_reload_result = encode_texts(
            reloaded_model, config.sample_texts, "quantized-post-reload"
        )
        validate_embedding_shape(
            post_reload_result, len(config.sample_texts), config.embedding_dim
        )
    finally:
        release_model(reloaded_model)

    reload_similarity = mean_cosine_similarity(
        pre_save_result.embeddings, post_reload_result.embeddings
    )
    reload_distance = 1.0 - reload_similarity
    LOGGER.info("Mean cosine similarity (pre-save vs post-reload): %.8f", reload_similarity)
    if reload_distance > config.reload_similarity_tolerance:
        raise QuantizationError(
            "Reloaded model diverges from the pre-save quantized model beyond "
            f"tolerance: cosine distance {reload_distance:.8f} > "
            f"{config.reload_similarity_tolerance:.8f}. The saved checkpoint "
            "may be corrupted."
        )

    elapsed_seconds = time.perf_counter() - start_time

    write_metadata(
        output_path=config.output_model,
        config=config,
        source_size_bytes=source_size_bytes,
        output_size_bytes=output_size_bytes,
        int8_layer_count=int8_layers,
        reload_similarity=reload_similarity,
        baseline_similarity=baseline_similarity,
        elapsed_seconds=elapsed_seconds,
    )

    reduction_pct = (
        100.0 * (1.0 - output_size_bytes / source_size_bytes) if source_size_bytes else 0.0
    )

    LOGGER.info("=" * 70)
    LOGGER.info("QUANTIZATION SUCCESSFUL")
    LOGGER.info("=" * 70)
    LOGGER.info("Full precision: %s", human_readable_size(source_size_bytes))
    LOGGER.info("INT8:           %s", human_readable_size(output_size_bytes))
    LOGGER.info("Reduction:      %.2f%%", reduction_pct)
    LOGGER.info("Output:         %s", config.output_model)
    LOGGER.info("Elapsed:        %.1fs", elapsed_seconds)

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""

    try:
        config = parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    try:
        return run(config)
    except QuantizationError as exc:
        LOGGER.error("Quantization pipeline failed: %s", exc)
        return 1
    except KeyboardInterrupt:
        LOGGER.warning("Interrupted by user.")
        return 130
    except Exception:  # noqa: BLE001 - top-level safety net with full traceback
        LOGGER.exception("Unexpected error during quantization pipeline.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
