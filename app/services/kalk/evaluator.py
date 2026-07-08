"""Kalk evaluator — check() and evaluate() (spec #kalk-exec contract).

M1.8 wires the toy **operation-cost** context only (COST + DAYS); the full
variable system and remaining contexts arrive in M1.9 on this same core.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from app.services.kalk.errors import KalkAbort, KalkError
from app.services.kalk.executor import Executor, InProcessExecutor
from app.services.kalk.limits import Limits
from app.services.kalk.runtime import (
    BUILTIN_NAMES,
    OPERATION_COST_NAMES,
    DynamicVar,
    Runtime,
    _sanitize_exception,
)
from app.services.kalk.transform import instrument
from app.services.kalk.validator import parse_and_validate

KALK_FILENAME = "<kalk>"

# M1.8 implements operation_cost; the other four (KALK-REFERENCE §1) land in
# M1.9 (pricing_item, add_on, discount) and M4 (operation_generation).
SUPPORTED_CONTEXTS = frozenset({"operation_cost"})

_CONTEXT_NAMES: dict[str, frozenset[str]] = {
    "operation_cost": OPERATION_COST_NAMES,
}


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    errors: list[KalkError]


@dataclass
class EvalResult:
    output: dict[str, Any] | None = None
    declared_variables: list[dict[str, Any]] = field(default_factory=list)
    applied_overrides: list[str] = field(default_factory=list)
    notes: str | None = None
    operation_name: str | None = None
    errors: list[KalkError] = field(default_factory=list)


def check(
    formula: str,
    context_type: str = "operation_cost",
    extra_names: Iterable[str] = (),
    limits: Limits | None = None,
) -> CheckResult:
    """Static validation only — the editor CHECK button. Never executes."""
    limits = limits or Limits()
    known = BUILTIN_NAMES | _CONTEXT_NAMES.get(context_type, frozenset()) | set(extra_names)
    _, errors = parse_and_validate(formula, known, limits)
    return CheckResult(ok=not errors, errors=errors)


def evaluate(
    formula: str,
    context_type: str = "operation_cost",
    eval_context: Mapping[str, object] | None = None,
    quantity: int = 1,
    overrides: Mapping[str, object] | None = None,
    limits: Limits | None = None,
    executor: Executor | None = None,
) -> EvalResult:
    limits = limits or Limits()
    eval_context = dict(eval_context or {})

    if context_type not in SUPPORTED_CONTEXTS:
        return EvalResult(
            errors=[
                KalkError(
                    code="invalid_context",
                    message=f"context {context_type!r} is not available in M1.8",
                )
            ]
        )

    known = BUILTIN_NAMES | _CONTEXT_NAMES[context_type] | set(eval_context)
    tree, errors = parse_and_validate(formula, known, limits)
    if errors or tree is None:
        return EvalResult(errors=errors)

    code = compile(instrument(tree), KALK_FILENAME, "exec")

    runtime = Runtime(limits=limits, overrides=overrides)
    namespace = runtime.build_globals(eval_context, quantity)
    result = EvalResult()

    try:
        (executor or InProcessExecutor()).execute(code, namespace)
    except KalkAbort as exc:
        result.errors.append(_locate(exc.error, exc.__traceback__))
    except Exception as exc:
        error = KalkError(code="runtime_error", message=_sanitize_exception(exc))
        result.errors.append(_locate(error, exc.__traceback__))

    result.declared_variables = runtime.declared_variables
    result.applied_overrides = runtime.applied_overrides
    result.notes = runtime.notes
    result.operation_name = runtime.operation_name

    if not result.errors:
        output = _extract_operation_cost_output(namespace, runtime)
        if isinstance(output, list):
            result.errors.extend(output)
        else:
            result.output = output
    return result


def _extract_operation_cost_output(
    namespace: dict[str, object], runtime: Runtime
) -> dict[str, Any] | list[KalkError]:
    if runtime.no_quote_called:
        return {"COST": None, "DAYS": None, "no_quote": True}

    errors: list[KalkError] = []

    cost = namespace.get("COST")
    if isinstance(cost, DynamicVar):
        try:
            cost = cost.kalk_value
        except KalkAbort as exc:
            return [exc.error]
    if cost is None and "COST" not in namespace:
        errors.append(
            KalkError(code="missing_output", message="the formula never set COST")
        )
    elif isinstance(cost, bool) or not isinstance(cost, int | float):
        errors.append(
            KalkError(code="invalid_output", message="COST must be a number")
        )

    days: object = namespace.get("DAYS", 0)
    if isinstance(days, DynamicVar):
        try:
            days = days.kalk_value
        except KalkAbort as exc:
            return [exc.error]
    if isinstance(days, bool) or not isinstance(days, int | float) or days != int(days):
        errors.append(
            KalkError(
                code="invalid_output", message="DAYS must be a whole number of days"
            )
        )

    if errors:
        return errors
    assert isinstance(cost, int | float)
    assert isinstance(days, int | float)
    return {"COST": float(cost), "DAYS": int(days), "no_quote": False}


def _locate(error: KalkError, tb: TracebackType | None) -> KalkError:
    """Attach the deepest in-formula line number to a runtime error."""
    if error.line is not None:
        return error
    line: int | None = None
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == KALK_FILENAME:
            line = tb.tb_lineno
        tb = tb.tb_next
    if line is None:
        return error
    return KalkError(code=error.code, message=error.message, line=line, col=error.col)
