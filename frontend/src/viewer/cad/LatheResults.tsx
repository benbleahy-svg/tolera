/**
 * Lathe Interrogation Results (M4.5) — the v2.15 attributes-only readout:
 * recommended cylindrical stock + setups (`analyze_lathe`), with the viewer
 * feature counts the DemoN/04 tree shows (External Cut / Internal Cut /
 * Setup / Lathe Stock). Live-tooling callouts (off-axis holes, asymmetric
 * faces) are FLAGGED, never auto-costed — the note says so. German-first.
 */
import { useTranslation } from 'react-i18next';

import type { InterrogationFeature, LatheScalars } from '../../parts/api';
import { formatLength, type DisplayOptions } from './measureFormat';

export function LatheResults({
  scalars,
  features,
  displayOpts,
}: {
  scalars: LatheScalars;
  features: InterrogationFeature[];
  displayOpts: DisplayOptions;
}) {
  const { t } = useTranslation();
  const count = (name: string) => features.filter((f) => f.name === name).length;
  const externalCuts = count('external_cut');
  const internalCuts = count('internal_cut');
  const offAxisHoles = count('off_axis_hole');
  const asymmetric = features.find((f) => f.name === 'asymmetric_cavity');
  const asymmetricFaces =
    asymmetric != null ? Number(asymmetric.properties.face_count) : 0;
  const liveTooling = offAxisHoles > 0 || asymmetricFaces > 0;
  return (
    <section className="cad-readout-block cad-lathe-results">
      <h3>{t('viewer.lathe_title')}</h3>
      <dl>
        <div>
          <dt>{t('viewer.lathe_stock')}</dt>
          <dd>
            {'⌀ '}
            {formatLength(2 * scalars.stock_radius, displayOpts)}
            {' × '}
            {formatLength(scalars.stock_length, displayOpts)}
          </dd>
        </div>
        <div>
          <dt>{t('viewer.lathe_setups')}</dt>
          <dd>{scalars.setup_count}</dd>
        </div>
        <div>
          <dt>{t('viewer.lathe_external_cuts')}</dt>
          <dd>{externalCuts}</dd>
        </div>
        <div>
          <dt>{t('viewer.lathe_internal_cuts')}</dt>
          <dd>{internalCuts}</dd>
        </div>
        {offAxisHoles > 0 && (
          <div>
            <dt>{t('viewer.lathe_off_axis')}</dt>
            <dd>{offAxisHoles}</dd>
          </div>
        )}
        {asymmetricFaces > 0 && (
          <div>
            <dt>{t('viewer.lathe_asymmetric')}</dt>
            <dd>{asymmetricFaces}</dd>
          </div>
        )}
      </dl>
      {liveTooling && (
        <p role="note" className="cad-lathe-live-tooling">
          {t('viewer.lathe_live_tooling_hint')}
        </p>
      )}
    </section>
  );
}
