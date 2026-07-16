/**
 * Quotes-list + saved-view types — the wire contract for `/api/quotes/search` and
 * `/api/saved-views` (M1.3). A saved view's `filters`/`sort` are the **same** shape
 * as the search request body, so applying a view = replaying its stored clauses.
 */

export type QuoteStatus = 'draft' | 'sent' | 'won' | 'lost' | 'expired';

export type FilterField =
  | 'status'
  | 'account_id'
  | 'salesperson_id'
  | 'estimator_id'
  | 'created_at'
  | 'due_date';

export type FilterOp = 'eq' | 'in' | 'is_null' | 'gte' | 'lte';
export type SortField = 'created_at' | 'due_date' | 'status' | 'number';
export type SortDir = 'asc' | 'desc';

export interface FilterClause {
  field: FilterField;
  op: FilterOp;
  value: unknown;
}

export interface SortClause {
  field: SortField;
  dir: SortDir;
}

export interface QuoteRow {
  id: string;
  number: string;
  status: QuoteStatus;
  account_id: string | null;
  salesperson_id: string | null;
  estimator_id: string | null;
  rfq_number: string | null;
  due_date: string | null;
  created_at: string;
}

export interface QuoteSearchRequest {
  system_view?: string | null;
  filters?: FilterClause[];
  sort?: SortClause[];
  limit?: number;
  offset?: number;
}

export interface QuoteSearchResponse {
  rows: QuoteRow[];
  total: number;
  limit: number;
  offset: number;
}

/** A built-in, non-stored view. `label_key` is an i18n key the UI localizes. */
export interface SystemView {
  key: string;
  label_key: string;
  is_default: boolean;
}

export interface SavedView {
  id: string;
  owner_id: string;
  view_scope: 'quotes' | 'line_items';
  name: string;
  filters: FilterClause[];
  sort: SortClause[];
  visibility: 'private' | 'org';
  created_at: string;
  updated_at: string;
}

export interface SavedViewList {
  system: SystemView[];
  custom: SavedView[];
}

export interface SavedViewCreate {
  name: string;
  filters?: FilterClause[];
  sort?: SortClause[];
}

// --- M3.9 RFQ Triage Brief (spec #ai-triage) ---
export interface TriageProcess {
  family: string;
  name: string;
  likelihood: string;
  source: string;
}

export interface TriageComplianceFlag {
  code: string;
  severity: string;
  source: string;
  detail: string;
  term?: string;
}

export interface TriageBrief {
  version: number;
  generated_at: string;
  ai: { enabled: boolean; reason: string };
  parts: {
    count: number;
    files: { step: number; dxf: number; pdf: number; other: number; total: number; summary: string };
  };
  missing_files: string[];
  detected_processes: TriageProcess[];
  est_time_to_quote: { low_min: number; high_min: number; display: string; deterministic: boolean };
  customer: { known: boolean; name: string | null; prior_quotes: number; one_liner: string };
  compliance_flags: TriageComplianceFlag[];
  need_by: { date: string | null; days_until: number | null; urgency: string };
}

export interface TriageBriefResponse {
  brief: TriageBrief | null;
  ai?: { enabled: boolean; reason: string };
}
