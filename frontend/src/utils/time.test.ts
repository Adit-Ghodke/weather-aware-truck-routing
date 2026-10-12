import { describe, expect, it } from 'vitest';
import { formatDateTime, formatETA, formatLocalETA } from './time';

describe('time utilities', () => {
  it('formats ETA correctly', () => {
    const formatted = formatETA('2025-01-20T14:30:00Z');
    expect(formatted).toBeDefined();
    expect(formatted).not.toBe('--');
  });

  it('formats local ETA with timezone abbreviation', () => {
    const formatted = formatLocalETA('2025-01-20T14:30:00Z', 'CST');
    expect(formatted).toContain('CST');
  });

  it('handles invalid strings gracefully', () => {
    expect(formatETA('')).toBe('--');
    expect(formatDateTime('')).toBe('--');
    expect(formatLocalETA('', 'CST')).toBe('--');
  });
});
