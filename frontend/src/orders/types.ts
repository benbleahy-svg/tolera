/**
 * Orders-list + detail types — the wire contract for `/api/orders/search` and
 * `/api/orders/:id` (M5.6, spec #orderslist). Mirrors the quotes grammar (M1.3):
 * an allow-listed filter/sort set plus a free-text search, and the computed
 * (never-stored) system views. Money is integer **minor units** + `currency`.
 */

export type OrderSource = 'buyer_portal' | 'facilitated';
export type OrderShippingMethod =
  | 'bill_at_shipment'
  | 'use_my_shipping_account'
  | 'no_shipping_fees';

export type OrderFilterField = 'account_id' | 'source' | 'created_at';
export type OrderFilterOp = 'eq' | 'in' | 'is_null' | 'gte' | 'lte';
export type OrderSortField = 'created_at' | 'number' | 'net_minor';
export type SortDir = 'asc' | 'desc';

export interface OrderFilterClause {
  field: OrderFilterField;
  op: OrderFilterOp;
  value: unknown;
}

export interface OrderSortClause {
  field: OrderSortField;
  dir: SortDir;
}

export interface OrderRow {
  id: string;
  number: string;
  quote_id: string;
  quote_number: string | null;
  account_id: string | null;
  account_name: string | null;
  contact_name: string | null;
  po_number: string | null;
  /** "Date Placed" (ISO). */
  created_at: string;
  /** "Parts" — count of order lines. */
  parts_count: number;
  /** "Order Total" — NET, excl. VAT (persisted minor units). */
  net_minor: number;
  currency: string;
  source: OrderSource;
  /** "Expected Ship Date" — earliest line ships_on (ISO date) or null. */
  expected_ship_date: string | null;
  /** Nullable shipment timestamp — the only shipment state in v1. */
  shipped_at: string | null;
  /** Whether the Edit-order ⋮ action is offered (opt-in on + no shipment). */
  can_edit: boolean;
}

/** A built-in, non-stored view. `label_key` is an i18n key the UI localizes. */
export interface OrderSystemView {
  key: string;
  label_key: string;
  is_default: boolean;
}

export interface OrderSearchRequest {
  system_view?: string | null;
  filters?: OrderFilterClause[];
  sort?: OrderSortClause[];
  search?: string | null;
  limit?: number;
  offset?: number;
}

export interface OrderSearchResponse {
  rows: OrderRow[];
  total: number;
  limit: number;
  offset: number;
  views: OrderSystemView[];
}

export interface OrderLineOut {
  id: string;
  quote_item_id: string;
  /** 1-based line number on the source quote. */
  position: number;
  /** Human label for the ordered part (part #/name/description) or null. */
  part_label: string | null;
  quantity: number;
  unit_price_minor: number;
  total_price_minor: number;
  expedites_fee_minor: number;
  lead_time_days: number | null;
  ships_on: string | null;
  add_ons: unknown[] | null;
}

export interface OrderTaxRateLine {
  rate_pct: number;
  net_minor: number;
  vat_minor: number;
}

export interface OrderDetail {
  id: string;
  number: string;
  source: OrderSource;
  quote_id: string;
  quote_number: string | null;
  account_id: string | null;
  account_name: string | null;
  contact_id: string | null;
  contact_name: string | null;
  po_number: string | null;
  company_name: string | null;
  billing_address: string | null;
  shipping_method: OrderShippingMethod | null;
  notes: string | null;
  created_at: string;
  shipped_at: string | null;
  currency: string;
  net_minor: number;
  vat_minor: number;
  gross_minor: number;
  vat_rate_pct: number;
  vat_label: string | null;
  reverse_charge: boolean;
  kleinunternehmer: boolean;
  tax_note: string | null;
  supplier_ust_id_nr: string | null;
  buyer_ust_id_nr: string | null;
  tax_rate_lines: OrderTaxRateLine[] | null;
  expected_ship_date: string | null;
  can_edit: boolean;
  lines: OrderLineOut[];
}

export interface ErpPushResult {
  order_id: string;
  status: string;
}

// --------------------------------------------------------------------------- //
// M5.7 — Facilitate Order (Build Order drawer) + pre-ship edit + history
// --------------------------------------------------------------------------- //

/** A per-line Discount (Percent) on the Build Order drawer. */
export interface FacilitateDiscount {
  label: string;
  /** Percentage 0–100 (decimal string on the wire, e.g. "5.00"). */
  percent: string;
}

/** A per-line Additional Charge (Price) on the Build Order drawer. */
export interface FacilitateCharge {
  label: string;
  /** Money amount (decimal string, e.g. "500.00"). */
  amount: string;
}

/** One line's build selection: a chosen break + optional Ships-On override + adjustments. */
export interface FacilitateLineSelection {
  quote_item_id: string;
  quantity: number;
  expedite_option_id?: string | null;
  add_on_ids?: string[];
  /** ISO date; absent → placement date + the break's lead time. */
  ships_on?: string | null;
  discounts?: FacilitateDiscount[];
  additional_charges?: FacilitateCharge[];
}

export interface FacilitateOrderRequest {
  selections: FacilitateLineSelection[];
  po_number?: string | null;
  company_name?: string | null;
  billing_address?: string | null;
  notes?: string | null;
  buyer_ust_id_nr?: string | null;
  /** null = "None" (a valid facilitated shipping option). */
  shipping_method?: OrderShippingMethod | null;
}

export interface FacilitateOrderResult {
  order_id: string;
  order_number: string;
  source: OrderSource;
  currency: string;
  net_minor: number;
  vat_minor: number;
  gross_minor: number;
  reverse_charge: boolean;
  kleinunternehmer: boolean;
  po_number: string | null;
  shipping_method: OrderShippingMethod | null;
}

/** A pre-ship order edit — only present fields change. */
export interface OrderEditRequest {
  po_number?: string | null;
  company_name?: string | null;
  billing_address?: string | null;
  shipping_method?: OrderShippingMethod | null;
  /** true clears the shipping method (distinct from "unchanged"). */
  clear_shipping_method?: boolean;
  notes?: string | null;
  add_lines?: FacilitateLineSelection[];
  remove_line_ids?: string[];
  notify_buyer?: boolean;
}

export interface OrderEditResult {
  order_id: string;
  changes: Record<string, unknown>;
  buyer_notified: boolean;
  net_minor: number;
  vat_minor: number;
  gross_minor: number;
}

export type OrderHistoryKind = 'created' | 'edited';

export interface OrderHistoryEvent {
  id: string;
  kind: OrderHistoryKind;
  actor_user_id: string | null;
  changes: Record<string, unknown>;
  buyer_notified: boolean;
  created_at: string;
}
