---
name: build-graph
description: Build or update the code review knowledge graph. Run this first to initialize, or let hooks keep it updated automatically.
argument-hint: "[full]"
---

# Build Graph

Build or incrementally update the persistent code knowledge graph for this repository.

## Steps

1. **Check graph status** by calling `graph` with `action="stats"`.
   - If the graph has never been built (last_updated is null), proceed with a full build.
   - If the graph exists, proceed with an incremental update.

2. **Build the graph** by calling `graph`:
   - For first-time setup: `graph(action="build", full_rebuild=True)`
   - For updates: `graph(action="update")` (incremental by default)

3. **Verify** by calling `graph(action="stats")` again and report the results:
   - Number of files parsed
   - Number of nodes and edges created
   - Languages detected
   - Any errors encountered

## When to Use

- First time setting up the graph for a repository
- After major refactoring or branch switches
- If the graph seems stale or out of sync
- The graph auto-updates via hooks on edit/commit, so manual builds are rarely needed

## Notes

- The graph is stored as a SQLite database (`.crg/graph.db`) in the repo root
- Binary files, generated files, and patterns in `.code-review-graphignore` are skipped
- Supported languages: Python, TypeScript/TSX/JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++, Solidity, Dart
