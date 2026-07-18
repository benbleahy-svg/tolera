/**
 * Buyer-portal payload contract (M5.1). The public, unauthenticated Digital
 * Quote endpoint (`GET /api/public/quotes/:token`) returns money as 4-dp
 * decimal STRINGS (e.g. "200.0000") or null — NOT minor units. These types
 * mirror that wire shape exactly; the portal is read-only and German-first.
 */

export interface BuyerQuote {
  quote_number: string;
  rfq_number: string | null;
  currency: 'EUR' | 'CHF';
  expiration_date: string | null; // ISO
  is_expired: boolean; // soft expiry: still selectable when true
  requotes_enabled: boolean;
  shop: { name: string; slug: string; country: string; currency: string; locale: string };
  price_range: { min_unit: string; max_unit: string } | null;
  line_items: BuyerLineItem[];
}

export interface BuyerLineItem {
  quote_item_id: string;
  position: number;
  is_no_quote: boolean;
  has_model: boolean;
  part_number?: string;
  revision?: string;
  description?: string;
  process?: string;
  material?: string;
  werkstoffnummer?: string | null;
  dimensions?: { x: string | null; y: string | null; z: string | null };
  dfm_warnings?: string[];
  breaks?: BuyerBreak[]; // absent when is_no_quote
  add_ons?: BuyerAddOn[]; // absent when is_no_quote
}

export interface BuyerBreak {
  quantity: number;
  unit_price: string | null;
  total_price: string | null;
  lead_time_days: number | null;
  expedites: BuyerExpedite[];
}

export interface BuyerExpedite {
  id: string;
  days_faster: number;
  lead_time_days: number | null;
  unit_price: string | null; // absolute expedited unit price
  total_price: string | null;
  unit_surcharge: string | null; // the "+ €60,00 / ea" delta over standard
}

export interface BuyerAddOn {
  id: string;
  display_name: string;
  is_required: boolean;
  prices: { quantity: number; price: string | null }[];
}

/** Per-line selection state held client-side (M5.2 checkout consumes it). */
export interface LineSelection {
  quantity: number | null;
  expediteId: string | null;
  addOnIds: Set<string>;
}

// --- M5.2 checkout → Order (PO only) --------------------------------------- //
/** The PO-compatible shipping methods (spec #shipping-options; CC hidden v1). */
export type ShippingMethod = 'bill_at_shipment' | 'use_my_shipping_account' | 'no_shipping_fees';

/** One line's selection, as the checkout endpoint consumes it (IDs only — the
 *  server re-derives every price; the client never sends money). */
export interface CheckoutLineSelection {
  quote_item_id: string;
  quantity: number;
  expedite_option_id?: string | null;
  add_on_ids?: string[];
}

export interface CheckoutRequest {
  selections: CheckoutLineSelection[];
  po_number: string;
  company_name?: string | null;
  billing_address?: string | null;
  notes?: string | null;
  buyer_ust_id_nr?: string | null;
  shipping_method: ShippingMethod;
}

/** The confirmation payload — money as integer minor units + currency. */
export interface CheckoutResult {
  order_id: string;
  order_number: string;
  currency: 'EUR' | 'CHF';
  net_minor: number;
  vat_minor: number;
  gross_minor: number;
  vat_rate_pct: string;
  vat_label: string | null;
  reverse_charge: boolean;
  kleinunternehmer: boolean;
  tax_note: string | null;
  po_number: string;
  shipping_method: ShippingMethod | null;
  lines: {
    quote_item_id: string;
    quantity: number;
    unit_price_minor: number;
    total_price_minor: number;
    expedites_fee_minor: number;
    lead_time_days: number | null;
    ships_on: string | null;
    add_ons: { id: string; name: string; price_minor: number; required: boolean }[];
  }[];
}
