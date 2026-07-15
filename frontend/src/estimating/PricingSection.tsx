/**
 * Costing & Pricing (M1.10, spec #costing; DemoE frames 07-15): the Costing
 * table (five standard categories with color chips, Total Estimated Cost, then
 * the custom-category re-slices below it), the Pricing stack (independent,
 * additive items — Markup / Margin / Target-Margin — an ORDERED stack with
 * drag-handle reorder, per-break "% over amount" cells, click-to-override %,
 * and an expand-to-edit path opening the Kalk editor), the Discounts section,
 * and the output rows (Total / Unit Price excl. discounts with override, Total
 * Markup, profit, margin). Items and discounts originate from the Configure
 * library (snapshot-on-attach, DECISIONS 2026-07-09 ruling 6) with ad-hoc
 * creation as the secondary path. Sections are collapsible with Display
 * Options; ADD buttons render inside the tables per the frames.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { CollapsibleSection, useSectionPrefs } from './CollapsibleSection';
import { KalkEditor } from './KalkEditor';
import { perUnitExact } from './money';
import type {
  CalcType,
  DiscountCreateBody,
  DiscountDefLite,
  KalkCheckResult,
  PricingCategory,
  PricingItemCreateBody,
  PricingItemDefLite,
  PricingItemOut,
  PricingItemUpdateBody,
  PricingSummary,
} from './types';

const CATEGORY_COLORS: Record<PricingCategory, string> = {
  general: '#64748b',
  material: '#d6409f',
  inside: '#8e4ec6',
  outside: '#d4a72c',
  purchased_component: '#46c8d8',
};

/** The 8 fixed cost-category swatches (spec #costing New-Pricing-Item modal);
 * `key` resolves to a translated color name for the aria-label. */
export const CATEGORY_SWATCHES: { value: string; key: string }[] = [
  { value: '#8b1e3f', key: 'maroon' },
  { value: '#d97706', key: 'orange' },
  { value: '#d4a72c', key: 'gold' },
  { value: '#1b6e3c', key: 'green' },
  { value: '#0d9488', key: 'teal' },
  { value: '#2563eb', key: 'blue' },
  { value: '#7c3aed', key: 'purple' },
  { value: '#64748b', key: 'grey' },
];

interface Props {
  pricing: PricingSummary;
  formatMoney: (value: string | null) => string;
  editable: boolean;
  onAddItem: (body: PricingItemCreateBody) => void;
  onUpdateItem: (pricingItemId: string, body: PricingItemUpdateBody) => void;
  onRemoveItem: (pricingItemId: string) => void;
  onReorderItems: (pricingItemIds: string[]) => void;
  onItemPctOverride: (pricingItemId: string, quantity: number, manualPct: string | null) => void;
  onAddDiscount: (body: DiscountCreateBody) => void;
  onRemoveDiscount: (discountId: string) => void;
  onDiscountPctOverride: (discountId: string, quantity: number, manualPct: string | null) => void;
  onUnitPriceOverride: (quantity: number, manualUnitPrice: string | null) => void;
  onRefreshPricing: () => void;
  loadItemDefs: () => Promise<PricingItemDefLite[]>;
  loadDiscountDefs: () => Promise<DiscountDefLite[]>;
  onKalkCheck: (formula: string) => Promise<KalkCheckResult>;
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
  quantity,
  unreachable = false,
  editable,
  label,
  showUnitValues = false,
  formatMoney,
  onOverride,
}: {
  pct: string | null;
  overridden: boolean;
  /** The break-total € contribution shown beneath the %; undefined = pct-only cell. */
  amount?: string | null;
  /** Break quantity — enables the per-unit line under "Stückwerte anzeigen". */
  quantity?: number;
  unreachable?: boolean;
  editable: boolean;
  label: string;
  showUnitValues?: boolean;
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
        {/* break-total contribution always (frames: "% over €"); the toggle
            adds the exact per-unit contribution beneath it */}
        {amount !== undefined && (
          <>
            <br />
            <small>{formatMoney(amount)}</small>
          </>
        )}
        {amount !== undefined && showUnitValues && quantity !== undefined && (
          <>
            <br />
            <small>{formatMoney(perUnitExact(amount ?? null, quantity))}</small>
          </>
        )}
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

/**
 * Create / edit a pricing item. Create mode leads with the Configure library
 * ("add from library" — snapshot-on-attach); the ad-hoc form doubles as the
 * edit surface ("Pricing Formula — <name>" with the Kalk editor).
 */
function PricingItemModal({
  initial,
  defs,
  onCreate,
  onUpdate,
  onClose,
  onKalkCheck,
}: {
  initial: PricingItemOut | null;
  defs: PricingItemDefLite[];
  onCreate: (body: PricingItemCreateBody) => void;
  onUpdate: (pricingItemId: string, body: PricingItemUpdateBody) => void;
  onClose: () => void;
  onKalkCheck: (formula: string) => Promise<KalkCheckResult>;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(initial?.name ?? '');
  const [calcType, setCalcType] = useState<CalcType>(initial?.calc_type ?? 'markup');
  const [category, setCategory] = useState<PricingCategory | 'custom'>(
    initial?.is_custom ? 'custom' : (initial?.category ?? 'general'),
  );
  const [customName, setCustomName] = useState(initial?.custom_category_name ?? '');
  const [color, setColor] = useState(initial?.color ?? CATEGORY_SWATCHES[0].value);
  const [formula, setFormula] = useState(initial?.formula ?? '');
  const [pct, setPct] = useState(initial?.default_pct ?? '');

  const isCustom = category === 'custom';
  const canCommit =
    name.trim() !== '' && (!isCustom || (customName.trim() !== '' && formula.trim() !== ''));

  const commit = () => {
    if (!canCommit) return;
    const body = {
      name: name.trim(),
      calc_type: calcType,
      category: isCustom ? ('general' as const) : category,
      is_custom: isCustom,
      custom_category_name: isCustom ? customName.trim() : null,
      color: isCustom ? color : null,
      formula: isCustom ? formula : formula.trim() === '' ? null : formula,
      default_pct: pct === '' ? null : String(pct).trim().replace(',', '.'),
    };
    if (initial) onUpdate(initial.id, body);
    else onCreate(body);
  };

  const title = initial
    ? t('pricing.edit_item_title', { name: initial.name })
    : t('pricing.new_item');

  return (
    <div className="est-modal-backdrop" role="dialog" aria-label={title}>
      <div className="est-modal est-pricing-modal">
        <h3>{title}</h3>
        {!initial && defs.length > 0 && (
          <>
            <h4>{t('pricing.from_library')}</h4>
            <ul className="est-picker-hits est-def-list">
              {defs.map((def) => (
                <li key={def.id}>
                  <button
                    type="button"
                    onClick={() => onCreate({ source_def_id: def.id })}
                    aria-label={t('pricing.add_from_library_label', { name: def.name })}
                  >
                    {def.name}
                    {def.is_custom && def.custom_category_name && (
                      <CategoryChip
                        label={def.custom_category_name}
                        color={def.color ?? '#64748b'}
                      />
                    )}
                  </button>
                </li>
              ))}
            </ul>
            <h4>{t('pricing.create_new')}</h4>
          </>
        )}
        <label>
          {t('pricing.item_name')}
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <fieldset className="est-radio-group">
          <legend>{t('pricing.calc_type')}</legend>
          {(['markup', 'margin', 'target_margin'] as CalcType[]).map((type) => (
            <label key={type}>
              <input
                type="radio"
                name="calc-type"
                value={type}
                checked={calcType === type}
                onChange={() => {
                  setCalcType(type);
                  // target-margin has no category — clear any custom-only
                  // state so it never leaks into the submitted body
                  if (type === 'target_margin' && category === 'custom') {
                    setCategory('general');
                    setCustomName('');
                    setFormula('');
                  }
                }}
              />
              {t(`pricing.type_${type}`)}
            </label>
          ))}
        </fieldset>
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
            <fieldset className="est-swatch-group">
              <legend>{t('pricing.color')}</legend>
              {CATEGORY_SWATCHES.map((swatch) => (
                <button
                  key={swatch.value}
                  type="button"
                  className={
                    swatch.value === color ? 'est-swatch est-swatch-active' : 'est-swatch'
                  }
                  style={{ background: swatch.value }}
                  aria-label={t('pricing.color_swatch_label', {
                    color: t(`pricing.color_${swatch.key}`),
                  })}
                  aria-pressed={swatch.value === color}
                  onClick={() => setColor(swatch.value)}
                />
              ))}
            </fieldset>
          </>
        )}
        {(isCustom || initial) && (
          <KalkEditor
            value={formula}
            onChange={setFormula}
            name={name.trim() === '' ? undefined : name.trim()}
            onCheck={onKalkCheck}
            rows={6}
          />
        )}
        <label>
          {t('pricing.default_pct')}
          <input value={pct ?? ''} onChange={(e) => setPct(e.target.value)} placeholder="10" />
        </label>
        <div className="est-modal-actions">
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={commit} disabled={!canCommit}>
            {initial ? t('estimating.save_changes') : t('pricing.add_item')}
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
  onUpdateItem,
  onRemoveItem,
  onReorderItems,
  onItemPctOverride,
  onAddDiscount,
  onRemoveDiscount,
  onDiscountPctOverride,
  onUnitPriceOverride,
  onRefreshPricing,
  loadItemDefs,
  loadDiscountDefs,
  onKalkCheck,
}: Props) {
  const { t } = useTranslation();
  const [costingPrefs, setCostingPref] = useSectionPrefs('costing');
  const [pricingPrefs, setPricingPref] = useSectionPrefs('pricing');
  const [discountPrefs, setDiscountPref] = useSectionPrefs('discounts');
  const [addingItem, setAddingItem] = useState(false);
  const [editingItem, setEditingItem] = useState<PricingItemOut | null>(null);
  const [itemDefs, setItemDefs] = useState<PricingItemDefLite[]>([]);
  const [addingDiscount, setAddingDiscount] = useState(false);
  const [discountDefs, setDiscountDefs] = useState<DiscountDefLite[]>([]);
  const [discountName, setDiscountName] = useState('');
  const [discountPct, setDiscountPct] = useState('');
  const [priceEdit, setPriceEdit] = useState<number | null>(null);
  const [priceDraft, setPriceDraft] = useState('');
  const [draggedId, setDraggedId] = useState<string | null>(null);

  const showCostingUnits = costingPrefs.unit_values !== false;
  const showPricingUnits = pricingPrefs.unit_values !== false;

  useEffect(() => {
    if (!addingItem) return;
    loadItemDefs().then(setItemDefs).catch(() => setItemDefs([]));
  }, [addingItem, loadItemDefs]);

  useEffect(() => {
    if (!addingDiscount) return;
    loadDiscountDefs().then(setDiscountDefs).catch(() => setDiscountDefs([]));
  }, [addingDiscount, loadDiscountDefs]);

  const quantities = pricing.quantities;
  const row = (quantity: number) => pricing.costing.find((c) => c.quantity === quantity);
  const totals = (quantity: number) => pricing.totals.find((x) => x.quantity === quantity);

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

  // reorder (the stack is ordered; position feeds Zuschlagskalkulation):
  // pointer drag on the handle, plus ArrowUp/ArrowDown when it has focus
  const dropOn = (targetId: string) => {
    if (!draggedId || draggedId === targetId) return;
    const ids = pricing.pricing_items.map((item) => item.id);
    const from = ids.indexOf(draggedId);
    const to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return;
    ids.splice(to, 0, ...ids.splice(from, 1));
    onReorderItems(ids);
  };

  const moveItemBy = (itemId: string, direction: -1 | 1) => {
    const ids = pricing.pricing_items.map((item) => item.id);
    const from = ids.indexOf(itemId);
    const to = from + direction;
    if (from < 0 || to < 0 || to >= ids.length) return;
    ids.splice(to, 0, ...ids.splice(from, 1));
    onReorderItems(ids);
  };

  const pricingColumnCount = quantities.length + 2;

  return (
    <>
      {/* ------------------------------ Costing ------------------------------ */}
      <CollapsibleSection
        id="costing"
        title={t('pricing.costing_title')}
        collapsed={costingPrefs.collapsed === true}
        onToggleCollapsed={() => setCostingPref('collapsed', costingPrefs.collapsed !== true)}
        options={[
          {
            key: 'unit_values',
            label: t('estimating.show_unit_values'),
            checked: showCostingUnits,
            onChange: (checked) => setCostingPref('unit_values', checked),
          },
        ]}
      >
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
                      {showCostingUnits && (
                        <>
                          <br />
                          <small>{formatMoney(perUnitExact(value, quantity))}</small>
                        </>
                      )}
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
                  {showCostingUnits && (
                    <>
                      <br />
                      <small>{formatMoney(totals(quantity)?.unit_cost ?? null)}</small>
                    </>
                  )}
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
                        {showCostingUnits && (
                          <>
                            <br />
                            <small>{formatMoney(perUnitExact(custom?.cost ?? null, quantity))}</small>
                          </>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </CollapsibleSection>

      {/* ------------------------------ Pricing ------------------------------ */}
      <CollapsibleSection
        id="pricing"
        title={t('pricing.pricing_title')}
        collapsed={pricingPrefs.collapsed === true}
        onToggleCollapsed={() => setPricingPref('collapsed', pricingPrefs.collapsed !== true)}
        options={[
          {
            key: 'unit_values',
            label: t('estimating.show_unit_values'),
            checked: showPricingUnits,
            onChange: (checked) => setPricingPref('unit_values', checked),
          },
        ]}
        actions={
          <details className="est-menu">
            <summary>{t('pricing.actions_menu')}</summary>
            <div className="est-menu-pop" role="menu">
              <button type="button" disabled={!editable} onClick={onRefreshPricing}>
                {t('pricing.refresh_pricing')}
              </button>
            </div>
          </details>
        }
      >
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
              <tr
                key={item.id}
                onDragOver={(e) => {
                  if (draggedId) e.preventDefault();
                }}
                onDrop={() => dropOn(item.id)}
              >
                <td>
                  <span
                    className="est-drag-handle"
                    draggable={editable}
                    role="button"
                    tabIndex={editable ? 0 : -1}
                    aria-label={t('pricing.reorder_handle_label', { name: item.name })}
                    onDragStart={() => setDraggedId(item.id)}
                    onDragEnd={() => setDraggedId(null)}
                    onKeyDown={(e) => {
                      if (!editable) return;
                      if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
                        e.preventDefault();
                        moveItemBy(item.id, e.key === 'ArrowUp' ? -1 : 1);
                      }
                    }}
                  >
                    ≡
                  </span>{' '}
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
                      quantity={quantity}
                      unreachable={cell?.unreachable ?? false}
                      editable={editable}
                      showUnitValues={showPricingUnits}
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
                    onClick={() => setEditingItem(item)}
                    disabled={!editable}
                    aria-label={t('pricing.edit_item_label', { name: item.name })}
                  >
                    ↗
                  </button>
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
            <tr className="est-add-row">
              <td colSpan={pricingColumnCount}>
                <button
                  type="button"
                  className="est-add-button"
                  onClick={() => setAddingItem(true)}
                  disabled={!editable}
                >
                  {t('pricing.add_pricing_item')}
                </button>
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr className="est-total-row">
              <td>{t('pricing.total_excl_discounts')}</td>
              {quantities.map((quantity) => (
                // the API's exact figure (cost + Σ amounts) — rebuilding it
                // from the rounded unit price drifts by cents at some breaks
                <td key={quantity} className="est-num">
                  {formatMoney(totals(quantity)?.total_excl_discounts ?? null)}
                </td>
              ))}
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
              <td>{t('pricing.total_markup')}</td>
              {quantities.map((quantity) => {
                const total = totals(quantity);
                return (
                  <td key={quantity} className="est-num">
                    {formatPct(total?.total_markup_pct ?? null)}
                    <br />
                    <small>{formatMoney(total?.total_markup ?? null)}</small>
                  </td>
                );
              })}
              <td />
            </tr>
            <tr>
              <td>{t('pricing.total_profit')}</td>
              {quantities.map((quantity) => (
                <td key={quantity} className="est-num">
                  {formatMoney(totals(quantity)?.total_profit ?? null)}
                </td>
              ))}
              <td />
            </tr>
            <tr>
              <td>{t('pricing.profit_margin')}</td>
              {quantities.map((quantity) => (
                <td key={quantity} className="est-num">
                  {formatPct(totals(quantity)?.profit_margin_pct ?? null)}
                </td>
              ))}
              <td />
            </tr>
          </tfoot>
        </table>
      </CollapsibleSection>

      {/* ------------------------------ Discounts ---------------------------- */}
      <CollapsibleSection
        id="discounts"
        title={t('pricing.discounts_title')}
        collapsed={discountPrefs.collapsed === true}
        onToggleCollapsed={() => setDiscountPref('collapsed', discountPrefs.collapsed !== true)}
      >
        <table className="est-table">
          <tbody>
            {pricing.discounts.map((discount) => (
              <tr key={discount.id}>
                <td>{discount.name}</td>
                {quantities.map((quantity) => {
                  const cell = discount.cells.find((c) => c.quantity === quantity);
                  return (
                    <PctCell
                      key={quantity}
                      pct={cell?.pct ?? null}
                      overridden={cell?.manual_pct != null}
                      editable={editable}
                      label={t('pricing.discount_pct_override_label', {
                        name: discount.name,
                        quantity,
                      })}
                      formatMoney={formatMoney}
                      onOverride={(manualPct) =>
                        onDiscountPctOverride(discount.id, quantity, manualPct)
                      }
                    />
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
            <tr className="est-add-row">
              <td colSpan={pricingColumnCount}>
                <button
                  type="button"
                  className="est-add-button"
                  onClick={() => setAddingDiscount((v) => !v)}
                  disabled={!editable}
                >
                  {t('pricing.add_discount')}
                </button>
                {addingDiscount && (
                  <div className="est-picker-pop">
                    {discountDefs.length > 0 && (
                      <ul className="est-picker-hits est-def-list">
                        {discountDefs.map((def) => (
                          <li key={def.id}>
                            <button
                              type="button"
                              onClick={() => {
                                onAddDiscount({ source_def_id: def.id });
                                setAddingDiscount(false);
                              }}
                              aria-label={t('pricing.add_from_library_label', {
                                name: def.name,
                              })}
                            >
                              {def.name}
                              {def.default_pct != null && ` (${formatPct(def.default_pct)})`}
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                    <input
                      autoFocus={discountDefs.length === 0}
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
                        onAddDiscount({
                          name: discountName.trim(),
                          default_pct: discountPct.trim().replace(',', '.'),
                        });
                        setAddingDiscount(false);
                        setDiscountName('');
                        setDiscountPct('');
                      }}
                    >
                      {t('pricing.add_discount')}
                    </button>
                  </div>
                )}
              </td>
            </tr>
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
      </CollapsibleSection>

      {(addingItem || editingItem) && (
        <PricingItemModal
          initial={editingItem}
          defs={itemDefs}
          onCreate={(body) => {
            setAddingItem(false);
            onAddItem(body);
          }}
          onUpdate={(id, body) => {
            setEditingItem(null);
            onUpdateItem(id, body);
          }}
          onClose={() => {
            setAddingItem(false);
            setEditingItem(null);
          }}
          onKalkCheck={onKalkCheck}
        />
      )}
    </>
  );
}
