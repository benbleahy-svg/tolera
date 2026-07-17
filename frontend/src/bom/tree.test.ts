/**
 * BOM document logic (M4.9): decimal-dot item numbering, unique-parts counting
 * (same part#+rev links as one), Add-Files matching by title-block part number,
 * child-BOM acceptance, and the snapshot undo/redo reducer.
 */

import { describe, expect, it } from 'vitest';

import {
  acceptChildBom,
  applyFileMatches,
  blankRow,
  docReducer,
  initialDocState,
  itemNumbers,
  matchFilesToRows,
  removeRow,
  uniquePartCount,
  updateRow,
} from './tree';
import type { BomDoc, BomRow, QuoteFileOut } from './types';

let seq = 0;

function row(partNumber: string | null, over: Partial<BomRow> = {}): BomRow {
  seq += 1;
  return {
    row_id: `t-${seq}`,
    row_type: 'manufactured',
    part_number: partNumber,
    revision: null,
    description: null,
    qty: 1,
    primary_file_id: null,
    supporting_file_ids: [],
    children: [],
    ...over,
  };
}

function doc(children: BomRow[]): BomDoc {
  return {
    schema_version: 1,
    root: row('ROOT-1', { row_type: 'assembly_root', children }),
  };
}

function file(id: string, partNumber: string | null): QuoteFileOut {
  return {
    id,
    part_id: 'p-root',
    filename: `${partNumber ?? id}.pdf`,
    role: 'supporting',
    part_number_extracted: partNumber,
    has_bom_table: false,
  };
}

describe('itemNumbers', () => {
  it('derives decimal-dot numbering from tree position (DemoD/09)', () => {
    const sub = row('SUB-1', {
      row_type: 'subassembly',
      children: [row('A'), row('B', { children: [row('C')] })],
    });
    const d = doc([sub, row('D')]);
    const numbers = itemNumbers(d);
    expect(numbers.get(d.root.row_id)).toBe('Root');
    expect(numbers.get(sub.row_id)).toBe('1');
    expect(numbers.get(sub.children[0].row_id)).toBe('1.1');
    expect(numbers.get(sub.children[1].row_id)).toBe('1.2');
    expect(numbers.get(sub.children[1].children[0].row_id)).toBe('1.2.1');
    expect(numbers.get(d.root.children[1].row_id)).toBe('2');
  });
});

describe('uniquePartCount', () => {
  it('links rows with the same part#+rev as ONE part (KB FAQ)', () => {
    const d = doc([
      row('SUB-A', { row_type: 'subassembly', children: [row('SHARED')] }),
      row('SUB-B', { row_type: 'subassembly', children: [row('SHARED')] }),
    ]);
    // root + SUB-A + SUB-B + SHARED(once) = 4
    expect(uniquePartCount(d)).toBe(4);
  });

  it('counts keyless rows individually and separates revisions', () => {
    const d = doc([
      row(null),
      row(null),
      row('X', { revision: '000' }),
      row('X', { revision: '001' }),
    ]);
    expect(uniquePartCount(d)).toBe(5);
  });
});

describe('matchFilesToRows', () => {
  it('pairs unassigned rows to files by extracted part number, case-insensitive', () => {
    const a = row('002-00008-000');
    const b = row('002-00025-000', { primary_file_id: 'already' });
    const d = doc([a, b]);
    const files = [
      file('f1', '002-00008-000'),
      file('f2', '002-00025-000'),
      file('f3', null),
    ];
    const matches = matchFilesToRows(d, files);
    expect(matches).toEqual([{ rowId: a.row_id, fileId: 'f1' }]);
    const applied = applyFileMatches(d, matches);
    expect(applied.root.children[0].primary_file_id).toBe('f1');
    // The source doc is untouched (immutability).
    expect(d.root.children[0].primary_file_id).toBeNull();
  });

  it('never assigns one file to two rows', () => {
    const a = row('PN-1');
    const b = row('PN-1', { revision: 'B' });
    const d = doc([a, b]);
    const matches = matchFilesToRows(d, [file('f1', 'pn-1')]);
    expect(matches).toHaveLength(1);
  });
});

describe('acceptChildBom', () => {
  it('converts the row to a subassembly and inserts extracted children', () => {
    const target = row('002-00008-000');
    const d = doc([target]);
    const accepted = acceptChildBom(d, target.row_id, [
      {
        item_no: '1',
        part_number: '002-00009-000',
        revision: '000',
        qty: 2,
        description: 'Corner bracket',
        type_hint: null,
      },
      {
        item_no: '2',
        part_number: '002-00006-000',
        revision: null,
        qty: 14,
        description: null,
        type_hint: 'purchased',
      },
    ]);
    const converted = accepted.root.children[0];
    expect(converted.row_type).toBe('subassembly');
    expect(converted.children.map((c) => c.part_number)).toEqual([
      '002-00009-000',
      '002-00006-000',
    ]);
    expect(converted.children.map((c) => c.row_type)).toEqual(['manufactured', 'purchased']);
    expect(converted.children.map((c) => c.qty)).toEqual([2, 14]);
  });
});

describe('docReducer (snapshot undo/redo)', () => {
  it('undoes and redoes committed edits; a new edit clears the redo stack', () => {
    const d0 = doc([]);
    let state = initialDocState(d0);
    const d1 = { ...d0, root: { ...d0.root, children: [row('A')] } };
    state = docReducer(state, { kind: 'edit', doc: d1 });
    expect(state.doc).toBe(d1);
    expect(state.dirtySeq).toBe(1);

    state = docReducer(state, { kind: 'undo' });
    expect(state.doc).toBe(d0);
    state = docReducer(state, { kind: 'redo' });
    expect(state.doc).toBe(d1);

    state = docReducer(state, { kind: 'undo' });
    const d2 = { ...d0, root: { ...d0.root, children: [row('B')] } };
    state = docReducer(state, { kind: 'edit', doc: d2 });
    expect(state.redoStack).toHaveLength(0);
    expect(docReducer(state, { kind: 'redo' })).toBe(state);
  });
});

describe('updateRow / removeRow', () => {
  it('edits and removes nested rows immutably', () => {
    const child = row('DEEP');
    const sub = row('SUB', { row_type: 'subassembly', children: [child] });
    const d = doc([sub]);
    const edited = updateRow(d, child.row_id, (r) => ({ ...r, qty: 7 }));
    expect(edited.root.children[0].children[0].qty).toBe(7);
    expect(d.root.children[0].children[0].qty).toBe(1);
    const removed = removeRow(d, child.row_id);
    expect(removed.root.children[0].children).toHaveLength(0);
  });
});

describe('blankRow', () => {
  it('mints unique ids', () => {
    expect(blankRow().row_id).not.toBe(blankRow().row_id);
  });
});
