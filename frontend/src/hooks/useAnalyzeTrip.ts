import { useMutation } from '@tanstack/react-query';
import { analyzeTrip } from '../api/trips';
import type { AnalyzeTripRequest, AnalyzeTripResponse, ApiError } from '../types/api';
import type { AxiosError } from 'axios';

export function useAnalyzeTrip() {
  return useMutation<AnalyzeTripResponse, AxiosError<ApiError>, AnalyzeTripRequest>({
    mutationFn: (payload: AnalyzeTripRequest) => analyzeTrip(payload),
  });
}
