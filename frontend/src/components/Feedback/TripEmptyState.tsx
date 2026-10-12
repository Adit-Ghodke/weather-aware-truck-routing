import type { FC } from 'react';
import { Box, Paper, Typography } from '@mui/material';
import { ShieldCheck, Wind, CloudSnow, Clock } from 'lucide-react';

export const TripEmptyState: FC = () => {
  return (
    <Paper
      elevation={0}
      sx={{
        p: 3,
        borderRadius: 3,
        bgcolor: 'rgba(17, 24, 39, 0.45)',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        my: 2,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
        <Box
          sx={{
            width: 36,
            height: 36,
            borderRadius: 2,
            bgcolor: 'rgba(56, 189, 248, 0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <ShieldCheck size={20} color="#38BDF8" />
        </Box>
        <Box>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#F3F4F6' }}>
            Dispatch Safety Engine Ready
          </Typography>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            Configure trip parameters above or select a preset to analyze routes.
          </Typography>
        </Box>
      </Box>

      <Typography variant="body2" sx={{ color: '#94A3B8', fontSize: '0.8rem', mb: 2, lineHeight: 1.5 }}>
        SafeHaul queries multiple route corridors from Mapbox, samples checkpoints at precise mile intervals, and evaluates weather risk at each point based on load weight:
      </Typography>

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Wind size={15} color="#38BDF8" style={{ marginTop: 2, flexShrink: 0 }} />
          <Typography variant="caption" sx={{ color: '#CBD5E1', fontSize: '0.75rem' }}>
            <strong>Load-Sensitive Wind:</strong> Heavy loads (&gt;30k lb and &gt;40k lb) escalate severe risk thresholds to prevent rollovers.
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <CloudSnow size={15} color="#A855F7" style={{ marginTop: 2, flexShrink: 0 }} />
          <Typography variant="caption" sx={{ color: '#CBD5E1', fontSize: '0.75rem' }}>
            <strong>Precipitation Bounds:</strong> Rain &gt; 1.0 in/hr or Snow &gt; 3.0 in/hr triggers No Travel recommendations.
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Clock size={15} color="#10B981" style={{ marginTop: 2, flexShrink: 0 }} />
          <Typography variant="caption" sx={{ color: '#CBD5E1', fontSize: '0.75rem' }}>
            <strong>Dynamic ETA Forecasting:</strong> Hourly weather is sampled precisely when the truck arrives at each milepost.
          </Typography>
        </Box>
      </Box>
    </Paper>
  );
};
