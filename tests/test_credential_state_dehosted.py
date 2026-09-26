"""Per-request subject scoping and data paths on the de-hosted surface.

Covers the still-consumer-visible parts of ``credential_state`` after the
BYOK cut removed the credential store / browser setup flow:

- ``CredentialState`` values and ``get_state``/``set_state``.
- ``set_current_sub``/``get_current_sub`` round-trip and the ``None`` default.
- ``db_path_for_sub`` layout (``<CRG_DATA_DIR>/subs/<sub>/graph.db``) and
  path-safety rejection of hostile subjects.
- ``resolve_credential_state`` reporting ``CONFIGURED``/``LOCAL`` from the
  host's model cells (no per-user stores involved).
"""

from __future__ import annotations

import pytest

from better_code_review_graph.credential_state import (
    SERVER_NAME,
    CredentialState,
    db_path_for_sub,
    get_current_sub,
    get_state,
    resolve_credential_state,
    set_current_sub,
    set_state,
)


@pytest.fixture(autouse=True)
def _reset_sub_and_state():
    """Leave process-global state untouched for other tests."""
    set_current_sub(None)
    yield
    set_current_sub(None)
    set_state(CredentialState.LOCAL)


class TestConstantsAndEnum:
    def test_server_name(self):
        assert SERVER_NAME == "better-code-review-graph"

    def test_credential_state_enum_values(self):
        # The BYOK cut collapsed the old awaiting_setup/setup_in_progress
        # machine to a pure configured/local report.
        assert {member.name for member in CredentialState} == {
            "CONFIGURED",
            "LOCAL",
        }


class TestStateAccessors:
    def test_set_state_changes_state(self):
        set_state(CredentialState.CONFIGURED)
        assert get_state() is CredentialState.CONFIGURED

    def test_set_state_to_local(self):
        set_state(CredentialState.CONFIGURED)
        set_state(CredentialState.LOCAL)
        assert get_state() is CredentialState.LOCAL


class TestCurrentSub:
    def test_default_is_none(self):
        set_current_sub(None)
        assert get_current_sub() is None

    def test_set_current_sub_roundtrip(self):
        set_current_sub("user_a")
        assert get_current_sub() == "user_a"

    def test_set_current_sub_none_clears(self):
        set_current_sub("user_a")
        set_current_sub(None)
        assert get_current_sub() is None


class TestDataDirPaths:
    def test_db_path_for_sub_layout(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
        path = db_path_for_sub("alice")
        assert path == tmp_path / "subs" / "alice" / "graph.db"

    def test_db_path_for_sub_uses_home_default(self, monkeypatch, tmp_path):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("USERPROFILE", str(fake_home))
        monkeypatch.delenv("CRG_DATA_DIR", raising=False)
        path = db_path_for_sub("bob")
        assert path == fake_home / ".crg" / "subs" / "bob" / "graph.db"

    @pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "a\\b"])
    def test_db_path_for_sub_rejects_hostile_subjects(self, monkeypatch, tmp_path, bad):
        monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
        with pytest.raises(ValueError, match="Invalid subject"):
            db_path_for_sub(bad)


class TestResolveCredentialState:
    def test_reports_local_without_cells(self, monkeypatch, tmp_path):
        # Point the instance config at an empty dir: no cells configured.
        monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "cfg"))
        state = resolve_credential_state()
        assert state in (CredentialState.LOCAL, CredentialState.CONFIGURED)

    def test_reports_configured_with_cell_key_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setenv("HULL_CHAT_API_KEY", "k-test")
        try:
            state = resolve_credential_state()
        finally:
            monkeypatch.delenv("HULL_CHAT_API_KEY", raising=False)
        assert state is CredentialState.CONFIGURED
