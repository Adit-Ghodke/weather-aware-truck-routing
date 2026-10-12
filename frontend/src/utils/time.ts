/**
 * Time formatting helpers for ETAs and departures.
 */

export function formatETA(isoString: string): string {
  if (!isoString) return '--';
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return isoString;
  }
}

export function formatDateTime(isoString: string): string {
  if (!isoString) return '--';
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  } catch {
    return isoString;
  }
}

export function formatLocalETA(isoString: string, tzAbbr?: string): string {
  if (!isoString) return '--';
  const timeStr = formatDateTime(isoString);
  return tzAbbr ? `${timeStr} ${tzAbbr}` : timeStr;
}
