# ADR 0001: Distribution and Binary Executable Names for crg

## Status
Accepted

## Context
Following the stack stabilization plan (Q3, Q13), distribution packages across the n24q02m stack are renamed to use the standard publisher prefix `n24q02m-*` on PyPI to prevent namespace confusion and clarify ownership.

Users invoke crg in multiple contexts:
1. `uvx` ephemeral execution with package name matching binary: `uvx n24q02m-crg`
2. Local shell invocation where a short command is preferred: `crg`
3. Existing automation, scripts, and workflows expecting the historical binary name: `better-code-review-graph`

## Decision
Entry points in `pyproject.toml`, all mapped to `crg.cli:main` (CLI subcommands; bare invocation serves the MCP stdio adapter):
- `n24q02m-crg`: canonical executable matching the PyPI distribution.
- `crg`: short alias for interactive shell use.
- `better-code-review-graph`: backward-compatible alias for existing configurations and scripts.

The Claude Code plugin manifest name is `crg` (matching the `mcpServers` key); the hook that runs the incremental update uses `uvx --python 3.13 --from n24q02m-crg`.

The plugin launches the server with `uvx --python 3.13 n24q02m-crg@latest`. `uvx` reuses the first cached environment of an unversioned spec, so `@latest` is what lets an installed plugin pick up a new release. The hook keeps the unversioned spec because it runs after every Write, Edit and Bash call, and `@latest` adds an index check of roughly 1.5 s to each run. Both pin `--python 3.13`: crg requires Python 3.13, and without the pin `uvx` resolves against the default interpreter and fails on any other version.

## Consequences
- PyPI package name is `n24q02m-crg`.
- Users running `uvx n24q02m-crg` execute without requiring `--from`.
- Historical configurations referencing `better-code-review-graph` remain supported through the command alias.
