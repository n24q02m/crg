---
name: security-sweep
description: Graph-driven security sweep -- scan for dangerous sinks, then rank each finding by whether an entry point can actually reach it, and triage the rest into suppressions.
argument-hint: "[path, rule id, or severity floor]"
---

# Security Sweep

Scan the codebase for dangerous constructs, then use the graph to answer the question a flat scanner cannot: **can untrusted input actually reach this?** A medium-severity finding in a request handler outranks a critical one in dead code, and only the call graph can tell them apart.

**Command surface:** run the local CLI through the coding harness shell. Examples
use the installed `crg` command; from a source checkout,
prefix it with `uv run`. No MCP mapping is required.

## Steps

1. **Make the graph current** with `crg graph build --base HEAD --repo-root "<path>"`. Findings are attached to graph nodes, so anything unindexed is unscanned.

2. **Read the active ruleset** with `crg security rule_list --engine heuristic` before scanning, and check which languages each rule declares. This determines what a clean result is worth -- see Coverage Limits below.

3. **Run the Tier 1 scan**: `crg security scan --engine heuristic --repo-root "<path>"`. It returns `total`, `by_severity`, `by_rule`, `tags_by_node`, and `suppressed_count`. Tier 1 is regex matching over the source of function, class, and method nodes -- fast, no external tool, no data-flow analysis.

4. **Run Tier 2 when it is available**: `crg security scan --engine semgrep --repo-root "<path>"`. Semgrep is not installed with crg: it needs the `semgrep` CLI on `PATH` (`uv tool install semgrep`).
   - When the CLI is missing the command returns `{"error": ..., "engine": "semgrep"}` with a non-zero exit.
   - Treat that as **not run**, never as **clean**. Report Tier 2 as unavailable instead of silently reporting Tier 1 numbers as the whole picture.

5. **Rank findings by reachability** -- the step that makes this a graph sweep rather than a grep. For each tagged node, walk backwards toward the entry points:
   - `crg query query --pattern callers_of --target "<node>" --repo-root "<path>"`
   - Repeat on the callers, two or three hops, until you reach either an entry point (route handler, CLI command, worker, event consumer) or nothing.
   - A node with no callers is either dead code or an entry point itself. Distinguish the two before ranking: an unreferenced HTTP handler is the *most* exposed code in the repository, not the least.

6. **Confirm the source-to-sink path before filing anything.** Tier 1 matches text, not data flow, so a match proves a dangerous construct exists, not that untrusted input reaches it. For each candidate:
   - Read the matched line and the parameters of the enclosing function.
   - Establish where the tainted value originates. A `subprocess` call built from a hardcoded constant is not an injection; the same call built from a request field is.
   - use `crg query query --pattern callees_of --target "<node>" --repo-root "<path>"` to confirm what the function actually invokes when the match is ambiguous.

7. **Triage the residue into suppressions.** For rules that are structurally inapplicable to this codebase, or findings confirmed as false positives:
   - `crg security suppress --rule-id "<rule_id>" --repo-root "<path>"` -- persists to `.code-review-graph/security-suppressions.json`
   - add `--remove` to reverse a suppression
   - Suppression is per rule, not per finding, so suppressing a rule hides every current and future match. Record the justification in the report; a suppressed rule that later becomes relevant is a silent regression.

8. **Export when the result feeds another system**: `crg security report --format sarif --repo-root "<path>"` returns SARIF v2.1.0; use `--format json` to re-emit the cached payload. Both replay the last scan rather than rescanning.

9. **Report**:

    ```
    ## Security Sweep: <repo>

    ### Coverage
    - **Tier 1 (heuristic)**: N rules active, applicable to <languages>
    - **Tier 2 (semgrep)**: run / not installed
    - **Unscanned**: <languages present in the repo with no applicable rules>
    - **Suppressed rules**: <rule_id -- justification>

    ### Priority 1 -- Reachable from an entry point
    - **<rule_id>** (<severity>) at `<file>:<line>` in `<node>`
      - Reached by: <entry point> -> <caller> -> <node>
      - Tainted input: <where the value comes from>
      - Fix: <specific change>

    ### Priority 2 -- Reachable, input not confirmed untrusted
    - <finding, and what would have to be true for it to matter>

    ### Priority 3 -- Not reachable from any entry point
    - <finding, plus whether the code is dead or merely unreferenced here>

    ### Dismissed
    - <finding> -- <why it is not a vulnerability>

    ### Recommendation
    1. <ordered, actionable>
    ```

## Priority Matrix

Rank on reachability first, severity second. Severity alone over-reports.

| Reachability | CRITICAL / HIGH | MEDIUM | LOW |
|---|---|---|---|
| Entry point reaches it with untrusted input | Priority 1 | Priority 1 | Priority 2 |
| Reachable, input provenance unconfirmed | Priority 2 | Priority 2 | Priority 3 |
| No caller path from any entry point | Priority 3 | Priority 3 | Dismiss with note |
| Test fixture or example code | Dismiss with note | Dismiss | Dismiss |

## Coverage Limits

State these in the report whenever they apply -- a sweep that hides them is worse than no sweep.

- **Tier 1 is not uniformly multi-language.** Most shipped rules declare a specific language; only the hardcoded-secret rule applies to every language. On a codebase whose main language has no applicable rules, a zero-finding result means *not covered*, not *no vulnerabilities*.
- **No data-flow analysis.** Tier 1 cannot distinguish a constant from user input; step 6 is mandatory, not optional.
- **Only indexed code is scanned.** Anything excluded by `.code-review-graphignore`, or in a repository not federated into the graph, is invisible.
- **Findings attach to function, class, and method nodes.** Dangerous constructs at module top level or in configuration files are outside this scan.
- **Reachability is graph reachability.** Call sites reached over HTTP, RPC, a queue, reflection, or a plugin registry produce no edge, so a finding can be reachable in production while the graph shows no path.

## When to Use

- Reviewing unfamiliar or inherited code before putting it in front of untrusted input
- Before exposing an internal service to a public network
- Auditing a dependency or vendored subtree that has been indexed into the graph
- Periodically on a service that handles user-supplied data, to catch newly introduced sinks

## Related Skills

- `onboard-repo` -- index the codebase and identify entry points first
- `impact-audit` -- scope the blast radius of the fix once a finding is confirmed
- `review-delta` / `review-pr` -- catch a new sink at review time rather than in a later sweep
