/**
 * ACTIONS ▾ on the costing-inputs band (M5.0, spec #partview). Carries the
 * per-line-item priority selector (numeric, higher = more urgent) — the field the
 * quotes grid rolls up as MAX (DECISIONS 2026-07-17 *Quote-level priority home*).
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

const PRIORITY_CHOICES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

interface LineItemActionsMenuProps {
  priority: number | null;
  onSetPriority: (priority: number | null) => void;
  disabled: boolean;
}

export function LineItemActionsMenu({ priority, onSetPriority, disabled }: LineItemActionsMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <details
      className="est-menu est-line-item-actions"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary>{t('estimating.actions_menu')}</summary>
      <div className="est-menu-pop" role="menu">
        <label className="est-action-priority">
          {t('estimating.priority')}
          <select
            value={priority ?? ''}
            disabled={disabled}
            onChange={(e) => onSetPriority(e.target.value === '' ? null : Number(e.target.value))}
          >
            <option value="">{t('estimating.priority_none')}</option>
            {PRIORITY_CHOICES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      </div>
    </details>
  );
}
