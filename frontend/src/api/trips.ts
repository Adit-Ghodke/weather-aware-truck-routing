import { apiClient } from './client';
import type {
  AnalyzeTripRequest,
  AnalyzeTripResponse,
  HeatmapRequest,
  HeatmapResponse,
} from '../types/api';


export async function analyzeTrip(payload: AnalyzeTripRequest): Promise<AnalyzeTripResponse> {
  const response = await apiClient.post<AnalyzeTripResponse>('/trips/analyze/', payload);
  return response.data;
}

export async function fetchHeatmap(payload: HeatmapRequest): Promise<HeatmapResponse> {
  const response = await apiClient.post<HeatmapResponse>('/trips/heatmap/', payload);
  return response.data;
}

export async function fetchTripDetail(tripId: string): Promise<AnalyzeTripResponse> {
  const response = await apiClient.get<AnalyzeTripResponse>(`/trips/${tripId}/`);
  return response.data;
}
