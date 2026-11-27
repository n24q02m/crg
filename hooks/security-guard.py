#!/usr/bin/env python3
"""CRG-22 PreToolUse security guard hook (stdlib-only, <300ms, <=300B stdout).

Inspects Claude Code ``PreToolUse`` payloads for ``Bash``, ``Write``, and
``Edit`` tool invocations and blocks high-confidence security hazards:

* Remote code execution pipelines (``curl ... | bash``, ``wget ... | sh``)
* Destructive filesystem wipes, raw disk writes, fork bombs, reverse shells
* Secret-file exfiltration over network utilities
* Writing hardcoded credentials/private keys or sensitive system/auth paths

Fails open (exit 0, silent stdout) on unreadable input or unrelated tools so
developer workflows never stall on malformed hook payloads.
"""

from __future__ import annotations

import json
import re
import sys

MAX_STDOUT_CHARS = 300
RULE_ID = "CRG-22"

_BASH_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "pipe-to-shell RCE blocked",
        re.compile(
            r"(?:curl|wget|fetch)\b[^\n|;]*\|\s*(?:sudo\s+)?"
            r"(?:sh|bash|zsh|ksh|dash|pwsh|powershell|python(?:\d+(?:\.\d+)?)?|node)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "destructive root/home delete blocked",
        re.compile(
            r"(?:^|[;&|]\s*|\s)(?:sudo\s+)?rm\s+"
            r"(?:-[A-Za-z]*r[A-Za-z]*f|-[A-Za-z]*f[A-Za-z]*r"
            r"|--recursive\s+--force|--force\s+--recursive)\s+"
            r"(?:/(?:\*|\s|$)|~/?(?:\s|$)|\$HOME/?(?:\s|$))",
        ),
    ),
    (
        "fork-bomb pattern blocked",
        re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;"),
    ),
    (
        "raw disk write/format blocked",
        re.compile(
            r"\b(?:mkfs(?:\.\w+)?|dd\b[^\n]*\bof=/dev/(?:sd|nvme|vd|hd|disk)\w*)"
        ),
    ),
    (
        "network reverse shell blocked",
        re.compile(r"/dev/(?:tcp|udp)/\S+"),
    ),
    (
        "credential exfiltration over network blocked",
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

_SENSITIVE_PATH_RE = re.compile(
    r"(?:^|/)(?:etc/(?:passwd|shadow|sudoers)|\.ssh/(?:authorized_keys|id_rsa|id_ed25519)|\.aws/credentials)$",
    re.IGNORECASE,
)

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("AWS access key literal blocked", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "GitHub token literal blocked",
        re.compile(
            r"\b(?:(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{20,})\b"
        ),
    ),
    ("live API secret literal blocked", re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b")),
    ("Slack token literal blocked", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    (
        "private key material blocked",
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
    """Return a short deny reason if ``payload`` violates CRG-22, else ``None``."""
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    if tool_name == "Bash":
        command = str(tool_input.get("command") or "")
        for label, pattern in _BASH_RULES:
            if pattern.search(command):
                return label
        return None

    if tool_name in {"Write", "Edit"}:
        raw_path = str(tool_input.get("file_path") or "").replace("\\", "/")
        if raw_path and _SENSITIVE_PATH_RE.search(raw_path):
            return "sensitive system/credential path write blocked"
        text = str(
            tool_input.get("content")
            if tool_name == "Write"
            else tool_input.get("new_string") or ""
        )
        for label, pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                return label
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

    reason = evaluate_tool_use(payload)
    if not reason:
        return 0

    sys.stdout.write(_format_deny_json(reason))
    sys.stderr.write(f"[crg] {RULE_ID}: {reason}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
