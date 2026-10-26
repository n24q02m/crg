"""Shared E2E test infrastructure for MCP servers.

Provides:
- --setup CLI option (relay | env | plugin)
- --browser CLI option (chrome | brave | edge)
- StderrCapture for relay URL detection
- open_browser() helper
- parse_result() / parse_result_allow_error() helpers

Copy this file to each MCP server's tests/ directory unchanged.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from typing import TextIO

BROWSER_PATHS: dict[str, str] = {
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
}

RELAY_URL_PATTERN = re.compile(r"https?://\S+#k=[A-Za-z0-9+/=_-]+&p=\S+")


def pytest_addoption(parser):
    """Add --setup and --browser CLI options for E2E tests."""
    parser.addoption(
        "--setup",
        choices=["relay", "env", "plugin"],
        default="env",
        help="Server setup mode: relay (manual credentials), env (env vars), plugin (published package)",
    )
    parser.addoption(
        "--browser",
        default="chrome",
        choices=["chrome", "brave", "edge"],
        help="Browser to open relay page (only used with --setup=relay)",
    )


class StderrCapture:
    """Capture subprocess stderr to a temp file for relay URL detection.

    On Windows, subprocess connects directly to a file descriptor,
    bypassing any Python-level write(). We use a real temp file
    and poll it for the relay URL.
    """

    def __init__(self, real_stderr: TextIO | None = None):
        import tempfile

        self._real_stderr = real_stderr or sys.stderr
        # Use a real temp file so subprocess can write via fd
        self._file = tempfile.NamedTemporaryFile(
            mode="w+", suffix=".log", delete=False, encoding="utf-8"
        )
        self._path = self._file.name

    def write(self, text: str) -> int:
        """Write to temp file (called on non-Windows or pipe mode)."""
        self._file.write(text)
        self._file.flush()
        return self._real_stderr.write(text)

    def flush(self) -> None:
        self._file.flush()
        self._real_stderr.flush()

    def fileno(self):
        """Return temp file fd for subprocess stderr redirection."""
        return self._file.fileno()

    def get_relay_url(self, timeout: float = 30.0) -> str | None:
        """Wait for relay URL to appear in captured stderr file."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with open(self._path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                match = RELAY_URL_PATTERN.search(content)
                if match:
                    return match.group(0)
            except (OSError, PermissionError):
                pass
            time.sleep(0.5)
        return None

    def get_output(self) -> str:
        """Read all captured stderr output."""
        try:
            with open(self._path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except (OSError, PermissionError):
            return ""

    def close(self):
        """Clean up temp file."""
        try:
            self._file.close()
        except Exception:
            pass
        try:
            os.unlink(self._path)
        except Exception:
            pass


def open_browser(url: str, browser: str = "chrome") -> None:
    """Open URL in specified browser."""
    exe = BROWSER_PATHS.get(browser)
    if exe and os.path.exists(exe):
        subprocess.Popen(
            [exe, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    else:
        import webbrowser

        webbrowser.open(url)


def parse_result(r) -> str:
    """Extract text from MCP tool result. Raise on error."""
    if hasattr(r, "is_error") and r.is_error:
        raise AssertionError(f"Tool returned error: {r.content[0].text}")
    return r.content[0].text


def parse_result_allow_error(r) -> str:
    """Extract text from MCP tool result, including errors."""
    return r.content[0].text
