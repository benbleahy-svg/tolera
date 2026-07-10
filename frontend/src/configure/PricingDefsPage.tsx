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
import {
  type DefCalcType,
  type DefCategory,
  type DiscountDefOut,
  type PricingItemDefBody,
  type PricingItemDefOut,
  useConfigureApi,
} from './api';

function NewPricingItemModal({
  onCommit,
  onClose,
}: {
  onCommit: (body: PricingItemDefBody) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [calcType, setCalcType] = useState<DefCalcType>('markup');
  const [category, setCategory] = useState<DefCategory | 'custom'>('general');
  const [customName, setCustomName] = useState('');
  const [color, setColor] = useState('#8b1e3f');
  const [formula, setFormula] = useState('');
  const [pct, setPct] = useState('');

  const isCustom = category === 'custom';
  const canCommit =
    name.trim() !== '' && (!isCustom || (customName.trim() !== '' && formula.trim() !== ''));

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
          <select value={calcType} onChange={(e) => setCalcType(e.target.value as DefCalcType)}>
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
                default_pct: pct.trim() === '' ? null : pct.trim().replace(',', '.'),
              })
            }
          >
            {t('pricing.add_item')}
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

      {creating && (
        <NewPricingItemModal
          onCommit={(body) => {
            setCreating(false);
            api.createPricingItemDef(body).then(reload).catch(fail);
          }}
          onClose={() => setCreating(false)}
        />
      )}
    </main>
  );
}
