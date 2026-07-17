/**
 * Configure → Interrogations (M4.7/M4.8, spec #interrogations-config): the
 * org's DFM profiles — per Core-4 family, every catalogued warning with its
 * `should_detect_*` toggle and threshold inputs (metric, shop-calibratable).
 * Always-on warnings render locked (no toggle exists server-side); warnings
 * the v1 OCCT engine cannot evaluate carry a "v2/Spatial" badge — listed,
 * never silently dropped (a missing feature is a missing review signal).
 *
 * M4.8 authoring (KB custom-interrogations): create named profiles per
 * family, bind them to a material class / family / material and/or operation
 * defs — the engine resolves the most-specific match for a part's material —
 * and delete them (the seeded default is undeletable). Saving op links may
 * return the advisory duplicate-dispatch ⚠️.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '../api/client';
import { useEstimatingApi } from '../estimating/api';
import type { ClassNode } from '../estimating/types';
import {
  useConfigureApi,
  type DfmFamilyCatalogOut,
  type DispatchWarningOut,
  type InterrogationProfileOut,
  type InterrogationProfileUpdate,
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

interface OpDefOption {
  id: string;
  name: string;
}

type LookupState = 'loading' | 'ready' | 'failed';

type SaveProfile = (
  profileId: string,
  body: InterrogationProfileUpdate,
) => Promise<DispatchWarningOut[]>;

/** Material class/family/material + operation-def binding (M4.8). Link
 * changes save immediately — a link is a small, atomic act, unlike the
 * threshold table's batched Save. The editor locks while a save is in
 * flight (each response replaces the whole profile, so concurrent PUTs
 * could land out of order) and stays disabled until BOTH lookup lists have
 * loaded — while they are pending or failed, existing bindings would render
 * blank and a save could silently overwrite them (options missing ≠ links
 * cleared). */
function LinkEditor({
  profile,
  materials,
  opDefs,
  lookupState,
  onSave,
  onNote,
}: {
  profile: InterrogationProfileOut;
  materials: ClassNode[];
  opDefs: OpDefOption[];
  lookupState: LookupState;
  onSave: SaveProfile;
  onNote: (note: string | null, warnings: DispatchWarningOut[]) => void;
}) {
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);

  const save = (body: InterrogationProfileUpdate) => {
    setSaving(true);
    void onSave(profile.id, body)
      .then((warnings) => {
        onNote(t('configure.interrogation_saved'), warnings);
      })
      .catch((e: unknown) => {
        onNote(
          `${t('configure.interrogation_save_failed')}: ${
            e instanceof ApiError ? e.message : String(e)
          }`,
          [],
        );
      })
      .finally(() => {
        setSaving(false);
      });
  };

  if (lookupState === 'failed') {
    return (
      <p className="interrogation-links" role="alert">
        {t('configure.interrogation_lookups_failed')}
      </p>
    );
  }

  const disabled = saving || lookupState !== 'ready';
  const families = materials.flatMap((c) => c.families);
  const allMaterials = families.flatMap((f) => f.materials);
  const none = t('configure.interrogation_link_none');

  return (
    <div className="interrogation-links">
      <label>
        <span>{t('configure.interrogation_link_class')}</span>
        <select
          value={profile.material_class_id ?? ''}
          disabled={disabled}
          onChange={(e) => save({ material_class_id: e.target.value || null })}
        >
          <option value="">{none}</option>
          {materials.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>{t('configure.interrogation_link_family')}</span>
        <select
          value={profile.material_family_id ?? ''}
          disabled={disabled}
          onChange={(e) => save({ material_family_id: e.target.value || null })}
        >
          <option value="">{none}</option>
          {families.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>{t('configure.interrogation_link_material')}</span>
        <select
          value={profile.material_id ?? ''}
          disabled={disabled}
          onChange={(e) => save({ material_id: e.target.value || null })}
        >
          <option value="">{none}</option>
          {allMaterials.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>{t('configure.interrogation_link_ops')}</span>
        <select
          multiple
          size={Math.min(6, Math.max(3, opDefs.length))}
          value={profile.operation_def_ids}
          disabled={disabled}
          onChange={(e) =>
            save({
              operation_def_ids: Array.from(e.target.selectedOptions, (o) => o.value),
            })
          }
        >
          {opDefs.map((op) => (
            <option key={op.id} value={op.id}>
              {op.name}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

function FamilySection({
  catalog,
  profile,
  materials,
  opDefs,
  lookupState,
  onSave,
  onDelete,
}: {
  catalog: DfmFamilyCatalogOut;
  profile: InterrogationProfileOut;
  materials: ClassNode[];
  opDefs: OpDefOption[];
  lookupState: LookupState;
  onSave: SaveProfile;
  onDelete: (profileId: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [inputs, setInputs] = useState<Record<string, number | boolean>>(profile.inputs);
  const [dirty, setDirty] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [dispatchWarnings, setDispatchWarnings] = useState<DispatchWarningOut[]>([]);
  // Every edit bumps the revision; a save response only clears the dirty
  // flag when no edit landed while the request was in flight — a late
  // response must never hide unsaved edits behind a disabled Save.
  const editRev = useRef(0);

  const set = (key: string, value: number | boolean) => {
    editRev.current += 1;
    setInputs((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
    setNote(null);
  };

  const onNote = (nextNote: string | null, warnings: DispatchWarningOut[]) => {
    setNote(nextNote);
    setDispatchWarnings(warnings);
  };

  const save = () => {
    const submittedRev = editRev.current;
    void onSave(profile.id, { inputs })
      .then((warnings) => {
        if (editRev.current === submittedRev) setDirty(false);
        onNote(t('configure.interrogation_saved'), warnings);
      })
      .catch((e: unknown) => {
        setNote(
          `${t('configure.interrogation_save_failed')}: ${
            e instanceof ApiError ? e.message : String(e)
          }`,
        );
      });
  };

  const remove = () => {
    // Destroying a profile drops tuned thresholds + links irrecoverably —
    // unlike everything else on this page, it deserves a confirm step.
    if (!window.confirm(t('configure.interrogation_delete_confirm', { name: profile.name }))) {
      return;
    }
    void onDelete(profile.id).catch((e: unknown) => {
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
        {profile.is_default && (
          <span className="interrogation-badge interrogation-default">
            {t('configure.interrogation_default')}
          </span>
        )}
      </h2>
      {!profile.is_default && (
        <LinkEditor
          profile={profile}
          materials={materials}
          opDefs={opDefs}
          lookupState={lookupState}
          onSave={onSave}
          onNote={onNote}
        />
      )}
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
                        min="0.000001"
                        defaultValue={String(inputs[field] ?? catalog.defaults[field] ?? '')}
                        aria-label={`${profile.name} ${field}`}
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
        {!profile.is_default && (
          <button type="button" className="interrogation-delete" onClick={remove}>
            {t('configure.interrogation_delete')}
          </button>
        )}
        {note != null && <span role="status">{note}</span>}
      </div>
      {dispatchWarnings.length > 0 && (
        <ul className="interrogation-dispatch-warnings" role="alert">
          {dispatchWarnings.map((w) => (
            <li key={`${w.other_profile_id}-${w.process_id}`}>
              ⚠️{' '}
              {t('configure.interrogation_duplicate_dispatch', {
                other: w.other_profile_name,
                process: w.process_name,
              })}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CreateProfileForm({
  family,
  onCreate,
}: {
  family: string;
  onCreate: (name: string, family: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [note, setNote] = useState<string | null>(null);
  const familyLabel = t(`dfm.family.${family}`, { defaultValue: family });

  const create = () => {
    if (name.trim() === '') return;
    void onCreate(name.trim(), family)
      .then(() => {
        setName('');
        setNote(null);
      })
      .catch((e: unknown) => {
        setNote(e instanceof ApiError ? e.message : String(e));
      });
  };

  return (
    <div className="interrogation-create">
      <input
        type="text"
        value={name}
        placeholder={t('configure.interrogation_new_name')}
        aria-label={`${familyLabel} ${t('configure.interrogation_new_name')}`}
        onChange={(e) => setName(e.target.value)}
      />
      <button type="button" disabled={name.trim() === ''} onClick={create}>
        {t('configure.interrogation_new', { family: familyLabel })}
      </button>
      {note != null && <span role="status">{note}</span>}
    </div>
  );
}

export function InterrogationsPage() {
  const { t } = useTranslation();
  const api = useConfigureApi();
  const estimatingApi = useEstimatingApi();
  const [config, setConfig] = useState<InterrogationsConfigOut | null>(null);
  const [materials, setMaterials] = useState<ClassNode[]>([]);
  const [opDefs, setOpDefs] = useState<OpDefOption[]>([]);
  const [lookupState, setLookupState] = useState<LookupState>('loading');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getInterrogationsConfig()
      .then(setConfig)
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : String(e));
      });
  }, [api]);

  useEffect(() => {
    // Link-picker data; the threshold tables work without it — but the link
    // editors stay DISABLED until both lists are in (and lock out on
    // failure): rendered empty, existing links would look cleared and could
    // be overwritten.
    Promise.all([
      estimatingApi.materialTree().then(setMaterials),
      api.listOperationDefs('').then((defs) => {
        setOpDefs(defs.map((d) => ({ id: d.id, name: d.name })));
      }),
    ])
      .then(() => {
        setLookupState('ready');
      })
      .catch(() => {
        setLookupState('failed');
      });
  }, [api, estimatingApi]);

  const onSave = useCallback<SaveProfile>(
    async (profileId, body) => {
      const saved = await api.updateInterrogationProfile(profileId, body);
      const { warnings, ...profile } = saved;
      setConfig((prev) =>
        prev == null
          ? prev
          : {
              ...prev,
              profiles: prev.profiles.map((p) => (p.id === profile.id ? profile : p)),
            },
      );
      return warnings;
    },
    [api],
  );

  const onCreate = useCallback(
    async (name: string, family: string) => {
      const created = await api.createInterrogationProfile(name, family);
      setConfig((prev) =>
        prev == null ? prev : { ...prev, profiles: [...prev.profiles, created] },
      );
    },
    [api],
  );

  const onDelete = useCallback(
    async (profileId: string) => {
      await api.deleteInterrogationProfile(profileId);
      setConfig((prev) =>
        prev == null
          ? prev
          : { ...prev, profiles: prev.profiles.filter((p) => p.id !== profileId) },
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
        // Default first, then variants oldest-first (mirrors resolution order).
        const profiles = config.profiles.filter((p) => p.family === catalog.family);
        profiles.sort((a, b) => Number(b.is_default) - Number(a.is_default));
        if (profiles.length === 0) return null;
        return (
          <div key={catalog.family} className="interrogation-family-group">
            {profiles.map((profile) => (
              <FamilySection
                key={profile.id}
                catalog={catalog}
                profile={profile}
                materials={materials}
                opDefs={opDefs}
                lookupState={lookupState}
                onSave={onSave}
                onDelete={onDelete}
              />
            ))}
            <CreateProfileForm family={catalog.family} onCreate={onCreate} />
          </div>
        );
      })}
    </main>
  );
}
