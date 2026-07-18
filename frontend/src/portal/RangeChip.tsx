/**
 * The "available-from" price-range chip (M5.1): a compact "Verfügbar ab
 * {min}–{max} / Stk." pill derived from the quote's unit-price range.
 */

import { useTranslation } from 'react-i18next';

import { formatMoney } from './money';

export function RangeChip({
  min,
  max,
  currency,
}: {
  min: string;
  max: string;
  currency: string;
}) {
  const { t } = useTranslation();
  const range = `${formatMoney(min, currency)}–${formatMoney(max, currency)}`;
  return (
    <span className="portal-range-chip">
      {t('portal.available_from', { range })}
    </span>
  );
}
