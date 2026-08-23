"""Evidence-language safety checks.

Port of person_med_a2 pipeline_core.safety plus ODE-specific banned phrases
from pipeline_v2_implementation.md §8.
"""

from __future__ import annotations

import re

BANNED_PHRASES = [
    r"\bbest drug\b",
    r"\bbest treatment\b",
    r"\brecommended treatment\b",
    r"\btreatment recommendation\b",
    r"\bwe recommend\b",
    r"\bshould (be treated|receive|take|use)\b",
    r"\bis eligible\b",
    r"\bpatient is eligible\b",
    r"\bguaranteed\b",
    r"\bcure[sd]?\b",
    r"\bproven to work\b",
    r"\bmust (take|use|receive)\b",
    r"\bwill respond\b",
    r"\bexpected response duration\b",
    r"\bpredicted survival\b",
    r"\bweeks of response\b",
    r"\btime to progression\b",
    r"top (choice|option|recommendation)",
    r"best (drug|agent|option)",
    r"first[- ]line choice",
    r"insufficient data,? but",
    r"low confidence,? however",
]

_COMPILED = [re.compile(pattern, re.IGNORECASE) for pattern in BANNED_PHRASES]


def check_safety(text: str) -> list[str]:
    """Return the list of banned phrases found in ``text`` (empty if safe)."""
    if not text:
        return []
    return [pattern.pattern for pattern in _COMPILED if pattern.search(text)]


def is_safe(text: str) -> bool:
    return len(check_safety(text)) == 0


def assert_safe(text: str, context: str = "") -> None:
    violations = check_safety(text)
    if violations:
        raise ValueError(
            f"Unsafe evidence language{f' in {context}' if context else ''}: "
            f"matched {violations} in: {text!r}"
        )
