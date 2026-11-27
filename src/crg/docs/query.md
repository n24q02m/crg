# query Tool Documentation

Read-only queries against the knowledge graph — pattern queries, search, impact analysis, and code quality checks.

## Actions

### query
Run predefined graph queries to explore code relationships.

**Parameters:**
- `pattern` (required): Query pattern. One of:
  - `callers_of`: Find functions that call the target
  - `callees_of`: Find functions called by the target
  - `imports_of`: Find what the target imports
  - `importers_of`: Find files that import the target
  - `children_of`: Find nodes contained in a file or class
  - `tests_for`: Find tests for the target
  - `inheritors_of`: Find classes inheriting from the target
  - `file_summary`: Get all nodes in a file
- `target` (required): Node name, qualified name, or file path
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)

- `repo`: Federated repo filter (Phase 2). When non-empty, restricts results to nodes whose `repo_id` matches. Default `""` queries every registered repo (legacy behaviour). Useful to disambiguate same-named symbols across federated repos. Discover available `repo_id`s by inspecting the `repos` table in the graph DB after a federated `graph(action="build", roots=[...])`; see `graph.md` "Federation: cross-repo graphs" for the derivation rule.

**Example:**
```json
{"action": "query", "pattern": "callers_of", "target": "authenticate"}
{"action": "query", "pattern": "file_summary", "target": "src/auth.py"}
{"action": "query", "pattern": "tests_for", "target": "UserService"}
{"action": "query", "pattern": "callers_of", "target": "authenticate", "repo": "repo_a-3f2a91bc"}
```

Multi-word search uses AND-logic: `"firebase auth"` matches nodes containing both words.
Common JS/TS builtins (map, filter, forEach, etc.) are filtered from `callers_of` results to reduce noise.

---

### search
Search for code entities by name, keyword, or semantic similarity.

**Parameters:**
- `search_query` (required): Search string
- `kind`: Filter by node type: File, Class, Function, Type, or Test
- `limit`: Maximum results (default: 20)
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)

- `repo`: Federated repo filter (Phase 2). When non-empty, restricts results to nodes whose `repo_id` matches. Default `""` searches across every registered repo. Vector hits are cross-checked against the SQL `repo_id` column so semantic-mode results are filtered consistently with keyword-mode. See `graph.md` "Federation: cross-repo graphs" for `repo_id` discovery.

Uses vector embeddings for semantic search when available (run `graph action=embed` first). Falls back to keyword matching otherwise.

**Example:**
```json
{"action": "search", "search_query": "authentication", "kind": "Function"}
{"action": "search", "search_query": "database connection", "limit": 10}
```

---

### impact
Analyze the blast radius of changed files. Shows which functions, classes, and files are impacted by changes.

**Parameters:**
- `changed_files`: List of changed file paths (auto-detected from git)
- `max_depth`: Hops to traverse in dependency graph (default: 2)
- `max_results`: Maximum impacted nodes to return (default: 500)
- `base`: Git ref for auto-detecting changes (default: HEAD~1)
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)

- `repo`: Federated repo filter (Phase 2). When non-empty, scopes the BFS to nodes whose `repo_id` matches. Default `""` traverses across every federated repo, so cross-repo `IMPORTS_FROM` edges count toward the blast radius. See `graph.md` "Federation: cross-repo graphs" for `repo_id` discovery.

**Example:**
```json
{"action": "impact", "changed_files": ["src/auth.py", "src/models.py"]}
{"action": "impact", "max_depth": 3, "base": "main"}
{"action": "impact", "changed_files": ["src/auth.py"], "repo": "repo_a-3f2a91bc"}
```

---

### large_functions
Find functions, classes, or files exceeding a line-count threshold. Useful for decomposition audits and code quality checks.

**Parameters:**
- `min_lines`: Minimum line count to flag (default: 50)
- `kind`: Filter: Function, Class, File, or Test
- `file_path_pattern`: Filter by file path substring (e.g. "components/")
- `limit`: Maximum results (default: 50)
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)

- `repo`: Federated repo filter (Phase 2). When non-empty, restricts oversized-node results to nodes whose `repo_id` matches. Default `""` returns large nodes across every federated repo. See `graph.md` "Federation: cross-repo graphs" for `repo_id` discovery.

**Example:**
```json
{"action": "large_functions", "min_lines": 100, "kind": "Function"}
{"action": "large_functions", "file_path_pattern": "src/", "limit": 20}
{"action": "large_functions", "min_lines": 100, "repo": "repo_a-3f2a91bc"}
```

---

### communities
Group the indexed graph into communities of tightly linked code with the
Leiden algorithm (Traag, Waltman and van Eck, 2019), optimising modularity.
Useful for finding module boundaries, coupling hot spots, or code that lives in
one directory but belongs with another.

The graph is treated as undirected. Only indexed nodes take part, so calls into
unresolved external symbols are ignored, and two nodes are weighted by the
number of distinct edge kinds (`CALLS`, `IMPORTS_FROM`, `CONTAINS`, ...) that
link them in either direction. Every returned community is connected, and the
same graph and `seed` always give the same communities.

**Parameters:**
- `resolution`: Modularity resolution, `>= 0` (default: 1.0). Higher values
  give more, smaller communities; lower values give fewer, larger ones.
- `seed`: Random seed (default: 0).
- `limit`: Maximum communities listed, largest first (default: 20).
- `as_of`: Optional commit SHA for a historical snapshot.
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)

At most 10 full Leiden passes run, which keeps very large graphs responsive;
`converged` is `false` when that limit stopped a search that was still
improving, and `passes` reports how many ran.

**Example:**
```json
{"action": "communities"}
{"action": "communities", "resolution": 2.0, "seed": 7, "limit": 5}
```

**Returns:**
```json
{
  "status": "ok",
  "algorithm": "leiden",
  "modularity": 0.4123,
  "total_communities": 14,
  "node_count": 812,
  "edge_count": 2410,
  "passes": 6,
  "converged": true,
  "truncated": false,
  "communities": [
    {"id": 0, "size": 96, "members": ["src/auth.py::login", "..."],
     "members_truncated": true, "files": ["src/auth.py", "src/session.py"]}
  ]
}
```

Each community lists up to 20 members, ordered by weighted degree, and the files
they live in, ordered by member count and shown relative to the repository root;
`size` is always the full count.

---

## Temporal queries (Phase 3 v2.0+)

Every `query` / `search` / `impact` action accepts an optional
`as_of: str = ""` cross-cutting param for snapshot semantics. Default
(`""`) returns currently-valid rows only -- the SQL filter is
`WHERE valid_to_sha IS NULL`. The temporal columns are populated by
the v2 ingest path (alembic revision `005_temporal_columns`), which
auto-applies on first `GraphStore` open and seeds `valid_from_sha`
from `git rev-parse HEAD`.

### `as_of`

When set, returns rows that were valid at the given commit SHA. MVP
scope: matches rows where `valid_from_sha == as_of` OR
`valid_to_sha == as_of`. Useful for "show me what `authenticate`
looked like three commits ago" style queries.

**Example:**
```json
{"action": "query", "pattern": "callers_of",
 "target": "src/auth.py::authenticate",
 "as_of": "abc12345"}
```

```json
{"action": "search", "search_query": "authenticate",
 "as_of": "abc12345"}
```

### `diff` action

`query(action="diff", from_sha=X, to_sha=Y)` returns three buckets
identifying nodes that changed between two commit SHAs. The diff is
computed entirely from the temporal columns -- the parser does NOT
re-run.

| Bucket | Meaning |
|---|---|
| `added` | Introduced at `to_sha` (no prior row with same `qualified_name`). |
| `removed` | Closed at `to_sha` with no replacement. |
| `modified` | Superseded at `to_sha` -- one row closed AND a new row opened (function body changed). |

**Parameters:**
- `from_sha` (required): Earlier commit SHA.
- `to_sha` (required): Later commit SHA.
- `repo`: Optional `repo_id` filter.
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection).


**Example:**
```json
{"action": "diff", "from_sha": "abc12345", "to_sha": "def67890"}
```

**Returns:**
```json
{
  "from_sha": "abc12345",
  "to_sha": "def67890",
  "added": [
    {"id": 17, "qualified_name": "src/auth.py::login_v2", "kind": "Function"}
  ],
  "removed": [
    {"id": 4, "qualified_name": "src/auth.py::login_legacy", "kind": "Function"}
  ],
  "modified": [
    {"qualified_name": "src/auth.py::authenticate"}
  ]
}
```

### Recipe -- audit a refactor commit

```json
{"tool": "query", "action": "diff",
 "from_sha": "abc12345", "to_sha": "def67890"}
```

Pair with `review(action="delta", show_line_shifts=true, ...)` (see
`review.md`) when you want callsite-line shifts on top of the
add/remove/modify buckets.
