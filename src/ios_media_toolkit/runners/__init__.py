"""
Runners layer - Execution engines for workflows.

Runners execute workflows, handling task orchestration and progress reporting.
They interpret tasks and call the appropriate actions.
"""

from .base import RunnerCallbacks, RunnerProtocol, RunnerResult
from .sequential import SequentialRunner

__all__ = [
    "RunnerCallbacks",
    "RunnerProtocol",
    "RunnerResult",
    "SequentialRunner",
]
