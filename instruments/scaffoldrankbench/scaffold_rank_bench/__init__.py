"""ScaffoldRankBench public API."""

from .scenarios import build_benchmark
from .semantics import evaluate

__all__ = ["build_benchmark", "evaluate"]
