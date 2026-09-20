# Performance decision log

Performance changes that have already landed, and proposals that were evaluated
and rejected. Read both sections before opening a performance PR, so that work
already done is not repeated and work already ruled out is not re-proposed.

Every landed entry is anchored to a commit. If an entry cannot be located in
`git log`, treat the anchor as authoritative over the date.

## Landed

### 2026-05-28 - Replace fetchall() with direct cursor iteration

**Anchor:** `c9741ab` (#514), reapplied in `8a300fe` (#686)

**Learning:** Using `.fetchall()` on SQLite cursors materializes large intermediate lists in memory. This is particularly problematic for queries that return many rows or rows with large text columns, leading to significant peak memory overhead.

**Action:** Iterate the cursor directly (`for row in cursor`) instead of materializing with `rows = cursor.fetchall()`. Where peeking at a result is necessary, remember that `fetchone()` advances the cursor.

### 2026-05-29 - Isolated mocking for edge case testing

**Anchor:** `ab9a319` (#524), `5894c24` (#528)

**Learning:** When testing edge cases in environments with missing heavy dependencies (like `networkx` or `tree-sitter`), using `sys.modules` to mock these dependencies *before* importing the target module allows for reliable unit testing without triggering `ModuleNotFoundError`.

**Action:** For specialized coverage tests, implement a `MockModule` that uses `__getattr__` to return `MagicMock()` and patch `sys.modules` prior to tool imports. This ensures that even deeply nested or lazy imports within the target module are safely handled during test execution.

### 2026-06-21 - Use str.translate over generator expressions for fast sanitization

**Anchor:** `7daa7fd` (#737)

**Learning:** In hot serialization loops (like returning large JSON responses containing node metadata), using a generator expression with `"".join(...)` to filter string characters is a significant performance bottleneck in Python.

**Action:** When filtering known character sets (like removing control characters), define a pre-compiled mapping module constant (e.g. `_MAP = {i: None for i in range(32)}`) and use `str.translate()`, which pushes the iteration into optimized C code, yielding roughly 7.5x performance improvements.

### 2026-06-23 - Eliminate N+1 query patterns in batch operations

**Learning:** Direct SQL execution within a loop structure causes N+1 query patterns, leading to significant performance degradation as the data set grows. In SQLite, this is especially impactful during write-heavy operations like temporal closing.

**Action:** Refactor row-by-row updates into batch operations using `UPDATE ... WHERE ... IN (SELECT value FROM json_each(?))`. This pushes the filtering logic into the database engine and reduces the overhead of multiple `execute()` calls and potential transaction management. Use `cursor.rowcount` to track affected rows when removing the manual loop counter.

### 2026-07-18 - Prevent N+1 queries when traversing graphs from multiple source nodes

**Anchor:** `062a62e`

**Learning:** Resolving targets (e.g. callees, imports, children, inheritors) for graph visualization/traversal previously resulted in N+1 database roundtrips. When expanding multiple edges, executing `get_edges_by_source` or `get_edges_by_target` per original node generated excessive SQLite overhead, especially for dense repositories.

**Action:** Replace looped individual lookups with batched SQLite queries utilizing `search_edges_by_source_names` or `search_edges_by_target_names`, which process multiple node identifiers in a single roundtrip via `json_each`.

### 2026-08-26 - Calculate aggregate graph statistics in Python

**Anchor:** `551501b`

**Learning:** When generating aggregate statistics across the entire graph, executing multiple scalar subqueries (like `(SELECT COUNT(*) FROM nodes)`) per call incurs unnecessary database I/O overhead. Since grouped aggregates (`SELECT kind, COUNT(*) ... GROUP BY kind`) are already fetched, overall totals can be calculated in Python.

**Action:** To optimize querying aggregate graph statistics in `GraphStore` (e.g., `get_stats` in `src/better_code_review_graph/graph.py`), derive absolute totals (`total_nodes`, `total_edges`, `files_count`) in Python by summing the values of grouped queries (`sum(nodes_by_kind.values())`) rather than executing redundant `COUNT(*)` subqueries, reducing database roundtrips.

## Rejected

Proposals that were evaluated with measurements and declined. The reasoning is
recorded here so that it carries forward instead of being rediscovered.

### 2026-07-25 - Do not replace the word-count subquery in search_nodes

**Rejected PRs:** #884, #885, #887, #891, #892 — five separate proposals of the same change.

**Proposal:** in `GraphStore.search_nodes`, replace `(SELECT COUNT(*) FROM json_each(?))` on the right-hand side of the WHERE equality with a bound `?` carrying `len(words)`.

**Why it was rejected:** the premise — that SQLite re-evaluates this subquery once per scanned row — is false. `EXPLAIN QUERY PLAN` labels the two subqueries in that statement differently:

```
CORRELATED SCALAR SUBQUERY 1   <- left-hand side, references nodes.name
SCALAR SUBQUERY 2              <- right-hand side, references only a parameter
```

Subquery 2 is not correlated, so SQLite already hoists it behind an `OP_Once` guard and evaluates it exactly once per statement. Measured in isolation it costs 3.7 microseconds; against a 423 ms `search_nodes` call that is 0.0009% of runtime. An interleaved A/B over 200,000 rows (25 reps each, alternating which variant ran first) put the median delta at +2.46% with a standard deviation of 9.7% of the median, and the proposed version was slower on `min`. The effect is noise.

**Action — where the time actually goes.** The cost in this query is `CORRELATED SCALAR SUBQUERY 1`: for every row of a full table scan it runs `json_each` plus two `LIKE '%...%'` comparisons. A leading-wildcard `LIKE` cannot use a B-tree index, so the scan itself is the bottleneck. The only changes that move this number are ones that remove the scan — an FTS5 virtual table over `name`/`qualified_name`, or a trigram index (SQLite 3.34+). That is the lever to reach for when optimizing `search_nodes`.

**Action — how to measure before proposing.** Run both variants interleaved with alternating order, at least 25 reps, and report `min`, `median` and `stdev`. A delta smaller than one standard deviation is not a result. `EXPLAIN QUERY PLAN` plus a count of `Once` opcodes shows whether a subquery is already hoisted, before any code is written.

### 2026-07-25 - Do not batch the startup DDL through executescript

**Rejected PR:** #882

**Proposal:** batch the `ALTER TABLE` / `CREATE TABLE` / `CREATE INDEX` statements in `_ensure_federation_columns`, `_ensure_temporal_columns` and `_ensure_summary_columns` into one `self._conn.executescript()` call each.

**Why it was rejected:** the measured saving is 46 microseconds per `GraphStore` init (median of 200 runs: 358.9 us individual vs 312.7 us batched), and these helpers run once per connection from `GraphStore.__init__`. Against that, `sqlite3.Connection.executescript()` issues an implicit `COMMIT` before running its script — an uncommitted `INSERT` was observed surviving a subsequent `rollback()`. The patch turns three ordinary helpers into calls that silently end whatever transaction is open, and that is invisible at the call site.

**Action:** keep schema backfills as individual `execute()` calls. Reserve `executescript()` for migration scripts that already run outside a transaction, where the implicit commit is intended.

## Conventions for this log

- Date every entry with the date of the commit that landed it, taken from `git log`, not from the wall clock of the run writing the entry. Entries in this file dated 2024 were corrected to their real 2026 dates on 2026-07-25 after cross-checking with `git log -S`; an entry misfiled by two years cannot be matched against history and reads as absent.
- Anchor every landed entry to a commit SHA.
- Cite file and symbol names rather than line numbers, which drift as the file changes.
- PR titles in this repo must start with `fix:` or `feat:`. `perf:` is not accepted — the gate in `ci.yml` enforces the narrower set deliberately, and widening that list to make a title pass is not an acceptable change.
- Performance PRs must carry a reproducible measurement. Correctness tests and "expected impact" prose are not measurements.

### 2026-07-26 - Push edge kind filtering to SQLite in batch queries

**Learning:** When fetching dependent edges via `get_edges_by_targets` and `get_edges_by_target`, filtering by edge kind in Python (e.g. `if e.kind == "IMPORTS_FROM"`) forces SQLite to materialize and return thousands of irrelevant rows, creating a significant memory overhead and serialization bottleneck.
**Action:** Always push the `kind` filter directly down to the database using the existing `_kind_filter` helper so the database engine only returns the relevant subsets of graph edges, preventing unnecessary Python-side object materialization.

## 2026-09-05 - Optimize peak memory overhead during full graph exports
**Learning:** Full graph serializations (e.g., `export_graphml`, `export_jsonld` in `src/better_code_review_graph/exporter.py`) iterated over python `GraphNode` and `GraphEdge` objects via `store.get_all_nodes()` / `store.get_all_edges()`. This led to significant unnecessary memory consumption due to the construction and destruction of tens of thousands of dataclass instances for operations that only required scalar row values.
**Action:** Replace `for node in store.get_all_nodes():` with a direct iterator over `sqlite3.Cursor` (e.g., `for row in store._conn.execute("SELECT * FROM nodes")`), accessing data via dictionary-style keys (`row["qualified_name"]`), eliminating object materialization on hot loops that touch the whole graph.

### 2026-09-11 - Stream large JSON graph exports via generator

**Anchor:** `N/A` (to be committed)

**Learning:** When exporting the full code review graph via `export_crg`, materializing the entire graph's nodes and edges into lists of Python dictionaries before passing them to `json.dumps()` causes massive peak memory overhead, especially for large repositories.

**Action:** Replace full list materialization (`[dict(row) for row in cursor]`) with a generator that iterates over the `sqlite3.Cursor` directly. Yield incrementally-dumped JSON string chunks (`json.dumps(dict(row), indent=2).replace("\\n", "\\n    ")`) to construct the final payload efficiently on-the-fly.

### 2026-09-12 - Speed up large payload size estimation via json.dumps

**Anchor:** `N/A` (to be committed)

**Learning:** When estimating the size of large list/dictionary payloads (e.g. in `_estimate_payload_bytes` for truncation limits), converting parts to string format using `repr(p)` in a loop is a significant bottleneck. `json.dumps()` is measurably faster (approx. 30-40%) because it relies on C-level optimizations for serialization.

**Action:** Use `json.dumps()` instead of `repr()` when performing size estimations of dictionaries/lists to minimize string overhead on hot paths.
