/**
 * Language toggle (de/en). Persists the user's choice so it wins over the org's
 * default locale on the next load. Changing the language re-renders every
 * translated string in the app live.
 */

import { useTranslation } from 'react-i18next';

import { LOCALE_STORAGE_KEY, SUPPORTED_LANGUAGES, type Language } from '../i18n';

export function LocaleToggle() {
  const { i18n, t } = useTranslation();
  const current = (i18n.resolvedLanguage ?? i18n.language ?? 'de').split('-')[0];
  // <html lang> sync lives in i18n/index.ts (languageChanged listener), so it
  // holds even when this toggle is unmounted (the account menu is closed).

  function choose(lang: Language) {
    void i18n.changeLanguage(lang);
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, lang);
    } catch {
      /* storage unavailable — language still applies for the session */
    }
  }

  return (
    <div className="seg" role="group" aria-label={t('account.language')}>
      {SUPPORTED_LANGUAGES.map((lang) => (
        <button
          key={lang}
          type="button"
          className={current === lang ? 'seg-btn active' : 'seg-btn'}
          aria-pressed={current === lang}
          onClick={() => choose(lang)}
        >
          {lang.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
