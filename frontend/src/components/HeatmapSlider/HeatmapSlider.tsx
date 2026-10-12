import { useEffect, useState } from 'react';
import type { FC } from 'react';
import {
  Box,
  Paper,
  Typography,
  Slider,
  IconButton,
  Button,
  Tooltip,
  CircularProgress,
} from '@mui/material';
import { Play, Pause, RotateCcw, CloudSun } from 'lucide-react';

interface HeatmapSliderProps {
  enabled: boolean;
  onToggle: () => void;
  isLoading: boolean;
  currentHour: number;
  onHourChange: (hour: number | ((prev: number) => number)) => void;
  maxHours?: number;
  departureTimeUtc?: string;
  originTimezone?: string;
}

function formatSliderTime(departureUtc?: string, hourOffset = 0, timezone?: string): string {
  if (!departureUtc) {
    return `+${hourOffset}h from Departure`;
  }
  try {
    const baseMs = new Date(departureUtc).getTime();
    if (isNaN(baseMs)) return `+${hourOffset}h from Departure`;
    const targetDate = new Date(baseMs + hourOffset * 3600 * 1000);
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone || 'UTC',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZoneName: 'short',
    });
    return formatter.format(targetDate);
  } catch {
    return `+${hourOffset}h from Departure`;
  }
}

export const HeatmapSlider: FC<HeatmapSliderProps> = ({
  enabled,
  onToggle,
  isLoading,
  currentHour,
  onHourChange,
  maxHours = 48,
  departureTimeUtc,
  originTimezone,
}) => {
  const [isPlaying, setIsPlaying] = useState<boolean>(false);

  // Play animation loop (advances 1 hour every 450ms)
  useEffect(() => {
    if (!isPlaying || !enabled) return;

    const timer = setInterval(() => {
      onHourChange((prev: number) => (prev + 1) % (maxHours + 1));
    }, 450);

    return () => clearInterval(timer);
  }, [isPlaying, enabled, maxHours, onHourChange]);

  // Stop playback if heatmap is disabled
  useEffect(() => {
    if (!enabled && isPlaying) {
      setIsPlaying(false);
    }
  }, [enabled, isPlaying]);

  return (
    <Paper
      elevation={0}
      sx={{
        position: 'absolute',
        bottom: 24,
        left: 20,
        zIndex: 10,
        p: 1.5,
        borderRadius: 2.5,
        bgcolor: 'rgba(15, 23, 42, 0.92)',
        backdropFilter: 'blur(10px)',
        border: '1px solid rgba(255, 255, 255, 0.12)',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.6)',
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        minWidth: { xs: 280, sm: 400 },
        maxWidth: 480,
      }}
    >
      {/* Header bar: Toggle Button + Real Time in Origin TZ */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
        <Button
          size="small"
          variant={enabled ? 'contained' : 'outlined'}
          onClick={onToggle}
          startIcon={
            isLoading ? (
              <CircularProgress size={14} color="inherit" />
            ) : (
              <CloudSun size={15} />
            )
          }
          sx={{
            fontSize: '0.75rem',
            fontWeight: 700,
            textTransform: 'none',
            px: 1.5,
            py: 0.4,
            borderRadius: 2,
            bgcolor: enabled ? '#38BDF8' : 'transparent',
            color: enabled ? '#0F172A' : '#38BDF8',
            borderColor: '#38BDF8',
            '&:hover': {
              bgcolor: enabled ? '#0284C7' : 'rgba(56, 189, 248, 0.1)',
            },
          }}
        >
          {enabled ? 'Forecast Heatmap Active' : '48h Forecast Heatmap'}
        </Button>

        {enabled && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box
              sx={{
                px: 1,
                py: 0.25,
                borderRadius: 1,
                bgcolor: 'rgba(56, 189, 248, 0.15)',
                color: '#38BDF8',
                fontSize: '0.75rem',
                fontWeight: 700,
                whiteSpace: 'nowrap',
              }}
            >
              {formatSliderTime(departureTimeUtc, currentHour, originTimezone)} (+{currentHour}h)
            </Box>
          </Box>
        )}
      </Box>

      {/* Loading indicator inside heatmap panel if user opens before ready */}
      {enabled && isLoading && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 1, px: 0.5 }}>
          <CircularProgress size={16} sx={{ color: '#38BDF8' }} />
          <Typography variant="caption" sx={{ color: '#E2E8F0', fontSize: '0.8125rem', fontWeight: 500 }}>
            Loading corridor weather forecast matrix...
          </Typography>
        </Box>
      )}

      {/* Time Slider & Play Controls (visible when enabled and data ready) */}
      {enabled && !isLoading && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, pt: 0.5 }}>
          {/* Play / Pause button */}
          <Tooltip title={isPlaying ? 'Pause timeline' : 'Animate 48h forecast'} arrow>
            <IconButton
              size="small"
              onClick={() => setIsPlaying(!isPlaying)}
              sx={{
                bgcolor: isPlaying ? 'rgba(239, 68, 68, 0.2)' : 'rgba(56, 189, 248, 0.15)',
                color: isPlaying ? '#EF4444' : '#38BDF8',
                '&:hover': {
                  bgcolor: isPlaying ? 'rgba(239, 68, 68, 0.3)' : 'rgba(56, 189, 248, 0.25)',
                },
              }}
            >
              {isPlaying ? <Pause size={15} /> : <Play size={15} />}
            </IconButton>
          </Tooltip>

          {/* Reset to 0h */}
          <Tooltip title="Reset to Departure (0h)" arrow>
            <IconButton
              size="small"
              onClick={() => {
                setIsPlaying(false);
                onHourChange(0);
              }}
              sx={{ color: '#94A3B8' }}
            >
              <RotateCcw size={13} />
            </IconButton>
          </Tooltip>

          {/* 0 to 48 Hours Slider */}
          <Slider
            value={currentHour}
            min={0}
            max={maxHours}
            step={1}
            onChange={(_, val) => onHourChange(val as number)}
            sx={{
              color: '#38BDF8',
              height: 4,
              flexGrow: 1,
              '& .MuiSlider-thumb': {
                width: 14,
                height: 14,
                '&:hover, &.Mui-focusVisible': {
                  boxShadow: '0 0 0 6px rgba(56, 189, 248, 0.2)',
                },
              },
              '& .MuiSlider-rail': {
                opacity: 0.2,
              },
            }}
          />

          <Typography variant="caption" sx={{ color: '#94A3B8', fontSize: '0.75rem', minWidth: 32, textAlign: 'right' }}>
            48h
          </Typography>
        </Box>
      )}
    </Paper>
  );
};
