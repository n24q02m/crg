# ADR 0001: Distribution and Binary Executable Names for crg

## Status
Accepted

## Context
Following the stack stabilization plan (Q3, Q13), distribution packages across the n24q02m stack are renamed to use the standard publisher prefix `n24q02m-*` on PyPI to prevent namespace confusion, clarify ownership, and align with other tools in the suite (`n24q02m-telegram`, etc.).

Users invoke crg in multiple contexts:
1. `uvx` ephemeral execution with package name matching binary: `uvx n24q02m-crg`
2. Local shell invocation where a short, concise command is preferred: `crg`
3. Existing automation, scripts, and workflows expecting the historical binary name: `better-code-review-graph`

## Decision
We expose entry point aliases in `pyproject.toml`:
- `n24q02m-crg`: Canonical primary executable name matching the PyPI package distribution.
- `crg`: Short ergonomic alias for local interactive shell use.
- `better-code-review-graph`: Backward-compatible alias for existing configurations and scripts.

## Consequences
- PyPI package name is `n24q02m-crg`.
- Users running `uvx n24q02m-crg` execute without requiring `--from`.
- Historical configurations referencing `better-code-review-graph` remain supported.
