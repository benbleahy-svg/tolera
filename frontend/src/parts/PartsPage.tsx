/**
 * Parts list — the `/parts` destination (spec #partview). A deliberately MINIMAL
 * host for M1.2: it lists parts, creates an empty one (gated on `quote_edit`), and
 * opens the reusable <FilesPanel> for the selected part so the upload→download
 * slice is demoable end-to-end. M1.5 replaces this with the full Part Estimating
 * View (part numbers, BOM, geometry); the FilesPanel is the lasting artifact.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { errorMessage } from '../api/errors';
import { useHasPermission } from '../session/session';
import { FilesPanel } from './FilesPanel';
import { type Part, usePartsApi } from './api';

export function PartsPage() {
  const { t } = useTranslation();
  const api = usePartsApi();
  const canEdit = useHasPermission('quote_edit');

  const [parts, setParts] = useState<Part[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const requestSeq = useRef(0);

  const load = useCallback(() => {
    const seq = ++requestSeq.current;
    setError(null);
    api
      .listParts()
      .then((nextParts) => {
        // Ignore a slow earlier request resolving after a newer one — otherwise
        // the mount load can overwrite a create's reload and move the selection
        // off the just-created part.
        if (seq !== requestSeq.current) return;
        setParts(nextParts);
        // Open the first part by default (keep a still-valid selection if there is one)
        // so the files pane isn't blank when parts already exist.
        setSelected((current) =>
          current && nextParts.some((p) => p.id === current)
            ? current
            : (nextParts[0]?.id ?? null),
        );
      })
      .catch((e: unknown) => {
        if (seq === requestSeq.current) setError(errorMessage(e, t));
      });
  }, [api, t]);

  useEffect(load, [load]);

  const onCreate = () => {
    if (creating) return; // guard against double-submit creating duplicate parts
    setCreating(true);
    setError(null);
    api
      .createPart()
      .then((part) => {
        setSelected(part.id);
        load();
      })
      .catch((e: unknown) => setError(errorMessage(e, t)))
      .finally(() => setCreating(false));
  };

  return (
    <section className="page">
      <div className="crm-header">
        <h1 className="page-title">{t('nav.parts')}</h1>
        {canEdit && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={onCreate}
            disabled={creating}
          >
            {t('parts.create')}
          </button>
        )}
      </div>

      {error && (
        <p className="crm-error" role="alert">
          {error}
        </p>
      )}

      <div className="parts-layout">
        {parts.length === 0 ? (
          <p className="page-empty">{t('parts.empty')}</p>
        ) : (
          <ul className="parts-list">
            {parts.map((part) => (
              <li key={part.id}>
                <button
                  type="button"
                  className={`parts-list-item${selected === part.id ? ' is-selected' : ''}`}
                  onClick={() => setSelected(part.id)}
                >
                  <span className="parts-list-id">{part.id.slice(0, 8)}</span>
                  {part.primary_file_id ? (
                    <span className="crm-chip files-chip-primary">{t('parts.has_primary')}</span>
                  ) : (
                    <span className="crm-chip">{t('parts.no_primary')}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}

        {selected && <FilesPanel key={selected} partId={selected} onMutate={load} />}
      </div>
    </section>
  );
}
