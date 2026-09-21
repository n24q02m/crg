"""Credential resolution for better-code-review-graph.

Resolution order (relay only when ALL local sources are empty):
1. ENV VARS          -- User explicitly set (highest priority, skip everything)
2. RELAY CONFIG      -- Saved from previous setup (PerPluginStore, ~/.better-code-review-graph-mcp/config.json)
3. RELAY SETUP       -- Interactive, ONLY when steps 1-2 are ALL empty (30s timeout)
4. LOCAL MODE        -- Fallback through fastretrieval
"""

from __future__ import annotations

import logging
import os
import sys

from mcp_core.storage.per_plugin_store import PerPluginStore

from .relay_schema import RELAY_SCHEMA

logger = logging.getLogger(__name__)

SERVER_NAME = "better-code-review-graph"
REQUIRED_FIELDS = [
    "GEMINI_API_KEY"
]  # Used for config file lookup (any key triggers match)

# Cloud API keys that indicate user has env vars configured
CLOUD_KEYS = [
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "JINA_AI_API_KEY",
    "OPENAI_API_KEY",
    "COHERE_API_KEY",
    "CO_API_KEY",
    "GOOGLE_VERTEX_EXPRESS_API_KEY",
]

# Shorter timeout for optional-credential servers (user can skip)
RELAY_TIMEOUT_S = 120.0


def apply_config(config: dict[str, str]) -> None:
    """Apply config dict to environment variables."""
    for key, value in config.items():
        if value and key not in os.environ:
            os.environ[key] = value
            logger.debug("Applied relay config: %s", key)


async def ensure_config() -> dict[str, str] | None:
    """Resolve config: env vars -> config file -> relay setup -> local fallback.

    Relay is ONLY triggered when steps 1-2 are ALL empty.
    Uses 30s timeout since CRG works locally without credentials.

    Returns:
        Config dict with credential keys, or None if skipped/failed (local mode).
    """
    # 1. Check env vars directly (highest priority, fast path)
    if any(os.environ.get(k) for k in CLOUD_KEYS):
        logger.info("Cloud API keys found in environment, skipping relay")
        return None  # env vars take priority, no relay needed

    # 2. Check saved per-plugin store (any cloud key is sufficient)
    try:
        saved = PerPluginStore(SERVER_NAME).load()
        if saved and any(saved.get(k) for k in CLOUD_KEYS):
            logger.info("Config loaded from per-plugin store")
            for key, value in saved.items():
                os.environ.setdefault(key, value)
            return saved
    except Exception as e:
        logger.debug("Exception in %s: %s", __name__, e)

    # 3. No local credentials found -- trigger relay setup.
    # Per mode-matrix 2.5, better-code-review-graph default is `http local relay`;
    # `remote-relay` mode requires user-supplied URL (no centralized
    # better-code-review-graph.n24q02m.com).
    relay_url = os.environ.get("MCP_RELAY_URL")
    if not relay_url:
        raise RuntimeError(
            "MCP_RELAY_URL env var is required for remote-relay mode. "
            "better-code-review-graph default mode is 'http local relay' "
            "(no remote URL needed). For self-host remote-relay, "
            "set MCP_RELAY_URL=https://<your-instance>."
        )

    logger.info("No credentials found. Starting relay setup...")
    try:
        from mcp_core.relay.client import create_session

        # RELAY_SCHEMA is dict[str, Any] for forward-compat with newer
        # relay UI keys — see relay_schema.py for details.
        session = await create_session(relay_url, SERVER_NAME, RELAY_SCHEMA)  # ty: ignore[invalid-argument-type]
    except Exception:
        logger.debug(
            "Cannot reach relay server at %s. Using local mode.",
            relay_url,
            exc_info=True,
        )
        return None

    # Log URL to stderr (visible to user in MCP client)
    print(
        f"\nConfigure cloud embedding (optional, 30s timeout):"
        f"\n{session.relay_url}"
        f"\nSkip to use local mode through fastretrieval.\n",
        file=sys.stderr,
        flush=True,
    )

    # Poll for result with shorter timeout
    try:
        from mcp_core.relay.client import poll_for_result

        config = await poll_for_result(relay_url, session, timeout_s=RELAY_TIMEOUT_S)

        # Save to per-plugin store
        PerPluginStore(SERVER_NAME).save(config)
        logger.info("Config saved successfully")

        # Notify relay page that setup is complete
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as http:
                await http.post(
                    f"{relay_url}/api/sessions/{session.session_id}/messages",
                    json={
                        "type": "complete",
                        "text": "CRG config saved. Setup complete!",
                    },
                )
        except Exception as e:
            logger.debug("Exception in %s: %s", __name__, e)

        # Inject into environment
        for key, value in config.items():
            os.environ.setdefault(key, value)

        return config

    except RuntimeError as e:
        if "RELAY_SKIPPED" in str(e):
            logger.info("Relay setup skipped by user. Using local mode.")
        elif "timed out" in str(e).lower():
            logger.info("Relay setup timed out. Using local mode.")
        else:
            logger.debug("Relay setup ended: %s", e)
        return None
