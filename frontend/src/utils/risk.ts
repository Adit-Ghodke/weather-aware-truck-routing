import { RISK_BG_COLORS, RISK_COLORS, RISK_INT_TO_LEVEL } from '../constants';
import type { RiskLevel } from '../types/api';


export function riskLevelToColor(level: RiskLevel): string {
  return RISK_COLORS[level] || RISK_COLORS.Low;
}

export function riskLevelToBgColor(level: RiskLevel): string {
  return RISK_BG_COLORS[level] || RISK_BG_COLORS.Low;
}

export function riskIntToLevel(val: number): RiskLevel {
  return RISK_INT_TO_LEVEL[val] || 'Low';
}
