/**
 * Loads the session bootstrap (`GET /api/me`) once on mount, using the Clerk
 * token, and provides it to the shell. While loading / on error it renders a
 * minimal status line (localised). When the user has not explicitly chosen a
 * language, the active org's locale seeds the UI language.
 */

import { useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { useTranslation } from 'react-i18next';

import { fetchMe } from '../api/client';
import { LOCALE_STORAGE_KEY, localeToLanguage } from '../i18n';
import { SessionContext, type Me } from './session';

export function SessionProvider({ children }: { children: ReactNode }) {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const { t, i18n } = useTranslation();
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    // Wait for Clerk; re-run on sign-in/out so the session can recover (rather
    // than a one-shot fetch that gets stuck if the first token isn't ready yet).
    if (!isLoaded) return;
    if (!isSignedIn) {
      setMe(null);
      setFailed(false);
      return;
    }
    let cancelled = false;
    setFailed(false);
    fetchMe(() => getToken())
      .then((data) => {
        if (cancelled) return;
        setMe(data);
        // Follow the active org's locale unless the user picked a language.
        let userChose = false;
        try {
          userChose = Boolean(localStorage.getItem(LOCALE_STORAGE_KEY));
        } catch {
          userChose = false;
        }
        if (!userChose) {
          void i18n.changeLanguage(localeToLanguage(data.active_org.locale));
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [getToken, i18n, isLoaded, isSignedIn]);

  if (failed) {
    return (
      <div className="session-status" role="alert">
        {t('session.error')}
      </div>
    );
  }
  if (!me) {
    return <div className="session-status">{t('session.loading')}</div>;
  }
  return <SessionContext.Provider value={me}>{children}</SessionContext.Provider>;
}
