/**
 * The BOM Builder modal (M4.9 — spec #bombuilder; DemoD/07–11 are the frames):
 * a near-full-screen staging area. Header: draft-saved indicator + discard,
 * CHECK BOM (validate only), CHECK AND PUBLISH (the only committing action), ✕.
 * Toolbar: UNDO/REDO, expand/collapse, search. Left: the Quote Files pane with
 * purple BOM-table badges. Grid: Item No. (decimal-dot) / Part Number (type
 * icon + child-BOM sparkle) / Rev / Type / Primary File / Description / Qty.
 * Footer: the "N/1000 unique parts" counter.
 *
 * AI-Governor: extraction only ever seeds *editable suggestion rows*; child-BOM
 * rows enter the document through the explicit per-row accept, and nothing
 * reaches part/node/component before CHECK AND PUBLISH.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { BomApi } from './api';
import {
  acceptChildBom,
  addChild,
  applyFileMatches,
  blankRow,
  defaultChildType,
  docReducer,
  initialDocState,
  itemNumbers,
  matchFilesToRows,
  removeRow,
  searchMatches,
  uniquePartCount,
  updateRow,
  walk,
} from './tree';
import type {
  BomDoc,
  BomRow,
  BuilderState,
  CheckResult,
  ChildSuggestionOut,
  PublishedNode,
  RowType,
} from './types';

interface Props {
  quoteItemId: string;
  api: BomApi;
  onPublished: (tree: PublishedNode) => void;
  onClose: () => void;
}

const AUTOSAVE_DELAY_MS = 800;

const TYPE_ICONS: Record<RowType, string> = {
  assembly_root: '▦',
  subassembly: '▦',
  manufactured: '⬛',
  purchased: '⚙',
};

export function BomBuilderModal({ quoteItemId, api, onPublished, onClose }: Props) {
  const { t } = useTranslation();
  const [state, setState] = useState<BuilderState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [docState, dispatch] = useReducer(docReducer, initialDocState(emptyDoc()));
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [check, setCheck] = useState<CheckResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [actionError, setActionError] = useState<string | null>(null);
  const [savedSeq, setSavedSeq] = useState(0);
  const failAction = (e: unknown) => {
    const detail = String(e instanceof Error ? e.message : e);
    setActionError(t('bom.action_failed', { detail }));
  };

  const doc = docState.doc;

  useEffect(() => {
    api
      .getBuilderState(quoteItemId)
      .then((data) => {
        setState(data);
        dispatch({ kind: 'reset', doc: data.draft ? data.draft.payload : data.initial });
        if (data.draft) setSavedAt(data.draft.updated_at);
      })
      .catch((e: unknown) => setLoadError(String(e instanceof Error ? e.message : e)));
  }, [api, quoteItemId]);

  // Draft autosave: every committed edit (dirtySeq) schedules one debounced
  // PUT. The in-flight promise is tracked so discard can wait it out (an
  // autosave landing after discard would silently recreate the draft), and
  // savedSeq records WHICH document version reached the server so the header
  // never claims unsaved work is saved.
  const docRef = useRef(doc);
  docRef.current = doc;
  const saveTimerRef = useRef<number | null>(null);
  const inFlightSaveRef = useRef<Promise<unknown> | null>(null);
  useEffect(() => {
    if (docState.dirtySeq === 0) return;
    const seq = docState.dirtySeq;
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      // Chain on the previous save so writes reach the server in order.
      const previous = inFlightSaveRef.current ?? Promise.resolve();
      const save = previous
        .then(() => api.saveDraft(quoteItemId, docRef.current))
        .then((res) => {
          setSavedAt(res.updated_at);
          setSavedSeq(seq);
        })
        .catch(() => undefined) // autosave is best-effort; publish revalidates
        .finally(() => {
          if (inFlightSaveRef.current === save) inFlightSaveRef.current = null;
        });
      inFlightSaveRef.current = save;
    }, AUTOSAVE_DELAY_MS);
    // Re-run supersedes the pending timer with a newer document (debounce);
    // the unmount-flush effect below covers the close-within-debounce case.
    return () => {
      if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current);
    };
  }, [api, quoteItemId, docState.dirtySeq]);

  // Closing the modal within the debounce window must not lose work: flush a
  // still-pending autosave once, on true unmount (api/quoteItemId are stable
  // for the modal's lifetime, so this cleanup runs exactly at close).
  useEffect(() => {
    return () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
        void api.saveDraft(quoteItemId, docRef.current).catch(() => undefined);
      }
    };
  }, [api, quoteItemId]);

  // A stale CHECK result describes an older document — drop it on any edit.
  useEffect(() => {
    setCheck(null);
  }, [docState.dirtySeq]);

  // ESC closes (the BulkCreateDialog affordance).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Modal focus management (the BulkCreateDialog pattern): focus lands inside
  // when the dialog opens, Tab/Shift+Tab wrap, and the opener regains focus
  // on close.
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const container = containerRef.current;
    if (!container) return;
    const focusables = () =>
      Array.from(
        container.querySelectorAll<HTMLElement>(
          'button, input, select, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => !el.hasAttribute('disabled'));
    focusables()[0]?.focus();
    const trap = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const items = focusables();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    container.addEventListener('keydown', trap);
    return () => {
      container.removeEventListener('keydown', trap);
      opener?.focus();
    };
  }, [state]);

  const busyRef = useRef(false);
  busyRef.current = busy;
  const edit = useCallback((next: BomDoc) => {
    // A CHECK/PUBLISH in flight validated the document as sent — freeze it.
    if (busyRef.current) return;
    dispatch({ kind: 'edit', doc: next });
  }, []);

  const numbers = useMemo(() => itemNumbers(doc), [doc]);
  const uniqueCount = useMemo(() => uniquePartCount(doc), [doc]);
  const matches = useMemo(
    () => (state ? matchFilesToRows(doc, state.quote_files) : []),
    [doc, state],
  );
  const typeLabels = useMemo(
    () =>
      new Map<RowType, string>([
        ['assembly_root', t('bom.type_assembly_root')],
        ['subassembly', t('bom.type_subassembly')],
        ['manufactured', t('bom.type_manufactured')],
        ['purchased', t('bom.type_purchased')],
      ]),
    [t],
  );
  const searchHits = useMemo(
    () => (state ? searchMatches(doc, search, state.quote_files, typeLabels) : new Set<string>()),
    [doc, search, state, typeLabels],
  );
  const suggestionsByFile = useMemo(() => {
    const map = new Map<string, ChildSuggestionOut>();
    state?.child_suggestions.forEach((s) => map.set(s.file_id, s));
    return map;
  }, [state]);
  const filenames = useMemo(() => {
    const map = new Map<string, string>();
    state?.quote_files.forEach((f) => map.set(f.id, f.filename));
    return map;
  }, [state]);
  const matchedPartCount = useMemo(() => new Set(matches.map((m) => m.rowId)).size, [matches]);

  const discard = async () => {
    if (!state) return;
    setBusy(true);
    setActionError(null);
    try {
      // An autosave racing the discard would recreate the row server-side.
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
      if (inFlightSaveRef.current) await inFlightSaveRef.current;
      await api.discardDraft(quoteItemId);
      setSavedAt(null);
      setSavedSeq(0);
      setCheck(null);
      dispatch({ kind: 'reset', doc: state.initial });
    } catch (e: unknown) {
      failAction(e);
    } finally {
      setBusy(false);
    }
  };

  const runCheck = async () => {
    setBusy(true);
    setActionError(null);
    try {
      setCheck(await api.checkBom(quoteItemId, doc));
    } catch (e: unknown) {
      failAction(e);
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    setBusy(true);
    setActionError(null);
    try {
      // A trailing autosave must not land after publish consumed the draft.
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
      if (inFlightSaveRef.current) await inFlightSaveRef.current;
      const result = await api.publishBom(quoteItemId, doc);
      onPublished(result.tree);
    } catch (e: unknown) {
      // The backend 409s with the CHECK result in details — surface it in place.
      const details = (
        e as { details?: { errors?: CheckResult['errors']; notices?: CheckResult['notices'] } }
      ).details;
      if (details?.errors) {
        setCheck({
          errors: details.errors,
          notices: details.notices ?? [],
          unique_parts: uniqueCount,
        });
      } else {
        failAction(e);
      }
    } finally {
      setBusy(false);
    }
  };

  const toggleCollapse = (rowId: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  };

  const setAllCollapsed = (collapse: boolean) => {
    if (!collapse) {
      setCollapsed(new Set());
      return;
    }
    setCollapsed(new Set(walk(doc.root).filter((r) => r.children.length > 0).map((r) => r.row_id)));
  };

  if (loadError) {
    return (
      <div className="bom-backdrop" role="dialog" aria-modal="true">
        <div className="bom-modal">
          <p className="bom-error" role="alert">
            {loadError}
          </p>
          <button type="button" onClick={onClose}>
            {t('common.close')}
          </button>
        </div>
      </div>
    );
  }
  if (!state) {
    return (
      <div className="bom-backdrop" role="dialog" aria-modal="true">
        <div className="bom-modal">
          <p>{t('common.loading')}</p>
        </div>
      </div>
    );
  }

  const renderRow = (row: BomRow, depth: number): React.ReactNode[] => {
    if (search && !searchHits.has(row.row_id)) return [];
    const isRoot = row.row_id === doc.root.row_id;
    const suggestion = row.primary_file_id
      ? suggestionsByFile.get(row.primary_file_id)
      : undefined;
    const showSparkle = !!suggestion && row.children.length === 0 && !isRoot;
    const isCollapsed = collapsed.has(row.row_id);
    const cells = (
      <tr key={row.row_id} className={isRoot ? 'bom-row bom-row-root' : 'bom-row'}>
        <td className="bom-cell-itemno">
          <span className="bom-drag" aria-hidden="true">
            ⠿
          </span>
          {isRoot ? t('bom.item_root') : numbers.get(row.row_id)}
        </td>
        <td className="bom-cell-pn" style={{ paddingLeft: `${depth * 18 + 4}px` }}>
          {row.children.length > 0 && (
            <button
              type="button"
              className="bom-collapse"
              aria-label={t(isCollapsed ? 'bom.expand_row' : 'bom.collapse_row')}
              onClick={() => toggleCollapse(row.row_id)}
            >
              {isCollapsed ? '▸' : '▾'}
            </button>
          )}
          {showSparkle && (
            <button
              type="button"
              className="bom-sparkle"
              title={t('bom.child_suggestion_available')}
              aria-label={t('bom.child_suggestion_available')}
              onClick={() => suggestion && edit(acceptChildBom(doc, row.row_id, suggestion.rows))}
            >
              ✦
            </button>
          )}
          <span className={`bom-type-icon bom-type-${row.row_type}`} aria-hidden="true">
            {TYPE_ICONS[row.row_type]}
          </span>
          <input
            aria-label={t('bom.col_part_number')}
            value={row.part_number ?? ''}
            onChange={(e) =>
              edit(
                updateRow(doc, row.row_id, (r) => ({
                  ...r,
                  part_number: e.target.value || null,
                })),
              )
            }
          />
        </td>
        <td>
          <input
            className="bom-input-rev"
            aria-label={t('bom.col_rev')}
            value={row.revision ?? ''}
            onChange={(e) =>
              edit(
                updateRow(doc, row.row_id, (r) => ({ ...r, revision: e.target.value || null })),
              )
            }
          />
        </td>
        <td>
          {isRoot ? (
            <span>{t(`bom.type_${row.row_type}`)}</span>
          ) : (
            <select
              aria-label={t('bom.col_type')}
              value={row.row_type}
              onChange={(e) =>
                edit(
                  updateRow(doc, row.row_id, (r) => ({
                    ...r,
                    row_type: e.target.value as RowType,
                  })),
                )
              }
            >
              <option value="subassembly">{t('bom.type_subassembly')}</option>
              <option value="manufactured">{t('bom.type_manufactured')}</option>
              <option value="purchased">{t('bom.type_purchased')}</option>
            </select>
          )}
        </td>
        <td className="bom-cell-file">
          {row.primary_file_id ? (
            <span className="bom-file-chip">{filenames.get(row.primary_file_id) ?? '…'}</span>
          ) : (
            <span className="bom-file-empty">—</span>
          )}
        </td>
        <td>
          <input
            aria-label={t('bom.col_description')}
            value={row.description ?? ''}
            onChange={(e) =>
              edit(
                updateRow(doc, row.row_id, (r) => ({
                  ...r,
                  description: e.target.value || null,
                })),
              )
            }
          />
        </td>
        <td>
          <input
            className="bom-input-qty"
            type="number"
            min={1}
            aria-label={t('bom.col_qty')}
            value={row.qty}
            disabled={isRoot}
            onChange={(e) =>
              edit(
                updateRow(doc, row.row_id, (r) => ({
                  ...r,
                  qty: Math.max(1, Math.floor(Number(e.target.value) || 1)),
                })),
              )
            }
          />
        </td>
        <td className="bom-cell-actions">
          {row.row_type !== 'purchased' && (
            <button
              type="button"
              className="bom-row-action"
              aria-label={t('bom.add_child')}
              title={t('bom.add_child')}
              onClick={() => edit(addChild(doc, row.row_id, blankRow(defaultChildType(row))))}
            >
              +
            </button>
          )}
          {!isRoot && (
            <button
              type="button"
              className="bom-row-action"
              aria-label={t('bom.remove_row')}
              title={t('bom.remove_row')}
              onClick={() => edit(removeRow(doc, row.row_id))}
            >
              ✕
            </button>
          )}
        </td>
      </tr>
    );
    const children = isCollapsed ? [] : row.children.flatMap((c) => renderRow(c, depth + 1));
    return [cells, ...children];
  };

  return (
    <div className="bom-backdrop" role="dialog" aria-modal="true" aria-label={t('bom.title')}>
      <div className="bom-modal" ref={containerRef}>
        <header className="bom-header">
          <h2>{t('bom.title')}</h2>
          <div className="bom-header-actions">
            <span className="bom-draft-state" role="status">
              {savedAt && savedSeq === docState.dirtySeq
                ? t('bom.draft_saved')
                : t('bom.draft_unsaved')}
            </span>
            <button
              type="button"
              className="bom-discard"
              aria-label={t('bom.discard_draft')}
              title={t('bom.discard_draft')}
              onClick={discard}
              disabled={busy}
            >
              🗑
            </button>
            <button type="button" onClick={runCheck} disabled={busy}>
              {t('bom.check')}
            </button>
            <button type="button" className="bom-publish" onClick={publish} disabled={busy}>
              {t('bom.check_and_publish')}
            </button>
            <button type="button" aria-label={t('common.close')} onClick={onClose}>
              ✕
            </button>
          </div>
        </header>

        <div className="bom-toolbar">
          <button
            type="button"
            onClick={() => dispatch({ kind: 'undo' })}
            disabled={docState.undoStack.length === 0}
          >
            {t('bom.undo')}
          </button>
          <button
            type="button"
            onClick={() => dispatch({ kind: 'redo' })}
            disabled={docState.redoStack.length === 0}
          >
            {t('bom.redo')}
          </button>
          <button type="button" className="bom-link" onClick={() => setAllCollapsed(false)}>
            {t('bom.expand_all')}
          </button>
          <button type="button" className="bom-link" onClick={() => setAllCollapsed(true)}>
            {t('bom.collapse_all')}
          </button>
          <input
            className="bom-search"
            type="search"
            placeholder={t('bom.search_placeholder')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {matches.length > 0 && (
          <div className="bom-files-banner" role="status">
            <span className="bom-sparkle" aria-hidden="true">
              ✦
            </span>
            <div>
              <strong>{t('bom.add_files_title')}</strong>
              <div>
                {t('bom.add_files_detail', {
                  files: matches.length,
                  parts: matchedPartCount,
                })}
              </div>
            </div>
            <button
              type="button"
              className="bom-accept-files"
              onClick={() => edit(applyFileMatches(doc, matches))}
            >
              {t('bom.add_files_accept')}
            </button>
          </div>
        )}

        {actionError && (
          <p className="bom-error bom-action-error" role="alert">
            {actionError}
          </p>
        )}

        <div className="bom-body">
          <aside className="bom-files-pane">
            <h3>{t('bom.quote_files')}</h3>
            <ul>
              {state.quote_files.map((f) => (
                <li key={f.id}>
                  {f.has_bom_table && (
                    <span
                      className="bom-badge"
                      title={t('bom.table_detected')}
                      aria-label={t('bom.table_detected')}
                    >
                      ✦
                    </span>
                  )}
                  <span className="bom-filename">{f.filename}</span>
                  {f.part_number_extracted && (
                    <span className="bom-file-pn">{f.part_number_extracted}</span>
                  )}
                </li>
              ))}
            </ul>
          </aside>

          <div className="bom-grid-wrap">
            <table className="bom-grid">
              <thead>
                <tr>
                  <th>{t('bom.col_item_no')}</th>
                  <th>{t('bom.col_part_number')}</th>
                  <th>{t('bom.col_rev')}</th>
                  <th>{t('bom.col_type')}</th>
                  <th>{t('bom.col_primary_file')}</th>
                  <th>{t('bom.col_description')}</th>
                  <th>{t('bom.col_qty')}</th>
                  <th aria-label={t('bom.col_actions')} />
                </tr>
              </thead>
              <tbody>{renderRow(doc.root, 0)}</tbody>
            </table>

            {check && (
              <div className="bom-check-results" role="status">
                {check.errors.length === 0 ? (
                  <p className="bom-check-ok">{t('bom.check_ok')}</p>
                ) : (
                  <ul className="bom-check-errors">
                    {check.errors.map((issue, i) => (
                      <li key={`${issue.code}-${i}`} className="bom-error">
                        {t(`bom.issue_${issue.code}`, { defaultValue: issue.message })}
                      </li>
                    ))}
                  </ul>
                )}
                {check.notices.length > 0 && (
                  <ul className="bom-check-notices">
                    {check.notices.map((issue, i) => (
                      <li key={`${issue.code}-${i}`}>
                        {t(`bom.issue_${issue.code}`, { defaultValue: issue.message })}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>

        <footer className="bom-footer">
          <span>
            <strong>{uniqueCount}</strong>
            {t('bom.unique_parts', { cap: state.cap })}
          </span>
        </footer>
      </div>
    </div>
  );
}

function emptyDoc(): BomDoc {
  return {
    schema_version: 1,
    root: {
      row_id: 'root',
      row_type: 'assembly_root',
      part_number: null,
      revision: null,
      description: null,
      qty: 1,
      primary_file_id: null,
      supporting_file_ids: [],
      children: [],
    },
  };
}
