/**
 * Change Process (spec #partview): pick a process, then choose between the two
 * commits — UPDATE (destructive: "This action will delete all existing
 * operations."; router regeneration is a no-op until M4) and UPDATE AND KEEP
 * EXISTING OPS (DECISIONS.md 2026-07-07 "Change Process semantics pre-router").
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ProcessOut } from './types';

interface Props {
  processes: ProcessOut[];
  currentProcessId: string | null;
  onCommit: (processId: string | null, keepOperations: boolean) => void;
  onClose: () => void;
}

export function ChangeProcessModal({ processes, currentProcessId, onCommit, onClose }: Props) {
  const { t } = useTranslation();
  const [processId, setProcessId] = useState<string>(currentProcessId ?? '');

  const commit = (keep: boolean) => {
    onCommit(processId === '' ? null : processId, keep);
  };

  return (
    <div className="est-modal-backdrop" role="dialog" aria-label={t('estimating.change_process')}>
      <div className="est-modal">
        <h3>{t('estimating.change_process')}</h3>
        <label>
          {t('estimating.process')}
          <select value={processId} onChange={(e) => setProcessId(e.target.value)}>
            <option value="">{t('estimating.no_process')}</option>
            {processes.map((process) => (
              <option key={process.id} value={process.id}>
                {process.name}
              </option>
            ))}
          </select>
        </label>
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
