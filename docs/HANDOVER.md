# Better Code Review Graph Handover

## Current operation

- Package: `crg`; local-first code intelligence graph.
- Runtime: Python 3.13, SQLite graph state, Tree-sitter parser, optional local Fastretrieval embeddings, optional cloud embedding and summary adapters through `mcp_core.llm`.
- Primary surfaces: `crg` CLI and MCP stdio adapter. HTTP is opt-in and uses authenticated subject-scoped storage.
- Default graph state: `<repository>/.crg/graph.db`. Existing `.better-code-review-graph` and `.code-review-graph` state is preserved and is never adopted or deleted automatically.
- Cloud model configuration is explicit per task. Empty embedding configuration uses local Fastretrieval; empty summary configuration disables summaries. Cohere `embed-v4.0` uses 1024 dimensions and explicit document/query input types.

## Install and surfaces

```bash
pip install n24q02m-crg                         # CLI + MCP server
pip install 'n24q02m-crg[security]'          # + semgrep (pinned <1.162: upstream mcp pin conflict)

# CLI-first usage without a persistent install (CLI and dist name differ)
uvx --python 3.13 --from n24q02m-crg crg graph build --full-rebuild <path>
uvx --python 3.13 --from n24q02m-crg crg graph stats <path>

# MCP server over stdio (secondary adapter; bare `crg` with no subcommand)
claude mcp add crg -- uvx --python 3.13 n24q02m-crg
```

HTTP is opt-in with token auth: point the client at
`http://127.0.0.1:8772/mcp` with `Authorization: Bearer <token>` (mint the
hash with `hull token hash`, which ships with crg's dependency tree).

## Build, run, and verify

```bash
uv sync --locked --group dev --no-sources
uv run crg
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv build
```

Use an isolated repository fixture for graph builds and protocol checks. Do not point validation at a user's existing graph database unless the scenario explicitly tests migration or preservation.

## Data and safety invariants

- A remote HTTP request without a verified authenticated subject fails closed.
- Subject credentials, model chains, API bases, and graph databases are isolated by subject.
- PHP CALLS post-processing resolves unique same-repository targets and leaves dynamic, ambiguous, inherited, or external calls unresolved with coverage warnings.
- Exporters stream SQLite rows and escape format-specific identifiers and values.
- Cohere requests must not be made without an explicit capped spend authorization and usage receipt.
- There is no sanctioned default cloud model. `EMBEDDING_MODELS`' first entry is the active cloud embedding (later entries are retained configuration, not runtime fallbacks); the summary model comes from the `model` field of the `[models.chat]` cell, and an unconfigured cell disables summaries. Embedding storage width is 1024 for Cohere `embed-v4.0` and Voyage `voyage-4-lite`, and 768 for other backends — never sliced or padded; re-embed after a model change.
- Provider credentials live in hull's key pool (`~/.hull/hull.db`, override
  `CRG_CREDENTIALS_DB`), one ordered pool per provider identity. Every cloud
  call rotates: 401/403 disables a key, 429 cools it down for the provider's
  `Retry-After`/`x-ratelimit-reset`, 5xx retries once then moves on, and an
  unusable pool fails with a redacted error carrying the remaining cooldown.
  A legacy single key (cell `api_key` or `HULL_<TASK>_API_KEY`) is migrated
  into the pool once and left in place; never print or log key material —
  report `KeyPool.health()` rows instead.
- CRG has no cloud rerank call: `LOCAL_RERANK_MODEL` is the only reranking path; setting `RERANK_MODELS` or `RERANK_API_BASE` does not enable one.
- This repository has no dependency on hosted VM infrastructure.

## In-flight and rollback

The current maintenance lane covers PHP call resolution, graph-state collision prevention, embedding dimension validation, request isolation, export correctness, and dependency maintenance. Roll back a source change by reverting the owning commit after checking the graph schema and package version; do not delete either old or new graph state as a rollback shortcut. Rebuild a graph into the new state directory when changing parser or embedding contracts.

## Target architecture and migration map

1. Keep domain logic in `parser.py`, `graph.py`, `incremental.py`, `embeddings.py`, `summarizer.py`, and `tools.py`; adapters remain thin.
2. Keep `server.py` responsible for MCP registration, request context, and structured error payloads only.
3. Preserve the graph schema and migration history. Add migrations for durable schema changes; never silently reinterpret legacy rows.
4. Keep embedding provider and dimension identity attached to stored vectors. Re-embed when provider or width changes; reject malformed or mixed-width data.
5. Keep exports cursor-based and validate representative DOT, JSON-LD, GraphML, Cypher, and CRG payloads with format consumers where available.
6. Extend CLI and MCP behavior from the same tool/domain functions; do not duplicate graph logic in an adapter.

## First weeks

### Week 1

- Reproduce graph build and impact behavior on an isolated PHP fixture.
- Verify new-state creation leaves legacy `.code-review-graph` data unchanged.
- Run repository-native lint, type, package, and full tests.
- Review current dependency and security backlog individually.

### Weeks 2–3

- Verify a BETA artifact by exact workflow run, job conclusions, digest, and install readback.
- Exercise a representative MCP graph build/query/impact round trip against the verified artifact.
- Verify remote subject isolation with two independent subjects and no ambient credential fallback.

### Months 1–3

- Measure large-graph export memory with a reproducible public fixture.
- Maintain provider/dimension compatibility as producer libraries evolve.
- Add domain API/CLI parity only where a real consumer requires it; preserve MCP compatibility during migration.
