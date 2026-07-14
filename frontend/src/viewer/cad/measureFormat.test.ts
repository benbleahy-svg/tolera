/**
 * Display formatting for the selection/readout numbers. Base units in (mm,
 * mm², mm³, kg, deg); M2.9 adds the display-options gear: a metric↔imperial
 * unit system and a user decimal-precision. The DACH default stays metric —
 * mm / mm² / cm³ / kg / deg with comma-decimals (de-DE), never imperial by
 * default (DACH-DELTA §6). Angle is always whole degrees; mass keeps a
 * 3-decimal floor (grams matter on small parts) regardless of the slider.
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

describe('measure formatting (de — DACH metric default)', () => {
  it('lengths in mm with a comma decimal', () => {
    expect(formatLength(8, { language: 'de' })).toBe('8,00 mm');
    expect(formatLength(20.5, { language: 'de' })).toBe('20,50 mm');
  });

  it('areas in mm²', () => {
    expect(formatArea(349.73, { language: 'de' })).toBe('349,73 mm²');
  });

  it('volumes converted mm³ → cm³', () => {
    // 3497.35 mm³ = 3.49735 cm³
    expect(formatVolume(3497.35, { language: 'de' })).toBe('3,50 cm³');
  });

  it('mass in kg (3-decimal floor), em-dash when unknown', () => {
    expect(formatMass(0.0275, { language: 'de' })).toBe('0,028 kg'); // round half away from zero
    expect(formatMass(0.0123, { language: 'de' })).toBe('0,012 kg');
    expect(formatMass(null, { language: 'de' })).toBe('—');
  });

  it('angles in whole degrees', () => {
    expect(formatAngle(360, { language: 'de' })).toBe('360°');
    expect(formatAngle(90, { language: 'de' })).toBe('90°');
  });

  it('measure distance carries a leading ~ only when approximate', () => {
    // exact (special orientation) → no prefix, the estimator-trust signal
    expect(formatMeasureDistance(10, true, { language: 'de' })).toBe('10,00 mm');
    // approximate → leading ~
    expect(formatMeasureDistance(14.28, false, { language: 'de' })).toBe('~14,28 mm');
  });

  it('renders an em-dash for null / non-finite values', () => {
    expect(formatLength(null, { language: 'de' })).toBe('—');
    expect(formatArea(NaN, { language: 'de' })).toBe('—');
    expect(formatVolume(null, { language: 'de' })).toBe('—');
    expect(formatAngle(null, { language: 'de' })).toBe('—');
  });
});

describe('measure formatting (en)', () => {
  it('uses a period decimal but keeps metric units by default', () => {
    expect(formatLength(20.5, { language: 'en' })).toBe('20.50 mm');
    expect(formatVolume(3497.35, { language: 'en' })).toBe('3.50 cm³');
  });
});

describe('imperial unit system (opt-in — never the DACH default)', () => {
  const en = { language: 'en', system: 'imperial' } as const;

  it('lengths convert mm → in (25.4 mm = 1 in)', () => {
    expect(formatLength(25.4, en)).toBe('1.00 in');
    expect(formatLength(50.8, en)).toBe('2.00 in');
  });

  it('areas convert mm² → in² (645.16 mm² = 1 in²)', () => {
    expect(formatArea(645.16, en)).toBe('1.00 in²');
  });

  it('volumes convert mm³ → in³ (16387.064 mm³ = 1 in³)', () => {
    expect(formatVolume(16387.064, en)).toBe('1.00 in³');
  });

  it('mass converts kg → lb (1 kg = 2.2046 lb)', () => {
    expect(formatMass(1, en)).toBe('2.205 lb');
  });

  it('angle stays degrees regardless of unit system', () => {
    expect(formatAngle(90, en)).toBe('90°');
  });

  it('comma decimals still follow the German locale under imperial', () => {
    expect(formatLength(25.4, { language: 'de', system: 'imperial' })).toBe('1,00 in');
  });
});

describe('decimal precision (live, user-set)', () => {
  it('drives length/area/volume digits', () => {
    expect(formatLength(20.4, { language: 'de', precision: 0 })).toBe('20 mm');
    expect(formatLength(20.5, { language: 'de', precision: 4 })).toBe('20,5000 mm');
    expect(formatArea(349.7, { language: 'de', precision: 1 })).toBe('349,7 mm²');
    expect(formatVolume(3497.35, { language: 'de', precision: 3 })).toBe('3,497 cm³');
  });

  it('mass keeps a 3-decimal floor but rises with precision', () => {
    // precision below the floor → still 3 decimals
    expect(formatMass(0.0275, { language: 'de', precision: 0 })).toBe('0,028 kg');
    // precision above the floor → follows the slider
    expect(formatMass(0.0275, { language: 'de', precision: 5 })).toBe('0,02750 kg');
  });

  it('angle ignores precision (always whole degrees)', () => {
    expect(formatAngle(90, { language: 'de', precision: 4 })).toBe('90°');
  });
});
