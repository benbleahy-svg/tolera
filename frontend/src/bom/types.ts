/**
 * BOM Builder types (M4.9 — spec #bombuilder). Mirrors app/bom_builder.py DTOs:
 * the staged document (BomDoc/BomRow), the builder state, CHECK BOM results and
 * the published tree. The document is the single editable artifact — the modal
 * mutates it locally (undo/redo snapshots), autosaves it as the draft, and
 * sends it verbatim to check/publish.
 */

export type RowType = 'assembly_root' | 'subassembly' | 'manufactured' | 'purchased';

export interface BomRow {
  row_id: string;
  row_type: RowType;
  part_number: string | null;
  revision: string | null;
  description: string | null;
  qty: number;
  primary_file_id: string | null;
  supporting_file_ids: string[];
  children: BomRow[];
}

export interface BomDoc {
  schema_version: 1;
  root: BomRow;
}

export interface BomTableRowOut {
  item_no: string | null;
  part_number: string | null;
  revision: string | null;
  qty: number;
  description: string | null;
  type_hint: 'subassembly' | 'manufactured' | 'purchased' | null;
}

export interface SuggestionOut {
  finding_id: string;
  file_id: string;
  filename: string;
  page: number | null;
}

export interface QuoteFileOut {
  id: string;
  part_id: string;
  filename: string;
  role: string;
  part_number_extracted: string | null;
  has_bom_table: boolean;
}

export interface ChildSuggestionOut {
  finding_id: string;
  file_id: string;
  page: number | null;
  root_part_number: string | null;
  rows: BomTableRowOut[];
}

export interface BuilderState {
  quote_item_id: string;
  root_part_id: string;
  root_component_id: string;
  draft: { payload: BomDoc; updated_at: string } | null;
  initial: BomDoc;
  suggestion: SuggestionOut | null;
  quote_files: QuoteFileOut[];
  child_suggestions: ChildSuggestionOut[];
  unique_parts: number;
  cap: number;
}

export interface BomIssue {
  code: string;
  message: string;
  row_ids: string[];
}

export interface CheckResult {
  errors: BomIssue[];
  notices: BomIssue[];
  unique_parts: number;
}

export interface PublishedNode {
  node_id: string;
  part_id: string;
  part_number: string | null;
  revision: string | null;
  description: string | null;
  row_type: RowType;
  qty_relative_to_parent: number;
  flat_qty: number;
  position: number;
  children: PublishedNode[];
}

export interface BomStatus {
  suggestion: SuggestionOut | null;
  has_children: boolean;
  has_draft: boolean;
}
