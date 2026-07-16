/**
 * Sheet Metal Interrogation Results (M4.2) — spec #sheetmetal, ground truth
 * DemoA/8: Sheet Thickness / Flat Surface Area / Bounding Dimensions /
 * Number of Bends, plus the flat-pattern thumbnail. Metric-first (the DACH
 * delta overrides the screenshot's inch-first display), German-first labels.
 *
 * The recognizer emits only what it measured: the unfolded dims and the
 * thumbnail are omitted for bodies outside the v1 analytic-unfold envelope.
 */
import { useTranslation } from 'react-i18next';

import type { SheetMetalScalars } from '../../parts/api';
import { formatArea, formatLength, type DisplayOptions } from './measureFormat';

type FlatPattern = NonNullable<SheetMetalScalars['flat_pattern']>;

export function SheetMetalResults({
  scalars,
  displayOpts,
}: {
  scalars: SheetMetalScalars;
  displayOpts: DisplayOptions;
}) {
  const { t } = useTranslation();
  const pattern = scalars.flat_pattern;
  return (
    <section className="cad-readout-block cad-sheetmetal-results">
      <h3>{t('viewer.sheetmetal_title')}</h3>
      {pattern != null && <FlatPatternThumb pattern={pattern} />}
      <dl>
        <div>
          <dt>{t('viewer.sheetmetal_thickness')}</dt>
          <dd>{formatLength(scalars.thickness, displayOpts)}</dd>
        </div>
        <div>
          <dt>{t('viewer.sheetmetal_flat_area')}</dt>
          <dd>{formatArea(scalars.flat_area, displayOpts)}</dd>
        </div>
        {scalars.size_x != null && scalars.size_y != null && (
          <div>
            <dt>{t('viewer.sheetmetal_unfolded')}</dt>
            <dd>
              {formatLength(scalars.size_x, displayOpts)} ×{' '}
              {formatLength(scalars.size_y, displayOpts)}
            </dd>
          </div>
        )}
        <div>
          <dt>{t('viewer.sheetmetal_bends')}</dt>
          <dd>{scalars.bend_count}</dd>
        </div>
      </dl>
    </section>
  );
}

/** Minimal flat-pattern render: the unfolded outline with dashed bend lines
 * at their developed positions (cutout outlines arrive with M4.7's punch
 * recognition). Strokes stay hairline regardless of part size. */
function FlatPatternThumb({ pattern }: { pattern: FlatPattern }) {
  const { t } = useTranslation();
  const pad = Math.max(pattern.size_x, pattern.size_y) * 0.06;
  return (
    <svg
      className="cad-flat-pattern"
      role="img"
      aria-label={t('viewer.sheetmetal_flat_pattern')}
      viewBox={`${-pad} ${-pad} ${pattern.size_x + 2 * pad} ${pattern.size_y + 2 * pad}`}
      style={{ width: '100%', maxWidth: '240px', display: 'block', margin: '0.25rem 0' }}
    >
      <rect
        x={0}
        y={0}
        width={pattern.size_x}
        height={pattern.size_y}
        fill="none"
        stroke="currentColor"
        vectorEffect="non-scaling-stroke"
      />
      {pattern.bend_lines.map((line) => (
        <line
          key={line.position}
          x1={line.position}
          y1={0}
          x2={line.position}
          y2={pattern.size_y}
          stroke="currentColor"
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </svg>
  );
}
