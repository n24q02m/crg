# crg

Fork of code-review-graph with fixed multi-word search, qualified call resolution,
dual-mode embedding (ONNX local + cloud chain via `EMBEDDING_MODELS`), and output pagination.
See `AGENTS.md` va `README.md` de hieu architecture va configuration.

## Cau truc

- `src/crg/` -- Package chinh (src layout)
  - `server.py` -- FastMCP server, 6 tools: graph + query + review (3 main) + config + security + help
  - `tools.py` -- MCP tool implementations (build, query, impact, review, search, embed, stats, docs, large functions)
  - `parser.py` -- Tree-sitter parsing (14 langs) + call target resolution
  - `graph.py` -- SQLite GraphStore, search, impact radius, NetworkX cache
  - `incremental.py` -- Git integration, file watching, incremental updates
  - `embeddings.py` -- Dual-mode embedding: local ONNX through the fastretrieval registry + cloud chain (`EMBEDDING_MODELS`) via OpenAI-compatible HTTP clients (`hull_core.providers`)
  - `docs/` -- Help tool documentation (graph.md, query.md, review.md, config.md)
- `cli.py` -- local CLI: no args starts MCP stdio; positional subcommands expose graph/query/review/security over the same domain services

  - `__init__.py` -- Version export
  - `__main__.py` -- `python -m` entry (calls cli.main)
  - `py.typed` -- PEP 561 marker
- `tests/` -- Mirror source modules
- `skills/` -- Claude Code skills (impact-audit, onboard-repo, refactor-check, review-delta, review-pr, security-sweep)
- `hooks/` -- SessionStart + UserPromptSubmit + PostToolUse hooks
- `.claude-plugin/` -- Plugin manifest + marketplace metadata

## Local-first boundary

- CLI and bundled Skills are the primary coding-harness surfaces.
- MCP stdio is a secondary protocol adapter; it must not duplicate graph logic.
- Graph state is local at `<repo>/.code-review-graph/graph.db` unless explicit
  self-host/multi-user configuration changes the data directory.
- CRG has no hosted Cloudflare runtime in the target topology. PyPI, CI,
  security, GitHub releases, and eligible stable MCP Registry publication remain
  active. Historical OCI tags remain available; new public OCI images do not.

## Lenh thuong dung

```bash
uv sync --group dev                # Cai dependencies
uv run pytest                      # Test tat ca
uv run pytest tests/test_graph.py::test_function_name -v  # Test don le
uv run ruff check .                # Lint
uv run ruff format .               # Format
uv run ruff check --fix . && uv run ruff format .  # Fix
uv run ty check                    # Type check (ty lenient config)
uv run crg        # Chay MCP server (stdio, default)
```

## Cau hinh quan trong

- **Python 3.13 bat buoc** -- `requires-python = "==3.13.*"`
- Ruff: line-length 88, target py313, rules E/F/W/I/UP/B/C4, ignore E501
- ty: lenient (unresolved-import, unresolved-attribute, possibly-missing-attribute all "ignore")

## Architecture

```
Source files --> Tree-sitter parser --> SQLite graph (nodes + edges)
                                          |
                                     NetworkX BFS --> Impact radius
                                          |
                                     Embedding store --> Semantic search
                                          |
                                     FastMCP server --> secondary MCP adapter (6 tools: graph + query + review + config + security + help)
```

- **Parser** (parser.py): Tree-sitter extracts nodes (File, Class, Function, Type, Test) and edges (CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON). Resolves same-file bare call targets to qualified names.
- **Graph** (graph.py): SQLite with WAL mode. Multi-word AND-logic search. GraphNode/GraphEdge dataclasses.
- **Incremental** (incremental.py): Git diff detection, file hash tracking, re-parses only changed files.
- **Embeddings** (embeddings.py): Dual-mode -- local ONNX through the fastretrieval registry (default, zero-config) or cloud via the `EMBEDDING_MODELS` chain (OpenAI-compatible HTTP clients; order = fallback, empty = local). Fixed 768-dim storage.
- **Tools** (tools.py): Implementation layer for all graph operations. Output pagination via max_results.
- **Server** (server.py): 6 tools — graph (build/update/stats/embed/export/summarize), query (query/search/impact/large_functions/spot_check/renamed_in_diff/diff), review, config, security, help. Returns structured dict payloads over MCP; the CLI serializes them as JSON.

## Embedding backends

Embedding (cloud backend) + the LLM summarizer dispatch through
OpenAI-compatible HTTP clients (`hull_core.providers.openai_spec`).

- `EMBEDDING_MODELS` -- CSV `provider/model,...` selection for the cloud embedding chain. The first entry is active; later entries are retained config, not runtime fallbacks. Empty = local ONNX from the fastretrieval built-in registry.
- **Local (default)**: fastretrieval ONNX registry -- zero-config, ~570MB download on first use, 768-dim MRL truncation
- Transport + credentials come from the per-task `[models.<task>]` cell in the instance config (`$CRG_CONFIG_DIR` or `~/.crg/config.toml`), fields `base_url` + `api_key` + `model` — plain OpenAI-spec HTTP through hull-core, OpenRouter pre-wired default (`hull config init`). Env overrides: `HULL_EMBED_API_KEY` / `HULL_CHAT_API_KEY` (host-injected).
- Credential rotation: `src/crg/credentials.py` sends every provider call through hull's `CredentialStore` + `KeyPool` (`~/.hull/hull.db`, override `CRG_CREDENTIALS_DB`). A 401/403 disables the key, 429 cools it down for the provider's `Retry-After`/`x-ratelimit-reset`, 5xx retries it once then moves on, and an unusable pool raises `PoolUnavailableError` (redacted, carries `retry_after`). The legacy cell key is migrated once, idempotently; env/config are never modified. `[models.<task>].provider` picks the pool identity, `.account` a named account (default: the provider's unaccounted pool).
- Model-name prefixes (`cohere/…`, `jina_ai/…`, `gemini/…`, `openrouter/…`) only select wire details (e.g. Cohere `input_type`); they never pick keys or transport. There are no per-vendor API-key env vars — ambient `*_API_KEY` vars are not read.
- `DISABLE_LOCAL_EMBED` -- skip the local ONNX download; embedding is `unavailable` unless a cloud chain is configured (`resolve_backend` 3-way: cloud / local / unavailable)
- Fixed 768-dim storage keeps the table schema valid across providers. Switching embedding MODEL changes the vector space; embeddings are tagged per provider (`embeddings.provider` column) and `EmbeddingStore.search` restricts the cosine scan to the active provider, so a provider switch just re-embeds rather than mixing incomparable vectors.
- Deprecated (honored one release with a warning): singular `EMBEDDING_MODEL` + `EMBEDDING_BACKEND` (backend is now inferred from whether the chain is empty). The old "Jina > Gemini > OpenAI > Cohere" auto-detect router is gone.

### BYO local embedding

- `LOCAL_EMBEDDING_MODEL` -- built-in fastretrieval model ID, or a local directory containing `fastretrieval-manifest.json`.
- `LOCAL_EMBEDDING_DIM` -- required positive dimension for an external model ID without a manifest.
- `LOCAL_EMBEDDING_MODEL_FILE` -- ONNX file path inside a manifest-backed artifact, default `onnx/model.onnx`.
- `LOCAL_EMBEDDING_POOLING` -- explicit `CLS`, `MEAN`, `LAST_TOKEN`, or `DISABLED` value for an external ID without a manifest.
- `LOCAL_EMBEDDING_NORMALIZE` -- explicit L2 normalization for an external ID without a manifest, default `true`.

CRG hỗ trợ reranker cục bộ opt-in qua `LOCAL_RERANK_MODEL` (Fastretrieval `TextCrossEncoder` model ID); bỏ trống nghĩa là tắt reranking, khi bật semantic search sẽ rerank pool kết quả và trả về `rerank_score`.
Directory artifact thiếu manifest hoặc model ID ngoài registry thiếu dimension sẽ bị từ
chối, không tự rơi về model mặc định.

### Manual config example

`~/.crg/config.toml`:

```toml
[models.embed]
base_url = "https://openrouter.ai/api/v1"
api_key = "sk-or-..."
model = "jina-ai/jina-embeddings-v5-text-small"

[models.chat]
base_url = "https://openrouter.ai/api/v1"
api_key = "sk-or-..."
model = "minimax/minimax-m3:free"
```

## LLM summarizer (graph `summarize` action)

- `[models.chat]` cell (`base_url` + `api_key` + `model` in `~/.crg/config.toml`, or the `HULL_CHAT_API_KEY` env override) -- an unconfigured cell disables summaries. OpenRouter pre-wired default; the chat model must expose a chat-completion API (embedding-only models do not).
- Dispatches through OpenAI-compatible chat completions (`hull_core.providers.openai_spec`); the cell `base_url` is SSRF-guarded.
- The pre-de-host summary-chain, singular-summary-model, and base-URL env vars are removed — dead strings, no longer read.

## Pytest

- `asyncio_mode = "auto"` -- KHONG can `@pytest.mark.asyncio`
- Default timeout: 30 seconds per test
- `addopts = "--tb=short -q"`
- Coverage: 95%+ enforced

## Release & Deploy

- Conventional Commits. Tag format: `v{version}`
- CD: PSR v10 -> PyPI; eligible stable releases -> MCP Registry
- No new public OCI publication. Historical tags remain; the Dockerfile supports
  source-built self-hosting only.

## Pre-commit hooks

1. Ruff lint (`--fix --target-version=py313`) + format
2. ty type check
3. pytest (`--tb=short -q --timeout=30`)
4. Commit message: enforce Conventional Commits

## Luu y quan trong

- Lazy imports cho heavy deps (tree-sitter, fastretrieval, hull_core cloud clients, numpy) -- tranh startup cost
- MCP tools return structured error payloads (`{"error": ...}`) and close local resources on every path.
- GraphStore.upsert_edge takes EdgeInfo (fields: source, target), GraphEdge uses source_qualified/target_qualified
- `_make_qualified()` builds qualified names as `file_path::name` or `file_path::parent.name`
- Supported languages: Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++, Solidity
