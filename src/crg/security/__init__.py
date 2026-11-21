"""Security scanning (Phase 3 v2.0).

Two-tier security engine:
- Tier 1 (heuristic): regex/AST patterns -- always available, ~50 rules.
- Tier 2 (semgrep): wrapper around the semgrep CLI -- opt-in, installed
  separately (``uv tool install semgrep``).
"""

from .heuristic import HeuristicScanner, ScanResult, Tag
from .semgrep_engine import SemgrepNotAvailable, SemgrepResult, SemgrepScanner

__all__ = [
    "HeuristicScanner",
    "ScanResult",
    "SemgrepNotAvailable",
    "SemgrepResult",
    "SemgrepScanner",
    "Tag",
]
