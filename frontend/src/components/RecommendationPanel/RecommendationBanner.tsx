import type { FC } from 'react';
import { Box, Paper, Typography, Alert } from '@mui/material';
import { ShieldCheck, AlertTriangle } from 'lucide-react';
import type { RouteRecommendation } from '../../types/api';

interface RecommendationBannerProps {
  recommendation: RouteRecommendation;
}

export const RecommendationBanner: FC<RecommendationBannerProps> = ({ recommendation }) => {
  const isAllSevere = recommendation.status === 'not_recommended_all_routes';

  return (
    <Paper
      elevation={0}
      sx={{
        p: 2.5,
        borderRadius: 2.5,
        bgcolor: isAllSevere ? 'rgba(239, 68, 68, 0.08)' : 'rgba(16, 185, 129, 0.08)',
        border: '1px solid',
        borderColor: isAllSevere ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.3)',
        mb: 2,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
        {isAllSevere ? (
          <AlertTriangle size={22} color="#EF4444" />
        ) : (
          <ShieldCheck size={22} color="#10B981" />
        )}
        <Typography
          variant="subtitle1"
          sx={{
            fontWeight: 700,
            color: isAllSevere ? '#EF4444' : '#10B981',
            lineHeight: 1.2,
          }}
        >
          {isAllSevere ? 'Caution: Severe Weather On All Routes' : 'SafeHaul Engine Recommendation'}
        </Typography>
      </Box>

      <Typography variant="body2" sx={{ color: '#E2E8F0', mb: recommendation.warning ? 1.5 : 0, lineHeight: 1.5 }}>
        {recommendation.explanation}
      </Typography>

      {recommendation.warning && (
        <Alert
          severity="warning"
          icon={<AlertTriangle size={16} />}
          sx={{
            bgcolor: 'rgba(245, 158, 11, 0.12)',
            color: '#F59E0B',
            border: '1px solid rgba(245, 158, 11, 0.3)',
            p: '4px 10px',
            '& .MuiAlert-message': { fontSize: '0.78rem' },
          }}
        >
          {recommendation.warning}
        </Alert>
      )}
    </Paper>
  );
};
