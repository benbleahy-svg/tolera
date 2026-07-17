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
  type LatheScalars,
  type MillingScalars,
  type SheetMetalScalars,
  type TubeLaserScalars,
} from '../../parts/api';
import {
  formatArea,
  formatLength,
  formatMass,
  formatVolume,
  type DisplayOptions,
} from './measureFormat';
import { DfmWarnings } from './DfmWarnings';
import { LatheResults } from './LatheResults';
import { MillingResults } from './MillingResults';
import { SheetMetalResults } from './SheetMetalResults';
import { TubeLaserResults } from './TubeLaserResults';

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
  const milling =
    status.run.result.family === 'MILLING' && scalars != null && 'setup_count' in scalars
      ? (scalars as MillingScalars)
      : null;
  const lathe =
    status.run.result.family === 'LATHE' && scalars != null && 'stock_radius' in scalars
      ? (scalars as LatheScalars)
      : null;
  const tubeLaser =
    status.run.result.family === 'TUBE_LASER' && scalars != null && 'stock_type' in scalars
      ? (scalars as TubeLaserScalars)
      : null;
  return (
    <div className="cad-interrogation-result">
      {/* Manufacturability Warnings (M4.7) — DemoN pins this list in the
          right panel; only fired warnings appear. */}
      {status.run.result.family != null && (
        <DfmWarnings
          family={status.run.result.family}
          feedback={status.run.result.feedback ?? []}
          displayOpts={displayOpts}
        />
      )}
      {sheetMetal != null && (
        <SheetMetalResults scalars={sheetMetal} displayOpts={displayOpts} />
      )}
      {milling != null && (
        <MillingResults
          scalars={milling}
          confidence={status.run.result.confidence}
          displayOpts={displayOpts}
        />
      )}
      {lathe != null && (
        <LatheResults
          scalars={lathe}
          features={status.run.result.features ?? []}
          displayOpts={displayOpts}
        />
      )}
      {tubeLaser != null && tubeLaser.stock_type !== 'incompatible' && (
        <TubeLaserResults
          scalars={tubeLaser}
          features={status.run.result.features ?? []}
          displayOpts={displayOpts}
        />
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
      {/* A LATHE run that returned no scalars DID run — the recognizer
          rejected the body as not turnable (the designed honest path), which
          is not the same as "recognition not shipped yet". */}
      {lathe == null && status.run.result.family === 'LATHE' && (
        <p className="cad-features-pending">{t('viewer.lathe_not_turnable')}</p>
      )}
      {/* Same honest path for TUBE_LASER: the run classified the body as
          matching none of the 5 stock profiles — nothing is fabricated. */}
      {tubeLaser != null && tubeLaser.stock_type === 'incompatible' && (
        <p className="cad-features-pending">{t('viewer.tube_incompatible')}</p>
      )}
      {/* Families without a recognizer (Wire EDM / Cast / Additive — post-
          pilot) keep the pending note. */}
      {sheetMetal == null && milling == null && lathe == null && tubeLaser == null &&
        status.run.result.family !== 'LATHE' && (
          <p className="cad-features-pending">{t('viewer.interrogation_features_pending')}</p>
        )}
    </div>
  );
}
