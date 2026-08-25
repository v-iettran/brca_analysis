"""Spec-compatible import path: notebooks may `from _gate import gate`."""

from gate import SYNTHETIC_PREFIXES, gate  # noqa: F401

__all__ = ["SYNTHETIC_PREFIXES", "gate"]
