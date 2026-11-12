"""Provider credential pools for crg's cloud cells.

crg used to resolve exactly one ``api_key`` per provider, so a single 401 or
429 took the whole cloud path down. Credentials now live in hull's
``CredentialStore`` (``~/.hull/hull.db``, sealed by hull's crypto) and every
call rotates through a ``KeyPool``:

* 401/403 disable the credential and move to the next one,
* 429 cools it down (``Retry-After`` / ``x-ratelimit-reset`` honoured),
* 5xx retries the same credential once, then moves on,
* anything else (a request problem, not a credential problem) re-raises.

Pools are per provider identity — ``[models.<task>].provider`` when the host
names one, otherwise :func:`hull_core.credentials.provider_from_base_url`. A
task may point at a named account (``[models.<task>].account``); the default
is the provider's unaccounted pool, and rotation never hops across accounts.

A pre-pool single-key setup keeps working unchanged: on the first resolution
of a process every configured cell is seeded into its pool once (hull's
migration skips duplicates), the env var / ``config.toml`` value is only
ever read, and the live cell still decides which model the task uses — a
pool entry only supplies the key and endpoint of one attempt.

Nothing here logs or echoes a key: health rows are masked by hull, and the
exhaustion error carries counts plus a redacted last-error string.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
from hull_core.config.models import ModelCell
from hull_core.config.settings import HullSettings
from hull_core.credentials import (
    AccountError,
    Credential,
    CredentialStore,
    KeyPool,
    MigrationResult,
    PoolExhaustedError,
    default_pool_db_path,
    provider_from_base_url,
)
from hull_core.providers.openai_spec import ProviderError

logger = logging.getLogger(__name__)

#: Override the credential database (self-host instances, tests). Unset means
#: hull's shared ``~/.hull/hull.db``, the database every hull surface uses.
CREDENTIALS_DB_ENV = "CRG_CREDENTIALS_DB"


class CredentialsConfigError(ValueError):
    """The configured provider/account selection cannot be honoured."""


class PoolUnavailableError(RuntimeError):
    """No credential for a provider pool can serve the call right now.

    The redacted counterpart of hull's ``PoolExhaustedError``: counts,
    ``retry_after`` and the (already redacted) last error, never a key.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        account_id: str | None = None,
        total: int = 0,
        disabled: int = 0,
        cooling_down: int = 0,
        leased: int = 0,
        retry_after: float | None = None,
        last_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.account_id = account_id
        self.total = total
        self.disabled = disabled
        self.cooling_down = cooling_down
        self.leased = leased
        self.retry_after = retry_after
        self.last_error = last_error

    @classmethod
    def from_exhausted(cls, exc: PoolExhaustedError) -> PoolUnavailableError:
        """Re-type hull's exhaustion error, keeping its redacted detail."""
        return cls(
            str(exc),
            provider=exc.provider,
            account_id=exc.account_id,
            total=exc.total,
            disabled=exc.disabled,
            cooling_down=exc.cooling_down,
            leased=exc.leased,
            retry_after=exc.retry_after,
            last_error=exc.last_error,
        )


class ProviderCallError(ProviderError):
    """A provider attempt failed, carrying the response's rate-limit hints.

    hull's ``ProviderError`` exposes the status but not the response
    headers, and the pool's 429 policy is only as good as the hint it
    receives. This subclass adds the two headers the pool understands while
    staying a ``ProviderError`` for every existing ``except`` clause.
    """

    def __init__(
        self,
        status: int,
        detail: str,
        *,
        retry_after: Any = None,
        rate_limit_reset: Any = None,
    ) -> None:
        super().__init__(status, detail)
        self.retry_after = retry_after
        self.rate_limit_reset = rate_limit_reset


# ---------------------------------------------------------------------------
# Credential store (one SQLite connection per process)
# ---------------------------------------------------------------------------

_store_lock = threading.RLock()
_store: CredentialStore | None = None
_store_path: Path | None = None
_migrated: set[tuple[str, str]] = set()


def credentials_db_path() -> Path:
    """``$CRG_CREDENTIALS_DB`` or hull's shared ``~/.hull/hull.db``."""
    override = os.environ.get(CREDENTIALS_DB_ENV, "").strip()
    return Path(override).expanduser() if override else default_pool_db_path()


# hull's store is one sqlite connection opened with ``check_same_thread=False``:
# safe to use from any thread, but not two at once. The MCP server runs tool
# calls in worker threads, so every store operation goes through this lock.
_store_io = threading.RLock()


def credentials_store() -> CredentialStore:
    """The process-wide credential store, re-opened when the path changes."""
    global _store, _store_path

    path = credentials_db_path()
    with _store_lock:
        if _store is not None and _store_path == path:
            return _store
        if _store is not None:
            _store.close()
        _store = CredentialStore(path)
        _store_path = path
        return _store


def reset_credentials_store() -> None:
    """Drop the cached store and migration state (tests, config-dir change)."""
    global _store, _store_path

    with _store_lock:
        if _store is not None:
            _store.close()
        _store = None
        _store_path = None
        _migrated.clear()


# ---------------------------------------------------------------------------
# Pool identity
# ---------------------------------------------------------------------------


def provider_identity(cell: ModelCell) -> str:
    """Pool identity for one task cell: declared provider, else its host."""
    declared = str(getattr(cell, "provider", "") or "")
    return declared or provider_from_base_url(str(cell.base_url))


def _account_of(cell: ModelCell) -> str | None:
    return str(getattr(cell, "account", "") or "") or None


def serves_task(credential: Credential, cell: ModelCell) -> bool:
    """Whether one pool entry is meant to serve ``cell``'s task.

    A credential migrated from a cell is bound to that cell's endpoint and
    model, so an embed-only key never silently enables a chat call. An entry
    added without a model expresses operator intent for the whole provider
    and serves every task on that endpoint.
    """
    endpoint = str(getattr(cell, "base_url", "") or "").rstrip("/")
    entry_endpoint = str(getattr(credential, "base_url", "") or "").rstrip("/")
    if not endpoint or entry_endpoint != endpoint:
        return False
    entry_model = str(getattr(credential, "model", "") or "").strip()
    return entry_model in ("", str(getattr(cell, "model", "") or "").strip())


def _keyed_cells(cells: Mapping[str, ModelCell]) -> dict[str, list[ModelCell]]:
    """Group the cells that still carry a legacy key by provider identity."""
    groups: dict[str, list[ModelCell]] = {}
    for cell in cells.values():
        if not str(getattr(cell, "api_key", "") or ""):
            continue
        groups.setdefault(provider_identity(cell), []).append(cell)
    return groups


def migrate_legacy_cells(
    cells: Mapping[str, ModelCell], *, store: CredentialStore | None = None
) -> list[MigrationResult]:
    """Seed each provider pool from the pre-pool single-key cells, once.

    Idempotent twice over: this process seeds a provider at most once, and
    hull refuses a credential the pool already holds — so a restart adds
    nothing. The cell (and therefore the user's env var or ``config.toml``)
    is never modified; it stays the source of the live model and endpoint.
    """
    store = store if store is not None else credentials_store()
    results: list[MigrationResult] = []
    for provider, group in _keyed_cells(cells).items():
        token = (str(store.path), provider)
        with _store_lock:
            if token in _migrated:
                continue
        try:
            result = store.migrate_model_cells(group, provider=provider)
        except AccountError as exc:
            raise CredentialsConfigError(
                f"credential pool {provider!r}: {exc}. Register the account in "
                "hull's account registry or drop the [models.*].account key."
            ) from exc
        with _store_lock:
            _migrated.add(token)
        if result.added:
            logger.info(
                "credential pool %r seeded from host config: added=%d skipped=%d",
                provider,
                result.added,
                result.skipped,
            )
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# One task's cell + pool
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PooledCell:
    """A task's config cell plus the credential pool that serves it.

    ``pool`` is ``None`` when neither the cell nor the store holds a
    credential for the task's provider — the "not configured" state that
    keeps local ONNX embedding and summaries-off working.
    """

    task: str
    provider: str
    account_id: str | None
    cell: ModelCell
    pool: KeyPool | None = None
    auth_mode: str = "no-auth"

    @property
    def configured(self) -> bool:
        """True when at least one key (cell or pool) can serve a call."""
        return self.pool is not None

    def cell_for(self, credential: Credential) -> ModelCell:
        """Bind the live cell to one pool credential's key and endpoint.

        A pool entry identifies a key/endpoint, not today's model: the
        config cell keeps the model so a model switch is not shadowed by an
        entry migrated earlier.
        """
        return replace(
            self.cell,
            api_key=credential.api_key,
            base_url=credential.base_url or self.cell.base_url,
        )


def resolve_pool(task: str, *, settings: HullSettings | None = None) -> PooledCell:
    """Resolve one task's cell and its provider/account pool.

    Legacy single-key cells are migrated on first use, so an existing
    ``HULL_<TASK>_API_KEY`` or ``config.toml`` key serves calls through the
    pool exactly as before.
    """
    from .config import load_instance_settings, resolve_cells

    settings = settings if settings is not None else load_instance_settings()
    cells = resolve_cells(settings)
    try:
        cell = cells[task]
    except KeyError as exc:  # pragma: no cover - tasks are a closed set
        raise CredentialsConfigError(f"unknown model task {task!r}") from exc

    provider = provider_identity(cell)
    account_id = _account_of(cell)
    store = credentials_store()
    migrate_legacy_cells(cells, store=store)

    if account_id is not None:
        account = store.accounts().maybe_get(account_id)
        if account is None:
            raise CredentialsConfigError(
                f"[models.{task}].account {account_id!r} is not in hull's "
                "account registry; add it there or drop the key."
            )
        if account.provider != provider:
            raise CredentialsConfigError(
                f"account {account_id!r} belongs to provider "
                f"{account.provider!r}, not {provider!r} ([models.{task}])"
            )

    auth_mode = str(settings.server.auth or "")
    pool = store.pool(provider, account_id=account_id)
    configured = bool(str(getattr(cell, "api_key", "") or "")) or any(
        serves_task(credential, cell) for credential in pool.credentials()
    )
    return PooledCell(
        task=task,
        provider=provider,
        account_id=account_id,
        cell=cell,
        pool=pool if configured else None,
        auth_mode=auth_mode or "no-auth",
    )


def configured_tasks() -> list[str]:
    """Tasks that can serve a cloud call right now (cell key or pool entry)."""
    from .config import load_instance_settings, resolve_cells

    settings = load_instance_settings()
    cells = resolve_cells(settings)
    migrate_legacy_cells(cells)
    return [task for task in cells if resolve_pool(task, settings=settings).configured]


# ---------------------------------------------------------------------------
# Rotation helpers
# ---------------------------------------------------------------------------


class _ServeRotation:
    """hull's rotation loop, bounded to the credentials that serve one task.

    ``KeyPool.run`` rotates over every entry of a provider pool. An entry
    migrated for another task is bound to its own endpoint, so spending it
    here would send this task's request to the wrong host. This mirrors
    hull's ``_Rotation`` (same attempt budget, 5xx retry budget and failure
    policy) with the non-serving entries excluded from the start.
    """

    def __init__(self, pool: KeyPool, cell: ModelCell) -> None:
        self._pool = pool
        with _store_io:
            entries = pool.credentials()
        self._skip = {c.id for c in entries if not serves_task(c, cell)}
        servable = len(entries) - len(self._skip)
        self._limit = max(1, servable * (1 + pool.max_5xx_retries))
        self._attempts = 0
        self._retried: dict[int, int] = {}
        self._last_error: str | None = None
        self._leased_out = False

    @property
    def concurrency(self) -> int:
        """Credentials that can serve this task at once."""
        return max(1, len(self._pool.credentials()) - len(self._skip))

    def next_credential(self) -> Credential | None:
        self._leased_out = False
        if self._attempts >= self._limit:
            return None
        try:
            with _store_io:
                credential = self._pool.acquire(exclude=self._skip)
        except PoolExhaustedError:
            self._leased_out = True
            return None
        self._attempts += 1
        return credential

    @property
    def leased_out(self) -> bool:
        """True when the last attempt found every servable key leased."""
        return self._leased_out

    def succeeded(self, credential: Credential) -> None:
        with _store_io:
            self._pool.report_success(credential)

    def failed(self, credential: Credential, error: BaseException) -> str:
        with _store_io:
            action = self._pool.report_failure(
                credential,
                KeyPool.status_of(error),
                retry_after=getattr(error, "retry_after", None),
                rate_limit_reset=getattr(error, "rate_limit_reset", None),
            )
        self._last_error = self._pool.redact(str(error))
        if action == "retry":
            seen = self._retried.get(credential.id, 0) + 1
            self._retried[credential.id] = seen
            if seen > self._pool.max_5xx_retries:
                self._skip.add(credential.id)
        elif action in ("disable", "cooldown"):
            self._skip.add(credential.id)
        return action

    def exhausted(self) -> PoolUnavailableError:
        with _store_io:
            return PoolUnavailableError.from_exhausted(
                self._pool.exhausted_error(last_error=self._last_error)
            )


# A pool can lease no more keys than it holds. A call that finds every usable
# key leased waits for one to come free instead of failing with "no usable
# credential"; the wait is bounded so a stuck holder still surfaces.
_LEASE_WAIT_SECONDS = 0.05
_MAX_LEASE_WAITS = 400


def _has_usable_key(pool: KeyPool) -> bool:
    """True when the pool still holds a key that could serve a later attempt.

    Read after a failed acquire, so a lease that frees in between is retried
    rather than mistaken for a pool that will never serve.
    """
    with _store_io:
        counts = pool.store.diagnose(pool.provider, pool.account_id)
    return (
        int(counts.get("total", 0) or 0)
        - int(counts.get("disabled", 0) or 0)
        - int(counts.get("cooling_down", 0) or 0)
    ) > 0


async def arun_pooled[T](
    pool: KeyPool, cell: ModelCell, call: Callable[[Credential], Awaitable[T]]
) -> T:
    """Run ``call`` through the task's rotation, mapping exhaustion to crg's error."""
    rotation = _ServeRotation(pool, cell)
    waits = 0
    while True:
        credential = rotation.next_credential()
        if credential is None:
            if (
                waits < _MAX_LEASE_WAITS
                and rotation.leased_out
                and _has_usable_key(pool)
            ):
                waits += 1
                await asyncio.sleep(_LEASE_WAIT_SECONDS)
                continue
            raise rotation.exhausted()
        try:
            result = await call(credential)
        except Exception as exc:
            if rotation.failed(credential, exc) == "fatal":
                raise
            continue
        rotation.succeeded(credential)
        return result


# ---------------------------------------------------------------------------
# Provider calls (one client per attempt, rate-limit hints preserved)
# ---------------------------------------------------------------------------


class _HintTransport(httpx.AsyncBaseTransport):
    """SSRF-safe transport that records the last response's rate-limit hints."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.retry_after: Any = None
        self.rate_limit_reset: Any = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        # Overwrite on every response so a later call never inherits a stale
        # hint from an earlier 429.
        self.retry_after = response.headers.get("retry-after")
        self.rate_limit_reset = response.headers.get("x-ratelimit-reset")
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


def _ssrf_transport(auth_mode: str) -> httpx.AsyncBaseTransport:
    """The transport hull's client would build itself, exposed for wrapping."""
    from hull_core.http.ssrf import AsyncSSRFSafeTransport
    from hull_core.providers.openai_spec import AuthPolicy

    policy = AuthPolicy.for_mode(auth_mode)
    return AsyncSSRFSafeTransport(
        allow_private=policy.allow_private, allow_loopback=policy.allow_loopback
    )


class AttemptClient:
    """One pool credential bound to a hull OpenAI-spec client.

    Constructed per attempt so rotation always uses that credential's own
    key/endpoint, and so the ``Retry-After``/``x-ratelimit-reset`` headers of
    a 429 reach the pool (hull's ``ProviderError`` carries no headers).
    """

    def __init__(self, cell: ModelCell, *, auth_mode: str = "no-auth") -> None:
        from hull_core.providers.openai_spec import OpenAICompatClient

        self._hints = _HintTransport(_ssrf_transport(auth_mode))
        self._client = OpenAICompatClient(
            cell, auth_mode=auth_mode, transport=self._hints
        )

    @property
    def cell(self) -> ModelCell:
        return self._client.cell

    async def embeddings(
        self, texts: list[str], *, dimensions: int | None = None, **extra: Any
    ) -> list[list[float]]:
        return await self._guarded(
            self._client.embeddings(texts, dimensions=dimensions, **extra)
        )

    async def chat(self, messages: list[dict], **options: Any) -> str:
        return await self._guarded(self._client.chat(messages, **options))

    async def _guarded(self, pending: Any) -> Any:
        try:
            return await pending
        except ProviderError as exc:
            raise ProviderCallError(
                exc.status,
                exc.detail,
                retry_after=self._hints.retry_after,
                rate_limit_reset=self._hints.rate_limit_reset,
            ) from exc

    async def aclose(self) -> None:
        await self._client.aclose()


class PooledClients:
    """Lazily built per-credential clients for one pooled cell.

    A batch keeps one client per credential (no re-dial per node) while each
    attempt still carries its own key and endpoint. Close every client at
    the end of the batch with :meth:`aclose`.
    """

    def __init__(
        self,
        pooled: PooledCell,
        factory: Callable[..., AttemptClient] | None = None,
    ) -> None:
        self._pooled = pooled
        self._factory = factory or AttemptClient
        self._clients: dict[int, AttemptClient] = {}

    def client(self, credential: Credential) -> AttemptClient:
        client = self._clients.get(credential.id)
        if client is None:
            client = self._factory(
                self._pooled.cell_for(credential), auth_mode=self._pooled.auth_mode
            )
            self._clients[credential.id] = client
        return client

    async def aclose(self) -> None:
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            await client.aclose()
