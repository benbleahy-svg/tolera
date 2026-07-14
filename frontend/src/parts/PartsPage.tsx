/**
 * Part Library — the `/parts` destination (M2.12, spec #partlib; KB
 * `navigate-and-manage-the-part-library`).
 *
 * Team Parts / Shared with me / Archived tabs over a card grid (placeholder
 * thumbnail by file type, filename, part# + rev, process). Search covers
 * identity, filenames and the full text of uploaded PDFs (server-side).
 * Upload New Part (multi-file, auto-bundling: same stem → one part, CAD
 * primary) works via the button or drag-and-drop anywhere on the page.
 * "Auswählen" enters selection mode for Merge Parts as Supporting Files and
 * Archive; the Archived tab restores or (irreversibly) deletes. Clicking a
 * card opens the FilesPanel. Shared-with-me stays an empty state until the
 * external-collaboration share arrives (M6).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { useHasPermission } from '../session/session';
import { FilesPanel } from './FilesPanel';
import { type Part, usePartsApi } from './api';

type Tab = 'team' | 'shared' | 'archived';

const FILE_TYPE_GLYPHS: Record<string, string> = {
  brep_cad: '◆',
  mesh: '▲',
  vector_2d: '▱',
  document: '▤',
  email: '✉',
  archive: '⬒',
};

export function PartsPage() {
  const { t } = useTranslation();
  const api = usePartsApi();
  const canEdit = useHasPermission('quote_edit');

  const [tab, setTab] = useState<Tab>('team');
  const [query, setQuery] = useState('');
  const [parts, setParts] = useState<Part[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [merging, setMerging] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const fail = useCallback(
    (e: unknown) => setError(e instanceof ApiError ? e.message : String(e)),
    [],
  );

  const load = useCallback(() => {
    if (tab === 'shared') {
      setParts([]);
      return;
    }
    setError(null);
    api
      .listParts({ tab, q: query || undefined })
      .then((next) => {
        setParts(next);
        setSelected((current) =>
          current && next.some((p) => p.id === current) ? current : null,
        );
      })
      .catch(fail);
  }, [api, tab, query, fail]);

  // Debounce so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const handle = setTimeout(load, 250);
    return () => clearTimeout(handle);
  }, [load]);

  const run = (work: Promise<unknown>) => {
    setBusy(true);
    setError(null);
    work
      .then(() => {
        setChecked(new Set());
        setSelecting(false);
        setMerging(false);
        load();
      })
      .catch(fail)
      .finally(() => setBusy(false));
  };

  const onUpload = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    run(api.uploadLibraryParts(Array.from(files)));
  };

  const toggleChecked = (id: string) => {
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const checkedIds = Array.from(checked);

  return (
    <section
      className="page"
      onDragOver={(e) => {
        if (canEdit && tab === 'team') e.preventDefault();
      }}
      onDrop={(e) => {
        if (!canEdit || tab !== 'team') return;
        e.preventDefault();
        onUpload(e.dataTransfer.files);
      }}
    >
      <div className="crm-header">
        <h1 className="page-title">{t('parts.library.title')}</h1>
        <input
          type="search"
          className="parts-search"
          placeholder={t('parts.library.search_placeholder')}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label={t('parts.library.search_placeholder')}
        />
        {canEdit && tab !== 'archived' && (
          <>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setSelecting((s) => !s);
                setChecked(new Set());
                setMerging(false);
              }}
            >
              {selecting ? t('common.cancel') : t('parts.library.select')}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => fileInput.current?.click()}
              disabled={busy}
            >
              {t('parts.library.upload')}
            </button>
            <input
              ref={fileInput}
              type="file"
              multiple
              hidden
              data-testid="library-upload-input"
              onChange={(e) => {
                onUpload(e.target.files);
                e.target.value = '';
              }}
            />
          </>
        )}
      </div>

      <div role="tablist" className="parts-tabs">
        {(['team', 'shared', 'archived'] as const).map((key) => (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={tab === key}
            className={`parts-tab${tab === key ? ' is-active' : ''}`}
            onClick={() => {
              setTab(key);
              setSelecting(false);
              setChecked(new Set());
            }}
          >
            {t(`parts.library.tab_${key}`)}
          </button>
        ))}
      </div>

      {error && (
        <p className="crm-error" role="alert">
          {error}
        </p>
      )}

      {selecting && checkedIds.length > 0 && (
        <div className="parts-actions" data-testid="selection-actions">
          <span>{t('parts.library.selected', { count: checkedIds.length })}</span>
          <button
            type="button"
            className="btn btn-ghost"
            disabled={busy || checkedIds.length < 2}
            onClick={() => setMerging(true)}
          >
            {t('parts.library.merge')}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            disabled={busy}
            onClick={() => run(Promise.all(checkedIds.map((id) => api.archivePart(id))))}
          >
            {t('parts.library.archive')}
          </button>
        </div>
      )}

      {tab === 'shared' ? (
        <p className="page-empty">{t('parts.library.shared_empty')}</p>
      ) : parts.length === 0 ? (
        <p className="page-empty">
          {query ? t('parts.library.no_results') : t('parts.library.empty')}
        </p>
      ) : (
        <ul className="parts-grid" data-testid="parts-grid">
          {parts.map((part) => (
            <li key={part.id}>
              <div
                className={`part-card${selected === part.id ? ' is-selected' : ''}`}
                data-testid={`part-card-${part.id}`}
              >
                {selecting && (
                  <input
                    type="checkbox"
                    className="part-card-check"
                    checked={checked.has(part.id)}
                    onChange={() => toggleChecked(part.id)}
                    aria-label={t('parts.library.select_part')}
                  />
                )}
                <button
                  type="button"
                  className="part-card-body"
                  onClick={() =>
                    selecting
                      ? toggleChecked(part.id)
                      : setSelected(selected === part.id ? null : part.id)
                  }
                >
                  <span className="part-card-thumb" aria-hidden="true">
                    {(part.primary_file_type && FILE_TYPE_GLYPHS[part.primary_file_type]) || '▦'}
                  </span>
                  <span className="part-card-file">
                    {part.primary_filename ?? part.name ?? t('parts.library.no_file')}
                  </span>
                  <span className="part-card-meta">
                    {part.part_number ?? '—'}
                    {part.revision ? ` · Rev ${part.revision}` : ''}
                  </span>
                  {part.process && <span className="crm-chip">{part.process}</span>}
                </button>
                {tab === 'archived' && canEdit && (
                  <div className="part-card-actions">
                    <button
                      type="button"
                      className="btn btn-link"
                      disabled={busy}
                      onClick={() => run(api.restorePart(part.id))}
                    >
                      {t('parts.library.restore')}
                    </button>
                    <button
                      type="button"
                      className="btn btn-link btn-danger"
                      disabled={busy}
                      onClick={() => {
                        if (confirmDelete === part.id) {
                          setConfirmDelete(null);
                          run(api.deletePart(part.id));
                        } else {
                          setConfirmDelete(part.id);
                        }
                      }}
                    >
                      {confirmDelete === part.id
                        ? t('parts.library.delete_confirm')
                        : t('parts.library.delete')}
                    </button>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {merging && (
        <MergeDialog
          parts={parts.filter((p) => checked.has(p.id))}
          busy={busy}
          onCancel={() => setMerging(false)}
          onMerge={(primaryId) => run(api.mergeParts(checkedIds, primaryId))}
        />
      )}

      {selected && !selecting && <FilesPanel key={selected} partId={selected} onMutate={load} />}
    </section>
  );
}

interface MergeDialogProps {
  parts: Part[];
  busy: boolean;
  onCancel: () => void;
  onMerge: (primaryPartId: string) => void;
}

/** KB merge flow: pick the primary (CAD preferred) — the rest become supporting. */
function MergeDialog({ parts, busy, onCancel, onMerge }: MergeDialogProps) {
  const { t } = useTranslation();
  const cadFirst =
    parts.find((p) => p.primary_file_type === 'brep_cad') ?? parts[0] ?? null;
  const [primary, setPrimary] = useState<string | null>(cadFirst?.id ?? null);

  return (
    <div className="crm-modal-backdrop">
      <div role="dialog" aria-modal="true" className="crm-modal" data-testid="merge-dialog">
        <h2>{t('parts.library.merge_title')}</h2>
        <p>{t('parts.library.merge_hint')}</p>
        <ul className="merge-choices">
          {parts.map((part) => (
            <li key={part.id}>
              <label>
                <input
                  type="radio"
                  name="merge-primary"
                  checked={primary === part.id}
                  onChange={() => setPrimary(part.id)}
                />
                {part.primary_filename ?? part.name ?? part.id.slice(0, 8)}
              </label>
            </li>
          ))}
        </ul>
        <div className="crm-modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || !primary}
            onClick={() => primary && onMerge(primary)}
          >
            {t('parts.library.merge_confirm')}
          </button>
        </div>
      </div>
    </div>
  );
}
