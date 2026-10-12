import type { FC } from 'react';
import { Box, Paper, Typography } from '@mui/material';
import { RISK_COLORS, ROUTE_LINE_COLORS } from '../../constants';
import type { RiskLevel } from '../../types/api';

const RISK_ITEMS: { level: RiskLevel; label: string }[] = [
  { level: 'Low', label: 'Low (Green)' },
  { level: 'Moderate', label: 'Moderate (Yellow)' },
  { level: 'High', label: 'High (Amber)' },
  { level: 'Severe', label: 'Severe (Red)' },
  { level: 'No Travel', label: 'No Travel (Dark Red)' },
];

export const MapLegend: FC = () => {
  return (
    <Paper
      elevation={0}
      sx={{
        position: 'absolute',
        bottom: 24,
        right: 16,
        p: 1.5,
        borderRadius: 2,
        bgcolor: 'rgba(15, 23, 42, 0.88)',
        backdropFilter: 'blur(8px)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        zIndex: 10,
        maxWidth: 240,
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.5)',
      }}
    >
      <Typography variant="caption" sx={{ fontWeight: 700, color: '#94A3B8', display: 'block', mb: 1, textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.8125rem' }}>
        Weather Risk Levels
      </Typography>

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, mb: 1.5 }}>
        {RISK_ITEMS.map(({ level, label }) => (
          <Box key={level} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box
              sx={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                bgcolor: RISK_COLORS[level],
                boxShadow: `0 0 6px ${RISK_COLORS[level]}`,
              }}
            />
            <Typography variant="caption" sx={{ color: '#E2E8F0', fontSize: '0.8125rem' }}>
              {label}
            </Typography>
          </Box>
        ))}
      </Box>

      <Typography variant="caption" sx={{ fontWeight: 700, color: '#94A3B8', display: 'block', mb: 0.75, textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.8125rem' }}>
        Route Candidates
      </Typography>

      <Box sx={{ display: 'flex', gap: 1 }}>
        {ROUTE_LINE_COLORS.map((color, idx) => (
          <Box key={color} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box sx={{ width: 14, height: 4, borderRadius: 1, bgcolor: color }} />
            <Typography variant="caption" sx={{ color: '#94A3B8', fontSize: '0.8125rem' }}>
              R{idx + 1}
            </Typography>
          </Box>
        ))}
      </Box>
    </Paper>
  );
};
