# graph Tool Documentation

Graph lifecycle operations — build, update, embed, and check stats.

## Actions

### build
Full or incremental graph build. Parses source files with Tree-sitter, extracts functions/classes/imports, and builds a structural knowledge graph.

Local state lives at `.crg/graph.db`, separate from the
upstream package's `.code-review-graph` directory. On upgrade, run a full build;
old databases and sidecars are never adopted or modified automatically.

Build responses include `php_calls: {total, resolved, unresolved}`. PHP functions,
static/scoped calls, `$this`/`self` calls, namespace and `use` aliases are resolved
to unique current symbols in the same repository after all files are indexed.
Bindings are recalculated after incremental edits. Dynamic receivers, ambiguous
definitions, external libraries, and inherited methods without a direct lexical
target stay unresolved; their counts warn that impact/callers results are partial,
not proof of no callers.

Build responses also include `bare_calls: {total, resolved, unresolved}`. A bare
CALLS target written by the parser (an identifier with no `file::symbol`
qualification, e.g. a callback with no resolvable import) binds after all files
are indexed when exactly one current Function, Test, Class, or Type in the same
repository carries that name, so cross-file impact traversal has edges to walk.
The original bare name and its candidates persist on the edge and are
re-evaluated on every build: deleting the symbol or introducing a same-name
definition unbinds the edge back to its bare form. Ambiguous definitions,
external libraries, and PHP dynamic receivers (owned by the PHP pass above)
stay unresolved.

Build responses also include `http_endpoints: {endpoints, calls, linked,
cross_repo, ambiguous, unmatched, dynamic, external, handlers_bound}` from the
HTTP link pass (see "HTTP endpoints" below). The pass runs after all files are
indexed, on full, incremental, federated and watch builds.

**Parameters:**
- `full_rebuild`: Re-parse all files (default: false, incremental)
- `base`: Git ref for incremental diff (default: HEAD~1)
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)

- `roots`: Optional list of additional repo roots for federated build (Phase 2). When provided, runs a full federated rebuild over `repo_root` plus every entry in `roots`. Each root is registered in the `repos` table with a stable `repo_id` derived from its path. Omit (default `null`) for a single-repo build that preserves the legacy behaviour. See "Federation: cross-repo graphs" below for the full recipe.

**Example:**
```json
{"action": "build", "full_rebuild": true}
{"action": "build", "base": "main"}
{"action": "build", "roots": ["../shared-lib", "../web-app"]}
```

---

### update
Alias for `build` with `full_rebuild=false`. Only re-parses changed files.

**Parameters:**
- `base`: Git ref for diff (default: HEAD~1)
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)


**Example:**
```json
{"action": "update"}
{"action": "update", "base": "origin/main"}
```

---

### stats
Get aggregate statistics about the code knowledge graph. Returns total nodes, edges, languages, files, embedding count, and last update time.

**Parameters:**
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)


**Example:**
```json
{"action": "stats"}
```

---

### embed
Compute vector embeddings for all graph nodes to enable semantic search.

**Parameters:**
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)


Embedding selection:
- **Local (default)**: the configured model or first fastretrieval built-in ONNX registry entry (~570MB download on first use, zero-config)
- **Cloud**: the first `EMBEDDING_MODELS` entry; configured entries after it are not runtime fallbacks
- **Unavailable**: `DISABLE_LOCAL_EMBED=true` with no cloud model configured

Cohere `embed-v4.0` and Voyage `voyage-4-lite` request and store exact 1024-dimensional vectors; other
backends retain 768 dimensions. No response is truncated or padded. Re-run
`graph(action="embed")` after changing models or upgrading a 768-wide Cohere
index; incompatible stored widths block queries until re-embedded. Queries use
Cohere's `search_query` input type, while indexing uses `search_document`.
`config(action="status")` reports the selected backend, model, dimensions, and
`none`/`unavailable` fallback result without loading the model.

**Example:**
```json
{"action": "embed"}
```

---

## Export the graph

Export the full code knowledge graph in an interoperable format. Inline by default; pass `output_path` to write to disk and return only metadata.

**Parameters:**
- `format`: `graphml` | `json-ld` | `dot` | `cypher` | `crg` (default: `graphml`, case-insensitive)
- `output_path`: Optional file path. When provided, payload is written and the response includes only `bytes` + `output_path`. When omitted, payload is returned inline under `payload`.
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)


**Format integration hints:**
- `graphml` -- Imports into Gephi / Cytoscape / NetworkX for visualization and structural analysis.
- `json-ld` -- JSON-aware tooling and linked-data pipelines; preserves node/edge typing.
- `dot` -- Renders directly via Graphviz (`dot -Tsvg graph.dot -o graph.svg`).
- `cypher` -- Replays into Neo4j (`MERGE` statements for nodes + edges); useful for ad-hoc graph queries.
- `crg` -- Portable crg graph; the only format that round-trips back into a store via `import`.

**Example:**
```json
{"action": "export", "format": "graphml"}
{"action": "export", "format": "json-ld", "output_path": "g.jsonld"}
```

MCP call form:
```
graph(action="export", format="graphml")                          # inline
graph(action="export", format="json-ld", output_path="g.jsonld")  # file
```

---

## Import a crg export

Merge a `crg`-format export (from `export` with `format="crg"`) into the current repo's graph. Imported node/edge ids are namespaced by the exporting repo, so they never collide with locally parsed nodes; re-importing the same file is idempotent. Built for artifact portability (build and export on a CI runner, import on a laptop).

**Parameters:**
- `import_path`: Required. JSON file written by `export` with `format="crg"` and an `output_path`; must resolve inside `repo_root`
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)

MCP call form:
```
graph(action="import", import_path="graph.crg.json")
```

---

## Generate LLM summaries

Generate one-paragraph LLM docstrings for `Function` nodes that lack a stored summary or whose source has changed. Stored alongside each node and concatenated into the embedding input -- boosts semantic search recall by roughly 15% by giving the embedder higher-signal text than raw identifiers + signatures alone.

**Parameters:**
- `max_nodes`: Cost cap -- max LLM calls per invocation (default: `500`)
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)


The `[models.chat]` cell of the instance config (`base_url` + `api_key` +
`model`; `HULL_CHAT_API_KEY` env override) selects the completion model —
OpenRouter pre-wired default via `crg config init`. There is no implicit
key-based selection or runtime fallback; model-name prefixes only select
wire details. The cell's key is migrated once into hull's provider credential
pool, and each node is one pooled attempt: a key that answers 401/403 is
disabled for later runs and a 429 key is cooled down for its `Retry-After`,
with the same node retried on the next key. Only a pool that cannot serve
fails — and it fails redacted, never printing key material.

Local-only mode does **not** generate summaries. When no summary model is set,
the action returns `status: "skipped", reason: "no_provider_configured"` and the
graph is unchanged. A provider key alone does not enable summaries.

**Cost cap + caching:**
- Default cap is 500 LLM calls per invocation. Tune with `max_nodes` for tighter budgets.
- Repeat invocations skip nodes whose `source_hash` + full selected model match. `summary_provider` stores the `provider/model` identity, so switching models within one provider invalidates stale summaries too.
- The work queue has a deterministic base order (`ORDER BY id`). When the host configures a `[models.jev_score]` cell, the pending queue is additionally re-prioritized by one advisory jev call per ~50-node batch (never one call per node); the result carries a `jev_ranking` receipt (`used`, `batches`, `ranked_nodes`, `failopen_reason`). Any jev failure is fail-open: the queue keeps its base order and only the receipt notes it.

**Example:**
```json
{"action": "summarize", "max_nodes": 200}
```

MCP call form:
```
graph(action="summarize", max_nodes=200)
```

**When to re-run:** after `graph(action="update")` brings new functions in, or after large refactors where many `source_hash` values change. Edits to existing function bodies invalidate their cached summary automatically -- the next `summarize` call regenerates only the changed nodes.

## Federation: cross-repo graphs (Phase 2 v1.7+)

A single graph DB can index multiple repository roots and resolve imports between them. Pass a `roots` list to `graph(action="build")` and each root is registered in the `repos` registry table with a stable `repo_id`. Subsequent `query` and `review` actions accept a `repo='<repo_id>'` filter to scope results to one federated repo (see `query.md` / `review.md`).

**`repo_id` derivation:** `<basename>-<sha256-prefix-8>` of the absolute, resolved path. Filesystem-root basenames (`/`, `C:\`) normalise to `root-<hash>`. The id is deterministic across machines for the same absolute path -- pass the same `roots` list and you get the same ids. Empty / `.` / `..` basenames also normalise to `root`.

**Single-repo backwards compat:** Omitting `roots` (or passing `roots=[]` / `null`) runs the existing single-root build path. Existing graphs created before Phase 2 keep working; the migration adds a `repo_id` column with a NULL default and a `repos` table without forcing a re-build. Federation is purely opt-in.

**Cross-repo edges:** When the parser resolves an `IMPORTS_FROM` edge whose target lives in a different registered repo, the edge's `target_qualified` is written as `<other_repo_id>:<file>::<symbol>` (note the leading `<repo_id>:` prefix -- single-repo edges keep the legacy `<file>::<symbol>` shape). Per-language resolvers cover Python, TypeScript, Go, Rust, and Java; remaining tier-2 languages fall back to a generic dispatcher that performs basename matching against registered roots.

**`last_indexed_sha`:** `graph(action="update")` records the current git HEAD per repo into `repos.last_indexed_sha` when git is available, so federated incremental updates can later diff per-root against the last indexed commit.

### Recipe 1 -- Federated multi-repo Python build

Two Python repos that import each other; build them into one graph and query a single repo.

```json
{"tool": "graph", "action": "build",
 "repo_root": "./repo_a",
 "roots": ["./repo_b"]}
```

Response (abridged):
```json
{
  "status": "ok",
  "build_type": "full_federated",
  "summary": "Federated build over 2 root(s): parsed 87 files, created 612 nodes and 941 edges.",
  "files_parsed": 87,
  "total_nodes": 612,
  "total_edges": 941,
  "roots": ["/abs/path/repo_a", "/abs/path/repo_b"]
}
```

The derived `repo_id`s for these roots will look like `repo_a-3f2a91bc` / `repo_b-1d4e87aa`. Inspect `repos` in the SQLite DB (or capture them from `RepoRegistry.entries()` if you embed the library) to copy-paste them into a scoped query:

```json
{"tool": "query", "action": "query",
 "pattern": "callers_of",
 "target": "src/auth.py::authenticate",
 "repo": "repo_a-3f2a91bc"}
```

Only callers whose nodes belong to `repo_a` are returned -- callers in `repo_b` are filtered out, even if `repo_b` imports `authenticate`.

### Recipe 2 -- Cross-language federation (Python lib + TypeScript app)

A Python library + a TypeScript app that consumes its compiled artefacts. Each language's per-language resolver runs first; the dispatcher falls back to basename matching for any tier-2 file under either root.

```json
{"tool": "graph", "action": "build",
 "repo_root": "./py-core",
 "roots": ["./ts-app"]}
```

After build, an import in `ts-app/src/api.ts` that resolves to a Python symbol in `py-core/src/core/auth.py::authenticate` materialises an `IMPORTS_FROM` edge whose `target_qualified` reads:

```
py_core-9a8b7c6d:src/core/auth.py::authenticate
```

Use the cross-repo qualified name to walk back across the boundary:

```json
{"tool": "query", "action": "query",
 "pattern": "importers_of",
 "target": "src/core/auth.py::authenticate",
 "repo": "py_core-9a8b7c6d"}
```

Importers in both repos appear, and each result row carries its own `repo_id` so you can tell which side the call lives on. Drop the `repo` filter to see every importer regardless of repo, including the TypeScript ones.

---

## HTTP endpoints

The parser turns HTTP route declarations into `Endpoint` nodes and records HTTP
client calls, then a link pass connects the two with `CALLS_ENDPOINT` edges. In
a federated build the pass runs once after every root is parsed, so a client in
one repo links to a route in another.

**Route declarations** (one `Endpoint` per method and path, named
`"<METHOD> <path>"`, e.g. `GET /users/{id}`; `*` means any method):

- FastAPI: `@app.get(...)` and the other verbs, `@app.api_route(path, methods=[...])`, `APIRouter(prefix=...)`, and `app.include_router(router, prefix=...)`.
- Flask: `@app.route(path, methods=[...])`, `@bp.get(...)`, `Blueprint(url_prefix=...)`, and `app.register_blueprint(bp, url_prefix=...)`.
- Express: `app.get(path, handler)`, `router.post(...)`, `app.all(...)`, `app.route(path).get(h).post(h)`, `express.Router()`, and `app.use(prefix, router)`.
- Go `net/http`: `http.HandleFunc`, `mux.HandleFunc` and `mux.Handle`, including Go 1.22 patterns such as `"GET /users/{id}"` and gorilla-style `.Methods("GET")`.

Each `Endpoint` is contained by its file and has a `ROUTES_TO` edge to its
handler when the handler is a named function. A handler imported from another
file (Express) is bound after indexing (`handlers_bound`). Router mounts are
followed across files, including `include_router(users.router)` with
`from .routers import users` and `app.use("/api", require("./routes/users"))`;
the full paths an endpoint is served under are stored in its
`extra.effective_paths`.

**Client calls** recorded on the calling function (or the file, for module
level code) as `extra.http_calls`: `fetch` and `axios` (including
`axios.create({baseURL})` instances) in JavaScript and TypeScript, `httpx` and
`requests` (including `Client(base_url=...)` and `Session()`) and the FastAPI
`TestClient` in Python, and
`http.Get`, `http.Post`, `http.NewRequest` and `fmt.Sprintf` URLs in Go.

**Matching.** Paths are normalised before comparison: path parameters in any
style (`{id}`, `{id:int}`, `:id`, `<int:id>`, `{path...}`) become one
placeholder, duplicate and trailing slashes are dropped, and the scheme, host,
query string and fragment of a call URL are removed. A runtime base URL in
front of a literal path (`f"{BASE_URL}/users/{uid}"`) is stripped, and a
runtime value that fills a whole path segment matches a route parameter. A call
links when exactly one endpoint has the same method (or `*`) and the best
match, where literal segments beat parameters (`/users/me` prefers the
`/users/me` route over `/users/{id}`). A tie is broken by an endpoint in the
caller's own repo, then by an exact method over `*`.

**No guessing.** A call whose URL or method is only known at runtime
(`httpx.get(url)`, `httpx.get(base + path)`), a call to an external host (a
dotted name such as `api.github.com`; single-label, private and `.internal`
style hosts count as internal), an ambiguous match, and a call with no match
never create an edge; they are only counted in `http_endpoints`.

**Confidence** on a `CALLS_ENDPOINT` edge starts at 1.0, is multiplied by 0.8
when a runtime base URL was stripped, by 0.9 for each runtime path segment, and
by 0.7 when the endpoint sits on a router that no indexed file mounts (its
public prefix is unknown). The edge uses `resolution: "http_route"` and carries
`extra.http_method`, `extra.path` (normalised, with `{}` placeholders),
`extra.endpoint_repo_id` and `extra.cross_repo`.

**Schema.** No migration is needed: `Endpoint` is a new node kind and
`ROUTES_TO` / `CALLS_ENDPOINT` are new edge kinds in the existing tables. The
new `extra` keys are `http_method`, `path`, `raw_path`, `framework`, `router`,
`router_kind`, `handler`, `handler_ref` and `effective_paths` on `Endpoint`
nodes, `http_calls` on functions and files, and `http_routers` and
`http_mounts` (with `replaces_prefix` for Flask blueprints registered under a
new `url_prefix`) on File nodes. Rebuild the graph to populate them. Because
`CALLS_ENDPOINT` points from the caller to the endpoint and `ROUTES_TO` from
the endpoint to the handler, the impact of a change to a route handler reaches
its clients, in other repos too.

---

## Supported Languages

Python, TypeScript/TSX, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++, Solidity, Dart

## Graph Structure

**Node types:** File, Class, Function, Type, Test, Endpoint
**Edge types:** CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON, ROUTES_TO, CALLS_ENDPOINT

`ROUTES_TO` links an HTTP `Endpoint` to its handler function and
`CALLS_ENDPOINT` links an HTTP client call to the `Endpoint` it reaches (see
"HTTP endpoints" above).

`IMPLEMENTS` means the parser found a declared abstract contract: an explicit
interface/trait clause in languages that have one, or an ABC/Protocol contract
in Python. Qualified Python decorators such as `@abc.abstractmethod` count.
It does not claim implicit or structural conformance, such as Python protocol
typing without inheritance or Go method-set satisfaction. C# has no distinct
`implements` syntax, so a class's single external base remains unresolved and
is kept as `INHERITS`; same-file interfaces and struct base lists are proven
implementations. `INHERITS` remains the edge for concrete superclass and other
inheritance relationships.

`TESTED_BY` means **called directly by a test function**, not "adequately
tested". It is emitted for each call site inside a test, so a function the
test merely uses along the way -- a fixture builder, a comparison utility --
also receives one. Functions defined in a test file are excluded, since test
scaffolding is never the subject under test; support code living in an
ordinary module cannot be told apart from a subject by syntax alone and is
not excluded. A call written inside a helper belongs to that helper, so
indirect reach is not credited to the test. Read `tests_for` results and the
untested-function warning in `get_review_context` with that meaning in mind.

That exclusion recognises a test file **by filename**, using the same patterns
that classify a test function. A module whose name merely looks like one --
`test_fixtures.py` holding sample data, or `Testimonial.py` -- is treated as a
test file too, so functions defined in it never receive a `TESTED_BY` edge and
stay in the untested list even when a test calls them. If a function you expect
to be covered keeps appearing there, check the filename first.

Qualified names use `file_path::name` format (e.g. `src/auth.py::authenticate`). Cross-repo edges produced by federation prefix the target with the owning `repo_id`: `<repo_id>:<file_path>::<symbol>` (see "Federation: cross-repo graphs" above).
