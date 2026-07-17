"""Auto-routing (M4.10) — instantiate a process's router onto a component.

Spec ``#assembly``: "Setting a process generates its default router". Two
paths (KB ``custom-operation-generation``):

* **Generic process** (``generation_formula IS NULL``): instantiate the
  process's ``process_operation`` template rows in position order, honoring
  the §4 flags — ``root_component_only`` (PP's PER QUOTE ITEM), ``is_assembly``
  (PP's ASSEMBLY), and ``per_setup`` (one op per detected CNC setup, each
  carrying its 0-based ``setup_index`` → the Kalk ``INDEX`` global).
* **Custom process**: evaluate the process-level Kalk in the
  ``operation_generation`` context; the formula's ``generate_operation()``
  calls become router rows (custom name + ``operation_properties`` persisted,
  read back by ``get_operation_property``).

Every generated row carries ``origin='auto_routing'`` (block AC: generated
values carry their source) and freezes its config from the op def at attach
time (E4-d), exactly like a manual add.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import AppError
from .models import (
    Component,
    ComponentQuantity,
    InterrogationRun,
    OperationDef,
    Process,
    ProcessOperation,
)
from .services.kalk import evaluate
from .services.kalk.objects import ContextData

__all__ = ["generate_router", "setup_count_for"]


async def setup_count_for(session: AsyncSession, component: Component, family: str) -> int:
    """The latest successful interrogation's ``setup_count`` for this part's
    family — 1 when no run (or no scalar) exists, so un-interrogated parts
    still route a single instance."""
    run = await session.scalar(
        select(InterrogationRun)
        .where(
            InterrogationRun.part_id == component.part_id,
            InterrogationRun.family == family,
            InterrogationRun.status == "succeeded",
        )
        .order_by(InterrogationRun.created_at.desc())
        .limit(1)
    )
    scalars: dict[str, Any] = (run.result or {}).get("family_scalars", {}) if run else {}
    count = scalars.get("setup_count")
    if isinstance(count, int) and count > 0:
        return count
    return 1


async def _generate_from_templates(
    session: AsyncSession, component: Component, process: Process
) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(ProcessOperation)
            .where(ProcessOperation.process_id == process.id)
            .order_by(ProcessOperation.position)
        )
    ).all()
    setups: int | None = None  # lazily resolved — most routers have no per_setup row
    generated: list[dict[str, Any]] = []
    def_names = {
        d.id: d.name
        for d in (
            await session.scalars(
                select(OperationDef).where(
                    OperationDef.id.in_([row.operation_def_id for row in rows])
                )
            )
        ).all()
    }
    for row in rows:
        if row.root_component_only and not component.is_root_component:
            continue
        if row.is_assembly and not component.is_assembly:
            continue
        name = def_names.get(row.operation_def_id)
        if name is None:  # pragma: no cover — FK-guaranteed
            continue
        if row.per_setup:
            if setups is None:
                setups = await setup_count_for(session, component, process.family.value)
            for index in range(setups):
                generated.append(
                    {
                        "op_def_name": name,
                        "custom_name": None,
                        "operation_properties": {"setup_index": index},
                    }
                )
        else:
            generated.append(
                {"op_def_name": name, "custom_name": None, "operation_properties": None}
            )
    return generated


async def _generate_from_formula(
    session: AsyncSession, component: Component, process: Process
) -> list[dict[str, Any]]:
    from . import kalk_costing

    assert process.generation_formula is not None
    allowed = (
        (
            await session.execute(
                select(OperationDef.name)
                .join(ProcessOperation, ProcessOperation.operation_def_id == OperationDef.id)
                .where(ProcessOperation.process_id == process.id)
                .order_by(ProcessOperation.position)
            )
        )
        .scalars()
        .all()
    )
    breaks = sorted(
        (
            await session.scalars(
                select(ComponentQuantity).where(ComponentQuantity.component_id == component.id)
            )
        ).all(),
        key=lambda b: b.quantity,
    )
    env = await kalk_costing.load_kalk_env(session, component, breaks)
    first_make = env.make_quantities[0] if env.make_quantities else 1
    first_deliver = env.quantities[0] if env.quantities else 1
    part = kalk_costing.build_part_object(env, first_make, first_deliver)
    # the KB constants compare against part.component_type
    part.attrs["component_type"] = (
        "ASSEMBLED" if component.is_assembly else component.obtain_method.value.upper()
    )
    result = evaluate(
        process.generation_formula,
        context_type="operation_generation",
        eval_context={"part": part},
        quantity=first_make,
        table_provider=env.provider,
        context_data=ContextData(
            quantities=env.quantities.copy(),
            make_quantities=env.make_quantities.copy(),
            bom_quantities=env.quantities.copy(),
        ),
        allowed_operations=list(allowed),
    )
    if result.errors:
        detail = "; ".join(e.message for e in result.errors)
        raise AppError(
            "operation_generation_failed",
            f"Process-level Kalk failed: {detail}",
            status_code=422,
        )
    assert result.output is not None
    operations: list[dict[str, Any]] = result.output["operations"]
    return operations


async def generate_router(session: AsyncSession, org_id: uuid.UUID, component: Component) -> int:
    """Generate ``component``'s router from its process. Appends below any
    existing rows (callers that mean "replace" delete first — the Change
    Process UPDATE path). Returns the number of operations created."""
    from .operations import attach_operation_from_def

    if component.process_id is None:
        return 0
    process = await session.get(Process, component.process_id)
    if process is None or process.deleted_at is not None:
        return 0

    if process.generation_formula is not None:
        generated = await _generate_from_formula(session, component, process)
    else:
        generated = await _generate_from_templates(session, component, process)
    if not generated:
        return 0

    defs_by_name = {
        d.name: d
        for d in (
            await session.scalars(
                select(OperationDef).where(
                    OperationDef.org_id == org_id,
                    OperationDef.name.in_({g["op_def_name"] for g in generated}),
                    OperationDef.deleted_at.is_(None),
                )
            )
        ).all()
    }
    created = 0
    for spec in generated:
        op_def = defs_by_name.get(spec["op_def_name"])
        if op_def is None:
            # formula names are membership-checked in-context; a vanished def
            # (deleted between check and attach) fails loudly
            raise AppError(
                "operation_generation_failed",
                f"Operation definition {spec['op_def_name']!r} is not in the library.",
                status_code=422,
            )
        operation = await attach_operation_from_def(
            session, org_id, component, op_def, added_manually=False
        )
        operation.origin = "auto_routing"
        operation.operation_properties = spec["operation_properties"]
        if spec["custom_name"]:
            operation.name = spec["custom_name"]
        created += 1
    await session.flush()
    return created
