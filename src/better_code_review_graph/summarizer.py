"""Host-configured LLM summaries, cached by source hash and selected model.

The chat cell of the instance config (``[models.chat]``: ``base_url +
api_key + model``, plain-HTTP OpenAI-spec via hull-core) is the single
summary model. An unconfigured cell (no api key supplied by the host)
disables summaries — there is no implicit paid model and no cross-provider
fallback. The full selected model is persisted in ``summary_provider`` so
switching models invalidates the cached summary.

Dispatch goes through hull-core's ``OpenAICompatClient`` (async httpx, one
client per batch). The batch queue keeps its exact historical shape: a
single ``SELECT ... LIMIT ?`` over Function nodes with no ORDER BY (spec
§7 K4 — the queue only lines work up; it does not reorder or change the
schema), capped at ``max_nodes`` per run.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from hull_core.providers.openai_spec import OpenAICompatClient, ProviderError

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


def summary_cell() -> Any:
    """The configured chat cell (host-only key), or ``None``.

    ``None`` -> summaries disabled. The cell comes from the instance
    ``config.toml`` ``[models.chat]`` table; the key may arrive via
    ``HULL_CHAT_API_KEY`` env (host injects at start, spec §4 Q1).
    """
    from .config import resolve_cells

    cell = resolve_cells()["chat"]
    return cell if cell.configured else None


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
    client: OpenAICompatClient,
) -> str:
    """Generate a one-paragraph docstring summary for a single node.

    One OpenAI-spec ``/chat/completions`` call through the batch's shared
    hull client. The caller owns cache hit/miss logic (see
    :func:`compute_summary_cache_key`).

    Returns:
        The generated summary text, stripped of leading/trailing whitespace.

    Raises:
        RuntimeError: if the call fails (wraps the original exception), or
            the provider returns empty/None content (e.g. safety filter).
    """
    # Concatenate rather than .format() so source code containing literal
    # ``{`` / ``}`` (dict literals, f-strings, JSX) does not blow up
    # ``str.format`` with KeyError/IndexError. Only one substitution slot
    # exists, so concatenation is the cleaner contract.
    prompt = _PROMPT_PREFIX + node.source_text
    try:
        content = await client.chat([{"role": "user", "content": prompt}])
    except ProviderError as exc:
        raise RuntimeError(f"summarize_node failed: {exc}") from exc
    if not content or not content.strip():
        raise RuntimeError(
            f"summarize_node: {client.cell.model} returned empty/None content "
            f"(likely safety filter) for node {node.node_id}"
        )
    return content.strip()


def _auth_mode() -> str:
    """SSRF policy input: the configured auth mode (loopback allowed only
    for a no-auth local instance, e.g. self-hosted Ollama/vLLM)."""
    try:
        from .config import load_instance_settings

        return load_instance_settings().server.auth
    except Exception:  # pragma: no cover - config errors surface elsewhere
        return "no-auth"


# ---------------------------------------------------------------------------
# Batch orchestration (Task 5)
# ---------------------------------------------------------------------------

# Default cap on per-run LLM calls. Override per-call via the max_nodes parameter.
DEFAULT_MAX_NODES_PER_RUN = 500


@dataclass(frozen=True)
class BatchSummarizeResult:
    """Outcome counts from a batch_summarize run."""

    generated: int  # nodes whose summary was newly generated this run
    cached: int  # nodes whose stored summary was still valid (cache hit)
    skipped_no_provider: bool = False  # True iff no chat cell is configured
    provider: str | None = None  # provider used (None if skipped)
    errors: int = 0  # nodes where the chat call raised; counted, batch continues


def batch_summarize(
    store: Any,
    *,
    max_nodes: int = DEFAULT_MAX_NODES_PER_RUN,
) -> BatchSummarizeResult:
    """Generate summaries for Function nodes that lack a current cache entry.

    Iteration scope: at most ``max_nodes`` Function-kind nodes whose
    ``source_text`` is non-null, selected by one ``SELECT ... LIMIT ?``
    with no ORDER BY (queue order is the storage engine's row order —
    spec §7 K4 keeps this exactly). For each candidate:

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

    Returns counts. No-op (``skipped_no_provider=True``) when the host has
    not configured a chat cell key.
    """
    if max_nodes < 1:
        raise ValueError(f"max_nodes must be >= 1, got {max_nodes}")

    cell = summary_cell()
    if cell is None:
        return BatchSummarizeResult(
            generated=0,
            cached=0,
            skipped_no_provider=True,
            provider=None,
            errors=0,
        )

    # The complete selected model is the cache identity, not just its provider.
    cache_provider = cell.model

    # Performance Optimization: iterate over the cursor directly rather than
    # materializing rows in memory using .fetchall(), which is expensive
    # because it copies large `source_text` columns.
    cursor = store._conn.execute(
        "SELECT id, source_text, source_hash, summary, summary_provider FROM nodes "
        "WHERE kind='Function' AND source_text IS NOT NULL LIMIT ?",
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

    if pending:
        generated, errors = asyncio.run(
            _summarize_pending(store, cell, cache_provider, pending)
        )
    else:
        errors = 0

    return BatchSummarizeResult(
        generated=generated,
        cached=cached,
        skipped_no_provider=False,
        provider=cache_provider,
        errors=errors,
    )


async def _summarize_pending(
    store: Any,
    cell: Any,
    cache_provider: str,
    pending: list[tuple[int, NodeNeedingSummary]],
) -> tuple[int, int]:
    """Run the pending queue through one shared hull client.

    Sequential, cursor order preserved. Each failure is logged + counted;
    the batch continues (fail-open per-node, spec §7).
    """
    client = OpenAICompatClient(cell, auth_mode=_auth_mode())
    generated = 0
    errors = 0
    try:
        for row_id, node in pending:
            try:
                summary = await summarize_node_async(node, client)
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
        await client.aclose()
    return generated, errors
