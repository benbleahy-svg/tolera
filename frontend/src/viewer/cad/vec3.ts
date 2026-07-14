/**
 * Minimal branch-free vector-3 ops shared by the CAD viewer's geometry modules
 * (selection fits + measure math). Deliberately free of any degenerate-case
 * policy: `normalize`, whose zero-length fallback differs by caller (selection
 * wants a +Z default for axis bases, measure wants a zero → "not collinear"),
 * stays local to each module. Types-only `model.ts` owns {@link Vec3}.
 */
import type { Vec3 } from './model';

export function add(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}
export function sub(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}
export function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}
export function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}
export function len(a: Vec3): number {
  return Math.sqrt(dot(a, a));
}
export function scale(a: Vec3, s: number): Vec3 {
  return [a[0] * s, a[1] * s, a[2] * s];
}
