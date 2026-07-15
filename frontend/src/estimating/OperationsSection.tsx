/**
 * One computational section of the part view (spec #partview, DemoA/8 +
 * DemoB/15): the Materials section (material lines) or the Operations router —
 * an ordered row list with Setup Time / Run Time columns, per-quantity cost
 * columns (total with per-unit beneath; overridden cells are marked), row
 * actions (open drawer, duplicate, remove, move up/down as the reorder
 * control), the in-table ADD button (type-ahead that creates unknown names on
 * the fly, auto-saved to the org library, #oplibrary), a named summary row and
 * — on the operations router — the Yield (%) and Make Quantity footer rows.
 * The section itself is collapsible with a Display-Options gear (chrome shared
 * via CollapsibleSection).
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { CollapsibleSection, useSectionPrefs } from './CollapsibleSection';
import { perUnitExact, sumExact } from './money';
import type { OpCategory, OperationDefOut, OperationOut } from './types';

interface Props {
  sectionId: string;
  title: string;
  addLabel: string;
  summaryLabel: string;
  category: OpCategory;
  operations: OperationOut[];
  quantities: number[];
  /** quantity → make quantity (yield gross-up); enables the Yield / Make
   * Quantity footer rows (operations router only per the frames). */
  makeQuantities?: Record<number, number>;
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

/** "manual ?? calc" minutes → "12,5 Min." (de) / "---" when absent (frames). */
function formatMins(manual: string | null, calc: string | null, locale: string): string {
  const raw = manual ?? calc;
  if (raw == null) return '---';
  const value = Number(raw);
  if (Number.isNaN(value)) return raw;
  return `${new Intl.NumberFormat(locale === 'de' ? 'de-DE' : 'en-IE', {
    maximumFractionDigits: 2,
  }).format(value)} Min.`;
}

export function OperationsSection({
  sectionId,
  title,
  addLabel,
  summaryLabel,
  category,
  operations,
  quantities,
  makeQuantities,
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
  const { t, i18n } = useTranslation();
  const [prefs, setPref] = useSectionPrefs(sectionId);
  const showUnitValues = prefs.unit_values !== false;
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
  const columnCount = quantities.length + 4; // name + setup + run + qtys + actions

  const cellFor = (op: OperationOut, quantity: number) =>
    op.cells.find((cell) => cell.quantity === quantity);

  // exact 4-dp sum; an empty section still shows a zero summary (frames: "$0.00")
  const summary = (quantity: number): string | null =>
    sumExact(
      rows.map((op) => cellFor(op, quantity)?.effective_cost),
      rows.length > 0,
    );

  const formatPctDe = (value: number): string =>
    `${new Intl.NumberFormat(i18n.language === 'de' ? 'de-DE' : 'en-IE', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)} %`;

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
    <CollapsibleSection
      id={sectionId}
      title={title}
      collapsed={prefs.collapsed === true}
      onToggleCollapsed={() => setPref('collapsed', prefs.collapsed !== true)}
      options={[
        {
          key: 'unit_values',
          label: t('estimating.show_unit_values'),
          checked: showUnitValues,
          onChange: (checked) => setPref('unit_values', checked),
        },
      ]}
    >
      <table className="est-table">
        <thead>
          <tr>
            <th>{t('estimating.operation')}</th>
            <th className="est-num">{t('estimating.setup_time_col')}</th>
            <th className="est-num">{t('estimating.run_time_col')}</th>
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
            <tr key={op.id} className={op.missing_rate ? 'est-missing-rate' : undefined}>
              <td>
                <button type="button" className="est-row-name" onClick={() => onOpen(op)}>
                  {op.name}
                </button>
                {op.is_outside_service && (
                  <span className="est-chip">{t('estimating.outside_service')}</span>
                )}
                {op.missing_rate && (
                  <span className="est-chip est-chip-warning">
                    {t('estimating.missing_rate')}
                  </span>
                )}
              </td>
              <td className="est-num">
                {/* flat setup has no time — '---' like the frames; the € cost
                    lives in the drawer, never under a time heading */}
                {op.setup_basis === 'flat'
                  ? '---'
                  : formatMins(op.manual_setup_mins, op.calc_setup_mins, i18n.language)}
              </td>
              <td className="est-num">
                {formatMins(op.manual_runtime_mins, op.calc_runtime_mins, i18n.language)}
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
                    {showUnitValues && (
                      <>
                        <br />
                        <small>{formatMoney(perUnitExact(cell?.effective_cost ?? null, quantity))}</small>
                      </>
                    )}
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
          {/* the ADD button lives inside the table, below the rows (frames) */}
          <tr className="est-add-row">
            <td colSpan={columnCount}>
              <button
                type="button"
                className="est-add-button"
                onClick={() => setAdding((v) => !v)}
                disabled={disabled}
              >
                {addLabel}
              </button>
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
                      !defs.some(
                        (def) => def.name.toLowerCase() === query.trim().toLowerCase(),
                      ) && (
                        <li>
                          <button type="button" onClick={addInline}>
                            {t('estimating.create_operation', { name: query.trim() })}
                          </button>
                        </li>
                      )}
                  </ul>
                </div>
              )}
            </td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={3}>{summaryLabel}</td>
            {quantities.map((quantity) => (
              <td key={quantity} className="est-num">
                {formatMoney(summary(quantity))}
                {showUnitValues && (
                  <>
                    <br />
                    <small>{formatMoney(perUnitExact(summary(quantity), quantity))}</small>
                  </>
                )}
              </td>
            ))}
            <td />
          </tr>
          {makeQuantities && (
            <>
              <tr className="est-meta-row">
                <td colSpan={3}>{t('estimating.yield_row')}</td>
                {quantities.map((quantity) => {
                  const make = makeQuantities[quantity];
                  return (
                    <td key={quantity} className="est-num">
                      {make && make > 0 ? formatPctDe((quantity / make) * 100) : '---'}
                    </td>
                  );
                })}
                <td />
              </tr>
              <tr className="est-meta-row">
                <td colSpan={3}>{t('estimating.make_quantity_row')}</td>
                {quantities.map((quantity) => (
                  <td key={quantity} className="est-num">
                    {makeQuantities[quantity] ?? '---'}
                  </td>
                ))}
                <td />
              </tr>
            </>
          )}
        </tfoot>
      </table>
    </CollapsibleSection>
  );
}
