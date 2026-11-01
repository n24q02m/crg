"""Tests for credential_state -- hull-core identity scoping + cell state.

WP2 de-host: there is no credential store, no browser setup, and no per-user key
bucket. What remains is (a) the host-level CONFIGURED/LOCAL cell state,
(b) the per-request subject contextvar with hull ``multi``-mode fallback,
and (c) the ``subs/<namespace>/graph.db`` path helpers.
"""

from __future__ import annotations

import pytest

import crg.credential_state as cs
from crg.credential_state import (
    SERVER_NAME,
    CredentialState,
    get_current_sub,
    get_state,
    resolve_credential_state,
    set_current_sub,
    set_state,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level state before and after each test."""
    set_current_sub(None)
    set_state(CredentialState.LOCAL)
    yield
    set_current_sub(None)
    set_state(CredentialState.LOCAL)


def _write_config(tmp_path, body: str):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "config.toml").write_text(body, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_server_name(self):
        assert SERVER_NAME == "crg"

    def test_credential_state_enum_values(self):
        assert CredentialState.CONFIGURED.value == "configured"
        assert CredentialState.LOCAL.value == "local"

    def test_enum_has_exactly_two_states(self):
        # No BYOK-era states may reappear (awaiting_setup / setup_in_progress).
        assert {member.name for member in CredentialState} == {"CONFIGURED", "LOCAL"}


# ---------------------------------------------------------------------------
# get_state / set_state
# ---------------------------------------------------------------------------


class TestStateAccessors:
    def test_set_state_changes_state(self):
        set_state(CredentialState.CONFIGURED)
        assert get_state() == CredentialState.CONFIGURED

    def test_set_state_to_local(self):
        set_state(CredentialState.LOCAL)
        assert get_state() == CredentialState.LOCAL


# ---------------------------------------------------------------------------
# resolve_credential_state (host model cells)
# ---------------------------------------------------------------------------


class TestResolveCredentialState:
    def test_no_config_is_local(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "absent"))
        assert resolve_credential_state() == CredentialState.LOCAL
        assert get_state() == CredentialState.LOCAL

    def test_chat_cell_key_sets_configured(self, tmp_path, monkeypatch):
        _write_config(
            tmp_path,
            '[models.chat]\nbase_url = "https://openrouter.ai/api/v1"\napi_key = "sk-h"\nmodel = "m"\n',
        )
        monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path))
        assert resolve_credential_state() == CredentialState.CONFIGURED

    def test_embed_cell_env_key_sets_configured(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("HULL_EMBED_API_KEY", "sk-e")
        try:
            assert resolve_credential_state() == CredentialState.CONFIGURED
        finally:
            monkeypatch.delenv("HULL_EMBED_API_KEY")

    def test_cell_without_key_stays_local(self, tmp_path, monkeypatch):
        _write_config(
            tmp_path,
            '[models.embed]\nbase_url = "https://openrouter.ai/api/v1"\napi_key = ""\nmodel = "voyage-4-lite"\n',
        )
        monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path))
        assert resolve_credential_state() == CredentialState.LOCAL


# ---------------------------------------------------------------------------
# Credential isolation regression guard
# ---------------------------------------------------------------------------


class TestCredentialIsolation:
    """crg must not write to peer MCP servers' configs."""

    def test_no_peer_key_sharing_helper(self):
        assert not hasattr(cs, "_share_cloud_keys_to_peers")


class TestCutSurfaceAbsent:
    """The BYOK surface must not reappear after the de-host."""

    @pytest.mark.parametrize(
        "symbol",
        [
            "CLOUD_KEYS",
            "credentials_for_current_request",
            "config_value_for_current_request",
            "save_credentials",
            "store_for_sub",
            "read_for_sub",
            "get_setup_url",
            "reset_state",
            "load_credentials",
            "clear_credentials",
        ],
    )
    def test_symbol_removed(self, symbol):
        assert not hasattr(cs, symbol)


# ---------------------------------------------------------------------------
# Current subject
# ---------------------------------------------------------------------------


class TestCurrentSub:
    def test_default_is_none(self):
        assert get_current_sub() is None

    def test_set_current_sub_roundtrip(self):
        set_current_sub("user-a")
        assert get_current_sub() == "user-a"

    def test_clearing_restores_none(self):
        set_current_sub("user-a")
        set_current_sub(None)
        assert get_current_sub() is None
