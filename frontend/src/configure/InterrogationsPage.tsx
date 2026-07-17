/**
 * Configure → Interrogations (M4.7, spec #interrogations-config): the org's
 * DFM profiles — per Core-4 family, every catalogued warning with its
 * `should_detect_*` toggle and threshold inputs (metric, shop-calibratable).
 * Always-on warnings render locked (no toggle exists server-side); warnings
 * the v1 OCCT engine cannot evaluate carry a "v2/Spatial" badge — listed,
 * never silently dropped (a missing feature is a missing review signal).
 * Material-specific profile binding arrives with M4.8.
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '../api/client';
import {
  useConfigureApi,
  type DfmFamilyCatalogOut,
  type InterrogationProfileOut,
  type InterrogationsConfigOut,
} from './api';

/** Unit hint per threshold field (metric-native storage — CLAUDE.md §5).
 * xt = multiple of material thickness (unit-agnostic); ratio fields unitless. */
const FIELD_UNITS: Record<string, string> = {
  smallest_cutout_size: 'xt',
  close_cutouts_threshold: 'xt',
  cutout_edge_proximity: 'xt',
  countersink_bore_proximity_threshold: 'xt',
  countersink_bore_edge_proximity_threshold: 'xt',
  cut_near_bend_threshold: 'xt',
  tight_curl_threshold: 'xt',
  curl_near_bend_threshold: 'xt',
  tight_hem_threshold: 'xt',
  short_hem_threshold: 'xt',
  hem_near_bend_threshold: 'xt',
  max_bend_radius: 'xt',
  min_bend_radius: 'xt',
  thin_bend_relief_threshold: 'xt',
  shallow_bend_relief_threshold: 'xt',
  min_flange_length: 'xt',
  short_flange_threshold: 'L:t',
  close_bends_same_orientation_threshold: 'xt',
  close_bends_opposite_orientation_threshold: 'xt',
  press_length: 'mm',
  max_length: 'mm',
  max_width: 'mm',
  max_height: 'mm',
  max_unfolded_length: 'mm',
  max_unfolded_width: 'mm',
  max_part_length: 'mm',
  max_part_width: 'mm',
  max_part_height: 'mm',
  max_part_diameter: 'mm',
  max_tool_diameter: 'mm',
  small_internal_radius_threshold: 'mm',
  small_hole_diameter: 'mm',
  slanted_hole_angle_threshold: 'deg',
  steep_profile_angle_threshold: 'deg',
  max_angled_cut_threshold: 'deg',
  close_countersinks_threshold: 'xt',
  countersink_edge_proximity_threshold: 'xt',
};

function fieldLabel(field: string): string {
  const unit = FIELD_UNITS[field];
  return unit ? `${field} (${unit})` : field;
}

function FamilySection({
  catalog,
  profile,
  onSave,
}: {
  catalog: DfmFamilyCatalogOut;
  profile: InterrogationProfileOut;
  onSave: (profileId: string, inputs: Record<string, number | boolean>) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [inputs, setInputs] = useState<Record<string, number | boolean>>(profile.inputs);
  const [dirty, setDirty] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const set = (key: string, value: number | boolean) => {
    setInputs((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
    setNote(null);
  };

  const save = () => {
    void onSave(profile.id, inputs)
      .then(() => {
        setDirty(false);
        setNote(t('configure.interrogation_saved'));
      })
      .catch((e: unknown) => {
        setNote(
          `${t('configure.interrogation_save_failed')}: ${
            e instanceof ApiError ? e.message : String(e)
          }`,
        );
      });
  };

  return (
    <section className="interrogation-family">
      <h2>
        {t(`dfm.family.${catalog.family}`, { defaultValue: catalog.family })}
        <span className="interrogation-profile-name"> — {profile.name}</span>
      </h2>
      <table>
        <thead>
          <tr>
            <th>{t('configure.interrogation_warning')}</th>
            <th>{t('configure.interrogation_enabled')}</th>
            <th>{t('configure.interrogation_thresholds')}</th>
          </tr>
        </thead>
        <tbody>
          {catalog.warnings.map((w) => {
            const enabled =
              w.toggle == null ? true : Boolean(inputs[w.toggle] ?? w.toggle_default);
            const localizedName = t(`dfm.names.${w.type}`, { defaultValue: w.type });
            return (
              <tr key={w.type} className={w.v1_supported ? undefined : 'interrogation-v2-row'}>
                <td>
                  <span title={t(`dfm.detects.${w.type}`, { defaultValue: w.detects })}>
                    {t(`dfm.names.${w.type}`, { defaultValue: w.type })}
                  </span>
                  {w.always_on && (
                    <span className="interrogation-badge interrogation-always-on">
                      {t('configure.interrogation_always_on')}
                    </span>
                  )}
                  {!w.v1_supported && (
                    <span className="interrogation-badge interrogation-v2">
                      {t('configure.interrogation_v2')}
                    </span>
                  )}
                </td>
                <td>
                  {w.toggle == null ? (
                    <input
                      type="checkbox"
                      checked
                      disabled
                      aria-label={`${localizedName} ${t(
                        w.always_on
                          ? 'configure.interrogation_always_on'
                          : 'configure.interrogation_not_toggleable',
                      )}`}
                    />
                  ) : (
                    <input
                      type="checkbox"
                      checked={enabled}
                      aria-label={`${localizedName} ${t('configure.interrogation_enabled')}`}
                      onChange={(e) => set(w.toggle as string, e.target.checked)}
                    />
                  )}
                </td>
                <td>
                  {w.threshold_fields.map((field) => (
                    <label key={field} className="interrogation-threshold">
                      <span>{fieldLabel(field)}</span>
                      {/* Semi-controlled: an in-progress edit (empty box) must
                          not be snapped back by the state value; only valid
                          positive numbers commit (the API rejects the rest). */}
                      <input
                        type="number"
                        step="any"
                        min="0"
                        defaultValue={String(inputs[field] ?? catalog.defaults[field] ?? '')}
                        aria-label={field}
                        onChange={(e) => {
                          const parsed = Number(e.target.value);
                          if (Number.isFinite(parsed) && parsed > 0) set(field, parsed);
                        }}
                        onBlur={(e) => {
                          // an uncommitted edit (empty/zero/negative) snaps
                          // back to the value that will actually be saved
                          const committed = inputs[field] ?? catalog.defaults[field] ?? '';
                          if (e.target.value !== String(committed)) {
                            e.target.value = String(committed);
                          }
                        }}
                      />
                    </label>
                  ))}
                </td>
              </tr>
            );
          })}
          {Object.keys(catalog.defaults)
            .filter(
              (key) =>
                typeof catalog.defaults[key] === 'boolean' &&
                !catalog.warnings.some((w) => w.toggle === key),
            )
            .map((key) => (
              <tr key={key}>
                <td>{t(`dfm.fields.${key}`, { defaultValue: key })}</td>
                <td>
                  <input
                    type="checkbox"
                    checked={Boolean(inputs[key] ?? catalog.defaults[key])}
                    aria-label={`${key} ${t('configure.interrogation_enabled')}`}
                    onChange={(e) => set(key, e.target.checked)}
                  />
                </td>
                <td />
              </tr>
            ))}
        </tbody>
      </table>
      <div className="interrogation-actions">
        <button type="button" disabled={!dirty} onClick={save}>
          {t('configure.interrogation_save')}
        </button>
        {note != null && <span role="status">{note}</span>}
      </div>
    </section>
  );
}

export function InterrogationsPage() {
  const { t } = useTranslation();
  const api = useConfigureApi();
  const [config, setConfig] = useState<InterrogationsConfigOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getInterrogationsConfig()
      .then(setConfig)
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : String(e));
      });
  }, [api]);

  const onSave = useCallback(
    async (profileId: string, inputs: Record<string, number | boolean>) => {
      const updated = await api.updateInterrogationProfile(profileId, inputs);
      setConfig((prev) =>
        prev == null
          ? prev
          : {
              ...prev,
              profiles: prev.profiles.map((p) => (p.id === updated.id ? updated : p)),
            },
      );
    },
    [api],
  );

  if (error != null) return <p role="alert">{error}</p>;
  if (config == null) return null;

  return (
    <main className="configure-page interrogations-page">
      <nav className="est-subnav">
        <Link to="/configure">{t('configure.custom_tables')}</Link>
        <Link to="/configure/pricing">{t('configure.pricing')}</Link>
        <Link to="/configure/operations">{t('configure.operations')}</Link>
        <Link to="/configure/rules">{t('configure.rules')}</Link>
        <span aria-current="page">{t('configure.interrogations')}</span>
      </nav>
      <h1>{t('configure.interrogations')}</h1>
      <p className="configure-hint">{t('configure.interrogations_hint')}</p>
      {config.catalog.map((catalog) => {
        const profile = config.profiles.find((p) => p.family === catalog.family);
        if (profile == null) return null;
        return (
          <FamilySection
            key={catalog.family}
            catalog={catalog}
            profile={profile}
            onSave={onSave}
          />
        );
      })}
    </main>
  );
}
