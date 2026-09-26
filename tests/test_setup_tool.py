"""Tests for setup_* sub-actions of the config tool (server.py).

Covers the de-hosted action set — config(action=setup_status|setup_start|
setup_skip|setup_reset|setup_complete) plus unknown-action variants. The
BYOK-era surface is gone: no browser relay flow, no ``_setup_url``/``_
maybe_include_setup_hint`` hook, no per-user credential store. Keys are
host-only material in instance config ``[models.<task>]`` cells or
``HULL_<TASK>_API_KEY`` env vars.
"""

from __future__ import annotations

import pytest

from better_code_review_graph.credential_state import CredentialState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_credential_state():
    """Reset credential state module before/after each test."""
    import better_code_review_graph.credential_state as cs

    original_state = cs._state
    yield
    cs._state = original_state


@pytest.fixture(autouse=True)
def _hermetic_config_dir(monkeypatch, tmp_path):
    """Empty per-test instance config dir; every cell env key removed."""
    import better_code_review_graph.credential_state as cs

    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "cfg"))
    for k in (
        "HULL_EMBED_API_KEY",
        "HULL_RERANK_API_KEY",
        "HULL_CHAT_API_KEY",
        "HULL_JEV_SCORE_API_KEY",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    cs._state = CredentialState.LOCAL


# ---------------------------------------------------------------------------
# config setup_status action
# ---------------------------------------------------------------------------


class TestSetupStatus:
    async def test_status_reports_configured_cell(self, monkeypatch):
        """setup_status derives `configured` from live host cells (G6 fix)."""
        from better_code_review_graph.server import config

        monkeypatch.setenv("HULL_EMBED_API_KEY", "test-key-123")

        result = await config(action="setup_status")
        assert result["state"] == "configured"
        assert result["providers_configured"] == ["embed"]

    async def test_status_has_no_relay_setup_url(self):
        """Post-de-host there is no browser setup form: setup_url is None."""
        from better_code_review_graph.server import config

        result = await config(action="setup_status")
        assert result["state"] == "local"
        assert result["setup_url"] is None


# ---------------------------------------------------------------------------
# config setup_start action
# ---------------------------------------------------------------------------


class TestSetupStart:
    async def test_start_already_configured_no_force(self):
        """setup_start with already configured state and no force returns already_configured."""
        import better_code_review_graph.credential_state as cs
        from better_code_review_graph.server import config

        cs._state = CredentialState.CONFIGURED

        result = await config(action="setup_start")
        assert result["status"] == "already_configured"
        assert "force=true" in result["message"]

    async def test_start_points_at_host_config_surface(self, monkeypatch):
        """setup_start explains the host-owned config surface (no browser flow).

        The pre-de-host response carried a PUBLIC_URL /authorize relay link
        (or a stdio env-var hint); the BYOK cut removed both — end users
        never supply keys, the host configures cells instead.
        """
        from better_code_review_graph.server import config

        monkeypatch.setenv("PUBLIC_URL", "https://relay.example.com")

        result = await config(action="setup_start")
        assert result["status"] == "host_config"
        assert "models.<task>" in result["message"]
        assert "HULL_" in result["message"]
        assert "setup_url" not in result

    async def test_start_force_overrides_configured(self):
        """setup_start with force=true re-reports the config surface."""
        import better_code_review_graph.credential_state as cs
        from better_code_review_graph.server import config

        cs._state = CredentialState.CONFIGURED

        result = await config(action="setup_start", force=True)
        assert result["status"] == "host_config"


# ---------------------------------------------------------------------------
# config setup_skip action
# ---------------------------------------------------------------------------


class TestSetupSkip:
    async def test_skip_sets_local_state(self):
        """setup_skip records LOCAL mode; no relay-mode marker is written.

        Pre-de-host this also called the shared core's set_local_mode to
        suppress the relay on restart; that store is gone, so the state
        enum is the only remaining mode keeper.
        """
        import better_code_review_graph.credential_state as cs
        from better_code_review_graph.server import config

        result = await config(action="setup_skip")
        assert result["status"] == "ok"
        assert "Local mode" in result["message"]
        assert cs.get_state() is CredentialState.LOCAL


# ---------------------------------------------------------------------------
# config setup_reset action
# ---------------------------------------------------------------------------


class TestSetupReset:
    async def test_reset_resets_to_local(self):
        """setup_reset resets state to local; host config re-resolves later."""
        import better_code_review_graph.credential_state as cs
        from better_code_review_graph.server import config

        cs._state = CredentialState.CONFIGURED

        result = await config(action="setup_reset")
        assert result["status"] == "ok"
        assert cs.get_state() is CredentialState.LOCAL


# ---------------------------------------------------------------------------
# config setup_complete action
# ---------------------------------------------------------------------------


class TestSetupComplete:
    async def test_complete_refreshes_state_from_cells(self, monkeypatch):
        """setup_complete re-resolves credential state from host cells."""
        from better_code_review_graph.server import config

        monkeypatch.setenv("HULL_EMBED_API_KEY", "test-key")

        result = await config(action="setup_complete")
        assert result["status"] == "ok"
        assert result["state"] == "configured"


# ---------------------------------------------------------------------------
# config setup_* unknown action (via config unknown action path)
# ---------------------------------------------------------------------------


class TestSetupUnknownAction:
    async def test_unknown_action_returns_error(self):
        """Unknown action returns error with valid actions."""
        from better_code_review_graph.server import config

        result = await config(action="nonexistent_setup_action")
        assert "error" in result
        assert "valid_actions" in result

    async def test_setup_prefix_typo_suggestion(self):
        """Typo in setup_ action returns a suggestion."""
        from better_code_review_graph.server import config

        result = await config(action="setup_statu")
        assert "error" in result
        assert "setup_status" in result["error"]
