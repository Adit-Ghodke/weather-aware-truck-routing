import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
  Alert,
  Chip,
  Stack,
  Slider,
} from '@mui/material';
import { Play, AlertTriangle, Scale, Clock } from 'lucide-react';
import { AddressAutocomplete } from './AddressAutocomplete';
import { apiClient } from '../../api/client';
import type { AnalyzeTripRequest, Coordinate } from '../../types/api';

interface TripFormProps {
  onSubmit: (payload: AnalyzeTripRequest) => void;
  isLoading: boolean;
  error?: string | null;
}

const PRESETS = [
  {
    name: 'Chicago → Kansas City',
    origin: { label: 'Chicago, IL', lat: 41.8781, lng: -87.6298 },
    destination: { label: 'Kansas City, MO', lat: 39.0997, lng: -94.5786 },
    loadWeight: 35000,
  },
  {
    name: 'Denver → Salt Lake City',
    origin: { label: 'Denver, CO', lat: 39.7392, lng: -104.9903 },
    destination: { label: 'Salt Lake City, UT', lat: 40.7608, lng: -111.8910 },
    loadWeight: 45000,
  },
  {
    name: 'Minneapolis → Chicago',
    origin: { label: 'Minneapolis, MN', lat: 44.9778, lng: -93.2650 },
    destination: { label: 'Chicago, IL', lat: 41.8781, lng: -87.6298 },
    loadWeight: 55000,
  },
];

interface OriginTimezone {
  name: string;
  abbr: string;
}

/**
 * Universal initial estimator for any coordinate on Earth.
 */
function guessUniversalTimezone(coord: Coordinate | null): OriginTimezone {
  if (!coord) return { name: 'America/Chicago', abbr: 'CDT' };
  const { lat, lng } = coord;
  if (-170.0 <= lng && lng <= -50.0 && 15.0 <= lat && lat <= 75.0) {
    if (lat > 50.0 && lng < -130.0) return { name: 'America/Anchorage', abbr: 'AKDT' };
    if (lat < 25.0 && lng < -150.0) return { name: 'Pacific/Honolulu', abbr: 'HST' };
    if (lng >= -85.0) return { name: 'America/New_York', abbr: 'EDT' };
    if (lng >= -103.0) return { name: 'America/Chicago', abbr: 'CDT' };
    if (lng >= -115.0) return { name: 'America/Denver', abbr: 'MDT' };
    return { name: 'America/Los_Angeles', abbr: 'PDT' };
  }
  const offsetHours = Math.round(lng / 15.0);
  const sign = offsetHours >= 0 ? '+' : '-';
  const absHours = Math.abs(offsetHours);
  return {
    name: offsetHours === 0 ? 'UTC' : `UTC${sign}${absHours}`,
    abbr: offsetHours === 0 ? 'UTC' : `UTC${sign}${absHours}`,
  };
}

/**
 * Universal backend resolver that queries TimezoneFinder covering every country on Earth.
 */
async function fetchOriginTimezone(coord: Coordinate): Promise<OriginTimezone | null> {
  try {
    const res = await apiClient.get('/timezones/resolve/', {
      params: { lat: coord.lat, lng: coord.lng },
    });
    return { name: res.data.timezone, abbr: res.data.abbr };
  } catch {
    return null;
  }
}

/**
 * Returns formatted "YYYY-MM-DDTHH:00" for the next full hour in the target origin timezone.
 */
function getDefaultDepartureInTimezone(timeZone: string): string {
  try {
    const tz = timeZone.startsWith('UTC') ? undefined : timeZone;
    const now = new Date();
    const minParts = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      minute: 'numeric',
      second: 'numeric',
    }).formatToParts(now);
    let currentMin = now.getMinutes();
    let currentSec = now.getSeconds();
    for (const p of minParts) {
      if (p.type === 'minute') currentMin = parseInt(p.value, 10);
      if (p.type === 'second') currentSec = parseInt(p.value, 10);
    }
    const msToNextHour = ((60 - currentMin) * 60 - currentSec) * 1000;
    const nextHourMs = msToNextHour > 0 ? msToNextHour : 3600000;
    const targetDate = new Date(now.getTime() + nextHourMs);

    const formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    });
    const parts = formatter.formatToParts(targetDate);
    const p: Record<string, string> = {};
    for (const part of parts) {
      p[part.type] = part.value;
    }
    const hour = p.hour === '24' ? '00' : p.hour;
    return `${p.year}-${p.month}-${p.day}T${hour}:00`;
  } catch {
    const d = new Date(Date.now() + 3600000);
    return `${d.toISOString().slice(0, 13)}:00`;
  }
}

/**
 * Converts a wall-clock "YYYY-MM-DDTHH:mm" string in origin timeZone into an ISO-8601 UTC string.
 */
function localDatetimeToUtcIso(localDatetimeStr: string, timeZone: string): string {
  if (!localDatetimeStr) return new Date().toISOString();
  try {
    const [datePart, timePart] = localDatetimeStr.split('T');
    const [year, month, day] = datePart.split('-').map(Number);
    const [hour, minute] = timePart.split(':').map(Number);

    const naiveUtc = new Date(Date.UTC(year, month - 1, day, hour, minute));

    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: timeZone.startsWith('UTC') ? undefined : timeZone,
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
      hour12: false,
    });

    const parts = formatter.formatToParts(naiveUtc);
    const p: Record<string, number> = {};
    for (const part of parts) {
      if (part.type !== 'literal') {
        p[part.type] = parseInt(part.value, 10);
      }
    }

    const targetHour = p.hour === 24 ? 0 : p.hour;
    const asInTzUtc = Date.UTC(p.year, p.month - 1, p.day, targetHour, p.minute);
    const offsetMs = naiveUtc.getTime() - asInTzUtc;

    return new Date(naiveUtc.getTime() + offsetMs).toISOString();
  } catch {
    return new Date(localDatetimeStr).toISOString();
  }
}

export const TripForm: React.FC<TripFormProps> = ({ onSubmit, isLoading, error }) => {
  const [origin, setOrigin] = useState<Coordinate | null>(PRESETS[0].origin);
  const [destination, setDestination] = useState<Coordinate | null>(PRESETS[0].destination);
  const [originTz, setOriginTz] = useState<OriginTimezone>(guessUniversalTimezone(PRESETS[0].origin));
  const [departureDatetime, setDepartureDatetime] = useState<string>(
    getDefaultDepartureInTimezone(PRESETS[0].origin ? 'America/Chicago' : 'UTC')
  );
  const [loadWeightLb, setLoadWeightLb] = useState<number>(35000);
  const [intervalMiles, setIntervalMiles] = useState<number | ''>(25);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Dynamic universal timezone resolution for any origin worldwide
  useEffect(() => {
    if (!origin) return;
    let isCurrent = true;
    fetchOriginTimezone(origin).then((tz) => {
      if (isCurrent && tz) {
        setOriginTz(tz);
      }
    });
    return () => {
      isCurrent = false;
    };
  }, [origin]);

  const handleOriginChange = (newOrigin: Coordinate | null) => {
    setOrigin(newOrigin);
    if (newOrigin) {
      const guessed = guessUniversalTimezone(newOrigin);
      setOriginTz(guessed);
      setDepartureDatetime(getDefaultDepartureInTimezone(guessed.name));
    }
  };

  const validate = (): boolean => {
    const errors: Record<string, string> = {};

    if (!origin) {
      errors.origin = 'Origin location is required.';
    }
    if (!destination) {
      errors.destination = 'Destination location is required.';
    }
    if (origin && destination && origin.lat === destination.lat && origin.lng === destination.lng) {
      errors.destination = 'Destination must be different from origin.';
    }

    if (!departureDatetime) {
      errors.departure = 'Departure date and time is required.';
    } else {
      const isoUtc = localDatetimeToUtcIso(departureDatetime, originTz.name);
      const depTime = new Date(isoUtc).getTime();
      const now = Date.now();
      const oneHourAgo = now - 60 * 60 * 1000;
      const sevenDaysAhead = now + 7 * 24 * 60 * 60 * 1000;

      if (depTime < oneHourAgo) {
        errors.departure = `Departure time cannot be more than 1 hour in the past (${originTz.abbr}).`;
      } else if (depTime > sevenDaysAhead) {
        errors.departure = `Departure time cannot be more than 7 days in the future (${originTz.abbr}).`;
      }
    }

    if (loadWeightLb < 1 || loadWeightLb > 80000) {
      errors.load = 'Load weight must be between 1 and 80,000 lb.';
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate() || !origin || !destination) return;

    // Send origin-local wall clock datetime directly — backend converts using the origin city's timezone
    const payload: AnalyzeTripRequest = {
      origin,
      destination,
      departure_datetime: departureDatetime,
      load_weight_lb: loadWeightLb,
      ...(intervalMiles ? { sample_interval_miles: intervalMiles as 10 | 25 | 50 } : {}),
    };

    onSubmit(payload);
  };

  const handleApplyPreset = (preset: typeof PRESETS[0]) => {
    setOrigin(preset.origin);
    setDestination(preset.destination);
    setLoadWeightLb(preset.loadWeight);
    const tz = guessUniversalTimezone(preset.origin);
    setOriginTz(tz);
    setDepartureDatetime(getDefaultDepartureInTimezone(tz.name));
    setFormErrors({});
  };

  // Rule indicators based on current cargo weight
  const isEscalationRuleActive = loadWeightLb > 30000;
  const isHighRuleActive = loadWeightLb > 40000;

  return (
    <Box component="form" onSubmit={handleSubmit} noValidate>
      {/* Preset Buttons */}
      <Box sx={{ mb: 2.5 }}>
        <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', mb: 1 }}>
          QUICK SCENARIOS
        </Typography>
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 0.75 }}>
          {PRESETS.map((preset) => (
            <Chip
              key={preset.name}
              label={preset.name}
              size="small"
              onClick={() => handleApplyPreset(preset)}
              disabled={isLoading}
              sx={{
                bgcolor: 'rgba(255, 255, 255, 0.05)',
                color: 'text.primary',
                '&:hover': { bgcolor: 'rgba(56, 189, 248, 0.15)', borderColor: 'primary.main' },
                cursor: 'pointer',
              }}
            />
          ))}
        </Stack>
      </Box>

      {/* Origin Autocomplete */}
      <Box sx={{ mb: 2 }}>
        <AddressAutocomplete
          label="Origin Address / City"
          value={origin}
          onChange={handleOriginChange}
          error={!!formErrors.origin}
          helperText={formErrors.origin}
          disabled={isLoading}
        />
      </Box>

      {/* Destination Autocomplete */}
      <Box sx={{ mb: 2 }}>
        <AddressAutocomplete
          label="Destination Address / City"
          value={destination}
          onChange={setDestination}
          error={!!formErrors.destination}
          helperText={formErrors.destination}
          disabled={isLoading}
        />
      </Box>

      {/* Departure Datetime */}
      <Box sx={{ mb: 2.5 }}>
        <TextField
          label="Departure date & time (origin local time)"
          type="datetime-local"
          value={departureDatetime}
          onChange={(e) => setDepartureDatetime(e.target.value)}
          error={!!formErrors.departure}
          helperText={formErrors.departure || `Origin local timezone: ${originTz.name} (${originTz.abbr})`}
          disabled={isLoading}
          fullWidth
          size="small"
          InputLabelProps={{ shrink: true }}
          InputProps={{
            startAdornment: (
              <Box sx={{ color: 'primary.main', display: 'flex', alignItems: 'center', mr: 1 }}>
                <Clock size={18} />
              </Box>
            ),
            endAdornment: (
              <Chip
                label={originTz.abbr}
                size="small"
                sx={{
                  height: 22,
                  fontWeight: 700,
                  fontSize: '0.75rem',
                  bgcolor: 'rgba(56, 189, 248, 0.15)',
                  color: '#38BDF8',
                  border: '1px solid rgba(56, 189, 248, 0.3)',
                }}
              />
            ),
          }}
        />
      </Box>

      {/* Load Weight Section */}
      <Box sx={{ mb: 2.5 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
            <Scale size={16} color="#38BDF8" />
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              Cargo Load Weight
            </Typography>
          </Box>
          <Typography variant="body2" sx={{ fontWeight: 700, color: 'primary.main' }}>
            {loadWeightLb.toLocaleString()} lb
          </Typography>
        </Box>

        <Slider
          value={loadWeightLb}
          min={5000}
          max={80000}
          step={1000}
          disabled={isLoading}
          onChange={(_, val) => setLoadWeightLb(val as number)}
          sx={{ color: 'primary.main', py: 1 }}
        />

        {/* Load Rule Escalate Badge */}
        <Box sx={{ mt: 0.5, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {isHighRuleActive && (
            <Chip
              label="35-44 mph Wind → Severe (>40k lb)"
              size="small"
              sx={{
                bgcolor: 'rgba(239, 68, 68, 0.15)',
                color: '#EF4444',
                fontSize: '0.75rem',
                border: '1px solid rgba(239, 68, 68, 0.3)',
              }}
            />
          )}
          {isEscalationRuleActive && (
            <Chip
              label="45-54 mph Wind → No Travel (>30k lb)"
              size="small"
              sx={{
                bgcolor: 'rgba(153, 27, 27, 0.25)',
                color: '#F87171',
                fontSize: '0.75rem',
                border: '1px solid rgba(248, 113, 113, 0.3)',
              }}
            />
          )}
        </Box>
      </Box>

      {/* Sample Interval Selection */}
      <Box sx={{ mb: 3 }}>
        <FormControl fullWidth size="small">
          <InputLabel id="interval-select-label">Sampling Resolution</InputLabel>
          <Select
            labelId="interval-select-label"
            value={intervalMiles}
            label="Sampling Resolution"
            disabled={isLoading}
            onChange={(e) => setIntervalMiles(e.target.value as number | '')}
          >
            <MenuItem value="">Automatic (Route Distance Based)</MenuItem>
            <MenuItem value={10}>10 miles (High Precision, Short Routes)</MenuItem>
            <MenuItem value={25}>25 miles (Standard Balanced)</MenuItem>
            <MenuItem value={50}>50 miles (Long Haul Corridor)</MenuItem>
          </Select>
        </FormControl>
      </Box>

      {/* Error Banner */}
      {error && (
        <Alert
          severity="error"
          icon={<AlertTriangle size={18} />}
          sx={{ mb: 2.5, bgcolor: 'rgba(239, 68, 68, 0.12)', color: '#FCA5A5' }}
        >
          {error}
        </Alert>
      )}

      {/* Action Buttons */}
      <Button
        type="submit"
        variant="contained"
        fullWidth
        size="large"
        disabled={isLoading}
        startIcon={isLoading ? <CircularProgress size={18} color="inherit" /> : <Play size={18} />}
        sx={{ py: 1.25, fontSize: '0.95rem' }}
      >
        {isLoading ? 'Evaluating Route Weather Hazards...' : 'Analyze Routes'}
      </Button>
    </Box>
  );
};
