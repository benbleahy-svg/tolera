"""M1.8 — Kalk determinism guard.

Contract (DECISIONS.md [2026-07-08]): identical canonical bytes on the same
platform/build — 1000 in-process runs plus fresh interpreters under varying
``PYTHONHASHSEED`` — with cross-environment equality delivered by running
golden tests in the canonical container image.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.services.kalk import canonical_bytes, evaluate

REPO_ROOT = Path(__file__).resolve().parent.parent

# A formula exercising every non-determinism-prone surface in the M1.8 subset:
# float arithmetic, pow, loops over tuples/lists, str format/split/membership,
# mean/median, banker's round, and a dynamic variable frozen mid-formula.
DETERMINISM_FORMULA = """
material_name = material.split(' ')
base = var('Base Rate', 60.0, 'machine rate EUR/h', number)
size = var('Max Dim', 0, '', number, frozen=False)
size.update(max(dims))
size.freeze()
x = 0.0
for d in dims:
    x = x + d * 1.1 - 0.3
avg = mean(dims)
mid = median(1.5, 2.5, 3.5)
grow = 1.07 ** quantity
label = '{} @{}'.format(material_name, quantity)
set_operation_name(label)
set_notes('deterministic run')
premium = 0.0
if 'Titan' in material:
    premium = 25.0
total = setup_time * base + runtime * make_quantity * base
COST = round(total + x + avg + mid + grow + premium + size, 2)
DAYS = 3
"""

CONTEXT = {
    "material": "Titan Grade 5",
    "dims": [120.5, 44.2, 18.9],
    "setup_time": 0.75,
    "runtime": 0.125,
    "make_quantity": 10,
}


def run_once() -> bytes:
    result = evaluate(
        DETERMINISM_FORMULA,
        context_type="operation_cost",
        eval_context=CONTEXT,
        quantity=10,
    )
    assert not result.errors, result.errors
    return canonical_bytes(result)


def test_thousand_runs_identical_bytes() -> None:
    """M1.8 acceptance: a formula evaluates identically across 1000 runs."""
    outputs = {run_once() for _ in range(1000)}
    assert len(outputs) == 1


SUBPROCESS_SNIPPET = (
    "import sys; sys.path.insert(0, '.');"
    "from tests.test_kalk_m18_determinism import run_once;"
    "sys.stdout.write(run_once().hex())"
)


def test_fresh_interpreters_hash_seeds_identical_bytes() -> None:
    """Hash-seed independence: fresh interpreters with different
    PYTHONHASHSEED values must produce the same canonical bytes."""
    outputs = set()
    for seed in ("0", "1", "424242"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, "-c", SUBPROCESS_SNIPPET],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        outputs.add(proc.stdout.strip())
    assert len(outputs) == 1


def test_float_shortest_repr_preserved() -> None:
    result = evaluate(
        "COST = 0.1 + 0.2",
        context_type="operation_cost",
    )
    assert not result.errors
    assert result.output is not None
    assert result.output["COST"] == 0.30000000000000004
    assert b"0.30000000000000004" in canonical_bytes(result)


def test_canonical_bytes_sorted_and_compact() -> None:
    result = evaluate("COST = 1.5", context_type="operation_cost")
    raw = canonical_bytes(result)
    # sorted keys, compact separators, ascii-only — byte-stable across locales
    assert b": " not in raw
    assert raw.decode("ascii")
    assert raw.index(b"errors") < raw.index(b"output")


def test_nonfinite_output_rejected_not_serialized() -> None:
    # inf/NaN can never reach the canonical serialization
    result = evaluate("COST = 1e308 * 1e308", context_type="operation_cost")
    assert result.errors
    assert result.output is None
