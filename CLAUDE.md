# better-code-review-graph

Fork of code-review-graph with fixed multi-word search, qualified call resolution,
dual-mode embedding (ONNX local + cloud chain via `EMBEDDING_MODELS`), and output pagination.
See `AGENTS.md` va `README.md` de hieu architecture va configuration.

## Cau truc

- `src/better_code_review_graph/` -- Package chinh (src layout)
  - `server.py` -- FastMCP server, 6 tools: graph + query + review (3 main) + config (incl. setup_*) + security + help
  - `tools.py` -- MCP tool implementations (build, query, impact, review, search, embed, stats, docs, large functions)
  - `parser.py` -- Tree-sitter parsing (14 langs) + call target resolution
  - `graph.py` -- SQLite GraphStore, search, impact radius, NetworkX cache
  - `incremental.py` -- Git integration, file watching, incremental updates
  - `embeddings.py` -- Dual-mode embedding: local ONNX through the fastretrieval registry + cloud chain (`EMBEDDING_MODELS`) via OpenAI-compatible HTTP clients (`hull_core.providers`)
  - `docs/` -- Help tool documentation (graph.md, query.md, review.md, config.md, recipes.md, security.md)
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
uv run better-code-review-graph        # Chay MCP server (stdio, default)
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
                                     FastMCP server --> secondary MCP adapter (6 tools: graph + query + review + config + security + help)
```

- **Parser** (parser.py): Tree-sitter extracts nodes (File, Class, Function, Type, Test) and edges (CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON). Resolves same-file bare call targets to qualified names.
- **Graph** (graph.py): SQLite with WAL mode. Multi-word AND-logic search. GraphNode/GraphEdge dataclasses.
- **Incremental** (incremental.py): Git diff detection, file hash tracking, re-parses only changed files.
- **Embeddings** (embeddings.py): Dual-mode -- local ONNX through the fastretrieval registry (default, zero-config) or cloud via the `EMBEDDING_MODELS` chain (OpenAI-compatible HTTP clients; order = fallback, empty = local). Fixed 768-dim storage.
- **Server** (server.py): 6 tools — graph (build/update/stats/embed/export/summarize), query (query/search/impact/large_functions/spot_check/renamed_in_diff/diff), review, config (status/set/cache_clear + setup_status/setup_start/setup_skip/setup_reset/setup_complete), security (scan/report/suppress/rule_list), help. Returns structured dict payloads over MCP; the CLI serializes them as JSON.

## Embedding + LLM backends

Embedding (cloud backend) + the LLM summarizer dispatch through
OpenAI-compatible HTTP clients (`hull_core.providers.openai_spec`).

Per-task model chains, CSV `provider/model,provider/model`, order = fallback. Provider is inferred from the model prefix.

- `EMBEDDING_MODELS` -- chain embedding. Empty = local ONNX from the fastretrieval built-in registry.
- `SUMMARY_MODELS` -- chain summarizer (graph `summarize` action). Empty = summaries disabled.
- **Local (default)**: fastretrieval ONNX registry -- zero-config, ~570MB download on first use, 768-dim MRL truncation
- API key theo convention `<PROVIDER>_API_KEY`. 7 provider servers goi y:

  | model prefix | key env var | get it at |
  |---|---|---|
  | `gemini/` | `GEMINI_API_KEY` | aistudio.google.com/apikey |
  | `openai/` (or bare) | `OPENAI_API_KEY` | platform.openai.com |
  | `jina_ai/` | `JINA_AI_API_KEY` | jina.ai/api-key |
  | `cohere/` | `COHERE_API_KEY` | dashboard.cohere.com |
  | `xai/` | `XAI_API_KEY` | console.x.ai |
  | `anthropic/` | `ANTHROPIC_API_KEY` | console.anthropic.com |
  | `vertex_express/` | `GOOGLE_VERTEX_EXPRESS_API_KEY` | cloud.google.com/vertex-ai/generative-ai/docs/start/express-mode/overview |

  Summarizer providers must expose a chat-completion API (Jina/Cohere do not).
- Custom endpoint (SSRF-guarded): `EMBEDDING_API_BASE` (embedding), `LLM_API_BASE` (summarizer)
- `DISABLE_LOCAL_EMBED` -- skip local ONNX download; `resolve_backend` returns `unavailable` (not local) when no cloud chain is configured
- Fixed 768-dim storage keeps the table schema valid across providers. Switching embedding MODEL changes the vector space; embeddings are tagged per provider and the cosine search restricts to the active provider, so a provider switch re-embeds rather than mixing incomparable vectors.
- Deprecated (honored one release voi warning): singular `EMBEDDING_MODEL`/`SUMMARY_MODEL` + `EMBEDDING_BACKEND` (backend gio suy ra tu chain rong hay khong). Router auto-detect cu "Jina > Gemini > OpenAI > Cohere" da bo.

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

```json
{
  "mcpServers": {
    "crg": {
      "command": "uvx", "args": ["better-code-review-graph"],
      "env": {
        "EMBEDDING_MODELS": "jina_ai/jina-embeddings-v5-text-small,gemini/gemini-embedding-001",
        "SUMMARY_MODELS": "gemini/gemini-2.5-flash",
        "JINA_AI_API_KEY": "jina_xxx",
        "GEMINI_API_KEY": "AIza_xxx"
      }
    }
  }
}
```

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

## Secrets (skret + AWS SSM)

- skret SSM namespace: `/better-code-review-graph/prod` (region `ap-southeast-1`)
- CI: `skret env -e prod --path=/better-code-review-graph/prod --format=dotenv >> $GITHUB_ENV`
- Local dev: `skret run -e prod -- <cmd>` (uses AWS credential chain)

## Luu y quan trong

- Lazy imports cho heavy deps (tree-sitter, fastretrieval, hull_core cloud clients, numpy) -- tranh startup cost
- MCP tools return structured error payloads (`{"error": ...}`) and close local resources on every path.
- GraphStore.upsert_edge takes EdgeInfo (fields: source, target), GraphEdge uses source_qualified/target_qualified
- `_make_qualified()` builds qualified names as `file_path::name` or `file_path::parent.name`
- Supported languages: Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++, Solidity
