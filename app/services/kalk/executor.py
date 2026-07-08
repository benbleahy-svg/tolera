"""Kalk execution seam.

DECISIONS.md [2026-07-08]: v1 executes in-process behind this interface so a
hard isolation boundary (subprocess + OS rlimits) can replace the execution
step later without touching the evaluator contract.
"""

from __future__ import annotations

from types import CodeType
from typing import Protocol


class Executor(Protocol):
    def execute(self, code: CodeType, namespace: dict[str, object]) -> None: ...


class InProcessExecutor:
    """Runs the instrumented, validated code object in the current process.

    All safety properties come from the layers before and around it: the AST
    allowlist, the empty ``__builtins__``, and the instrumented resource caps.
    """

    def execute(self, code: CodeType, namespace: dict[str, object]) -> None:
        exec(code, namespace)
