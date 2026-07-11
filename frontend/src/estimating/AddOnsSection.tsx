/**
 * Add-Ons (M1.11, spec #addons; DemoB frame 17): per-line one-time charges —
 * each row has the Required toggle (Required / Not Required) and a per-break
 * price cell (calc from the flat default or the Kalk add_on formula,
 * click-to-override). Rows roll into "Total Required Add-Ons" and "Total
 * Price with Required Add-Ons"; the add-on never touches the unit price and
 * applies after discounts (KB add-ons-p3l-cheat-sheet).
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AddOnCreateBody, AddOnDefOut, PricingSummary } from './types';

interface Props {
  pricing: PricingSummary;
  formatMoney: (value: string | null) => string;
  editable: boolean;
  loadDefs: () => Promise<AddOnDefOut[]>;
  onAdd: (body: AddOnCreateBody) => void;
  onRemove: (addOnId: string) => void;
  onToggleRequired: (addOnId: string, manualIsRequired: boolean) => void;
  onPriceOverride: (addOnId: string, quantity: number, manualPrice: string | null) => void;
}

/** A money cell that flips into a price-override input (PctCell's sibling). */
function PriceCell({
  price,
  overridden,
  editable,
  label,
  formatMoney,
  onOverride,
}: {
  price: string | null;
  overridden: boolean;
  editable: boolean;
  label: string;
  formatMoney: (value: string | null) => string;
  onOverride: (manualPrice: string | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  if (editing) {
    return (
      <td className="est-num">
        <input
          autoFocus
          className="est-cell-input"
          value={draft}
          aria-label={label}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              const trimmed = draft.trim().replace(',', '.');
              onOverride(trimmed === '' ? null : trimmed);
              setEditing(false);
            }
            if (e.key === 'Escape') setEditing(false);
          }}
          onBlur={() => setEditing(false)}
        />
      </td>
    );
  }
  return (
    <td className="est-num">
      <button
        type="button"
        className="est-cell-button"
        disabled={!editable}
        aria-label={label}
        onClick={() => {
          setDraft(price == null ? '' : Number(price).toString());
          setEditing(true);
        }}
      >
        <span className={overridden ? 'est-overridden' : undefined}>
          {formatMoney(price)}
          {overridden && ' *'}
        </span>
      </button>
    </td>
  );
}

export function AddOnsSection({
  pricing,
  formatMoney,
  editable,
  loadDefs,
  onAdd,
  onRemove,
  onToggleRequired,
  onPriceOverride,
}: Props) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const [defs, setDefs] = useState<AddOnDefOut[]>([]);
  const [name, setName] = useState('');

  useEffect(() => {
    if (adding) loadDefs().then(setDefs).catch(() => setDefs([]));
  }, [adding, loadDefs]);

  const quantities = pricing.quantities;

  return (
    <section className="est-section">
      <h3>{t('pricing.add_ons_title')}</h3>
      <table className="est-table">
        <thead>
          <tr>
            <th>{t('pricing.add_on')}</th>
            <th>{t('pricing.required')}</th>
            {quantities.map((qty) => (
              <th key={qty} className="est-num">
                {qty}
              </th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody>
          {pricing.add_ons.map((addOn) => (
            <tr key={addOn.id}>
              <td>{addOn.name}</td>
              <td>
                <button
                  type="button"
                  disabled={!editable}
                  aria-label={t('pricing.required_toggle_label', { name: addOn.name })}
                  onClick={() => onToggleRequired(addOn.id, !addOn.is_required)}
                >
                  {addOn.is_required ? t('pricing.required') : t('pricing.not_required')}
                </button>
              </td>
              {quantities.map((qty) => {
                const cell = addOn.cells.find((c) => c.quantity === qty);
                return (
                  <PriceCell
                    key={qty}
                    price={cell?.price ?? null}
                    overridden={cell?.manual_price != null}
                    editable={editable}
                    label={t('pricing.add_on_price_label', { name: addOn.name, qty })}
                    formatMoney={formatMoney}
                    onOverride={(manualPrice) => onPriceOverride(addOn.id, qty, manualPrice)}
                  />
                );
              })}
              <td>
                <button
                  type="button"
                  disabled={!editable}
                  aria-label={t('pricing.remove_add_on_label', { name: addOn.name })}
                  onClick={() => onRemove(addOn.id)}
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
          <tr className="est-total-row">
            <td>{t('pricing.total_required_add_ons')}</td>
            <td />
            {quantities.map((qty) => {
              const row = pricing.totals.find((r) => r.quantity === qty);
              return (
                <td key={qty} className="est-num">
                  {formatMoney(row?.total_required_add_ons ?? null)}
                </td>
              );
            })}
            <td />
          </tr>
          <tr className="est-total-row">
            <td>{t('pricing.total_with_required_add_ons')}</td>
            <td />
            {quantities.map((qty) => {
              const row = pricing.totals.find((r) => r.quantity === qty);
              return (
                <td key={qty} className="est-num">
                  {formatMoney(row?.total_with_required_add_ons ?? null)}
                </td>
              );
            })}
            <td />
          </tr>
        </tbody>
      </table>
      {adding ? (
        <div className="est-inline-form">
          <select
            aria-label={t('pricing.add_on_type')}
            defaultValue=""
            onChange={(e) => {
              if (e.target.value) {
                onAdd({ source_def_id: e.target.value });
                setAdding(false);
              }
            }}
          >
            <option value="" disabled>
              {t('pricing.add_on_type')}
            </option>
            {defs.map((def) => (
              <option key={def.id} value={def.id}>
                {def.name}
              </option>
            ))}
          </select>
          <input
            aria-label={t('pricing.add_on_name')}
            placeholder={t('pricing.add_on_name')}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            type="button"
            disabled={!name.trim()}
            onClick={() => {
              onAdd({ name: name.trim() });
              setName('');
              setAdding(false);
            }}
          >
            {t('common.add')}
          </button>
          <button type="button" onClick={() => setAdding(false)}>
            {t('common.cancel')}
          </button>
        </div>
      ) : (
        <button type="button" disabled={!editable} onClick={() => setAdding(true)}>
          {t('pricing.add_add_on')}
        </button>
      )}
    </section>
  );
}
