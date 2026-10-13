/**
 * SafeHaul UI Constants — Risk Colors, Labels, and Defaults.
 */

import type { RiskLevel } from './types/api';

export const RISK_COLORS: Record<RiskLevel, string> = {
  Low: '#059669',       // Deep Emerald Green (richer, slightly darker for contrast)
  Moderate: '#EAB308',  // Yellow
  High: '#F59E0B',      // Amber
  Severe: '#EF4444',    // Ruby Red
  'No Travel': '#991B1B', // Deep Crimson
};

export const RISK_BG_COLORS: Record<RiskLevel, string> = {
  Low: 'rgba(5, 150, 105, 0.20)',
  Moderate: 'rgba(234, 179, 8, 0.15)',
  High: 'rgba(245, 158, 11, 0.15)',
  Severe: 'rgba(239, 68, 68, 0.15)',
  'No Travel': 'rgba(153, 27, 27, 0.25)',
};

export const RISK_ORDER: Record<RiskLevel, number> = {
  Low: 0,
  Moderate: 1,
  High: 2,
  Severe: 3,
  'No Travel': 4,
};

export const RISK_INT_TO_LEVEL: Record<number, RiskLevel> = {
  0: 'Low',
  1: 'Moderate',
  2: 'High',
  3: 'Severe',
  4: 'No Travel',
};

// Route line colors for the 3 candidates on the Map
export const ROUTE_LINE_COLORS = [
  '#38BDF8', // Sky Blue (Route 1)
  '#A855F7', // Purple (Route 2)
  '#EC4899', // Pink (Route 3)
];

// Shared maximum risk score for risk progress bars and comparison matrix
export const MAX_RISK_SCORE = 5;

// Fallback Mapbox public token if not set in .env
export const MAPBOX_PUBLIC_TOKEN =
  import.meta.env.VITE_MAPBOX_TOKEN || '';
