# review Tool Documentation

Generate focused, token-efficient review context for code changes. Combines impact analysis with source snippets and review guidance.

## Actions

- `context` (default): Auto-detects changed files from git diff and returns the structural summary, impacted nodes, source snippets, and review guidance.
- `delta`: Wraps the `query.diff` buckets (added / removed / modified) and, when `show_line_shifts=true`, surfaces qualified_names whose `line_start` moved between two commits — useful for refactor auditing ("this function moved from line 10 to line 42, did anything break?").

## Parameters

### context action

- `changed_files`: Files to review (auto-detected from git diff if omitted)
- `max_depth`: Impact radius depth (default: 2)
- `include_source`: Include source code snippets (default: true)
- `max_lines_per_file`: Max source lines per file (default: 200)
- `base`: Git ref for change detection (default: HEAD~1)
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection)

- `languages`: Optional list of language names (e.g. `["python"]`) to scope the `untested_functions` list. Excludes functions whose language doesn't match.
- `repo`: Federated repo filter (Phase 2). When non-empty, scopes the impact subgraph and untested-function audit to nodes whose `repo_id` matches. Default `""` includes every federated repo, so cross-repo callers/importers contribute to the review context. Useful when a PR touches one repo in a federated graph but you only want review guidance about that repo. See `graph.md` "Federation: cross-repo graphs" for `repo_id` discovery.
- `include_ownership`: Add the git ownership and health report as `context.ownership` plus its review guidance lines (default: true). Set it to false to skip the git history reads. CLI: `--no-ownership`.

### delta action

- `from_sha`: Earlier commit SHA (required).
- `to_sha`: Later commit SHA (required).
- `show_line_shifts`: When true, include nodes whose `line_start` moved between `from_sha` and `to_sha` in the response (default: false). Each entry is `{qualified_name, before_line, after_line}`.
- `repo`: Federated repo filter (same semantics as context).
- `repo_root`: Repository root path (optional; falls back to the server-configured default root, then to cwd auto-detection).


## Examples

```json
{"changed_files": ["src/auth.py"]}
{"action": "context", "include_source": false, "base": "main"}
{"changed_files": ["src/auth.py"], "repo": "repo_a-3f2a91bc"}
{"action": "delta", "from_sha": "abc123...", "to_sha": "def456...", "show_line_shifts": true}
```

## What It Returns

### context action

1. **Changed files** — auto-detected from git diff
2. **Impacted nodes and files** — blast radius via BFS traversal
3. **Source code snippets** — relevant lines for changed areas (with context)
4. **Review guidance** — automated analysis:
   - Untested changed functions
   - Wide blast radius warnings
   - Inheritance/implementation relationship changes
   - Cross-file impact assessment
   - Suggested reviewers, bus-factor risks, churn hotspots, change coupling and stale code (from the ownership report)
5. **Ownership** (`context.ownership`, unless `include_ownership=false`) -- see below

### Ownership and health

The ownership report reads git history only; nothing is written to the graph.

- `files`: one entry per changed file with `owners` (name, email, `lines`, `line_share`, `commits`, `commit_share`), `bus_factor`, `churn` (`commits`, `added`, `deleted`) and `is_hotspot`. Line shares come from `git blame` of the current file; commit shares come from `git shortlog` of the file.
- `modules`: the same owner and bus-factor data per directory of the changed files.
- `suggested_reviewers`: up to 3 owners of the changed files ranked by line share (weight 0.7) plus commit share (weight 0.3). People who wrote the change (`base..HEAD` authors and the local `git config user.email`, listed in `change_authors`) are never suggested, and authors with no commit in the last 365 days rank after active ones (`active: false`).
- `risks.bus_factor`: files and modules whose bus factor is 1.
- `hotspots`: up to 10 of the most churned files in recent history (at least 2 commits), ranked by commits and then by lines changed.
- `coupling`: files that changed together with a changed file in at least 2 commits and at least 30% of its commits. `in_change: false` marks a partner that is not part of this change, which is the usual sign of a forgotten edit.
- `health.stale`: changed files that had not changed for 365 days before this change, and whether their main owners are still active.
- `health.complex_hotspots`: functions in churn hotspots that are long (50 or more lines) or complex (cyclomatic complexity 10 or more, when the graph records it).
- `health.possibly_unused`: module-level functions in the changed files that nothing in the graph references (calls, imports, route bindings and other edges count; containment and co-change do not). Dunder methods, `main`, `test*` names and decorated functions are left out. This is a signal, not proof: entry points, framework callbacks and dynamic dispatch have no static caller.

**Bus factor** is the smallest number of authors whose blamed lines cover at least 50% of the file (or module). A bus factor of 1 means one person wrote most of the code.

**Authors** are normalised through `.mailmap`, so one person who committed under several names or emails counts once, under the canonical identity.

**Limits** keep the report cheap on large repositories: at most 25 changed files and 10 modules (20 files each) are blamed, files above 512 KB and binary files are skipped (`skipped` says why), history is read from the last 500 non-merge commits, commits touching more than 50 files are ignored for coupling, every git call times out after 10 seconds, and the whole report stops after 15 seconds. `truncated` and `budget_exhausted` say when a limit was hit. Outside a git repository the report is `{"available": false, "reason": ...}`.

### delta action

- `diff`: The full `query.diff` payload (`from_sha`, `to_sha`, `added`, `removed`, `modified`).
- `line_shifts` (only when `show_line_shifts=true`): list of `{qualified_name, before_line, after_line}` for every symbol whose `line_start` moved across the supersede pair at `to_sha`. Same-line supersedes (body changed but `line_start` unchanged) are excluded.

## Usage Tips

- Use `base="main"` when reviewing a full PR (instead of just last commit)
- Set `include_source=false` to reduce token usage when you only need structural info
- Set `include_ownership=false` (CLI `--no-ownership`) when git history is unavailable or not needed
- Combine with `query(action="query", pattern="tests_for", target=<func>)` for deeper test coverage analysis
- Use `action="delta"` with `show_line_shifts=true` to audit pure refactors — when no logic changed but functions moved, the `line_shifts` list pinpoints exactly which callsites a reviewer should re-verify.
