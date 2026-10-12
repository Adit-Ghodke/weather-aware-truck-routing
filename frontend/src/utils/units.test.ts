import { describe, expect, it } from 'vitest';
import { formatDistance, formatDuration, formatWeight } from './units';

describe('formatDistance', () => {
  it('formats miles correctly', () => {
    expect(formatDistance(512.4)).toBe('512.4 mi');
    expect(formatDistance(0)).toBe('0.0 mi');
  });
});

describe('formatDuration', () => {
  it('formats minutes into hours and minutes', () => {
    expect(formatDuration(487)).toBe('8 hr 7 min');
    expect(formatDuration(60)).toBe('1 hr');
    expect(formatDuration(45)).toBe('45 min');
  });
});

describe('formatWeight', () => {
  it('formats load weight with commas', () => {
    expect(formatWeight(35000)).toBe('35,000 lb');
  });
});
