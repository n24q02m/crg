"""Tests for host-configured LLM summaries (post-de-host hull model cells).

Covers the pure helpers (``compute_source_hash``, ``compute_summary_cache_key``,
``NodeNeedingSummary`` immutability), the chat-cell resolution seam
(``summary_cell``, which returns the cell plus its credential pool), the
single-node ``summarize_node_async`` LLM call through ``AttemptClient``, and
the ``batch_summarize`` queue/cache behaviour against a real ``GraphStore``.

The pre-de-host tests drove the summary-model env vars and patched
``summarize_node``; the de-host cut replaced that with one host-owned
``[models.chat]`` cell, and hull's provider pool now owns key rotation, so
the tests fake the pooled cell and the per-attempt client instead of the env.
"""

from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest
from hull_core.config.models import ModelCell
from hull_core.credentials import KeyPool
from hull_core.providers.openai_spec import OpenAICompatClient, ProviderError

from crg.summarizer import (
    BatchSummarizeResult,
    JevRankingReceipt,
    NodeNeedingSummary,
    _parse_jev_ranking,
    batch_summarize,
    compute_source_hash,
    compute_summary_cache_key,
    summarize_node_async,
)


def _receipt(result: BatchSummarizeResult) -> JevRankingReceipt:
    """The jev receipt of a run that reached the queue (only the skip path has none)."""
    assert result.jev_ranking is not None
    return result.jev_ranking


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
        node.__setattr__("source_text", "mutated")


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
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakePool:
    """One healthy credential standing in for hull's ``KeyPool``.

    Only the surface ``crg.credentials._ServeRotation`` touches; rotation
    itself is pinned in ``tests/test_credentials.py``.
    """

    max_5xx_retries = 1

    def __init__(self) -> None:
        self.credential = SimpleNamespace(
            id=1, api_key="k-test", base_url="https://openrouter.ai/api/v1"
        )
        self.successes = 0

    def credentials(self):
        return [self.credential]

    def acquire(self, *, exclude=()):
        if self.credential.id in exclude:
            raise AssertionError("the only fake credential was excluded")
        return self.credential

    def report_success(self, credential):
        self.successes += 1

    def report_failure(self, credential, status, **hints):
        return "fatal"

    def redact(self, text):
        return text or ""

    def exhausted_error(self, *, last_error=None):
        raise AssertionError("the fake pool never exhausts")

    @staticmethod
    def status_of(error):
        return getattr(error, "status", None)


def _pooled_cell(task: str = "chat", model: str = "openai/gpt-4o-mini"):
    """A configured cell plus its pool, as ``summary_cell`` returns it."""
    from crg.credentials import PooledCell

    return PooledCell(
        task=task,
        provider="openrouter",
        account_id=None,
        cell=ModelCell(
            task=task,
            base_url="https://openrouter.ai/api/v1",
            api_key="k-test",
            model=model,
        ),
        pool=cast(KeyPool, _FakePool()),
        auth_mode="no-auth",
    )


def test_summary_cell_none_when_not_configured(monkeypatch):
    import crg.config as cfg

    monkeypatch.setattr(
        cfg, "resolve_cells", lambda *a, **k: {"chat": _cell(api_key="")}
    )
    monkeypatch.delenv("HULL_CHAT_API_KEY", raising=False)
    from crg.summarizer import summary_cell

    assert summary_cell() is None


def test_jev_score_cell_fails_open_when_resolution_raises(monkeypatch):
    """An unreadable config may only disable ranking, never the queue."""
    import crg.credentials as credentials

    def boom(*args, **kwargs):
        raise RuntimeError("unreadable config")

    monkeypatch.setattr(credentials, "resolve_pool", boom)
    from crg.summarizer import jev_score_cell

    assert jev_score_cell() is None


def test_summary_cell_returns_configured_cell(monkeypatch):
    import crg.config as cfg

    cell = _cell()
    monkeypatch.setattr(cfg, "resolve_cells", lambda *a, **k: {"chat": cell})
    monkeypatch.delenv("HULL_CHAT_API_KEY", raising=False)
    from crg.summarizer import summary_cell

    pooled = summary_cell()
    assert pooled is not None
    assert pooled.cell is cell


# ---------------------------------------------------------------------------
# summarize_node_async (single-node LLM call through the shared client)
# ---------------------------------------------------------------------------


class FakeClient(OpenAICompatClient):
    """Stand-in for hull's OpenAICompatClient (async chat + aclose).

    Subclasses the real client so ``summarize_node_async``'s declared
    contract holds; ``__init__`` deliberately skips the base SSRF/httpx
    wiring because the scripted ``chat``/``aclose`` never touch the wire.
    """

    def __init__(self, replies=None, error: Exception | None = None):
        self.cell = ModelCell(
            task="chat",
            base_url="https://openrouter.ai/api/v1",
            api_key="k-test",
            model="openai/gpt-4o-mini",
        )
        self.replies = list(replies or [])
        self.error = error
        self.calls: list[list[dict]] = []
        self.closed = False

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
    """The failure keeps its status so the credential pool can rotate on it."""
    from crg.credentials import ProviderCallError

    client = FakeClient(error=ProviderCallError(429, "boom", retry_after="12"))
    with pytest.raises(ProviderCallError, match="summarize_node failed") as excinfo:
        asyncio.run(summarize_node_async(_node(), client))
    assert excinfo.value.status == 429
    assert excinfo.value.retry_after == "12"


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
    from crg.graph import GraphStore
    from crg.parser import NodeInfo

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
    from crg.parser import NodeInfo

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
    store._conn.execute("UPDATE nodes SET source_text=? WHERE id=?", (body, node_id))
    store._conn.commit()
    return node_id


def _patched_llm(client: FakeClient, cell=None):
    """Patch summary_cell + AttemptClient so batch runs against ``client``."""
    return (
        patch(
            "crg.summarizer.summary_cell",
            return_value=cell or _pooled_cell(),
        ),
        patch(
            "crg.summarizer.AttemptClient",
            return_value=client,
        ),
    )


def test_batch_summarize_skips_when_no_provider(tmp_path, monkeypatch):
    """With no chat cell configured, batch_summarize skips without calling the LLM."""
    import crg.config as cfg
    from crg.graph import GraphStore

    monkeypatch.setattr(
        cfg, "resolve_cells", lambda *a, **k: {"chat": _cell(api_key="")}
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
    from crg.graph import GraphStore

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
    from crg.graph import GraphStore

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
    from crg.graph import GraphStore

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
    from crg.graph import GraphStore

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
    from crg.graph import GraphStore

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
    from crg.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        _seed_function(store, name="f0", body="def f0(): return 0")
        _seed_function(store, name="f1", body="def f1(): return 1")

        class FlakyClient(FakeClient):
            async def chat(self, messages, **options):
                if len(self.calls) == 0:
                    self.calls.append(messages)
                    raise ProviderError(503, "transient provider hiccup")
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
    from crg.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        with pytest.raises(ValueError, match="max_nodes"):
            batch_summarize(store, max_nodes=0)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# jev queue ranking (spec §7 K4): base ORDER BY + advisory batch re-rank
# ---------------------------------------------------------------------------


class FakeJevClient:
    """Stand-in jev client: scripted ranking replies, or a hard failure."""

    def __init__(self, replies=None, error: Exception | None = None):
        self.replies = list(replies or [])
        self.error = error
        self.prompts: list[str] = []
        self.closed = False
        self.cell = SimpleNamespace(model="z-ai/glm-5.3-flash", task="jev_score")

    async def chat(self, messages, **options):
        self.prompts.append(messages[0]["content"])
        if self.error is not None:
            raise self.error
        return self.replies.pop(0)

    async def aclose(self):
        self.closed = True


def _patched_chat_and_jev(chat_client: FakeClient, jev_client: FakeJevClient):
    """Patch both cells + OpenAICompatClient, dispatching fakes on cell.task."""

    def _factory(cell, **_kwargs):
        return jev_client if getattr(cell, "task", None) == "jev_score" else chat_client

    return (
        patch("crg.summarizer.summary_cell", return_value=_pooled_cell()),
        patch(
            "crg.summarizer.jev_score_cell",
            return_value=_pooled_cell(task="jev_score"),
        ),
        patch(
            "crg.summarizer.AttemptClient",
            side_effect=_factory,
        ),
    )


def _processed_order(names: list[str], client: FakeClient) -> list[str]:
    """Map recorded LLM calls back to the function each prompt carried."""
    order = []
    for call in client.calls:
        content = call[0]["content"]
        order.append(next(n for n in names if f"def {n}()" in content))
    return order


def test_parse_jev_ranking_valid_permutation():
    assert _parse_jev_ranking("Prioritized: [2, 0, 3, 1]", 4) == [2, 0, 3, 1]


def test_parse_jev_ranking_tolerates_float_tokens():
    # mnemo-wp4-writer precedent regex; float-looking tokens floor to indices
    assert _parse_jev_ranking("[1.0, 0.0, 3.0, 2.0]", 4) == [1, 0, 3, 2]


def test_parse_jev_ranking_skips_out_of_range_and_duplicates():
    assert _parse_jev_ranking("[9, 0, 0, 1, 2]", 3) == [0, 1, 2]


def test_parse_jev_ranking_raises_on_no_numbers():
    with pytest.raises(ValueError, match="no numeric tokens"):
        _parse_jev_ranking("I cannot rank these.", 2)


def test_parse_jev_ranking_raises_on_incomplete_permutation():
    with pytest.raises(ValueError, match="incomplete"):
        _parse_jev_ranking("[0, 1]", 3)


def test_batch_summarize_orders_queue_by_ascending_id(tmp_path):
    """Base queue order is deterministic: ascending node id (spec §7 K4)."""
    from crg.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        names = [f"fn{i}" for i in range(8)]
        for name in names:
            _seed_function(store, name=name, body=f"def {name}(): return 1")

        client = FakeClient(replies=["s"] * 8)
        p_cell, p_client = _patched_llm(client)
        with p_cell, p_client:
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 8
        assert _receipt(result).used is False  # autouse fixture keeps jev off
        assert _processed_order(names, client) == names
    finally:
        store.close()


def test_batch_summarize_jev_ranking_reorders_queue_and_records_receipt(tmp_path):
    """jev ranking re-orders processing; the receipt records it (spec §7 K4)."""
    from crg.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        names = ["fn0", "fn1", "fn2", "fn3"]
        for name in names:
            _seed_function(store, name=name, body=f"def {name}(): return 1")

        jev = FakeJevClient(replies=["[3, 1, 0, 2]"])
        chat = FakeClient(replies=["s"] * 4)
        p_cell, p_jev, p_client = _patched_chat_and_jev(chat, jev)
        with p_cell, p_jev, p_client:
            result = batch_summarize(store, max_nodes=10)

        assert _receipt(result).used is True
        assert _receipt(result).batches == 1
        assert _receipt(result).ranked_nodes == 4
        assert _receipt(result).failopen_reason is None
        assert len(jev.prompts) == 1, "one jev call per ~50-node batch"
        assert _processed_order(names, chat) == ["fn3", "fn1", "fn0", "fn2"]
        assert chat.closed and jev.closed, "both shared clients must be closed"
        assert result.generated == 4
        assert result.errors == 0
    finally:
        store.close()


def test_batch_summarize_jev_ranks_in_batches_of_50_one_call_each(tmp_path):
    """120 pending nodes → exactly 3 jev calls (50+50+20), one per batch."""
    from crg.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        names = [f"fn{i}" for i in range(120)]
        for name in names:
            _seed_function(store, name=name, body=f"def {name}(): return 1")

        def perm(n: int) -> str:
            return "[" + ", ".join(str(i) for i in range(n - 1, -1, -1)) + "]"

        jev = FakeJevClient(replies=[perm(50), perm(50), perm(20)])
        chat = FakeClient(replies=["s"] * 120)
        p_cell, p_jev, p_client = _patched_chat_and_jev(chat, jev)
        with p_cell, p_jev, p_client:
            result = batch_summarize(store, max_nodes=200)

        assert _receipt(result).used is True
        assert _receipt(result).batches == 3
        assert _receipt(result).ranked_nodes == 120
        assert len(jev.prompts) == 3, "exactly one jev call per ~50-node batch"
        assert len(chat.calls) == 120
        order = _processed_order(names, chat)
        # each batch's reversed perm decides processing order inside the batch
        assert order[0] == "fn49"
        assert order[49] == "fn0"
        assert order[50] == "fn99"
        assert order[99] == "fn50"
        assert order[100] == "fn119"
        assert order[119] == "fn100"
    finally:
        store.close()


def test_batch_summarize_jev_failure_falls_open_to_base_order(tmp_path):
    """jev call failure → queue processed in base ORDER BY order, run completes."""
    from crg.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        names = ["fn0", "fn1", "fn2", "fn3"]
        for name in names:
            _seed_function(store, name=name, body=f"def {name}(): return 1")

        jev = FakeJevClient(error=ProviderError(503, "jev unavailable"))
        chat = FakeClient(replies=["s"] * 4)
        p_cell, p_jev, p_client = _patched_chat_and_jev(chat, jev)
        with p_cell, p_jev, p_client:
            result = batch_summarize(store, max_nodes=10)

        assert _receipt(result).used is False
        assert _receipt(result).failopen_reason is not None
        assert result.generated == 4
        assert result.errors == 0, "summary batch must be unaffected by jev failure"
        assert _processed_order(names, chat) == names, "queue stays in base order"
        assert jev.closed, "jev client must be closed even when ranking fails"
    finally:
        store.close()


def test_batch_summarize_jev_unparseable_reply_falls_open(tmp_path):
    """A reply with no numeric tokens raises in the ranking layer → fail-open."""
    from crg.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        names = ["fn0", "fn1", "fn2", "fn3"]
        for name in names:
            _seed_function(store, name=name, body=f"def {name}(): return 1")

        jev = FakeJevClient(replies=["I cannot rank these functions."])
        chat = FakeClient(replies=["s"] * 4)
        p_cell, p_jev, p_client = _patched_chat_and_jev(chat, jev)
        with p_cell, p_jev, p_client:
            result = batch_summarize(store, max_nodes=10)

        receipt = _receipt(result)
        assert receipt.used is False
        assert receipt.failopen_reason is not None
        assert "no numeric tokens" in receipt.failopen_reason
        assert result.generated == 4
        assert _processed_order(names, chat) == names, "queue stays in base order"
    finally:
        store.close()


def test_batch_summarize_without_jev_cell_skips_ranking_silently(tmp_path):
    """No jev cell configured → base order; receipt says disabled, no reason."""
    from crg.graph import GraphStore

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        names = ["fn0", "fn1", "fn2"]
        for name in names:
            _seed_function(store, name=name, body=f"def {name}(): return 1")

        client = FakeClient(replies=["s"] * 3)
        p_cell, p_client = _patched_llm(client)
        with p_cell, p_client:
            result = batch_summarize(store, max_nodes=10)

        assert _receipt(result).used is False
        assert _receipt(result).failopen_reason is None
        assert result.generated == 3
        assert _processed_order(names, client) == names
    finally:
        store.close()
