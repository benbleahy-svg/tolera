/**
 * Impressum + Datenschutzerklärung footer for the unauthenticated portals (M6.9).
 *
 * DACH-DELTA-LAYER §5 requires both on **all customer- and vendor-facing
 * surfaces**. M5.9 covered the server-rendered ones (quote PDF, quote email) via
 * `impressum_footer_html`; the two React portals are the remaining surfaces, and
 * they receive the same facts as structured JSON in the payload's `legal` block
 * (`app/impressum.legal_block`).
 *
 * Renders **only what the shop configured** — the "never invent" contract from
 * `app/impressum.py`. A shop with no commercial register emits no Impressum, and
 * one that has published no privacy policy shows no link rather than a guessed
 * URL. When neither is present the component renders nothing at all: an empty
 * "Impressum" heading is worse than no heading, because it looks like a legal
 * disclosure that is missing its content.
 *
 * Shared by both portals deliberately. These are separate bundles, and a legal
 * obligation that has to be remembered twice eventually gets remembered once.
 */

export type LegalLine = { label: string | null; value: string };

export type LegalBlock = {
  heading: string;
  impressum: LegalLine[];
  privacy_policy_url: string | null;
};

type Props = {
  legal?: LegalBlock | null;
  /** de-DE label for the privacy link (the portals are German-first). */
  privacyLabel?: string;
};

export function LegalFooter({ legal, privacyLabel = 'Datenschutzerklärung' }: Props) {
  const lines = legal?.impressum ?? [];
  const privacyUrl = legal?.privacy_policy_url ?? null;

  if (lines.length === 0 && !privacyUrl) return null;

  return (
    <footer className="portal-legal" data-testid="portal-legal">
      {lines.length > 0 && (
        <>
          <p className="portal-legal-heading">{legal?.heading ?? 'Impressum'}</p>
          {lines.map((line, index) => (
            // Address lines carry real newlines; preserve them rather than
            // collapsing a multi-line address onto one row.
            <p className="portal-legal-line" key={`${line.label ?? ''}-${index}`}>
              {line.label ? `${line.label}: ${line.value}` : line.value}
            </p>
          ))}
        </>
      )}
      {privacyUrl && (
        <p className="portal-legal-line">
          {/* noopener/noreferrer: an external link out of an unauthenticated
              token page must not hand the opener to the destination. */}
          <a href={privacyUrl} target="_blank" rel="noopener noreferrer">
            {privacyLabel}
          </a>
        </p>
      )}
    </footer>
  );
}
