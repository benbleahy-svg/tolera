/**
 * One viewer route, type-dispatched (M2.6): the M1.2 file record decides the
 * surface — PDF → the M2.1 viewer, STEP → the 3D viewer, anything else on the
 * upload allow-list → an honest no-preview state. Dispatch reads the server
 * record (file_type category + filename extension), never the bytes.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { usePartsApi, type PartFile } from '../parts/api';
import { CadViewerPage } from './cad/CadViewerPage';
import { PdfViewerPage } from './PdfViewerPage';

type Surface =
  | { kind: 'loading' }
  | { kind: 'pdf' }
  | { kind: 'cad'; file: PartFile }
  | { kind: 'no_preview'; file: PartFile }
  | { kind: 'not_found' }
  | { kind: 'error' };

function surfaceFor(file: PartFile): Surface {
  const ext = file.filename.split('.').pop()?.toLowerCase() ?? '';
  if (ext === 'pdf') return { kind: 'pdf' };
  if (ext === 'step' || ext === 'stp') return { kind: 'cad', file };
  return { kind: 'no_preview', file };
}

export function FileViewerPage() {
  const { partId = '', fileId = '' } = useParams<{ partId: string; fileId: string }>();
  const api = usePartsApi();
  const { t } = useTranslation();
  const [surface, setSurface] = useState<Surface>({ kind: 'loading' });

  useEffect(() => {
    let cancelled = false;
    api
      .listFiles(partId)
      .then((files) => {
        if (cancelled) return;
        const file = files.find((f) => f.id === fileId);
        setSurface(file ? surfaceFor(file) : { kind: 'not_found' });
      })
      .catch(() => {
        if (!cancelled) setSurface({ kind: 'error' });
      });
    return () => {
      cancelled = true;
    };
  }, [api, partId, fileId]);

  switch (surface.kind) {
    case 'pdf':
      return <PdfViewerPage />;
    case 'cad':
      return <CadViewerPage file={surface.file} />;
    case 'loading':
      return (
        <main className="viewer-page">
          <p role="status">{t('viewer.file_loading')}</p>
        </main>
      );
    case 'not_found':
    case 'error':
    case 'no_preview':
      return (
        <main className="viewer-page">
          <header className="viewer-toolbar">
            <Link to="/parts">{t('viewer.back_to_parts')}</Link>
            {surface.kind === 'no_preview' && <strong>{surface.file.filename}</strong>}
          </header>
          <p role="status">
            {t(
              surface.kind === 'no_preview'
                ? 'viewer.no_preview'
                : surface.kind === 'not_found'
                  ? 'viewer.file_not_found'
                  : 'viewer.file_load_failed',
            )}
          </p>
        </main>
      );
  }
}
