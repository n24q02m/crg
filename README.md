# Better Code Review Graph

> **Renamed (2026-09-13):** repo is now `crg` — CLI-first (`crg` command). PyPI package stays `better-code-review-graph`; MCP server is a secondary surface.

mcp-name: io.github.n24q02m/crg

**Knowledge graph for token-efficient code reviews -- semantic search and call-graph resolution across your codebase.**

<!-- Badge Row 1: Status -->
[![Mode](https://img.shields.io/badge/mode-stdio_%C2%B7_http_self_host-5C6BC0)](https://mcp.n24q02m.com/get-started/modes-overview/)
[![CI](https://github.com/n24q02m/crg/actions/workflows/ci.yml/badge.svg)](https://github.com/n24q02m/crg/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/n24q02m/crg/graph/badge.svg)](https://codecov.io/gh/n24q02m/crg)
[![PyPI](https://img.shields.io/pypi/v/n24q02m-crg?logo=pypi&logoColor=white)](https://pypi.org/project/n24q02m-crg/)
[![License: Apache-2.0](https://img.shields.io/github/license/n24q02m/crg)](LICENSE)

<!-- Badge Row 2: Tech -->
[![Python](https://img.shields.io/badge/Python_3.13-3776AB?logo=python&logoColor=white)](#)
[![MCP](https://img.shields.io/badge/MCP-000000?logo=anthropic&logoColor=white)](#)
[![semantic-release](https://img.shields.io/badge/semantic--release-e10079?logo=semantic-release&logoColor=white)](https://github.com/python-semantic-release/python-semantic-release)
[![Renovate](https://img.shields.io/badge/renovate-enabled-1A1F6C?logo=renovatebot&logoColor=white)](https://developer.mend.io/)

<!-- BEGIN: AUTO-GENERATED-CROSS-PROMO -->
<details>
  <summary><strong>Sister projects from n24q02m</strong> (click to expand)</summary>

| Project | Tagline | Tag |
|---|---|---|
| [crg](https://github.com/n24q02m/crg) | Knowledge graph for token-efficient code reviews -- semantic search and call-... | MCP |
| [better-drive](https://github.com/n24q02m/better-drive) | 2-way Google Drive sync with .driveignore filter — rclone engine, Windows tray | Tooling |
| [better-email-mcp](https://github.com/n24q02m/better-email-mcp) | IMAP/SMTP email for AI agents -- read, send, organize folders, and manage att... | MCP |
| [better-godot-mcp](https://github.com/n24q02m/better-godot-mcp) | Composite MCP server for Godot Engine -- 17 composite tools for AI-assisted g... | MCP |
| [better-notion-mcp](https://github.com/n24q02m/better-notion-mcp) | Markdown-first Notion for AI agents -- pages, databases, blocks, and comments... | MCP |
| [better-semantic-release](https://github.com/n24q02m/better-semantic-release) | Drop-in python-semantic-release fork with built-in release-safety guards (orp... | Tooling |
| [better-telegram-mcp](https://github.com/n24q02m/better-telegram-mcp) | Telegram for AI agents -- messages, chats, media, and contacts across both bo... | MCP |
| [better-workspace-mcp](https://github.com/n24q02m/better-workspace-mcp) | Google Workspace MCP server (Docs/Drive/Calendar/Gmail/Sheets/Slides/Tasks/Ch... | MCP |
| [claude-plugins](https://github.com/n24q02m/claude-plugins) | Claude Code plugin marketplace for the n24q02m MCP servers -- install web sea... | Marketplace |
| [imagine-mcp](https://github.com/n24q02m/imagine-mcp) | Image and video understanding + generation for AI agents -- across Gemini, Op... | MCP |
| [jules-task-archiver](https://github.com/n24q02m/jules-task-archiver) | Chrome Extension for bulk operations on Jules tasks via batchexecute API -- a... | Tooling |
| [mcp-core](https://github.com/n24q02m/mcp-core) | Shared foundation for building MCP servers -- Streamable HTTP transport, OAut... | MCP |
| [mnemo-mcp](https://github.com/n24q02m/mnemo-mcp) | Persistent AI memory with hybrid search and embedded sync. Open, free, unlimi... | MCP |
| [fastretrieval](https://github.com/n24q02m/fastretrieval) | Fast multi-model retrieval runtime for ONNX and GGUF embeddings, reranking, and model contracts | Library |
| [skret](https://github.com/n24q02m/skret) | Secrets without the server. | CLI |
| [tacet](https://github.com/n24q02m/tacet) | A self-distilling neuro-symbolic cascade that amortises LLM cost across knowl... | Tooling |
| [web-core](https://github.com/n24q02m/web-core) | Shared web infrastructure package for search, scraping, HTTP security, and st... | Library |
| [wet-mcp](https://github.com/n24q02m/wet-mcp) | Open-source MCP server for AI agents: web search, content extraction, and lib... | MCP |

</details>
<!-- END: AUTO-GENERATED-CROSS-PROMO -->

<!-- Glama badge -->
<a href="https://glama.ai/mcp/servers/n24q02m/crg">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/n24q02m/crg/badge" alt="crg MCP server" />
</a>

An MCP server that parses your codebase with [Tree-sitter](https://tree-sitter.github.io/tree-sitter/), builds a structural graph of functions/classes/imports, and gives Claude (or any MCP client) precise context so it reads only what matters instead of the whole tree. Semantic search runs through the local ONNX model registry from [fastretrieval](https://github.com/n24q02m/fastretrieval) by default (zero config, no API key), with an optional cloud embedding chain. Fork of [code-review-graph](https://github.com/tirth8205/code-review-graph) with fixed multi-word search, qualified call resolution, dual-mode embeddings, output pagination, and production CI/CD.

## v2.0 migration (BREAKING)

v2.0 adds temporal columns (`valid_from_sha` / `valid_to_sha` on every node + edge) and an opt-in security scanner. The schema migration is auto-applied on first `GraphStore` open, and a backup of the pre-2.0 DB is saved to `<graph_db>.pre-2.0.bak` so you can roll back. See [BREAKING_CHANGES.md](BREAKING_CHANGES.md) for the full schema-change list, behavior changes, environment requirements, and the downgrade procedure (`CRG_DOWNGRADE_TO_1_X=1 uv run crg`).

## Table of contents

- [v2.0 migration (BREAKING)](#v20-migration-breaking)
- [Install](#install)
- [Usage](#usage)
- [Smithery](#smithery)
- [Configuration](#configuration)
- [Tools](#tools)
- [CLI](#cli)
- [Features](#features)
- [Comparison](#comparison)
- [Security](#security)
- [Build from source](#build-from-source)
- [Trust model](#trust-model)
- [Migration & changelog](#migration--changelog)
- [Documentation](#documentation)
- [License](#license)

## Install

For OMP and other local coding harnesses, the primary surface is the package CLI
plus the bundled `skills/` workflows. The skills invoke the CLI directly and do
not require an MCP server mapping.

```bash
# Run without a persistent install (short `crg` script; PyPI package name stays
# better-code-review-graph, so `uvx` needs the explicit --from form)
uvx --python 3.13 --from better-code-review-graph crg graph build --full-rebuild \
  --repo-root /path/to/repo
uvx --python 3.13 --from better-code-review-graph crg graph stats \
  --repo-root /path/to/repo

# Or install the console scripts (installs both `crg` and the legacy long name)
pip install better-code-review-graph
crg query search --search-query "authentication" \
  --repo-root /path/to/repo
```

The optional Semgrep engine for deeper security scans is a separate extra:

```bash
pip install 'better-code-review-graph[security]'
```

MCP stdio remains a secondary protocol adapter for clients that require it:

```json
{
  "mcpServers": {
    "crg": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph"],
      "env": { "MCP_TRANSPORT": "stdio" }
    }
  }
}
```

Install matrix (stdio unless noted; the CLI-first usage above stays the primary surface):

| Client | Install |
|---|---|
| Claude Code (plugin) | `/plugin marketplace add n24q02m/claude-plugins` then `/plugin install better-code-review-graph@n24q02m-plugins` |
| Claude Code (stdio) | `claude mcp add crg -- uvx --python 3.13 better-code-review-graph` |
| Codex | register stdio command `uvx --python 3.13 better-code-review-graph` under `mcp_servers` in `~/.codex/config.toml` |
| Gemini CLI | add the `mcpServers` JSON above to `~/.gemini/settings.json` |
| Cursor / Windsurf | add the `mcpServers` JSON above via the client's MCP settings (`mcp.json`) |
| Any client (HTTP self-host) | point the client at `https://<your-host>/mcp` (`MCP_TRANSPORT=http`) -- self-host only, no hosted endpoint |

**Install with an AI agent** -- paste this to your AI coding agent:

> Install MCP server `crg` following the steps at
> https://raw.githubusercontent.com/n24q02m/claude-plugins/main/plugins/better-code-review-graph/setup-with-agent.md

Full CLI usage is in [CLI](#cli). Optional per-client MCP setup is at
**[mcp.n24q02m.com/servers/better-code-review-graph/setup/](https://mcp.n24q02m.com/servers/better-code-review-graph/setup/)**.

## Usage

Two ways to run the server, plus the surfaces to consume it.

### Dev: uv, no auth (loopback only)

```bash
# instance config lives at $CRG_CONFIG_DIR or ~/.crg (same schema as hull's
# config.toml); a default no-auth template is fine for local dev
uv run better-code-review-graph server start
# -> http://127.0.0.1:8000/mcp  (no-auth is refused on any off-loopback bind)
```

### Always-on: docker (token auth)

```bash
cp docker-config/config.example.toml docker-config/config.toml
# mint a token + hash (hull CLI ships with crg's dependency tree):
#   TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
#   hull token hash "$TOKEN"   # paste output into token_hash in config.toml
docker compose up -d
```

The compose file builds the Dockerfile's `http` target (image `crg:http`),
publishes the container on host loopback only
(`127.0.0.1:${CRG_PORT:-8772}:8080`), and mounts
`./docker-config/config.toml` read-only at the container's config dir
(`CRG_CONFIG_DIR=/data/config`); graph state persists in the `crg-data`
named volume. All state stays on your machine.

### Consuming: CLI or MCP

CLI (local graphs, no server needed):

```bash
crg graph build --full-rebuild --repo-root /path/to/repo
crg query search --search-query "authentication" --repo-root /path/to/repo
```

MCP over HTTP (remote/always-on): point any MCP client at
`http://127.0.0.1:8772/mcp` with `Authorization: Bearer <token>`:

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "url": "http://127.0.0.1:8772/mcp",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

### Per-task model configuration

Each task (embed / rerank / chat / jev_score) resolves its own OpenAI-spec
provider cell from `[models.<task>]` in the instance config: an independent
`base_url` + `api_key` + `model`. Cloud or local is purely a config choice —
point `base_url` at OpenRouter, a vendor, or your own local gateway
(e.g. `http://host.docker.internal:11434/v1`). API keys are host-only
material: keep them in `config.toml` (gitignored under `docker-config/`) or
supply via `HULL_<TASK>_API_KEY` env; they are never end-user supplied.

## Local-first boundary

CRG is local-first for coding workflows:

- **CLI and bundled Skills are the primary surfaces** for graph build/query,
  impact analysis, review context, security scans, and repository onboarding.
- **MCP stdio is the secondary protocol adapter** over the same local domain
  services; it does not maintain a separate graph implementation.
- Graph state stays in `<repo>/.crg/graph.db` unless an explicit
  multi-user/self-host configuration selects another data directory.
- PyPI, CI, security scanning, GitHub releases, and eligible stable MCP Registry
  publication remain active. Historical public OCI tags are retained, but new
  public Docker Hub/GHCR images are no longer published.
- CRG has no hosted Cloudflare runtime in the target topology.

## Smithery

The repo ships a [`smithery.yaml`](smithery.yaml) so the server can be built and
run through [Smithery](https://smithery.ai). It deploys over **stdio** and needs
no startup configuration -- the config schema is empty, and any optional cloud
embedding/summary keys are supplied at runtime through the server's own config
flow (see [Configuration](#configuration) below). The launch command is the same
`uvx` invocation as a local install:

```yaml
startCommand:
  type: stdio
  commandFunction: |-
    (config) => ({ command: 'uvx', args: ['--python', '3.13', 'crg'] })
```

## Configuration

Everything works **out of the box with zero configuration** -- semantic search
uses the local ONNX registry from [fastretrieval](https://github.com/n24q02m/fastretrieval)
(`Qwen3-Embedding-0.6B` is the current built-in reference entry, ~570 MB
downloaded on first `graph embed`). This reference entry is not a Qwen-only
boundary: any built-in registry ID or valid non-Qwen artifact manifest follows
the same resolver. All environment variables below are optional and only needed
for cloud embeddings, LLM summaries, or an explicit BYO local artifact.

### Model selection

Embeddings select the first `provider/model` entry in `EMBEDDING_MODELS`; later
entries are retained as configuration but are not runtime fallbacks. The summary
model comes from the `model` field of the `[models.chat]` cell (an unconfigured
cell disables summaries). Transport always comes from the per-task
`[models.<task>]` cell (OpenRouter pre-wired default) — model-name prefixes
only select wire details, never keys.

| Variable | Purpose | Empty (default) |
|---|---|---|
| `EMBEDDING_MODELS` | Cloud embedding selection; the first entry is active | Local fastretrieval registry |
| `[models.chat]` cell `model` | Completion model selection for `graph(action="summarize")` | Summaries disabled |

Cohere `embed-v4.0` requests and stores **1024 dimensions**; other backends retain
768-dimensional storage. CRG never slices, pads, or silently accepts a different
provider width. The embedding row's model and byte width must match before reuse.
Run `graph(action="embed")` after changing models or upgrading an old 768-wide
Cohere index. Searches reject incompatible widths before a provider call; graph
nodes are retained and re-embedding replaces only stale vectors.

### Provider API keys

The key lives in the per-task cell's `api_key` (host-only; see the table below).
Keys alone never select models: an empty embedding chain stays local, and an empty summary
chain stays disabled. A configured cloud error does not fall back to local or
another provider. Summarizers require a chat-completion model.

| Task | Config cell | Notes |
|---|---|---|
| Embedding | `[models.embed]` in the instance config (`base_url` + `api_key` + `model`), or `HULL_EMBED_API_KEY` env | Plain OpenAI-spec HTTP through hull-core; OpenRouter pre-wired default. `EMBEDDING_MODELS` picks the model name(s) — keys never select a model. Model prefixes (`cohere/…`, `jina_ai/…`, `gemini/…`) select wire details only (e.g. Cohere `input_type`); there are no per-vendor API keys. Cohere embed-4.0 direct is the documented opt-in exception (spec 2026-09-26 §9). |
| Summarizer | `[models.chat]` cell (or `HULL_CHAT_API_KEY`) | Requires a chat-completion model; OpenRouter default. |

Vendor-specific key env vars (`JINA_AI_API_KEY`, `GEMINI_API_KEY`,
`OPENAI_API_KEY`, `GOOGLE_VERTEX_EXPRESS_API_KEY`, …) are **not read** by
crg; the removed per-vendor dispatch lived in the pre-de-host stack.

### Advanced

| Variable | Purpose |
|---|---|
| `EMBEDDING_MODELS` | Comma-separated embedding model chain; the first entry is the cloud model (host-owned; keys never select a model). Legacy `EMBEDDING_MODEL` is honored with a deprecation warning until the next release. |
| `DISABLE_LOCAL_EMBED` | Skip the local ONNX download; embedding is unavailable unless a cloud chain is configured |
| `LOCAL_RERANK_MODEL` | Fastretrieval `TextCrossEncoder` model ID for bounded semantic reranking | Blank (disabled) |
| `LOCAL_EMBEDDING_DIM` | Required dimension for an external model ID without a manifest | `0` |
| `LOCAL_EMBEDDING_MODEL_FILE` | ONNX file path inside a manifest-backed artifact directory | `onnx/model.onnx` |
| `LOCAL_EMBEDDING_POOLING` | Explicit pooling for an external ID without a manifest: `CLS`, `MEAN`, `LAST_TOKEN`, or `DISABLED` | `MEAN` |
| `LOCAL_EMBEDDING_NORMALIZE` | Explicit L2 normalization for an external ID without a manifest | `true` |
| `CRG_DATA_DIR` | Override the per-user data directory (default `~/.crg`) used for per-user graphs and credentials in HTTP multi-user mode |
| `EMBEDDING_BACKEND` / `EMBEDDING_MODEL` | **Deprecated** singular vars, honored one release with a warning -- migrate to `EMBEDDING_MODELS`. The pre-de-host summary-model and base-URL env vars are no longer read; model + transport live in the `[models.*]` cells |

When `LOCAL_RERANK_MODEL` is configured, semantic vector search retrieves a
bounded candidate pool of `min(max(limit * 4, limit), 100)` rows, applies the
existing `kind`, `repo`, and live-row filters, then reranks that pool and returns
at most `limit` rows. The response uses `search_mode="semantic_reranked"` and
adds `rerank_score` while preserving `similarity_score`. Blank keeps the
existing `limit * 2` vector path and `search_mode="semantic"`. Configured
reranker failures return an explicit error; CRG does not silently fall back to
vector or keyword results. Keyword searches, including `as_of` snapshots, do
not invoke the reranker.

### Example -- cloud embeddings + summaries

`~/.crg/config.toml` (write by hand, or start from `hull config init` which
pre-wires OpenRouter defaults):

```toml
[models.embed]
base_url = "https://openrouter.ai/api/v1"
api_key = "sk-or-..."
model = "cohere/embed-v4.0"

[models.chat]
base_url = "https://openrouter.ai/api/v1"
api_key = "sk-or-..."
model = "minimax/minimax-m3:free"
```

Equivalent env surface for the MCP server entry (keys override the cells;
model names still come from `EMBEDDING_MODELS` / the `model` field):

```json
{
  "mcpServers": {
    "crg": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph"],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "EMBEDDING_MODELS": "cohere/embed-v4.0",
        "HULL_EMBED_API_KEY": "sk-or-...",
        "HULL_CHAT_API_KEY": "sk-or-..."
      }
    }
  }
}
```

Cohere embedding is paid. Authorize a bounded budget before a live index/query;
the Minimax-free completion choice does not make embeddings free. Model-name
prefixes (`cohere/…`, `openrouter/…`) select wire details only — transport and
credentials come from the `[models.*]` cells, which the host owns.

CRG currently has **no cloud rerank call**: `LOCAL_RERANK_MODEL` is its only
reranking path. Setting `RERANK_MODELS` or `RERANK_API_BASE` does not enable one.

## Tools

Six tools, each grouping related actions to keep the tool surface small.

### `graph` -- Graph lifecycle

Actions: `build` | `update` | `stats` | `embed` | `export` | `summarize`

| Action | Description |
|:-------|:------------|
| `build` | Full or incremental graph build. Set `full_rebuild=true` to re-parse all files; pass `roots` to federate extra repo directories into one graph. |
| `update` | Alias for `build` with `full_rebuild=false` (incremental). |
| `stats` | Graph size, languages, node/edge breakdown, embedding count. |
| `embed` | Compute vector embeddings for semantic search. Dual-mode: local ONNX or cloud chain. |
| `export` | Export the graph as `graphml` / `json-ld` / `dot` / `cypher`. Inline or to `output_path`. |
| `summarize` | LLM-generated one-paragraph docstrings for `Function` nodes (via the `[models.chat]` cell; no-op when no model is configured). Calls bounded by `max_nodes`. |

### `query` -- Graph queries

Actions: `query` | `search` | `impact` | `large_functions` | `spot_check` | `renamed_in_diff` | `diff`

| Action | Description |
|:-------|:------------|
| `query` | Predefined patterns: `callers_of`, `callees_of`, `imports_of`, `importers_of`, `children_of`, `tests_for`, `inheritors_of`, `file_summary`. |
| `search` | Search code entities by name/keyword or semantic similarity. |
| `impact` | Blast radius of changed files. Auto-detects from git diff. Paginated with `max_results`. |
| `large_functions` | Find functions/classes exceeding a line-count threshold. |
| `spot_check` | Random callsite snippets from the last `callers_of`/`callees_of`/`inheritors_of`/`importers_of` result. |
| `renamed_in_diff` | Symbols whose callsite line shifted versus a base ref. |
| `diff` | Nodes added/removed/modified between two commit SHAs (`from_sha`, `to_sha`). |

Most read actions accept `as_of=<sha>` for temporal (point-in-time) snapshots
and `repo=<repo_id>` to scope a federated multi-repo graph.

### `review` -- Code review context

Actions: `context` (default) | `delta`

Token-optimized review context with structural summary, impacted nodes, source
snippets, and review guidance. `context` auto-detects changed files from the
git diff; `delta` (with `from_sha`/`to_sha`, optional `show_line_shifts`)
surfaces refactor moves between two commits.

### `config` -- Server configuration and credential setup

Actions: `status` | `set` | `cache_clear` | `setup_status` | `setup_start` | `setup_skip` | `setup_reset` | `setup_complete`

| Action | Description |
|:-------|:------------|
| `status` | Server info: version, graph path, node/edge counts, embedding backend, embeddings count. |
| `set` | Update a runtime setting (`key=log_level`). |
| `cache_clear` | Remove all computed embeddings. |
| `setup_status` | Show current credential state and which model cells have keys. |
| `setup_start` | Explain where the host configures API keys (host-owned model cells). |
| `setup_skip` | Set local mode (local ONNX embedding, no cloud cells). |
| `setup_reset` | Reset state to local; host config re-resolves on next call. |
| `setup_complete` | Re-resolve credential state from host config. |

### `security` -- Security scanning

Actions: `scan` | `report` | `suppress` | `rule_list`

| Action | Description |
|:-------|:------------|
| `scan` | Run a security scan (`engine='heuristic'` default = 5 regex rules, or `'semgrep'`). Findings persist on `nodes.security_tags`. |
| `report` | Re-emit cached findings as JSON (`format='json'`) or SARIF v2.1.0 (`format='sarif'`). |
| `suppress` | Suppress a finding by `rule_id` (or `remove=true` to un-suppress). |
| `rule_list` | List available rules for an engine. |

The `semgrep` engine requires the `[security]` extra and runs Semgrep's
`p/auto` registry pack plus a 3-rule curated overlay.

### `help` -- Full documentation

Topics: `graph` | `query` | `review` | `config` | `security` | `recipes`

Returns complete documentation for each tool. Use when the compressed
descriptions above are insufficient.

## CLI

The package installs two console scripts: **`crg`** (primary) and
`crg` (legacy long name). Running either with **no
arguments** starts the MCP server over stdio; a leading positional argument
routes to a local CLI subcommand that calls the same domain services used by
the MCP adapter. Run them directly after `pip install`, or without a
persistent install via `uvx --python 3.13 --from better-code-review-graph crg ...`.

```bash
# Start the MCP server over stdio (default -- no subcommand)
crg

# Build, inspect, and embed the local graph
crg graph build
crg graph stats
crg graph embed

# Query relationships and impact
crg query query \
  --pattern callers_of --target "path/to/module.py::function"
crg query search --search-query "authentication"
crg query impact --changed-files src/app.py

# Produce review context and run a local security scan
crg review context --base HEAD~1
crg security scan --engine heuristic
```

| Command | Description |
|:--------|:------------|
| `graph build` | Full or incremental graph build. `--full-rebuild` re-parses every file; `--base <ref>` sets the incremental diff ref; `--repo-root <path>` overrides auto-detection. |
| `graph embed` | Compute vector embeddings using local ONNX or the configured cloud chain. |
| `graph stats` / `graph export` / `graph import` / `graph summarize` | Inspect, export/import a portable `crg` graph, or summarize functions. |
| `query query` / `query search` | Run relationship patterns or keyword/semantic search. |
| `query impact` / `query large_functions` | Analyze changed-file blast radius or find oversized nodes. |
| `query spot_check` / `query renamed_in_diff` / `query diff` | Inspect callsites, line shifts, or commit-to-commit graph changes. |
| `review context` / `review delta` | Generate review context or diff buckets for a code change. |
| `security scan` / `security report` / `security suppress` / `security rule_list` | Run and manage heuristic/Semgrep security findings. |

CLI subcommands print structured JSON and exit non-zero on an error.


## Features

What this fork fixes versus the upstream [code-review-graph](https://github.com/tirth8205/code-review-graph):

| Feature | code-review-graph | crg |
|:--------|:------------------|:-------------------------|
| Multi-word search | Broken (literal substring) | AND-logic word splitting |
| callers_of/callees_of | Empty results (bare name targets) | Qualified name resolution + bare fallback |
| Embedding | sentence-transformers + torch (1.1 GB) | fastretrieval ONNX + cloud (200 MB), dual-mode |
| Output size | Unbounded (500K+ chars) | Paginated (max_results, truncated flag) |
| Tool design | 9 individual tools | 6 grouped tools: graph + query + review + config + security + help |
| Plugin hooks | Invalid PostEdit/PostGit | Valid PostToolUse |

## Comparison

How crg stacks up against direct competitors in each pillar:

| Capability | crg | Greptile | Sourcegraph (Cody / MCP) | CodeGraph (colbymchenry) |
|---|---|---|---|---|
| Codebase knowledge graph | Yes (Tree-sitter, 14 langs, SQLite) | Yes (functions/classes/deps) | Yes (precise code indexing) | Yes (Tree-sitter, 20+ langs, SQLite) |
| Persistent incremental updates | Yes (git-diff + file-hash re-parse) | ? | Yes (continuous indexing) | Yes (OS file-watcher debounced) |
| Qualified call resolution (callers/callees) | Yes (same-file bare-call resolution + fallback) | ? | Yes (go-to-def / find-references) | Yes (callers / callees / impact) |
| Semantic search / embeddings | Yes (fastretrieval local registry + cloud Jina/Gemini/OpenAI/Cohere) | ? | Yes (semantic + keyword + regex) | No (FTS5 full-text only) |
| Token-optimized review context | Yes (`review` tool, git-diff scoped) | Yes (PR review comments) | No (code-context assistant) | No (context layer, not review) |
| Security scanning | Yes (Semgrep `p/auto` + 3-rule overlay, SARIF) | ? | ? | No |
| Self-hostable | Yes (stdio default, machine-bound) | Yes (Docker / K8s / air-gapped) | Yes (self-hosted instance) | Yes (100% local, no API keys) |
| Free / open source | Yes (Apache-2.0) | No (proprietary SaaS; free OSS tier) | No (Enterprise license, source private) | Yes (MIT) |

Sources: [Greptile](https://www.greptile.com/docs/introduction) · [Greptile pricing](https://www.greptile.com/pricing) · [Sourcegraph MCP](https://sourcegraph.com/mcp) · [CodeGraph](https://github.com/colbymchenry/codegraph). Cells marked `?` are capabilities the competitor does not publicly document, not confirmed absences.

## Security

- **Explicit selection** -- Cloud embedding errors are reported; the runtime does not silently switch models or fall back to local ONNX.
- **Error handling** -- Tools return error strings with fix suggestions, never crash.
- **Read-only mount** -- Docker mode mounts the repo as `:ro` (read-only).
- **SSRF-guarded endpoints** -- Custom `[models.*]` cell `base_url` values are validated before any outbound call.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Build from source

```bash
git clone https://github.com/n24q02m/crg
cd crg
uv sync --group dev
uv run pytest
uv run crg
```

**Requirements:** Python 3.13, [uv](https://docs.astral.sh/uv/).

## Trust model

This plugin implements **TC-Local** (machine-bound, single trust principal). See the [mcp-core trust model](https://mcp.n24q02m.com/servers/mcp-core/trust-model/) for full classification.

| Mode | Graph DB | Cloud credentials | Who can read your data? |
|---|---|---|---|
| stdio (default) | `<repo>/.crg/graph.db` (git-ignored) | `~/.crg/config.toml` (AES-GCM, machine-bound key) | Only your OS user |
| HTTP self-host (multi-user) | Per-user `~/.crg/subs/<sub>/graph.db` | Per-user `~/.crg/subs/<sub>/config.json` | Only the authenticated user |

## Migration & changelog

Graph, security scan cache, and suppression state now use the package-owned
`.crg/` directory. Run `graph(action="build", full_rebuild=true)`
once after upgrading, followed by `graph(action="embed")` if semantic search is
needed. The old `.better-code-review-graph/` state directory plus the ambiguous
`.code-review-graph/` and `.code-review-graph.db` paths and their SQLite
sidecars are left untouched, not migrated. Review and reapply any desired
suppression rules explicitly.

The v2.0 release added **temporal columns** (`valid_from_sha` / `valid_to_sha`
on every node and edge) plus an opt-in security scanner. The schema migration
is auto-applied on first `GraphStore` open, and a backup of the pre-2.0 DB is
written to `<graph_db>.pre-2.0.bak`. To downgrade and restore it:

```sh
CRG_DOWNGRADE_TO_1_X=1 uvx n24q02m-crg
```

Full schema-change list, behavior changes, and rollback procedure:
[BREAKING_CHANGES.md](BREAKING_CHANGES.md). Release-by-release history:
[CHANGELOG.md](CHANGELOG.md).

## Documentation

Full docs at
**[mcp.n24q02m.com/servers/better-code-review-graph/setup/](https://mcp.n24q02m.com/servers/better-code-review-graph/setup/)**:

- [Setup](https://mcp.n24q02m.com/servers/better-code-review-graph/setup/) -- install methods for Claude Code, Codex, Gemini CLI, Cursor, Windsurf, mcp.json
- [Modes overview](https://mcp.n24q02m.com/get-started/modes-overview/) -- stdio / http
- [Multi-user setup](https://mcp.n24q02m.com/get-started/multi-user/) -- per-JWT-sub credential model

Use the `help` tool from any MCP client for inline per-tool reference.

## License

Apache-2.0 -- See [LICENSE](LICENSE).
