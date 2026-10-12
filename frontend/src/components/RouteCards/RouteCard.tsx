import type { FC } from 'react';
import { Box, Paper, Typography, Chip } from '@mui/material';
import { CheckCircle2, Clock, MapPin, AlertTriangle } from 'lucide-react';
import type { CandidateRoute } from '../../types/api';
import { formatDistance, formatDuration } from '../../utils/units';
import { RISK_COLORS, ROUTE_LINE_COLORS } from '../../constants';
import { RiskProgressBar } from './RiskProgressBar';

interface RouteCardProps {
  route: CandidateRoute;
  index: number;
  isSelected: boolean;
  isRecommended: boolean;
  onSelect: (routeId: string) => void;
}

export const RouteCard: FC<RouteCardProps> = ({
  route,
  index,
  isSelected,
  isRecommended,
  onSelect,
}) => {
  const routeColor = ROUTE_LINE_COLORS[index % ROUTE_LINE_COLORS.length];
  const worstRiskColor = RISK_COLORS[route.metrics.worst_level] || RISK_COLORS.Low;

  return (
    <Paper
      elevation={0}
      onClick={() => onSelect(route.id)}
      sx={{
        p: 2,
        borderRadius: 2.5,
        cursor: 'pointer',
        bgcolor: isSelected ? 'rgba(56, 189, 248, 0.08)' : 'rgba(17, 24, 39, 0.65)',
        border: '1px solid',
        borderColor: isSelected ? '#38BDF8' : 'rgba(255, 255, 255, 0.08)',
        transition: 'all 0.2s ease',
        position: 'relative',
        overflow: 'hidden',
        '&:hover': {
          borderColor: isSelected ? '#38BDF8' : 'rgba(255, 255, 255, 0.2)',
          bgcolor: isSelected ? 'rgba(56, 189, 248, 0.1)' : 'rgba(17, 24, 39, 0.85)',
          transform: 'translateY(-1px)',
        },
      }}
    >
      {/* Top row: Route index badge, label, and Recommended chip */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box
            sx={{
              px: 1.25,
              py: 0.35,
              borderRadius: 1.2,
              bgcolor: 'rgba(255, 255, 255, 0.08)',
              border: `2px solid ${routeColor}`,
              color: routeColor,
              fontWeight: 800,
              fontSize: '0.875rem',
            }}
          >
            R{index + 1}
          </Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#F8FAFC', fontSize: '0.975rem' }}>
            {route.label}
          </Typography>
        </Box>

        {isRecommended && (
          <Chip
            icon={<CheckCircle2 size={15} color="#10B981" />}
            label="RECOMMENDED"
            size="small"
            sx={{
              bgcolor: 'rgba(16, 185, 129, 0.2)',
              color: '#34D399',
              border: '1.5px solid rgba(16, 185, 129, 0.5)',
              fontWeight: 800,
              fontSize: '0.8rem',
              height: 26,
            }}
          />
        )}
      </Box>

      {/* Metric badges: Distance, Duration, Worst Risk */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap', mb: 1.25 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
          <MapPin size={16} color="#38BDF8" />
          <Typography variant="body1" sx={{ fontWeight: 700, color: '#F1F5F9', fontSize: '0.95rem' }}>
            {formatDistance(route.distance_miles)}
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
          <Clock size={16} color="#38BDF8" />
          <Typography variant="body1" sx={{ fontWeight: 700, color: '#F1F5F9', fontSize: '0.95rem' }}>
            {formatDuration(route.duration_minutes)}
          </Typography>
        </Box>

        <Box sx={{ ml: 'auto' }}>
          <Chip
            icon={<AlertTriangle size={14} color={worstRiskColor} />}
            label={`Worst: ${route.metrics.worst_level}`}
            size="small"
            sx={{
              bgcolor: `${worstRiskColor}25`,
              color: worstRiskColor,
              border: `1.5px solid ${worstRiskColor}66`,
              fontWeight: 700,
              fontSize: '0.825rem',
              height: 26,
            }}
          />
        </Box>
      </Box>

      {/* Segmented Risk Progress Bar */}
      <RiskProgressBar metrics={route.metrics} totalMiles={route.distance_miles} />
    </Paper>
  );
};
