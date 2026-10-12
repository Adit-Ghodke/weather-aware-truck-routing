import type { FC } from 'react';
import { Box, Typography } from '@mui/material';
import type { CandidateRoute } from '../../types/api';
import { RouteCard } from './RouteCard';

interface RouteCardListProps {
  routes: CandidateRoute[];
  selectedRouteId: string | null;
  recommendedRouteId?: string;
  onSelectRoute: (routeId: string) => void;
}

export const RouteCardList: FC<RouteCardListProps> = ({
  routes,
  selectedRouteId,
  recommendedRouteId,
  onSelectRoute,
}) => {
  if (!routes || routes.length === 0) {
    return null;
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, my: 2 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.75rem' }}>
        Candidate Routes ({routes.length})
      </Typography>

      {routes.map((route, idx) => (
        <RouteCard
          key={route.id}
          route={route}
          index={idx}
          isSelected={route.id === selectedRouteId}
          isRecommended={route.id === recommendedRouteId}
          onSelect={onSelectRoute}
        />
      ))}
    </Box>
  );
};
