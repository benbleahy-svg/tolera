/**
 * Vendor-RFQ portal wire types (M6.2), mirroring `app.vendor_portal`'s payload.
 *
 * Money is an exact decimal STRING end-to-end — never a JS number (a float would
 * silently round a price the shop is about to pay).
 */

export interface VendorRfqFile {
  id: string;
  filename: string;
  size_bytes: number;
}

export interface VendorRfqLine {
  id: string;
  part_number: string | null;
  revision: string | null;
  description: string | null;
  process: string | null;
  quantities: number[];
  estimator_notes: string | null;
  files: VendorRfqFile[];
}

export interface VendorRfqShop {
  name: string;
  slug: string;
  country: string;
  locale: string;
}

/** A price the vendor already submitted (the form reopens pre-filled). */
export interface VendorSubmittedPrice {
  quantity: number;
  unit_price: string | null;
  lead_time_days: number | null;
}

export interface VendorSubmittedLine {
  rfq_line_id: string;
  cannot_quote: boolean;
  notes: string | null;
  prices: VendorSubmittedPrice[];
}

export interface VendorSubmittedResponse {
  currency: string;
  valid_until: string | null;
  notes: string | null;
  is_late: boolean;
  submitted_at: string;
  attachment_filename: string | null;
  lines: VendorSubmittedLine[];
}

export interface VendorRfq {
  rfq_number: string;
  need_by_date: string | null;
  /** Informational only — the portal never renders a closed state (spec). */
  is_past_due: boolean;
  message: string | null;
  shop: VendorRfqShop;
  vendor: { name: string };
  lines: VendorRfqLine[];
  response: VendorSubmittedResponse | null;
}

/** What the form POSTs back. */
export interface VendorResponseRequest {
  currency: string;
  valid_until: string | null;
  notes: string | null;
  lines: {
    rfq_line_id: string;
    cannot_quote: boolean;
    notes: string | null;
    prices: { quantity: number; unit_price: string | null; lead_time_days: number | null }[];
  }[];
}

export interface VendorResponseResult {
  submitted_at: string;
  is_late: boolean;
}
