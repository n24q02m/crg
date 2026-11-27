#!/usr/bin/env python3
"""CRG-22 PreToolUse security guard hook (stdlib-only, <300ms, <=300B stdout).

Inspects Claude Code ``PreToolUse`` payloads for ``Bash``, ``Write``, and
``Edit`` tool invocations and blocks high-confidence hazards:

* Remote code execution pipelines (``curl ... | bash``, ``wget ... | sh``)
* Destructive filesystem wipes, raw disk writes, fork bombs, reverse shells
* Environment/SSH file exfiltration over network utilities
* Writing hardcoded credentials/private keys or restricted system paths

Fails open (exit 0, silent stdout) on unreadable input or unrelated tools so
developer workflows never stall on malformed hook payloads.
"""

from __future__ import annotations

import json
import re
import sys

MAX_STDOUT_CHARS = 300
RULE_ID = "CRG-22"

_STATIC_REASONS: dict[str, str] = {
    "B1": "pipe-to-shell RCE blocked",
    "B2": "destructive root/home delete blocked",
    "B3": "fork-bomb pattern blocked",
    "B4": "raw disk write/format blocked",
    "B5": "network reverse shell blocked",
    "B6": "restricted file network exfiltration blocked",
    "P1": "restricted system/auth path write blocked",
    "C1": "hardcoded AWS access identifier blocked",
    "C2": "hardcoded GitHub auth material blocked",
    "C3": "hardcoded live service literal blocked",
    "C4": "hardcoded Slack workspace literal blocked",
    "C5": "private key block literal blocked",
}

_SHELL_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "B1",
        re.compile(
            r"(?:curl|wget|fetch)\b[^\n|;]*\|\s*(?:sudo\s+)?"
            r"(?:sh|bash|zsh|ksh|dash|pwsh|powershell|python(?:\d+(?:\.\d+)?)?|node)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "B2",
        re.compile(
            r"(?:^|[;&|]\s*|\s)(?:sudo\s+)?rm\s+"
            r"(?:-[A-Za-z]*r[A-Za-z]*f|-[A-Za-z]*f[A-Za-z]*r"
            r"|--recursive\s+--force|--force\s+--recursive)\s+"
            r"(?:/(?:\*|\s|$)|~/?(?:\s|$)|\$HOME/?(?:\s|$))",
        ),
    ),
    (
        "B3",
        re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;"),
    ),
    (
        "B4",
        re.compile(
            r"\b(?:mkfs(?:\.\w+)?|dd\b[^\n]*\bof=/dev/(?:sd|nvme|vd|hd|disk)\w*)"
        ),
    ),
    (
        "B5",
        re.compile(r"/dev/(?:tcp|udp)/\S+"),
    ),
    (
        "B6",
        re.compile(
            r"(?:(?:curl|wget|nc|ncat|scp|Invoke-WebRequest)\b[^\n]*"
            r"(?:\.env\b|\.ssh/(?:id_|authorized_keys)|\.aws/credentials|\.netrc\b)"
            r"|(?:cat|type|head|tail)\s+[^\n]*"
            r"(?:\.env\b|\.ssh/(?:id_|authorized_keys)|\.aws/credentials|\.netrc\b)"
            r"[^\n]*\|\s*(?:curl|wget|nc|ncat)\b)",
            re.IGNORECASE,
        ),
    ),
)

_RESTRICTED_PATH_RE = re.compile(
    r"(?:^|/)(?:etc/(?:passwd|shadow|sudoers)|\.ssh/(?:authorized_keys|id_rsa|id_ed25519)|\.aws/credentials)$",
    re.IGNORECASE,
)

_CONTENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("C1", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "C2",
        re.compile(
            r"\b(?:(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{20,})\b"
        ),
    ),
    ("C3", re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b")),
    ("C4", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    (
        "C5",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    ),
)


def _format_deny_json(reason: str) -> str:
    prefix = f"{RULE_ID}: "
    full_reason = f"{prefix}{reason}"
    template = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": full_reason,
        }
    }
    serialized = json.dumps(template, separators=(",", ":"), ensure_ascii=True)
    if len(serialized) <= MAX_STDOUT_CHARS:
        return serialized
    overhead = len(serialized) - len(full_reason)
    budget = max(len(prefix), MAX_STDOUT_CHARS - overhead - 3)
    template["hookSpecificOutput"]["permissionDecisionReason"] = (
        full_reason[:budget] + "..."
    )
    return json.dumps(template, separators=(",", ":"), ensure_ascii=True)


def evaluate_tool_use(payload: dict) -> str | None:
    """Return a short deny code if ``payload`` violates CRG-22, else ``None``."""
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    if tool_name == "Bash":
        command = str(tool_input.get("command") or "")
        for code, pattern in _SHELL_RULES:
            if pattern.search(command):
                return code
        return None

    if tool_name in {"Write", "Edit"}:
        raw_path = str(tool_input.get("file_path") or "").replace("\\", "/")
        if raw_path and _RESTRICTED_PATH_RE.search(raw_path):
            return "P1"
        text = str(
            tool_input.get("content")
            if tool_name == "Write"
            else tool_input.get("new_string") or ""
        )
        for code, pattern in _CONTENT_RULES:
            if pattern.search(text):
                return code
        return None

    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
    except Exception:
        return 0

    rule_code = evaluate_tool_use(payload)
    if not rule_code:
        return 0

    message = _STATIC_REASONS.get(rule_code, "security policy violation blocked")
    sys.stdout.write(_format_deny_json(message))
    sys.stderr.write(f"[crg] {RULE_ID}: {message}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
