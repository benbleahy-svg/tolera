/**
 * Settings → Finalized Quote Settings (M5.8, spec #digital-quote-settings) — the
 * client for the org's `org_quote_settings` row. Reads are `view_all`; writes are
 * `settings_edit` (the backend gates both). The update is a partial PATCH-style
 * PUT: only the fields present change, so the page sends just what the user
 * touched. Bound to the Clerk session token once (the `useEmailApi` pattern).
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';

export type TotalDisplay = 'price_range' | 'maximum_price' | 'none';
export type PreparerDisplay = 'salesperson' | 'estimator' | 'both';
export type NotesPlacement = 'above' | 'below';
export type ShippingMethod =
  | 'bill_at_shipment'
  | 'use_my_shipping_account'
  | 'no_shipping_fees'
  | 'local_pickup';

/** The shipping methods the shop can disable at checkout (local pickup has its
 * own "Allow Local Pickup" toggle, so it is not in this list). */
export const DISABLEABLE_SHIPPING_METHODS: ShippingMethod[] = [
  'bill_at_shipment',
  'use_my_shipping_account',
  'no_shipping_fees',
];

/** The Email-Notification recipient keys (spec Email Notification Settings). */
export const NOTIFICATION_KEYS = [
  'quote_send_bcc',
  'order_confirmation',
  'requote_request',
  'smartrfq_received',
  'email_fwd_received',
] as const;
export type NotificationKey = (typeof NOTIFICATION_KEYS)[number];

export interface QuoteSettings {
  // Display Settings — show_* toggles.
  show_part_number: boolean;
  show_revision: boolean;
  show_description: boolean;
  show_process: boolean;
  show_material: boolean;
  show_dimensions: boolean;
  show_dfm: boolean;
  show_3d: boolean;
  show_part_file_name: boolean;
  show_thumbnail: boolean;
  show_quote_number: boolean;
  show_rfq_number: boolean;
  show_facility_phone: boolean;
  show_facility_website: boolean;
  show_digital_quote_link: boolean;
  total_display: TotalDisplay;
  preparer: PreparerDisplay;
  notes_placement: NotesPlacement;
  // Quote merge content.
  terms: string | null;
  manufacturers_notes: string | null;
  quote_notes: string | null;
  require_terms_acceptance: boolean;
  // Requotes + Checkout Settings.
  requotes_enabled: boolean;
  allow_local_pickup: boolean;
  send_order_confirmation_emails: boolean;
  disabled_shipping_methods: ShippingMethod[];
  // Lead-Time + notifications + accounting.
  lead_time_business_days: boolean;
  notification_recipients: Partial<Record<NotificationKey, string | null>>;
  default_tax_rate_pct: string | null;
}

export type QuoteSettingsUpdate = Partial<QuoteSettings>;

/** The show_* Display-Settings toggle keys, in display order. */
export const SHOW_FLAG_KEYS: (keyof QuoteSettings)[] = [
  'show_part_number',
  'show_revision',
  'show_description',
  'show_process',
  'show_material',
  'show_dimensions',
  'show_dfm',
  'show_3d',
  'show_part_file_name',
  'show_thumbnail',
  'show_quote_number',
  'show_rfq_number',
  'show_facility_phone',
  'show_facility_website',
  'show_digital_quote_link',
];

export interface QuoteSettingsApi {
  get: () => Promise<QuoteSettings>;
  update: (body: QuoteSettingsUpdate) => Promise<QuoteSettings>;
}

/** Build a Finalized-Quote-Settings client bound to the current Clerk token. */
export function useQuoteSettingsApi(): QuoteSettingsApi {
  const { getToken } = useAuth();
  return useMemo<QuoteSettingsApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      get: () => apiFetch('/api/settings/quote', token),
      update: (body) => apiFetch('/api/settings/quote', token, { method: 'PUT', body }),
    };
  }, [getToken]);
}
