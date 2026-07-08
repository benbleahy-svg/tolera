/**
 * The operation drawer (spec #partview "Operation drawer (per-op detail)",
 * simplified per the M1.7 grill): PRIMARY times as Calculated-vs-Override pairs
 * (minutes — never hours, #oplibrary), rates, setup basis (flat € / time),
 * surcharge, yield factor (material lines), per-quantity cost cells with a
 * manual-cost override (clearing falls back to Calculated), and notes.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { OperationOut, OperationUpdateBody } from './types';

interface Props {
  operation: OperationOut;
  formatMoney: (value: string | null) => string;
  onSave: (body: OperationUpdateBody) => void;
  onCellOverride: (quantity: number, manualCost: string | null) => void;
  onClose: () => void;
  disabled?: boolean;
}

/** One Calculated-vs-Override row: read-only calc, editable override. */
function OverrideRow({
  label,
  calc,
  value,
  onChange,
}: {
  label: string;
  calc: string | null;
  value: string;
  onChange: (next: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <label className="est-override-row">
      <span>{label}</span>
      <span className="est-calc-value">
        {t('estimating.calculated')}: {calc ?? '—'}
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t('estimating.override_placeholder')}
      />
    </label>
  );
}

export function OperationDrawer({
  operation,
  formatMoney,
  onSave,
  onCellOverride,
  onClose,
  disabled,
}: Props) {
  const { t } = useTranslation();
  const [setupMins, setSetupMins] = useState(operation.manual_setup_mins ?? '');
  const [runtimeMins, setRuntimeMins] = useState(operation.manual_runtime_mins ?? '');
  const [attendMins, setAttendMins] = useState(operation.manual_attend_mins ?? '');
  const [runRate, setRunRate] = useState(operation.run_rate ?? '');
  const [labourRate, setLabourRate] = useState(operation.labour_rate ?? '');
  const [setupCost, setSetupCost] = useState(operation.setup_cost ?? '');
  const [surcharge, setSurcharge] = useState(operation.surcharge_pct);
  const [yieldFactor, setYieldFactor] = useState(operation.yield_factor);
  const [notes, setNotes] = useState(operation.notes ?? '');
  const [cellDrafts, setCellDrafts] = useState<Record<number, string>>(
    Object.fromEntries(
      operation.cells.map((cell) => [cell.quantity, cell.manual_cost ?? '']),
    ),
  );

  const blankToNull = (value: string): string | null => (value.trim() === '' ? null : value.trim());

  const save = () => {
    const body: OperationUpdateBody = {
      manual_setup_mins: blankToNull(setupMins),
      manual_runtime_mins: blankToNull(runtimeMins),
      run_rate: blankToNull(runRate),
      setup_cost: blankToNull(setupCost),
      surcharge_pct: surcharge,
      notes: blankToNull(notes),
    };
    if (operation.calculation_mode === 'machine_plus_operator') {
      body.manual_attend_mins = blankToNull(attendMins);
      body.labour_rate = blankToNull(labourRate);
    }
    if (operation.category === 'material') body.yield_factor = yieldFactor;
    onSave(body);
  };

  const isMachine = operation.calculation_mode === 'machine_plus_operator';

  return (
    <aside className="est-drawer" aria-label={t('estimating.operation_drawer', { name: operation.name })}>
      <header>
        <h3>{operation.name}</h3>
        <button type="button" onClick={onClose} aria-label={t('common.close')}>
          ×
        </button>
      </header>
      <section>
        <h4>{t('estimating.primary')}</h4>
        {operation.setup_basis === 'flat' ? (
          <label className="est-override-row">
            <span>{t('estimating.setup_cost')}</span>
            <input value={setupCost} onChange={(e) => setSetupCost(e.target.value)} />
          </label>
        ) : (
          <OverrideRow
            label={t('estimating.setup_mins')}
            calc={operation.calc_setup_mins}
            value={setupMins}
            onChange={setSetupMins}
          />
        )}
        <OverrideRow
          label={t(isMachine ? 'estimating.runtime_mins' : 'estimating.work_mins')}
          calc={operation.calc_runtime_mins}
          value={runtimeMins}
          onChange={setRuntimeMins}
        />
        {isMachine && (
          <OverrideRow
            label={t('estimating.attend_mins')}
            calc={operation.calc_attend_mins}
            value={attendMins}
            onChange={setAttendMins}
          />
        )}
      </section>
      <section>
        <h4>{t('estimating.rates')}</h4>
        <label className="est-override-row">
          <span>{t('estimating.run_rate')}</span>
          <input value={runRate} onChange={(e) => setRunRate(e.target.value)} />
        </label>
        {isMachine && (
          <label className="est-override-row">
            <span>{t('estimating.labour_rate')}</span>
            <input value={labourRate} onChange={(e) => setLabourRate(e.target.value)} />
          </label>
        )}
        <label className="est-override-row">
          <span>{t('estimating.surcharge_pct')}</span>
          <input value={surcharge} onChange={(e) => setSurcharge(e.target.value)} />
        </label>
        {operation.category === 'material' && (
          <label className="est-override-row">
            <span>{t('estimating.yield_factor')}</span>
            <input value={yieldFactor} onChange={(e) => setYieldFactor(e.target.value)} />
          </label>
        )}
      </section>
      <section>
        <h4>{t('estimating.cost_per_quantity')}</h4>
        {operation.cells.map((cell) => (
          <div className="est-cell-row" key={cell.quantity}>
            <span className="est-cell-qty">{cell.quantity}</span>
            <span className="est-calc-value">
              {t('estimating.calculated')}: {formatMoney(cell.calc_cost)}
            </span>
            <input
              aria-label={t('estimating.cell_override_label', { quantity: cell.quantity })}
              value={cellDrafts[cell.quantity] ?? ''}
              onChange={(e) =>
                setCellDrafts((prev) => ({ ...prev, [cell.quantity]: e.target.value }))
              }
            />
            <button
              type="button"
              disabled={disabled}
              onClick={() => onCellOverride(cell.quantity, blankToNull(cellDrafts[cell.quantity] ?? ''))}
            >
              {t('estimating.apply_override')}
            </button>
          </div>
        ))}
      </section>
      <section>
        <h4>{t('estimating.notes')}</h4>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
      </section>
      <footer className="est-actions">
        <button type="button" onClick={onClose}>
          {t('common.cancel')}
        </button>
        <button type="button" onClick={save} disabled={disabled}>
          {t('estimating.save_changes')}
        </button>
      </footer>
    </aside>
  );
}
