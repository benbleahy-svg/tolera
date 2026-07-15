/**
 * Part Setup panel: "Part fields | Found in files [N]" (M3.2 — spec #wingman
 * §2/§3/§5, #lens-accept; DemoC/02+03 ground truth).
 *
 * AI-Governor throughout (CLAUDE.md §1/§5): suggested findings render as
 * purple chips at 55 % opacity and write NOTHING until the explicit
 * Accept/Übernehmen action calls the backend — which flips the status and
 * fills the part field in one transaction. "Mark as inaccurate" / replace /
 * "Add missing extraction" persist per-tenant training labels. Per-section
 * whiteout toggles push the section's finding regions into the M2.4 whiteout
 * session state via `onLensWhiteoutsChange` (the viewer overlay renders them).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import { usePartsApi, type Part } from '../parts/api';
import {
  fillSuggestion,
  fillTarget,
  findingsBadgeCount,
  groupFindings,
  whiteoutSectionsFor,
  type Axis,
  type Chip,
  type Finding,
  type IdentityType,
  type SectionKey,
} from './lens';
import { useLensApi, type AddMissingBody } from './lens-api';
import type { WhiteoutSection } from './redact';

const POLL_MS = 1500;

interface Props {
  partId: string;
  fileId: string;
  filename: string;
  /** Lens-driven whiteout sections for the print overlay (M2.4 state). */
  onLensWhiteoutsChange?: (sections: WhiteoutSection[]) => void;
}

type Tab = 'fields' | 'found';

export function FoundInFilesPanel({ partId, fileId, filename, onLensWhiteoutsChange }: Props) {
  const { t } = useTranslation();
  const partsApi = usePartsApi();
  const lensApi = useLensApi();

  const [tab, setTab] = useState<Tab>('found');
  const [findings, setFindings] = useState<Finding[]>([]);
  const [part, setPart] = useState<Part | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [openChip, setOpenChip] = useState<string | null>(null);
  const [whiteoutOn, setWhiteoutOn] = useState<Set<SectionKey>>(new Set());
  const [addOpen, setAddOpen] = useState(false);
  const pollRef = useRef<number | null>(null);

  const reload = useCallback(() => {
    lensApi
      .listFindings(partId, fileId)
      .then(setFindings)
      .catch(() => setNotice(t('lens.load_failed')));
    partsApi
      .getPart(partId)
      .then(setPart)
      .catch(() => undefined);
  }, [lensApi, partsApi, partId, fileId, t]);

  useEffect(() => {
    reload();
    return () => {
      if (pollRef.current) window.clearTimeout(pollRef.current);
    };
  }, [reload]);

  // Lens whiteout: recompute whenever the toggles or findings change.
  useEffect(() => {
    onLensWhiteoutsChange?.(whiteoutSectionsFor(findings, [...whiteoutOn]));
  }, [findings, whiteoutOn, onLensWhiteoutsChange]);

  const sections = useMemo(() => groupFindings(findings), [findings]);
  const badge = findingsBadgeCount(findings);

  const startExtract = async () => {
    setExtracting(true);
    setNotice(null);
    try {
      const { task_id } = await lensApi.extract(partId, fileId);
      const poll = async () => {
        const status = await lensApi.extractStatus(partId, fileId, task_id);
        if (status.state === 'queued' || status.state === 'in_progress') {
          pollRef.current = window.setTimeout(() => void poll(), POLL_MS);
          return;
        }
        setExtracting(false);
        if (status.state === 'failed') setNotice(t('lens.extract_failed'));
        if (status.state === 'skipped') setNotice(t('lens.extract_skipped'));
        reload();
      };
      pollRef.current = window.setTimeout(() => void poll(), POLL_MS);
    } catch (err) {
      setExtracting(false);
      setNotice(err instanceof Error ? err.message : t('lens.extract_failed'));
    }
  };

  const runAction = async (action: () => Promise<unknown>) => {
    setNotice(null);
    try {
      await action();
      reload();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : t('lens.action_failed'));
    }
  };

  const accept = (finding: Finding, applyTo?: IdentityType | Axis) =>
    runAction(() => lensApi.acceptFinding(partId, fileId, finding.id, applyTo));
  const reject = (finding: Finding) =>
    runAction(() => lensApi.rejectFinding(partId, fileId, finding.id));
  const replace = (finding: Finding, value: string) =>
    runAction(() => lensApi.replaceFinding(partId, fileId, finding.id, value));
  const addMissing = (body: AddMissingBody) =>
    runAction(async () => {
      await lensApi.addMissing(partId, fileId, body);
      setAddOpen(false);
    });

  return (
    <aside className="lens-panel" aria-label={t('lens.part_setup')}>
      <h2>{t('lens.part_setup')}</h2>
      <p className="lens-panel-hint">{t('lens.part_setup_hint')}</p>
      <div className="lens-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'fields'}
          onClick={() => setTab('fields')}
        >
          {t('lens.tab_part_fields')}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'found'}
          onClick={() => setTab('found')}
        >
          {t('lens.tab_found_in_files')}
          <span className="lens-badge">{badge}</span>
        </button>
      </div>
      {notice && <p role="status">{notice}</p>}

      {tab === 'fields' && part && (
        <PartFieldsTab part={part} findings={findings} onAccept={accept} onSaved={reload} />
      )}

      {tab === 'found' && (
        <div className="lens-found">
          {sections.length === 0 && (
            <button type="button" disabled={extracting} onClick={() => void startExtract()}>
              {extracting ? t('lens.extracting') : t('lens.extract')}
            </button>
          )}
          {sections.map((section) => (
            <section key={section.key} className="lens-section">
              <header>
                <h3>{t(`lens.section_${section.key}`)}</h3>
                <label className="lens-whiteout-toggle">
                  {t('lens.whiteout')}
                  <input
                    type="checkbox"
                    checked={whiteoutOn.has(section.key)}
                    onChange={(e) => {
                      setWhiteoutOn((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(section.key);
                        else next.delete(section.key);
                        return next;
                      });
                    }}
                  />
                </label>
              </header>
              {section.groups.map((group) => (
                <div key={group.key} className="lens-group">
                  <span className="lens-group-label">{t(`lens.group_${group.key}`)}</span>
                  <div className="lens-chips">
                    {group.chips.map((chip) => (
                      <FindingChip
                        key={chip.finding.id}
                        chip={chip}
                        filename={filename}
                        open={openChip === chip.finding.id}
                        onToggle={() =>
                          setOpenChip((cur) => (cur === chip.finding.id ? null : chip.finding.id))
                        }
                        onAccept={accept}
                        onReject={reject}
                        onReplace={replace}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </section>
          ))}
          <button type="button" className="lens-add-missing" onClick={() => setAddOpen(true)}>
            {t('lens.add_missing')}
          </button>
          {addOpen && (
            <AddMissingModal onSubmit={addMissing} onCancel={() => setAddOpen(false)} />
          )}
        </div>
      )}
    </aside>
  );
}

/**
 * One value chip. Suggested = purple at 55 % opacity (`data-status`); the ⓘ
 * popover carries the plain-language line, the page reference and the
 * corrective actions (DemoC/03).
 */
function FindingChip({
  chip,
  filename,
  open,
  onToggle,
  onAccept,
  onReject,
  onReplace,
}: {
  chip: Chip;
  filename: string;
  open: boolean;
  onToggle: () => void;
  onAccept: (finding: Finding, applyTo?: IdentityType | Axis) => void;
  onReject: (finding: Finding) => void;
  onReplace: (finding: Finding, value: string) => void;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const finding = chip.finding;
  const target = fillTarget(finding);

  return (
    <span className="lens-chip-wrap">
      <button
        type="button"
        className="lens-chip"
        data-status={finding.status}
        aria-expanded={open}
        onClick={onToggle}
      >
        {chip.label}
        {chip.count > 1 && <span className="lens-chip-count">{chip.count}</span>}
      </button>
      {open && (
        <div className="lens-popover" role="dialog" aria-label={chip.label}>
          <p>{describeFinding(finding, t)}</p>
          {finding.page != null && (
            <p className="lens-popover-source">
              {t('lens.found_on_page', { page: finding.page, filename })}
            </p>
          )}
          <div className="lens-popover-actions">
            {target.kind === 'identity' && finding.status === 'suggested' && (
              <button type="button" onClick={() => onAccept(finding)}>
                {t('lens.accept')}
              </button>
            )}
            {target.kind === 'axis' && finding.status === 'suggested' && (
              <span className="lens-axis-actions">
                {t('lens.apply_as')}
                {(['size_x', 'size_y', 'size_z'] as const).map((axis) => (
                  <button key={axis} type="button" onClick={() => onAccept(finding, axis)}>
                    {axis.slice(-1).toUpperCase()}
                  </button>
                ))}
              </span>
            )}
            {target.kind === 'none' && finding.status === 'suggested' && (
              <button type="button" onClick={() => onAccept(finding)}>
                {t('lens.accept_plain')}
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard?.writeText(finding.value ?? finding.raw_text ?? '');
              }}
            >
              {t('lens.copy')}
            </button>
            {finding.status !== 'rejected' &&
              (editing ? (
                <span className="lens-replace">
                  <input
                    value={editValue}
                    aria-label={t('lens.replace_value')}
                    onChange={(e) => setEditValue(e.target.value)}
                  />
                  <button
                    type="button"
                    disabled={!editValue.trim()}
                    onClick={() => {
                      onReplace(finding, editValue.trim());
                      setEditing(false);
                    }}
                  >
                    {t('lens.replace_save')}
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setEditValue(finding.value ?? '');
                    setEditing(true);
                  }}
                >
                  {t('lens.replace')}
                </button>
              ))}
            <button type="button" className="lens-inaccurate" onClick={() => onReject(finding)}>
              {t('lens.mark_inaccurate')}
            </button>
          </div>
        </div>
      )}
    </span>
  );
}

/** Plain-language description (spec #wingman §2 — each finding explains itself). */
function describeFinding(finding: Finding, t: TFunction): string {
  if (finding.gdt?.symbol) {
    return t('lens.describe_control_frame', {
      symbol: finding.gdt.symbol,
      value: finding.value ?? '',
      datums: finding.gdt.datum_refs?.join(', ') ?? '—',
    });
  }
  const label = t(`lens.type_${finding.type}`, { defaultValue: finding.type });
  const value = finding.value ?? finding.raw_text ?? '—';
  const units = finding.units ? ` ${finding.units}` : '';
  return `${label}: ${value}${units}`;
}

/**
 * Minimal Part-fields editor (M1.5 fields — stands in until the full M2.10
 * Part Setup panel). Purple click-fill dots appear on fields with a
 * ≥ 0.7-confidence suggestion (spec #wingman §5); clicking one is the
 * explicit Accept.
 */
function PartFieldsTab({
  part,
  findings,
  onAccept,
  onSaved,
}: {
  part: Part;
  findings: Finding[];
  onAccept: (finding: Finding, applyTo?: IdentityType) => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const partsApi = usePartsApi();
  const [draft, setDraft] = useState({
    part_number: part.part_number ?? '',
    revision: part.revision ?? '',
    description: part.description ?? '',
  });
  const [dims, setDims] = useState({ size_x: '', size_y: '', size_z: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft({
      part_number: part.part_number ?? '',
      revision: part.revision ?? '',
      description: part.description ?? '',
    });
  }, [part]);

  useEffect(() => {
    partsApi
      .getGeometry(part.id)
      .then((geom) =>
        setDims({
          size_x: geom.size_x != null ? String(geom.size_x) : '',
          size_y: geom.size_y != null ? String(geom.size_y) : '',
          size_z: geom.size_z != null ? String(geom.size_z) : '',
        }),
      )
      .catch(() => undefined);
  }, [partsApi, part.id]);

  const save = async () => {
    setSaving(true);
    try {
      await partsApi.updatePart(part.id, {
        part_number: draft.part_number || null,
        revision: draft.revision || null,
        description: draft.description || null,
      });
      const dimChanges: Record<string, string | null> = {};
      for (const [key, value] of Object.entries(dims)) {
        dimChanges[key] = value.trim() === '' ? null : value;
      }
      await partsApi.updateGeometry(part.id, dimChanges);
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  const identityField = (field: IdentityType, label: string) => {
    const suggestion = fillSuggestion(findings, field);
    return (
      <label className="lens-field">
        {label}
        <span className="lens-field-input">
          <input
            value={draft[field]}
            onChange={(e) => setDraft((d) => ({ ...d, [field]: e.target.value }))}
          />
          {suggestion && (
            <button
              type="button"
              className="lens-fill-dot"
              title={t('lens.fill_from_print', { value: suggestion.value ?? '' })}
              onClick={() => onAccept(suggestion)}
            >
              ✦
            </button>
          )}
        </span>
      </label>
    );
  };

  return (
    <div className="lens-fields">
      {identityField('part_number', t('lens.field_part_number'))}
      {identityField('revision', t('lens.field_revision'))}
      {identityField('description', t('lens.field_description'))}
      <fieldset className="lens-dims">
        <legend>{t('lens.dims_legend')}</legend>
        {(['size_x', 'size_y', 'size_z'] as const).map((axis) => (
          <label key={axis}>
            {axis.slice(-1).toUpperCase()}
            <input
              value={dims[axis]}
              inputMode="decimal"
              onChange={(e) => setDims((d) => ({ ...d, [axis]: e.target.value }))}
            />
          </label>
        ))}
      </fieldset>
      <button type="button" disabled={saving} onClick={() => void save()}>
        {saving ? t('lens.saving') : t('lens.save_fields')}
      </button>
    </div>
  );
}

const ADD_CATEGORIES = ['quote_setup', 'requirements', 'features', 'dimensions'] as const;

/** "Add missing extraction" — typed form (v1; the drawn region can follow
 * via the viewer marquee — the API already takes page + bbox). */
function AddMissingModal({
  onSubmit,
  onCancel,
}: {
  onSubmit: (body: AddMissingBody) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [category, setCategory] = useState<AddMissingBody['category']>('requirements');
  const [type, setType] = useState('');
  const [value, setValue] = useState('');
  const [page, setPage] = useState('');

  return (
    <div className="lens-modal" role="dialog" aria-label={t('lens.add_missing')}>
      <h4>{t('lens.add_missing')}</h4>
      <label>
        {t('lens.add_category')}
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value as AddMissingBody['category'])}
        >
          {ADD_CATEGORIES.map((key) => (
            <option key={key} value={key}>
              {t(`lens.section_${key}`)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('lens.add_type')}
        <input value={type} onChange={(e) => setType(e.target.value)} placeholder="length" />
      </label>
      <label>
        {t('lens.add_value')}
        <input value={value} onChange={(e) => setValue(e.target.value)} />
      </label>
      <label>
        {t('lens.add_page')}
        <input value={page} inputMode="numeric" onChange={(e) => setPage(e.target.value)} />
      </label>
      <div className="lens-popover-actions">
        <button type="button" onClick={onCancel}>
          {t('lens.cancel')}
        </button>
        <button
          type="button"
          disabled={!type.trim() || !value.trim()}
          onClick={() =>
            onSubmit({
              category,
              type: type.trim(),
              value: value.trim(),
              ...(page.trim() ? { page: Number(page) } : {}),
            })
          }
        >
          {t('lens.add_save')}
        </button>
      </div>
    </div>
  );
}
