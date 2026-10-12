import type { FC } from 'react';
import { Box, Tooltip, Typography } from '@mui/material';
import type { RouteMetrics } from '../../types/api';
import { RISK_COLORS, MAX_RISK_SCORE } from '../../constants';

interface RiskProgressBarProps {
  metrics: RouteMetrics;
  totalMiles: number;
}

export const RiskProgressBar: FC<RiskProgressBarProps> = ({ metrics, totalMiles }) => {
  const safeTotal = totalMiles > 0 ? totalMiles : 1;

  const segments = [
    { label: 'Low', miles: metrics.low_miles, color: RISK_COLORS.Low },
    { label: 'Moderate', miles: metrics.moderate_miles, color: RISK_COLORS.Moderate },
    { label: 'High', miles: metrics.high_miles, color: RISK_COLORS.High },
    { label: 'Severe', miles: metrics.severe_miles, color: RISK_COLORS.Severe },
    { label: 'No Travel', miles: metrics.no_travel_miles, color: RISK_COLORS['No Travel'] },
  ].filter((s) => s.miles > 0);

  return (
    <Box sx={{ width: '100%', mt: 1 }}>
      <Box
        sx={{
          display: 'flex',
          height: 10,
          borderRadius: 1.5,
          overflow: 'hidden',
          bgcolor: 'rgba(255, 255, 255, 0.08)',
        }}
      >
        {segments.map((seg) => {
          const pct = Math.max(1, (seg.miles / safeTotal) * 100);
          return (
            <Tooltip
              key={seg.label}
              title={`${seg.label}: ${seg.miles.toFixed(1)} mi (${pct.toFixed(0)}%)`}
              arrow
              placement="top"
            >
              <Box
                sx={{
                  width: `${pct}%`,
                  bgcolor: seg.color,
                  transition: 'width 0.3s ease',
                }}
              />
            </Tooltip>
          );
        })}
      </Box>

      {/* Summary caption under the bar */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.75 }}>
        <Typography variant="body2" sx={{ color: '#CBD5E1', fontSize: '0.875rem' }}>
          {metrics.severe_miles > 0 || metrics.no_travel_miles > 0 ? (
            <span style={{ color: RISK_COLORS.Severe, fontWeight: 700 }}>
              {(metrics.severe_miles + metrics.no_travel_miles).toFixed(1)} mi hazardous weather
            </span>
          ) : (
            <span style={{ color: RISK_COLORS.Low, fontWeight: 700 }}>Safe weather corridor</span>
          )}
        </Typography>
        <Typography variant="body2" sx={{ color: '#F1F5F9', fontSize: '0.875rem', fontWeight: 700 }}>
          Avg Risk: <span style={{ color: '#38BDF8' }}>{metrics.average_risk.toFixed(2)}</span> / {MAX_RISK_SCORE}
        </Typography>
      </Box>
    </Box>
  );
};
