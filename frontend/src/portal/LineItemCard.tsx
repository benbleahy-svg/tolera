/**
 * One buyer-portal line-item card (M5.1). Read-only part identity (only the
 * fields the server chose to expose — already gated), an optional 3D thumbnail
 * placeholder, the qty×lead-time RADIO grid (one radio per break, with expedite
 * tiers as selectable sub-rows showing the "+ surcharge / Stk." delta), and
 * optional add-on checkboxes (required add-ons are always checked + disabled).
 * A No-Quote line shows contact copy and no grid.
 */

import { Fragment } from 'react';
import { useTranslation } from 'react-i18next';

import { formatMoney } from './money';
import type { BuyerAddOn, BuyerLineItem, LineSelection } from './types';

/** The add-on's price at the selected quantity, falling back to its first tier. */
function addOnPriceFor(addOn: BuyerAddOn, quantity: number | null): string | null {
  const match = quantity != null ? addOn.prices.find((p) => p.quantity === quantity) : undefined;
  return (match ?? addOn.prices[0])?.price ?? null;
}

function DimensionLine({
  dimensions,
}: {
  dimensions: NonNullable<BuyerLineItem['dimensions']>;
}) {
  const parts = [dimensions.x, dimensions.y, dimensions.z].filter((d): d is string => d != null);
  if (parts.length === 0) return null;
  return <div className="portal-part-dims">{parts.join(' × ')} mm</div>;
}

export function LineItemCard({
  item,
  currency,
  selection,
  onSelectBreak,
  onToggleAddOn,
}: {
  item: BuyerLineItem;
  currency: string;
  selection: LineSelection | undefined;
  onSelectBreak: (quantity: number, expediteId: string | null) => void;
  onToggleAddOn: (addOnId: string) => void;
}) {
  const { t } = useTranslation();
  const selectedQuantity = selection?.quantity ?? null;
  const selectedExpedite = selection?.expediteId ?? null;
  const radioName = `li-${item.quote_item_id}`;

  return (
    <article className="portal-line-card">
      <header className="portal-line-head">
        {item.has_model && (
          <div className="portal-thumb" aria-hidden="true">
            3D
          </div>
        )}
        <div className="portal-part-identity">
          <div className="portal-part-title">
            {item.part_number ? (
              <span className="portal-part-number">{item.part_number}</span>
            ) : (
              <span className="portal-part-number">{t('portal.position', { position: item.position })}</span>
            )}
            {item.revision && <span className="portal-part-rev">Rev. {item.revision}</span>}
          </div>
          {item.description && <div className="portal-part-desc">{item.description}</div>}
          <dl className="portal-part-meta">
            {item.process && (
              <>
                <dt>{t('portal.process')}</dt>
                <dd>{item.process}</dd>
              </>
            )}
            {item.material && (
              <>
                <dt>{t('portal.material')}</dt>
                <dd>
                  {item.material}
                  {item.werkstoffnummer ? ` (${item.werkstoffnummer})` : ''}
                </dd>
              </>
            )}
          </dl>
          {item.dimensions && <DimensionLine dimensions={item.dimensions} />}
          {item.dfm_warnings && item.dfm_warnings.length > 0 && (
            <ul className="portal-dfm">
              {item.dfm_warnings.map((warning, index) => (
                <li key={index}>{warning}</li>
              ))}
            </ul>
          )}
        </div>
      </header>

      {item.is_no_quote ? (
        <p className="portal-no-quote">{t('portal.no_quote')}</p>
      ) : (
        <>
          <div className="portal-grid-scroll">
            <table className="portal-break-grid">
              <thead>
                <tr>
                  <th className="portal-radio-col">
                    <span className="portal-visually-hidden">{t('portal.select_option')}</span>
                  </th>
                  <th>{t('portal.quantity')}</th>
                  <th>{t('portal.lead_time_days')}</th>
                  <th className="portal-num">{t('portal.unit_price')}</th>
                  <th className="portal-num">{t('portal.total')}</th>
                </tr>
              </thead>
              <tbody>
                {(item.breaks ?? []).map((brk) => {
                  const stdChecked = selectedQuantity === brk.quantity && selectedExpedite === null;
                  return (
                    <Fragment key={`b-${brk.quantity}`}>
                      <tr className={stdChecked ? 'portal-row-selected' : undefined}>
                        <td className="portal-radio-col">
                          <input
                            type="radio"
                            name={radioName}
                            checked={stdChecked}
                            onChange={() => onSelectBreak(brk.quantity, null)}
                            aria-label={t('portal.select_break', { quantity: brk.quantity })}
                          />
                        </td>
                        <td>{brk.quantity}</td>
                        <td>{brk.lead_time_days ?? '—'}</td>
                        <td className="portal-num">{formatMoney(brk.unit_price, currency)}</td>
                        <td className="portal-num">{formatMoney(brk.total_price, currency)}</td>
                      </tr>
                      {brk.expedites.map((exp) => {
                        const expChecked =
                          selectedQuantity === brk.quantity && selectedExpedite === exp.id;
                        return (
                          <tr
                            key={`e-${exp.id}`}
                            className={
                              expChecked ? 'portal-row-expedite portal-row-selected' : 'portal-row-expedite'
                            }
                          >
                            <td className="portal-radio-col">
                              <input
                                type="radio"
                                name={radioName}
                                checked={expChecked}
                                onChange={() => onSelectBreak(brk.quantity, exp.id)}
                                aria-label={t('portal.select_expedite', {
                                  quantity: brk.quantity,
                                  days: exp.days_faster,
                                })}
                              />
                            </td>
                            <td className="portal-expedite-label">
                              {t('portal.expedite_faster', { days: exp.days_faster })}
                              <span className="portal-surcharge">
                                {t('portal.expedite_surcharge', {
                                  amount: formatMoney(exp.unit_surcharge, currency),
                                })}
                              </span>
                            </td>
                            <td>{exp.lead_time_days ?? '—'}</td>
                            <td className="portal-num">{formatMoney(exp.unit_price, currency)}</td>
                            <td className="portal-num">{formatMoney(exp.total_price, currency)}</td>
                          </tr>
                        );
                      })}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {item.add_ons && item.add_ons.length > 0 && (
            <fieldset className="portal-add-ons">
              <legend>{t('portal.add_ons')}</legend>
              {item.add_ons.map((addOn) => {
                const price = formatMoney(addOnPriceFor(addOn, selectedQuantity), currency);
                const checked = addOn.is_required || (selection?.addOnIds.has(addOn.id) ?? false);
                return (
                  <label key={addOn.id} className="portal-add-on">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={addOn.is_required}
                      onChange={() => onToggleAddOn(addOn.id)}
                    />
                    <span>
                      {addOn.display_name} — {price}
                      {addOn.is_required && (
                        <span className="portal-required"> {t('portal.add_on_required')}</span>
                      )}
                    </span>
                  </label>
                );
              })}
            </fieldset>
          )}
        </>
      )}
    </article>
  );
}
