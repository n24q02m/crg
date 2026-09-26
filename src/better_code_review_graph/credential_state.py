"""Per-request subject scoping and per-sub data paths.

De-hosted (WP2, spec 2026-09-26 §4): authentication is hull-core's token
middleware with three config modes (no-auth / token / multi, ``users.toml``).
There is no credential store, no browser setup flow, and no per-user key
bucket —
provider keys are host-only material configured in the instance
``config.toml`` ``[models.*]`` cells (or ``HULL_<TASK>_API_KEY`` env); the
end user never sees or submits them (BYOK cut).

What remains here is the data-isolation half: in auth mode ``multi`` the
authenticated user's namespace scopes the graph database at
``subs/<namespace>/graph.db`` under ``CRG_DATA_DIR`` so concurrent users on
one process never see each other's graph. Modes no-auth/token keep one
shared namespace and therefore the repo-local ``graph.db`` (same file the
CLI uses — host indexing and serving stay consistent).
"""

from __future__ import annotations

import contextvars
import logging
import os
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

SERVER_NAME = "better-code-review-graph"


class CredentialState(Enum):
    CONFIGURED = "configured"  # at least one per-task model cell has a key
    LOCAL = "local"  # no cloud cells configured; local ONNX fallback serves


# Module-level state (host-level; never per-request — per-request identity
# flows exclusively through the contextvars below).
_state: CredentialState = CredentialState.LOCAL

# Per-request namespace subject (HTTP multi-user mode).
#
# Bound by the hull auth middleware's resolved identity: tool handlers call
# :func:`get_current_sub`, which prefers an explicit :func:`set_current_sub`
# binding and otherwise falls back to hull-core's ``current_user()``
# contextvar when the request authenticated in ``multi`` mode. ``None`` in
# stdio mode, the CLI, and single-namespace HTTP modes (no-auth/token) —
# those share the repo-local graph.db.
_current_sub: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "crg_current_sub", default=None
)


def get_state() -> CredentialState:
    """Return current credential state."""
    return _state


def resolve_credential_state() -> CredentialState:
    """Resolve whether any per-task model cell is configured (has a key).

    Host-only check against the instance ``config.toml`` cells + key env
    vars. Local ONNX embedding and everything except cloud summarize/embed
    work regardless, so ``LOCAL`` is a valid steady state, not an error.
    Takes <10ms; called during HTTP lifespan startup and by ``config``.
    """
    global _state

    from .config import resolve_cells

    cells = resolve_cells()
    configured = any(cell.configured for cell in cells.values())
    _state = CredentialState.CONFIGURED if configured else CredentialState.LOCAL
    logger.info("Credential state resolved: %s", _state.value)
    return _state


def set_state(state: CredentialState) -> None:
    """For testing and the config tool status action."""
    global _state
    _state = state


def _sub_data_dir(sub: str) -> Path:
    """Return per-sub data directory (creates if missing).

    Each authenticated namespace gets its own scope under
    ``<CRG_DATA_DIR>/subs/<sub>/`` so graph state never leaks across users
    sharing one deployment process.
    """
    # sub must be a single path component to prevent traversal.
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
    """Return per-sub graph.db path for multi-user mode."""
    return _sub_data_dir(sub) / "graph.db"


def set_current_sub(sub: str | None) -> None:
    """Bind the namespace subject for the current request (multi-user mode).

    Normally the hull auth middleware's identity is consumed implicitly via
    :func:`get_current_sub`; this explicit binding exists for tests and
    host tooling that must scope work to one namespace outside a request.
    Pass ``None`` to clear.
    """
    _current_sub.set(sub)


def get_current_sub() -> str | None:
    """Return the namespace subject for the current request, or ``None``.

    Resolution order:

    1. Explicit :func:`set_current_sub` binding.
    2. hull-core's request identity (``current_user()``) when the request
       authenticated in ``multi`` mode — its namespace is the data root.
       Worker-thread tool handlers inherit the contextvar via anyio's
       context copy, same channel hull's own tools use.

    ``None`` means shared-namespace context (stdio, CLI, no-auth/token HTTP):
    callers use the repo-local ``graph.db``.
    """
    sub = _current_sub.get()
    if sub is not None:
        return sub

    from hull_core.auth.context import current_user

    try:
        ctx = current_user()
    except Exception:  # pragma: no cover - hull always present post de-host
        return None
    if ctx.mode == "multi" and ctx.namespace:
        sub = ctx.namespace
        # Reuse the path-safety validation so a hostile users.toml namespace
        # cannot escape the subs/ root.
        _sub_data_dir(sub)
        return sub
    return None
