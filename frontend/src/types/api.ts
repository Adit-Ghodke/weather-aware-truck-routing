/**
 * SafeHaul API Data Models and TypeScript Contracts (§7).
 */

export type RiskLevel = 'Low' | 'Moderate' | 'High' | 'Severe' | 'No Travel';

export interface Coordinate {
  lat: number;
  lng: number;
  label: string;
}

export interface WeatherConditions {
  wind_mph: number;
  gust_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
}

export interface CheckpointConditionLevels {
  wind: RiskLevel;
  rain: RiskLevel;
  snow: RiskLevel;
}

export interface Checkpoint {
  index: number;
  mile_marker: number;
  lat: number;
  lng: number;
  eta_utc: string;
  eta_local: string;
  timezone: string;
  timezone_abbr: string;
  segment_miles: number;
  weather: WeatherConditions | null;
  condition_levels: CheckpointConditionLevels;
  level: RiskLevel;
  reason: string;
  weather_available: boolean;
}

export interface RouteMetrics {
  severe_miles: number;
  high_miles: number;
  moderate_miles: number;
  low_miles: number;
  no_travel_miles: number;
  average_risk: number;
  worst_level: RiskLevel;
}

export interface RouteGeometry {
  type: 'LineString';
  coordinates: [number, number][]; // [lng, lat]
}

export interface RouteComparisonItem {
  route_id: string;
  label: string;
  rank: number;
  status: 'ok' | 'no_travel' | 'error';
  distance_miles: number;
  severe_miles: number;
  high_miles: number;
  moderate_miles: number;
  low_miles: number;
  no_travel_miles: number;
  average_risk: number;
  duration_minutes: number;
}

export interface RouteRecommendation {
  recommended_route_id: string;
  status: 'recommended' | 'not_recommended_all_routes';
  explanation: string;
  warning?: string | null;
  comparison: RouteComparisonItem[];
}

export interface CandidateRoute {
  id: string;
  label: string;
  distance_miles: number;
  duration_minutes: number;
  departure_datetime_utc: string;
  arrival_datetime_utc: string;
  arrival_datetime_local: string;
  geometry: RouteGeometry;
  checkpoints: Checkpoint[];
  metrics: RouteMetrics;
}

export interface TripAnalysisMeta {
  units: {
    distance: string;
    wind: string;
    precipitation: string;
    load: string;
  };
  interval_miles: number;
  routing_provider: string;
  weather_provider: string;
  generated_at: string;
  warnings: string[];
}

export interface AnalyzeTripResponse {
  id: string;
  routes: CandidateRoute[];
  recommendation: RouteRecommendation;
  meta: TripAnalysisMeta;
}

export interface AnalyzeTripRequest {
  origin: Coordinate;
  destination: Coordinate;
  departure_datetime: string;
  load_weight_lb: number;
  sample_interval_miles?: 10 | 25 | 50;
}

export interface HeatmapGridPoint {
  lat: number;
  lng: number;
  hour_risks: number[]; // 49 integer values [0..4]
}

export interface HeatmapResponse {
  grid: HeatmapGridPoint[];
  hours: number;
  departure_datetime_utc: string;
  meta: {
    grid_points: number;
    max_points_cap: number;
    warnings: string[];
  };
}

export interface HeatmapRequest {
  trip_id?: string;
  corridor_geometry?: {
    routes: Array<{
      type: string;
      coordinates: [number, number][];
    }>;
  };
  departure_datetime?: string;
  load_weight_lb: number;
}

export interface GeocodeResult {
  label: string;
  lat: number;
  lng: number;
}

export interface GeocodeResponse {
  results: GeocodeResult[];
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
