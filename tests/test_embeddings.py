"""Tests for the dual-mode embedding module."""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from hull_core.providers.openai_spec import ProviderError

from better_code_review_graph.embeddings import (
    _DEFAULT_DIMS,
    CloudEmbeddingBackend,
    EmbeddingStore,
    LocalEmbeddingBackend,
    _cosine_similarity,
    _decode_vector,
    _detect_embedding_provider,
    _encode_vector,
    _strip_provider,
    describe_backend_selection,
    embed_all_nodes,
    init_backend,
    resolve_backend,
    resolve_embedding_chain,
    semantic_search,
)
from better_code_review_graph.graph import GraphNode, GraphStore


@pytest.fixture(autouse=True)
def mock_local_inference():
    """Mock local model inference to avoid downloads and real inference."""
    with patch(
        "better_code_review_graph.embeddings.LocalEmbeddingBackend._get_model"
    ) as mock_get:
        mock_model = MagicMock()
        mock_get.return_value = mock_model
        # Mock embed and query_embed to return random vectors of requested dimension
        mock_model.embed.side_effect = lambda texts, **kwargs: [
            np.random.rand(kwargs.get("dim", 768)) for _ in texts
        ]
        mock_model.query_embed.side_effect = lambda text, **kwargs: [
            np.random.rand(kwargs.get("dim", 768))
        ]
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(**kwargs) -> GraphNode:
    defaults = {
        "id": 1,
        "kind": "Function",
        "name": "my_func",
        "qualified_name": "file.py::my_func",
        "file_path": "file.py",
        "line_start": 1,
        "line_end": 10,
        "language": "python",
        "parent_name": None,
        "params": None,
        "return_type": None,
        "is_test": False,
        "file_hash": None,
        "extra": {},
    }
    defaults.update(kwargs)
    return GraphNode(**defaults)


# ---------------------------------------------------------------------------
# Vector encoding
# ---------------------------------------------------------------------------


class TestVectorEncoding:
    def test_roundtrip(self):
        original = [1.0, 2.5, -3.14, 0.0, 100.0]
        blob = _encode_vector(original)
        decoded = _decode_vector(blob)
        assert len(decoded) == len(original)
        for a, b in zip(original, decoded, strict=True):
            assert abs(a - b) < 1e-5

    def test_empty_vector(self):
        blob = _encode_vector([])
        decoded = _decode_vector(blob)
        assert decoded == ()

    def test_blob_size(self):
        vec = [1.0, 2.0, 3.0]
        blob = _encode_vector(vec)
        assert len(blob) == 12  # 3 floats * 4 bytes each


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_different_lengths(self):
        a = [1.0, 2.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0


# ---------------------------------------------------------------------------
# Provider Detection
# ---------------------------------------------------------------------------


class TestProviderDetection:
    def test_detect_by_prefix(self):
        assert _detect_embedding_provider("jina-embeddings-v3") == "jina"
        assert _detect_embedding_provider("jina_ai/v3") == "jina"
        assert _detect_embedding_provider("gemini-embedding-2") == "gemini"
        assert _detect_embedding_provider("gemini/v2") == "gemini"
        assert _detect_embedding_provider("openai/text-embedding-3") == "openai"
        assert _detect_embedding_provider("text-embedding-3-large") == "openai"
        assert _detect_embedding_provider("embed-multilingual-v3.0") == "cohere"
        assert _detect_embedding_provider("cohere/v3") == "cohere"

    def test_strip_provider(self):
        assert _strip_provider("gemini/embedding-v1") == "embedding-v1"
        assert _strip_provider("model-name") == "model-name"


# ---------------------------------------------------------------------------
# Backend Selection
# ---------------------------------------------------------------------------


class TestResolveBackend:
    def test_legacy_backend_env_is_ignored(self, caplog):
        """The legacy EMBEDDING_BACKEND value no longer selects a backend.

        Pre-de-host it picked cloud/litellm/local; the de-hosted inference
        uses only EMBEDDING_MODELS + DISABLE_LOCAL_EMBED, and the stale
        variable draws a deprecation warning instead.
        """
        import logging

        with caplog.at_level(logging.WARNING, logger="better_code_review_graph.embeddings"):
            with patch.dict(os.environ, {"EMBEDDING_BACKEND": "cloud"}, clear=True):
                assert resolve_backend() == "local"
            with patch.dict(os.environ, {"EMBEDDING_BACKEND": "litellm"}, clear=True):
                assert resolve_backend() == "local"
            with patch.dict(os.environ, {"EMBEDDING_BACKEND": "local"}, clear=True):
                assert resolve_backend() == "local"
        assert any("EMBEDDING_BACKEND" in rec.message for rec in caplog.records)

    def test_default_local(self):
        with patch.dict(os.environ, {}, clear=True):
            assert resolve_backend() == "local"

    def test_unavailable_when_local_disabled_and_no_chain(self):
        """DISABLE_LOCAL_EMBED + empty chain -> 'unavailable' (NOT forced)."""
        with patch.dict(os.environ, {"DISABLE_LOCAL_EMBED": "true"}, clear=True):
            assert resolve_backend() == "unavailable"

    def test_cloud_wins_even_when_local_disabled(self):
        with patch.dict(
            os.environ,
            {
                "DISABLE_LOCAL_EMBED": "true",
                "EMBEDDING_MODELS": "gemini/gemini-embedding-001",
            },
            clear=True,
        ):
            assert resolve_backend() == "cloud"

    def test_init_backend_unavailable_raises_clear_error(self):
        import pytest

        from better_code_review_graph.embeddings import init_backend

        with patch.dict(os.environ, {"DISABLE_LOCAL_EMBED": "true"}, clear=True):
            with pytest.raises(ValueError, match="DISABLE_LOCAL_EMBED"):
                init_backend()

    def test_describe_local_selection_without_loading_model(self):
        with (
            patch.dict(os.environ, {"EMBEDDING_BACKEND": "local"}, clear=True),
            patch(
                "better_code_review_graph.embeddings._first_supported_local_model_id",
                return_value="fastretrieval/reference",
            ),
        ):
            assert describe_backend_selection() == {
                "backend": "local",
                "model": "fastretrieval/reference",
                "dimensions": 768,
                "fallback": "none",
            }

    def test_describe_cloud_selection_uses_first_configured_model(self):
        with patch.dict(
            os.environ,
            {
                "EMBEDDING_BACKEND": "cloud",
                "EMBEDDING_MODELS": "cohere/embed-v4.0,openai/text-embedding-3-large",
            },
            clear=True,
        ):
            assert describe_backend_selection() == {
                "backend": "cloud",
                "model": "cohere/embed-v4.0",
                "dimensions": 1024,
                "fallback": "none",
            }

    def test_legacy_cloud_backend_env_does_not_force_cloud(self):
        """Legacy EMBEDDING_BACKEND=cloud cannot trigger model-less cloud.

        The pre-de-host guard raised ValueError('EMBEDDING_MODELS') here;
        post-de-host the legacy env is ignored, so a cloud chain only ever
        starts from EMBEDDING_MODELS (pinned in TestResolveEmbeddingChain)
        and init_backend falls back to local.
        """
        with patch.dict(os.environ, {"EMBEDDING_BACKEND": "cloud"}, clear=True):
            assert isinstance(init_backend(), LocalEmbeddingBackend)

    def test_describe_unavailable_selection(self):
        with patch.dict(os.environ, {"DISABLE_LOCAL_EMBED": "true"}, clear=True):
            assert describe_backend_selection() == {
                "backend": "unavailable",
                "model": None,
                "dimensions": 768,
                "fallback": "unavailable",
            }


# ---------------------------------------------------------------------------
# Embedding model chain (per-task model-chain redesign)
# ---------------------------------------------------------------------------


class TestResolveEmbeddingChain:
    def test_explicit_models_from_env(self, monkeypatch):
        monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
        monkeypatch.setenv(
            "EMBEDDING_MODELS",
            "jina_ai/jina-embeddings-v5-text-small,gemini/gemini-embedding-001",
        )
        chain = resolve_embedding_chain()
        assert chain == [
            "jina_ai/jina-embeddings-v5-text-small",
            "gemini/gemini-embedding-001",
        ]
        assert resolve_backend() == "cloud"

    def test_explicit_models_strip_and_skip_empties(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MODELS", " openai/text-embedding-3-large , , ")
        assert resolve_embedding_chain() == ["openai/text-embedding-3-large"]

    def test_empty_no_keys_is_local(self, monkeypatch):
        for k in (
            "EMBEDDING_MODELS",
            "EMBEDDING_MODEL",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        assert resolve_embedding_chain() == []
        assert resolve_backend() == "local"

    def test_keys_do_not_implicitly_select_cloud_models(self):
        with patch.dict(
            os.environ,
            {
                "JINA_AI_API_KEY": "test",
                "COHERE_API_KEY": "test",
                "OPENAI_API_KEY": "test",
            },
            clear=True,
        ):
            assert resolve_embedding_chain() == []
            assert resolve_backend() == "local"

    def test_legacy_embedding_model_honored(self, monkeypatch):
        for k in (
            "EMBEDDING_BACKEND",
            "EMBEDDING_MODELS",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("EMBEDDING_MODEL", "gemini/gemini-embedding-001")
        assert resolve_embedding_chain() == ["gemini/gemini-embedding-001"]
        assert resolve_backend() == "cloud"

    def test_explicit_models_wins_over_legacy(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MODELS", "openai/text-embedding-3-large")
        monkeypatch.setenv("EMBEDDING_MODEL", "gemini/gemini-embedding-001")
        assert resolve_embedding_chain() == ["openai/text-embedding-3-large"]

    def test_legacy_backend_env_ignored_with_warning(self, monkeypatch, caplog):
        """Legacy EMBEDDING_BACKEND never selects; only chain + local flag do."""
        import logging

        for k in (
            "EMBEDDING_MODELS",
            "EMBEDDING_MODEL",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        with caplog.at_level(logging.WARNING, logger="better_code_review_graph.embeddings"):
            for legacy in ("cloud", "litellm", "local"):
                monkeypatch.setenv("EMBEDDING_BACKEND", legacy)
                assert resolve_backend() == "local"
        assert any("EMBEDDING_BACKEND" in rec.message for rec in caplog.records)

    def test_cloud_backend_uses_first_chain_model(self, monkeypatch):
        for k in (
            "EMBEDDING_MODEL",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("EMBEDDING_MODELS", "gemini/gemini-embedding-001")
        backend = CloudEmbeddingBackend()
        assert backend.model == "gemini/gemini-embedding-001"


class TestInitBackend:
    def test_local_backend(self):
        with patch.dict(os.environ, {"EMBEDDING_BACKEND": "local"}, clear=True):
            backend = init_backend()
            assert isinstance(backend, LocalEmbeddingBackend)

    def test_cloud_backend(self):
        with patch.dict(
            os.environ,
            {"EMBEDDING_MODELS": "openai/text-embedding-3-large"},
            clear=True,
        ):
            backend = init_backend()
            assert isinstance(backend, CloudEmbeddingBackend)

    def test_auto_detect_local(self):
        with patch.dict(os.environ, {}, clear=True):
            backend = init_backend()
            assert isinstance(backend, LocalEmbeddingBackend)

    def test_invalid_mode(self):
        with pytest.raises(ValueError, match="Unknown backend type"):
            init_backend(mode="invalid")


# ---------------------------------------------------------------------------
# LocalEmbeddingBackend (local ONNX)
# ---------------------------------------------------------------------------


class TestLocalEmbeddingBackend:
    def test_embed_produces_768_dim(self):
        backend = LocalEmbeddingBackend()
        vectors = backend.embed_texts(["hello world"], dimensions=768)
        assert len(vectors) == 1
        assert len(vectors[0]) == 768

    def test_embed_multiple_texts(self):
        backend = LocalEmbeddingBackend()
        vectors = backend.embed_texts(["hello", "world"], dimensions=768)
        assert len(vectors) == 2
        for v in vectors:
            assert len(v) == 768

    def test_embed_empty_list(self):
        backend = LocalEmbeddingBackend()
        vectors = backend.embed_texts([])
        assert vectors == []

    def test_embed_single(self):
        backend = LocalEmbeddingBackend()
        vector = backend.embed_single("hello world", dimensions=768)
        assert len(vector) == 768


# ---------------------------------------------------------------------------
# CloudEmbeddingBackend (hull [models.embed] cell, plain-HTTP OpenAI-spec)
# ---------------------------------------------------------------------------


class _RecordingClient:
    """Fake hull ``OpenAICompatClient`` recording embeddings calls.

    Patched over ``hull_core.providers.openai_spec.OpenAICompatClient`` so
    tests exercise the real ``_post_embeddings`` body — instance-config cell
    resolution, the api-key guard, per-provider body fields, and the
    count/width validation — without any network.
    """

    # Per-subclass script, bound by _patched_client(). ``fail_with`` indexes
    # on CLASS-LEVEL attempt number: each _post_embeddings retry constructs
    # a fresh client instance, so the script must count across instances.
    instances: list = []
    vectors: list | None = None
    fail_with: list = []
    attempts: int = 0

    def __init__(self, cell, **kwargs):
        self.cell = cell
        self.init_kwargs = kwargs
        self.calls: list[dict] = []
        type(self).instances.append(self)

    async def embeddings(self, texts, dimensions=None, **extra):
        call: dict = {"texts": list(texts), "dimensions": dimensions}
        call.update(extra)
        self.calls.append(call)
        idx = type(self).attempts
        type(self).attempts += 1
        if idx < len(self.fail_with):
            raise self.fail_with[idx]
        return list(self.vectors or [])

    async def aclose(self):
        self.closed = True


def _make_scripted_client(vectors, fail_with):
    """Bind one outcome script onto a fresh _RecordingClient subclass.

    ``fail_with`` entries are raised from the first N embeddings calls (in
    order) before ``vectors`` is returned; an unbounded script (e.g.
    ``[Exception("429")] * 99``) models retry exhaustion.
    """
    return type(
        "ScriptedClient",
        (_RecordingClient,),
        {
            "instances": [],
            "vectors": vectors,
            "fail_with": list(fail_with),
            "attempts": 0,
        },
    )


def _patched_client(vectors=None, fail_with=None):
    """Patch the hull client class with one scripted outcome.

    Use as ``with _patched_client(...) as client_cls:`` — ``client_cls`` is
    the scripted class; ``client_cls.instances`` records every client that
    ``_post_embeddings`` constructed.
    """
    return patch(
        "hull_core.providers.openai_spec.OpenAICompatClient",
        _make_scripted_client(vectors, fail_with or []),
    )


class TestCloudEmbeddingBackend:
    """CloudEmbeddingBackend dispatch through hull's embed cell.

    The pre-de-host surface (litellm ``mcp_core.llm.embedding`` passthrough,
    per-user ``api_key=`` kwarg, ``EMBEDDING_API_BASE`` env) is gone: the
    transport is the host-owned ``[models.embed]`` cell via hull-core's
    OpenAI-spec client, and the dispatch seam is ``_post_embeddings``.
    """

    @pytest.fixture(autouse=True)
    def _embed_cell_key(self, monkeypatch, tmp_path):
        """Give the real ``_post_embeddings`` a host key, hermetically."""
        monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setenv("HULL_EMBED_API_KEY", "k-test")

    # -- hull client response contract (what _post_embeddings consumes) ----

    def test_hull_client_parses_and_sorts_openai_response(self):
        """The hull client returns vectors sorted by the response's index.

        Replaces the pre-de-host dict-shape/pydantic-shape parse tests:
        response items are always OpenAI-spec JSON dicts now, and the
        index sort lives in hull_core's client, so the contract is pinned
        through a real client against a scripted HTTP response.
        """
        import httpx
        from hull_core.config.models import ModelCell
        from hull_core.providers.openai_spec import OpenAICompatClient

        captured = {}

        def handler(request):
            captured["payload"] = json.loads(request.content)
            captured["auth"] = request.headers.get("Authorization")
            # Out-of-order indices to prove sorting by index.
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 1, "embedding": [0.2, 0.2]},
                        {"index": 0, "embedding": [0.1, 0.1]},
                    ]
                },
            )

        cell = ModelCell(
            task="embed",
            base_url="http://127.0.0.1:9/v1",
            api_key="k-test",
            model="text-embedding-3-large",
        )
        client = OpenAICompatClient(
            cell, auth_mode="no-auth", transport=httpx.MockTransport(handler)
        )

        async def _run():
            try:
                return await client.embeddings(["a", "b"], dimensions=2)
            finally:
                await client.aclose()

        vectors = asyncio.run(_run())

        assert vectors == [[0.1, 0.1], [0.2, 0.2]]
        # Payload contract: the cell wins for model, texts go to input.
        assert captured["payload"] == {
            "model": "text-embedding-3-large",
            "input": ["a", "b"],
            "dimensions": 2,
        }
        assert captured["auth"] == "Bearer k-test"

    def test_hull_client_omits_dimensions_and_forwards_input_type(self):
        """Without dimensions the payload key is omitted; extra fields pass."""
        import httpx
        from hull_core.config.models import ModelCell
        from hull_core.providers.openai_spec import OpenAICompatClient

        captured = {}

        def handler(request):
            captured["payload"] = json.loads(request.content)
            return httpx.Response(
                200, json={"data": [{"index": 0, "embedding": [1.0]}]}
            )

        cell = ModelCell(
            task="embed",
            base_url="http://127.0.0.1:9/v1",
            api_key="k-test",
            model="cohere/embed-v4.0",
        )
        client = OpenAICompatClient(
            cell, auth_mode="no-auth", transport=httpx.MockTransport(handler)
        )

        async def _run():
            try:
                return await client.embeddings(["a"], input_type="search_document")
            finally:
                await client.aclose()

        vectors = asyncio.run(_run())

        assert vectors == [[1.0]]
        assert captured["payload"] == {
            "model": "cohere/embed-v4.0",
            "input": ["a"],
            "input_type": "search_document",
        }

    # -- _post_embeddings fail-closed validation ---------------------------

    def test_missing_vectors_fails_closed(self):
        """An empty provider response must raise, not store zero vectors."""
        backend = CloudEmbeddingBackend(model="openai/text-embedding-3-large")
        with _patched_client(vectors=[]) as client_cls:
            with pytest.raises(ValueError, match="vector count"):
                backend.embed_texts(["a"])
        assert client_cls.instances[-1].calls == [
            {"texts": ["a"], "dimensions": None}
        ]

    def test_width_mismatch_fails_closed(self):
        """Provider width != requested dimensions must fail loudly."""
        backend = CloudEmbeddingBackend(model="cohere/embed-english-v3.0")
        with _patched_client(vectors=[[0.1] * 1024]) as client_cls:
            with pytest.raises(ValueError, match="different width"):
                backend.embed_texts(["test"], dimensions=768)
        assert len(client_cls.instances[-1].calls) == 1

    # -- retry semantics ----------------------------------------------------

    def test_retry_on_transient_error(self):
        """A transient 429 is retried once, then succeeds."""
        backend = CloudEmbeddingBackend(model="cohere/embed-english-v3.0")
        vectors = [[0.5] * 768]
        with _patched_client(
            vectors=vectors, fail_with=[ProviderError(429, "rate limit exceeded")]
        ) as client_cls:
            with patch("time.sleep"):  # Skip actual delay
                result = backend.embed_texts(["test"], dimensions=768)
        assert result == vectors
        # Each _post_embeddings attempt constructs a fresh client.
        assert client_cls.attempts == 2

    # Retry semantics (transient retry, exhaustion, non-retryable) are pinned
    # in tests/test_coverage_gaps.py::TestRetryExhaustion on the same seam.

    # -- dispatch forwarding -------------------------------------------------

    def test_dispatch_forwards_dimensions_only_when_set(self):
        """dimensions flows to the client call; input_type only for Cohere."""
        backend = CloudEmbeddingBackend(model="jina-embeddings-v3")
        vectors = [[0.1] * 768]
        with _patched_client(vectors=vectors) as client_cls:
            result = backend.embed_texts(["hello"], dimensions=768)
        assert result == vectors
        call = client_cls.instances[-1].calls[0]
        assert call["dimensions"] == 768
        assert "input_type" not in call

        with _patched_client(vectors=vectors) as client_cls:
            backend.embed_texts(["hello"], dimensions=None)
        call = client_cls.instances[-1].calls[0]
        assert call["dimensions"] is None

    def test_dispatch_cohere_passes_input_type(self):
        """Cohere dispatch forwards input_type='search_document' for docs."""
        backend = CloudEmbeddingBackend(model="cohere/embed-multilingual-v3.0")
        with _patched_client(vectors=[[0.1] * 768]) as client_cls:
            backend.embed_texts(["hello"], dimensions=768)
        call = client_cls.instances[-1].calls[0]
        assert call["input_type"] == "search_document"

    # -- host-config cell wiring ---------------------------------------------

    @staticmethod
    def _write_instance_config(
        cfg_dir,
        *,
        base_url=None,
        model=None,
        api_key=None,
    ):
        lines = ["[models.embed]"]
        if base_url is not None:
            lines.append(f'base_url = "{base_url}"')
        if model is not None:
            lines.append(f'model = "{model}"')
        if api_key is not None:
            lines.append(f'api_key = "{api_key}"')
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_instance_config_cell_flows_into_client(self, tmp_path, monkeypatch):
        """base_url/model/api_key come from the instance config cell."""
        cfg = tmp_path / "cfg"
        self._write_instance_config(
            cfg,
            base_url="https://proxy.example/v1",
            model="gemini/embedding-v1",
            api_key="from-file",
        )
        monkeypatch.setenv("CRG_CONFIG_DIR", str(cfg))
        monkeypatch.delenv("HULL_EMBED_API_KEY", raising=False)

        # Explicit model: the backend's chain-head selection is orthogonal
        # to the instance-config cell this test pins.
        backend = CloudEmbeddingBackend(model="openai/text-embedding-3-large")
        with _patched_client(vectors=[[0.1] * 2]) as client_cls:
            backend.embed_texts(["x"], dimensions=2)

        client = client_cls.instances[-1]
        assert client.cell.base_url == "https://proxy.example/v1"
        assert client.cell.model == "gemini/embedding-v1"
        assert client.cell.api_key == "from-file"

    def test_missing_embed_cell_key_fails_closed(self, tmp_path, monkeypatch):
        """No key in the embed cell -> clear error, no client constructed."""
        monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "empty-cfg"))
        monkeypatch.delenv("HULL_EMBED_API_KEY", raising=False)

        backend = CloudEmbeddingBackend(model="openai/text-embedding-3-large")
        with _patched_client(vectors=[[0.1]]) as client_cls:
            with pytest.raises(ValueError, match="HULL_EMBED_API_KEY"):
                backend.embed_texts(["a"])
        assert client_cls.instances == []

    def test_env_key_overrides_config_file(self, tmp_path, monkeypatch):
        """HULL_EMBED_API_KEY wins over the config.toml api_key (host injects)."""
        cfg = tmp_path / "cfg"
        self._write_instance_config(cfg, api_key="from-file")
        monkeypatch.setenv("CRG_CONFIG_DIR", str(cfg))
        monkeypatch.setenv("HULL_EMBED_API_KEY", "from-env")

        backend = CloudEmbeddingBackend(model="openai/text-embedding-3-large")
        with _patched_client(vectors=[[0.1] * 2]) as client_cls:
            backend.embed_texts(["x"], dimensions=2)

        assert client_cls.instances[-1].cell.api_key == "from-env"


# ---------------------------------------------------------------------------
# EmbeddingStore
# ---------------------------------------------------------------------------


class TestEmbeddingStore:
    def test_store_initializes(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = LocalEmbeddingBackend()
        store = EmbeddingStore(db, backend)
        try:
            assert store.count() == 0
        finally:
            store.close()

    def test_embed_nodes_and_count(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = LocalEmbeddingBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [
                _make_node(
                    name="foo",
                    qualified_name="a.py::foo",
                    file_path="a.py",
                ),
                _make_node(
                    name="bar",
                    qualified_name="b.py::bar",
                    file_path="b.py",
                ),
            ]
            count = store.embed_nodes(nodes)
            assert count == 2
            assert store.count() == 2
        finally:
            store.close()

    def test_embed_nodes_skips_files(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = LocalEmbeddingBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [
                _make_node(kind="File", name="a.py", qualified_name="a.py"),
            ]
            count = store.embed_nodes(nodes)
            assert count == 0
        finally:
            store.close()

    def test_embed_nodes_deduplicates(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = LocalEmbeddingBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [
                _make_node(name="foo", qualified_name="a.py::foo"),
            ]
            count1 = store.embed_nodes(nodes)
            assert count1 == 1
            # Re-embed same node (no change) -- should skip
            count2 = store.embed_nodes(nodes)
            assert count2 == 0
        finally:
            store.close()

    def test_search(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = LocalEmbeddingBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [
                _make_node(
                    name="verify_firebase_token",
                    qualified_name="auth.py::verify_firebase_token",
                    language="python",
                ),
                _make_node(
                    name="process_payment",
                    qualified_name="payment.py::process_payment",
                    language="python",
                ),
            ]
            store.embed_nodes(nodes)

            results = store.search("firebase authentication", limit=2)
            assert len(results) >= 1
            names = [qn for qn, _score in results]
            assert "auth.py::verify_firebase_token" in names
        finally:
            store.close()

    def test_remove_node(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = LocalEmbeddingBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [_make_node(name="foo", qualified_name="a.py::foo")]
            store.embed_nodes(nodes)
            assert store.count() == 1

            store.remove_node("a.py::foo")
            assert store.count() == 0
        finally:
            store.close()

    def test_search_returns_empty_when_no_embeddings(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = LocalEmbeddingBackend()
        store = EmbeddingStore(db, backend)
        try:
            results = store.search("anything")
            assert results == []
        finally:
            store.close()

    def test_fixed_768_dim_storage(self, tmp_path):
        """All embeddings should be stored at fixed 768 dimensions."""
        db = tmp_path / "graph.db"
        backend = LocalEmbeddingBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [_make_node(name="foo", qualified_name="a.py::foo")]
            store.embed_nodes(nodes)

            # Read raw vector from DB and verify dimension
            row = store._conn.execute(
                "SELECT vector FROM embeddings WHERE qualified_name = ?",
                ("a.py::foo",),
            ).fetchone()
            assert row is not None
            vec = _decode_vector(row["vector"])
            assert len(vec) == 768
        finally:
            store.close()

    def test_search_filters_by_active_provider(self, tmp_path):
        """search() must only score rows of the active provider.

        Switching embedding providers must NOT mix vectors from different
        models in one cosine ranking. Rows stored under a different provider
        than the active backend must be excluded from the scan.
        """
        db = tmp_path / "graph.db"
        # No embed_single_query attr -> search() uses embed_single fallback.
        backend = MagicMock(spec=["name", "embed_single", "embed_texts"])
        backend.name = "cloud:openai:openai/text-embedding-3-large"
        # Deterministic query vector so cosine is well-defined.
        backend.embed_single.return_value = [1.0] * _DEFAULT_DIMS

        store = EmbeddingStore(db, backend)
        try:
            # Two rows under DIFFERENT providers, identical vectors.
            vec_blob = _encode_vector([1.0] * _DEFAULT_DIMS)
            store._conn.execute(
                "INSERT INTO embeddings "
                "(qualified_name, vector, text_hash, provider) "
                "VALUES (?, ?, ?, ?)",
                ("active.py::keep", vec_blob, "h1", backend.name),
            )
            store._conn.execute(
                "INSERT INTO embeddings "
                "(qualified_name, vector, text_hash, provider) "
                "VALUES (?, ?, ?, ?)",
                ("other.py::drop", vec_blob, "h2", "cloud:cohere:cohere/embed-v3"),
            )
            store._conn.commit()

            results = store.search("anything", limit=10)
            names = [qn for qn, _score in results]
            assert "active.py::keep" in names
            assert "other.py::drop" not in names
        finally:
            store.close()

    def test_re_embeds_on_backend_change(self, tmp_path):
        """Changing backend name should trigger re-embedding."""
        db = tmp_path / "graph.db"
        backend = LocalEmbeddingBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [_make_node(name="foo", qualified_name="a.py::foo")]
            count1 = store.embed_nodes(nodes)
            assert count1 == 1
        finally:
            store.close()

        # Open with a "different" backend by changing the backend_name
        store2 = EmbeddingStore(db, backend)
        try:
            # Manually override the stored provider to simulate switching
            store2._conn.execute("UPDATE embeddings SET provider = 'old_backend'")
            store2._conn.commit()

            count2 = store2.embed_nodes(nodes)
            assert count2 == 1  # re-embedded because provider changed
        finally:
            store2.close()


# ---------------------------------------------------------------------------
# embed_all_nodes + semantic_search (integration)
# ---------------------------------------------------------------------------


def _insert_file_and_functions(
    graph_store, file_path, function_names, language="python"
):
    """Helper: insert a File node and Function nodes into the graph store."""
    from better_code_review_graph.parser import NodeInfo

    # File node is required for get_all_files() to find the file
    graph_store.upsert_node(
        NodeInfo(
            kind="File",
            name=file_path,
            file_path=file_path,
            line_start=1,
            line_end=100,
            language=language,
        )
    )
    for name in function_names:
        graph_store.upsert_node(
            NodeInfo(
                kind="Function",
                name=name,
                file_path=file_path,
                line_start=1,
                line_end=5,
                language=language,
                params="()",
            )
        )
    graph_store.commit()


class TestEmbedAllNodes:
    def test_embed_all_nodes(self, tmp_path):
        db_path = tmp_path / "graph.db"
        graph_store = GraphStore(db_path)
        try:
            _insert_file_and_functions(graph_store, "test.py", ["hello"])

            backend = LocalEmbeddingBackend()
            emb_store = EmbeddingStore(db_path, backend)
            try:
                count = embed_all_nodes(graph_store, emb_store)
                # File node is skipped, only "hello" function embedded
                assert count == 1
                assert emb_store.count() == 1
            finally:
                emb_store.close()
        finally:
            graph_store.close()


class TestSemanticSearch:
    def test_semantic_search_with_embeddings(self, tmp_path):
        db_path = tmp_path / "graph.db"
        graph_store = GraphStore(db_path)
        try:
            _insert_file_and_functions(
                graph_store, "app.py", ["auth_handler", "payment_process", "user_login"]
            )

            backend = LocalEmbeddingBackend()
            emb_store = EmbeddingStore(db_path, backend)
            try:
                embed_all_nodes(graph_store, emb_store)

                results = semantic_search(
                    "authentication", graph_store, emb_store, limit=3
                )
                assert len(results) >= 1
                # Should return dicts with similarity_score
                assert "similarity_score" in results[0]
            finally:
                emb_store.close()
        finally:
            graph_store.close()

    def test_semantic_search_fallback_to_keyword(self, tmp_path):
        """When no embeddings exist, falls back to keyword search."""
        db_path = tmp_path / "graph.db"
        graph_store = GraphStore(db_path)
        try:
            _insert_file_and_functions(graph_store, "test.py", ["my_function"])

            backend = LocalEmbeddingBackend()
            emb_store = EmbeddingStore(db_path, backend)
            try:
                # Don't embed -- should fallback to keyword
                results = semantic_search(
                    "my_function", graph_store, emb_store, limit=5
                )
                assert len(results) >= 1
            finally:
                emb_store.close()
        finally:
            graph_store.close()
