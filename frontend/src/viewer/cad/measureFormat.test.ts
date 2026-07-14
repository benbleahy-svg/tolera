/**
 * Display formatting for the selection/readout numbers. Base units in (mm,
 * mm², mm³, kg, deg); the DACH default shows mm / mm² / cm³ / kg / deg with
 * comma-decimals (de-DE), never imperial. Decimal precision is fixed here for
 * M2.7; the user-configurable precision gear is M2.9.
 */
import { describe, expect, it } from 'vitest';

import {
  formatAngle,
  formatArea,
  formatLength,
  formatMass,
  formatMeasureDistance,
  formatVolume,
} from './measureFormat';

describe('measure formatting (de — DACH default)', () => {
  it('lengths in mm with a comma decimal', () => {
    expect(formatLength(8, 'de')).toBe('8,00 mm');
    expect(formatLength(20.5, 'de')).toBe('20,50 mm');
  });

  it('areas in mm²', () => {
    expect(formatArea(349.73, 'de')).toBe('349,73 mm²');
  });

  it('volumes converted mm³ → cm³', () => {
    // 3497.35 mm³ = 3.49735 cm³
    expect(formatVolume(3497.35, 'de')).toBe('3,50 cm³');
  });

  it('mass in kg (3 decimals), em-dash when unknown', () => {
    expect(formatMass(0.0275, 'de')).toBe('0,028 kg'); // round half away from zero
    expect(formatMass(0.0123, 'de')).toBe('0,012 kg');
    expect(formatMass(null, 'de')).toBe('—');
  });

  it('angles in whole degrees', () => {
    expect(formatAngle(360, 'de')).toBe('360°');
    expect(formatAngle(90, 'de')).toBe('90°');
  });

  it('measure distance carries a leading ~ only when approximate', () => {
    // exact (special orientation) → no prefix, the estimator-trust signal
    expect(formatMeasureDistance(10, true, 'de')).toBe('10,00 mm');
    // approximate → leading ~
    expect(formatMeasureDistance(14.28, false, 'de')).toBe('~14,28 mm');
  });

  it('renders an em-dash for null / non-finite values', () => {
    expect(formatLength(null, 'de')).toBe('—');
    expect(formatArea(NaN, 'de')).toBe('—');
    expect(formatVolume(null, 'de')).toBe('—');
    expect(formatAngle(null, 'de')).toBe('—');
  });
});

describe('measure formatting (en)', () => {
  it('uses a period decimal but keeps metric units (no imperial path)', () => {
    expect(formatLength(20.5, 'en')).toBe('20.50 mm');
    expect(formatVolume(3497.35, 'en')).toBe('3.50 cm³');
  });
});
