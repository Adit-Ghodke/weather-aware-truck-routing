import { useState, lazy, Suspense } from 'react';
import {
  AppBar,
  Box,
  Paper,
  Toolbar,
  Typography,
  Grid,
} from '@mui/material';
import { Truck, Navigation } from 'lucide-react';
import { TripForm } from './components/TripForm';
import { RouteCardList } from './components/RouteCards';
import { RecommendationBanner, ComparisonTable } from './components/RecommendationPanel';
import { HeatmapSlider } from './components/HeatmapSlider';
import { TripLoadingSkeleton, TripEmptyState, TripErrorAlert } from './components/Feedback';
import { useAnalyzeTrip } from './hooks/useAnalyzeTrip';
import { useHeatmap } from './hooks/useHeatmap';
import type { AnalyzeTripRequest, AnalyzeTripResponse, HeatmapResponse } from './types/api';

const MapView = lazy(() => import('./components/MapView/MapView'));

export default function App() {
  const [analysisResult, setAnalysisResult] = useState<AnalyzeTripResponse | null>(null);
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  const [showHeatmap, setShowHeatmap] = useState<boolean>(false);
  const [heatmapResponse, setHeatmapResponse] = useState<HeatmapResponse | null>(null);
  const [selectedHour, setSelectedHour] = useState<number>(0);
  const [lastSubmittedPayload, setLastSubmittedPayload] = useState<AnalyzeTripRequest | null>(null);

  const { mutate: analyze, isPending: isLoading, error } = useAnalyzeTrip();
  const { mutate: fetchHeatmapMutate, data: heatmapData, isPending: isHeatmapLoading } = useHeatmap();

  const handleTripSubmit = (payload: AnalyzeTripRequest) => {
    setLastSubmittedPayload(payload);
    setShowHeatmap(false);
    setSelectedHour(0);
    setHeatmapResponse(null);
    analyze(payload, {
      onSuccess: (data) => {
        setAnalysisResult(data);
        if (data.recommendation?.recommended_route_id) {
          setSelectedRouteId(data.recommendation.recommended_route_id);
        } else if (data.routes?.[0]?.id) {
          setSelectedRouteId(data.routes[0].id);
        }
        // Start loading heatmap data in background as soon as Analyze Routes finishes
        fetchHeatmapMutate(
          {
            trip_id: data.id,
            load_weight_lb: payload.load_weight_lb,
            departure_datetime: payload.departure_datetime,
            corridor_geometry: {
              routes: data.routes.map((r) => ({
                type: r.geometry.type,
                coordinates: r.geometry.coordinates,
              })),
            },
          },
          {
            onSuccess: (hm) => {
              setHeatmapResponse(hm);
            },
          }
        );
      },
    });
  };

  const handleToggleHeatmap = () => {
    if (!showHeatmap) {
      if (analysisResult && !heatmapResponse && !heatmapData && !isHeatmapLoading && lastSubmittedPayload) {
        fetchHeatmapMutate(
          {
            trip_id: analysisResult.id,
            load_weight_lb: lastSubmittedPayload.load_weight_lb,
            departure_datetime: lastSubmittedPayload.departure_datetime,
            corridor_geometry: {
              routes: analysisResult.routes.map((r) => ({
                type: r.geometry.type,
                coordinates: r.geometry.coordinates,
              })),
            },
          },
          {
            onSuccess: (hm) => {
              setHeatmapResponse(hm);
            },
          }
        );
      }
      setShowHeatmap(true);
    } else {
      setShowHeatmap(false);
    }
  };

  const errorMessage = error?.response?.data?.error?.message || error?.message || null;
  const currentHeatmapGrid = heatmapResponse?.grid || heatmapData?.grid;
  if (showHeatmap) {
    console.log('[App] heatmapGrid prop check:', {
      isArray: Array.isArray(currentHeatmapGrid),
      length: currentHeatmapGrid ? currentHeatmapGrid.length : 0,
      type: typeof currentHeatmapGrid,
    });
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* Top Navigation Bar */}
      <AppBar
        position="sticky"
        elevation={0}
        sx={{
          bgcolor: 'rgba(17, 24, 39, 0.85)',
          backdropFilter: 'blur(12px)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        <Toolbar sx={{ justifyContent: 'space-between', px: { xs: 2, md: 4 } }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Box
              sx={{
                width: 38,
                height: 38,
                borderRadius: 2,
                background: 'linear-gradient(135deg, #0284C7 0%, #38BDF8 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 12px rgba(2, 132, 199, 0.35)',
              }}
            >
              <Truck size={22} color="#0B0F19" />
            </Box>
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 700, color: '#F3F4F6', lineHeight: 1.2 }}>
                SafeHaul
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', display: { xs: 'none', sm: 'block' }, fontSize: '0.75rem' }}>
                Weather-Aware Truck Route Planner
              </Typography>
            </Box>
          </Box>
        </Toolbar>
      </AppBar>

      {/* Main Content Area */}
      <Box sx={{ flexGrow: 1, p: { xs: 2, md: 3 } }}>
        <Grid container spacing={3} sx={{ height: 'calc(100vh - 100px)' }}>
          {/* Left Column: Trip Form & Results Panel */}
          <Grid item xs={12} md={4.5} lg={4} sx={{ height: '100%', overflowY: 'auto' }}>
            <Paper
              elevation={0}
              sx={{
                p: 3,
                borderRadius: 3,
                bgcolor: 'background.paper',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                mb: 3,
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <Navigation size={20} color="#38BDF8" />
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  Trip Dispatch Parameters
                </Typography>
              </Box>

              <TripForm
                onSubmit={handleTripSubmit}
                isLoading={isLoading}
                error={errorMessage}
              />
            </Paper>

            {/* Loading State Skeleton */}
            {isLoading && <TripLoadingSkeleton />}

            {/* Error Alert if request failed */}
            {errorMessage && !isLoading && (
              <TripErrorAlert error={errorMessage} />
            )}

            {/* Initial Empty State before dispatching */}
            {!analysisResult && !isLoading && !errorMessage && (
              <TripEmptyState />
            )}

            {/* Route Analysis Results */}
            {analysisResult && !isLoading && (
              <Box sx={{ pb: 3 }}>
                <RecommendationBanner recommendation={analysisResult.recommendation} />

                <RouteCardList
                  routes={analysisResult.routes}
                  selectedRouteId={selectedRouteId}
                  recommendedRouteId={analysisResult.recommendation.recommended_route_id}
                  onSelectRoute={(id) => setSelectedRouteId(id)}
                />

                <ComparisonTable
                  comparison={analysisResult.recommendation.comparison}
                  selectedRouteId={selectedRouteId}
                  onSelectRoute={(id) => setSelectedRouteId(id)}
                />
              </Box>
            )}
          </Grid>

          {/* Right Column: Mapbox & Forecast Heatmap Area */}
          <Grid item xs={12} md={7.5} lg={8} sx={{ height: '100%' }}>
            <Paper
              elevation={0}
              sx={{
                height: '100%',
                borderRadius: 3,
                bgcolor: '#0E1320',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              <Suspense
                fallback={
                  <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Typography variant="body2" sx={{ color: '#94A3B8' }}>
                      Loading map view...
                    </Typography>
                  </Box>
                }
              >
                <MapView
                  routes={analysisResult?.routes}
                  selectedRouteId={selectedRouteId}
                  onSelectRoute={(id) => setSelectedRouteId(id)}
                  showHeatmap={showHeatmap}
                  heatmapGrid={currentHeatmapGrid}
                  selectedHour={selectedHour}
                />
              </Suspense>

              {analysisResult && (
                <HeatmapSlider
                  enabled={showHeatmap}
                  onToggle={handleToggleHeatmap}
                  isLoading={isHeatmapLoading && !heatmapResponse}
                  currentHour={selectedHour}
                  onHourChange={setSelectedHour}
                  maxHours={48}
                  departureTimeUtc={
                    heatmapResponse?.departure_datetime_utc ||
                    heatmapData?.departure_datetime_utc ||
                    analysisResult?.routes?.[0]?.departure_datetime_utc ||
                    analysisResult?.routes?.[0]?.checkpoints?.[0]?.eta_utc
                  }
                  originTimezone={analysisResult?.routes?.[0]?.checkpoints?.[0]?.timezone}
                />
              )}
            </Paper>
          </Grid>
        </Grid>
      </Box>
    </Box>
  );
}
