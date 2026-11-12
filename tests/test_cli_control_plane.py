"""Host control-plane CLI: server/token/config/db subcommands (WP2 lifecycle).

Fast, hermetic coverage of the operator surface — the server path is tested
end-to-end (spawn + bearer + build/query) in tests/test_http_mcp_e2e.py; here
we pin the dispatch contract and the env handoff to run_http().
"""

from __future__ import annotations

import sys
from pathlib import Path

from crg.cli import main


def _run(capsys, *argv: str) -> int:
    sys.argv = ["crg", *argv]
    return main()


def test_token_hash_matches_hull_primitive(capsys) -> None:
    from hull_core.auth.tokens import verify_token

    rc = _run(capsys, "token", "hash", "s3cret-token")
    out = capsys.readouterr().out.strip()
    assert rc == 0
    # scrypt hashes are salted per call: verify rather than compare.
    assert verify_token("s3cret-token", out)
    assert not verify_token("wrong-token", out)
    rc2 = _run(capsys, "token", "hash", "s3cret-token")
    out2 = capsys.readouterr().out.strip()
    assert rc2 == 0
    assert out2 != out  # fresh salt per mint


def test_config_path_prints_instance_config(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path))
    rc = _run(capsys, "config", "path")
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == str(Path(tmp_path) / "config.toml")


def test_config_init_writes_then_refuses_without_force(
    capsys, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path))
    rc = _run(capsys, "config", "init")
    assert rc == 0
    assert (Path(tmp_path) / "config.toml").is_file()

    rc = _run(capsys, "config", "init")
    err = capsys.readouterr().err
    assert rc == 2
    assert "error" in err

    rc = _run(capsys, "config", "init", "--force")
    assert rc == 0


def test_config_show_prints_template_when_absent(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "missing"))
    rc = _run(capsys, "config", "show")
    out = capsys.readouterr().out
    assert rc == 0
    assert "[server]" in out  # template content


def test_db_path_prints_graph_db(capsys) -> None:
    rc = _run(capsys, "db", "path")
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out.endswith("graph.db")


def test_server_start_forces_http_transport(capsys, tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.toml").write_text(
        '[server]\nhost = "127.0.0.1"\nport = 61000\nauth = "no-auth"\n'
    )
    monkeypatch.setenv("CRG_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("MCP_HOST", raising=False)
    monkeypatch.delenv("MCP_PORT", raising=False)
    seen: dict[str, object] = {}

    def fake_serve_main() -> None:
        seen["transport"] = __import__("os").environ.get("MCP_TRANSPORT")
        seen["host"] = __import__("os").environ.get("MCP_HOST")
        seen["port"] = __import__("os").environ.get("MCP_PORT")

    monkeypatch.setattr("crg.server.serve_main", fake_serve_main)

    rc = _run(capsys, "server", "start", "--host", "127.0.0.1", "--port", "60077")
    assert rc == 0
    assert seen == {"transport": "http", "host": "127.0.0.1", "port": "60077"}


def test_server_start_keyboard_interrupt_is_clean(capsys, monkeypatch) -> None:
    def interrupted() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("crg.server.serve_main", interrupted)
    rc = _run(capsys, "server", "start")
    assert rc == 0


def test_server_start_refuses_no_auth_off_loopback(
    capsys, tmp_path, monkeypatch
) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.toml").write_text(
        '[server]\nhost = "127.0.0.1"\nport = 61000\nauth = "no-auth"\n'
    )
    monkeypatch.setenv("CRG_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("MCP_HOST", raising=False)
    serve_called = False

    def must_not_serve() -> None:
        nonlocal serve_called  # noqa: F841
        serve_called = True  # pragma: no cover

    monkeypatch.setattr("crg.server.serve_main", must_not_serve)
    rc = _run(capsys, "server", "start", "--host", "0.0.0.0")
    err = capsys.readouterr().err
    assert rc == 2
    assert "no-auth" in err and "loopback" in err
    assert serve_called is False


def test_server_start_refuses_no_auth_config_host_off_loopback(
    capsys, tmp_path, monkeypatch
) -> None:
    """Bypass regression: no --host/MCP_HOST, config-sourced host binds."""
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.toml").write_text(
        '[server]\nhost = "0.0.0.0"\nport = 61000\nauth = "no-auth"\n'
    )
    monkeypatch.setenv("CRG_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("MCP_HOST", raising=False)
    serve_called = False

    def must_not_serve() -> None:
        nonlocal serve_called  # noqa: F841
        serve_called = True  # pragma: no cover

    monkeypatch.setattr("crg.server.serve_main", must_not_serve)
    rc = _run(capsys, "server", "start")
    err = capsys.readouterr().err
    assert rc == 2
    assert "no-auth" in err and "loopback" in err
    assert serve_called is False


def test_unknown_subcommand_is_rc2(capsys) -> None:
    rc = _run(capsys, "nope")
    err = capsys.readouterr().err
    assert rc == 2
    assert "unknown subcommand" in err


def test_config_get_and_set_share_the_hull_editor(capsys, tmp_path, monkeypatch) -> None:
    """`config set` rewrites one line and `config get` reads it back."""
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path))
    assert _run(capsys, "config", "init") == 0
    capsys.readouterr()

    assert _run(capsys, "config", "set", "server.port", "9100") == 0
    capsys.readouterr()
    body = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "port = 9100" in body
    # The template's comments survive: a round-trip through a TOML writer
    # would drop every one of them.
    assert "# " in body

    assert _run(capsys, "config", "get", "server.port") == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "9100"


def test_config_get_masks_a_token_and_keeps_a_hash(capsys, tmp_path, monkeypatch) -> None:
    """Credential-shaped values are not echoed; a scrypt hash is not one."""
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path))
    assert _run(capsys, "config", "init") == 0
    capsys.readouterr()
    assert _run(capsys, "config", "set", "server.token", "s3cret") == 0
    capsys.readouterr()

    assert _run(capsys, "config", "get", "server.token") == 0
    out = capsys.readouterr().out
    assert "s3cret" not in out
    assert "***" in out

    assert _run(capsys, "config", "set", "server.token_hash", "abc123") == 0
    capsys.readouterr()
    assert _run(capsys, "config", "get", "server.token_hash") == 0
    assert "abc123" in capsys.readouterr().out


def test_config_get_refuses_an_unknown_key(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path))
    assert _run(capsys, "config", "init") == 0
    capsys.readouterr()

    assert _run(capsys, "config", "get", "server.nope") == 2
    assert "key not found" in capsys.readouterr().err
