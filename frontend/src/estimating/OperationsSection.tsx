/**
 * One computational section of the part view (spec #partview): the Materials
 * section (material lines) or the Operations router — an ordered row list with
 * per-quantity cost columns (effective cost; overridden cells are marked), row
 * actions (open drawer, duplicate, remove, move up/down as the reorder control),
 * a summary row, and the ADD (MATERIAL) OPERATION type-ahead that creates
 * unknown names on the fly (auto-saved to the org library, #oplibrary).
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { OpCategory, OperationDefOut, OperationOut } from './types';

interface Props {
  title: string;
  addLabel: string;
  category: OpCategory;
  operations: OperationOut[];
  quantities: number[];
  formatMoney: (value: string | null) => string;
  searchDefs: (q: string) => Promise<OperationDefOut[]>;
  onAddFromDef: (defId: string) => void;
  onAddInline: (name: string) => void;
  onOpen: (operation: OperationOut) => void;
  onDuplicate: (operationId: string) => void;
  onRemove: (operationId: string) => void;
  onMove: (operationId: string, direction: -1 | 1) => void;
  disabled?: boolean;
}

export function OperationsSection({
  title,
  addLabel,
  category,
  operations,
  quantities,
  formatMoney,
  searchDefs,
  onAddFromDef,
  onAddInline,
  onOpen,
  onDuplicate,
  onRemove,
  onMove,
  disabled,
}: Props) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState('');
  const [defs, setDefs] = useState<OperationDefOut[]>([]);
  const seq = useRef(0);

  useEffect(() => {
    if (!adding) return;
    const mySeq = ++seq.current;
    const timer = setTimeout(() => {
      searchDefs(query.trim())
        .then((next) => {
          if (mySeq === seq.current) {
            setDefs(next.filter((def) => def.category === category));
          }
        })
        .catch(() => {
          if (mySeq === seq.current) setDefs([]);
        });
    }, 150);
    return () => clearTimeout(timer);
  }, [adding, query, category, searchDefs]);

  const rows = operations.filter((op) => op.category === category);

  const cellFor = (op: OperationOut, quantity: number) =>
    op.cells.find((cell) => cell.quantity === quantity);

  const summary = (quantity: number): string | null => {
    let total = 0;
    let seen = false;
    for (const op of rows) {
      const cell = cellFor(op, quantity);
      if (cell?.effective_cost != null) {
        total += Number(cell.effective_cost);
        seen = true;
      }
    }
    return seen ? total.toFixed(4) : null;
  };

  const addInline = () => {
    const name = query.trim();
    if (name === '') return;
    setAdding(false);
    setQuery('');
    onAddInline(name);
  };

  const addFromDef = (defId: string) => {
    setAdding(false);
    setQuery('');
    onAddFromDef(defId);
  };

  return (
    <section className="est-section">
      <header className="est-section-header">
        <h3>{title}</h3>
        <button type="button" onClick={() => setAdding((v) => !v)} disabled={disabled}>
          {addLabel}
        </button>
      </header>
      {adding && (
        <div className="est-picker-pop">
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('estimating.operation_search_placeholder')}
            aria-label={t('estimating.operation_search_placeholder')}
          />
          <ul className="est-picker-hits">
            {defs.map((def) => (
              <li key={def.id}>
                <button type="button" onClick={() => addFromDef(def.id)}>
                  {def.name}
                </button>
              </li>
            ))}
            {query.trim() !== '' &&
              !defs.some((def) => def.name.toLowerCase() === query.trim().toLowerCase()) && (
                <li>
                  <button type="button" onClick={addInline}>
                    {t('estimating.create_operation', { name: query.trim() })}
                  </button>
                </li>
              )}
          </ul>
        </div>
      )}
      {rows.length === 0 ? (
        <p className="est-empty">{t('estimating.section_empty')}</p>
      ) : (
        <table className="est-table">
          <thead>
            <tr>
              <th>{t('estimating.operation')}</th>
              {quantities.map((quantity) => (
                <th key={quantity} className="est-num">
                  {quantity}
                </th>
              ))}
              <th aria-label={t('estimating.row_actions')} />
            </tr>
          </thead>
          <tbody>
            {rows.map((op, index) => (
              <tr key={op.id}>
                <td>
                  <button type="button" className="est-row-name" onClick={() => onOpen(op)}>
                    {op.name}
                  </button>
                  {op.is_outside_service && (
                    <span className="est-chip">{t('estimating.outside_service')}</span>
                  )}
                </td>
                {quantities.map((quantity) => {
                  const cell = cellFor(op, quantity);
                  const overridden = cell?.manual_cost != null;
                  return (
                    <td key={quantity} className="est-num">
                      <span className={overridden ? 'est-overridden' : undefined}>
                        {formatMoney(cell?.effective_cost ?? null)}
                        {overridden && ' *'}
                      </span>
                    </td>
                  );
                })}
                <td className="est-row-actions">
                  <button
                    type="button"
                    onClick={() => onMove(op.id, -1)}
                    disabled={disabled || index === 0}
                    aria-label={t('estimating.move_up', { name: op.name })}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => onMove(op.id, 1)}
                    disabled={disabled || index === rows.length - 1}
                    aria-label={t('estimating.move_down', { name: op.name })}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    onClick={() => onDuplicate(op.id)}
                    disabled={disabled}
                    aria-label={t('estimating.duplicate', { name: op.name })}
                  >
                    ⧉
                  </button>
                  <button
                    type="button"
                    onClick={() => onRemove(op.id)}
                    disabled={disabled}
                    aria-label={t('estimating.remove', { name: op.name })}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>{t('estimating.section_summary')}</td>
              {quantities.map((quantity) => (
                <td key={quantity} className="est-num">
                  {formatMoney(summary(quantity))}
                </td>
              ))}
              <td />
            </tr>
          </tfoot>
        </table>
      )}
    </section>
  );
}
