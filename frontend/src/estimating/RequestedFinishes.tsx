/**
 * REQUESTED FINISHES multi-select on the costing-inputs band (M5.0, spec #partview).
 * Backed by finish operation defs (`is_finish`, DECISIONS 2026-07-17); a selected
 * finish is a finish `Operation` on the line item's root component, so operations
 * stay the single source of truth (toggling attaches/removes one).
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { OperationDefOut, OperationOut } from './types';

interface RequestedFinishesProps {
  /** Current operations on the active component — its finishes are the `is_finish` ones. */
  operations: OperationOut[];
  loadFinishDefs: () => Promise<OperationDefOut[]>;
  onAttach: (defId: string) => void;
  onRemove: (operationId: string) => void;
  disabled: boolean;
}

export function RequestedFinishes({
  operations,
  loadFinishDefs,
  onAttach,
  onRemove,
  disabled,
}: RequestedFinishesProps) {
  const { t } = useTranslation();
  const [defs, setDefs] = useState<OperationDefOut[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadFinishDefs()
      .then((d) => {
        if (!cancelled) setDefs(d);
      })
      .catch(() => {
        if (!cancelled) setDefs([]);
      });
    return () => {
      cancelled = true;
    };
  }, [loadFinishDefs]);

  const finishes = operations.filter((op) => op.is_finish);
  // A def is selected when a finish operation copied from it is attached.
  const opByDef = new Map(finishes.filter((f) => f.operation_def_id).map((f) => [f.operation_def_id, f]));

  const toggle = (def: OperationDefOut) => {
    const existing = opByDef.get(def.id);
    if (existing) onRemove(existing.id);
    else onAttach(def.id);
  };

  return (
    <div className="est-finishes">
      <span className="est-field-label">{t('estimating.requested_finishes')}</span>
      <div className="est-finishes-chips">
        {finishes.length === 0 && (
          <span className="est-finishes-none">{t('estimating.no_finishes')}</span>
        )}
        {finishes.map((f) => (
          <span key={f.id} className="est-finish-chip">
            {f.name}
            {!disabled && (
              <button
                type="button"
                aria-label={t('estimating.remove_finish', { name: f.name })}
                onClick={() => onRemove(f.id)}
              >
                ×
              </button>
            )}
          </span>
        ))}
      </div>
      <details
        className="est-menu est-finishes-menu"
        open={open}
        onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      >
        <summary aria-disabled={disabled}>{t('estimating.add_finish')}</summary>
        <div className="est-menu-pop" role="menu">
          {defs.length === 0 && (
            <span className="est-menu-empty">{t('estimating.no_finish_defs')}</span>
          )}
          {defs.map((def) => {
            const selected = opByDef.has(def.id);
            return (
              <label key={def.id} className="est-finish-option">
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={disabled}
                  onChange={() => toggle(def)}
                />
                {def.name}
              </label>
            );
          })}
        </div>
      </details>
    </div>
  );
}
