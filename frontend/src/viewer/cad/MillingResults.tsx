/**
 * Milling Interrogation Results (M4.4) — the setups[] readout: per-setup
 * runtime + confidence from `analyze_mill3`. Low confidence is the DESIGNED
 * signal to fall back to a manual runtime override (build-plan M4.4 /
 * GEOMETRY.md §9 honest ceilings) — the block says so instead of pretending
 * the estimate is trustworthy. German-first labels, hours per KB.
 */
import { useTranslation } from 'react-i18next';

import type { MillingScalars } from '../../parts/api';
import { formatHours, type DisplayOptions } from './measureFormat';

const AXIS_LABELS: [number[], string][] = [
  [[1, 0, 0], '+X'],
  [[-1, 0, 0], '−X'],
  [[0, 1, 0], '+Y'],
  [[0, -1, 0], '−Y'],
  [[0, 0, 1], '+Z'],
  [[0, 0, -1], '−Z'],
];

function directionLabel(direction: number[]): string {
  const hit = AXIS_LABELS.find(([axis]) => axis.every((c, i) => c === direction[i]));
  return hit ? hit[1] : direction.map((c) => c.toFixed(0)).join(',');
}

export function MillingResults({
  scalars,
  confidence,
  displayOpts,
}: {
  scalars: MillingScalars;
  confidence: 'High' | 'Medium' | 'Low' | null | undefined;
  displayOpts: DisplayOptions;
}) {
  const { t } = useTranslation();
  return (
    <section className="cad-readout-block cad-milling-results">
      <h3>{t('viewer.milling_title')}</h3>
      <dl>
        <div>
          <dt>{t('viewer.milling_setups')}</dt>
          <dd>{scalars.setup_count}</dd>
        </div>
        <div>
          <dt>{t('viewer.milling_runtime')}</dt>
          <dd>{formatHours(scalars.runtime, displayOpts)}</dd>
        </div>
        <div>
          <dt>{t('viewer.milling_setup_time')}</dt>
          <dd>{formatHours(scalars.setup_time, displayOpts)}</dd>
        </div>
        {confidence != null && (
          <div>
            <dt>{t('viewer.milling_confidence')}</dt>
            <dd className={`cad-confidence cad-confidence-${confidence.toLowerCase()}`}>
              {t(`viewer.milling_confidence_${confidence.toLowerCase()}`)}
            </dd>
          </div>
        )}
      </dl>
      {scalars.setup_count > 1 && (
        <table className="cad-milling-setups">
          <thead>
            <tr>
              <th>{t('viewer.milling_setup')}</th>
              <th>{t('viewer.milling_direction')}</th>
              <th>{t('viewer.milling_runtime')}</th>
            </tr>
          </thead>
          <tbody>
            {scalars.setups.map((setup, i) => (
              <tr key={directionLabel(setup.direction)}>
                <td>{i + 1}</td>
                <td>{directionLabel(setup.direction)}</td>
                <td>{formatHours(setup.runtime, displayOpts)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {confidence === 'Low' && (
        <p role="note" className="cad-milling-low-confidence">
          {t('viewer.milling_low_confidence_hint')}
        </p>
      )}
    </section>
  );
}
