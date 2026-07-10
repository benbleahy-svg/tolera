"""Kalk evaluator — check() and evaluate() (spec #kalk-exec contract).

M1.8 wires the toy **operation-cost** context only (COST + DAYS); the full
variable system and remaining contexts arrive in M1.9 on this same core.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from app.services.kalk.errors import KalkAbort, KalkError
from app.services.kalk.executor import Executor, InProcessExecutor
from app.services.kalk.limits import Limits
from app.services.kalk.objects import ContextData
from app.services.kalk.runtime import (
    BUILTIN_NAMES,
    DISCOUNT_NAMES,
    OPERATION_COST_NAMES,
    PRICING_ITEM_NAMES,
    DynamicVar,
    Runtime,
    _sanitize_exception,
)
from app.services.kalk.tables import TableProvider
from app.services.kalk.transform import instrument
from app.services.kalk.validator import parse_and_validate

KALK_FILENAME = "<kalk>"

# M1.9 implemented operation_cost + pricing_item, M1.10 adds discount;
# add_on lands with M1.11 and operation_generation with M4 (KALK-REFERENCE §1).
SUPPORTED_CONTEXTS = frozenset({"operation_cost", "pricing_item", "discount"})

_CONTEXT_NAMES: dict[str, frozenset[str]] = {
    "operation_cost": OPERATION_COST_NAMES,
    "pricing_item": PRICING_ITEM_NAMES,
    "discount": DISCOUNT_NAMES,
}


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    errors: list[KalkError]


@dataclass
class EvalResult:
    output: dict[str, Any] | None = None
    declared_variables: list[dict[str, Any]] = field(default_factory=list)
    variable_groups: list[dict[str, Any]] = field(default_factory=list)
    applied_overrides: list[str] = field(default_factory=list)
    notes: str | None = None
    operation_name: str | None = None
    profit_item_name: str | None = None
    discount_name: str | None = None
    workpiece: dict[str, Any] = field(default_factory=dict)
    custom_attributes: dict[str, Any] = field(default_factory=dict)
    errors: list[KalkError] = field(default_factory=list)


def check(
    formula: str,
    context_type: str = "operation_cost",
    extra_names: Iterable[str] = (),
    limits: Limits | None = None,
) -> CheckResult:
    """Static validation only — the editor CHECK button. Never executes."""
    limits = limits or Limits()
    if context_type not in SUPPORTED_CONTEXTS:
        # mirror evaluate(): CHECK must never bless a context that cannot run
        return CheckResult(
            ok=False,
            errors=[
                KalkError(
                    code="invalid_context",
                    message=f"context {context_type!r} is not supported yet "
                    f"(available: {', '.join(sorted(SUPPORTED_CONTEXTS))})",
                )
            ],
        )
    known = BUILTIN_NAMES | _CONTEXT_NAMES[context_type] | set(extra_names)
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
    table_provider: TableProvider | None = None,
    context_data: ContextData | None = None,
) -> EvalResult:
    limits = limits or Limits()
    eval_context = dict(eval_context or {})

    if context_type not in SUPPORTED_CONTEXTS:
        return EvalResult(
            errors=[
                KalkError(
                    code="invalid_context",
                    message=f"context {context_type!r} is not supported yet "
                    f"(available: {', '.join(sorted(SUPPORTED_CONTEXTS))})",
                )
            ]
        )

    known = BUILTIN_NAMES | _CONTEXT_NAMES[context_type] | set(eval_context)
    tree, errors = parse_and_validate(formula, known, limits)
    if errors or tree is None:
        return EvalResult(errors=errors)

    code = compile(instrument(tree), KALK_FILENAME, "exec")

    runtime = Runtime(
        limits=limits,
        overrides=overrides,
        quantity=quantity,
        table_provider=table_provider,
        context_data=context_data,
    )
    namespace = runtime.build_globals(eval_context, context_type)
    result = EvalResult()

    try:
        (executor or InProcessExecutor()).execute(code, namespace)
    except KalkAbort as exc:
        result.errors.append(_locate(exc.error, exc.__traceback__))
    except Exception as exc:
        error = KalkError(code="runtime_error", message=_sanitize_exception(exc))
        result.errors.append(_locate(error, exc.__traceback__))

    result.declared_variables = runtime.declared_variables
    result.variable_groups = runtime.variable_groups
    result.applied_overrides = runtime.applied_overrides
    result.notes = runtime.notes
    result.operation_name = runtime.operation_name
    result.profit_item_name = runtime.profit_item_name
    result.discount_name = runtime.discount_name
    result.workpiece = runtime.workpiece
    result.custom_attributes = runtime.custom_attributes_out

    if not result.errors:
        extract = _OUTPUT_EXTRACTORS[context_type]
        output = extract(namespace, runtime)
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
        errors.append(KalkError(code="missing_output", message="the formula never set COST"))
    elif isinstance(cost, bool) or not isinstance(cost, int | float) or not math.isfinite(cost):
        # var() defaults/overrides can inject inf/nan that skip the arithmetic
        # guards; catch them before they reach canonical serialization.
        errors.append(KalkError(code="invalid_output", message="COST must be a finite number"))

    days: object = namespace.get("DAYS", 0)
    if isinstance(days, DynamicVar):
        try:
            days = days.kalk_value
        except KalkAbort as exc:
            return [exc.error]
    if (
        isinstance(days, bool)
        or not isinstance(days, int | float)
        or not math.isfinite(days)
        or days != int(days)
    ):
        errors.append(
            KalkError(code="invalid_output", message="DAYS must be a whole number of days")
        )

    if errors:
        return errors
    assert isinstance(cost, int | float)
    assert isinstance(days, int | float)
    return {"COST": float(cost), "DAYS": int(days), "no_quote": False}


def _extract_pricing_item_output(
    namespace: dict[str, object], runtime: Runtime
) -> dict[str, Any] | list[KalkError]:
    percentage = namespace.get("PERCENTAGE")
    if isinstance(percentage, DynamicVar):
        try:
            percentage = percentage.kalk_value
        except KalkAbort as exc:
            return [exc.error]
    if percentage is None and "PERCENTAGE" not in namespace:
        return [KalkError(code="missing_output", message="the formula never set PERCENTAGE")]
    if (
        isinstance(percentage, bool)
        or not isinstance(percentage, int | float)
        or not math.isfinite(percentage)
    ):
        return [KalkError(code="invalid_output", message="PERCENTAGE must be a finite number")]
    return {"PERCENTAGE": float(percentage), "custom_cost": runtime.custom_cost}


def _extract_discount_output(
    namespace: dict[str, object], runtime: Runtime
) -> dict[str, Any] | list[KalkError]:
    percentage = namespace.get("PERCENTAGE")
    if isinstance(percentage, DynamicVar):
        try:
            percentage = percentage.kalk_value
        except KalkAbort as exc:
            return [exc.error]
    if percentage is None and "PERCENTAGE" not in namespace:
        return [KalkError(code="missing_output", message="the formula never set PERCENTAGE")]
    if (
        isinstance(percentage, bool)
        or not isinstance(percentage, int | float)
        or not math.isfinite(percentage)
        or percentage < 0
    ):
        # the discount contract fixes PERCENTAGE as positive (KALK-REFERENCE §1)
        # — a sign flip would turn a discount into a hidden surcharge
        return [
            KalkError(
                code="invalid_output", message="PERCENTAGE must be a finite, non-negative number"
            )
        ]
    return {"PERCENTAGE": float(percentage)}


_OUTPUT_EXTRACTORS: dict[str, Any] = {
    "operation_cost": _extract_operation_cost_output,
    "pricing_item": _extract_pricing_item_output,
    "discount": _extract_discount_output,
}


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
