"""Non-blocking credential state management for better-code-review-graph.

State machine: awaiting_setup -> (configured | local)
Reset: configured/local -> awaiting_setup (via setup tool).

CRG has a local fallback through fastretrieval so all tools work without
cloud credentials. Cloud keys are optional enhancements.

After the stdio-pure + http-multi-user split (spec
2026-05-01-stdio-pure-http-multiuser.md), the daemon-bridge auto-spawn
flow has been removed. In stdio mode the server reads cloud API keys
from env vars only; in HTTP mode the relay form lives on the HTTP
server itself at ``<PUBLIC_URL>/authorize``.

Migrated from mcp_core.storage.config_file (shared config.enc) to
mcp_core.storage.per_plugin_store (per-plugin encrypted store) for
trust model alignment per spec 2026-04-30-trust-model-alignment.md.
"""

from __future__ import annotations

import contextvars
import json
import os
import sys
from enum import Enum
from pathlib import Path

from loguru import logger
from mcp_core.storage.per_plugin_store import PerPluginStore

SERVER_NAME = "better-code-review-graph"
PLUGIN_NAME = "better-code-review-graph"

CLOUD_KEYS = [
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "JINA_AI_API_KEY",
    "OPENAI_API_KEY",
    "COHERE_API_KEY",
    "CO_API_KEY",
    "GOOGLE_VERTEX_EXPRESS_API_KEY",
    "OPENROUTER_API_KEY",
    # Per-sub custom endpoints (SSRF-vetted in mcp_core.llm dispatch). Listed
    # here so the per-sub bucket carries them and the os.environ filter in
    # credentials_for_current_request keeps them, same as the provider keys.
    "EMBEDDING_API_BASE",
    "LLM_API_BASE",
]


class CredentialState(Enum):
    AWAITING_SETUP = "awaiting_setup"
    SETUP_IN_PROGRESS = "setup_in_progress"
    CONFIGURED = "configured"
    LOCAL = "local"


# Module-level state
_state: CredentialState = CredentialState.AWAITING_SETUP
_setup_url: str | None = None

# Per-request JWT ``sub`` (HTTP multi-user mode).
#
# Set by the ``auth_scope`` middleware in ``run_http_server`` AFTER mcp-core
# verifies the bearer JWT. Per-tool-call handlers consume this via
# :func:`credentials_for_current_request` to look up the correct
# per-sub credential bucket so concurrent users do not see each other's
# API keys. ``None`` in stdio mode and any non-HTTP context.
_current_sub: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "crg_current_sub", default=None
)


def get_state() -> CredentialState:
    """Return current credential state."""
    return _state


def get_setup_url() -> str | None:
    """Return current relay setup URL (if any).

    After stdio-pure + http-multi-user split, this is always ``None``
    in stdio mode and only set externally by HTTP-mode entry points.
    """
    return _setup_url


def _is_http_mode() -> bool:
    """Detect HTTP transport mode per spec 2026-05-01-stdio-pure-http-multiuser §4.1.

    Mirrors the TS detection in ``init-server.ts``: HTTP requires explicit
    opt-in via ``--http`` argv, ``MCP_TRANSPORT=http``, or ``TRANSPORT_MODE=http``.
    Default (no flag) is stdio.
    """
    return (
        "--http" in sys.argv
        or os.environ.get("MCP_TRANSPORT") == "http"
        or os.environ.get("TRANSPORT_MODE") == "http"
    )


def resolve_credential_state() -> CredentialState:
    """Fast, synchronous credential check. Called during lifespan startup.

    Stdio mode (default per spec 2026-05-01-stdio-pure-http-multiuser §4.1 + OQ3):
    env vars ONLY. ``PerPluginStore`` is NOT consulted -- stdio = single-user
    pure local; reading per-plugin store risks cross-process leak when the
    user has multiple Claude Code sessions or has previously run HTTP mode.
    Missing optional creds is acceptable -- crg has local FalkorDB + ONNX
    embedding fallback so AWAITING_SETUP is a valid steady state in stdio.

    HTTP mode (``--http`` / ``MCP_TRANSPORT=http`` / ``TRANSPORT_MODE=http``):
    env vars first, then ``PerPluginStore`` for previously-saved relay form
    submissions, then ``mcp_core.get_mode`` local-marker fallback.

    Checks (in order):
    1. ENV VARS -- if any CLOUD_KEYS present, state = CONFIGURED (both modes)
    2. CONFIG FILE -- HTTP mode only; saved config with cloud keys -> CONFIGURED
    3. LOCAL MODE MARKER -- HTTP mode only; user explicitly skipped -> LOCAL
    4. NOTHING -- state = AWAITING_SETUP

    Returns new state. Takes <10ms.
    """
    global _state

    if any(os.environ.get(k) for k in CLOUD_KEYS):
        logger.info("Cloud API keys found in environment")
        _state = CredentialState.CONFIGURED
        return _state

    if _is_http_mode():
        try:
            saved = PerPluginStore(PLUGIN_NAME).load()
            if saved and any(saved.get(k) for k in CLOUD_KEYS):
                for key, value in saved.items():
                    if value and key not in os.environ:
                        os.environ[key] = value
                logger.info("Config loaded from encrypted per-plugin store")
                _state = CredentialState.CONFIGURED
                return _state
        except Exception as e:
            # load() returns None when nothing was ever saved, so reaching
            # here means the store exists but could not be read: a corrupt
            # config.json, a rotated machine key, or a permission problem.
            # Startup still continues -- crg runs without cloud credentials --
            # but falling through silently would report "not configured yet"
            # and send the user to re-enter keys that are already saved.
            logger.warning(
                "Per-plugin credential store exists but could not be read "
                "({}: {}). Continuing in awaiting_setup mode; any saved cloud "
                "API keys are being ignored until this is resolved.",
                type(e).__name__,
                e,
            )

        try:
            from mcp_core import get_mode

            mode = get_mode(SERVER_NAME)
            if mode == "local":
                logger.info("Local mode marker found, skipping relay")
                _state = CredentialState.LOCAL
                return _state
        except Exception as e:
            # Same reasoning: get_mode returns None when no marker was ever
            # written, so an exception means an earlier "skip relay" choice is
            # unreadable and the user will be prompted to set up again.
            logger.warning(
                "Local-mode marker could not be read ({}: {}). Continuing in "
                "awaiting_setup mode; a previous 'skip relay' choice is being "
                "ignored.",
                type(e).__name__,
                e,
            )

    logger.info("No credentials found -- server starting in awaiting_setup mode")
    _state = CredentialState.AWAITING_SETUP
    return _state


def _sub_data_dir(sub: str) -> Path:
    """Return per-JWT-sub data directory (creates if missing).

    Used in multi-user remote mode where ``PUBLIC_URL`` is set. Each JWT
    ``sub`` gets its own scope for ``config.json`` (cloud API keys) and
    ``graph.db`` (per-user code knowledge graph) so credentials and graph
    state never leak across users sharing the same deployment.
    """
    # sub must be a single path component to prevent traversal.
    # JWT 'sub' should be a string like 'user-123' or a UUID, never a path.
    if (
        not sub
        or sub in (".", "..")
        or "/" in sub
        or "\\" in sub
        or os.path.sep in sub
        or (os.path.altsep and os.path.altsep in sub)
    ):
        raise ValueError(f"Invalid subject (must be a single path component): {sub}")

    base = Path(os.environ.get("CRG_DATA_DIR", str(Path.home() / ".crg")))
    subs_base = (base / "subs").resolve()

    # defense-in-depth: still verify the resolved path stays within subs_base
    d = (subs_base / sub).resolve()
    if not d.is_relative_to(subs_base) or d == subs_base:
        raise ValueError(f"Invalid subject: {sub}")

    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path_for_sub(sub: str) -> Path:
    """Return per-sub graph.db path for multi-user remote mode."""
    return _sub_data_dir(sub) / "graph.db"


def store_for_sub(sub: str, config: dict[str, str]) -> None:
    """Persist a sub's credential config to ``<data>/subs/<sub>/config.json``."""
    (_sub_data_dir(sub) / "config.json").write_text(json.dumps(config))


def read_for_sub(sub: str) -> dict[str, str]:
    """Read a sub's credential config; returns ``{}`` if absent."""
    p = _sub_data_dir(sub) / "config.json"
    return json.loads(p.read_text()) if p.exists() else {}


def set_current_sub(sub: str | None) -> None:
    """Set the JWT ``sub`` for the current request (HTTP multi-user mode).

    Called by the ``auth_scope`` middleware in :func:`run_http` so per-tool-call
    handlers can resolve credentials for the right user via
    :func:`credentials_for_current_request`. Pass ``None`` to clear.
    """
    _current_sub.set(sub)


def get_current_sub() -> str | None:
    """Return the subject, refusing unscoped access on a remote deployment."""
    sub = _current_sub.get()
    if os.environ.get("PUBLIC_URL") and not sub:
        raise RuntimeError("Remote requests require an authenticated subject")
    return sub


def credentials_for_current_request() -> dict[str, str]:
    """Return cloud API key dict applicable to the current request.

    HTTP multi-user mode: ``auth_scope`` middleware sets ``_current_sub``
    from the verified JWT before the tool handler runs. We look up that
    user's per-sub bucket (``<CRG_DATA_DIR>/subs/<sub>/config.json``) and
    return its contents. Empty dict if the user has not completed setup.

    Stdio / single-user HTTP contexts without PUBLIC_URL may use process
    credentials. Remote requests without an authenticated subject fail closed.
    """
    sub = get_current_sub()
    if sub is None:
        return {k: v for k, v in os.environ.items() if k in CLOUD_KEYS and v}
    return read_for_sub(sub)


def config_value_for_current_request(key: str) -> str | None:
    """Return a single config value scoped to the current request.

    HTTP multi-user mode (``_current_sub`` set by the ``auth_scope``
    middleware): reads ``key`` from that user's per-sub bucket
    (``<CRG_DATA_DIR>/subs/<sub>/config.json``) and NOTHING else, so one
    user's API keys / model chain never reach another concurrent user's
    request. Returns ``None`` if the sub has not configured that key.

    Stdio / single-user HTTP / no-JWT contexts (``_current_sub`` is
    ``None``): falls back to the process environment via ``os.environ.get``,
    preserving the existing single-user ``apply_config`` -> env behavior.

    This helper is the request-scoped read path that live dispatch
    (embedding + summarizer chain/key resolution) MUST use instead of
    reading ``os.environ`` directly: per-sub values flow request-scoped and
    are never written to the process-global environment.
    """
    sub = get_current_sub()
    if sub is None:
        return os.environ.get(key)
    value = read_for_sub(sub).get(key)
    return value if value else None


def save_credentials(
    config: dict[str, str], context: dict[str, str] | None = None
) -> dict | None:
    """Save credentials from OAuth form and apply to environment.

    Single-user mode (default, ``PUBLIC_URL`` unset): writes via
    ``PerPluginStore`` to ``~/.better-code-review-graph-mcp/config.json``
    (AES-GCM, machine-bound key) -- one set of cloud API keys for one user.

    Multi-user remote mode (``PUBLIC_URL`` set): scopes credentials by the
    per-authorize JWT ``sub`` from ``context``. Each user's keys land in
    ``<CRG_DATA_DIR>/subs/<sub>/config.json`` so credentials never leak
    across users. Refuses to persist if ``sub`` missing.

    Called by the local OAuth AS when the user submits API keys via the
    browser form. Returns optional dict with next_step info (always None
    for CRG -- no multi-step flow).
    """
    global _state

    if os.environ.get("PUBLIC_URL"):
        sub = context.get("sub") if context else None
        if not sub:
            raise RuntimeError(
                "multi-user mode: SubjectContext sub required to save credentials"
            )
        store_for_sub(sub, config)
        _state = CredentialState.CONFIGURED
        logger.info("Credentials saved for sub={} via remote OAuth form", sub)
        return None

    from better_code_review_graph.relay_setup import apply_config

    PerPluginStore(PLUGIN_NAME).save(config)
    apply_config(config)
    _state = CredentialState.CONFIGURED
    logger.info("Credentials saved via local OAuth form")
    return None


def set_state(state: CredentialState) -> None:
    """For testing and setup tool actions."""
    global _state
    _state = state


def reset_state() -> None:
    """Reset to awaiting_setup (used by setup reset action)."""
    global _state, _setup_url
    _state = CredentialState.AWAITING_SETUP
    _setup_url = None

    try:
        from mcp_core import clear_mode

        clear_mode(SERVER_NAME)
        PerPluginStore(PLUGIN_NAME).clear()
    except Exception as e:
        logger.warning("Exception in %s: %s", __name__, e)


# ---------------------------------------------------------------------------
# Simple load/save/clear helpers (thin wrappers over PerPluginStore)
# ---------------------------------------------------------------------------


def load_credentials(sub: str | None = None) -> dict:
    """Load credentials from per-plugin store. Returns empty dict if absent."""
    return PerPluginStore(PLUGIN_NAME, sub).load() or {}


def clear_credentials(sub: str | None = None) -> None:
    """Remove credentials from per-plugin store."""
    PerPluginStore(PLUGIN_NAME, sub).clear()
