// The acceptance oracle, as data. Mirrors build-plan/DEMOS-TRACEABILITY.md (the master matrix).
// DRY: this is a pointer table — the authoritative narrative lives in the spec (#demos / #acceptance)
// and the visual truth in docs/reference/screenshots/DemoX/. Don't restate demo steps here.
//
// Note: the matrix lists 15 rows (A–O); the spec calls them "14" because Demo H is *progressive*
// (a grab-bag with no single fixture). It's included here, tagged `progressive`.

export type DemoKind = 'spine' | 'breadth' | 'progressive';

export interface Demo {
  id: string;            // A–O
  title: string;
  kind: DemoKind;        // spine = golden thread, exact figures
  firstReplayable: string; // milestone the demo first replays fully
  milestones: string[];
  screenshots: string;   // dir, relative to repo root
  fixture: string;       // what the replay asserts
}

export const DEMOS: Demo[] = [
  { id: 'A', title: 'Precision Cut + Global Shop ERP', kind: 'spine', firstReplayable: 'M4', milestones: ['M4', 'M1', 'M2', 'M6'], screenshots: 'docs/reference/screenshots/DemoA/', fixture: 'assembly PDF → BOM → nest → cost rollup' },
  { id: 'B', title: 'Arch Medial Solutions', kind: 'spine', firstReplayable: 'M5', milestones: ['M3', 'M2', 'M4', 'M1', 'M5'], screenshots: 'docs/reference/screenshots/DemoB/', fixture: 'RFQ email → quote → … → Build Order' },
  { id: 'C', title: 'Requirements Review', kind: 'breadth', firstReplayable: 'M3', milestones: ['M2', 'M3', 'M1'], screenshots: 'docs/reference/screenshots/DemoC/', fixture: 'rule library works end-to-end' },
  { id: 'D', title: 'Meet the BOM Builder', kind: 'breadth', firstReplayable: 'M4', milestones: ['M2', 'M3', 'M4'], screenshots: 'docs/reference/screenshots/DemoD/', fixture: 'split → detect → publish multi-level BOM' },
  { id: 'E', title: 'Custom Markups & Margins', kind: 'spine', firstReplayable: 'M1', milestones: ['M1'], screenshots: 'docs/reference/screenshots/DemoE/', fixture: 'M1.13: all six figures incl. golden 2160.84' },
  { id: 'F', title: 'Free Part Viewer / Collaboration / Sourcing', kind: 'breadth', firstReplayable: 'M6', milestones: ['M2', 'M6'], screenshots: 'docs/reference/screenshots/DemoF/', fixture: 'vendor RFQ round-trip' },
  { id: 'G', title: 'Costing Templates & Dynamic Routing', kind: 'breadth', firstReplayable: 'M4', milestones: ['M1', 'M4'], screenshots: 'docs/reference/screenshots/DemoG/', fixture: 'auto-routing generates the router' },
  { id: 'H', title: '2025 “Hidden Gems” Roundup', kind: 'progressive', firstReplayable: 'progressive', milestones: ['M1', 'M2', 'M5'], screenshots: 'docs/reference/screenshots/DemoH/', fixture: 'per-feature; no single fixture' },
  { id: 'I', title: 'Sheet Metal Fabricators (overview)', kind: 'breadth', firstReplayable: 'M4', milestones: ['M4', 'M1'], screenshots: 'docs/reference/screenshots/DemoI/', fixture: 'sheet-metal interrogate → nest → cost' },
  { id: 'J', title: 'Nesting deep-dive', kind: 'breadth', firstReplayable: 'M4', milestones: ['M4'], screenshots: 'docs/reference/screenshots/DemoJ/', fixture: 'nest math = hand-calc' },
  { id: 'K', title: 'CNC Machine Shops (overview)', kind: 'breadth', firstReplayable: 'M5', milestones: ['M4', 'M1', 'M5'], screenshots: 'docs/reference/screenshots/DemoK/', fixture: 'milling quote → order' },
  { id: 'L', title: 'Real-time Purchased Components', kind: 'breadth', firstReplayable: 'M6', milestones: ['M4', 'M6'], screenshots: 'docs/reference/screenshots/DemoL/', fixture: 'Würth adapter live pricing' },
  { id: 'M', title: 'Assembly Table Updates', kind: 'breadth', firstReplayable: 'M4', milestones: ['M4'], screenshots: 'docs/reference/screenshots/DemoM/', fixture: 'bulk-edit components + table ops' },
  { id: 'N', title: 'Geometric Feature Overview (no CAD license)', kind: 'breadth', firstReplayable: 'M4', milestones: ['M4'], screenshots: 'docs/reference/screenshots/DemoN/', fixture: 'per-family interrogation goldens' },
  { id: 'O', title: 'Quoting Assemblies', kind: 'breadth', firstReplayable: 'M4', milestones: ['M4', 'M1', 'M2'], screenshots: 'docs/reference/screenshots/DemoO/', fixture: 'assembly root → child BOM → rollup' },
];
