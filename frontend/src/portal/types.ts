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
