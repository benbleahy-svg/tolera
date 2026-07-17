/**
 * Manufacturability Warnings (M4.7) — the viewer right-panel list the DemoN
 * frames pin: family group label, one row per fired warning with severity dot
 * + localized name + count + ⓘ (the threshold that fired), expandable to
 * per-instance rows. The highlight-on-model checkbox arrives with the
 * server-mesh face ids (`geometry_refs` are empty across v1 recognizers), so
 * no dead checkbox is rendered meanwhile.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { DfmWarning } from '../../parts/api';
import { formatLength, type DisplayOptions } from './measureFormat';

/** Instance keys that are lengths in mm (formatted via the unit toggle);
 * everything else renders as a plain number/text. */
const LENGTH_KEYS = new Set([
  'radius',
  'angle_radius',
  'length',
  'depth',
  'diameter',
  'min_diameter',
  'value',
  'area',
]);

function formatInstanceValue(
  key: string,
  value: number | string | boolean | null,
  displayOpts: DisplayOptions,
): string {
  if (value == null) return '—';
  if (typeof value === 'boolean') return value ? '✓' : '—';
  if (typeof value === 'number') {
    if (key === 'angle') return `${value.toFixed(1)}°`;
    if (key === 'ratio') return value.toFixed(1);
    if (LENGTH_KEYS.has(key)) return formatLength(value, displayOpts);
    return String(value);
  }
  return String(value);
}

function thresholdSummary(w: DfmWarning): string {
  return Object.entries(w.threshold_used)
    .map(([field, value]) => `${field} = ${value}`)
    .join(' · ');
}

function WarningRow({
  warning,
  displayOpts,
}: {
  warning: DfmWarning;
  displayOpts: DisplayOptions;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const name = t(`dfm.names.${warning.type}`, { defaultValue: warning.type });
  const threshold = thresholdSummary(warning);
  return (
    <li className="dfm-warning">
      <div className="dfm-warning-row">
        <button
          type="button"
          className="dfm-expand"
          aria-expanded={expanded}
          aria-label={t('dfm.toggle_instances', { name })}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? '▾' : '▸'}
        </button>
        <span className="dfm-severity-dot" aria-hidden="true" />
        <span className="dfm-warning-name">
          {name} ({warning.count})
        </span>
        {threshold !== '' && (
          <span className="dfm-info" title={`${t('dfm.threshold')}: ${threshold}`}>
            ⓘ
          </span>
        )}
      </div>
      {expanded && (
        <ul className="dfm-instances">
          {warning.instances.map((instance, i) => (
            <li key={i}>
              {Object.entries(instance)
                .map(
                  ([key, value]) =>
                    `${t(`dfm.instance.${key}`, { defaultValue: key })}: ` +
                    formatInstanceValue(key, value, displayOpts),
                )
                .join(' · ')}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function DfmWarnings({
  family,
  feedback,
  displayOpts,
}: {
  family: string;
  feedback: DfmWarning[];
  displayOpts: DisplayOptions;
}) {
  const { t } = useTranslation();
  if (feedback.length === 0) return null;
  return (
    <section className="cad-readout-block dfm-warnings">
      <h3>{t('dfm.title')}</h3>
      <p className="dfm-family-label">{t(`dfm.family.${family}`, { defaultValue: family })}</p>
      <ul>
        {feedback.map((w) => (
          <WarningRow key={w.type} warning={w} displayOpts={displayOpts} />
        ))}
      </ul>
    </section>
  );
}
