import type { FC } from 'react';
import { Box, Paper, Skeleton, Typography, CircularProgress } from '@mui/material';

export const TripLoadingSkeleton: FC = () => {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, my: 2 }}>
      {/* Loading banner */}
      <Paper
        elevation={0}
        sx={{
          p: 2.5,
          borderRadius: 2.5,
          bgcolor: 'rgba(56, 189, 248, 0.05)',
          border: '1px solid rgba(56, 189, 248, 0.25)',
          display: 'flex',
          alignItems: 'center',
          gap: 2,
        }}
      >
        <CircularProgress size={26} sx={{ color: '#38BDF8' }} />
        <Box>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#38BDF8' }}>
            Evaluating Route Weather Hazards
          </Typography>
          <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
            Sampling route intervals, fetching Open-Meteo hourly forecasts, and calculating cargo risk boundaries...
          </Typography>
        </Box>
      </Paper>

      {/* Skeletons for 3 candidate routes */}
      {[1, 2, 3].map((key) => (
        <Paper
          key={key}
          elevation={0}
          sx={{
            p: 2,
            borderRadius: 2.5,
            bgcolor: 'rgba(17, 24, 39, 0.5)',
            border: '1px solid rgba(255, 255, 255, 0.06)',
          }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1.5 }}>
            <Skeleton variant="text" width={160} height={24} sx={{ bgcolor: 'rgba(255, 255, 255, 0.08)' }} />
            <Skeleton variant="rounded" width={80} height={20} sx={{ bgcolor: 'rgba(255, 255, 255, 0.08)' }} />
          </Box>
          <Box sx={{ display: 'flex', gap: 2, mb: 1.5 }}>
            <Skeleton variant="text" width={90} height={20} sx={{ bgcolor: 'rgba(255, 255, 255, 0.08)' }} />
            <Skeleton variant="text" width={80} height={20} sx={{ bgcolor: 'rgba(255, 255, 255, 0.08)' }} />
            <Skeleton variant="text" width={100} height={20} sx={{ bgcolor: 'rgba(255, 255, 255, 0.08)', ml: 'auto' }} />
          </Box>
          <Skeleton variant="rounded" width="100%" height={8} sx={{ bgcolor: 'rgba(255, 255, 255, 0.08)', borderRadius: 1 }} />
        </Paper>
      ))}
    </Box>
  );
};
