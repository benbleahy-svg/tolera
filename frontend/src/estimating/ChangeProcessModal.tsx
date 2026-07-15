/**
 * "Update Process and Material" (spec #partview, DemoG/01): a searchable
 * process picker plus an optional material type-ahead in the same modal, then
 * the two commits — UPDATE (destructive: "This action will delete all existing
 * operations."; router regeneration is a no-op until M4) and UPDATE AND KEEP
 * EXISTING OPS (DECISIONS.md 2026-07-07 "Change Process semantics pre-router").
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { MaterialSearchHit, ProcessOut } from './types';

interface Props {
  processes: ProcessOut[];
  currentProcessId: string | null;
  currentMaterial: MaterialSearchHit | null;
  searchMaterials: (q: string) => Promise<MaterialSearchHit[]>;
  /** materialId is undefined when the material was left untouched. */
  onCommit: (
    processId: string | null,
    keepOperations: boolean,
    materialId?: string | null,
  ) => void;
  onClose: () => void;
}

export function ChangeProcessModal({
  processes,
  currentProcessId,
  currentMaterial,
  searchMaterials,
  onCommit,
  onClose,
}: Props) {
  const { t } = useTranslation();
  const [processId, setProcessId] = useState<string>(currentProcessId ?? '');
  const [filter, setFilter] = useState('');
  const [materialQuery, setMaterialQuery] = useState('');
  const [materialHits, setMaterialHits] = useState<MaterialSearchHit[]>([]);
  const [pickedMaterial, setPickedMaterial] = useState<MaterialSearchHit | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const q = materialQuery.trim();
    if (q === '') {
      setMaterialHits([]);
      return;
    }
    const mySeq = ++seq.current;
    const timer = setTimeout(() => {
      searchMaterials(q)
        .then((hits) => {
          if (mySeq === seq.current) setMaterialHits(hits);
        })
        .catch(() => {
          if (mySeq === seq.current) setMaterialHits([]);
        });
    }, 150);
    return () => clearTimeout(timer);
  }, [materialQuery, searchMaterials]);

  const visible = processes.filter((p) =>
    p.name.toLowerCase().includes(filter.trim().toLowerCase()),
  );

  const commit = (keep: boolean) => {
    onCommit(
      processId === '' ? null : processId,
      keep,
      pickedMaterial === null ? undefined : pickedMaterial.id,
    );
  };

  return (
    <div
      className="est-modal-backdrop"
      role="dialog"
      aria-label={t('estimating.change_process_title')}
    >
      <div className="est-modal">
        <h3>{t('estimating.change_process_title')}</h3>
        <label>
          {t('estimating.process_search_placeholder')}
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t('estimating.process_search_placeholder')}
          />
        </label>
        <label>
          {t('estimating.process')}
          <select value={processId} onChange={(e) => setProcessId(e.target.value)}>
            <option value="">{t('estimating.no_process')}</option>
            {visible.map((process) => (
              <option key={process.id} value={process.id}>
                {process.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('estimating.material')}
          <input
            value={materialQuery}
            onChange={(e) => setMaterialQuery(e.target.value)}
            placeholder={
              pickedMaterial?.display_name ??
              currentMaterial?.display_name ??
              t('estimating.material_search_placeholder')
            }
            aria-label={t('estimating.material_search_placeholder')}
          />
        </label>
        {materialHits.length > 0 && (
          <ul className="est-picker-hits est-def-list">
            {materialHits.map((hit) => (
              <li key={hit.id}>
                <button
                  type="button"
                  onClick={() => {
                    setPickedMaterial(hit);
                    setMaterialQuery('');
                    setMaterialHits([]);
                  }}
                >
                  {hit.path}
                </button>
              </li>
            ))}
          </ul>
        )}
        {pickedMaterial && (
          <p className="est-hint">
            {t('estimating.material')}: {pickedMaterial.path}
          </p>
        )}
        <p className="est-warning">{t('estimating.change_process_warning')}</p>
        <div className="est-actions">
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={() => commit(true)}>
            {t('estimating.update_keep_ops')}
          </button>
          <button type="button" className="est-danger" onClick={() => commit(false)}>
            {t('estimating.update')}
          </button>
        </div>
      </div>
    </div>
  );
}
