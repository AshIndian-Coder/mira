from __future__ import annotations

import math
import os
import shutil
from collections.abc import Callable, Iterable
from functools import lru_cache
from typing import Any

import httpx
import numpy as np


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
    return max(minimum, min(maximum, value))


EMBED_BATCH_SIZE = _env_int("MIRA_EMBED_BATCH_SIZE", DEFAULT_BATCH_SIZE, 1, MAX_BATCH_SIZE)
EMBED_MAX_CONCURRENCY = _env_int("MIRA_EMBED_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY, 1, 8)
EMBED_RETRIES = _env_int("MIRA_EMBED_RETRIES", DEFAULT_RETRIES, 0, 5)
EMBED_TIMEOUT = _env_float("MIRA_EMBED_TIMEOUT", DEFAULT_TIMEOUT, 15.0, 600.0)


class MiraRemoteEmbeddingError(RuntimeError):
    pass


class RemoteMiraEmbeddingModel:
    def __init__(self, base_url: str | None = None, *, timeout: float = EMBED_TIMEOUT) -> None:
        configured_url = (
            base_url if base_url is not None else os.getenv(REMOTE_SERVER_ENV, "")
        ).strip()
        self.base_url = configured_url.rstrip("/")
        if not self.base_url:
            raise RuntimeError(f"{REMOTE_SERVER_ENV} is not configured.")
        if not self.base_url.startswith(("http://", "https://")):
            raise RuntimeError(f"{REMOTE_SERVER_ENV} must start with http:// or https://.")

        self.timeout = timeout
        headers: dict[str, str] = {}
        api_key = os.getenv(API_KEY_ENV, "").strip()
        if api_key:
            headers["X-API-Key"] = api_key

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                connect=min(timeout, 20.0),
                read=timeout,
                write=min(timeout, 60.0),
                pool=min(timeout, 30.0),
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
            response = self._client.get(
                "/health",
                timeout=httpx.Timeout(connect=10.0, read=min(self.timeout, 30.0), write=10.0, pool=10.0),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("status") != "ok":
                raise MiraRemoteEmbeddingError(
                    f"Invalid MIRA model server health response: {payload}"
                )
            return payload
        except MiraRemoteEmbeddingError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise MiraRemoteEmbeddingError(
                f"Unable to reach MIRA model server at {self.base_url}: {exc}"
            ) from exc

    @staticmethod
    def _clean_texts(texts: Iterable[str]) -> list[str]:
        cleaned: list[str] = []
        for text in texts:
            if not isinstance(text, str):
                raise TypeError(f"Expected string text, got {type(text).__name__}.")
            value = " ".join(text.split()).strip()
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
                raise MiraRemoteEmbeddingError(
                    "MIRA model server returned neither embeddings nor embedding."
                )
            embeddings = [single]

        if not isinstance(embeddings, list) or len(embeddings) != expected_count:
            received = len(embeddings) if isinstance(embeddings, list) else "invalid"
            raise MiraRemoteEmbeddingError(
                f"Embedding count mismatch: sent {expected_count}, received {received}."
            )

        validated: list[list[float]] = []
        for embedding in embeddings:
            if not isinstance(embedding, list) or len(embedding) != EXPECTED_EMBEDDING_DIM:
                raise MiraRemoteEmbeddingError(
                    f"Invalid embedding dimension: expected {EXPECTED_EMBEDDING_DIM}."
                )
            vector: list[float] = []
            for value in embedding:
                try:
                    number = float(value)
                except (TypeError, ValueError) as exc:
                    raise MiraRemoteEmbeddingError(
                        "MIRA model server returned a non-numeric embedding value."
                    ) from exc
                if not math.isfinite(number):
                    raise MiraRemoteEmbeddingError(
                        "MIRA model server returned a non-finite embedding value."
                    )
                vector.append(number)
            validated.append(vector)
        return validated

    def _post_embeddings(self, texts: list[str]) -> list[list[float]]:
        response = self._client.post("/embed", json={"text": texts})
        response.raise_for_status()
        return self._validate_payload(response.json(), len(texts))

    def _request_embeddings(self, texts: list[str], *, allow_split: bool = True) -> list[list[float]]:
        if not texts:
            return []

        cleaned = self._clean_texts(texts)
        delay = 1.0
        last_error: Exception | None = None

        for attempt in range(EMBED_RETRIES + 1):
            try:
                return self._post_embeddings(cleaned)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status == 413 and allow_split and len(cleaned) > MIN_ADAPTIVE_BATCH_SIZE:
                    middle = len(cleaned) // 2
                    return self._request_embeddings(cleaned[:middle]) + self._request_embeddings(cleaned[middle:])
                retryable = status in {408, 409, 425, 429, 500, 502, 503, 504}
                if not retryable or attempt >= EMBED_RETRIES:
                    raise MiraRemoteEmbeddingError(
                        f"MIRA embedding request failed with HTTP {status}: {exc}"
                    ) from exc
                last_error = exc
            except httpx.ReadTimeout as exc:
                if allow_split and len(cleaned) > MIN_ADAPTIVE_BATCH_SIZE:
                    middle = len(cleaned) // 2
                    return self._request_embeddings(cleaned[:middle]) + self._request_embeddings(cleaned[middle:])
                if attempt >= EMBED_RETRIES:
                    raise MiraRemoteEmbeddingError(
                        f"MIRA embedding request timed out after {EMBED_RETRIES + 1} attempts."
                    ) from exc
                last_error = exc
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
                if attempt >= EMBED_RETRIES:
                    raise MiraRemoteEmbeddingError(
                        f"MIRA embedding request failed after {EMBED_RETRIES + 1} attempts: {exc}"
                    ) from exc
                last_error = exc
            except httpx.HTTPError as exc:
                if attempt >= EMBED_RETRIES:
                    raise MiraRemoteEmbeddingError(f"MIRA embedding request failed: {exc}") from exc
                last_error = exc
            except ValueError as exc:
                raise MiraRemoteEmbeddingError(
                    f"MIRA embedding response could not be decoded: {exc}"
                ) from exc

            if attempt < EMBED_RETRIES:
                time.sleep(delay)
                delay = min(delay * 2.0, 8.0)

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
        effective_batch_size = max(1, min(requested, EMBED_BATCH_SIZE, MAX_BATCH_SIZE))
        batches = [
            list(sentences[start:start + effective_batch_size])
            for start in range(0, len(sentences), effective_batch_size)
        ]

        if len(batches) == 1:
            batch_results = [self._request_embeddings(batches[0])]
        elif EMBED_MAX_CONCURRENCY == 1:
            batch_results = [self._request_embeddings(batch) for batch in batches]
        else:
            worker_count = min(EMBED_MAX_CONCURRENCY, len(batches))
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                batch_results = list(executor.map(self._request_embeddings, batches))

        flattened = [embedding for batch in batch_results for embedding in batch]
        if len(flattened) != len(sentences):
            raise MiraRemoteEmbeddingError(
                f"Embedding count mismatch after batching: sent {len(sentences)}, received {len(flattened)}."
            )

        matrix = np.asarray(flattened, dtype=np.float32)
        expected_shape = (len(sentences), EXPECTED_EMBEDDING_DIM)
        if matrix.shape != expected_shape:
            raise MiraRemoteEmbeddingError(
                f"Invalid embedding matrix shape: {matrix.shape}; expected {expected_shape}."
            )
        return matrix


@lru_cache(maxsize=1)
def _load_model(target: str) -> RemoteMiraEmbeddingModel:
    if target != REMOTE_MODEL_TOKEN:
        raise RuntimeError(f"Unsupported production model target: {target}")
    return RemoteMiraEmbeddingModel()


def resolve_model_name(name_or_alias: str | None = None) -> str:
    target = (
        name_or_alias
        if name_or_alias is not None
        else os.getenv("MIRA_EMBEDDING_MODEL", "")
    )
    target = str(target).strip()

    if not target or target == REMOTE_MODEL_TOKEN:
        return REMOTE_MODEL_TOKEN

    production_aliases = {
        "default",
        "production",
        "qwen",
        "mira",
        "mira.ai",
        "ashindian/mira.ai",
    }
    if target.lower() in production_aliases:
        return REMOTE_MODEL_TOKEN

    if target.lower() in {"minilm", "base-minilm", "base_minilm"}:
        raise RuntimeError(
            "Legacy MiniLM models are not enabled in the Render production deployment."
        )

    raise RuntimeError(f"Unsupported embedding model '{target}'.")


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
    def __init__(
        self,
        initial_embeddings: dict[str, np.ndarray] | None = None,
        model_name: str | None = None,
    ) -> None:
        self.model_name = resolve_model_name(model_name)
        self._cache: dict[tuple[str, str], np.ndarray] = {}
        if initial_embeddings:
            for text, embedding in initial_embeddings.items():
                self._cache[(self.model_name, text)] = embedding

    def _resolve_model(self, model_name: str | None = None) -> str:
        return resolve_model_name(model_name) if model_name is not None else self.model_name

    def get(self, text: str, model_name: str | None = None) -> np.ndarray | None:
        return self._cache.get((self._resolve_model(model_name), text))

    def set(self, text: str, embedding: np.ndarray, model_name: str | None = None) -> None:
        self._cache[(self._resolve_model(model_name), text)] = embedding

    def precompute(
        self,
        texts: Iterable[str],
        batch_size: int = EMBED_BATCH_SIZE,
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

        model = self._resolve_model(model_name)
        key = (model, text)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        embedding = get_embedding_model(model).encode(
            text,
            normalize_embeddings=True,
        )
        if embedding.shape != (EXPECTED_EMBEDDING_DIM,):
            raise MiraRemoteEmbeddingError(
                f"Invalid single embedding shape: {embedding.shape}"
            )
        self._cache[key] = embedding
        return embedding

    def similarity(
        self,
        left: str,
        right: str,
        model_name: str | None = None,
    ) -> float:
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
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, text: str) -> bool:
        return (self.model_name, text) in self._cache


def precompute_embeddings(
    texts: Iterable[str],
    batch_size: int = EMBED_BATCH_SIZE,
    model_name: str | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> EmbeddingCache:
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
    embedding = get_embedding_model(model_name).encode(
        text,
        normalize_embeddings=True,
    )
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


    return max(0.0, min(1.0, similarity))
