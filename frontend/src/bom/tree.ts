/**
 * BOM Builder document logic (M4.9) — pure helpers over the staged BomDoc:
 * decimal-dot item numbering (DemoD/09), the N/1000 unique-parts counter,
 * immutable row edits, Add-Files matching by title-block part number, child-BOM
 * acceptance, and the snapshot undo/redo state (the viewer/annotations.ts
 * pattern). Everything here is deterministic and covered by tree.test.ts.
 */

import type { BomDoc, BomRow, BomTableRowOut, QuoteFileOut, RowType } from './types';

let rowSeq = 0;

/** Client-side row ids: unique within a session, stable across edits. */
export function nextRowId(): string {
  rowSeq += 1;
  return `c-${Date.now().toString(36)}-${rowSeq}`;
}

export function blankRow(rowType: RowType = 'manufactured'): BomRow {
  return {
    row_id: nextRowId(),
    row_type: rowType,
    part_number: null,
    revision: null,
    description: null,
    qty: 1,
    primary_file_id: null,
    supporting_file_ids: [],
    children: [],
  };
}

/** DFS over the document; parents before children (grid row order). */
export function walk(row: BomRow): BomRow[] {
  return [row, ...row.children.flatMap(walk)];
}

/** Decimal-dot item numbers keyed by row_id; the root is labeled "Root". */
export function itemNumbers(doc: BomDoc): Map<string, string> {
  const numbers = new Map<string, string>();
  numbers.set(doc.root.row_id, 'Root');
  const visit = (row: BomRow, prefix: string) => {
    row.children.forEach((child, index) => {
      const label = prefix ? `${prefix}.${index + 1}` : `${index + 1}`;
      numbers.set(child.row_id, label);
      visit(child, label);
    });
  };
  visit(doc.root, '');
  return numbers;
}

function partKey(row: BomRow): string | null {
  const pn = (row.part_number ?? '').trim();
  if (!pn) return null;
  return `${pn}\u0000${(row.revision ?? '').trim()}`;
}

/** Unique parts (root included) — rows with the same part#+rev link as one. */
export function uniquePartCount(doc: BomDoc): number {
  const keys = new Set<string>();
  let keyless = 0;
  for (const row of walk(doc.root)) {
    const key = partKey(row);
    if (key === null) keyless += 1;
    else keys.add(key);
  }
  return keys.size + keyless;
}

/** Immutably replace one row (matched by row_id) via the updater. */
export function updateRow(doc: BomDoc, rowId: string, update: (row: BomRow) => BomRow): BomDoc {
  const visit = (row: BomRow): BomRow => {
    if (row.row_id === rowId) return update(row);
    const children = row.children.map(visit);
    return children.some((c, i) => c !== row.children[i]) ? { ...row, children } : row;
  };
  return { ...doc, root: visit(doc.root) };
}

export function removeRow(doc: BomDoc, rowId: string): BomDoc {
  const visit = (row: BomRow): BomRow => {
    const kept = row.children.filter((c) => c.row_id !== rowId).map(visit);
    return kept.length !== row.children.length || kept.some((c, i) => c !== row.children[i])
      ? { ...row, children: kept }
      : row;
  };
  return { ...doc, root: visit(doc.root) };
}

export function addChild(doc: BomDoc, parentRowId: string, child: BomRow): BomDoc {
  return updateRow(doc, parentRowId, (row) => ({
    ...row,
    // KB §Part type: a manufactured parent stays manufactured (part with
    // hardware); only explicit subassembly conversion changes row_type.
    children: [...row.children, child],
  }));
}

/** KB §Part type: default child type follows the parent's type. */
export function defaultChildType(parent: BomRow): RowType {
  return parent.row_type === 'manufactured' ? 'purchased' : 'manufactured';
}

export interface FileMatch {
  rowId: string;
  fileId: string;
}

/**
 * Add-Files matching (spec #bombuilder step 4): pair quote files to rows by the
 * title-block part number Lens extracted at split time. Case-insensitive exact
 * match; only rows without a primary file and files not yet assigned pair up.
 */
export function matchFilesToRows(doc: BomDoc, files: QuoteFileOut[]): FileMatch[] {
  const assigned = new Set<string>();
  for (const row of walk(doc.root)) {
    if (row.primary_file_id) assigned.add(row.primary_file_id);
    row.supporting_file_ids.forEach((id) => assigned.add(id));
  }
  const byPartNumber = new Map<string, QuoteFileOut[]>();
  for (const file of files) {
    if (assigned.has(file.id) || !file.part_number_extracted) continue;
    const key = file.part_number_extracted.trim().toUpperCase();
    byPartNumber.set(key, [...(byPartNumber.get(key) ?? []), file]);
  }
  const matches: FileMatch[] = [];
  const taken = new Set<string>();
  for (const row of walk(doc.root)) {
    if (row.primary_file_id || !row.part_number) continue;
    const candidates = byPartNumber.get(row.part_number.trim().toUpperCase()) ?? [];
    const file = candidates.find((f) => !taken.has(f.id));
    if (file) {
      taken.add(file.id);
      matches.push({ rowId: row.row_id, fileId: file.id });
    }
  }
  return matches;
}

export function applyFileMatches(doc: BomDoc, matches: FileMatch[]): BomDoc {
  return matches.reduce(
    (acc, m) => updateRow(acc, m.rowId, (row) => ({ ...row, primary_file_id: m.fileId })),
    doc,
  );
}

/**
 * Accept a child-BOM suggestion (the purple sparkle): the row becomes a
 * subassembly (unless it keeps hardware semantics) and the extracted rows
 * insert as its children — the explicit AI-Governor accept for BOM tables.
 */
export function acceptChildBom(doc: BomDoc, rowId: string, rows: BomTableRowOut[]): BomDoc {
  return updateRow(doc, rowId, (row) => ({
    ...row,
    row_type: 'subassembly',
    children: [
      ...row.children,
      ...rows.map((r) => ({
        ...blankRow(r.type_hint ?? 'manufactured'),
        part_number: r.part_number,
        revision: r.revision,
        description: r.description,
        qty: r.qty !== null && r.qty >= 1 ? r.qty : 1,
      })),
    ],
  }));
}

/** Row-ids whose subtree matches the search (part #, description, files, type).
 *  `typeLabels` carries the localized type names so a German user can search
 *  "Kaufteil", not the internal enum. */
export function searchMatches(
  doc: BomDoc,
  query: string,
  files: QuoteFileOut[],
  typeLabels?: Map<RowType, string>,
): Set<string> {
  const q = query.trim().toLowerCase();
  const hits = new Set<string>();
  if (!q) return hits;
  const filenames = new Map(files.map((f) => [f.id, f.filename.toLowerCase()]));
  const visit = (row: BomRow): boolean => {
    const rowFiles = [row.primary_file_id, ...row.supporting_file_ids];
    const own =
      (row.part_number ?? '').toLowerCase().includes(q) ||
      (row.description ?? '').toLowerCase().includes(q) ||
      row.row_type.includes(q) ||
      (typeLabels?.get(row.row_type) ?? '').toLowerCase().includes(q) ||
      rowFiles.some((id) => (id ? (filenames.get(id) ?? '').includes(q) : false));
    const childHit = row.children.map(visit).some(Boolean);
    if (own || childHit) hits.add(row.row_id);
    return own || childHit;
  };
  visit(doc.root);
  return hits;
}

// --------------------------------------------------------------------------- #
// Snapshot undo/redo (the viewer/annotations.ts reducer pattern)
// --------------------------------------------------------------------------- #
export interface BuilderDocState {
  doc: BomDoc;
  undoStack: BomDoc[];
  redoStack: BomDoc[];
  /** Bumps on every committed edit — the autosave effect keys on it. */
  dirtySeq: number;
}

export type DocAction =
  | { kind: 'edit'; doc: BomDoc }
  | { kind: 'undo' }
  | { kind: 'redo' }
  | { kind: 'reset'; doc: BomDoc };

const UNDO_LIMIT = 100;

export function initialDocState(doc: BomDoc): BuilderDocState {
  return { doc, undoStack: [], redoStack: [], dirtySeq: 0 };
}

export function docReducer(state: BuilderDocState, action: DocAction): BuilderDocState {
  switch (action.kind) {
    case 'edit': {
      if (action.doc === state.doc) return state;
      return {
        doc: action.doc,
        undoStack: [...state.undoStack.slice(-(UNDO_LIMIT - 1)), state.doc],
        redoStack: [],
        dirtySeq: state.dirtySeq + 1,
      };
    }
    case 'undo': {
      const prev = state.undoStack.at(-1);
      if (!prev) return state;
      return {
        doc: prev,
        undoStack: state.undoStack.slice(0, -1),
        redoStack: [...state.redoStack, state.doc],
        dirtySeq: state.dirtySeq + 1,
      };
    }
    case 'redo': {
      const next = state.redoStack.at(-1);
      if (!next) return state;
      return {
        doc: next,
        undoStack: [...state.undoStack, state.doc],
        redoStack: state.redoStack.slice(0, -1),
        dirtySeq: state.dirtySeq + 1,
      };
    }
    case 'reset':
      return initialDocState(action.doc);
    default:
      return state;
  }
}
