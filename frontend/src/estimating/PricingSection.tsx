/**
 * Costing & Pricing (M1.10, spec #costing; DemoE frames 07-15): the Costing
 * table (five standard categories with color chips, Total Estimated Cost, then
 * the custom-category re-slices below it), the Pricing stack (independent,
 * additive items — Markup / Margin / Target-Margin — with per-break "% over
 * amount" cells, click-to-override %), the Discounts section, and the output
 * rows (Total / Unit Price excl. discounts with override, discounted price,
 * profit + margin). Everything renders per quantity break, total with per-unit
 * beneath where the frames show it.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type {
  CalcType,
  PricingCategory,
  PricingItemCreateBody,
  PricingSummary,
} from './types';

const CATEGORY_COLORS: Record<PricingCategory, string> = {
  general: '#64748b',
  material: '#d6409f',
  inside: '#8e4ec6',
  outside: '#d4a72c',
  purchased_component: '#46c8d8',
};

interface Props {
  pricing: PricingSummary;
  formatMoney: (value: string | null) => string;
  editable: boolean;
  onAddItem: (body: PricingItemCreateBody) => void;
  onRemoveItem: (pricingItemId: string) => void;
  onItemPctOverride: (pricingItemId: string, quantity: number, manualPct: string | null) => void;
  onAddDiscount: (name: string, defaultPct: string) => void;
  onRemoveDiscount: (discountId: string) => void;
  onUnitPriceOverride: (quantity: number, manualUnitPrice: string | null) => void;
}

function formatPct(value: string | null): string {
  if (value == null) return '—';
  const num = Number(value);
  return Number.isNaN(num) ? value : `${num.toFixed(2).replace('.', ',')} %`;
}

function CategoryChip({ label, color }: { label: string; color: string }) {
  return (
    <span className="est-chip" style={{ background: color, color: '#fff' }}>
      {label}
    </span>
  );
}

/** A cell showing "% over amount" that flips into a % override input. */
function PctCell({
  pct,
  overridden,
  amount,
  unreachable,
  editable,
  label,
  formatMoney,
  onOverride,
}: {
  pct: string | null;
  overridden: boolean;
  amount: string | null;
  unreachable: boolean;
  editable: boolean;
  label: string;
  formatMoney: (value: string | null) => string;
  onOverride: (manualPct: string | null) => void;
}) {
  const { t } = useTranslation();
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
          setDraft(pct == null ? '' : Number(pct).toString());
          setEditing(true);
        }}
      >
        <span className={overridden ? 'est-overridden' : undefined}>
          {formatPct(pct)}
          {overridden && ' *'}
        </span>
        <br />
        <small>{formatMoney(amount)}</small>
        {unreachable && (
          <span className="est-warning" title={t('pricing.unreachable_hint')}>
            {' '}
            {t('pricing.unreachable')}
          </span>
        )}
      </button>
    </td>
  );
}

function AddPricingItemModal({
  onCommit,
  onClose,
}: {
  onCommit: (body: PricingItemCreateBody) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [calcType, setCalcType] = useState<CalcType>('markup');
  const [category, setCategory] = useState<PricingCategory | 'custom'>('general');
  const [customName, setCustomName] = useState('');
  const [color, setColor] = useState('#8b1e3f');
  const [formula, setFormula] = useState('');
  const [pct, setPct] = useState('');

  const isCustom = category === 'custom';
  const canCommit =
    name.trim() !== '' && (!isCustom || (customName.trim() !== '' && formula.trim() !== ''));

  const commit = () => {
    if (!canCommit) return;
    onCommit({
      name: name.trim(),
      calc_type: calcType,
      category: isCustom ? 'general' : category,
      is_custom: isCustom,
      custom_category_name: isCustom ? customName.trim() : null,
      color: isCustom ? color : null,
      formula: isCustom ? formula : formula.trim() === '' ? null : formula,
      default_pct: pct.trim() === '' ? null : pct.trim().replace(',', '.'),
    });
  };

  return (
    <div className="est-modal-backdrop" role="dialog" aria-label={t('pricing.new_item')}>
      <div className="est-modal">
        <h3>{t('pricing.new_item')}</h3>
        <label>
          {t('pricing.item_name')}
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          {t('pricing.calc_type')}
          <select value={calcType} onChange={(e) => setCalcType(e.target.value as CalcType)}>
            <option value="markup">{t('pricing.type_markup')}</option>
            <option value="margin">{t('pricing.type_margin')}</option>
            <option value="target_margin">{t('pricing.type_target_margin')}</option>
          </select>
        </label>
        {calcType !== 'target_margin' && (
          <label>
            {t('pricing.category')}
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as PricingCategory | 'custom')}
            >
              <option value="general">{t('pricing.cat_general')}</option>
              <option value="material">{t('pricing.cat_material')}</option>
              <option value="inside">{t('pricing.cat_inside')}</option>
              <option value="outside">{t('pricing.cat_outside')}</option>
              <option value="purchased_component">{t('pricing.cat_purchased')}</option>
              <option value="custom">{t('pricing.cat_custom')}</option>
            </select>
          </label>
        )}
        {isCustom && (
          <>
            <label>
              {t('pricing.custom_category_name')}
              <input value={customName} onChange={(e) => setCustomName(e.target.value)} />
            </label>
            <label>
              {t('pricing.color')}
              <input type="color" value={color} onChange={(e) => setColor(e.target.value)} />
            </label>
            <label>
              {t('pricing.formula')}
              <textarea
                rows={8}
                value={formula}
                onChange={(e) => setFormula(e.target.value)}
                spellCheck={false}
              />
            </label>
          </>
        )}
        <label>
          {t('pricing.default_pct')}
          <input value={pct} onChange={(e) => setPct(e.target.value)} placeholder="10" />
        </label>
        <div className="est-modal-actions">
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={commit} disabled={!canCommit}>
            {t('pricing.add_item')}
          </button>
        </div>
      </div>
    </div>
  );
}

export function PricingSection({
  pricing,
  formatMoney,
  editable,
  onAddItem,
  onRemoveItem,
  onItemPctOverride,
  onAddDiscount,
  onRemoveDiscount,
  onUnitPriceOverride,
}: Props) {
  const { t } = useTranslation();
  const [addingItem, setAddingItem] = useState(false);
  const [addingDiscount, setAddingDiscount] = useState(false);
  const [discountName, setDiscountName] = useState('');
  const [discountPct, setDiscountPct] = useState('');
  const [priceEdit, setPriceEdit] = useState<number | null>(null);
  const [priceDraft, setPriceDraft] = useState('');

  const quantities = pricing.quantities;
  const row = (quantity: number) => pricing.costing.find((c) => c.quantity === quantity);
  const totals = (quantity: number) => pricing.totals.find((x) => x.quantity === quantity);

  const perUnit = (value: string | null, quantity: number): string | null =>
    value == null ? null : (Number(value) / quantity).toFixed(4);

  const standardRows: {
    key: 'material' | 'inside' | 'outside' | 'purchased_component' | 'child_override';
    label: string;
    chip?: { label: string; color: string };
  }[] = [
    {
      key: 'material',
      label: t('pricing.total_raw_material'),
      chip: { label: t('pricing.chip_material'), color: CATEGORY_COLORS.material },
    },
    {
      key: 'inside',
      label: t('pricing.total_inside'),
      chip: { label: t('pricing.chip_inside'), color: CATEGORY_COLORS.inside },
    },
    {
      key: 'outside',
      label: t('pricing.total_outside'),
      chip: { label: t('pricing.chip_outside'), color: CATEGORY_COLORS.outside },
    },
    {
      key: 'purchased_component',
      label: t('pricing.total_purchased'),
      chip: { label: t('pricing.chip_purchased'), color: CATEGORY_COLORS.purchased_component },
    },
    { key: 'child_override', label: t('pricing.total_overrides') },
  ];

  const customRowIds = pricing.costing[0]?.custom_rows.map((c) => c.pricing_item_id) ?? [];

  const itemCell = (itemId: string, quantity: number) =>
    pricing.pricing_items
      .find((item) => item.id === itemId)
      ?.cells.find((cell) => cell.quantity === quantity);

  return (
    <>
      {/* ------------------------------ Costing ------------------------------ */}
      <section className="est-section">
        <h3>{t('pricing.costing_title')}</h3>
        <table className="est-table">
          <thead>
            <tr>
              <th>{t('estimating.rollup_category')}</th>
              {quantities.map((quantity) => (
                <th key={quantity} className="est-num">
                  {quantity}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {standardRows.map(({ key, label, chip }) => (
              <tr key={key}>
                <td>
                  {label} {chip && <CategoryChip label={chip.label} color={chip.color} />}
                </td>
                {quantities.map((quantity) => {
                  const costing = row(quantity);
                  const value = costing ? costing[key] : null;
                  return (
                    <td key={quantity} className="est-num">
                      {formatMoney(value)}
                      <br />
                      <small>{formatMoney(perUnit(value, quantity))}</small>
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr className="est-total-row">
              <td>{t('pricing.total_estimated_cost')}</td>
              {quantities.map((quantity) => (
                <td key={quantity} className="est-num">
                  {formatMoney(row(quantity)?.total ?? null)}
                  <br />
                  <small>{formatMoney(totals(quantity)?.unit_cost ?? null)}</small>
                </td>
              ))}
            </tr>
            {customRowIds.map((itemId) => {
              const meta = pricing.costing[0]?.custom_rows.find(
                (c) => c.pricing_item_id === itemId,
              );
              return (
                <tr key={itemId}>
                  <td>
                    {meta?.name}{' '}
                    {meta?.name && (
                      <CategoryChip label={meta.name} color={meta.color ?? '#64748b'} />
                    )}
                  </td>
                  {quantities.map((quantity) => {
                    const custom = row(quantity)?.custom_rows.find(
                      (c) => c.pricing_item_id === itemId,
                    );
                    return (
                      <td key={quantity} className="est-num">
                        {formatMoney(custom?.cost ?? null)}
                        <br />
                        <small>{formatMoney(perUnit(custom?.cost ?? null, quantity))}</small>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {/* ------------------------------ Pricing ------------------------------ */}
      <section className="est-section">
        <header className="est-section-header">
          <h3>{t('pricing.pricing_title')}</h3>
          <button type="button" onClick={() => setAddingItem(true)} disabled={!editable}>
            {t('pricing.add_pricing_item')}
          </button>
        </header>
        <table className="est-table">
          <thead>
            <tr>
              <th>{t('pricing.item')}</th>
              {quantities.map((quantity) => (
                <th key={quantity} className="est-num">
                  {quantity}
                </th>
              ))}
              <th aria-label={t('estimating.row_actions')} />
            </tr>
          </thead>
          <tbody>
            {pricing.pricing_items.map((item) => (
              <tr key={item.id}>
                <td>
                  {item.name}{' '}
                  {item.is_custom && item.custom_category_name ? (
                    <CategoryChip
                      label={item.custom_category_name}
                      color={item.color ?? '#64748b'}
                    />
                  ) : item.calc_type === 'target_margin' ? (
                    <span className="est-chip">{t('pricing.type_target_margin')}</span>
                  ) : item.category !== 'general' ? (
                    <CategoryChip
                      label={t(`pricing.chip_${item.category === 'purchased_component' ? 'purchased' : item.category}`)}
                      color={CATEGORY_COLORS[item.category]}
                    />
                  ) : null}
                  {item.calc_type === 'margin' && (
                    <span className="est-chip">{t('pricing.type_margin')}</span>
                  )}
                </td>
                {quantities.map((quantity) => {
                  const cell = itemCell(item.id, quantity);
                  return (
                    <PctCell
                      key={quantity}
                      pct={cell?.pct ?? null}
                      overridden={cell?.manual_pct != null}
                      amount={cell?.amount ?? null}
                      unreachable={cell?.unreachable ?? false}
                      editable={editable}
                      label={t('pricing.pct_override_label', {
                        name: item.name,
                        quantity,
                      })}
                      formatMoney={formatMoney}
                      onOverride={(manualPct) => onItemPctOverride(item.id, quantity, manualPct)}
                    />
                  );
                })}
                <td className="est-row-actions">
                  <button
                    type="button"
                    onClick={() => onRemoveItem(item.id)}
                    disabled={!editable}
                    aria-label={t('estimating.remove', { name: item.name })}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="est-total-row">
              <td>{t('pricing.total_excl_discounts')}</td>
              {quantities.map((quantity) => {
                const total = totals(quantity);
                const preUnit = total?.manual_unit_price ?? total?.calc_unit_price ?? null;
                const totalExcl =
                  preUnit == null ? null : (Number(preUnit) * quantity).toFixed(2);
                return (
                  <td key={quantity} className="est-num">
                    {formatMoney(totalExcl)}
                  </td>
                );
              })}
              <td />
            </tr>
            <tr>
              <td>{t('pricing.unit_price_excl_discounts')}</td>
              {quantities.map((quantity) => {
                const total = totals(quantity);
                const overridden = total?.manual_unit_price != null;
                if (priceEdit === quantity) {
                  return (
                    <td key={quantity} className="est-num">
                      <input
                        autoFocus
                        className="est-cell-input"
                        value={priceDraft}
                        aria-label={t('pricing.unit_price_override_label', { quantity })}
                        onChange={(e) => setPriceDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            const trimmed = priceDraft.trim().replace(',', '.');
                            onUnitPriceOverride(quantity, trimmed === '' ? null : trimmed);
                            setPriceEdit(null);
                          }
                          if (e.key === 'Escape') setPriceEdit(null);
                        }}
                        onBlur={() => setPriceEdit(null)}
                      />
                    </td>
                  );
                }
                const preUnit = total?.manual_unit_price ?? total?.calc_unit_price ?? null;
                return (
                  <td key={quantity} className="est-num">
                    <button
                      type="button"
                      className="est-cell-button"
                      disabled={!editable}
                      aria-label={t('pricing.unit_price_override_label', { quantity })}
                      onClick={() => {
                        setPriceDraft(preUnit == null ? '' : Number(preUnit).toString());
                        setPriceEdit(quantity);
                      }}
                    >
                      <span className={overridden ? 'est-overridden' : undefined}>
                        {formatMoney(preUnit)}
                        {overridden && ' *'}
                      </span>
                    </button>
                  </td>
                );
              })}
              <td />
            </tr>
            <tr>
              <td>{t('pricing.total_profit')}</td>
              {quantities.map((quantity) => {
                const total = totals(quantity);
                return (
                  <td key={quantity} className="est-num">
                    {formatMoney(total?.total_profit ?? null)}
                    <br />
                    <small>{formatPct(total?.profit_margin_pct ?? null)}</small>
                  </td>
                );
              })}
              <td />
            </tr>
          </tfoot>
        </table>
      </section>

      {/* ------------------------------ Discounts ---------------------------- */}
      <section className="est-section">
        <header className="est-section-header">
          <h3>{t('pricing.discounts_title')}</h3>
          <button type="button" onClick={() => setAddingDiscount(true)} disabled={!editable}>
            {t('pricing.add_discount')}
          </button>
        </header>
        {addingDiscount && (
          <div className="est-picker-pop">
            <input
              autoFocus
              value={discountName}
              onChange={(e) => setDiscountName(e.target.value)}
              placeholder={t('pricing.discount_name')}
              aria-label={t('pricing.discount_name')}
            />
            <input
              value={discountPct}
              onChange={(e) => setDiscountPct(e.target.value)}
              placeholder="%"
              aria-label={t('pricing.discount_pct')}
            />
            <button
              type="button"
              disabled={discountName.trim() === '' || discountPct.trim() === ''}
              onClick={() => {
                onAddDiscount(discountName.trim(), discountPct.trim().replace(',', '.'));
                setAddingDiscount(false);
                setDiscountName('');
                setDiscountPct('');
              }}
            >
              {t('pricing.add_discount')}
            </button>
          </div>
        )}
        <table className="est-table">
          <tbody>
            {pricing.discounts.map((discount) => (
              <tr key={discount.id}>
                <td>{discount.name}</td>
                {quantities.map((quantity) => {
                  const cell = discount.cells.find((c) => c.quantity === quantity);
                  return (
                    <td key={quantity} className="est-num">
                      {formatPct(cell?.pct ?? null)}
                    </td>
                  );
                })}
                <td className="est-row-actions">
                  <button
                    type="button"
                    onClick={() => onRemoveDiscount(discount.id)}
                    disabled={!editable}
                    aria-label={t('estimating.remove', { name: discount.name })}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>{t('pricing.total_discount')}</td>
              {quantities.map((quantity) => {
                const total = totals(quantity);
                return (
                  <td key={quantity} className="est-num">
                    {formatPct(total?.total_discount_pct ?? null)}
                    <br />
                    <small>{formatMoney(total?.total_discount ?? null)}</small>
                  </td>
                );
              })}
              <td />
            </tr>
            <tr className="est-total-row">
              <td>{t('pricing.total_incl_discounts')}</td>
              {quantities.map((quantity) => {
                const total = totals(quantity);
                return (
                  <td key={quantity} className="est-num">
                    {formatMoney(total?.total_price ?? null)}
                    <br />
                    <small>{formatMoney(total?.unit_price ?? null)}</small>
                  </td>
                );
              })}
              <td />
            </tr>
          </tfoot>
        </table>
      </section>

      {addingItem && (
        <AddPricingItemModal
          onCommit={(body) => {
            setAddingItem(false);
            onAddItem(body);
          }}
          onClose={() => setAddingItem(false)}
        />
      )}
    </>
  );
}
