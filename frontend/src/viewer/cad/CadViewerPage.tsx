/**
 * 3D viewer page (M2.6) — placeholder shell; the full viewer (worker-backed
 * MeshProvider, three.js canvas, tree, readout) lands in the next slice.
 */
import type { PartFile } from '../../parts/api';

export function CadViewerPage({ file }: { file: PartFile }) {
  return <main className="viewer-page" data-file={file.id} />;
}
