/**
 * Formatting helpers for distance, travel time, and load weights.
 */

export function formatDistance(miles: number): string {
  if (miles == null || isNaN(miles)) return '0.0 mi';
  return `${miles.toFixed(1)} mi`;
}

export function formatDuration(minutes: number): string {
  if (minutes == null || isNaN(minutes) || minutes < 0) return '0 min';
  const hrs = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);

  if (hrs === 0) {
    return `${mins} min`;
  }
  if (mins === 0) {
    return `${hrs} hr`;
  }
  return `${hrs} hr ${mins} min`;
}

export function formatWeight(lbs: number): string {
  if (lbs == null || isNaN(lbs)) return '0 lb';
  return `${lbs.toLocaleString()} lb`;
}
