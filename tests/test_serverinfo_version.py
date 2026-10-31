"""Regression test: server reports its own package version in serverInfo.

Previously the FastMCP constructor was called without ``version=``, so the
reported version defaulted to the fastmcp framework version (e.g. "3.4.2")
instead of the crg package version.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from unittest.mock import patch

from crg.server import _resolve_version, mcp


def test_serverinfo_reports_package_version():
    for name in ("n24q02m-crg", "better-code-review-graph"):
        try:
            expected = pkg_version(name)
            break
        except PackageNotFoundError:
            pass
    else:
        raise PackageNotFoundError("n24q02m-crg")
    reported = mcp._mcp_server.create_initialization_options().server_version
    assert reported == expected


def test_serverinfo_not_fastmcp_version():
    reported = mcp._mcp_server.create_initialization_options().server_version
    fastmcp_version = pkg_version("fastmcp")
    assert reported != fastmcp_version


def test_resolve_version_fallback_when_not_installed():
    with patch(
        "crg.server.pkg_version",
        side_effect=PackageNotFoundError("better-code-review-graph"),
    ):
        assert _resolve_version() == "dev"
