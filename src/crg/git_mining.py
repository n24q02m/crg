"""Git co-change edge mining (CRG-16).

Mines temporal co-change probabilities ``P(B | A) = co_changes(A, B) / commits(A)``
from ``git log --numstat`` and stores directed ``CO_CHANGES_WITH`` edges in
``GraphStore`` with ``confidence = P(B | A)`` and ``resolution = "heuristic"``.

``analyze_ownership`` builds a read-only ownership and health report for a set
of changed files: line ownership from ``git blame``, commit ownership from
``git shortlog``, bus factor, churn hotspots, change coupling, suggested
reviewers and stale/unused-code signals. Every git call has a timeout and the
whole analysis runs under a time budget, so it stays safe on large repositories.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .incremental import _run_git
from .parser import EdgeInfo

if TYPE_CHECKING:
    from .graph import GraphStore

_COMMIT_MARKER = "COMMIT:"


def _parse_numstat_commits(
    stdout: str, *, max_files_per_commit: int = 50
) -> list[list[str]]:
    commits: list[list[str]] = []
    current: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if line.startswith(_COMMIT_MARKER):
            if 1 <= len(current) <= max_files_per_commit:
                commits.append(list(dict.fromkeys(current)))
            current = []
            continue
        if not line:
            continue
        parts = raw_line.split("\t")
        if len(parts) >= 3:
            file_part = parts[-1].strip()
            if "=>" in file_part and "{" not in file_part:
                file_part = file_part.split("=>")[-1].strip()
            if file_part:
                current.append(file_part.replace("\\", "/"))
    if 1 <= len(current) <= max_files_per_commit:
        commits.append(list(dict.fromkeys(current)))
    return commits


def mine_co_changes(
    repo_root: Path,
    store: GraphStore,
    *,
    max_commits: int = 1000,
    min_confidence: float = 0.3,
    min_co_changes: int = 2,
) -> dict[str, int]:
    """Compute conditional file co-change probabilities and store CO_CHANGES_WITH edges."""
    root = repo_root.resolve()
    git_check = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if git_check.returncode != 0:
        return {"commits_scanned": 0, "edges_upserted": 0}

    log_proc = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "log",
            f"-n{max_commits}",
            "--numstat",
            f"--format={_COMMIT_MARKER}%H",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if log_proc.returncode != 0 or not log_proc.stdout.strip():
        return {"commits_scanned": 0, "edges_upserted": 0}

    commits = _parse_numstat_commits(log_proc.stdout)
    file_counts: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()
    for touched in commits:
        for f in touched:
            file_counts[f] += 1
        if len(touched) >= 2:
            for a, b in combinations(sorted(touched), 2):
                pair_counts[(a, b)] += 1

    # Map normalized relative paths -> graph File qualified_names
    file_lookup: dict[str, str] = {}
    for fp in store.get_all_files():
        p = Path(fp)
        file_lookup[p.as_posix()] = fp
        try:
            rel = p.resolve().relative_to(root).as_posix()
            file_lookup[rel] = fp
        except ValueError:
            pass

    edges_upserted = 0
    for (a, b), co_count in pair_counts.items():
        if co_count < min_co_changes:
            continue
        qa = file_lookup.get(a) or file_lookup.get(str((root / a).resolve().as_posix()))
        qb = file_lookup.get(b) or file_lookup.get(str((root / b).resolve().as_posix()))
        if not qa or not qb:
            continue
        for src_rel, src_qn, dst_qn in ((a, qa, qb), (b, qb, qa)):
            denom = file_counts[src_rel]
            if denom <= 0:
                continue
            conf = co_count / denom
            if conf < min_confidence:
                continue
            store.upsert_edge(
                EdgeInfo(
                    kind="CO_CHANGES_WITH",
                    source=src_qn,
                    target=dst_qn,
                    file_path=src_qn,
                    line=1,
                    extra={
                        "co_changes": co_count,
                        "commits": denom,
                    },
                    confidence=round(conf, 4),
                    resolution="heuristic",
                )
            )
            edges_upserted += 1

    if edges_upserted:
        store.commit()
    return {
        "commits_scanned": len(commits),
        "edges_upserted": edges_upserted,
    }


# ---------------------------------------------------------------------------
# Ownership, bus factor, churn hotspots, change coupling and health signals
# ---------------------------------------------------------------------------

_DAY = 86_400
_SHA_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_SHORTLOG_RE = re.compile(r"^\s*(\d+)\t(.*?)(?:\s*<([^>]*)>)?\s*$")
_BRACE_RENAME_RE = re.compile(r"\{([^{}]*?) => ([^{}]*?)\}")
_EMAIL_RE = re.compile(r"<([^>]*)>")
# Inbound edges of these kinds do not mean that a symbol is used.
_NON_REFERENCE_EDGES = frozenset({"CONTAINS", "CO_CHANGES_WITH"})
_LINE_WEIGHT = 0.7
_COMMIT_WEIGHT = 0.3


def bus_factor(counts: Mapping[str, int], threshold: float = 0.5) -> int:
    """Return the minimum number of authors who together own ``threshold`` of the lines.

    Authors are taken largest first. ``{"a": 5, "b": 3, "c": 2}`` has a bus
    factor of 1 (``a`` alone owns half), ``{"a": 3, "b": 3, "c": 3, "d": 1}``
    has 2. An empty or all-zero mapping returns 0.
    """
    values = sorted((v for v in counts.values() if v > 0), reverse=True)
    need = threshold * sum(values)
    covered = 0
    authors = 0
    for value in values:
        if covered >= need:
            break
        covered += value
        authors += 1
    return authors


def _author_key(name: str, email: str) -> str:
    return (email or name).strip().lower() or "unknown"


def parse_blame_porcelain(stdout: str) -> tuple[dict[str, int], dict[str, str]]:
    """Count blamed lines per author from ``git blame --porcelain`` output.

    Returns ``(line_counts, display_names)`` keyed by lowercased author email
    (or lowercased name when the email is empty). Git applies ``.mailmap``
    before printing, so the keys are already normalised.
    """
    authors: dict[str, list[str]] = {}
    counts: Counter[str] = Counter()
    names: dict[str, str] = {}
    current: list[str] | None = None
    for line in stdout.splitlines():
        if line.startswith("\t"):
            if current is not None:
                key = _author_key(current[0], current[1])
                counts[key] += 1
                names.setdefault(key, current[0] or current[1] or key)
            continue
        head, _, rest = line.partition(" ")
        if _SHA_RE.match(head):
            current = authors.setdefault(head, ["", ""])
        elif current is not None and head == "author":
            current[0] = rest.strip()
        elif current is not None and head == "author-mail":
            current[1] = rest.strip().strip("<>").strip()
    return dict(counts), names


def parse_shortlog(stdout: str) -> tuple[dict[str, int], dict[str, str]]:
    """Count commits per author from ``git shortlog -sne`` output.

    Returns ``(commit_counts, display_names)`` keyed like
    :func:`parse_blame_porcelain`. The first name seen for an email wins.
    """
    counts: Counter[str] = Counter()
    names: dict[str, str] = {}
    for line in stdout.splitlines():
        match = _SHORTLOG_RE.match(line)
        if not match:
            continue
        name = match.group(2).strip()
        email = (match.group(3) or "").strip()
        key = _author_key(name, email)
        counts[key] += int(match.group(1))
        names.setdefault(key, name or email or key)
    return dict(counts), names


def expand_numstat_path(raw: str) -> str:
    """Return the post-rename path of a ``git log --numstat`` path column.

    ``src/{old => new}/f.py`` becomes ``src/new/f.py`` and ``a.py => b.py``
    becomes ``b.py``.
    """
    path = raw.strip().replace("\\", "/")
    if "{" in path and " => " in path:
        path = _BRACE_RENAME_RE.sub(lambda m: m.group(2), path)
        path = re.sub(r"/{2,}", "/", path).lstrip("/")
    elif " => " in path:
        path = path.split(" => ", 1)[1]
    return path.strip()


@dataclass
class _LogCommit:
    sha: str
    timestamp: int
    email: str
    files: dict[str, tuple[int, int]] = field(default_factory=dict)


def _parse_numstat_log(stdout: str) -> list[_LogCommit]:
    """Parse ``git log --numstat --format=COMMIT:%H%x09%at%x09%aE`` output."""
    commits: list[_LogCommit] = []
    current: _LogCommit | None = None
    for raw in stdout.splitlines():
        if raw.startswith(_COMMIT_MARKER):
            fields = raw[len(_COMMIT_MARKER) :].split("\t")
            fields += [""] * (3 - len(fields))
            timestamp = int(fields[1]) if fields[1].isdigit() else 0
            current = _LogCommit(
                fields[0].strip(), timestamp, fields[2].strip().lower()
            )
            commits.append(current)
            continue
        parts = raw.split("\t")
        if current is None or len(parts) < 3:
            continue
        added = int(parts[0]) if parts[0].isdigit() else 0
        deleted = int(parts[1]) if parts[1].isdigit() else 0
        path = expand_numstat_path("\t".join(parts[2:]))
        if path:
            current.files[path] = (added, deleted)
    return commits


def _git_proc(
    top: Path, args: list[str], timeout: float
) -> subprocess.CompletedProcess[str] | None:
    return _run_git(
        top, ["-c", "core.quotepath=false", *args], timeout=timeout, encoding="utf-8"
    )


def _git_out(top: Path, args: list[str], timeout: float) -> str | None:
    proc = _git_proc(top, args, timeout)
    if proc is None or proc.returncode != 0:
        return None
    return proc.stdout


def _looks_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\0" in handle.read(8000)
    except OSError:
        return False


def _canonical_emails(top: Path, emails: Iterable[str], timeout: float) -> list[str]:
    """Lowercase emails and map them through ``.mailmap`` when git can."""
    cleaned = [e.strip().strip("<>").strip() for e in emails if e and e.strip()]
    if not cleaned:
        return []
    out = _git_out(top, ["check-mailmap", *[f"<{e}>" for e in cleaned]], timeout)
    mapped: list[str] = []
    for line in (out or "").splitlines():
        match = _EMAIL_RE.search(line)
        if match and match.group(1).strip():
            mapped.append(match.group(1).strip().lower())
    if len(mapped) != len(cleaned):
        mapped = [e.lower() for e in cleaned]
    return list(dict.fromkeys(mapped))


def _owner_rows(
    line_counts: Mapping[str, int],
    commit_counts: Mapping[str, int],
    names: Mapping[str, str],
    max_owners: int,
) -> list[dict[str, Any]]:
    total_lines = sum(line_counts.values())
    total_commits = sum(commit_counts.values())
    emails = sorted(
        set(line_counts) | set(commit_counts),
        key=lambda e: (-line_counts.get(e, 0), -commit_counts.get(e, 0), e),
    )
    rows = []
    for email in emails[:max_owners]:
        lines = line_counts.get(email, 0)
        commits = commit_counts.get(email, 0)
        rows.append(
            {
                "name": names.get(email, email),
                "email": email,
                "lines": lines,
                "line_share": round(lines / total_lines, 4) if total_lines else 0.0,
                "commits": commits,
                "commit_share": (
                    round(commits / total_commits, 4) if total_commits else 0.0
                ),
            }
        )
    return rows


class _OwnershipRun:
    """Git access, caches and the time budget for one ``analyze_ownership`` call."""

    def __init__(
        self,
        top: Path,
        *,
        max_blame_bytes: int,
        max_commits: int,
        git_timeout: float,
        deadline: float,
    ) -> None:
        self.top = top
        self.max_blame_bytes = max_blame_bytes
        self.max_commits = max_commits
        self.git_timeout = git_timeout
        self.deadline = deadline
        self.budget_exhausted = False
        self._blame: dict[str, tuple[dict[str, int], dict[str, str]] | str] = {}

    def out_of_time(self) -> bool:
        if time.monotonic() >= self.deadline:
            self.budget_exhausted = True
        return self.budget_exhausted

    def blame(self, rel: str) -> tuple[dict[str, int], dict[str, str]] | str:
        """Return ``(line_counts, names)`` or a skip reason string."""
        if rel not in self._blame:
            self._blame[rel] = self._blame_uncached(rel)
        return self._blame[rel]

    def _blame_uncached(self, rel: str) -> tuple[dict[str, int], dict[str, str]] | str:
        path = self.top / rel
        if path.is_file():
            if path.stat().st_size > self.max_blame_bytes:
                return "too_large"
            if _looks_binary(path):
                return "binary"
        proc = _git_proc(
            self.top, ["blame", "--porcelain", "HEAD", "--", rel], self.git_timeout
        )
        if proc is None:
            return "git_error"
        if proc.returncode != 0:
            return "not_committed"
        return parse_blame_porcelain(proc.stdout)

    def shortlog(self, pathspec: str) -> tuple[dict[str, int], dict[str, str]]:
        out = _git_out(
            self.top,
            [
                "shortlog",
                "-sne",
                f"--max-count={self.max_commits}",
                "HEAD",
                "--",
                pathspec,
            ],
            self.git_timeout,
        )
        return parse_shortlog(out or "")

    def module_files(self, module: str) -> list[str]:
        """Files directly inside ``module`` at HEAD (not recursive)."""
        args = ["ls-tree", "HEAD"]
        if module != ".":
            args += ["--", f"{module}/"]
        out = _git_out(self.top, args, self.git_timeout) or ""
        files = []
        for line in out.splitlines():
            meta, _, path = line.partition("\t")
            if meta.split(" ")[1:2] == ["blob"] and path:
                files.append(path)
        return files

    def last_change(self, rel: str, rev: str) -> int | None:
        out = _git_out(
            self.top, ["log", "-1", "--format=%at", rev, "--", rel], self.git_timeout
        )
        value = (out or "").strip()
        return int(value) if value.isdigit() else None


def _relative_targets(top: Path, root: Path, changed_files: Iterable[str]) -> list[str]:
    rels: list[str] = []
    for raw in changed_files:
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        try:
            rels.append(path.resolve().relative_to(top).as_posix())
        except ValueError:
            continue
    return list(dict.fromkeys(rels))


def _hotspots(
    run: _OwnershipRun,
    file_commits: Counter[str],
    churn: Mapping[str, list[int]],
    file_authors: Mapping[str, set[str]],
    *,
    min_commits: int,
    limit: int,
) -> list[dict[str, Any]]:
    ranked = sorted(
        file_commits,
        key=lambda p: (-file_commits[p], -(churn[p][0] + churn[p][1]), p),
    )
    hotspots: list[dict[str, Any]] = []
    for path in ranked:
        if file_commits[path] < min_commits or len(hotspots) >= limit:
            break
        if not (run.top / path).is_file():
            continue
        hotspots.append(
            {
                "path": path,
                "commits": file_commits[path],
                "added": churn[path][0],
                "deleted": churn[path][1],
                "authors": len(file_authors[path]),
            }
        )
    return hotspots


def _coupling(
    run: _OwnershipRun,
    targets: list[str],
    changed: set[str],
    commits: list[_LogCommit],
    *,
    max_files_per_commit: int,
    min_co_changes: int,
    min_confidence: float,
    per_file: int,
) -> list[dict[str, Any]]:
    by_file: dict[str, list[_LogCommit]] = defaultdict(list)
    for commit in commits:
        if len(commit.files) <= max_files_per_commit:
            for path in commit.files:
                by_file[path].append(commit)
    pairs: list[dict[str, Any]] = []
    for rel in targets:
        with_file = by_file.get(rel, [])
        partners = Counter(p for c in with_file for p in c.files if p != rel)
        found = 0
        for partner, co_changes in partners.most_common():
            if co_changes < min_co_changes or found >= per_file:
                break
            confidence = co_changes / len(with_file)
            if confidence < min_confidence or not (run.top / partner).is_file():
                continue
            found += 1
            pairs.append(
                {
                    "source": rel,
                    "target": partner,
                    "co_changes": co_changes,
                    "commits": len(with_file),
                    "confidence": round(confidence, 4),
                    "in_change": partner in changed,
                }
            )
    return pairs


def _store_nodes(store: GraphStore, top: Path, rel: str) -> list[Any]:
    for candidate in dict.fromkeys([str(top / rel), (top / rel).as_posix()]):
        nodes = store.get_nodes_by_file(candidate)
        if nodes:
            return nodes
    return []


def _complex_hotspots(
    store: GraphStore,
    top: Path,
    hotspots: list[dict[str, Any]],
    *,
    min_lines: int,
    min_complexity: int,
) -> list[dict[str, Any]]:
    """Functions in churn hotspots that are long or (when known) complex."""
    result: list[dict[str, Any]] = []
    for hot in hotspots:
        functions: list[dict[str, Any]] = []
        for node in _store_nodes(store, top, hot["path"]):
            if node.kind != "Function" or node.is_test:
                continue
            lines = 0
            if node.line_start and node.line_end:
                lines = node.line_end - node.line_start + 1
            complexity = node.extra.get("complexity", node.extra.get("cyclomatic"))
            if not isinstance(complexity, int | float):
                complexity = None
            if lines >= min_lines or (
                complexity is not None and complexity >= min_complexity
            ):
                functions.append(
                    {
                        "name": node.name,
                        "qualified_name": node.qualified_name,
                        "line_start": node.line_start,
                        "lines": lines,
                        "complexity": complexity,
                    }
                )
        if functions:
            functions.sort(key=lambda f: (-int(f["lines"]), str(f["name"])))
            result.append(
                {
                    "path": hot["path"],
                    "commits": hot["commits"],
                    "functions": functions[:5],
                }
            )
    return result


def _is_decorated(lines: list[str], line_start: int | None) -> bool:
    index = (line_start or 0) - 2
    return 0 <= index < len(lines) and lines[index].lstrip().startswith("@")


def _possibly_unused(
    store: GraphStore, top: Path, rels: list[str], *, limit: int
) -> list[dict[str, Any]]:
    """Module-level functions in ``rels`` that nothing in the graph references."""
    result: list[dict[str, Any]] = []
    for rel in rels:
        try:
            source_lines = (
                (top / rel).read_text(encoding="utf-8", errors="replace").splitlines()
            )
        except OSError:
            source_lines = []
        for node in _store_nodes(store, top, rel):
            name = node.name
            if (
                node.kind != "Function"
                or node.is_test
                or node.parent_name
                or (name.startswith("__") and name.endswith("__"))
                or name == "main"
                or name.startswith("test")
                or _is_decorated(source_lines, node.line_start)
            ):
                continue
            inbound = store.get_edges_by_target(
                node.qualified_name, fallback=False
            ) + store.get_edges_by_target(name, fallback=False)
            if any(e.kind not in _NON_REFERENCE_EDGES for e in inbound):
                continue
            result.append(
                {
                    "name": name,
                    "qualified_name": node.qualified_name,
                    "path": rel,
                    "line_start": node.line_start,
                }
            )
            if len(result) >= limit:
                return result
    return result


def _change_authors(
    top: Path,
    base: str | None,
    exclude_authors: Iterable[str] | None,
    timeout: float,
) -> list[str]:
    if exclude_authors is not None:
        return _canonical_emails(top, exclude_authors, timeout)
    raw: list[str] = []
    if base:
        log = _git_out(
            top, ["log", "--no-merges", "--format=%aE", f"{base}..HEAD"], timeout
        )
        raw += (log or "").splitlines()
    raw += (_git_out(top, ["config", "user.email"], timeout) or "").splitlines()
    return _canonical_emails(top, raw, timeout)


def _module_entry(
    run: _OwnershipRun,
    module: str,
    files: list[dict[str, Any]],
    *,
    max_files: int,
    max_owners: int,
) -> dict[str, Any]:
    members = run.module_files(module)
    ordered = [f["path"] for f in files if f["path"] in members]
    ordered += sorted(p for p in members if p not in ordered)
    line_counts: Counter[str] = Counter()
    names: dict[str, str] = {}
    analyzed = 0
    for rel in ordered[:max_files]:
        if run.out_of_time():
            break
        blamed = run.blame(rel)
        if isinstance(blamed, str):
            continue
        analyzed += 1
        line_counts.update(blamed[0])
        for key, value in blamed[1].items():
            names.setdefault(key, value)
    commit_counts, commit_names = run.shortlog(module)
    return {
        "path": module,
        "lines": sum(line_counts.values()),
        "files_analyzed": analyzed,
        "files_total": len(members),
        "owners": _owner_rows(
            line_counts, commit_counts, {**commit_names, **names}, max_owners
        ),
        "bus_factor": bus_factor(line_counts),
    }


def analyze_ownership(
    repo_root: str | Path,
    changed_files: Iterable[str],
    *,
    store: GraphStore | None = None,
    base: str | None = None,
    exclude_authors: Iterable[str] | None = None,
    max_files: int = 25,
    max_modules: int = 10,
    max_module_files: int = 20,
    max_blame_bytes: int = 512_000,
    max_commits: int = 500,
    max_files_per_commit: int = 50,
    max_owners: int = 5,
    max_reviewers: int = 3,
    git_timeout: float = 10.0,
    time_budget: float = 15.0,
    stale_days: int = 365,
    now: float | None = None,
) -> dict[str, Any]:
    """Build an ownership and health report for ``changed_files``.

    Read-only: nothing is written to the graph. ``store`` is optional and only
    used for the graph-backed health signals (complex hotspots, possibly unused
    functions). ``exclude_authors`` lists the people who wrote the change; when
    it is ``None`` they are detected from ``base..HEAD`` and ``git config
    user.email``. Paths in the result are relative to the git top level.

    Limits: at most ``max_files`` changed files and ``max_modules`` modules
    (``max_module_files`` files each) are blamed, files above
    ``max_blame_bytes`` and binary files are skipped, history is read from the
    last ``max_commits`` commits, every git call gets ``git_timeout`` seconds,
    and the analysis stops early after ``time_budget`` seconds.
    """
    root = Path(repo_root).resolve()
    top_proc = _run_git(root, ["rev-parse", "--show-toplevel"], timeout=git_timeout)
    if top_proc is None:
        return {"available": False, "reason": "git unavailable"}
    if top_proc.returncode != 0 or not top_proc.stdout.strip():
        return {"available": False, "reason": "not a git repository"}
    top = Path(top_proc.stdout.strip()).resolve()
    now = time.time() if now is None else now
    stale_cutoff = now - stale_days * _DAY
    run = _OwnershipRun(
        top,
        max_blame_bytes=max_blame_bytes,
        max_commits=max_commits,
        git_timeout=git_timeout,
        deadline=time.monotonic() + time_budget,
    )
    if base is not None and base.startswith("-"):
        base = None  # never let a ref be parsed as a git option

    changed = _relative_targets(top, root, changed_files)
    targets = changed[:max_files]

    # One bounded history read feeds churn, coupling, hotspots and activity.
    log_out = _git_out(
        top,
        [
            "log",
            f"-n{max_commits}",
            "--no-merges",
            "--numstat",
            f"--format={_COMMIT_MARKER}%H%x09%at%x09%aE",
            "HEAD",
        ],
        git_timeout,
    )
    commits = _parse_numstat_log(log_out or "")
    file_commits: Counter[str] = Counter()
    churn: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    file_authors: dict[str, set[str]] = defaultdict(set)
    last_touch: dict[str, int] = {}
    author_last: dict[str, int] = {}
    for commit in commits:
        author_last[commit.email] = max(
            author_last.get(commit.email, 0), commit.timestamp
        )
        for path, (added, deleted) in commit.files.items():
            file_commits[path] += 1
            churn[path][0] += added
            churn[path][1] += deleted
            file_authors[path].add(commit.email)
            last_touch[path] = max(last_touch.get(path, 0), commit.timestamp)

    hotspots = _hotspots(
        run, file_commits, churn, file_authors, min_commits=2, limit=10
    )
    hot_set = {h["path"] for h in hotspots}

    files: list[dict[str, Any]] = []
    for rel in targets:
        if run.out_of_time():
            break
        added, deleted = churn.get(rel, [0, 0])
        entry: dict[str, Any] = {
            "path": rel,
            "lines": 0,
            "owners": [],
            "bus_factor": 0,
            "churn": {
                "commits": file_commits.get(rel, 0),
                "added": added,
                "deleted": deleted,
            },
            "is_hotspot": rel in hot_set,
        }
        blamed = run.blame(rel)
        if isinstance(blamed, str):
            entry["skipped"] = blamed
        else:
            line_counts, names = blamed
            commit_counts, commit_names = run.shortlog(rel)
            entry["lines"] = sum(line_counts.values())
            entry["owners"] = _owner_rows(
                line_counts, commit_counts, {**commit_names, **names}, max_owners
            )
            entry["bus_factor"] = bus_factor(line_counts)
        files.append(entry)

    modules: list[dict[str, Any]] = []
    module_names = dict.fromkeys(
        posixpath.dirname(f["path"]) or "." for f in files if "skipped" not in f
    )
    for module in list(module_names)[:max_modules]:
        if run.out_of_time():
            break
        modules.append(
            _module_entry(
                run,
                module,
                files,
                max_files=max_module_files,
                max_owners=max_owners,
            )
        )

    coupling = _coupling(
        run,
        [f["path"] for f in files],
        set(changed),
        commits,
        max_files_per_commit=max_files_per_commit,
        min_co_changes=2,
        min_confidence=0.3,
        per_file=5,
    )

    change_authors = _change_authors(top, base, exclude_authors, git_timeout)
    excluded = set(change_authors)

    def is_active(email: str) -> bool:
        return author_last.get(email, 0) >= stale_cutoff

    scores: dict[str, float] = defaultdict(float)
    reviewer_files: dict[str, list[str]] = defaultdict(list)
    reviewer_names: dict[str, str] = {}
    for entry in files:
        for owner in entry["owners"]:
            email = owner["email"]
            if email in excluded:
                continue
            scores[email] += (
                _LINE_WEIGHT * owner["line_share"]
                + _COMMIT_WEIGHT * owner["commit_share"]
            )
            reviewer_files[email].append(entry["path"])
            reviewer_names.setdefault(email, owner["name"])
    ranked = sorted(scores, key=lambda e: (not is_active(e), -scores[e], e))
    suggested = [
        {
            "email": email,
            "name": reviewer_names[email],
            "score": round(scores[email], 4),
            "files": reviewer_files[email],
            "active": is_active(email),
            "last_active": author_last.get(email),
        }
        for email in ranked[:max_reviewers]
    ]

    risks: list[dict[str, Any]] = []
    for scope, entries in (("file", files), ("module", modules)):
        for entry in entries:
            if entry["bus_factor"] == 1:
                top_owner = entry["owners"][0]
                risks.append(
                    {
                        "path": entry["path"],
                        "scope": scope,
                        "owner": top_owner["name"],
                        "owner_email": top_owner["email"],
                        "line_share": top_owner["line_share"],
                    }
                )

    # A changed file is stale when it had not been touched for ``stale_days``
    # before this change; with ``base`` the age is measured at the base ref.
    stale: list[dict[str, Any]] = []
    for entry in files:
        rel = entry["path"]
        if base:
            last = run.last_change(rel, base)
        else:
            last = last_touch.get(rel) or run.last_change(rel, "HEAD")
        if last is None or last >= stale_cutoff:
            continue
        key_owners = entry["owners"][: max(entry["bus_factor"], 1)]
        stale.append(
            {
                "path": rel,
                "age_days": int((now - last) // _DAY),
                "last_change": last,
                "owners_inactive": all(not is_active(o["email"]) for o in key_owners),
            }
        )

    complex_hot: list[dict[str, Any]] = []
    unused: list[dict[str, Any]] = []
    if store is not None:
        complex_hot = _complex_hotspots(
            store, top, hotspots, min_lines=50, min_complexity=10
        )
        unused = _possibly_unused(
            store, top, [f["path"] for f in files if "skipped" not in f], limit=20
        )

    return {
        "available": True,
        "files": files,
        "modules": modules,
        "hotspots": hotspots,
        "coupling": coupling,
        "change_authors": change_authors,
        "suggested_reviewers": suggested,
        "risks": {"bus_factor": risks},
        "health": {
            "stale": stale,
            "complex_hotspots": complex_hot,
            "possibly_unused": unused,
        },
        "history": {"commits_scanned": len(commits)},
        "limits": {
            "max_files": max_files,
            "max_modules": max_modules,
            "max_module_files": max_module_files,
            "max_blame_bytes": max_blame_bytes,
            "max_commits": max_commits,
            "git_timeout": git_timeout,
            "time_budget": time_budget,
        },
        "truncated": len(changed) > len(targets) or run.budget_exhausted,
        "budget_exhausted": run.budget_exhausted,
    }
