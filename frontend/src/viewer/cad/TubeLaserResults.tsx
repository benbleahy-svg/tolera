/**
 * Tube-Laser Interrogation Results (M4.6) — the classified stock profile
 * (`analyze_tube_laser`), its section dims, and the laser cut metrics.
 * An end cut beyond the angled-cut threshold means secondary machining —
 * flagged, never auto-costed (DFM: `machining_required`). German-first.
 */
import { useTranslation } from 'react-i18next';

import type { InterrogationFeature, TubeLaserScalars } from '../../parts/api';
import { formatLength, type DisplayOptions } from './measureFormat';

export function TubeLaserResults({
  scalars,
  features,
  displayOpts,
}: {
  scalars: TubeLaserScalars;
  features: InterrogationFeature[];
  displayOpts: DisplayOptions;
}) {
  const { t } = useTranslation();
  const angledCuts = features.filter((f) => f.name === 'angled_cut').length;
  const countersinks = features.filter((f) => f.name === 'countersink').length;
  return (
    <section className="cad-readout-block cad-tube-results">
      <h3>{t('viewer.tube_title')}</h3>
      <dl>
        <div>
          <dt>{t('viewer.tube_profile')}</dt>
          <dd>{t(`viewer.tube_profile_${scalars.stock_type}`)}</dd>
        </div>
        <div>
          <dt>{t('viewer.tube_section')}</dt>
          <dd>
            {scalars.stock_type === 'round' && scalars.diameter != null
              ? `⌀ ${formatLength(scalars.diameter, displayOpts)}`
              : scalars.width != null && scalars.height != null
                ? `${formatLength(scalars.width, displayOpts)} × ${formatLength(
                    scalars.height,
                    displayOpts,
                  )}`
                : '—'}
          </dd>
        </div>
        {scalars.thickness != null && (
          <div>
            <dt>{t('viewer.tube_wall_thickness')}</dt>
            <dd>{formatLength(scalars.thickness, displayOpts)}</dd>
          </div>
        )}
        {scalars.length != null && (
          <div>
            <dt>{t('viewer.tube_length')}</dt>
            <dd>{formatLength(scalars.length, displayOpts)}</dd>
          </div>
        )}
        {scalars.total_cut_length != null && (
          <div>
            <dt>{t('viewer.tube_cut_length')}</dt>
            <dd>{formatLength(scalars.total_cut_length, displayOpts)}</dd>
          </div>
        )}
        {scalars.pierce_count != null && (
          <div>
            <dt>{t('viewer.tube_pierce_count')}</dt>
            <dd>{scalars.pierce_count}</dd>
          </div>
        )}
        {angledCuts > 0 && (
          <div>
            <dt>{t('viewer.tube_angled_cuts')}</dt>
            <dd>{angledCuts}</dd>
          </div>
        )}
        {countersinks > 0 && (
          <div>
            <dt>{t('viewer.tube_countersinks')}</dt>
            <dd>{countersinks}</dd>
          </div>
        )}
      </dl>
      {scalars.machining_required === true && (
        <p role="note" className="cad-tube-machining">
          {t('viewer.tube_machining_hint')}
        </p>
      )}
    </section>
  );
}
