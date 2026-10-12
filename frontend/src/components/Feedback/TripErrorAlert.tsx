import type { FC } from 'react';
import { Alert, AlertTitle, Box, Typography } from '@mui/material';
import { AlertCircle } from 'lucide-react';

interface TripErrorAlertProps {
  error: string;
  onDismiss?: () => void;
}

export const TripErrorAlert: FC<TripErrorAlertProps> = ({ error, onDismiss }) => {
  return (
    <Box sx={{ my: 2 }}>
      <Alert
        severity="error"
        icon={<AlertCircle size={20} />}
        onClose={onDismiss}
        sx={{
          borderRadius: 2.5,
          bgcolor: 'rgba(239, 68, 68, 0.12)',
          color: '#F87171',
          border: '1px solid rgba(239, 68, 68, 0.35)',
          '& .MuiAlert-icon': { color: '#EF4444' },
        }}
      >
        <AlertTitle sx={{ fontWeight: 700, fontSize: '0.9rem', mb: 0.5 }}>
          Trip Evaluation Failed
        </AlertTitle>
        <Typography variant="body2" sx={{ color: '#FECACA', fontSize: '0.8rem', mb: 1 }}>
          {error}
        </Typography>
        <Typography variant="caption" sx={{ color: '#FCA5A5', display: 'block', fontSize: '0.75rem' }}>
          Tip: Verify origin and destination coordinates, confirm departure time is within the next 7 days, or select a preset corridor.
        </Typography>
      </Alert>
    </Box>
  );
};
