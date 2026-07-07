/**
 * i18n plumbing — German-first (DECISIONS.md 2026-06-14 "German translation
 * strings"). The catalog default language is `de` (de-DE for the pilot); `en` is
 * the secondary. A user's explicit choice (locale toggle) is persisted and wins;
 * otherwise the active org's locale seeds the language (see SessionProvider).
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import de from './locales/de.json';
import en from './locales/en.json';

export const SUPPORTED_LANGUAGES = ['de', 'en'] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];
export const DEFAULT_LANGUAGE: Language = 'de';
export const LOCALE_STORAGE_KEY = 'bf-locale';

function isSupported(value: string): value is Language {
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

/** Map a locale tag ("de-DE", "de-CH", "en") to a supported UI language. */
export function localeToLanguage(locale: string): Language {
  const prefix = locale.toLowerCase().split('-')[0];
  return isSupported(prefix) ? prefix : DEFAULT_LANGUAGE;
}

function initialLanguage(): Language {
  try {
    const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (saved && isSupported(saved)) return saved;
  } catch {
    /* storage unavailable */
  }
  return DEFAULT_LANGUAGE;
}

/** Keep `<html lang>` in sync so screen readers / spellcheck match the UI
 * language from first paint — index.html hard-codes `lang="de"`. */
function syncHtmlLang(language: string): void {
  document.documentElement.lang = language.split('-')[0];
}

i18n.on('languageChanged', syncHtmlLang);

void i18n.use(initReactI18next).init({
  resources: { de: { translation: de }, en: { translation: en } },
  lng: initialLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  interpolation: { escapeValue: false },
});

syncHtmlLang(i18n.resolvedLanguage ?? i18n.language ?? DEFAULT_LANGUAGE);

export default i18n;
