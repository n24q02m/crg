# `security` -- code security scanning

The `security` tool surfaces vulnerability findings on `Function` /
`Class` / `Method` nodes via two complementary engines:

- **Tier 1 (heuristic)** -- always available, regex-based, ~5 rules
  covering OWASP top sinks (SQL injection, shell injection, hardcoded
  secrets, dynamic-evaluation, path traversal). Zero extra
  dependencies; bundled rule files live under
  `crg_security_rules/heuristic/*.yaml`.
- **Tier 2 (semgrep)** -- opt-in; wraps the [Semgrep](https://semgrep.dev/)
  CLI, installed separately with `uv tool install semgrep`. By default the scanner runs
  Semgrep's `p/auto` registry pack (auto-selected community rules) plus
  the bundled 3-rule curated overlay (`rules/semgrep/curated.yaml`).

Findings are persisted to `nodes.security_tags` as a JSON array of
`<rule_id>:<severity>` strings so subsequent queries (or the
`review` tool) can filter by tag without re-scanning.

The four actions below operate on the graph DB at
`<repo_root>/.crg/graph.db` (resolved from the
  server-configured default root, else cwd, when
`repo_root` is omitted). Cached scan payloads land at
`.crg/security-last-scan.json` and the
suppression list at `.crg/security-suppressions.json`.

## Actions

### `scan`

Run a security scan over every `Function` / `Class` / `Method` node
in the graph. The result is cached on disk (so `report` can re-emit
it without re-running the engine) and the per-node tags are
persisted into `nodes.security_tags`.

| Param | Type | Default | Notes |
|---|---|---|---|
| `repo_root` | str | None | Auto-detected from the current dir (looks for `.crg/graph.db`). |
| `engine` | str | `"heuristic"` | `"heuristic"` (default, regex tier-1) or `"semgrep"` (tier-2; requires the `semgrep` CLI on `PATH`). |

**Example:**

```json
{"action": "scan"}
{"action": "scan", "engine": "semgrep"}
```

**Returns:**

```json
{
  "engine": "heuristic",
  "total": 3,
  "by_severity": {"HIGH": 2, "MEDIUM": 1},
  "by_rule": {
    "cwe-89-sql-string-format": 1,
    "cwe-78-shell-command-sink": 1,
    "hardcoded-secret": 1
  },
  "tags_by_node": {
    "src/db.py::run_query": [
      {
        "rule_id": "cwe-89-sql-string-format",
        "severity": "HIGH",
        "message": "Possible SQL injection via Python f-string or .format() in execute()",
        "line": 42
      }
    ],
    "src/cli.py::shell_out": [
      {
        "rule_id": "cwe-78-shell-command-sink",
        "severity": "HIGH",
        "message": "Possible shell command injection -- subprocess called with shell=True",
        "line": 17
      }
    ],
    "src/config.py::Settings": [
      {
        "rule_id": "hardcoded-secret",
        "severity": "MEDIUM",
        "message": "Possible hardcoded secret -- high-entropy string assigned to credential-like variable",
        "line": 8
      }
    ]
  },
  "suppressed_count": 0
}
```

When `engine="semgrep"` is requested but the CLI is not installed
the action returns `{"error": "...", "engine": "semgrep"}` instead
of raising -- install the CLI and re-run (see Recipe 3).

The Tier 1 ruleset bundled with v2.0:

| `rule_id` | severity | languages | message |
|---|---|---|---|
| `cwe-89-sql-string-format` | HIGH | python | SQL injection via f-string / `.format()` in `execute()` |
| `cwe-78-shell-command-sink` | HIGH | python | `subprocess.*` invoked with `shell=True` |
| `cwe-22-path-traversal` | HIGH | python | File path concatenated with `request.*` data |
| `cwe-95-eval-on-input` | CRITICAL | python, javascript | Dynamic-evaluation builtin applied directly to user input |
| `hardcoded-secret` | MEDIUM | (any) | High-entropy string assigned to a credential-like variable |

---

### `report`

Re-emit the most recent scan in JSON or SARIF v2.1.0 format. Reads
the cached payload at `.crg/security-last-scan.json`
-- does not re-run the engine.

| Param | Type | Default | Notes |
|---|---|---|---|
| `repo_root` | str | None | Auto-detected. |
| `format` | str | `"json"` | `"json"` returns the cached payload directly; `"sarif"` wraps it in a SARIF v2.1.0 envelope suitable for GitHub code-scanning ingest. |

**Example:**

```json
{"action": "report"}
{"action": "report", "format": "sarif"}
```

If no scan has run yet the action returns
`{"error": "No prior scan found. Run security_scan first."}`.

---

### `suppress`

Add (or remove) a `rule_id` from the persistent suppression list at
`.crg/security-suppressions.json`. Suppressed rules
are silently dropped from subsequent `scan` results -- the rule
itself is NOT removed from the engine, only filtered out at
aggregation time.

| Param | Type | Default | Notes |
|---|---|---|---|
| `rule_id` | str | (required) | Rule identifier, e.g. `"hardcoded-secret"`. |
| `remove` | bool | `false` | When `true`, removes `rule_id` from the suppression list instead of adding it. |
| `repo_root` | str | None | Auto-detected. |

**Example:**

```json
{"action": "suppress", "rule_id": "hardcoded-secret"}
{"action": "suppress", "rule_id": "hardcoded-secret", "remove": true}
```

**Returns:**

```json
{
  "rule_id": "hardcoded-secret",
  "suppressed": true,
  "total_suppressed": 1
}
```

---

### `rule_list`

Enumerate active rules for the given engine.

| Param | Type | Default | Notes |
|---|---|---|---|
| `engine` | str | `"heuristic"` | `"heuristic"` returns full rule metadata; `"semgrep"` returns the names of bundled overlay YAML files. |

**Example:**

```json
{"action": "rule_list"}
{"action": "rule_list", "engine": "semgrep"}
```

**Returns (heuristic):**

```json
{
  "engine": "heuristic",
  "rules": [
    {
      "id": "cwe-89-sql-string-format",
      "severity": "HIGH",
      "languages": ["python"],
      "message": "Possible SQL injection via Python f-string or .format() in execute()"
    }
  ]
}
```

**Returns (semgrep, when no overlay is bundled):**

```json
{"engine": "semgrep", "rules": [], "note": "no curated overlay found"}
```

---

## Recipes

### Recipe 1 -- scan + JSON report

Run a heuristic scan, then re-emit the cached payload as JSON for
downstream tooling (e.g. piping into `jq`):

```json
{"tool": "security", "action": "scan"}
{"tool": "security", "action": "report"}
```

Use the same flow with `format="sarif"` to produce a SARIF v2.1.0
envelope suitable for `github/codeql-action/upload-sarif`:

```json
{"tool": "security", "action": "report", "format": "sarif"}
```

---

### Recipe 2 -- suppress a noisy rule

If `hardcoded-secret` is firing on test fixtures full of fake API
keys, suppress it persistently:

```json
{"tool": "security", "action": "suppress", "rule_id": "hardcoded-secret"}
{"tool": "security", "action": "scan"}
```

The second `scan` returns the same shape as before but with
`hardcoded-secret` entries filtered out and `suppressed_count`
incremented. Lift the suppression later with `remove=true`:

```json
{"tool": "security", "action": "suppress", "rule_id": "hardcoded-secret", "remove": true}
```

---

### Recipe 3 -- install the Semgrep tier

The Tier 2 engine is intentionally opt-in -- Semgrep pulls in a
sizeable runtime, and its releases pin dependencies that conflict
with crg's, so it is not a crg dependency. Install the CLI in its
own environment and keep it on `PATH`:

```sh
uv tool install semgrep
```

Then run `scan` with `engine="semgrep"`:

```json
{"tool": "security", "action": "scan", "engine": "semgrep"}
```

If Semgrep is not installed the action returns
`{"error": "...", "engine": "semgrep"}` -- install the CLI and
re-run, no scan state is mutated on the failure path.

---

## See also

- `query.md` -- the `as_of` / `diff` cross-cutting params land
  scanner findings on the right historical commit when used
  together with `security.scan`.
- `recipes.md` -- "Security scanning" pointer entry.
