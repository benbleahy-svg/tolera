/**
 * Files panel for a part (M1.2, spec #partview Files section). Lists a part's
 * files with the PRIMARY tagged, and — for an editor (`quote_edit`) — uploads
 * (one or more), swaps the PRIMARY, downloads, and deletes. This is the reusable
 * artifact; M1.5's Part Estimating View embeds it. Rendering/thumbnails arrive in
 * M2/M4 — here a file is an identity row (name · type · size · role).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { useHasPermission } from '../session/session';
import { type PartFile, formatBytes, usePartsApi } from './api';

export function FilesPanel({ partId }: { partId: string }) {
  const { t, i18n } = useTranslation();
  const api = usePartsApi();
  const canEdit = useHasPermission('quote_edit');

  const [files, setFiles] = useState<PartFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .listFiles(partId)
      .then(setFiles)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [api, partId]);

  useEffect(load, [load]);

  const run = useCallback(
    async (action: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await action();
        load();
      } catch (e: unknown) {
        setError(e instanceof ApiError ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  const onPick = (event: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    if (picked.length > 0) void run(() => api.uploadFiles(partId, picked));
    event.target.value = ''; // allow re-picking the same file
  };

  return (
    <section className="files-panel">
      <div className="files-header">
        <h2 className="files-title">{t('parts.files.title')}</h2>
        {canEdit && (
          <>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              {t('parts.files.upload')}
            </button>
            <input
              ref={fileInput}
              type="file"
              multiple
              hidden
              aria-label={t('parts.files.upload')}
              onChange={onPick}
            />
          </>
        )}
      </div>

      {error && (
        <p className="crm-error" role="alert">
          {error}
        </p>
      )}

      {files.length === 0 ? (
        <p className="page-empty">{t('parts.files.empty')}</p>
      ) : (
        <table className="crm-table files-table">
          <thead>
            <tr>
              <th>{t('parts.files.col.name')}</th>
              <th>{t('parts.files.col.type')}</th>
              <th>{t('parts.files.col.size')}</th>
              <th>{t('parts.files.col.role')}</th>
              <th aria-label={t('parts.files.col.actions')} />
            </tr>
          </thead>
          <tbody>
            {files.map((file) => (
              <tr key={file.id}>
                <td>{file.filename}</td>
                <td>{t(`parts.files.type.${file.file_type}`, file.file_type)}</td>
                <td>{formatBytes(file.size_bytes, i18n.language)}</td>
                <td>
                  {file.role === 'primary' ? (
                    <span className="crm-chip files-chip-primary">{t('parts.files.primary')}</span>
                  ) : (
                    <span className="crm-chip">{t('parts.files.supporting')}</span>
                  )}
                </td>
                <td className="files-actions">
                  <button
                    type="button"
                    className="btn btn-link"
                    onClick={() => void api.downloadFile(partId, file.id, file.filename)}
                  >
                    {t('parts.files.download')}
                  </button>
                  {canEdit && file.role !== 'primary' && (
                    <button
                      type="button"
                      className="btn btn-link"
                      disabled={busy}
                      onClick={() => void run(() => api.setPrimary(partId, file.id))}
                    >
                      {t('parts.files.make_primary')}
                    </button>
                  )}
                  {canEdit && (
                    <button
                      type="button"
                      className="btn btn-link btn-danger"
                      disabled={busy}
                      onClick={() => void run(() => api.deleteFile(partId, file.id))}
                    >
                      {t('parts.files.delete')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
