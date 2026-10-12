import React, { useState, useEffect, useRef } from 'react';
import {
  Autocomplete,
  TextField,
  CircularProgress,
  Box,
  Typography,
} from '@mui/material';
import { MapPin } from 'lucide-react';
import { searchGeocode } from '../../api/geocode';
import type { Coordinate, GeocodeResult } from '../../types/api';

interface AddressAutocompleteProps {
  label: string;
  value: Coordinate | null;
  onChange: (val: Coordinate | null) => void;
  error?: boolean;
  helperText?: string;
  disabled?: boolean;
}

export const AddressAutocomplete: React.FC<AddressAutocompleteProps> = ({
  label,
  value,
  onChange,
  error,
  helperText,
  disabled,
}) => {
  const [inputValue, setInputValue] = useState(value?.label || '');
  const [options, setOptions] = useState<GeocodeResult[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (value) {
      setInputValue(value.label);
    } else {
      setInputValue('');
    }
  }, [value]);

  const handleInputChange = (_: React.SyntheticEvent, newInputValue: string) => {
    setInputValue(newInputValue);

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    if (!newInputValue || newInputValue.trim().length < 2) {
      setOptions([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    // 300ms debounce
    debounceTimerRef.current = setTimeout(async () => {
      try {
        const results = await searchGeocode(newInputValue);
        setOptions(results);
      } catch (err) {
        console.warn('Geocoding search failed:', err);
        setOptions([]);
      } finally {
        setLoading(false);
      }
    }, 300);
  };

  return (
    <Autocomplete<GeocodeResult, false, false, false>
      disabled={disabled}
      options={options}
      getOptionLabel={(option) => (typeof option === 'string' ? option : option.label)}
      isOptionEqualToValue={(option, val) =>
        option.lat === val.lat && option.lng === val.lng
      }
      value={value}
      inputValue={inputValue}
      onInputChange={handleInputChange}
      onChange={(_, selected) => {
        if (selected) {
          onChange({
            label: selected.label,
            lat: selected.lat,
            lng: selected.lng,
          });
        } else {
          onChange(null);
        }
      }}
      filterOptions={(x) => x} // Backend handles search filtering
      noOptionsText={inputValue.length < 2 ? 'Type at least 2 characters' : 'No places found'}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          size="small"
          error={error}
          helperText={helperText}
          InputProps={{
            ...params.InputProps,
            startAdornment: (
              <Box sx={{ color: 'primary.main', display: 'flex', alignItems: 'center', mr: 1, pl: 0.5 }}>
                <MapPin size={18} />
              </Box>
            ),
            endAdornment: (
              <>
                {loading ? <CircularProgress color="inherit" size={16} sx={{ mr: 1 }} /> : null}
                {params.InputProps.endAdornment}
              </>
            ),
          }}
        />
      )}
      renderOption={(props, option) => (
        <Box component="li" {...props} key={`${option.lat}-${option.lng}-${option.label}`} sx={{ py: 1 }}>
          <Box sx={{ color: 'text.secondary', mr: 1.5, display: 'flex', alignItems: 'center' }}>
            <MapPin size={16} />
          </Box>
          <Box>
            <Typography variant="body2" sx={{ fontWeight: 500, color: 'text.primary' }}>
              {option.label}
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              {option.lat.toFixed(4)}, {option.lng.toFixed(4)}
            </Typography>
          </Box>
        </Box>
      )}
    />
  );
};
