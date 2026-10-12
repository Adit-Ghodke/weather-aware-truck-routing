import { useMutation } from '@tanstack/react-query';
import { fetchHeatmap } from '../api/trips';
import type { HeatmapRequest, HeatmapResponse, ApiError } from '../types/api';
import type { AxiosError } from 'axios';

export function useHeatmap() {
  return useMutation<HeatmapResponse, AxiosError<ApiError>, HeatmapRequest>({
    mutationFn: (payload: HeatmapRequest) => fetchHeatmap(payload),
  });
}
