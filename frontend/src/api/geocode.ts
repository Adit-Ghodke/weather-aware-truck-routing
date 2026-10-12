import { apiClient } from './client';
import type { GeocodeResponse, GeocodeResult } from '../types/api';

export async function searchGeocode(query: string): Promise<GeocodeResult[]> {
  const clean = query.trim();
  if (clean.length < 2) return [];

  const response = await apiClient.get<GeocodeResponse>('/geocode/', {
    params: { q: clean },
  });
  return response.data.results || [];
}
