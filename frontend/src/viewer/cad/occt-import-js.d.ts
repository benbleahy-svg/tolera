// occt-import-js ships no typings; this covers the surface parseStep uses.
declare module 'occt-import-js' {
  interface OcctBrepFace {
    /** first/last triangle index (inclusive) of this face within `index`. */
    first: number;
    last: number;
    color: [number, number, number] | null;
  }

  interface OcctMesh {
    name?: string;
    color?: [number, number, number];
    attributes: {
      position: { array: number[] };
      normal?: { array: number[] };
    };
    index: { array: number[] };
    brep_faces?: OcctBrepFace[];
  }

  interface OcctReadResult {
    success: boolean;
    meshes: OcctMesh[];
  }

  interface OcctReadParams {
    linearUnit?: 'millimeter' | 'centimeter' | 'meter' | 'inch' | 'foot';
    linearDeflectionType?: 'bounding_box_ratio' | 'absolute_value';
    linearDeflection?: number;
    angularDeflection?: number;
  }

  interface OcctModule {
    ReadStepFile(content: Uint8Array, params: OcctReadParams | null): OcctReadResult;
  }

  interface OcctInitOptions {
    locateFile?: (path: string, scriptDirectory: string) => string;
  }

  export default function occtimportjs(options?: OcctInitOptions): Promise<OcctModule>;
}
