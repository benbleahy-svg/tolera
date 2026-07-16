/**
 * Interrogation status + core-dims readout (M4.1) — the Merkmale tab's
 * content until the per-family feature recognizers land (M4.2+).
 *
 * Polls the latest run while it is queued/running (the spec's
 * "interrogating…" state) and renders the GeometryService dimensions block
 * once it succeeds. Formatting reuses the viewer's display options, so the
 * metric-first unit toggle and precision apply here too (DACH §6).
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  usePartsApi,
  type InterrogationStatus,
  type SheetMetalScalars,
} from '../../parts/api';
import {
  formatArea,
  formatLength,
  formatMass,
  formatVolume,
  type DisplayOptions,
} from './measureFormat';
import { SheetMetalResults } from './SheetMetalResults';

/** Default poll cadence while a run is in flight. */
export const POLL_INTERVAL_MS = 3000;

export function InterrogationPanel({
  partId,
  displayOpts,
  pollIntervalMs = POLL_INTERVAL_MS,
}: {
  partId: string;
  displayOpts: DisplayOptions;
  /** Poll cadence while a run is in flight; tests shrink it. */
  pollIntervalMs?: number;
}) {
  const api = usePartsApi();
  const { t } = useTranslation();
  const [status, setStatus] = useState<InterrogationStatus | null>(null);
  const [failedToLoad, setFailedToLoad] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = async () => {
      try {
        const next = await api.getInterrogation(partId);
        if (cancelled) return;
        setStatus(next);
        setFailedToLoad(false);
        if (next.status === 'queued' || next.status === 'running') {
          timer = setTimeout(poll, pollIntervalMs);
        }
      } catch {
        if (!cancelled) {
          // Transient fetch failures must not strand the panel: surface the
          // load-failed note but keep polling — the run continues server-side.
          setFailedToLoad(true);
          timer = setTimeout(poll, pollIntervalMs);
        }
      }
    };
    void poll();
    return () => {
      cancelled = true;
      if (timer != null) clearTimeout(timer);
    };
  }, [api, partId, pollIntervalMs]);

  if (failedToLoad) {
    return <p className="cad-features-pending">{t('viewer.interrogation_load_failed')}</p>;
  }
  if (status == null) return null;

  if (status.status === 'queued' || status.status === 'running') {
    return (
      <p role="status" className="cad-interrogating">
        {t('viewer.interrogating')}
      </p>
    );
  }
  if (status.status === 'failed') {
    const code = status.run?.error_code;
    return (
      <p role="status" className="cad-interrogation-failed">
        {code === 'multi_body'
          ? t('viewer.interrogation_failed_multi_body')
          : t('viewer.interrogation_failed')}
      </p>
    );
  }
  if (status.status === 'none' || status.run?.result == null) {
    return <p className="cad-features-pending">{t('viewer.interrogation_none')}</p>;
  }

  const dims = status.run.result.dimensions;
  const scalars = status.run.result.family_scalars;
  const sheetMetal =
    status.run.result.family === 'SHEET_METAL' && scalars != null && 'thickness' in scalars
      ? (scalars as SheetMetalScalars)
      : null;
  return (
    <div className="cad-interrogation-result">
      {sheetMetal != null && (
        <SheetMetalResults scalars={sheetMetal} displayOpts={displayOpts} />
      )}
      <section className="cad-readout-block">
        <h3>{t('viewer.interrogation_dims')}</h3>
        <dl>
          <div>
            <dt>{t('viewer.interrogation_size')}</dt>
            <dd>
              {[dims.size_x, dims.size_y, dims.size_z]
                .map((v) => formatLength(v, displayOpts))
                .join(' × ')}
            </dd>
          </div>
          <div>
            <dt>{t('viewer.interrogation_area')}</dt>
            <dd>{formatArea(dims.area, displayOpts)}</dd>
          </div>
          <div>
            <dt>{t('viewer.interrogation_volume')}</dt>
            <dd>{formatVolume(dims.volume, displayOpts)}</dd>
          </div>
          <div>
            <dt>{t('viewer.interrogation_weight')}</dt>
            <dd>{dims.weight == null ? '—' : formatMass(dims.weight / 1000, displayOpts)}</dd>
          </div>
        </dl>
      </section>
      {/* Families without a recognizer yet (M4.4+) keep the pending note. */}
      {sheetMetal == null && (
        <p className="cad-features-pending">{t('viewer.interrogation_features_pending')}</p>
      )}
    </div>
  );
}
