"""Tests for host-configured LLM summaries (post-de-host hull model cells).

Covers the pure helpers (``compute_source_hash``, ``compute_summary_cache_key``,
``NodeNeedingSummary`` immutability), the chat-cell resolution seam
(``summary_cell``), the single-node ``summarize_node_async`` LLM call through
hull-core's ``OpenAICompatClient``, and the ``batch_summarize`` queue/cache
behaviour against a real ``GraphStore``.

The pre-de-host tests drove ``SUMMARY_MODELS``/provider-key env vars and
patched ``summarize_node``; the BYOK cut replaced that with one host-owned
``[models.chat]`` cell dispatched through hull-core, so the tests now fake
the cell and the client instead of the env.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from hull_core.providers.openai_spec import ProviderError

from better_code_review_graph.summarizer import (
    NodeNeedingSummary,
    batch_summarize,
    compute_source_hash,
    compute_summary_cache_key,
    summarize_node_async,
)


# ---------------------------------------------------------------------------
# compute_source_hash
# ---------------------------------------------------------------------------


def test_compute_source_hash_is_sha256():
    import hashlib

    body = "def f():\n    return 1\n"
    assert compute_source_hash(body) == hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_compute_source_hash_empty_string():
    assert compute_source_hash("") == hashlib.sha256(b"").hexdigest()


def test_compute_source_hash_handles_unicode():
    body = "def f():\n    return 'héllo wörld ☃'\n"
    assert compute_source_hash(body) == hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# NodeNeedingSummary + cache key
# ---------------------------------------------------------------------------


def test_node_needing_summary_is_frozen():
    node = NodeNeedingSummary(
        node_id="x.py::f", source_text="def f(): pass", source_hash=None
    )
    with pytest.raises(AttributeError):
        node.source_text = "mutated"


def test_cache_key_combines_source_hash_and_provider():
    node = NodeNeedingSummary(
        node_id="x.py::f", source_text="def f(): pass", source_hash="abc123"
    )
    key = compute_summary_cache_key(node, "openai/gpt-4o-mini")
    assert key == "abc123:openai/gpt-4o-mini"


def test_cache_key_changes_when_provider_changes():
    node = NodeNeedingSummary(
        node_id="x.py::f", source_text="def f(): pass", source_hash="abc123"
    )
    assert compute_summary_cache_key(
        node, "openai/gpt-4o-mini"
    ) != compute_summary_cache_key(node, "gemini/gemini-2.5-flash")


def test_cache_key_uses_precomputed_hash_when_provided():
    node = NodeNeedingSummary(
        node_id="x.py::f",
        source_text="def f(): pass",
        source_hash="deadbeef",
    )
    # A precomputed hash must be trusted verbatim, not recomputed from
    # source_text (which would produce a different digest than "deadbeef").
    key = compute_summary_cache_key(node, "p")
    assert key.startswith("deadbeef:")


def test_cache_key_hashes_source_text_when_hash_absent():
    node = NodeNeedingSummary(
        node_id="x.py::f", source_text="def f(): pass", source_hash=None
    )
    key = compute_summary_cache_key(node, "p")
    assert key == f"{compute_source_hash('def f(): pass')}:p"


# ---------------------------------------------------------------------------
# summary_cell resolution (host-owned chat cell)
# ---------------------------------------------------------------------------


def _cell(**overrides):
    base = {
        "task": "chat",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "k-test",
        "model": "openai/gpt-4o-mini",
        "configured": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_summary_cell_none_when_not_configured(monkeypatch):
    import better_code_review_graph.config as cfg

    monkeypatch.setattr(
        cfg, "resolve_cells", lambda *a, **k: {"chat": _cell(configured=False)}
    )
    from better_code_review_graph.summarizer import summary_cell

    assert summary_cell() is None


def test_summary_cell_returns_configured_cell(monkeypatch):
    import better_code_review_graph.config as cfg

    cell = _cell()
    monkeypatch.setattr(cfg, "resolve_cells", lambda *a, **k: {"chat": cell})
    from better_code_review_graph.summarizer import summary_cell

    assert summary_cell() is cell


# ---------------------------------------------------------------------------
# summarize_node_async (single-node LLM call through the shared client)
# ---------------------------------------------------------------------------


class FakeClient:
    """Stand-in for hull's OpenAICompatClient (async chat + aclose)."""

    def __init__(self, replies=None, error: Exception | None = None):
        self.replies = list(replies or [])
        self.error = error
        self.calls: list[list[dict]] = []
        self.closed = False
        self.cell = SimpleNamespace(model="openai/gpt-4o-mini")

    async def chat(self, messages, **options):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.replies.pop(0)

    async def aclose(self):
        self.closed = True


def _node(body: str = "def f(): return 1") -> NodeNeedingSummary:
    return NodeNeedingSummary(
        node_id="x.py::f",
        source_text=body,
        source_hash=compute_source_hash(body),
    )


def test_summarize_node_returns_stripped_text():
    client = FakeClient(replies=["  Returns 1.  \n"])
    out = asyncio.run(summarize_node_async(_node(), client))
    assert out == "Returns 1."
    assert len(client.calls) == 1
    prompt = client.calls[0][0]["content"]
    assert "def f(): return 1" in prompt


def test_summarize_node_wraps_provider_errors():
    client = FakeClient(error=ProviderError(503, "boom"))
    with pytest.raises(RuntimeError, match="summarize_node failed"):
        asyncio.run(summarize_node_async(_node(), client))


def test_summarize_node_empty_content_raises():
    client = FakeClient(replies=["   "])
    with pytest.raises(RuntimeError, match="empty/None content"):
        asyncio.run(summarize_node_async(_node(), client))


def test_summarize_node_handles_braces_in_source():
    # Source containing literal braces must not break prompt construction
    # (concatenation, never str.format).
    body = 'def f():\n    return {"a": {1}}  # f-string {x}\n'
    client = FakeClient(replies=["ok"])
    out = asyncio.run(summarize_node_async(_node(body), client))
    assert out == "ok"


# ---------------------------------------------------------------------------
# GraphStore.update_summary persistence
# ---------------------------------------------------------------------------


def test_update_summary_persists_to_db(tmp_path):
    """GraphStore.update_summary should write summary + provider + source_hash atomically."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        node_id = store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="h",
        )
        store.update_summary(
            node_id, summary="A summary.", provider="gemini", source_hash="abc123"
        )
        row = store._conn.execute(
            "SELECT summary, summary_provider, source_hash FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] == "A summary."
        assert row[1] == "gemini"
        assert row[2] == "abc123"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# batch_summarize (queue shape, cache behaviour, per-node fail-open)
# ---------------------------------------------------------------------------


def _seed_function(store, name: str = "f", body: str = "def f(): return 1") -> int:
    from better_code_review_graph.parser import NodeInfo

    node_id = store.upsert_node(
        NodeInfo(
            kind="Function",
            name=name,
            file_path="x.py",
            line_start=1,
            line_end=2,
            language="python",
        ),
        file_hash="h",
    )
    store._conn.execute(
        "UPDATE nodes SET source_text=? WHERE id=?", (body, node_id)
    )
    store._conn.commit()
    return node_id


def _patched_llm(client: FakeClient, cell=None):
    """Patch summary_cell + OpenAICompatClient so batch runs against ``client``."""
    return (
        patch(
            "better_code_review_graph.summarizer.summary_cell",
            return_value=cell or _cell(),
        ),
        patch(
            "better_code_review_graph.summarizer.OpenAICompatClient",
            return_value=client,
        ),
    )


def test_batch_summarize_skips_when_no_provider(tmp_path, monkeypatch):
    """With no chat cell configured, batch_summarize skips without calling the LLM."""
    import better_code_review_graph.config as cfg
    from better_code_review_graph.graph import GraphStore

    monkeypatch.setattr(
        cfg, "resolve_cells", lambda *a, **k: {"chat": _cell(configured=False)}
    )
    monkeypatch.delenv("HULL_CHAT_API_KEY", raising=False)

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        result = batch_summarize(store, max_nodes=10)
        assert result.skipped_no_provider is True
        assert result.generated == 0
        assert result.cached == 0
        assert result.provider is None
    finally:
        store.close()


def test_batch_summarize_generates_for_uncached_nodes(tmp_path):
    """Function nodes without summary should be sent to LLM and result persisted."""
    from better_code_review_graph.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        node_id = _seed_function(store)
        client = FakeClient(replies=["Returns 1."])
        p_cell, p_client = _patched_llm(client)
        with p_cell, p_client:
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.cached == 0
        assert result.skipped_no_provider is False
        assert result.provider == "openai/gpt-4o-mini"
        row = store._conn.execute(
            "SELECT summary, summary_provider, source_hash FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] == "Returns 1."
        assert row[1] == "openai/gpt-4o-mini"
        assert row[2] == compute_source_hash("def f(): return 1")
        assert client.closed, "batch must close the shared client"
    finally:
        store.close()


def test_batch_summarize_cache_hit_when_hash_and_provider_match(tmp_path):
    from better_code_review_graph.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        node_id = _seed_function(store)
        body_hash = compute_source_hash("def f(): return 1")
        store.update_summary(
            node_id,
            summary="Cached.",
            provider="openai/gpt-4o-mini",
            source_hash=body_hash,
        )

        client = FakeClient(replies=["should not be called"])
        p_cell, p_client = _patched_llm(client)
        with p_cell, p_client:
            result = batch_summarize(store, max_nodes=10)

        assert result.cached == 1
        assert result.generated == 0
        assert client.calls == [], "cache hit must not hit the LLM"
    finally:
        store.close()


def test_batch_summarize_regenerates_when_source_changed(tmp_path):
    from better_code_review_graph.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        node_id = _seed_function(store)
        store.update_summary(
            node_id,
            summary="Stale summary.",
            provider="openai/gpt-4o-mini",
            source_hash="stale-hash",
        )

        client = FakeClient(replies=["Fresh summary."])
        p_cell, p_client = _patched_llm(client)
        with p_cell, p_client:
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.cached == 0
        row = store._conn.execute(
            "SELECT summary, source_hash FROM nodes WHERE id=?", (node_id,)
        ).fetchone()
        assert row[0] == "Fresh summary."
        assert row[1] == compute_source_hash("def f(): return 1")
    finally:
        store.close()


def test_batch_summarize_treats_empty_string_summary_as_cache_miss(tmp_path):
    from better_code_review_graph.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        node_id = _seed_function(store)
        body_hash = compute_source_hash("def f(): return 1")
        store.update_summary(
            node_id, summary="", provider="openai/gpt-4o-mini", source_hash=body_hash
        )

        client = FakeClient(replies=["Regenerated."])
        p_cell, p_client = _patched_llm(client)
        with p_cell, p_client:
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.cached == 0
        row = store._conn.execute(
            "SELECT summary FROM nodes WHERE id=?", (node_id,)
        ).fetchone()
        assert row[0] == "Regenerated."
    finally:
        store.close()


def test_batch_summarize_respects_max_nodes_cap(tmp_path):
    from better_code_review_graph.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        for i in range(5):
            _seed_function(store, name=f"f{i}", body=f"def f{i}(): return {i}")

        client = FakeClient(replies=[f"s{i}" for i in range(5)])
        p_cell, p_client = _patched_llm(client)
        with p_cell, p_client:
            result = batch_summarize(store, max_nodes=2)

        assert result.generated == 2
        assert len(client.calls) == 2, "cap must bound LLM calls per run"
    finally:
        store.close()


def test_batch_summarize_continues_after_per_node_error(tmp_path):
    """If one node's LLM call raises, batch should count error + continue with others."""
    from better_code_review_graph.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        _seed_function(store, name="f0", body="def f0(): return 0")
        _seed_function(store, name="f1", body="def f1(): return 1")

        class FlakyClient(FakeClient):
            async def chat(self, messages, **options):
                if len(self.calls) == 0:
                    self.calls.append(messages)
                    raise ProviderError("transient provider hiccup")
                return self.replies.pop(0)

        client = FlakyClient(replies=["ok"])
        p_cell, p_client = _patched_llm(client)
        with p_cell, p_client:
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.errors == 1
    finally:
        store.close()


def test_batch_summarize_rejects_nonpositive_max_nodes(tmp_path):
    from better_code_review_graph.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        with pytest.raises(ValueError, match="max_nodes"):
            batch_summarize(store, max_nodes=0)
    finally:
        store.close()
