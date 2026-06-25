/** Display helpers for CRM entities. */

import type { Contact } from './api';

/** A contact's best human label: full name if present, else the email. */
export function contactDisplayName(contact: Contact): string {
  const name = [contact.first_name, contact.last_name].filter(Boolean).join(' ').trim();
  return name || contact.email;
}
