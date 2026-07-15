/**
 * Configure → Pricing (M1.10, spec #costing; DemoE frame 16): the org library
 * of pricing items — the "New Pricing Item" modal creates an item with a
 * Calculation Type (Markup / Margin / Target-Margin) and an existing or NEW
 * custom cost category (name + color + Kalk formula) — plus the discount
 * library. Quote items snapshot these at creation (E4-d freeze); edits here
 * only reach existing drafts via Refresh Pricing.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '../api/client';
import { KalkEditor } from '../estimating/KalkEditor';
import { CATEGORY_SWATCHES } from '../estimating/PricingSection';
import type { KalkCheckResult } from '../estimating/types';
import {
  type DefCalcType,
  type DefCategory,
  type DiscountDefOut,
  type PricingItemDefBody,
  type PricingItemDefOut,
  useConfigureApi,
} from './api';

function PricingItemDefModal({
  initial,
  onCommit,
  onClose,
  onKalkCheck,
}: {
  initial: PricingItemDefOut | null;
  onCommit: (body: PricingItemDefBody) => void;
  onClose: () => void;
  onKalkCheck: (formula: string) => Promise<KalkCheckResult>;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(initial?.name ?? '');
  const [calcType, setCalcType] = useState<DefCalcType>(initial?.calc_type ?? 'markup');
  const [category, setCategory] = useState<DefCategory | 'custom'>(
    initial?.is_custom ? 'custom' : (initial?.category ?? 'general'),
  );
  const [customName, setCustomName] = useState(initial?.custom_category_name ?? '');
  const [color, setColor] = useState(initial?.color ?? CATEGORY_SWATCHES[0].value);
  const [formula, setFormula] = useState(initial?.formula ?? '');
  const [pct, setPct] = useState(initial?.default_pct ?? '');

  const isCustom = category === 'custom';
  const canCommit =
    name.trim() !== '' && (!isCustom || (customName.trim() !== '' && formula.trim() !== ''));

  const title = initial
    ? t('pricing.edit_item_title', { name: initial.name })
    : t('pricing.new_item');

  return (
    <div className="est-modal-backdrop" role="dialog" aria-label={title}>
      <div className="est-modal est-pricing-modal">
        <h3>{title}</h3>
        <label>
          {t('pricing.item_name')}
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <fieldset className="est-radio-group">
          <legend>{t('pricing.calc_type')}</legend>
          {(['markup', 'margin', 'target_margin'] as DefCalcType[]).map((type) => (
            <label key={type}>
              <input
                type="radio"
                name="def-calc-type"
                value={type}
                checked={calcType === type}
                onChange={() => setCalcType(type)}
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
              onChange={(e) => setCategory(e.target.value as DefCategory | 'custom')}
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
          <button
            type="button"
            disabled={!canCommit}
            onClick={() =>
              onCommit({
                name: name.trim(),
                calc_type: calcType,
                category: isCustom ? 'general' : category,
                is_custom: isCustom,
                custom_category_name: isCustom ? customName.trim() : null,
                color: isCustom ? color : null,
                formula: isCustom || formula.trim() !== '' ? formula : null,
                default_pct:
                  String(pct).trim() === '' ? null : String(pct).trim().replace(',', '.'),
              })
            }
          >
            {initial ? t('estimating.save_changes') : t('pricing.add_item')}
          </button>
        </div>
      </div>
    </div>
  );
}

export function PricingDefsPage() {
  const { t } = useTranslation();
  const api = useConfigureApi();
  const [defs, setDefs] = useState<PricingItemDefOut[]>([]);
  const [discountDefs, setDiscountDefs] = useState<DiscountDefOut[]>([]);
  const [creating, setCreating] = useState(false);
  const [editingDef, setEditingDef] = useState<PricingItemDefOut | null>(null);
  const [discountName, setDiscountName] = useState('');
  const [discountPct, setDiscountPct] = useState('');
  const [error, setError] = useState<string | null>(null);

  const fail = useCallback((e: unknown) => {
    setError(e instanceof ApiError ? e.message : String(e));
  }, []);

  const reload = useCallback(() => {
    api.listPricingItemDefs().then(setDefs).catch(fail);
    api.listDiscountDefs().then(setDiscountDefs).catch(fail);
  }, [api, fail]);

  useEffect(reload, [reload]);

  const typeLabel: Record<DefCalcType, string> = {
    markup: t('pricing.type_markup'),
    margin: t('pricing.type_margin'),
    target_margin: t('pricing.type_target_margin'),
  };

  return (
    <main className="est-page">
      <nav className="est-subnav">
        <Link to="/configure">{t('configure.custom_tables')}</Link>
        <span aria-current="page">{t('configure.pricing')}</span>
        <Link to="/configure/operations">{t('configure.operations')}</Link>
      </nav>
      <header className="est-header">
        <h2>{t('configure.pricing')}</h2>
        <button type="button" onClick={() => setCreating(true)}>
          {t('pricing.new_item')}
        </button>
      </header>
      <p className="est-hint">{t('configure.pricing_hint')}</p>
      {error && (
        <p className="est-error" role="alert">
          {error}
        </p>
      )}

      <section className="est-section">
        <table className="est-table">
          <thead>
            <tr>
              <th>{t('pricing.item_name')}</th>
              <th>{t('pricing.calc_type')}</th>
              <th>{t('pricing.category')}</th>
              <th className="est-num">{t('pricing.default_pct')}</th>
              <th aria-label={t('estimating.row_actions')} />
            </tr>
          </thead>
          <tbody>
            {defs.map((def) => (
              <tr key={def.id}>
                <td>{def.name}</td>
                <td>{typeLabel[def.calc_type]}</td>
                <td>
                  {def.is_custom && def.custom_category_name ? (
                    <span
                      className="est-chip"
                      style={{ background: def.color ?? '#64748b', color: '#fff' }}
                    >
                      {def.custom_category_name}
                    </span>
                  ) : (
                    t(
                      `pricing.cat_${
                        def.category === 'purchased_component' ? 'purchased' : def.category
                      }`,
                    )
                  )}
                </td>
                <td className="est-num">{def.default_pct ?? '—'}</td>
                <td className="est-row-actions">
                  <button
                    type="button"
                    onClick={() => setEditingDef(def)}
                    aria-label={t('pricing.edit_item_label', { name: def.name })}
                  >
                    ↗
                  </button>
                  <button
                    type="button"
                    onClick={() => api.deletePricingItemDef(def.id).then(reload).catch(fail)}
                    aria-label={t('estimating.remove', { name: def.name })}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="est-section">
        <header className="est-section-header">
          <h3>{t('pricing.discounts_title')}</h3>
        </header>
        <div className="est-picker-pop">
          <input
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
            disabled={discountName.trim() === ''}
            onClick={() =>
              api
                .createDiscountDef({
                  name: discountName.trim(),
                  default_pct:
                    discountPct.trim() === '' ? null : discountPct.trim().replace(',', '.'),
                })
                .then(() => {
                  setDiscountName('');
                  setDiscountPct('');
                  reload();
                })
                .catch(fail)
            }
          >
            {t('pricing.add_discount')}
          </button>
        </div>
        <table className="est-table">
          <tbody>
            {discountDefs.map((def) => (
              <tr key={def.id}>
                <td>{def.name}</td>
                <td className="est-num">{def.default_pct ?? '—'}</td>
                <td className="est-row-actions">
                  <button
                    type="button"
                    onClick={() => api.deleteDiscountDef(def.id).then(reload).catch(fail)}
                    aria-label={t('estimating.remove', { name: def.name })}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {(creating || editingDef) && (
        <PricingItemDefModal
          initial={editingDef}
          onKalkCheck={api.kalkCheck}
          onCommit={(body) => {
            const save = editingDef
              ? api.updatePricingItemDef(editingDef.id, body)
              : api.createPricingItemDef(body);
            // close only on success — a failed save keeps the modal (and the
            // user's edits) alive with the error shown
            save
              .then(() => {
                setCreating(false);
                setEditingDef(null);
                reload();
              })
              .catch(fail);
          }}
          onClose={() => {
            setCreating(false);
            setEditingDef(null);
          }}
        />
      )}
    </main>
  );
}
