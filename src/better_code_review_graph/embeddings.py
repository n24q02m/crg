"""Dual-mode embedding: local ONNX (default) + cloud via hull-core.

Backends:
- **local**: ONNX runtime embedding through the ``fastretrieval`` model
  registry. Zero-config for the built-in reference model; custom artifacts
  use the explicit LOCAL_* configuration in ``config.py``.
- **cloud**: any OpenAI-spec ``/embeddings`` endpoint via hull-core's
  per-task ``[models.embed]`` cell (base_url + api_key from host config;
  plain HTTP). Supports Jina, Gemini, OpenAI, Cohere, or any
  OpenRouter model name. Model names come from the ``EMBEDDING_MODELS``
  chain (first entry is the active model).

Backend selection:
- ``EMBEDDING_MODELS`` non-empty -> 'cloud' (first entry is the model).
- Empty -> 'local' unless ``DISABLE_LOCAL_EMBED`` makes it unavailable.
- Keys never select a cloud model; only ``EMBEDDING_MODELS`` does.

Cohere embed-v4.0 uses exact 1024-dimensional vectors; other backends use 768.
Changing model or storage width requires re-embedding; vectors are never coerced.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any, Protocol

from .graph import GraphNode, GraphStore, node_to_dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_DIMS = 768

# Retry config for transient errors (rate limits, 5xx, network).
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds, doubles each retry

_RETRYABLE_PATTERNS = (
    "rate limit",
    "rate_limit",
    "429",
    "quota",
    "too many requests",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "connection",
    "temporarily unavailable",
    "overloaded",
    "resource exhausted",
    "resource_exhausted",
)


# Patterns marking a PERMANENT provider error (invalid request, unsupported
# capability, auth, not-found). Transport layers frequently re-wrap these as
# generic connection errors whose class name contains "connection" and whose
# status_code is a hardcoded 500 -- so classification MUST look at the message
# semantics, not the exception class or status code. Retrying a permanent error
# just re-sends the same doomed request and burns the whole retry budget before
# failing.
_PERMANENT_PATTERNS = (
    "not a valid",
    "not support",
    "unsupported",
    "invalid request",
    "invalid_request",
    "invalid api key",
    "output_dimension",
    "unauthorized",
    "forbidden",
    "authentication",
    "no such model",
    "model not found",
    "does not exist",
    "401",
    "403",
    "404",
    "422",
)


def _is_retryable(exc: Exception) -> bool:
    """Return True only for TRANSIENT errors worth retrying.

    Classifies on error-message semantics, NOT the exception class name or
    status code: transport wrappers (hull-core's ``ProviderError``, httpx
    errors) may collapse a provider's permanent 4xx (a 422 unsupported
    dimension, a 401 bad key, a 404 unknown model) into a generic
    connection/5xx-shaped message -- matching on class or status would
    retry a request that can never succeed, burning the full retry budget
    before failing loudly.
    """
    msg = str(exc).lower()
    if any(p in msg for p in _PERMANENT_PATTERNS):
        return False
    return any(p in msg for p in _RETRYABLE_PATTERNS)


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------


def _detect_embedding_provider(model: str) -> str:
    """Detect provider from model name. Returns 'jina', 'gemini', 'openai', or 'cohere'."""
    lower = model.lower()
    if lower.startswith("jina_ai/") or lower.startswith("jina"):
        return "jina"
    if lower.startswith("gemini/") or "gemini" in lower:
        return "gemini"
    if lower.startswith("embed-") or lower.startswith("cohere/"):
        return "cohere"
    return "openai"


def _strip_provider(model: str) -> str:
    """Strip provider prefix (e.g. 'gemini/model' -> 'model')."""
    if "/" in model:
        return model.split("/", 1)[1]
    return model


# ---------------------------------------------------------------------------
# Backend Protocol
# ---------------------------------------------------------------------------


class EmbeddingBackend(Protocol):  # pragma: no cover
    """Protocol for embedding backends."""

    def embed_texts(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed a batch of texts. Returns list of embedding vectors."""
        ...

    def embed_single(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a single text. Returns embedding vector."""
        ...


def _supported_local_model_ids() -> list[str]:
    """Return public fastretrieval model IDs without loading a model."""
    from fastretrieval import TextEmbedding

    model_ids: list[str] = []
    for item in TextEmbedding.list_supported_models():
        model_id = (
            item.get("model")
            if isinstance(item, dict)
            else getattr(item, "model", None)
        )
        if isinstance(model_id, str) and model_id:
            model_ids.append(model_id)
    return model_ids


def _first_supported_local_model_id() -> str:
    """Return the first public fastretrieval registry model ID."""
    model_ids = _supported_local_model_ids()
    if not model_ids:
        raise ValueError("fastretrieval TextEmbedding registry is empty")
    return model_ids[0]


# ---------------------------------------------------------------------------
# LocalEmbeddingBackend (local ONNX)
# ---------------------------------------------------------------------------


class LocalEmbeddingBackend:
    """Local ONNX embedding through ``fastretrieval.TextEmbedding``.

    The default model is a built-in registry entry. A custom model can be
    registered by the server and loaded from a local artifact directory.
    """

    def __init__(self, model_name: str | None = None, model_path: str | None = None):
        self._model_name = model_name
        self._model_path = model_path
        self._model = None

    @property
    def name(self) -> str:
        if self._model_name is None:
            self._model_name = _first_supported_local_model_id()
        return f"local:{self._model_name}"

    def _get_model(self):
        """Lazy-load the embedding model.

        The runtime resolves built-in IDs and custom registrations through its
        public ``TextEmbedding`` facade. A manifest-backed artifact is pinned
        to its local directory with ``specific_model_path``.
        """
        if self._model is None:
            from fastretrieval import TextEmbedding

            if self._model_name is None:
                self._model_name = _first_supported_local_model_id()

            self._model = TextEmbedding(
                model_name=self._model_name,
                specific_model_path=self._model_path,
            )
        return self._model

    def embed_texts(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed texts using local ONNX model."""
        if not texts:
            return []

        model = self._get_model()
        kwargs: dict[str, Any] = {}
        if dimensions and dimensions > 0:
            kwargs["dim"] = dimensions
        embeddings = list(model.embed(texts, **kwargs))
        return [emb.tolist() for emb in embeddings]

    def embed_single(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a single text (document/passage)."""
        results = self.embed_texts([text], dimensions)
        return results[0]

    def embed_single_query(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a query with instruction prefix (asymmetric retrieval)."""
        model = self._get_model()
        kwargs: dict[str, Any] = {}
        if dimensions and dimensions > 0:
            kwargs["dim"] = dimensions
        result = list(model.query_embed(text, **kwargs))
        return result[0].tolist()


# ---------------------------------------------------------------------------
# Cloud Embedding Backend (hull-core per-task cell, plain-HTTP OpenAI-spec)
# ---------------------------------------------------------------------------

# Cohere only accepts these exact output widths. Never widen and slice.
# Source: https://docs.cohere.com/docs/cohere-embed
_COHERE_OUTPUT_DIMENSIONS = (256, 512, 1024, 1536)


def _run_provider_call(coro: Any) -> Any:
    """Bridge an async hull provider call into crg's sync call sites.

    The tool entry points that reach the cloud backend are sync functions
    executed by FastMCP on anyio worker threads (or plain CLI processes), so
    no event loop is running here; a fresh loop per call is cheap relative
    to the HTTP round trip.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "sync cloud provider bridge called inside a running event loop; "
        "call hull_core's async client directly from async contexts"
    )


# Explicit storage contract for the supported Cohere v4 embedding space.
_COHERE_WIDTH_SELECTABLE_MODELS = ("embed-v4.0",)


def _cohere_supports_width_selection(model: str) -> bool:
    """Whether ``model`` can be asked for a width other than its native one."""
    return _strip_provider(model).lower() in _COHERE_WIDTH_SELECTABLE_MODELS


def _cloud_storage_dimensions(model: str | None) -> int:
    """Chọn chiều lưu trữ hợp lệ cho model, không cắt hoặc đệm vector."""
    if model and _cohere_supports_width_selection(model):
        return 1024
    return _DEFAULT_DIMS


def resolve_embedding_chain() -> list[str]:
    """Configured embedding models in selection order.

    The current embedding backend selects the first entry; later entries are
    retained as configuration but are not runtime fallbacks. Empty -> local
    ONNX. The model name is host configuration (``EMBEDDING_MODELS`` env);
    transport always comes from the instance ``[models.embed]`` cell.

    Returns a fresh list each call; safe under concurrent requests because
    the host owns the value process-wide.
    """
    explicit = (os.environ.get("EMBEDDING_MODELS") or "").strip()
    if explicit:
        return [m.strip() for m in explicit.split(",") if m.strip()]
    legacy = (os.environ.get("EMBEDDING_MODEL") or "").strip()
    if legacy:
        logger.warning(
            "Deprecated EMBEDDING_MODEL honored; migrate to EMBEDDING_MODELS "
            "(removed next release)."
        )
        return [legacy]
    return []


def _selected_cloud_model(model: str | None = None) -> str:
    """Return the model CloudEmbeddingBackend will use."""
    if model:
        return model
    chain = resolve_embedding_chain()
    if not chain:
        raise ValueError(
            "Cloud embedding requires an explicit EMBEDDING_MODELS selection"
        )
    return chain[0]


def _post_embeddings(
    texts: list[str],
    model: str,
    dimensions: int | None,
    *,
    input_type: str,
    provider: str,
) -> list[list[float]]:
    """One cloud embedding call through the hull ``embed`` cell.

    Body contract kept from the pre-dehost dispatch: OpenAI-spec
    ``model``/``input``/``dimensions`` plus Cohere's ``input_type``; the
    storage width is validated before spending a request and after the
    response returns.
    """
    from hull_core.providers.openai_spec import OpenAICompatClient

    from .config import load_instance_settings, resolve_cells

    settings = load_instance_settings()
    cell = resolve_cells(settings)["embed"]
    if not cell.api_key:
        raise ValueError(
            "Cloud embedding requires the [models.embed] cell to carry an api_key "
            "(instance config.toml, or HULL_EMBED_API_KEY in the environment)"
        )

    extra: dict[str, Any] = {}
    if provider == "cohere":
        extra["input_type"] = input_type
        if (
            dimensions is not None
            and _cohere_supports_width_selection(model)
            and dimensions not in _COHERE_OUTPUT_DIMENSIONS
        ):
            raise ValueError(
                f"Cohere embed-v4.0 requires dimensions in {_COHERE_OUTPUT_DIMENSIONS}; "
                f"received {dimensions}. Re-embed the graph with its selected storage width."
            )
    if dimensions is not None and dimensions <= 0:
        raise ValueError("Embedding dimensions must be positive")

    async def _call() -> list[list[float]]:
        client = OpenAICompatClient(cell, auth_mode=settings.server.auth)
        try:
            return await client.embeddings(texts, dimensions=dimensions, **extra)
        finally:
            await client.aclose()

    embeddings = _run_provider_call(_call())

    if len(embeddings) != len(texts):
        raise ValueError("Embedding provider returned the wrong vector count")
    if dimensions is not None and any(len(vec) != dimensions for vec in embeddings):
        raise ValueError(
            f"Embedding provider returned a different width than requested ({dimensions})"
        )
    return embeddings


class CloudEmbeddingBackend:
    """Cloud embedding via hull-core's per-task ``embed`` cell.

    Transport (``base_url`` + ``api_key`` + SSRF policy) always comes from
    the host-owned instance config ``[models.embed]`` cell (or the
    ``HULL_EMBED_API_KEY`` env override) — plain-HTTP OpenAI-spec through
    hull-core, no per-user key buckets (spec 2026-09-26 §4). The model name
    is the ``EMBEDDING_MODELS`` chain head; provider detection is name-based.
    """

    MAX_BATCH_SIZE = 96

    def __init__(
        self,
        model: str | None = None,
    ):
        self.model = _selected_cloud_model(model)
        self._provider = _detect_embedding_provider(self.model)

    @property
    def name(self) -> str:
        return f"cloud:{self._provider}:{self.model}"

    def _call_provider(
        self,
        texts: list[str],
        dimensions: int | None = None,
        *,
        input_type: str = "search_document",
    ) -> list[list[float]]:
        """Single cloud path: one hull OpenAI-spec client call.

        Dispatch seam for tests: monkeypatch ``_post_embeddings``.
        """
        return _post_embeddings(
            texts,
            self.model,
            dimensions,
            input_type=input_type,
            provider=self._provider,
        )

    def _embed_batch_inner(
        self,
        texts: list[str],
        dimensions: int | None = None,
        *,
        input_type: str = "search_document",
    ) -> list[list[float]]:
        """Embed a single batch with retry logic for transient errors."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return self._call_provider(texts, dimensions, input_type=input_type)
            except Exception as e:
                last_exc = e
                if attempt < _MAX_RETRIES - 1 and _is_retryable(e):
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                    time.sleep(delay)
                else:
                    break

        # Loop always sets last_exc before breaking (range is non-empty for
        # _MAX_RETRIES >= 1); fall back to a RuntimeError defensively.
        if last_exc is None:
            raise RuntimeError("embed batch failed without capturing an exception")
        raise last_exc

    def embed_texts(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed texts with auto batch splitting."""
        if not texts:
            return []

        if len(texts) <= self.MAX_BATCH_SIZE:
            return self._embed_batch_inner(texts, dimensions)

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i : i + self.MAX_BATCH_SIZE]
            batch_result = self._embed_batch_inner(batch, dimensions)
            all_embeddings.extend(batch_result)

        return all_embeddings

    def embed_single(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a single text."""
        results = self.embed_texts([text], dimensions)
        return results[0]

    def embed_single_query(
        self, text: str, dimensions: int | None = None
    ) -> list[float]:
        """Dùng search_query cho truy vấn Cohere, tách biệt với tài liệu."""
        return self._embed_batch_inner([text], dimensions, input_type="search_query")[0]


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def resolve_backend() -> str:
    """Resolve the embedding backend: 'cloud', 'local', or 'unavailable'.

    'cloud' when an EMBEDDING_MODELS chain is configured, 'local' when the
    chain is empty and the local ONNX leg is enabled (DISABLE_LOCAL_EMBED
    unset), 'unavailable' when neither — embedding is then gracefully
    unavailable, not forced. The legacy ``EMBEDDING_BACKEND`` env is ignored
    with a warning.
    """
    legacy = os.environ.get("EMBEDDING_BACKEND")
    if legacy:
        logger.warning(
            "Deprecated EMBEDDING_BACKEND is ignored; backend is inferred "
            "from EMBEDDING_MODELS + DISABLE_LOCAL_EMBED."
        )
    if resolve_embedding_chain():
        return "cloud"
    local_enabled = not (os.environ.get("DISABLE_LOCAL_EMBED") or "").strip()
    return "local" if local_enabled else "unavailable"


def describe_backend_selection() -> dict[str, str | int | None]:
    """Describe the selected embedding configuration without loading a model."""
    backend = resolve_backend()
    model: str | None = None

    if backend == "cloud":
        model = _selected_cloud_model()
    elif backend == "local":
        from .config import settings

        configured_model = settings.local_embedding_model.strip()
        if configured_model:
            model, _ = _resolve_local_model_source(configured_model)
        else:
            model = _first_supported_local_model_id()

    return {
        "backend": backend,
        "model": model,
        "dimensions": _cloud_storage_dimensions(model)
        if backend == "cloud"
        else _DEFAULT_DIMS,
        "fallback": "unavailable" if backend == "unavailable" else "none",
    }


def init_backend(mode: str | None = None) -> EmbeddingBackend:
    """Create an embedding backend instance.

    Args:
        mode: 'local', 'cloud', or None (auto-detect).

    Returns:
        Initialized backend instance.
    """
    mode = mode or resolve_backend()
    if mode == "cloud":
        return CloudEmbeddingBackend()
    if mode == "local":
        from .config import settings

        configured_model = settings.local_embedding_model.strip()
        if not configured_model:
            return LocalEmbeddingBackend()

        from .server import _maybe_register_custom_embed

        _maybe_register_custom_embed(configured_model)
        model_name, model_path = _resolve_local_model_source(configured_model)
        if model_path is None:
            from .server import _built_in_model_ids

            built_in_ids = {model_id.casefold() for model_id in _built_in_model_ids()}
            if (
                configured_model.casefold() not in built_in_ids
                and settings.local_embedding_dim <= 0
            ):
                raise ValueError(
                    f"Custom local embedding model {configured_model!r} requires "
                    "LOCAL_EMBEDDING_DIM > 0 or a manifest-backed directory"
                )
        return LocalEmbeddingBackend(model_name=model_name, model_path=model_path)
    if mode == "unavailable":
        raise ValueError(
            "Embedding unavailable: DISABLE_LOCAL_EMBED is set but no EMBEDDING_MODELS cloud "
            "chain is configured. Set EMBEDDING_MODELS + a provider key, or unset DISABLE_LOCAL_EMBED."
        )
    raise ValueError(f"Unknown backend type: {mode}")


def _resolve_local_model_source(local_model: str) -> tuple[str, str | None]:
    """Resolve a configured model ID or manifest-backed local directory."""
    model_dir = Path(local_model).expanduser()
    if not model_dir.is_dir():
        return local_model, None

    manifest_path = model_dir / "fastretrieval-manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            f"Custom local embedding directory {model_dir} requires "
            "fastretrieval-manifest.json"
        )

    from fastretrieval.contract import ModelContract

    contract = ModelContract.from_manifest(manifest_path)
    return contract.model_id, str(model_dir.resolve())


# ---------------------------------------------------------------------------
# SQLite vector storage
# ---------------------------------------------------------------------------

_EMBEDDINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
    qualified_name TEXT PRIMARY KEY,
    vector BLOB NOT NULL,
    text_hash TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown'
);
"""


def _encode_vector(vec: list[float]) -> bytes:
    """Encode a float vector as a compact binary blob."""
    return struct.pack(f"{len(vec)}f", *vec)


def _decode_vector(blob: bytes) -> tuple[float, ...]:
    """Decode a binary blob back to a float vector."""
    n = len(blob) // 4  # 4 bytes per float32
    return struct.unpack(f"{n}f", blob)


def _cosine_similarity(
    a: list[float] | tuple[float, ...],
    b: list[float] | tuple[float, ...],
    norm_a: float | None = None,
) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First vector.
        b: Second vector.
        norm_a: Optional precalculated Euclidean norm of ``a`` to avoid
            redundant recalculation in hot loops.
    """
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    # math.sumprod computes dot product entirely in C (Python 3.12+)
    dot = math.sumprod(a, b)
    # math.hypot calculates the Euclidean norm efficiently in C
    n_a = norm_a if norm_a is not None else math.hypot(*a)
    n_b = math.hypot(*b)
    if n_a == 0 or n_b == 0:
        return 0.0
    return dot / (n_a * n_b)


def _node_to_text(node: GraphNode) -> str:
    """Convert a node to a searchable text representation."""
    parts = [node.name]
    if node.kind != "File":
        parts.append(node.kind.lower())
    if node.parent_name:
        parts.append(f"in {node.parent_name}")
    if node.params:
        parts.append(node.params)
    if node.return_type:
        parts.append(f"returns {node.return_type}")
    if node.language:
        parts.append(node.language)
    return " ".join(parts)


class EmbeddingStore:
    """Manages vector embeddings for graph nodes in SQLite.

    Storage width follows the selected embedding model. Provider and vector
    width are checked before reuse so incompatible persisted rows are re-embedded.
    """

    def __init__(
        self, db_path: str | Path, backend: EmbeddingBackend | None = None
    ) -> None:
        self.backend = backend
        self.available = backend is not None
        self.dimensions = (
            _cloud_storage_dimensions(backend.model)
            if isinstance(backend, CloudEmbeddingBackend)
            else _DEFAULT_DIMS
        )
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_EMBEDDINGS_SCHEMA)

        # Migration for existing DBs missing the provider column
        try:
            self._conn.execute("SELECT provider FROM embeddings LIMIT 1")
        except sqlite3.OperationalError:
            self._conn.execute(
                "ALTER TABLE embeddings ADD COLUMN provider "
                "TEXT NOT NULL DEFAULT 'unknown'"
            )

        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _get_backend_name(self) -> str:
        if self.backend is None:
            return "none"
        return getattr(self.backend, "name", "unknown")

    def embed_nodes(self, nodes: list[GraphNode], batch_size: int = 64) -> int:
        """Compute and store embeddings for a list of nodes.

        Skips File nodes and nodes whose text + provider haven't changed.
        """
        if not self.backend:
            return 0

        provider_name = self._get_backend_name()

        # Filter to nodes that need embedding
        to_embed: list[tuple[GraphNode, str, str]] = []

        # Batch fetch existing metadata to prevent N+1 queries
        qns = [n.qualified_name for n in nodes if n.kind != "File"]
        existing_map: dict[str, dict[str, Any]] = {}
        cursor = self._conn.execute(
            "SELECT qualified_name, text_hash, provider, length(vector) AS vector_bytes FROM embeddings "
            "WHERE qualified_name IN (SELECT value FROM json_each(?))",
            (json.dumps(qns),),
        )
        for r in cursor:
            existing_map[r["qualified_name"]] = r

        for node in nodes:
            if node.kind == "File":
                continue
            text = _node_to_text(node)
            text_hash = hashlib.sha256(text.encode()).hexdigest()

            existing = existing_map.get(node.qualified_name)

            if (
                existing
                and existing["text_hash"] == text_hash
                and existing["provider"] == provider_name
                and existing["vector_bytes"] == self.dimensions * 4
            ):
                continue
            to_embed.append((node, text, text_hash))

        if not to_embed:
            return 0

        # Encode in batches
        texts = [t for _, t, _ in to_embed]
        vectors = self.backend.embed_texts(texts, dimensions=self.dimensions)
        if len(vectors) != len(texts) or any(
            len(vec) != self.dimensions for vec in vectors
        ):
            raise ValueError(
                f"Embedding output must contain one {self.dimensions}-dimensional vector per node"
            )

        # Use executemany for batch insertion to eliminate N+1 query bottlenecks
        insert_data = [
            (
                node.qualified_name,
                _encode_vector(vec),
                text_hash,
                provider_name,
            )
            for (node, _text, text_hash), vec in zip(to_embed, vectors, strict=True)
        ]
        self._conn.executemany(
            """INSERT OR REPLACE INTO embeddings
               (qualified_name, vector, text_hash, provider)
               VALUES (?, ?, ?, ?)""",
            insert_data,
        )

        self._conn.commit()
        return len(to_embed)

    def search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        """Search for nodes by semantic similarity.

        Uses embed_single_query if available (asymmetric retrieval),
        otherwise falls back to embed_single.
        """
        if not self.backend:
            return []

        # Restrict the scan to the active provider. Vectors from different
        # embedding models are not comparable, so mixing them in one cosine
        # ranking silently corrupts results when the user switches providers.
        provider_name = self._get_backend_name()

        # Refuse stale dimensions before spending a query request.
        count, minimum, maximum = self._conn.execute(
            "SELECT COUNT(*), MIN(length(vector)), MAX(length(vector)) "
            "FROM embeddings WHERE provider = ?",
            (provider_name,),
        ).fetchone()
        if count == 0:
            return []
        if minimum != self.dimensions * 4 or maximum != self.dimensions * 4:
            raise ValueError(
                f"Stored embeddings are incompatible with {self.dimensions}-dimensional "
                "queries. Run graph(action='embed') to re-embed the graph."
            )

        # Embed query -- use query-specific method if available
        query_method = getattr(self.backend, "embed_single_query", None)
        if callable(query_method):
            query_vec = query_method(query, dimensions=self.dimensions)
        else:
            query_vec = self.backend.embed_single(query, dimensions=self.dimensions)
        if len(query_vec) != self.dimensions:
            raise ValueError(f"Query embedding must have {self.dimensions} dimensions")

        # Brute-force cosine similarity scan with precalculated query norm
        scored: list[tuple[str, float]] = []
        query_norm = math.hypot(*query_vec)
        cursor = self._conn.execute(
            "SELECT qualified_name, vector FROM embeddings WHERE provider = ?",
            (provider_name,),
        )
        chunk_size = 500
        while True:
            rows = cursor.fetchmany(chunk_size)
            if not rows:
                break
            for row in rows:
                vec = _decode_vector(row["vector"])
                sim = _cosine_similarity(query_vec, vec, norm_a=query_norm)
                scored.append((row["qualified_name"], sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def remove_node(self, qualified_name: str) -> None:
        self._conn.execute(
            "DELETE FROM embeddings WHERE qualified_name = ?", (qualified_name,)
        )
        self._conn.commit()

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]

    def clear(self) -> None:
        """Remove all embeddings."""
        self._conn.execute("DELETE FROM embeddings")
        self._conn.commit()


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def embed_all_nodes(graph_store: GraphStore, embedding_store: EmbeddingStore) -> int:
    """Embed all non-file nodes in the graph."""
    if not embedding_store.available:
        return 0

    all_files = graph_store.get_all_files()
    all_nodes = graph_store.get_nodes_by_files(all_files)

    return embedding_store.embed_nodes(all_nodes)


def semantic_search(
    query: str,
    graph_store: GraphStore,
    embedding_store: EmbeddingStore,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search nodes using vector similarity, falling back to keyword search."""
    if embedding_store.available and embedding_store.count() > 0:
        results = embedding_store.search(query, limit=limit)
        # Batch fetch all nodes to avoid N+1 queries
        qns = [r[0] for r in results]
        node_list = graph_store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in node_list}

        output = []
        for qn, score in results:
            if qn in node_map:
                d = node_to_dict(node_map[qn])
                d["similarity_score"] = round(score, 4)
                output.append(d)
        return output

    # Fallback to keyword search
    nodes = graph_store.search_nodes(query, limit=limit)
    return [node_to_dict(n) for n in nodes]
