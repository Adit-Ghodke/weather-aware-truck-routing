import type { FC } from 'react';
import {
  Box,
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
} from '@mui/material';
import type { RouteComparisonItem } from '../../types/api';
import { formatDuration } from '../../utils/units';
import { RISK_COLORS, MAX_RISK_SCORE } from '../../constants';

interface ComparisonTableProps {
  comparison: RouteComparisonItem[];
  selectedRouteId: string | null;
  onSelectRoute?: (routeId: string) => void;
}

export const ComparisonTable: FC<ComparisonTableProps> = ({
  comparison,
  selectedRouteId,
  onSelectRoute,
}) => {
  if (!comparison || comparison.length === 0) return null;

  return (
    <Paper
      elevation={0}
      sx={{
        borderRadius: 2.5,
        bgcolor: 'rgba(17, 24, 39, 0.65)',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        overflow: 'hidden',
        mt: 2,
        mb: 2,
      }}
    >
      <Box sx={{ p: 2, borderBottom: '1px solid rgba(255, 255, 255, 0.06)' }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#E2E8F0' }}>
          Route Comparison Matrix
        </Typography>
      </Box>

      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ bgcolor: 'rgba(255, 255, 255, 0.04)', '& th': { color: '#F1F5F9', fontWeight: 700, fontSize: '0.85rem', borderColor: 'rgba(255, 255, 255, 0.1)', py: 1.25 } }}>
              <TableCell>Route</TableCell>
              <TableCell align="right">Distance</TableCell>
              <TableCell align="right">Severe</TableCell>
              <TableCell align="right">High</TableCell>
              <TableCell align="right">No Travel</TableCell>
              <TableCell align="right">Avg Risk</TableCell>
              <TableCell align="right">Duration</TableCell>
              <TableCell align="center">Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {comparison.map((item) => {
              const isSelected = item.route_id === selectedRouteId;
              const hasHazards = item.severe_miles > 0 || item.no_travel_miles > 0;

              return (
                <TableRow
                  key={item.route_id}
                  hover
                  onClick={() => onSelectRoute?.(item.route_id)}
                  sx={{
                    cursor: 'pointer',
                    bgcolor: isSelected ? 'rgba(56, 189, 248, 0.12)' : 'transparent',
                    '& td': {
                      borderColor: 'rgba(255, 255, 255, 0.08)',
                      fontSize: '0.875rem',
                      color: isSelected ? '#38BDF8' : '#F1F5F9',
                      py: 1.25,
                    },
                  }}
                >
                  <TableCell sx={{ fontWeight: 700 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Chip
                        label={`#${item.rank}`}
                        size="small"
                        sx={{
                          height: 24,
                          fontSize: '0.825rem',
                          fontWeight: 800,
                          bgcolor: item.rank === 1 ? 'rgba(16, 185, 129, 0.25)' : 'rgba(255, 255, 255, 0.1)',
                          color: item.rank === 1 ? '#34D399' : '#CBD5E1',
                          border: item.rank === 1 ? '1px solid rgba(16, 185, 129, 0.5)' : 'none',
                        }}
                      />
                      <span style={{ color: isSelected ? '#38BDF8' : '#F8FAFC' }}>{item.label}</span>
                    </Box>
                  </TableCell>

                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    {item.distance_miles ? `${item.distance_miles.toFixed(1)} mi` : '-'}
                  </TableCell>

                  <TableCell align="right" sx={{ color: item.severe_miles > 0 ? `${RISK_COLORS.Severe} !important` : undefined, fontWeight: item.severe_miles > 0 ? 700 : 500 }}>
                    {item.severe_miles.toFixed(1)} mi
                  </TableCell>

                  <TableCell align="right" sx={{ color: item.high_miles > 0 ? `${RISK_COLORS.High} !important` : undefined, fontWeight: item.high_miles > 0 ? 700 : 500 }}>
                    {item.high_miles.toFixed(1)} mi
                  </TableCell>

                  <TableCell align="right" sx={{ color: item.no_travel_miles > 0 ? `${RISK_COLORS['No Travel']} !important` : undefined, fontWeight: item.no_travel_miles > 0 ? 800 : 500 }}>
                    {item.no_travel_miles.toFixed(1)} mi
                  </TableCell>

                  <TableCell align="right" sx={{ fontWeight: 700, color: '#38BDF8' }}>
                    {item.average_risk.toFixed(2)} / {MAX_RISK_SCORE}
                  </TableCell>

                  <TableCell align="right" sx={{ fontWeight: 600 }}>{formatDuration(item.duration_minutes)}</TableCell>

                  <TableCell align="center">
                    <Chip
                      label={item.status === 'ok' && !hasHazards ? 'CLEAR' : item.status === 'no_travel' ? 'BLOCKED' : 'HAZARD'}
                      size="small"
                      sx={{
                        height: 24,
                        fontSize: '0.75rem',
                        fontWeight: 800,
                        bgcolor: item.status === 'no_travel'
                          ? 'rgba(153, 27, 27, 0.2)'
                          : hasHazards
                          ? 'rgba(239, 68, 68, 0.15)'
                          : 'rgba(16, 185, 129, 0.15)',
                        color: item.status === 'no_travel'
                          ? RISK_COLORS['No Travel']
                          : hasHazards
                          ? RISK_COLORS.Severe
                          : RISK_COLORS.Low,
                      }}
                    />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};
