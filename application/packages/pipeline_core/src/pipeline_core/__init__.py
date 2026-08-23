"""Deterministic scientific core for the MOFA-Guided Oncology Research Copilot.

Every function in this package is pure/deterministic given its inputs so that the
FastAPI service, offline jobs, and test suite can all share a single source of
truth for the science. Nothing here calls the network or a language model.
"""

from importlib import metadata as _metadata

try:
    __version__ = _metadata.version("pipeline_core")
except _metadata.PackageNotFoundError:  # pragma: no cover - editable installs
    __version__ = "0.1.0"
