// occt-import-js ships no typings; this covers the surface parseStep uses.
declare module 'occt-import-js' {
  interface OcctMesh {
    name?: string;
    color?: [number, number, number];
    attributes: {
      position: { array: number[] };
      normal?: { array: number[] };
    };
    index: { array: number[] };
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
