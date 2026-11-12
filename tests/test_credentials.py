"""Provider credential pools: rotation, health, and legacy-key migration.

The pre-pool crg resolved exactly one ``api_key`` per provider, so one 401 or
429 took the cloud path down. These tests pin the adoption of hull's
``CredentialStore``/``KeyPool``:

- a 429 rotates to the next key and honours ``Retry-After``,
- a 401 disables the key so later calls skip it,
- exhaustion surfaces as crg's redacted :class:`PoolUnavailableError`,
- a legacy ``HULL_<TASK>_API_KEY`` / ``config.toml`` key is migrated into the
  pool once, idempotently, and the env var is left untouched,
- ``[models.<task>].account`` scopes a task to one named account's pool,
- concurrent leases never hand the same key to two callers.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import httpx
import pytest
from hull_core.config.models import ModelCell
from hull_core.credentials import CredentialStore

from crg.credentials import (
    CREDENTIALS_DB_ENV,
    AttemptClient,
    CredentialsConfigError,
    PoolUnavailableError,
    ProviderCallError,
    arun_pooled,
    configured_tasks,
    credentials_store,
    migrate_legacy_cells,
    provider_identity,
    reset_credentials_store,
    resolve_pool,
)

LOOPBACK = "http://127.0.0.1:9/v1"
PROVIDER = "test-provider"


@pytest.fixture(autouse=True)
def _isolated_pool(monkeypatch, tmp_path):
    """One credential database per test, with the process cache cleared."""
    monkeypatch.setenv(CREDENTIALS_DB_ENV, str(tmp_path / "pool.db"))
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "cfg"))
    reset_credentials_store()
    try:
        yield
    finally:
        reset_credentials_store()


@pytest.fixture
def store() -> CredentialStore:
    return credentials_store()


def _cell(*, task: str = "chat", api_key: str = "", account: str = "") -> ModelCell:
    return ModelCell(
        task=task,
        base_url=LOOPBACK,
        api_key=api_key,
        model="test/model",
        provider=PROVIDER,
        account=account,
    )


def _two_key_pool(store: CredentialStore) -> Any:
    store.add_credential(PROVIDER, "sk-first-key", base_url=LOOPBACK)
    store.add_credential(PROVIDER, "sk-second-key", base_url=LOOPBACK)
    return store.pool(PROVIDER)


def _keys(pool: Any) -> dict[int, str]:
    return {row.id: row.api_key for row in pool.credentials()}


# ---------------------------------------------------------------------------
# Rotation policy
# ---------------------------------------------------------------------------


def test_429_rotates_to_the_next_key(store):
    """A rate-limited key cools down and the call is retried on the next key."""
    pool = _two_key_pool(store)
    keys = _keys(pool)
    seen: list[str] = []

    async def call(credential):
        seen.append(credential.api_key)
        if credential.api_key == "sk-first-key":
            raise ProviderCallError(429, "slow down", retry_after="7")
        return "answer"

    assert asyncio_run(arun_pooled, pool, _cell(), call) == "answer"
    assert seen == ["sk-first-key", "sk-second-key"]

    cooled = pool.health()[0]
    assert cooled.last_status == 429
    assert cooled.disabled is False
    # Retry-After wins over hull's 60s default, clamped to the pool's range.
    assert 0 < cooled.cooldown_remaining <= 7
    assert keys[cooled.id] == "sk-first-key"


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_disables_the_key_for_later_calls(store, status):
    """A rejected key is disabled, so the next run never touches it again."""
    pool = _two_key_pool(store)
    first_run: list[str] = []

    async def rejected(credential):
        first_run.append(credential.api_key)
        if credential.api_key == "sk-first-key":
            raise ProviderCallError(status, "invalid api key")
        return "answer"

    assert asyncio_run(arun_pooled, pool, _cell(), rejected) == "answer"
    assert first_run == ["sk-first-key", "sk-second-key"]
    assert pool.health()[0].disabled is True

    second_run: list[str] = []

    async def accepted(credential):
        second_run.append(credential.api_key)
        return "answer"

    assert asyncio_run(arun_pooled, pool, _cell(), accepted) == "answer"
    assert second_run == ["sk-second-key"]


def test_rotation_never_spends_an_entry_for_another_endpoint(store):
    """An entry bound to a different endpoint is skipped, not rotated into."""
    store.add_credential(
        PROVIDER,
        "sk-embed-key",
        base_url="https://embed.example/v1",
        model="cohere/embed-v4.0",
    )
    store.add_credential(PROVIDER, "sk-chat-key", base_url=LOOPBACK, model="test/model")
    pool = store.pool(PROVIDER)
    seen: list[str] = []

    async def call(credential):
        seen.append(credential.api_key)
        return "answer"

    assert asyncio_run(arun_pooled, pool, _cell(), call) == "answer"
    assert seen == ["sk-chat-key"]


def test_5xx_retries_the_same_key_once_then_moves_on(store):
    """A server error is not the credential's fault: retry it, then rotate."""
    pool = _two_key_pool(store)
    seen: list[str] = []

    async def flaky(credential):
        seen.append(credential.api_key)
        if credential.api_key == "sk-first-key":
            raise ProviderCallError(503, "upstream unavailable")
        return "answer"

    assert asyncio_run(arun_pooled, pool, _cell(), flaky) == "answer"
    # One retry on the same key, then the pool moves to the next credential.
    assert seen == ["sk-first-key", "sk-first-key", "sk-second-key"]
    assert pool.health()[0].failure_count == 2
    assert pool.health()[0].disabled is False


def test_single_key_5xx_exhausts_the_rotation(store):
    """The pool's retry budget is bounded: two 5xx on one key end the call."""
    store.add_credential(PROVIDER, "sk-only-key", base_url=LOOPBACK)
    pool = store.pool(PROVIDER)
    calls: list[str] = []

    async def unavailable(credential):
        calls.append(credential.api_key)
        raise ProviderCallError(503, "upstream unavailable")

    with pytest.raises(PoolUnavailableError) as excinfo:
        asyncio_run(arun_pooled, pool, _cell(), unavailable)
    # One attempt + one 5xx retry, then the rotation is out of budget.
    assert calls == ["sk-only-key", "sk-only-key"]
    assert "sk-only-key" not in str(excinfo.value)


def test_non_http_failure_does_not_blame_the_credential(store):
    """A request-level error re-raises and leaves the key's health alone."""
    pool = _two_key_pool(store)

    async def broken(credential):
        raise ValueError("invalid request body")

    with pytest.raises(ValueError, match="invalid request body"):
        asyncio_run(arun_pooled, pool, _cell(), broken)
    assert pool.health()[0].failure_count == 0
    assert pool.health()[0].lease_until == 0


# ---------------------------------------------------------------------------
# Exhaustion
# ---------------------------------------------------------------------------


def test_exhaustion_is_redacted_and_carries_retry_after(store):
    """Every key cooling down raises crg's error without leaking a key."""
    pool = _two_key_pool(store)

    async def rate_limited(credential):
        raise ProviderCallError(
            429,
            f"key {credential.api_key} is rate limited",
            retry_after="42",
        )

    with pytest.raises(PoolUnavailableError) as excinfo:
        asyncio_run(arun_pooled, pool, _cell(), rate_limited)

    error = excinfo.value
    message = str(error)
    assert "sk-first-key" not in message
    assert "sk-second-key" not in message
    assert "[redacted]" in message
    assert "retry in" in message
    assert error.provider == PROVIDER
    assert (error.total, error.cooling_down) == (2, 2)
    assert error.retry_after is not None
    assert 0 < error.retry_after <= 42
    assert error.last_error is not None
    assert "sk-first-key" not in error.last_error


def test_empty_pool_reports_nothing_usable(store):
    """An empty provider pool must fail closed with counts, not a key error."""
    pool = store.pool(PROVIDER)

    async def unreachable(credential):  # pragma: no cover - never called
        raise AssertionError("an empty pool must not dispatch")

    with pytest.raises(PoolUnavailableError) as excinfo:
        asyncio_run(arun_pooled, pool, _cell(), unreachable)
    assert excinfo.value.total == 0
    assert "no usable" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Legacy single-key setups
# ---------------------------------------------------------------------------


def test_legacy_env_key_is_migrated_once_and_left_in_place(monkeypatch, store):
    """The existing HULL_<TASK>_API_KEY keeps working and is never consumed."""
    monkeypatch.setenv("HULL_EMBED_API_KEY", "sk-legacy-embed")
    monkeypatch.delenv("HULL_CHAT_API_KEY", raising=False)

    pooled = resolve_pool("embed")
    assert pooled.configured is True
    assert pooled.pool is not None
    assert [row.api_key for row in pooled.pool.credentials()] == ["sk-legacy-embed"]

    # Second resolution re-runs the (idempotent) migration: no duplicate row.
    again = resolve_pool("embed")
    assert again.pool is not None
    assert len(again.pool.credentials()) == 1

    import os

    assert os.environ["HULL_EMBED_API_KEY"] == "sk-legacy-embed"
    # The live cell still owns the model — the pool only supplies key+endpoint.
    assert pooled.cell.api_key == "sk-legacy-embed"


def test_migration_wraps_a_missing_account(store):
    """A keyed cell pointing at an unregistered account fails loudly."""
    cell = _cell(api_key="sk-legacy", account="ghost-account")
    with pytest.raises(CredentialsConfigError, match="ghost-account"):
        migrate_legacy_cells({"chat": cell}, store=store)


def test_migration_is_idempotent(store):
    """Re-running the migration adds nothing and skips the known key."""
    cells = {"embed": _cell(task="embed", api_key="sk-file-key")}

    first = migrate_legacy_cells(cells, store=store)
    assert [(row.provider, row.added, row.skipped) for row in first] == [
        (PROVIDER, 1, 0)
    ]

    # Clear the process-level guard to exercise hull's duplicate refusal too.
    reset_credentials_store()
    fresh = CredentialStore(store.path)
    try:
        second = migrate_legacy_cells(cells, store=fresh)
        assert [(row.added, row.skipped) for row in second] == [(0, 1)]
        assert len(fresh.pool(PROVIDER).credentials()) == 1
    finally:
        fresh.close()


def test_keyless_cell_with_empty_pool_is_not_configured(store):
    """No cell key and no pool entry is the "local / summaries off" state."""
    pooled = resolve_pool("chat")
    assert pooled.configured is False
    assert pooled.pool is None
    assert configured_tasks() == []


def test_pool_only_key_counts_as_configured(store):
    """A key added to hull's pool alone configures the task."""
    cell = resolve_pool("chat").cell
    store.add_credential(
        provider_identity(cell), "sk-pool-only", base_url=cell.base_url
    )

    pooled = resolve_pool("chat")
    assert pooled.configured is True
    assert pooled.account_id is None
    # An entry with no model is provider-wide: every task on that endpoint.
    assert configured_tasks() == ["embed", "rerank", "chat", "jev_score"]


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def test_named_account_scopes_the_pool(store, tmp_path):
    """``[models.chat].account`` reads that account's pool, not the default."""
    account = store.accounts().add(provider=PROVIDER, name="day-job")
    store.add_credential(PROVIDER, "sk-default-key", base_url=LOOPBACK)
    store.add_credential(
        PROVIDER, "sk-account-key", base_url=LOOPBACK, account_id=account.account_id
    )
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.toml").write_text(
        "[models.chat]\n"
        f'provider = "{PROVIDER}"\n'
        f'base_url = "{LOOPBACK}"\n'
        f'account = "{account.account_id}"\n'
        'model = "test/model"\n',
        encoding="utf-8",
    )

    pooled = resolve_pool("chat")
    assert pooled.account_id == account.account_id
    assert pooled.pool is not None
    assert [row.api_key for row in pooled.pool.credentials()] == ["sk-account-key"]


def test_unknown_account_is_a_config_error(store, tmp_path):
    """A configured account that is not registered fails loudly."""
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.toml").write_text(
        '[models.chat]\naccount = "ghost"\n', encoding="utf-8"
    )

    with pytest.raises(CredentialsConfigError, match="not in hull's account registry"):
        resolve_pool("chat")


def test_account_of_another_provider_is_a_config_error(store, tmp_path):
    """An account registered for a different provider cannot serve this cell."""
    store.accounts().add(provider="other-provider", name="elsewhere")
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.toml").write_text(
        "[models.chat]\n"
        f'provider = "{PROVIDER}"\n'
        f'base_url = "{LOOPBACK}"\n'
        'account = "other-provider:elsewhere"\n',
        encoding="utf-8",
    )

    with pytest.raises(CredentialsConfigError, match="belongs to provider"):
        resolve_pool("chat")


# ---------------------------------------------------------------------------
# Provider identity
# ---------------------------------------------------------------------------


def test_credentials_db_path_prefers_the_override(monkeypatch, tmp_path):
    from crg.credentials import credentials_db_path

    override = tmp_path / "custom.db"
    monkeypatch.setenv(CREDENTIALS_DB_ENV, str(override))
    assert credentials_db_path() == override

    monkeypatch.delenv(CREDENTIALS_DB_ENV)
    assert credentials_db_path().name == "hull.db"


def test_reset_is_idempotent():
    reset_credentials_store()
    reset_credentials_store()
    assert credentials_store().path.exists()


def test_ssrf_transport_follows_the_auth_mode():
    from hull_core.http.ssrf import AsyncSSRFSafeTransport

    from crg.credentials import _ssrf_transport

    assert isinstance(_ssrf_transport("no-auth"), AsyncSSRFSafeTransport)
    assert isinstance(_ssrf_transport("token"), AsyncSSRFSafeTransport)


def test_declared_provider_wins_over_the_host():
    assert provider_identity(_cell()) == PROVIDER


def test_provider_falls_back_to_the_base_url_host():
    cell = ModelCell(
        task="embed",
        base_url="https://openrouter.ai/api/v1",
        api_key="k",
        model="m",
    )
    assert provider_identity(cell) == "openrouter"


# ---------------------------------------------------------------------------
# Provider call seam
# ---------------------------------------------------------------------------


def _mock_transport(monkeypatch, handler) -> None:
    """Give every attempt an in-process transport (no DNS, no network)."""
    monkeypatch.setattr(
        "crg.credentials._ssrf_transport",
        lambda auth_mode: httpx.MockTransport(handler),
    )


def test_attempt_client_surfaces_retry_after_header(monkeypatch):
    """The 429 headers reach crg's error (hull's ProviderError has none)."""
    _mock_transport(
        monkeypatch,
        lambda request: httpx.Response(
            429, headers={"Retry-After": "9", "x-ratelimit-reset": "120"}, text="slow"
        ),
    )
    client = AttemptClient(_cell(), auth_mode="no-auth")

    with pytest.raises(ProviderCallError) as excinfo:
        asyncio_run(client.embeddings, ["hello"])
    assert excinfo.value.status == 429
    assert excinfo.value.retry_after == "9"
    assert excinfo.value.rate_limit_reset == "120"
    assert client.cell.model == "test/model"


def test_rotation_uses_retry_after_from_the_wire(monkeypatch, store):
    """End to end: a real 429 cools that key for its Retry-After and rotates."""
    _mock_transport(
        monkeypatch,
        lambda request: (
            httpx.Response(429, headers={"Retry-After": "5"}, text="slow")
            if request.headers["authorization"] == "Bearer sk-first-key"
            else httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})
        ),
    )
    pool = _two_key_pool(store)
    cell = _cell(task="embed")

    async def call(credential):
        client = AttemptClient(
            ModelCell(
                task="embed",
                base_url=cell.base_url,
                api_key=credential.api_key,
                model=cell.model,
            ),
            auth_mode="no-auth",
        )
        try:
            return await client.embeddings(["hello"])
        finally:
            await client.aclose()

    assert asyncio_run(arun_pooled, pool, _cell(), call) == [[1.0]]
    cooled = pool.health()[0]
    assert cooled.last_status == 429
    assert 0 < cooled.cooldown_remaining <= 5


def test_chat_rotation_disables_a_rejected_key(monkeypatch, store):
    """The summarizer path rotates too: a 401 key is retired, chat succeeds."""
    _mock_transport(
        monkeypatch,
        lambda request: (
            httpx.Response(401, text="invalid api key")
            if request.headers["authorization"] == "Bearer sk-first-key"
            else httpx.Response(
                200,
                json={"choices": [{"message": {"content": "answer"}}]},
            )
        ),
    )
    pool = _two_key_pool(store)
    cell = _cell()

    async def call(credential):
        client = AttemptClient(
            ModelCell(
                task="chat",
                base_url=cell.base_url,
                api_key=credential.api_key,
                model=cell.model,
            ),
            auth_mode="no-auth",
        )
        try:
            return await client.chat([{"role": "user", "content": "hi"}])
        finally:
            await client.aclose()

    assert asyncio_run(arun_pooled, pool, _cell(), call) == "answer"
    assert pool.health()[0].disabled is True
    assert pool.health()[1].last_status == 200


def test_client_keeps_the_live_model(store, monkeypatch):
    """A migrated entry never shadows a model switch in the config cell."""
    from crg.credentials import PooledCell

    cell = resolve_pool("chat").cell
    provider = provider_identity(cell)
    credential = store.add_credential(
        provider, "sk-model-key", base_url=cell.base_url, model="old/legacy-model"
    )
    pooled = PooledCell(
        task="chat",
        provider=provider,
        account_id=None,
        cell=cell,
        pool=store.pool(provider),
    )
    attempt = pooled.cell_for(credential)
    assert attempt.model == cell.model
    assert attempt.model != "old/legacy-model"
    assert attempt.api_key == "sk-model-key"


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_concurrent_leases_never_share_a_key(store):
    """Two callers leasing at once get different keys (DB-backed lease)."""
    pool = _two_key_pool(store)
    barrier = threading.Barrier(2)
    leased: list[int] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=10)
            leased.append(pool.acquire().id)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not errors
    assert len(leased) == 2
    assert len(set(leased)) == 2


# ---------------------------------------------------------------------------
# Embedding retry loop
# ---------------------------------------------------------------------------


def test_other_task_key_does_not_enable_a_task(store):
    """An embed-only key must not silently enable paid chat summaries."""
    embed = resolve_pool("embed").cell
    chat = resolve_pool("chat").cell
    store.add_credential(
        provider_identity(embed),
        "sk-embed-only",
        base_url=embed.base_url,
        model=embed.model,
    )

    assert resolve_pool("embed").configured is True
    assert resolve_pool("chat").configured is False
    assert "chat" not in configured_tasks()
    assert chat.model != embed.model


def test_embedding_batch_does_not_retry_pool_exhaustion(monkeypatch):
    """Pool exhaustion already spent the pool's attempts: no outer retry."""
    from crg.embeddings import CloudEmbeddingBackend

    backend = CloudEmbeddingBackend(model="jina-embeddings-v3")
    calls: list[list[str]] = []

    def exhausted(texts, dimensions=None, *, input_type="search_document"):
        calls.append(texts)
        raise PoolUnavailableError(
            "no usable 'test-provider' credential (total=1, disabled=1)",
            provider=PROVIDER,
            total=1,
            disabled=1,
        )

    monkeypatch.setattr(backend, "_call_provider", exhausted)
    with pytest.raises(PoolUnavailableError):
        backend.embed_texts(["hello"])
    assert calls == [["hello"]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_concurrent_calls_queue_on_a_single_key(store):
    """Eight concurrent calls with one pooled key serialise, not fail."""
    store.add_credential(PROVIDER, "sk-only-key", base_url=LOOPBACK)
    pool = store.pool(PROVIDER)
    active = 0
    peak = 0

    async def call(credential):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.01)
        finally:
            active -= 1
        return credential.api_key

    async def gather():
        return await asyncio.gather(
            *[arun_pooled(pool, _cell(), call) for _ in range(8)]
        )

    assert asyncio_run(lambda: gather()) == ["sk-only-key"] * 8
    assert peak == 1


def asyncio_run(func, *args):
    """Run one coroutine function to completion on a fresh loop."""
    import asyncio

    return asyncio.run(func(*args))
