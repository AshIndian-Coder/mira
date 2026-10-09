import os
import shutil
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import logging

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "Mira.ai"

# Must match the Milvus collection dimension; a downloaded model that does not
# match would be unusable as a drop-in replacement.
_EXPECTED_EMBEDDING_DIM = 1024


def _preferred_embedding_device() -> str:
    """Use CUDA when this PyTorch installation can access a GPU; otherwise CPU."""
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception as exc:
        logger.info("Could not detect a CUDA device; using CPU embeddings: %s", exc)
    return "cpu"


def get_embedding_device() -> str:
    """Human-readable preferred device for the embedding model."""
    device = _preferred_embedding_device()
    if device == "cpu":
        return "CPU"
    try:
        import torch

        return f"GPU ({torch.cuda.get_device_name(0)})"
    except Exception:
        return "GPU (CUDA)"


def _load_sentence_transformer(target: str, device: str | None = None) -> SentenceTransformer:
    selected_device = device or _preferred_embedding_device()
    try:
        model = SentenceTransformer(target, device=selected_device)
        logger.info("Loaded embedding model on %s", selected_device)
        return model
    except Exception:
        if selected_device == "cpu":
            raise

        logger.exception("Could not load embedding model on CUDA; retrying on CPU.")
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass
        model = SentenceTransformer(target, device="cpu")
        logger.info("Loaded embedding model on CPU after CUDA load failed")
        return model


def _get_project_root() -> Path:
    """Find the MIRA workspace root portably across operating systems."""
    cur = Path(__file__).resolve().parent
    for parent in [cur] + list(cur.parents):
        if (parent / "backend").exists() and (parent / "models").exists():
            return parent
        if (parent / ".git").exists():
            return parent
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT = _get_project_root()
LEGACY_MINILM_PATH = PROJECT_ROOT / "models" / "trained" / "minilm_cpse_v1"


def get_qwen_candidate_paths() -> list[Path]:
    """Return prioritized candidate search paths for the local Qwen model across OSes."""
    env_paths = [
        Path(os.getenv("MIRA_QWEN_MODEL_PATH", "").strip()),
        Path(os.getenv("MIRA_MODEL_PATH", "").strip()),
    ]
    models_dir = os.getenv("MIRA_MODELS_DIR", "").strip()
    if models_dir:
        env_paths.append(Path(models_dir) / "Mira.ai")

    home = Path.home()
    standard_paths = [
        home / "mira-model-test" / "Mira.ai",
        home / "Desktop" / "mira-model-test" / "Mira.ai",
        home / ".mira" / "models" / "Mira.ai",
        home / "models" / "Mira.ai",
        PROJECT_ROOT / "models" / "Mira.ai",
        PROJECT_ROOT / "models" / "trained" / "Mira.ai",
        PROJECT_ROOT / "models" / "trained" / "qwen",
        PROJECT_ROOT / "models" / "qwen",
    ]

    candidates: list[Path] = []
    for p in env_paths + standard_paths:
        if p and str(p) != "." and p not in candidates:
            candidates.append(p)
    return candidates


# A directory only counts as a model if it also holds weights. An interrupted
# download can leave config.json behind with no weights; treating that as
# "found" would poison every later run.
_WEIGHT_MARKERS = (
    "model.safetensors",
    "pytorch_model.bin",
    "model.safetensors.index.json",
    "pytorch_model.bin.index.json",
    "model.onnx",
)


def _is_complete_model_dir(path: Path) -> bool:
    """True only for a directory holding both config.json and weights."""
    try:
        return (
            path.is_dir()
            and (path / "config.json").exists()
            and any((path / marker).exists() for marker in _WEIGHT_MARKERS)
        )
    except (OSError, PermissionError):
        return False


def find_qwen_model_path() -> Path | None:
    """Locate the Qwen embedding directory on the current filesystem."""
    for p in get_qwen_candidate_paths():
        if _is_complete_model_dir(p):
            return p
    return None


# ---------------------------------------------------------------------------
# Hugging Face auto-download (bootstrap for a fresh clone)
#
# settings.model_hub_id points at the fine-tuned Epoch-2 INT8 checkpoint.
# Requires bitsandbytes + accelerate to load (see requirements.txt).
# ---------------------------------------------------------------------------

_download_attempted = False
_download_failed_reason: str | None = None


def _download_target_dir() -> Path:
    """Destination for an auto-downloaded model.

    Must be one of get_qwen_candidate_paths() so the NEXT run finds it on disk
    and does not download again.
    """
    override = os.getenv("MIRA_MODELS_DIR", "").strip()
    if override:
        return Path(override) / "Mira.ai"

    configured = (settings.model_auto_download_dir or "").strip()
    if configured:
        return Path(configured).expanduser() / "Mira.ai"

    return PROJECT_ROOT / "models" / "Mira.ai"


def reset_model_download_state() -> None:
    """Clears the one-shot download cache. Used by tests."""
    global _download_attempted, _download_failed_reason
    _download_attempted = False
    _download_failed_reason = None


def _loaded_dimension(model: SentenceTransformer) -> int:
    """Read the embedding dimension across sentence-transformers versions."""
    for attr in ("get_embedding_dimension", "get_sentence_embedding_dimension"):
        getter = getattr(model, attr, None)
        if callable(getter):
            dim = getter()
            if dim is not None:
                return int(dim)
    raise RuntimeError("could not determine the embedding dimension")


def _download_qwen_model(dest: Path) -> Path | None:
    """Fetch the embedding model from Hugging Face and install it at dest.

    Returns dest on success, or None on failure. Never raises -- the caller
    falls through to the original FileNotFoundError so the message stays
    actionable.

    The Hub files are copied as-is instead of re-saving a loaded model: this
    checkpoint loads through bitsandbytes INT8, and re-serialising a quantised
    model raises NotImplementedError inside transformers (it cannot reverse the
    quantisation weight conversion).

    The download lands in a staging directory, is verified by loading it back
    through the same call production uses, and only then replaces dest -- so an
    interrupted download can never leave a half-installed model behind.
    """
    global _download_attempted, _download_failed_reason

    # One attempt per process: resolve_model_name() is called very often, and
    # retrying a network fetch on every call would be pathological.
    if _download_attempted:
        return None
    _download_attempted = True

    hub_id = (settings.model_hub_id or "").strip()
    if not hub_id:
        _download_failed_reason = "settings.model_hub_id is empty"
        return None

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - dependency of sentence-transformers
        _download_failed_reason = (
            f"huggingface_hub is not installed ({exc}); "
            "run: pip install huggingface_hub"
        )
        return None

    logger.warning(
        "MIRA embedding model not found locally -- downloading '%s' from "
        "Hugging Face to '%s' (~750 MB, one time).",
        hub_id,
        dest,
    )

    staging = dest.parent / (dest.name + ".download")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if staging.exists():
            shutil.rmtree(staging)
        snapshot_download(repo_id=hub_id, local_dir=str(staging))
    except Exception as exc:
        _download_failed_reason = f"snapshot_download failed: {exc!r}"
        logger.warning("Hugging Face download of '%s' failed: %r", hub_id, exc)
        return None

    if not _is_complete_model_dir(staging):
        _download_failed_reason = (
            f"'{staging}' is missing config.json or model weights after download"
        )
        return None

    # Verify through the SAME call production uses.
    try:
        verified = _load_sentence_transformer(str(staging))
        dim = _loaded_dimension(verified)
    except Exception as exc:
        _download_failed_reason = (
            f"verification load failed: {exc!r} "
            "(if this mentions bitsandbytes or accelerate, install them: "
            "pip install bitsandbytes accelerate)"
        )
        logger.warning("Downloaded model failed verification: %r", exc)
        return None

    if dim != _EXPECTED_EMBEDDING_DIM:
        _download_failed_reason = (
            f"dimension {dim} != expected {_EXPECTED_EMBEDDING_DIM}"
        )
        logger.warning(
            "Downloaded model has dimension %s but MIRA expects %s -- rejecting.",
            dim,
            _EXPECTED_EMBEDDING_DIM,
        )
        return None

    # Install: drop any incomplete folder (e.g. from an earlier failed attempt),
    # then move the verified copy into its place.
    try:
        if dest.exists():
            shutil.rmtree(dest)
        staging.rename(dest)
    except OSError as exc:
        _download_failed_reason = f"could not install the model at '{dest}': {exc!r}"
        logger.warning("Could not move the downloaded model into place: %r", exc)
        return None

    try:
        (dest / "MIRA_MODEL_PROVENANCE.txt").write_text(
            f"Auto-downloaded from Hugging Face: {hub_id}\n"
            f"Verified load: dim={dim}\n"
            "Fine-tuned Epoch-2 INT8 checkpoint. Requires bitsandbytes and "
            "accelerate to load.\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # provenance is informational only

    logger.info("Embedding model downloaded and verified: %s (dim=%s)", dest, dim)
    return dest


def get_embedding_dimension(model_name: str | None = None) -> int:
    """Derive embedding dimension dynamically from the active or specified model."""
    model = get_embedding_model(model_name)
    if hasattr(model, "get_embedding_dimension"):
        try:
            dim = model.get_embedding_dimension()
            if dim is not None:
                return int(dim)
        except Exception:
            pass
    if hasattr(model, "get_sentence_embedding_dimension"):
        try:
            dim = model.get_sentence_embedding_dimension()
            if dim is not None:
                return int(dim)
        except Exception:
            pass
    return 1024


def resolve_model_name(name_or_alias: str | None = None) -> str:
    """
    Resolve model alias or environment variable into a valid model path or identifier.

    Production defaults exclusively to the local Qwen INT8 1024D model (`Mira.ai`).
    Silent fallbacks to 384D MiniLM have been removed.

    Resolution rules:
      1. Default / production (unset, '', 'default', 'production', 'qwen', 'mira', 'mira.ai'):
         - Locates Qwen INT8 model across candidate paths.
         - If not found, raises FileNotFoundError with actionable guidance.
      2. Explicit custom model path / HuggingFace ID / legacy evaluation alias:
         - 'minilm': legacy fine-tuned MiniLM checkpoint for historical evaluation scripts.
         - 'base-minilm' / 'base_minilm': 'all-MiniLM-L6-v2' for baseline comparison.
         - Any other string or Path is passed through directly.
    """
    target = name_or_alias if name_or_alias is not None else os.getenv("MIRA_EMBEDDING_MODEL", "")
    target = target.strip()

    if not target or target.lower() in ("default", "production", "qwen", "mira", "mira.ai"):
        qwen_path = find_qwen_model_path()
        if qwen_path is not None:
            return str(qwen_path)

        # Not on disk -- optionally fetch from Hugging Face.
        if settings.model_auto_download:
            downloaded = _download_qwen_model(_download_target_dir())
            if downloaded is not None:
                return str(downloaded)

        candidates = get_qwen_candidate_paths()
        candidate_str = "\n  - ".join(str(p) for p in candidates)
        download_note = (
            f"\nAuto-download attempt: {_download_failed_reason}"
            if _download_failed_reason
            else "\nAuto-download: disabled (MIRA_MODEL_AUTO_DOWNLOAD=false)."
        )
        raise FileNotFoundError(
            "MIRA production Qwen embedding model (1024D INT8) could not be located.\n"
            f"Searched candidate locations:\n  - {candidate_str}\n"
            f"{download_note}\n"
            "Please ensure the model directory exists at ~/mira-model-test/Mira.ai, "
            "or configure MIRA_QWEN_MODEL_PATH / MIRA_MODEL_PATH / MIRA_MODELS_DIR / MIRA_EMBEDDING_MODEL, "
            "or set MIRA_MODEL_AUTO_DOWNLOAD=true to fetch it from Hugging Face."
        )

    target_lower = target.lower()
    if target_lower == "minilm":
        if LEGACY_MINILM_PATH.exists() and (LEGACY_MINILM_PATH / "model.safetensors").exists():
            return str(LEGACY_MINILM_PATH)
        return "all-MiniLM-L6-v2"
    elif target_lower in ("base-minilm", "base_minilm"):
        return "all-MiniLM-L6-v2"

    return target


def get_embedding_model_name() -> str:
    return resolve_model_name()


@lru_cache(maxsize=8)
def _load_model(target: str, device: str) -> SentenceTransformer:
    return _load_sentence_transformer(target, device=device)


def get_embedding_model(
    model_name: str | None = None,
    device: str | None = None,
) -> SentenceTransformer:
    resolved = resolve_model_name(model_name)
    preferred_device = device or _preferred_embedding_device()
    try:
        return _load_model(resolved, preferred_device)
    except Exception:
        if preferred_device == "cpu":
            raise
        logger.exception("CUDA model load failed; retrying embedding model on CPU")
        return _load_model(resolved, "cpu")


class EmbeddingCache:
    """
    Scoped in-memory embedding cache for a matching batch or request.

    Precomputes or lazily caches normalized embeddings for unique texts
    so that repeated material descriptions are encoded at most once.
    Distinguishes models in the cache key to prevent cross-model cache contamination.
    """

    def __init__(
        self,
        initial_embeddings: dict[str, np.ndarray] | None = None,
        model_name: str | None = None,
    ):
        self.model_name = resolve_model_name(model_name)
        self._cache: dict[tuple[str, str], np.ndarray] = {}
        if initial_embeddings:
            for text, emb in initial_embeddings.items():
                self._cache[(self.model_name, text)] = emb

    def _resolve_model(self, model_name: str | None = None) -> str:
        return resolve_model_name(model_name) if model_name is not None else self.model_name

    def get(self, text: str, model_name: str | None = None) -> np.ndarray | None:
        m = self._resolve_model(model_name)
        return self._cache.get((m, text))

    def set(self, text: str, embedding: np.ndarray, model_name: str | None = None) -> None:
        m = self._resolve_model(model_name)
        self._cache[(m, text)] = embedding

    def precompute(
        self,
        texts: Iterable[str],
        batch_size: int = 64,
        model_name: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        m = self._resolve_model(model_name)
        missing = [t for t in set(texts) if t and (m, t) not in self._cache]
        if not missing:
            return

        model = get_embedding_model(m)
        effective_batch = max(1, min(int(batch_size), 64))

        # Encode in chunks (several batches each) instead of one giant call,
        # so progress can be reported between chunks. Results are identical.
        # Report more frequently on CPU, where each batch takes longer; retain
        # the larger batch on CUDA for throughput.
        model_device = str(getattr(model, "device", "cpu")).lower()
        chunk_size = effective_batch if "cuda" in model_device else min(effective_batch, 16)
        total = len(missing)
        done = 0
        if progress_callback is not None:
            progress_callback(0, total)

        for start in range(0, total, chunk_size):
            chunk = missing[start:start + chunk_size]
            try:
                embeddings = model.encode(
                    chunk,
                    batch_size=effective_batch,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            except RuntimeError as exc:
                if "out of memory" not in str(exc).lower() or _preferred_embedding_device() != "cuda":
                    raise
                logger.warning("CUDA ran out of memory while embedding; retrying this chunk on CPU")
                try:
                    import torch

                    torch.cuda.empty_cache()
                except Exception:
                    pass
                model = get_embedding_model(m, device="cpu")
                embeddings = model.encode(
                    chunk,
                    batch_size=effective_batch,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            for text, embedding in zip(chunk, embeddings):
                self._cache[(m, text)] = embedding
            done += len(chunk)
            if progress_callback is not None:
                progress_callback(done, total)

    def get_or_encode(self, text: str, model_name: str | None = None) -> np.ndarray | None:
        if not text:
            return None
        m = self._resolve_model(model_name)
        key = (m, text)
        if key not in self._cache:
            model = get_embedding_model(m)
            self._cache[key] = model.encode(
                text,
                normalize_embeddings=True,
            )
        return self._cache[key]

    def similarity(self, left: str, right: str, model_name: str | None = None) -> float:
        if not left or not right:
            return 0.0

        vec_a = self.get_or_encode(left, model_name=model_name)
        vec_b = self.get_or_encode(right, model_name=model_name)

        if vec_a is None or vec_b is None:
            return 0.0

        sim = float(vec_a @ vec_b)
        return max(0.0, min(1.0, sim))

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, text: str) -> bool:
        return (self.model_name, text) in self._cache


def precompute_embeddings(
    texts: Iterable[str],
    batch_size: int = 64,
    model_name: str | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> EmbeddingCache:
    """Convenience factory to precompute embeddings for a collection of texts into a new scoped cache."""
    cache = EmbeddingCache(model_name=model_name)
    cache.precompute(
        texts,
        batch_size=batch_size,
        model_name=model_name,
        progress_callback=progress_callback,
    )
    return cache


def generate_embedding(text: str, model_name: str | None = None) -> list[float]:
    if not text:
        return []

    model = get_embedding_model(model_name)

    embedding = model.encode(
        text,
        normalize_embeddings=True,
    )

    return embedding.tolist()


def semantic_similarity(
    left: str,
    right: str,
    embedding_cache: EmbeddingCache | None = None,
    model_name: str | None = None,
) -> float:
    if not left or not right:
        return 0.0

    if embedding_cache is not None:
        return embedding_cache.similarity(left, right, model_name=model_name)

    model = get_embedding_model(model_name)

    embeddings = model.encode(
        [left, right],
        normalize_embeddings=True,
    )

    similarity = float(embeddings[0] @ embeddings[1])

    return max(0.0, min(1.0, similarity))
