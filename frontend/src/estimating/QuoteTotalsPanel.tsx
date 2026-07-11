/**
 * Quote totals with the VAT line (M1.11, spec #dach-tax): Netto → MwSt./USt./
 * MWST at the org country's standard rate → Brutto. The API returns integer
 * minor units + explicit currency (the tier-1 money boundary); this panel is
 * the only place that turns minor units into a locale money string — de-DE
 * `1.234,56 €`, de-CH `CHF 1'234.56`.
 */

import { useTranslation } from 'react-i18next';

import type { QuoteTotals } from './types';

export function QuoteTotalsPanel({ totals }: { totals: QuoteTotals }) {
  const { t, i18n } = useTranslation();

  const locale =
    totals.currency === 'CHF' ? 'de-CH' : i18n.language === 'de' ? 'de-DE' : 'en-IE';
  const money = (minor: number): string =>
    new Intl.NumberFormat(locale, { style: 'currency', currency: totals.currency }).format(
      minor / 100,
    );
  const rate = Number(totals.vat_rate_pct).toLocaleString(locale);

  return (
    <section className="est-section" aria-label={t('pricing.quote_totals_title')}>
      <h3>{t('pricing.quote_totals_title')}</h3>
      <table className="est-table est-totals">
        <tbody>
          <tr>
            <td>{t('pricing.net_total')}</td>
            <td className="est-num">{money(totals.net_minor)}</td>
          </tr>
          <tr>
            <td>
              {totals.vat_label} ({rate} %)
            </td>
            <td className="est-num">{money(totals.vat_minor)}</td>
          </tr>
          <tr className="est-total-row">
            <td>{t('pricing.gross_total')}</td>
            <td className="est-num">{money(totals.gross_minor)}</td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}
