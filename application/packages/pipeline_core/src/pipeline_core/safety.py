"""Evidence-language safety checks.

The interface must never imply a clinical recommendation, a ranked "best"
option, or a trial-eligibility determination that a clinician has not made.
This module is deliberately simple and rule-based -- language safety is a
compliance gate, not a place for a language model to "helpfully" rewrite
the rule.
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
