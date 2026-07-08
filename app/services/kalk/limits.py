"""Kalk resource caps.

Defaults are deliberately conservative, reversible constants (DECISIONS.md
[2026-07-08] — caps are code-level defaults, not spec). Together they make the
un-interruptible CPython cases (huge bigint pow, giant allocations) unreachable
for the in-process executor.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    # wall clock per evaluation; checked in every tick
    deadline_seconds: float = 0.5
    # global instrumented-operation budget per evaluation
    op_budget: int = 1_000_000
    # iterations per single loop invocation
    max_loop_iterations: int = 100_000
    # strings (source literals and computed values)
    max_str_len: int = 64 * 1024
    # list/tuple lengths
    max_collection_len: int = 100_000
    # |exponent| ceiling for ** (and bit-size ceiling for int bases)
    max_pow_exponent: float = 512
    max_pow_result_bits: int = 4096
    # magnitude ceiling for any numeric value (~1e300; ints via bit_length)
    max_numeric_magnitude: float = 1e300
    max_int_bits: int = 997  # 2**997 ≈ 1.3e300
    # source-size caps (checked before parsing/validation)
    max_source_bytes: int = 100_000
    max_ast_nodes: int = 50_000
    max_ast_depth: int = 200
    # str.format guards (padding-bomb defence)
    max_format_string_len: int = 1024
    max_format_spec_number: int = 100_000
