/**
 * A localized empty-state page. The real destination screens are out of M0.4
 * scope (Dashboard → M6, Quotes → M1, Configure → M5, …); each nav destination
 * routes here until its block lands, so the shell + nav are fully navigable.
 */

import { useTranslation } from 'react-i18next';

export function PlaceholderPage({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation();
  return (
    <section className="page">
      <h1 className="page-title">{t(titleKey)}</h1>
      <p className="page-empty">{t('page.placeholder_body')}</p>
    </section>
  );
}
