/**
 * Tolera Source — in-context fastener availability + pricing (M6.7, spec `#collab`
 * "Supplier sourcing integrations").
 *
 * Opened from a purchased component's row menu in the assembly. It shows the
 * supplier's stock, an inventory dot per make-quantity, price-by-quantity, and
 * SEND RFQ — without leaving the quote.
 *
 * Deliberately read-only against costing: the supplier price is displayed, never
 * written back to the library or the component. Applying an outside price stays
 * the vendor-quotes Apply path, so there is one price-application code path
 * (spec `#sourcing-adapters` → E4-d freeze).
 *
 * A supplier outage renders a badge, not an error page — `degraded` is a normal
 * answer and the estimator keeps costing.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { formatMinor } from '../portal/money';
import { useSourcingApi, type AvailabilityOut, type AvailabilityStatus } from './api';

const DOT: Record<AvailabilityStatus, string> = {
  available: '🟢',
  at_risk: '🟡',
  insufficient: '🔴',
  unknown: '❓',
};

export function ToleraSourcePanel({
  purchasedComponentId,
  partName,
  quantities,
  onClose,
}: {
  purchasedComponentId: string;
  partName: string;
  /** The line's make quantities — the columns the estimator already reasons in. */
  quantities: number[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const api = useSourcingApi();
  const [result, setResult] = useState<AvailabilityOut | null>(null);
  const [failed, setFailed] = useState(false);
  const [sending, setSending] = useState(false);
  const [sentReference, setSentReference] = useState<string | null>(null);
  const [sendFailed, setSendFailed] = useState(false);

  const breaks = quantities.length > 0 ? quantities : [1];

  useEffect(() => {
    let cancelled = false;
    api
      .availability(purchasedComponentId, breaks)
      .then((res) => {
        if (!cancelled) setResult(res);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
    // breaks is derived from `quantities`; joining keeps the effect from
    // refiring on every render just because the array identity changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, purchasedComponentId, breaks.join(',')]);

  const item = result?.item;
  const degraded = failed || result?.degraded === true;

  return (
    <div className="est-modal-backdrop" role="dialog" aria-modal="true">
      <div className="est-modal src-panel">
        <header>
          <h3>{t('sourcing.title')}</h3>
          <button type="button" aria-label={t('common.close')} onClick={onClose}>
            ×
          </button>
        </header>

        <p className="src-part">{partName}</p>

        {degraded && (
          <p className="src-degraded" role="status">
            {t('sourcing.degraded')}
          </p>
        )}

        {!degraded && item && !item.found && (
          <p className="src-not-found" role="status">
            {t('sourcing.not_found', { partNumber: item.oem_part_number })}
          </p>
        )}

        {!degraded && item?.found && (
          <>
            <p className="src-stock">
              {t('sourcing.stock', { qty: item.quantity_available ?? 0 })}
              {item.lead_time_days != null &&
                ` · ${t('sourcing.lead_time', { days: item.lead_time_days })}`}
            </p>
            <table className="src-breaks">
              <thead>
                <tr>
                  <th scope="col">{t('sourcing.quantity')}</th>
                  <th scope="col">{t('sourcing.unit_price')}</th>
                  <th scope="col">{t('sourcing.extended_price')}</th>
                  <th scope="col">{t('sourcing.availability')}</th>
                </tr>
              </thead>
              <tbody>
                {item.quotes.map((quote) => (
                  <tr key={quote.quantity}>
                    <td className="est-num">{quote.quantity}</td>
                    <td className="est-num">
                      {formatMinor(quote.unit_price_minor, item.currency)}
                    </td>
                    <td className="est-num">
                      {formatMinor(quote.extended_price_minor, item.currency)}
                    </td>
                    <td>
                      <span aria-hidden="true">{DOT[quote.status]}</span>{' '}
                      {t(`sourcing.status.${quote.status}`)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {/* The price is information, not a costing input — say so, so nobody
                assumes the quote just repriced itself. */}
            <p className="src-note">{t('sourcing.suggestion_note')}</p>
          </>
        )}

        {sentReference && (
          <p className="src-sent" role="status">
            {t('sourcing.rfq_sent', { reference: sentReference })}
          </p>
        )}
        {sendFailed && (
          <p className="src-send-failed" role="alert">
            {t('sourcing.rfq_failed')}
          </p>
        )}

        <footer>
          <button type="button" onClick={onClose}>
            {t('common.close')}
          </button>
          <button
            type="button"
            className="est-primary"
            disabled={sending || sentReference != null}
            onClick={async () => {
              setSending(true);
              setSendFailed(false);
              try {
                const res = await api.sendRfq({
                  purchased_component_ids: [purchasedComponentId],
                  quantities: breaks,
                });
                setSentReference(res.reference);
              } catch {
                setSendFailed(true);
              } finally {
                setSending(false);
              }
            }}
          >
            {t('sourcing.send_rfq')}
          </button>
        </footer>
      </div>
    </div>
  );
}
