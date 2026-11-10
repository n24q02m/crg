"""Host-configured LLM summaries, cached by source hash and selected model.

The chat cell of the instance config (``[models.chat]``: ``base_url +
api_key + model``, plain-HTTP OpenAI-spec via hull-core) is the single
summary model. An unconfigured cell (no api key supplied by the host)
disables summaries — there is no implicit paid model and no cross-provider
fallback. The full selected model is persisted in ``summary_provider`` so
switching models invalidates the cached summary.

Dispatch goes through hull-core's ``OpenAICompatClient`` (async httpx, one
client per credential). Credentials come from the provider pool that the
``[models.chat]`` cell's key was migrated into (``crg.credentials``), so a
401/429/key rotation is handled by the pool instead of failing the whole
batch. The batch queue is a single ``SELECT ... LIMIT ?`` over
Function nodes with a deterministic base ordering (``ORDER BY id``, spec
§7 K4). On top of that base order, an optional jev ranking layer re-orders
the pending (cache-miss) queue in ~50-node batches — exactly one advisory
``jev_score`` call per batch, never one call per node — and is strictly
fail-open: any jev unavailability (cell not configured, call error,
unparseable reply) leaves the queue in base order and is recorded in the
run receipt only. The queue never changes the schema, only the processing
order.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any

from hull_core.credentials import Credential, KeyPool
from hull_core.providers.openai_spec import OpenAICompatClient, ProviderError

from .credentials import (
    AttemptClient,
    PooledCell,
    PooledClients,
    ProviderCallError,
    arun_pooled,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NodeNeedingSummary:
    """One node candidate for LLM summarization.

    Attributes:
        node_id: Qualified-name primary key (``file_path::name``).
        source_text: Raw function source code that the LLM will summarize.
        source_hash: Optional pre-computed SHA-256 hex digest of
            ``source_text`` -- when provided the cache key trusts it
            verbatim and skips rehashing.
    """

    node_id: str
    source_text: str
    source_hash: str | None


def compute_source_hash(source_text: str) -> str:
    """Return the SHA-256 hex digest of ``source_text`` encoded as UTF-8.

    Pure function, no I/O. ``source_text=""`` is well-defined and returns
    ``hashlib.sha256(b"").hexdigest()``.
    """
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def compute_summary_cache_key(node: NodeNeedingSummary, provider: str) -> str:
    """Derive the LLM-summary cache key for ``node`` under ``provider``.

    Uses ``node.source_hash`` if present (trusted verbatim, no
    recomputation), otherwise hashes ``node.source_text`` on demand.
    Format: ``"{hash}:{provider}"``.
    """
    hash_value = (
        node.source_hash
        if node.source_hash is not None
        else compute_source_hash(node.source_text)
    )
    return f"{hash_value}:{provider}"


def summary_cell() -> PooledCell | None:
    """The configured chat cell plus its provider pool, or ``None``.

    ``None`` -> summaries disabled. The cell comes from the instance
    ``config.toml`` ``[models.chat]`` table; the key may arrive via
    ``HULL_CHAT_API_KEY`` env (host injects at start, spec §4 Q1) and is
    migrated once into hull's credential pool, which is what actually
    rotates a failing key.
    """
    from .credentials import resolve_pool

    pooled = resolve_pool("chat")
    return pooled if pooled.configured else None


def jev_score_cell() -> PooledCell | None:
    """The configured jev_score cell plus its pool, or ``None``.

    Unlike :func:`summary_cell`, resolution failures also yield ``None``:
    the ranking layer is advisory (spec §7 K4 fail-open), so an unreadable
    config may only ever disable prioritization, never the queue itself.
    """
    try:
        from .credentials import resolve_pool

        pooled = resolve_pool("jev_score")
    except Exception:  # config problems must only disable ranking
        return None
    return pooled if pooled.configured else None


# ---------------------------------------------------------------------------
# Single-node LLM summarization
# ---------------------------------------------------------------------------

_PROMPT_PREFIX = (
    "Write a one-paragraph docstring (max 3 sentences) describing what this function does. "
    "No code, no examples, no markdown. Just the description.\n\n"
    "Source:\n"
)


async def summarize_node_async(
    node: NodeNeedingSummary,
    client: AttemptClient | OpenAICompatClient,
) -> str:
    """Generate a one-paragraph docstring summary for a single node.

    One OpenAI-spec ``/chat/completions`` call through the batch's shared
    hull client. The caller owns cache hit/miss logic (see
    :func:`compute_summary_cache_key`).

    Returns:
        The generated summary text, stripped of leading/trailing whitespace.

    Raises:
        ProviderCallError: if the provider rejects the call. The status and
            rate-limit hints are preserved so the pool can disable a 401/403
            key or cool a 429 one down instead of failing the batch.
        RuntimeError: if the provider returns empty/None content (e.g. a
            safety filter).
    """
    # Concatenate rather than .format() so source code containing literal
    # ``{`` / ``}`` (dict literals, f-strings, JSX) does not blow up
    # ``str.format`` with KeyError/IndexError. Only one substitution slot
    # exists, so concatenation is the cleaner contract.
    prompt = _PROMPT_PREFIX + node.source_text
    try:
        content = await client.chat([{"role": "user", "content": prompt}])
    except ProviderError as exc:
        raise ProviderCallError(
            exc.status,
            f"summarize_node failed: {exc.detail}",
            retry_after=getattr(exc, "retry_after", None),
            rate_limit_reset=getattr(exc, "rate_limit_reset", None),
        ) from exc
    if not content or not content.strip():
        raise RuntimeError(
            f"summarize_node: {client.cell.model} returned empty/None content "
            f"(likely safety filter) for node {node.node_id}"
        )
    return content.strip()


# ---------------------------------------------------------------------------
# Batch orchestration (Task 5)
# ---------------------------------------------------------------------------

# Default cap on per-run LLM calls. Override per-call via the max_nodes parameter.
DEFAULT_MAX_NODES_PER_RUN = 500

# jev ranking layer (spec §7 K4): the pending queue is re-ordered in batches
# of this many nodes, with exactly one advisory jev_score call per batch.
JEV_BATCH_SIZE = 50

# Per-node excerpt handed to the ranking call, and the cap on the recorded
# fail-open reason so a chatty provider error cannot bloat the receipt.
_JEV_EXCERPT_CHARS = 160
_FAILOPEN_REASON_MAX_CHARS = 200


@dataclass(frozen=True)
class JevRankingReceipt:
    """Provenance of the jev ranking layer for one batch_summarize run.

    ``used=True`` means jev re-ordered the queue. ``used=False`` with a
    ``None`` ``failopen_reason`` means the layer was disabled (no jev cell,
    or a single-node queue); a non-``None`` reason means jev was attempted,
    failed, and the queue fell back to base order.
    """

    used: bool
    batches: int = 0  # ranked batches; one jev call each
    ranked_nodes: int = 0  # nodes whose queue position jev decided
    failopen_reason: str | None = None  # why ranking was skipped, if attempted


@dataclass(frozen=True)
class BatchSummarizeResult:
    """Outcome counts from a batch_summarize run."""

    generated: int  # nodes whose summary was newly generated this run
    cached: int  # nodes whose stored summary was still valid (cache hit)
    skipped_no_provider: bool = False  # True iff no chat cell is configured
    provider: str | None = None  # provider used (None if skipped)
    errors: int = 0  # nodes where the chat call raised; counted, batch continues
    jev_ranking: JevRankingReceipt | None = None  # queue ranking provenance


# ---------------------------------------------------------------------------
# jev queue ranking (spec §7 K4 — advisory, fail-open)
# ---------------------------------------------------------------------------

_JEV_RANK_PROMPT_PREFIX = (
    "You are prioritizing a code-review summarization queue. Rank the "
    "numbered functions below by value to a code reviewer: core logic, "
    "complex control flow and public entry points first; trivial accessors, "
    "constants and one-line wrappers last.\n"
    "Reply with ONLY a JSON array of the indices in priority order, e.g. "
    "[3, 1, 0, 2]. Every index must appear exactly once.\n\nFunctions:\n"
)

# Scan the reply for numeric tokens (mnemo-wp4-writer jev precedent:
# ``[+-]?\\d*\\.\\d+|\\d+``); a reply without any number raises instead of
# guessing an order.
_NUMBER_RE = re.compile(r"[+-]?\d*\.\d+|\d+")


def _parse_jev_ranking(content: str, batch_size: int) -> list[int]:
    """Parse jev's priority order out of its reply.

    Follows the mnemo-wp4-writer precedent: scan for numeric tokens, raise
    when the reply carries no numbers at all. Indices outside
    ``range(batch_size)`` and duplicates are ignored; an incomplete
    permutation raises so the caller can fail open to base order.
    """
    tokens = _NUMBER_RE.findall(content)
    if not tokens:
        raise ValueError(f"jev ranking reply has no numeric tokens: {content[:80]!r}")
    order: list[int] = []
    seen: set[int] = set()
    for token in tokens:
        index = int(float(token))
        if 0 <= index < batch_size and index not in seen:
            seen.add(index)
            order.append(index)
    if len(order) != batch_size:
        raise ValueError(
            f"jev ranking incomplete: got {len(order)} of {batch_size} indices"
        )
    return order


async def _jev_rank_batch(
    client: Any,
    batch: list[tuple[int, NodeNeedingSummary]],
) -> list[tuple[int, NodeNeedingSummary]]:
    """One advisory jev call: return ``batch`` re-ordered by review priority."""
    listing = _JEV_RANK_PROMPT_PREFIX
    for position, (_, node) in enumerate(batch):
        condensed = " ".join(node.source_text.split())[:_JEV_EXCERPT_CHARS]
        listing += (
            f"{position}. ({len(node.source_text.splitlines())} lines) {condensed}\n"
        )
    content = await client.chat(
        [{"role": "user", "content": listing}],
        max_tokens=1024,
        reasoning={"exclude": True},
    )
    order = _parse_jev_ranking(content, len(batch))
    return [batch[index] for index in order]


async def _jev_rank_queue(
    client: Any,
    pending: list[tuple[int, NodeNeedingSummary]],
    batch_size: int = JEV_BATCH_SIZE,
) -> tuple[list[tuple[int, NodeNeedingSummary]], int]:
    """Rank the whole pending queue, one jev call per ``batch_size`` chunk.

    Any failure propagates: the caller discards partial rankings and keeps
    the queue in base order (fail-open is all-or-nothing per run).
    """
    ordered: list[tuple[int, NodeNeedingSummary]] = []
    batches = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        ordered.extend(await _jev_rank_batch(client, batch))
        batches += 1
    return ordered, batches


def _maybe_jev_rank(
    pending: list[tuple[int, NodeNeedingSummary]],
) -> tuple[JevRankingReceipt, list[tuple[int, NodeNeedingSummary]]]:
    """Re-order ``pending`` via the advisory jev ranking layer (spec §7 K4).

    Fail-open: an unconfigured cell returns the queue unchanged silently;
    any ranking failure logs a warning and returns the queue unchanged with
    the reason on the receipt. Only a fully successful pass re-orders.
    """
    if len(pending) < 2:  # nothing to prioritize
        return JevRankingReceipt(used=False), pending

    jev = jev_score_cell()
    if jev is None or jev.pool is None:
        return JevRankingReceipt(used=False), pending
    jev_pool: KeyPool = jev.pool

    async def _rank() -> tuple[list[tuple[int, NodeNeedingSummary]], int]:
        clients = PooledClients(jev, AttemptClient)

        async def _rank_once(credential: Credential) -> tuple[list[Any], int]:
            client = clients.client(credential)
            return await _jev_rank_queue(client, pending, JEV_BATCH_SIZE)

        try:
            return await arun_pooled(jev_pool, jev.cell, _rank_once)
        finally:
            await clients.aclose()

    try:
        ordered, batches = asyncio.run(_rank())
    except Exception as exc:  # ranking is advisory only — never block the queue
        logger.warning("jev ranking failed; queue keeps base order: %s", exc)
        return (
            JevRankingReceipt(
                used=False,
                batches=0,
                ranked_nodes=0,
                failopen_reason=str(exc)[:_FAILOPEN_REASON_MAX_CHARS],
            ),
            pending,
        )
    return (
        JevRankingReceipt(used=True, batches=batches, ranked_nodes=len(ordered)),
        ordered,
    )


def batch_summarize(
    store: Any,
    *,
    max_nodes: int = DEFAULT_MAX_NODES_PER_RUN,
) -> BatchSummarizeResult:
    """Generate summaries for Function nodes that lack a current cache entry.

    Iteration scope: at most ``max_nodes`` Function-kind nodes whose
    ``source_text`` is non-null, selected by one ``SELECT ... LIMIT ?``
    with deterministic base ordering (``ORDER BY id`` — spec §7 K4). When
    the host configures a jev_score cell, the pending (cache-miss) queue is
    additionally re-ordered by one advisory jev call per ~50-node batch;
    any jev failure leaves the queue in base order (fail-open) and is
    recorded in :attr:`BatchSummarizeResult.jev_ranking`. For each candidate:

    - If stored summary + ``summary_provider`` + ``source_hash`` all match
      the selected model + freshly-computed source hash, it's a cache hit
      and we skip.
    - Otherwise call the chat cell and persist via
      :meth:`GraphStore.update_summary`.

    Errors are logged and counted in :class:`BatchSummarizeResult.errors`;
    the batch continues so a single transient provider hiccup doesn't kill
    an entire run. Caller can re-run later — failed nodes will retry next
    time because their stored ``source_hash`` still doesn't match the live
    one.

    Returns counts. No-op (``skipped_no_provider=True``) when no chat
    credential is configured (cell key or provider pool).
    """
    if max_nodes < 1:
        raise ValueError(f"max_nodes must be >= 1, got {max_nodes}")

    pooled = summary_cell()
    if pooled is None:
        return BatchSummarizeResult(
            generated=0,
            cached=0,
            skipped_no_provider=True,
            provider=None,
            errors=0,
        )

    # The complete selected model is the cache identity, not just its provider.
    cache_provider = pooled.cell.model

    # Performance Optimization: iterate over the cursor directly rather than
    # materializing rows in memory using .fetchall(), which is expensive
    # because it copies large `source_text` columns.
    cursor = store._conn.execute(
        "SELECT id, source_text, source_hash, summary, summary_provider FROM nodes "
        "WHERE kind='Function' AND source_text IS NOT NULL "
        "ORDER BY id LIMIT ?",
        (max_nodes,),
    )

    generated = 0
    cached = 0
    pending: list[tuple[int, NodeNeedingSummary]] = []

    for row in cursor:
        row_id = row[0]
        src = row[1]
        stored_hash = row[2]
        stored_summary = row[3]
        stored_provider = row[4]

        live_hash = compute_source_hash(src)

        if (
            stored_summary
            and stored_hash == live_hash
            and stored_provider == cache_provider
        ):
            cached += 1
            continue

        pending.append(
            (
                row_id,
                NodeNeedingSummary(
                    node_id=str(row_id),
                    source_text=src,
                    source_hash=live_hash,
                ),
            )
        )

    ranking, pending = _maybe_jev_rank(pending)

    if pending:
        generated, errors = asyncio.run(
            _summarize_pending(store, pooled, cache_provider, pending)
        )
    else:
        errors = 0

    return BatchSummarizeResult(
        generated=generated,
        cached=cached,
        skipped_no_provider=False,
        provider=cache_provider,
        errors=errors,
        jev_ranking=ranking,
    )


async def _summarize_pending(
    store: Any,
    pooled: PooledCell,
    cache_provider: str,
    pending: list[tuple[int, NodeNeedingSummary]],
) -> tuple[int, int]:
    """Run the pending queue through the chat provider pool.

    Sequential, queue order preserved (base ``ORDER BY id`` order,
    optionally re-ranked by the jev layer). Each node is one pooled
    attempt: a key that answers 401/429 is retired by the pool and the same
    node is retried on the next key. Each node's failure is logged and
    counted; the batch continues (fail-open per-node, spec §7).
    """
    if pooled.pool is None:  # pragma: no cover - guarded by the caller
        raise RuntimeError("summaries require a configured chat credential")
    pool: KeyPool = pooled.pool

    clients = PooledClients(pooled, AttemptClient)

    generated = 0
    errors = 0
    try:
        for row_id, node in pending:
            try:
                summary = await arun_pooled(
                    pool,
                    pooled.cell,
                    lambda credential, node=node: summarize_node_async(
                        node, clients.client(credential)
                    ),
                )
            except Exception as exc:
                logger.warning("summarize_node failed for id=%d: %s", row_id, exc)
                errors += 1
                continue
            store.update_summary(
                row_id,
                summary=summary,
                provider=cache_provider,
                source_hash=node.source_hash,
            )
            generated += 1
    finally:
        await clients.aclose()
    return generated, errors
