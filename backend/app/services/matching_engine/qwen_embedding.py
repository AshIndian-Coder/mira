"""Qwen-1B-Embedding inference service (1536-dim output, INT8-ready).

Model strategy (per MIRA spec):
    1. Fine-tuned INT8 checkpoint   -> models/qwen_quantized/  (production/demo)
    2. Fine-tuned full precision    -> models/qwen_finetuned/
    3. Untrained Qwen-1B-Embedding  -> HF cache (baseline)
    4. Deterministic hashing embedder -> always available fallback

The fallback keeps the whole pipeline (and the test suite) runnable on a
laptop without torch/transformers/GPU. ``EMBEDDING_BACKEND`` controls
auto/qwen/hashing behaviour.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from typing import List, Optional

import numpy as np

from app.config import settings

logger = logging.getLogger("mira.embedding")

# ---------------------------------------------------------------------- #
# Deterministic fallback embedder (no dependencies, reproducible)
# ---------------------------------------------------------------------- #


class HashingEmbedder:
    """Multi-hash bag-of-words embedder into a fixed 1536-dim L2-normalized space.

    Not semantically powerful, but:
      * identical texts -> identical vectors (cosine 1.0)
      * shared tokens   -> positively correlated vectors
      * fully offline, deterministic, zero-dependency
    Good enough for demos without a GPU and for unit tests.
    """

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    def _token_vector(self, tokens: List[str]) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        return vector

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        vectors = []
        for text in texts:
            tokens = [tok for tok in (text or "").lower().split() if tok]
            # add bigrams for a little n-gram signal
            tokens += [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
            vector = self._token_vector(tokens)
            norm = float(np.linalg.norm(vector))
            vectors.append(vector / norm if norm > 0 else vector)
        return np.vstack(vectors) if vectors else np.zeros((0, self.dim), dtype=np.float32)


# ---------------------------------------------------------------------- #
# Qwen service
# ---------------------------------------------------------------------- #


class QwenEmbeddingService:
    """Loads the best available Qwen-1B-Embedding checkpoint.

    ``backend`` is one of: "qwen-int8" | "qwen-full" | "qwen-base" | "hashing".
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        dim: Optional[int] = None,
        backend: Optional[str] = None,
    ) -> None:
        self.dim = dim or settings.EMBEDDING_DIM
        self.backend = "hashing"
        self.model_path = model_path or settings.QWEN_MODEL_PATH
        self._requested_backend = backend or settings.EMBEDDING_BACKEND
        self._tokenizer = None
        self._model = None
        self._fallback = HashingEmbedder(self.dim)
        self._load()

    # ---------------- model loading ---------------- #

    def _candidate_paths(self) -> List[str]:
        candidates = []
        if self.model_path:
            candidates.append(self.model_path)
        candidates.append("models/qwen_finetuned")
        return candidates

    def _try_load_qwen(self) -> bool:
        try:
            from transformers import AutoModel, AutoTokenizer
        except ImportError:
            if self._requested_backend == "qwen":
                raise RuntimeError(
                    "EMBEDDING_BACKEND=qwen but transformers is not installed. "
                    "Run: pip install torch transformers"
                )
            logger.info("transformers not installed; using hashing embedder")
            return False

        for path in self._candidate_paths():
            import os

            if not os.path.isdir(path):
                continue
            try:
                logger.info("Loading Qwen embedding model from %s", path)
                self._tokenizer = AutoTokenizer.from_pretrained(path)
                self._model = AutoModel.from_pretrained(path)
                self._model.eval()
                # INT8 dynamic quantization when torch is present (Qwen-1B
                # ~500MB fp32 -> ~125MB int8 on CPU).
                try:
                    import torch

                    if self._model is not None and not torch.jit.is_scripting():
                        self._model = torch.quantization.quantize_dynamic(
                            self._model, {torch.nn.Linear}, dtype=torch.qint8
                        )
                        self.backend = "qwen-int8"
                except Exception as exc:  # pragma: no cover
                    logger.warning("INT8 quantization skipped: %s", exc)
                    self.backend = "qwen-full"
                self.model_path = path
                return True
            except Exception as exc:
                logger.warning("Failed to load model from %s: %s", path, exc)
        return False

    def _try_load_base(self) -> bool:
        """Load the untrained baseline from the HF hub (cached)."""
        try:
            from transformers import AutoModel, AutoTokenizer
        except ImportError:
            return False
        try:
            logger.info("Loading base %s from hub cache", settings.QWEN_BASE_MODEL)
            self._tokenizer = AutoTokenizer.from_pretrained(settings.QWEN_BASE_MODEL)
            self._model = AutoModel.from_pretrained(settings.QWEN_BASE_MODEL)
            self._model.eval()
            self.backend = "qwen-base"
            return True
        except Exception as exc:
            logger.warning("Base model unavailable: %s", exc)
            return False

    def _load(self) -> None:
        if self._requested_backend == "hashing":
            self.backend = "hashing"
            return
        if self._try_load_qwen():
            return
        if self._requested_backend == "qwen":
            raise RuntimeError(
                "EMBEDDING_BACKEND=qwen but no local checkpoint found and "
                "base model could not be loaded. Place a checkpoint at "
                f"{self.model_path} or use EMBEDDING_BACKEND=auto/hashing."
            )
        self._try_load_base()
        if self.backend == "hashing":
            logger.info(
                "Using deterministic hashing embedder (dim=%d). Install "
                "torch+transformers and train via app/ml_pipeline for real "
                "semantic embeddings.",
                self.dim,
            )

    # ---------------- inference ---------------- #

    def _qwen_embed(self, texts: List[str]) -> np.ndarray:
        import torch

        all_vectors = []
        batch_size = max(1, settings.QWEN_BATCH_SIZE)
        with torch.no_grad():
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                encoded = self._tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                )
                output = self._model(**encoded)
                # Last-token pooling (standard for Qwen embedding models).
                last_hidden = output.last_hidden_state
                attention_mask = encoded["attention_mask"]
                mask_idx = (attention_mask.cumsum(dim=1) == attention_mask.sum(dim=1, keepdim=True))
                pooled = last_hidden.masked_select(mask_idx).reshape(
                    len(batch), last_hidden.size(-1)
                )
                # Project to frozen dim if the head is wider/narrower.
                pooled = pooled.cpu().numpy().astype(np.float32)
                if pooled.shape[1] != self.dim:
                    pooled = pooled[:, : self.dim]
                norms = np.linalg.norm(pooled, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                all_vectors.append(pooled / norms)
        return np.vstack(all_vectors)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Embed a list of texts -> (n, dim) L2-normalized float32 array."""
        if self.backend.startswith("qwen"):
            return self._qwen_embed(texts)
        return self._fallback.embed_texts(texts)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]

    def model_info(self) -> dict:
        return {
            "backend": self.backend,
            "dim": self.dim,
            "model_path": self.model_path if self.backend.startswith("qwen") else None,
        }


_embedding_service: Optional[QwenEmbeddingService] = None
_embedding_lock = threading.Lock()


def get_embedding_service() -> QwenEmbeddingService:
    """Process-wide embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        with _embedding_lock:
            if _embedding_service is None:
                _embedding_service = QwenEmbeddingService()
    return _embedding_service

