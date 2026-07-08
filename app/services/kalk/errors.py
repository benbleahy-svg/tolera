"""Kalk error model — typed, position-carrying, never a traceback."""

from __future__ import annotations

from dataclasses import dataclass

# Error codes (stable strings — part of the evaluator contract):
#   syntax             — the source does not parse
#   source_too_large   — source/AST size caps exceeded
#   forbidden_node     — syntax outside the Kalk grammar (import, def, while, …)
#   invalid_constant   — literal outside int/float(finite)/str/bool/None
#   forbidden_name     — underscore-prefixed identifier
#   forbidden_attribute— underscore-prefixed or non-allowlisted attribute
#   unknown_name       — identifier not in the context/builtin/assigned set
#   declaration_in_block — var/table_var/… called inside if/for/lambda
#   invalid_context    — unsupported context_type
#   resource_limit     — an instrumented cap fired (op budget, sizes, pow, …)
#   timeout            — the wall-clock deadline fired
#   runtime_error      — a sanitized in-formula runtime failure
#   missing_output     — required output (COST, …) not set
#   invalid_output     — output set to a value of the wrong type


@dataclass(frozen=True)
class KalkError:
    code: str
    message: str
    line: int | None = None
    col: int | None = None


class KalkAbort(Exception):
    """Internal control flow: carries a KalkError out of guarded runtime code.

    Never escapes the evaluator — ``evaluate()`` converts it to a result error.
    """

    def __init__(self, error: KalkError) -> None:
        super().__init__(error.message)
        self.error = error
