/**
 * Light/dark mode toggle. Both palettes ship; default is light (DECISIONS.md
 * 2026-06-24 "Default colour mode"). The choice is applied to `<html>` and
 * persisted by `applyMode`.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { applyMode, getInitialMode, type Mode } from '../theme/theme';
import { MoonIcon, SunIcon } from './icons';

export function ThemeToggle() {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>(getInitialMode);

  function toggle() {
    const next: Mode = mode === 'dark' ? 'light' : 'dark';
    applyMode(next);
    setMode(next);
  }

  const goingDark = mode !== 'dark';
  return (
    <button type="button" className="menu-row" onClick={toggle} aria-pressed={mode === 'dark'}>
      {goingDark ? <MoonIcon /> : <SunIcon />}
      <span>{goingDark ? t('account.theme_dark') : t('account.theme_light')}</span>
    </button>
  );
}
