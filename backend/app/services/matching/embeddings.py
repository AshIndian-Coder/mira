from __future__ import annotations

import logging
import math
import os
import random
import threading
import time
from collections import OrderedDict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

import httpx
import numpy as np

EXPECTED_EMBEDDING_DIM = 1024
REMOTE_MODEL_NAME = "AshIndian/Mira.ai"
REMOTE_SERVER_ENV = "MIRA_MODEL_SERVER_URL"
API_KEY_ENV = "MIRA_API_KEY"
REMOTE_MODEL_TOKEN = "__MIRA_REMOTE_AWS__"

DEFAULT_TIMEOUT = 105.0
DEFAULT_BATCH_SIZE = 8
DEFAULT_MAX_CONCURRENCY = 1
DEFAULT_RETRIES = 1
MAX_BATCH_SIZE = 128
MAX_SPLIT_DEPTH = 7
DEFAULT_CACHE_ITEMS = 4096

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    if not math.isfinite(value):
        value = default
    return max(minimum, min(maximum, value))


EMBED_BATCH_SIZE = _env_int("MIRA_EMBED_BATCH_SIZE", DEFAULT_BATCH_SIZE, 1, MAX_BATCH_SIZE)
EMBED_MAX_CONCURRENCY = _env_int("MIRA_EMBED_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY, 1, 8)
EMBED_RETRIES = _env_int("MIRA_EMBED_RETRIES", DEFAULT_RETRIES, 0, 3)
EMBED_TIMEOUT = _env_float("MIRA_EMBED_TIMEOUT", DEFAULT_TIMEOUT, 10.0, 120.0)
EMBED_CACHE_MAX_ITEMS = _env_int("MIRA_EMBED_CACHE_MAX_ITEMS", DEFAULT_CACHE_ITEMS, 0, 50000)

_RETRYABLE_STATUSES = {408, 409, 425, 429, 500, 502, 503}
_SPLIT_STATUSES = {413, 504, 524}
_RETRYABLE_TRANSPORT_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)

_request_slots = threading.BoundedSemaphore(EMBED_MAX_CONCURRENCY)
_adaptive_batch_lock = threading.Lock()
_adaptive_batch_size = EMBED_BATCH_SIZE
_cache_lock = threading.RLock()
_process_cache: OrderedDict[tuple[str, str], np.ndarray] = OrderedDict()


class MiraRemoteEmbeddingError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _model_cache_namespace(model: str) -> str:
    return "|".join(
        (
            model,
            os.getenv("MIRA_EMBEDDING_PIPELINE_VERSION", ""),
            os.getenv("MIRA_MODEL_SERVER_URL", "").strip().rstrip("/"),
        )
    )


def _current_batch_size(requested: int | None = None) -> int:
    with _adaptive_batch_lock:
        adaptive = _adaptive_batch_size
    configured = EMBED_BATCH_SIZE if requested is None else max(1, int(requested))
    return max(1, min(configured, EMBED_BATCH_SIZE, adaptive, MAX_BATCH_SIZE))


def _reduce_adaptive_batch_size(failed_size: int) -> int:
    global _adaptive_batch_size
    with _adaptive_batch_lock:
        proposed = max(1, failed_size // 2)
        _adaptive_batch_size = max(1, min(_adaptive_batch_size, proposed))
        return _adaptive_batch_size


def _cache_get(key: tuple[str, str]) -> np.ndarray | None:
    if EMBED_CACHE_MAX_ITEMS == 0:
        return None
    with _cache_lock:
        value = _process_cache.get(key)
        if value is not None:
            _process_cache.move_to_end(key)
        return value


def _cache_set(key: tuple[str, str], value: np.ndarray) -> None:
    if EMBED_CACHE_MAX_ITEMS == 0:
        return
    stored = np.asarray(value, dtype=np.float32).copy()
    stored.setflags(write=False)
    with _cache_lock:
        _process_cache[key] = stored
        _process_cache.move_to_end(key)
        while len(_process_cache) > EMBED_CACHE_MAX_ITEMS:
            _process_cache.popitem(last=False)


class RemoteMiraEmbeddingModel:
    def __init__(self, base_url: str | None = None, *, timeout: float = EMBED_TIMEOUT) -> None:
        configured_url = base_url if base_url is not None else os.getenv(REMOTE_SERVER_ENV, "")
        self.base_url = configured_url.strip().rstrip("/")
        if not self.base_url:
            raise RuntimeError(f"{REMOTE_SERVER_ENV} is not configured.")
        if not self.base_url.startswith(("http://", "https://")):
            raise RuntimeError(f"{REMOTE_SERVER_ENV} must start with http:// or https://.")

        self.timeout = max(10.0, min(float(timeout), 120.0))
        headers: dict[str, str] = {}
        api_key = os.getenv(API_KEY_ENV, "").strip()
        if api_key:
            headers["X-API-Key"] = api_key

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                connect=min(self.timeout, 15.0),
                read=self.timeout,
                write=min(self.timeout, 30.0),
                pool=min(self.timeout, 15.0),
            ),
            limits=httpx.Limits(
                max_connections=max(2, EMBED_MAX_CONCURRENCY + 1),
                max_keepalive_connections=max(1, EMBED_MAX_CONCURRENCY),
                keepalive_expiry=30.0,
            ),
            headers=headers,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def get_embedding_dimension(self) -> int:
        return EXPECTED_EMBEDDING_DIM

    def get_sentence_embedding_dimension(self) -> int:
        return EXPECTED_EMBEDDING_DIM

    def health(self) -> dict[str, Any]:
        try:
            response = self._client.get(
                "/health",
                timeout=httpx.Timeout(connect=10.0, read=min(self.timeout, 20.0), write=10.0, pool=10.0),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("status") != "ok":
                raise MiraRemoteEmbeddingError("MIRA model server returned an invalid health response.")
            return payload
        except MiraRemoteEmbeddingError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise MiraRemoteEmbeddingError(f"Unable to reach MIRA model server: {exc}") from exc

    @staticmethod
    def _clean_texts(texts: Iterable[str]) -> list[str]:
        cleaned: list[str] = []
        for text in texts:
            if not isinstance(text, str):
                raise TypeError(f"Expected string text, got {type(text).__name__}.")
            value = _normalize_text(text)
            if not value:
                raise ValueError("Embedding text cannot be empty.")
            cleaned.append(value)
        return cleaned

    @staticmethod
    def _validate_payload(payload: Any, expected_count: int) -> list[list[float]]:
        if not isinstance(payload, dict):
            raise MiraRemoteEmbeddingError("MIRA model server returned a non-object JSON response.")

        embeddings = payload.get("embeddings")
        if embeddings is None:
            single = payload.get("embedding")
            if single is None:
                raise MiraRemoteEmbeddingError("MIRA model server returned no embedding vectors.")
            embeddings = [single]

        if not isinstance(embeddings, list) or len(embeddings) != expected_count:
            received = len(embeddings) if isinstance(embeddings, list) else "invalid"
            raise MiraRemoteEmbeddingError(
                f"Embedding count mismatch: sent {expected_count}, received {received}."
            )

        matrix: list[list[float]] = []
        for embedding in embeddings:
            if not isinstance(embedding, list) or len(embedding) != EXPECTED_EMBEDDING_DIM:
                raise MiraRemoteEmbeddingError(
                    f"Invalid embedding dimension; expected {EXPECTED_EMBEDDING_DIM}."
                )
            try:
                vector = [float(value) for value in embedding]
            except (TypeError, ValueError) as exc:
                raise MiraRemoteEmbeddingError("Embedding contains a non-numeric value.") from exc
            if not all(math.isfinite(value) for value in vector):
                raise MiraRemoteEmbeddingError("Embedding contains a non-finite value.")
            matrix.append(vector)
        return matrix

    def _post_embeddings(self, texts: list[str]) -> list[list[float]]:
        acquired = _request_slots.acquire(timeout=min(self.timeout, 30.0))
        if not acquired:
            raise MiraRemoteEmbeddingError("Embedding request capacity is busy; retry the matching job shortly.")
        try:
            response = self._client.post("/embed", json={"text": texts})
            response.raise_for_status()
            return self._validate_payload(response.json(), len(texts))
        finally:
            _request_slots.release()

    def _split_and_retry(self, texts: list[str], split_depth: int, reason: str) -> list[list[float]]:
        if len(texts) <= 1 or split_depth >= MAX_SPLIT_DEPTH:
            raise MiraRemoteEmbeddingError(
                f"Embedding service could not process a batch of {len(texts)} text(s): {reason}",
                status_code=524 if "524" in reason else None,
            )

        preferred = _reduce_adaptive_batch_size(len(texts))
        midpoint = len(texts) // 2
        logger.warning(
            "Embedding batch failed; reducing preferred batch size to %d (%d items: %s)",
            preferred,
            len(texts),
            reason,
        )
        left = self._request_embeddings(texts[:midpoint], split_depth=split_depth + 1)
        right = self._request_embeddings(texts[midpoint:], split_depth=split_depth + 1)
        return left + right

    def _request_embeddings(self, texts: list[str], *, split_depth: int = 0) -> list[list[float]]:
        if not texts:
            return []
        cleaned = self._clean_texts(texts)
        delay = 0.5
        last_error: Exception | None = None

        for attempt in range(EMBED_RETRIES + 1):
            try:
                return self._post_embeddings(cleaned)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in _SPLIT_STATUSES:
                    return self._split_and_retry(cleaned, split_depth, f"HTTP {status}")
                if status not in _RETRYABLE_STATUSES or attempt >= EMBED_RETRIES:
                    raise MiraRemoteEmbeddingError(
                        f"MIRA embedding request failed with HTTP {status}.", status_code=status
                    ) from exc
                last_error = exc
                retry_after = exc.response.headers.get("Retry-After") if exc.response is not None else None
                if retry_after:
                    try:
                        delay = min(5.0, max(delay, float(retry_after)))
                    except ValueError:
                        pass
            except httpx.ReadTimeout as exc:
                if len(cleaned) > 1:
                    return self._split_and_retry(cleaned, split_depth, "read timeout")
                raise MiraRemoteEmbeddingError(
                    f"Single-text embedding request exceeded the {self.timeout:.0f}s read timeout."
                ) from exc
            except httpx.WriteTimeout as exc:
                if len(cleaned) > 1:
                    return self._split_and_retry(cleaned, split_depth, "write timeout")
                raise MiraRemoteEmbeddingError("Single-text embedding request timed out while uploading.") from exc
            except _RETRYABLE_TRANSPORT_ERRORS as exc:
                if attempt >= EMBED_RETRIES:
                    raise MiraRemoteEmbeddingError(
                        f"MIRA embedding transport failed after {attempt + 1} attempt(s): {exc}"
                    ) from exc
                last_error = exc
            except httpx.HTTPError as exc:
                if attempt >= EMBED_RETRIES:
                    raise MiraRemoteEmbeddingError(f"MIRA embedding HTTP request failed: {exc}") from exc
                last_error = exc
            except ValueError as exc:
                raise MiraRemoteEmbeddingError(f"MIRA embedding response could not be decoded: {exc}") from exc

            if attempt < EMBED_RETRIES:
                time.sleep(min(5.0, delay) + random.uniform(0.0, 0.2))
                delay = min(delay * 2.0, 5.0)

        raise MiraRemoteEmbeddingError(f"MIRA embedding request failed: {last_error}")

    def encode(
        self,
        sentences: str | list[str] | tuple[str, ...],
        *,
        normalize_embeddings: bool = True,
        batch_size: int | None = None,
        **_: Any,
    ) -> np.ndarray:
        del normalize_embeddings

        if isinstance(sentences, str):
            result = self._request_embeddings([sentences])
            return np.asarray(result[0], dtype=np.float32)
        if not isinstance(sentences, (list, tuple)):
            raise TypeError("sentences must be str, list[str], or tuple[str, ...].")
        if not sentences:
            return np.empty((0, EXPECTED_EMBEDDING_DIM), dtype=np.float32)

        requested = EMBED_BATCH_SIZE if batch_size is None else int(batch_size)
        requested = max(1, min(requested, MAX_BATCH_SIZE))

        if EMBED_MAX_CONCURRENCY == 1:
            output: list[list[float]] = []
            offset = 0
            while offset < len(sentences):
                size = _current_batch_size(requested)
                batch = list(sentences[offset:offset + size])
                output.extend(self._request_embeddings(batch))
                offset += len(batch)
            flattened = output
        else:
            effective_size = _current_batch_size(requested)
            batches = [
                list(sentences[start:start + effective_size])
                for start in range(0, len(sentences), effective_size)
            ]
            with ThreadPoolExecutor(max_workers=min(EMBED_MAX_CONCURRENCY, len(batches))) as executor:
                results = list(executor.map(self._request_embeddings, batches))
            flattened = [embedding for batch_result in results for embedding in batch_result]

        if len(flattened) != len(sentences):
            raise MiraRemoteEmbeddingError(
                f"Embedding count mismatch after batching: sent {len(sentences)}, received {len(flattened)}."
            )
        matrix = np.asarray(flattened, dtype=np.float32)
        expected_shape = (len(sentences), EXPECTED_EMBEDDING_DIM)
        if matrix.shape != expected_shape or not np.isfinite(matrix).all():
            raise MiraRemoteEmbeddingError(
                f"Invalid embedding matrix; received shape {matrix.shape}, expected {expected_shape}."
            )
        return matrix


@lru_cache(maxsize=1)
def _load_model(target: str) -> RemoteMiraEmbeddingModel:
    if target != REMOTE_MODEL_TOKEN:
        raise RuntimeError(f"Unsupported production model target: {target}")
    return RemoteMiraEmbeddingModel()


def resolve_model_name(name_or_alias: str | None = None) -> str:
    target = name_or_alias if name_or_alias is not None else os.getenv("MIRA_EMBEDDING_MODEL", "")
    target = str(target).strip()
    if not target or target == REMOTE_MODEL_TOKEN:
        return REMOTE_MODEL_TOKEN

    if target.lower() in {
        "default", "production", "qwen", "mira", "mira.ai", "ashindian/mira.ai"
    }:
        return REMOTE_MODEL_TOKEN
    if target.lower() in {"minilm", "base-minilm", "base_minilm"}:
        raise RuntimeError("Legacy MiniLM models are not enabled in the Render production deployment.")
    raise RuntimeError(f"Unsupported embedding model '{target}'.")


def get_embedding_model_name() -> str:
    return resolve_model_name()


def get_embedding_model(model_name: str | None = None) -> RemoteMiraEmbeddingModel:
    return _load_model(resolve_model_name(model_name))


def get_embedding_dimension(model_name: str | None = None) -> int:
    return get_embedding_model(model_name).get_embedding_dimension()


class EmbeddingCache:
    def __init__(
        self,
        initial_embeddings: dict[str, np.ndarray] | None = None,
        model_name: str | None = None,
    ) -> None:
        self.model_name = resolve_model_name(model_name)
        self._namespace = _model_cache_namespace(self.model_name)
        self._cache: dict[tuple[str, str], np.ndarray] = {}
        if initial_embeddings:
            for text, embedding in initial_embeddings.items():
                self.set(text, embedding)

    def _resolve_model(self, model_name: str | None = None) -> str:
        return resolve_model_name(model_name) if model_name is not None else self.model_name

    def _key(self, text: str, model_name: str | None = None) -> tuple[str, str]:
        model = self._resolve_model(model_name)
        namespace = self._namespace if model == self.model_name else _model_cache_namespace(model)
        return namespace, _normalize_text(text)

    def get(self, text: str, model_name: str | None = None) -> np.ndarray | None:
        key = self._key(text, model_name)
        value = self._cache.get(key)
        if value is None:
            value = _cache_get(key)
            if value is not None:
                self._cache[key] = value
        return value

    def set(self, text: str, embedding: np.ndarray, model_name: str | None = None) -> None:
        key = self._key(text, model_name)
        value = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if value.shape != (EXPECTED_EMBEDDING_DIM,) or not np.isfinite(value).all():
            raise MiraRemoteEmbeddingError("Refusing to cache an invalid embedding vector.")
        value = value.copy()
        value.setflags(write=False)
        self._cache[key] = value
        _cache_set(key, value)

    def precompute(
        self,
        texts: Iterable[str],
        batch_size: int = EMBED_BATCH_SIZE,
        model_name: str | None = None,
    ) -> None:
        model = self._resolve_model(model_name)
        unique_texts = list(
            dict.fromkeys(
                _normalize_text(text)
                for text in texts
                if isinstance(text, str) and text.strip()
            )
        )
        missing = [text for text in unique_texts if self.get(text, model_name=model) is None]
        if not missing:
            return

        embedding_model = get_embedding_model(model)
        offset = 0
        while offset < len(missing):
            size = _current_batch_size(batch_size)
            batch = missing[offset:offset + size]
            embeddings = embedding_model.encode(
                batch,
                batch_size=size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            expected_shape = (len(batch), EXPECTED_EMBEDDING_DIM)
            if embeddings.shape != expected_shape:
                raise MiraRemoteEmbeddingError(
                    f"Invalid embedding matrix shape: {embeddings.shape}; expected {expected_shape}."
                )
            for text, embedding in zip(batch, embeddings):
                self.set(text, embedding, model_name=model)
            offset += len(batch)

    def get_or_encode(self, text: str, model_name: str | None = None) -> np.ndarray | None:
        if not isinstance(text, str) or not text.strip():
            return None
        cached = self.get(text, model_name=model_name)
        if cached is not None:
            return cached
        model = self._resolve_model(model_name)
        embedding = get_embedding_model(model).encode(text, normalize_embeddings=True)
        if embedding.shape != (EXPECTED_EMBEDDING_DIM,):
            raise MiraRemoteEmbeddingError(f"Invalid single embedding shape: {embedding.shape}.")
        self.set(text, embedding, model_name=model)
        return self.get(text, model_name=model)

    def similarity(self, left: str, right: str, model_name: str | None = None) -> float:
        if not left or not right:
            return 0.0
        vec_a = self.get_or_encode(left, model_name=model_name)
        vec_b = self.get_or_encode(right, model_name=model_name)
        if vec_a is None or vec_b is None:
            return 0.0
        similarity = float(np.dot(vec_a, vec_b))
        if not math.isfinite(similarity):
            return 0.0
        return max(0.0, min(1.0, similarity))

    def clear(self) -> None:
        with _cache_lock:
            for key in self._cache:
                _process_cache.pop(key, None)
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, text: str) -> bool:
        return self.get(text) is not None


def precompute_embeddings(
    texts: Iterable[str],
    batch_size: int = EMBED_BATCH_SIZE,
    model_name: str | None = None,
) -> EmbeddingCache:
    cache = EmbeddingCache(model_name=model_name)
    cache.precompute(texts, batch_size=batch_size, model_name=model_name)
    return cache


def generate_embedding(text: str, model_name: str | None = None) -> list[float]:
    if not isinstance(text, str) or not text.strip():
        return []
    embedding = get_embedding_model(model_name).encode(text, normalize_embeddings=True)
    return embedding.astype(np.float32, copy=False).tolist()


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
    embeddings = get_embedding_model(model_name).encode(
        [left, right],
        normalize_embeddings=True,
        batch_size=2,
    )
    similarity = float(np.dot(embeddings[0], embeddings[1]))
    if not math.isfinite(similarity):
        return 0.0
    return max(0.0, min(1.0, similarity))


def health_check() -> dict[str, Any]:
    return get_embedding_model().health()
