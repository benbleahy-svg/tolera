/**
 * Shared section chrome for the part view (spec #partview; DemoA/B/E frames):
 * every computational section is collapsible (chevron, state remembered per
 * section) and carries a gear → Display Options popover (e.g. "Show unit
 * values"). Preferences persist in localStorage per section id.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

const STORAGE_PREFIX = 'tolera.est.section.';

function readPrefs(id: string): Record<string, boolean> {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + id);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    return typeof parsed === 'object' && parsed !== null
      ? (parsed as Record<string, boolean>)
      : {};
  } catch {
    return {};
  }
}

/** Per-section booleans (collapsed, unit_values, …) remembered across visits. */
export function useSectionPrefs(
  id: string,
): [Record<string, boolean>, (key: string, value: boolean) => void] {
  const [prefs, setPrefs] = useState<Record<string, boolean>>(() => readPrefs(id));
  const setPref = (key: string, value: boolean) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: value };
      try {
        window.localStorage.setItem(STORAGE_PREFIX + id, JSON.stringify(next));
      } catch {
        // private mode etc. — keep the in-memory state
      }
      return next;
    });
  };
  return [prefs, setPref];
}

export interface DisplayOption {
  key: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

interface Props {
  id: string;
  title: string;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  /** Display-Options entries behind the gear; omit for no gear. */
  options?: DisplayOption[];
  /** Right-side header content (ACTIONS menu etc.). */
  actions?: ReactNode;
  children: ReactNode;
}

export function CollapsibleSection({
  id,
  title,
  collapsed,
  onToggleCollapsed,
  options,
  actions,
  children,
}: Props) {
  const { t } = useTranslation();
  const [gearOpen, setGearOpen] = useState(false);
  const gearRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!gearOpen) return;
    const onDocClick = (event: MouseEvent) => {
      if (gearRef.current && !gearRef.current.contains(event.target as Node)) {
        setGearOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [gearOpen]);

  return (
    <section className="est-section">
      <header className="est-section-header">
        <button
          type="button"
          className="est-collapse-toggle"
          aria-expanded={!collapsed}
          aria-controls={`est-section-body-${id}`}
          aria-label={
            collapsed
              ? t('estimating.expand_section', { title })
              : t('estimating.collapse_section', { title })
          }
          onClick={onToggleCollapsed}
        >
          {collapsed ? '▸' : '▾'}
        </button>
        <h3>{title}</h3>
        <span className="est-section-actions">
          {actions}
          {options && options.length > 0 && (
            <span className="est-gear" ref={gearRef}>
              <button
                type="button"
                aria-label={t('estimating.display_options')}
                aria-expanded={gearOpen}
                onClick={() => setGearOpen((v) => !v)}
              >
                ⚙
              </button>
              {gearOpen && (
                <div className="est-gear-pop" role="menu">
                  <strong>{t('estimating.display_options')}</strong>
                  {options.map((option) => (
                    <label key={option.key}>
                      <input
                        type="checkbox"
                        checked={option.checked}
                        onChange={(e) => option.onChange(e.target.checked)}
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
              )}
            </span>
          )}
        </span>
      </header>
      <div id={`est-section-body-${id}`} hidden={collapsed}>
        {children}
      </div>
    </section>
  );
}
