# Better Code Review Graph

mcp-name: io.github.n24q02m/better-code-review-graph

**Knowledge graph for token-efficient code reviews -- semantic search and call-graph resolution across your codebase.**

<!-- Badge Row 1: Status -->
[![Mode](https://img.shields.io/badge/mode-daemon_%C2%B7_http_remote_relay-5C6BC0)](https://mcp.n24q02m.com/get-started/modes-overview/)
[![CI](https://github.com/n24q02m/better-code-review-graph/actions/workflows/ci.yml/badge.svg)](https://github.com/n24q02m/better-code-review-graph/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/n24q02m/better-code-review-graph/graph/badge.svg)](https://codecov.io/gh/n24q02m/better-code-review-graph)
[![PyPI](https://img.shields.io/pypi/v/better-code-review-graph?logo=pypi&logoColor=white)](https://pypi.org/project/better-code-review-graph/)
[![License: Apache-2.0](https://img.shields.io/github/license/n24q02m/better-code-review-graph)](LICENSE)

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
| [agent-chat-plugin](https://github.com/n24q02m/agent-chat-plugin) | Peer AI agents chat in a shared folder — no human relay, no orchestrator, wor... | Tooling |
| [better-code-review-graph](https://github.com/n24q02m/better-code-review-graph) | Knowledge graph for token-efficient code reviews -- semantic search and call-... | MCP |
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
<a href="https://glama.ai/mcp/servers/n24q02m/better-code-review-graph">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/n24q02m/better-code-review-graph/badge" alt="better-code-review-graph MCP server" />
</a>

An MCP server that parses your codebase with [Tree-sitter](https://tree-sitter.github.io/tree-sitter/), builds a structural graph of functions/classes/imports, and gives Claude (or any MCP client) precise context so it reads only what matters instead of the whole tree. Semantic search runs through the local ONNX model registry from [fastretrieval](https://github.com/n24q02m/fastretrieval) by default (zero config, no API key), with an optional cloud embedding chain. Fork of [code-review-graph](https://github.com/tirth8205/code-review-graph) with fixed multi-word search, qualified call resolution, dual-mode embeddings, output pagination, and production CI/CD.

## v2.0 migration (BREAKING)

v2.0 adds temporal columns (`valid_from_sha` / `valid_to_sha` on every node + edge) and an opt-in security scanner. The schema migration is auto-applied on first `GraphStore` open, and a backup of the pre-2.0 DB is saved to `<graph_db>.pre-2.0.bak` so you can roll back. See [BREAKING_CHANGES.md](BREAKING_CHANGES.md) for the full schema-change list, behavior changes, environment requirements, and the downgrade procedure (`CRG_DOWNGRADE_TO_1_X=1 uv run better-code-review-graph`).

## Table of contents

- [v2.0 migration (BREAKING)](#v20-migration-breaking)
- [Install](#install)
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
# Run without a persistent install
uvx --python 3.13 better-code-review-graph graph build --full-rebuild \
  --repo-root /path/to/repo
uvx --python 3.13 better-code-review-graph graph stats \
  --repo-root /path/to/repo

# Or install the console script
pip install better-code-review-graph
better-code-review-graph query search --search-query "authentication" \
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
    "better-code-review-graph": {
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
| Claude Code (stdio) | `claude mcp add better-code-review-graph -- uvx --python 3.13 better-code-review-graph` |
| Codex | register stdio command `uvx --python 3.13 better-code-review-graph` under `mcp_servers` in `~/.codex/config.toml` |
| Gemini CLI | add the `mcpServers` JSON above to `~/.gemini/settings.json` |
| Cursor / Windsurf | add the `mcpServers` JSON above via the client's MCP settings (`mcp.json`) |
| Any client (HTTP self-host) | point the client at `https://<your-host>/mcp` (`MCP_TRANSPORT=http`) -- self-host only, no hosted endpoint |

**Install with an AI agent** -- paste this to your AI coding agent:

> Install MCP server `better-code-review-graph` following the steps at
> https://raw.githubusercontent.com/n24q02m/claude-plugins/main/plugins/better-code-review-graph/setup-with-agent.md

Full CLI usage is in [CLI](#cli). Optional per-client MCP setup is at
**[mcp.n24q02m.com/servers/better-code-review-graph/setup/](https://mcp.n24q02m.com/servers/better-code-review-graph/setup/)**.

## Local-first boundary

CRG is local-first for coding workflows:

- **CLI and bundled Skills are the primary surfaces** for graph build/query,
  impact analysis, review context, security scans, and repository onboarding.
- **MCP stdio is the secondary protocol adapter** over the same local domain
  services; it does not maintain a separate graph implementation.
- Graph state stays in `<repo>/.better-code-review-graph/graph.db` unless an explicit
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
    (config) => ({ command: 'uvx', args: ['--python', '3.13', 'better-code-review-graph'] })
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
entries are retained as configuration but are not runtime fallbacks. Summaries
select the first `SUMMARY_MODELS` entry too, without runtime fallback. Providers
are inferred from model prefixes and use the matching `<PROVIDER>_API_KEY`.

| Variable | Purpose | Empty (default) |
|---|---|---|
| `EMBEDDING_MODELS` | Cloud embedding selection; the first entry is active | Local fastretrieval registry |
| `SUMMARY_MODELS` | Completion model selection for `graph(action="summarize")` | Summaries disabled |

Cohere `embed-v4.0` requests and stores **1024 dimensions**; other backends retain
768-dimensional storage. CRG never slices, pads, or silently accepts a different
provider width. The embedding row's model and byte width must match before reuse.
Run `graph(action="embed")` after changing models or upgrading an old 768-wide
Cohere index. Searches reject incompatible widths before a provider call; graph
nodes are retained and re-embedding replaces only stale vectors.

### Provider API keys

Cloud models need the provider key for the selected model prefix. Keys alone
never select models: an empty embedding chain stays local, and an empty summary
chain stays disabled. A configured cloud error does not fall back to local or
another provider. Summarizers require a chat-completion model.

| Model prefix | API key env var | Get a key |
|---|---|---|
| `jina_ai/` | `JINA_AI_API_KEY` | <https://jina.ai/api-key> |
| `gemini/` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | <https://aistudio.google.com/apikey> |
| `openai/` (or bare `text-embedding-*`) | `OPENAI_API_KEY` | <https://platform.openai.com/api-keys> |
| `cohere/` | `COHERE_API_KEY` | <https://dashboard.cohere.com/api-keys> |
| `openrouter/` | `OPENROUTER_API_KEY` | <https://openrouter.ai/settings/keys> |
| `vertex_express/` | `GOOGLE_VERTEX_EXPRESS_API_KEY` | <https://cloud.google.com/vertex-ai/generative-ai/docs/start/express-mode/overview> |

Any other [litellm provider](https://docs.litellm.ai/docs/providers) works via
its standard `<PROVIDER>_API_KEY`.

### Advanced

| Variable | Purpose |
|---|---|
| `EMBEDDING_API_BASE` | Provider-compatible endpoint for cloud embedding, including CF AI Gateway (SSRF-guarded) |
| `LLM_API_BASE` | Provider-compatible base URL for the summarizer, including CF AI Gateway (SSRF-guarded) |
| `DISABLE_LOCAL_EMBED` | Skip the local ONNX download; embedding is unavailable unless a cloud chain is configured |
| `LOCAL_EMBEDDING_MODEL` | Built-in fastretrieval model ID, or a local directory containing `fastretrieval-manifest.json` | Built-in default |
| `LOCAL_RERANK_MODEL` | Fastretrieval `TextCrossEncoder` model ID for bounded semantic reranking | Blank (disabled) |
| `LOCAL_EMBEDDING_DIM` | Required dimension for an external model ID without a manifest | `0` |
| `LOCAL_EMBEDDING_MODEL_FILE` | ONNX file path inside a manifest-backed artifact directory | `onnx/model.onnx` |
| `LOCAL_EMBEDDING_POOLING` | Explicit pooling for an external ID without a manifest: `CLS`, `MEAN`, `LAST_TOKEN`, or `DISABLED` | `MEAN` |
| `LOCAL_EMBEDDING_NORMALIZE` | Explicit L2 normalization for an external ID without a manifest | `true` |
| `CRG_DATA_DIR` | Override the per-user data directory (default `~/.crg`) used for per-user graphs and credentials in HTTP multi-user mode |
| `EMBEDDING_BACKEND` / `EMBEDDING_MODEL` / `SUMMARY_MODEL` | **Deprecated** singular vars, honored one release with a warning -- migrate to the `*_MODELS` chains |

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

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph"],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "EMBEDDING_MODELS": "cohere/embed-v4.0",
        "SUMMARY_MODELS": "openrouter/minimax/minimax-m3:free",
        "EMBEDDING_API_BASE": "https://gateway.ai.cloudflare.com/v1/<account>/<gateway>/cohere/v2/embed",
        "LLM_API_BASE": "https://gateway.ai.cloudflare.com/v1/<account>/<gateway>/openrouter/v1",
        "COHERE_API_KEY": "<cohere-key>",
        "OPENROUTER_API_KEY": "<openrouter-key>"
      }
    }
  }
}
```

Cohere embedding is paid. Authorize a bounded budget before a live index/query;
the Minimax-free completion choice does not make embeddings free. This example
does not add a process-wide model override: in remote mode each authenticated
subject's relay record supplies its models, endpoints and keys. Missing subject
credentials fail closed rather than inheriting the server environment.

CRG currently has **no cloud rerank call**: `LOCAL_RERANK_MODEL` is its only
reranking path. Setting `RERANK_MODELS` or `RERANK_API_BASE` does not enable one.

You can also configure cloud keys interactively in HTTP mode via the relay
setup form (`config(action="setup_start")` returns the browser URL). See the
[modes overview](https://mcp.n24q02m.com/get-started/modes-overview/) and
[multi-user setup](https://mcp.n24q02m.com/get-started/multi-user/).

### Workspace username (HTTP setup form)

The relay setup form has an optional **workspace username** field. Entering the
same username always lands you in the same per-`sub` bucket, so your keys and
graph stay reachable across a re-authorization and across devices, instead of
being tied to the one-off subject minted for each `/authorize` round-trip.
Leaving it blank keeps the previous per-authorize behaviour.

Trust boundary: when the form is gated by a *shared* `MCP_RELAY_PASSWORD`, the
username is a partition key, not a secret -- anyone who knows that password can
type any username and reach that bucket. That is fine for a trusted group; an
untrusted multi-tenant deployment needs a per-user secret or delegated OAuth
instead.

**One-time migration:** existing users must re-enter their credentials once after
this change. Nothing is deleted; credentials stored under the old random subject
are simply no longer addressed.

## Tools

Seven tools, each grouping related actions to keep the tool surface small.

### `graph` -- Graph lifecycle

Actions: `build` | `update` | `stats` | `embed` | `export` | `summarize`

| Action | Description |
|:-------|:------------|
| `build` | Full or incremental graph build. Set `full_rebuild=true` to re-parse all files; pass `roots` to federate extra repo directories into one graph. |
| `update` | Alias for `build` with `full_rebuild=false` (incremental). |
| `stats` | Graph size, languages, node/edge breakdown, embedding count. |
| `embed` | Compute vector embeddings for semantic search. Dual-mode: local ONNX or cloud chain. |
| `export` | Export the graph as `graphml` / `json-ld` / `dot` / `cypher`. Inline or to `output_path`. |
| `summarize` | LLM-generated one-paragraph docstrings for `Function` nodes (via the first explicit `SUMMARY_MODELS` entry; no-op when no model is selected). Calls bounded by `max_nodes`. |

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
| `setup_status` | Show current credential state, providers configured, and setup URL. |
| `setup_start` | Start relay setup to configure API keys via browser (HTTP mode). |
| `setup_skip` | Set local mode (skip relay permanently, use ONNX only). |
| `setup_reset` | Clear credentials and reset state. |
| `setup_complete` | Re-resolve credentials from environment variables. |

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

### `config__open_relay` -- Re-trigger the relay setup form

Registered automatically from [mcp-core](https://github.com/n24q02m/mcp-core).
In HTTP mode it returns `<PUBLIC_URL>/authorize` so the agent can re-open the
browser setup form (e.g. after credential expiry); in stdio mode it returns
`status: 'stdio_unsupported'`.

## CLI

Running `better-code-review-graph` with **no arguments** starts the MCP server
over stdio. A leading positional argument routes to a local CLI subcommand
that calls the same domain services used by the MCP adapter. Run these with
`uvx` (or `uv run` from a source checkout):

```bash
# Start the MCP server over stdio (default -- no subcommand)
uvx better-code-review-graph

# Build, inspect, and embed the local graph
uvx better-code-review-graph graph build
uvx better-code-review-graph graph stats
uvx better-code-review-graph graph embed

# Query relationships and impact
uvx better-code-review-graph query query \
  --pattern callers_of --target "path/to/module.py::function"
uvx better-code-review-graph query search --search-query "authentication"
uvx better-code-review-graph query impact --changed-files src/app.py

# Produce review context and run a local security scan
uvx better-code-review-graph review context --base HEAD~1
uvx better-code-review-graph security scan --engine heuristic
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
| `config status` / `config delete` | Show or remove stored credential config (`--yes` skips confirmation). |
| `doctor` | Environment self-check from shared `mcp-core` CLI. |
| `relay status` / `relay open` / `relay reset` | Inspect, open, or clear the relay setup session. |

CLI subcommands print structured JSON and exit non-zero on an error. The
`config`, `doctor`, and `relay` subcommands come from shared `mcp-core`.


## Features

What this fork fixes versus the upstream [code-review-graph](https://github.com/tirth8205/code-review-graph):

| Feature | code-review-graph | better-code-review-graph |
|:--------|:------------------|:-------------------------|
| Multi-word search | Broken (literal substring) | AND-logic word splitting |
| callers_of/callees_of | Empty results (bare name targets) | Qualified name resolution + bare fallback |
| Embedding | sentence-transformers + torch (1.1 GB) | fastretrieval ONNX + cloud (200 MB), dual-mode |
| Output size | Unbounded (500K+ chars) | Paginated (max_results, truncated flag) |
| Tool design | 9 individual tools | 7 grouped tools: graph + query + review + config + security + help + config__open_relay |
| Plugin hooks | Invalid PostEdit/PostGit | Valid PostToolUse |

## Comparison

How better-code-review-graph stacks up against direct competitors in each pillar:

| Capability | better-code-review-graph | Greptile | Sourcegraph (Cody / MCP) | CodeGraph (colbymchenry) |
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
- **SSRF-guarded endpoints** -- Custom `EMBEDDING_API_BASE` / `LLM_API_BASE` URLs are validated before any outbound call.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Build from source

```bash
git clone https://github.com/n24q02m/better-code-review-graph
cd better-code-review-graph
uv sync --group dev
uv run pytest
uv run better-code-review-graph
```

**Requirements:** Python 3.13, [uv](https://docs.astral.sh/uv/).

## Trust model

This plugin implements **TC-Local** (machine-bound, single trust principal). See the [mcp-core trust model](https://mcp.n24q02m.com/servers/mcp-core/trust-model/) for full classification.

| Mode | Graph DB | Cloud credentials | Who can read your data? |
|---|---|---|---|
| stdio (default) | `<repo>/.better-code-review-graph/graph.db` (git-ignored) | `~/.better-code-review-graph-mcp/config.json` (AES-GCM, machine-bound key) | Only your OS user |
| HTTP self-host (multi-user) | Per-user `~/.crg/subs/<sub>/graph.db` | Per-user `~/.crg/subs/<sub>/config.json` | Only the authenticated user |

## Migration & changelog

Graph, security scan cache, and suppression state now use the package-owned
`.better-code-review-graph/` directory. Run `graph(action="build", full_rebuild=true)`
once after upgrading, followed by `graph(action="embed")` if semantic search is
needed. The ambiguous old `.code-review-graph/` and `.code-review-graph.db` paths
and their SQLite sidecars are left untouched: they may belong to the separate
upstream package. Review and reapply any desired suppression rules explicitly.

The v2.0 release added **temporal columns** (`valid_from_sha` / `valid_to_sha`
on every node and edge) plus an opt-in security scanner. The schema migration
is auto-applied on first `GraphStore` open, and a backup of the pre-2.0 DB is
written to `<graph_db>.pre-2.0.bak`. To downgrade and restore it:

```sh
CRG_DOWNGRADE_TO_1_X=1 uvx better-code-review-graph
```

Full schema-change list, behavior changes, and rollback procedure:
[BREAKING_CHANGES.md](BREAKING_CHANGES.md). Release-by-release history:
[CHANGELOG.md](CHANGELOG.md).

## Documentation

Full docs at
**[mcp.n24q02m.com/servers/better-code-review-graph/setup/](https://mcp.n24q02m.com/servers/better-code-review-graph/setup/)**:

- [Setup](https://mcp.n24q02m.com/servers/better-code-review-graph/setup/) -- install methods for Claude Code, Codex, Gemini CLI, Cursor, Windsurf, mcp.json
- [Modes overview](https://mcp.n24q02m.com/get-started/modes-overview/) -- stdio / local-relay / remote-relay / remote-oauth
- [Multi-user setup](https://mcp.n24q02m.com/get-started/multi-user/) -- per-JWT-sub credential model

Use the `help` tool from any MCP client for inline per-tool reference.

## License

Apache-2.0 -- See [LICENSE](LICENSE).
