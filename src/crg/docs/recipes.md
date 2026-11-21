# Recipes

Stage-mapped operational patterns combining the 5 tools (graph, query,
review, config, help). Reduces derive-from-first-principles overhead for
new agents picking up the toolset for code review and scope-completeness
audits.

## Stage 0 - Prerequisites

### Freshness check
Before any query: verify the graph is current and embeddings exist.

```json
{"tool": "config", "action": "status"}
```

Look for `total_nodes > 0` and `last_updated < 24h`. If `embeddings_count == 0`
and you plan to run `search` on phrases (not literal identifiers), run
`graph action=embed` first or expect a keyword-only warning (#317).

`embeddings_count` is `null` (not `0`) when the embedding store could not be
read at all, with the reason in `header.embeddings_error`. Running
`graph action=embed` will not fix that - check the store itself.

---

## Stage 1 - Build / refresh

### Fresh clone
```json
{"tool": "graph", "action": "build", "full_rebuild": true}
```

### Incremental after fetch / pull
```json
{"tool": "graph", "action": "update"}
```

The response includes a `reviewer_summary` block (#329) with
`functions_added` / `functions_removed` / `functions_modified` /
`modules_newly_impacted`. Feed those names into Stage 5 verification
subagents directly.

---

## Stage 2 - Search and exploration

### Who calls X
```json
{"tool": "query", "action": "query", "pattern": "callers_of", "target": "<file::symbol>"}
```

Spot-check at least one caller's source line before drawing conclusions.
Same-file dynamic dispatch (`asyncio.to_thread`, `functools.partial`,
decorators) is surfaced via `dynamic_dispatch_hints` (#331) so you know
when the AST answer is a lower bound.

### Blast radius
```json
{"tool": "query", "action": "impact", "target": "<file::symbol>", "max_depth": 1}
```

Depth 2 fans to 1000+ on shared hooks/utils. The response is auto-truncated
to `max_payload_bytes` bytes (default 500_000); check `results_truncated`
and `hint` to scope down (#315).

### Duplicate-implementation check
```json
{"tool": "query", "action": "search", "search_query": "<pattern>"}
```

Check the response `header.embeddings_count` first (#330). If zero, use a
literal identifier only - keyword fallback returns garbage on phrases
(#317 emits a warning when it sees a phrase-shaped query). If it is `null`,
the count is unknown rather than zero; see `header.embeddings_error`.

---

## Stage 3 - Scope completeness check

For every function named in scope, run `callers_of` and compare the
caller count against your expectation. For every "X doesn't exist" claim,
run `search X`.

```json
{"tool": "query", "action": "query", "pattern": "callers_of", "target": "<symbol>"}
{"tool": "query", "action": "search", "search_query": "<symbol>"}
```

Note: the response `header.keyword_only` (#330) tells you whether `search`
ran in semantic or keyword mode without a separate `config status` call.

---

## Stage 4 - Pre-merge review

```json
{"tool": "review", "base": "<default-branch>"}
```

Returns: blast radius, untested-function list, wide-blast flags, and
`source_snippets` for the diff in one call. Use `base="main"` for full PRs,
`base="HEAD~1"` for the most recent commit.

---

## Cross-repo federation

Index multiple repos into a single graph and scope queries to one of them
via the `repo='<repo_id>'` filter on `query` / `review`:

```json
{"tool": "graph", "action": "build", "repo_root": "./repo_a", "roots": ["./repo_b"]}
{"tool": "query", "action": "query", "pattern": "callers_of",
 "target": "src/auth.py::authenticate", "repo": "repo_a-3f2a91bc"}
```

`repo_id`s are derived as `<basename>-<sha256[:8]>` of the absolute path,
so they're stable across runs. See `graph.md` section
"Federation: cross-repo graphs" for full recipes (including cross-language
Python + TypeScript federation) and the cross-repo `IMPORTS_FROM`
qualified-name format.

---

## Security scanning

Run a security scan over the graph and re-emit the cached result as
SARIF for CI ingest:

```json
{"tool": "security", "action": "scan"}
{"tool": "security", "action": "report", "format": "sarif"}
```

Tier 1 (heuristic, default) needs no extra deps. Tier 2 (Semgrep's
`p/auto` registry pack + a 3-rule curated overlay) is opt-in: install
the CLI with `uv tool install semgrep` and pass `engine="semgrep"`. Suppress noisy rules persistently with
`security(action="suppress", rule_id=...)`. See `security.md` for the
bundled ruleset, SARIF envelope shape, and the Semgrep install recipe.

---

## Temporal review (v2.0+)

Every `query` / `search` / `impact` accepts `as_of=<sha>` to pin
results to a historical commit (default returns currently-valid
rows). For two-point comparisons:

```json
{"tool": "query", "action": "diff",
 "from_sha": "<earlier-sha>", "to_sha": "<later-sha>"}
```

Returns `{added, removed, modified}` buckets. Pair with
`review(action="delta", show_line_shifts=true, from_sha=..., to_sha=...)`
to also surface symbols whose `line_start` shifted between the two
commits -- useful for refactor auditing. See `query.md` "Temporal
queries" and `review.md` "delta action" for the full parameter
reference.

---

## Tips

- `query.action="callers_of"` auto-resolves the bare-name File+Function
  ambiguity (#316) - you can pass `auth` directly when both `auth.py`
  and `auth()` exist, the Function will be picked.
- `search` and `query` responses always include a `header` block with
  `embeddings_count`, `keyword_only`, and `graph_last_updated` (#330)
  so audit trails do not need a separate `config status` call. A `null` in
  `embeddings_count` or `graph_last_updated` means the read failed, not that
  the value is zero or unset; the companion `embeddings_error` /
  `graph_last_updated_error` key carries the reason.
- A `not_found` response reports `indexed_kinds: null` plus
  `indexed_kinds_error` when the graph could not be queried for its node
  kinds. That is distinct from `indexed_kinds: []`, which means the graph
  really is empty and should be rebuilt.
- Pass `max_payload_bytes=0` to `impact` to opt out of the size cap if
  you can handle the full payload.
