import { describe, expect, it } from 'vitest';
import type { RiskLevel } from '../types/api';
import { riskIntToLevel, riskLevelToBgColor, riskLevelToColor } from './risk';

describe('risk utilities', () => {
  const levels: RiskLevel[] = ['Low', 'Moderate', 'High', 'Severe', 'No Travel'];

  it('returns valid colors for all 5 risk levels', () => {
    levels.forEach((level) => {
      const color = riskLevelToColor(level);
      expect(color).toBeDefined();
      expect(color.startsWith('#')).toBe(true);

      const bg = riskLevelToBgColor(level);
      expect(bg).toBeDefined();
      expect(bg.startsWith('rgba')).toBe(true);
    });
  });

  it('maps integer risk values to correct risk levels', () => {
    expect(riskIntToLevel(0)).toBe('Low');
    expect(riskIntToLevel(1)).toBe('Moderate');
    expect(riskIntToLevel(2)).toBe('High');
    expect(riskIntToLevel(3)).toBe('Severe');
    expect(riskIntToLevel(4)).toBe('No Travel');
  });
});
