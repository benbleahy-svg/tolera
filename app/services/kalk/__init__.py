"""Kalk — the AST-sandboxed pricing DSL core (M1.8).

Public surface: ``check()`` (static validation, the editor CHECK button),
``evaluate()`` (run a formula in a context), ``canonical_bytes()`` (the
determinism-contract serialization), plus the ``Limits`` resource caps and
the result/error dataclasses.

Isolation boundary and determinism contract: DECISIONS.md [2026-07-08].
This package must stay import-light (no app.config/db) so fresh interpreters
can load it for determinism checks and future subprocess executors.
"""

from app.services.kalk.errors import KalkError
from app.services.kalk.evaluator import (
    SUPPORTED_CONTEXTS,
    CheckResult,
    EvalResult,
    check,
    evaluate,
)
from app.services.kalk.executor import Executor, InProcessExecutor
from app.services.kalk.limits import Limits
from app.services.kalk.objects import ContextData, KalkObject
from app.services.kalk.serialization import canonical_bytes
from app.services.kalk.tables import (
    MappingTableProvider,
    TableColumn,
    TableProvider,
    TableSnapshot,
)

__all__ = [
    "SUPPORTED_CONTEXTS",
    "CheckResult",
    "ContextData",
    "EvalResult",
    "Executor",
    "InProcessExecutor",
    "KalkError",
    "KalkObject",
    "Limits",
    "MappingTableProvider",
    "TableColumn",
    "TableProvider",
    "TableSnapshot",
    "canonical_bytes",
    "check",
    "evaluate",
]
