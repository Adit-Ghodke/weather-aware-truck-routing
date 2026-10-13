import { useEffect, useRef, useState } from 'react';
import type { FC } from 'react';
import mapboxgl from 'mapbox-gl';
import type { Feature, FeatureCollection, LineString, Point } from 'geojson';
import { Box, Alert, Typography } from '@mui/material';
import type { CandidateRoute, Checkpoint, HeatmapGridPoint } from '../../types/api';
import { MAPBOX_PUBLIC_TOKEN, RISK_COLORS, ROUTE_LINE_COLORS, RISK_INT_TO_LEVEL } from '../../constants';
import { MapLegend } from './MapLegend';

const EMPTY_GRID: HeatmapGridPoint[] = [];
const HEATMAP_SOURCE = 'safehaul-heatmap-source';
const HEATMAP_LAYER = 'safehaul-heatmap-glow-layer';

function formatPopupEta(etaLocal?: string, timezoneAbbr?: string): string {
  if (!etaLocal) return '';
  try {
    const [datePart, timePart] = etaLocal.split('T');
    if (!datePart || !timePart) return `${etaLocal} ${timezoneAbbr || ''}`.trim();
    const [, monthStr, dayStr] = datePart.split('-');
    const [hourStr, minuteStr] = timePart.split(':');
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const monthIdx = parseInt(monthStr, 10) - 1;
    const month = monthNames[monthIdx] || monthStr;
    const day = parseInt(dayStr, 10);
    const hour = parseInt(hourStr, 10);
    const minute = parseInt(minuteStr, 10);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const h12 = hour % 12 === 0 ? 12 : hour % 12;
    const mStr = minute.toString().padStart(2, '0');
    return `${month} ${day}, ${h12}:${mStr} ${ampm} ${timezoneAbbr || ''}`.trim();
  } catch {
    return `${etaLocal} ${timezoneAbbr || ''}`.trim();
  }
}

function isNearRoutes(ptLng: number, ptLat: number, routes: CandidateRoute[], maxDeg = 0.65): boolean {
  if (!routes || routes.length === 0) return true;
  const maxDegSq = maxDeg * maxDeg;
  const latRad = (ptLat * Math.PI) / 180;
  const cosLat = Math.cos(latRad);

  for (const route of routes) {
    if (route.checkpoints && route.checkpoints.length > 0) {
      for (const cp of route.checkpoints) {
        const dLat = ptLat - cp.lat;
        const dLng = (ptLng - cp.lng) * cosLat;
        if (dLat * dLat + dLng * dLng <= maxDegSq) {
          return true;
        }
      }
    } else if (route.geometry?.coordinates) {
      const coords = route.geometry.coordinates;
      for (let i = 0; i < coords.length; i += 6) {
        const [cLng, cLat] = coords[i];
        const dLat = ptLat - cLat;
        const dLng = (ptLng - cLng) * cosLat;
        if (dLat * dLat + dLng * dLng <= maxDegSq) {
          return true;
        }
      }
    }
  }
  return false;
}

function buildHeatmapGeoJSON(
  grid: HeatmapGridPoint[],
  hour: number,
  routes: CandidateRoute[] = []
): FeatureCollection<Point> {
  const corridorGrid = routes.length > 0
    ? grid.filter((pt) => isNearRoutes(pt.lng, pt.lat, routes, 0.65))
    : grid;

  return {
    type: 'FeatureCollection',
    features: corridorGrid.map((pt) => {
      const level = RISK_INT_TO_LEVEL[pt.hour_risks[hour] ?? 0] || 'Low';
      return {
        type: 'Feature',
        properties: { level, color: RISK_COLORS[level] },
        geometry: { type: 'Point', coordinates: [pt.lng, pt.lat] },
      };
    }),
  };
}

interface MapViewProps {
  routes?: CandidateRoute[];
  selectedRouteId?: string | null;
  onSelectRoute?: (routeId: string) => void;
  onSelectCheckpoint?: (checkpoint: Checkpoint | null) => void;
  showHeatmap?: boolean;
  heatmapGrid?: HeatmapGridPoint[];
  selectedHour?: number;
}

export const MapView: FC<MapViewProps> = ({
  routes = [],
  selectedRouteId,
  onSelectRoute,
  onSelectCheckpoint,
  showHeatmap = false,
  heatmapGrid = EMPTY_GRID,
  selectedHour = 0,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const popupRef = useRef<mapboxgl.Popup | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);
  const [mapError, setMapError] = useState<string | null>(null);
  const [styleReady, setStyleReady] = useState<boolean>(false);

  // Keep callback and selection state in refs so layer listeners never trigger effect rebuilds
  const onSelectRouteRef = useRef(onSelectRoute);
  onSelectRouteRef.current = onSelectRoute;

  const onSelectCheckpointRef = useRef(onSelectCheckpoint);
  onSelectCheckpointRef.current = onSelectCheckpoint;

  const selectedRouteIdRef = useRef(selectedRouteId);
  selectedRouteIdRef.current = selectedRouteId;

  const routesRef = useRef(routes);
  routesRef.current = routes;

  const routeBuildCounterRef = useRef<number>(0);

  // Initialize Mapbox instance once
  useEffect(() => {
    if (!mapContainerRef.current) return;

    mapboxgl.accessToken = MAPBOX_PUBLIC_TOKEN;

    const map = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: [-98.5795, 39.8283],
      zoom: 3.5,
    });

    map.addControl(new mapboxgl.NavigationControl({ showCompass: true }), 'top-right');

    map.on('error', (e) => {
      if (e.error?.message?.includes('Forbidden') || e.error?.message?.includes('Unauthorized')) {
        setMapError('Mapbox access token is demo/unauthorized. Add your public token to VITE_MAPBOX_TOKEN in .env to display official vector basemaps.');
      }
    });

    map.on('load', () => {
      setStyleReady(true);
    });

    mapRef.current = map;
    (window as unknown as { safehaulMap?: mapboxgl.Map }).safehaulMap = map;

    return () => {
      setStyleReady(false);
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      if (popupRef.current) popupRef.current.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // 1. Route & Checkpoint Build Effect: runs ONLY when routes change or style becomes ready
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReady) return;

    routeBuildCounterRef.current += 1;
    console.log(`[MapView] Route layers built count: ${routeBuildCounterRef.current}`);

    // Remove existing route and checkpoint event listeners if any
    const existingLayers = map.getStyle()?.layers || [];
    existingLayers.forEach((layer) => {
      if (layer.id.startsWith('safehaul-route-layer-') || layer.id === 'safehaul-checkpoints-layer') {
        const untypedMap = map as unknown as { off: (type: string, layer: string) => void };
        untypedMap.off('click', layer.id);
        untypedMap.off('mouseenter', layer.id);
        untypedMap.off('mouseleave', layer.id);
        map.removeLayer(layer.id);
      }
    });

    const existingSources = Object.keys(map.getStyle()?.sources || {});
    existingSources.forEach((sourceId) => {
      if (sourceId.startsWith('safehaul-route-source-') || sourceId === 'safehaul-checkpoints-source') {
        map.removeSource(sourceId);
      }
    });

    // Clear markers & popups
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    if (popupRef.current) popupRef.current.remove();

    if (!routes || routes.length === 0) return;

    const bounds = new mapboxgl.LngLatBounds();

    // Add route line sources and layers
    routes.forEach((route, idx) => {
      const sourceId = `safehaul-route-source-${route.id}`;
      const layerId = `safehaul-route-layer-${route.id}`;
      const color = ROUTE_LINE_COLORS[idx % ROUTE_LINE_COLORS.length];
      const isSelected = route.id === selectedRouteIdRef.current;

      const geojson: Feature<LineString> = {
        type: 'Feature',
        properties: { id: route.id, label: route.label },
        geometry: {
          type: 'LineString',
          coordinates: route.geometry.coordinates,
        },
      };

      map.addSource(sourceId, { type: 'geojson', data: geojson });

      map.addLayer({
        id: layerId,
        type: 'line',
        source: sourceId,
        layout: {
          'line-join': 'round',
          'line-cap': 'round',
        },
        paint: {
          'line-color': color,
          'line-width': isSelected ? 5.5 : 3.0,
          'line-opacity': isSelected ? 0.95 : 0.45,
        },
      });

      // Register click and hover once per layer
      map.on('click', layerId, () => {
        onSelectRouteRef.current?.(route.id);
      });
      map.on('mouseenter', layerId, () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', layerId, () => {
        map.getCanvas().style.cursor = '';
      });

      route.geometry.coordinates.forEach(([lng, lat]) => {
        bounds.extend([lng, lat]);
      });
    });

    // Origin and destination markers from routes[0]
    if (routes[0] && routes[0].geometry.coordinates.length > 0) {
      const coords = routes[0].geometry.coordinates;
      const firstCoord = coords[0];
      const lastCoord = coords[coords.length - 1];

      const originMarker = new mapboxgl.Marker({ color: '#10B981' })
        .setLngLat([firstCoord[0], firstCoord[1]])
        .addTo(map);
      markersRef.current.push(originMarker);

      const destMarker = new mapboxgl.Marker({ color: '#38BDF8' })
        .setLngLat([lastCoord[0], lastCoord[1]])
        .addTo(map);
      markersRef.current.push(destMarker);
    }

    // Checkpoints layer
    const allCheckpointFeatures: Feature<Point>[] = [];
    routes.forEach((route) => {
      (route.checkpoints || []).forEach((cp) => {
        allCheckpointFeatures.push({
          type: 'Feature',
          properties: {
            route_id: route.id,
            route_label: route.label,
            index: cp.index,
            mile_marker: cp.mile_marker,
            eta_local: cp.eta_local,
            timezone_abbr: cp.timezone_abbr,
            level: cp.level,
            reason: cp.reason,
            wind_mph: cp.weather?.wind_mph ?? 0,
            gust_mph: cp.weather?.gust_mph ?? 0,
            rain_in_hr: cp.weather?.rain_in_hr ?? 0,
            snow_in_hr: cp.weather?.snow_in_hr ?? 0,
          },
          geometry: {
            type: 'Point',
            coordinates: [cp.lng, cp.lat],
          },
        });
      });
    });

    if (allCheckpointFeatures.length > 0) {
      map.addSource('safehaul-checkpoints-source', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: allCheckpointFeatures,
        },
      });

      map.addLayer({
        id: 'safehaul-checkpoints-layer',
        type: 'circle',
        source: 'safehaul-checkpoints-source',
        paint: {
          'circle-radius': [
            'case',
            ['==', ['get', 'route_id'], selectedRouteIdRef.current ?? ''],
            7.0,
            5.5,
          ],
          'circle-opacity': [
            'case',
            ['==', ['get', 'route_id'], selectedRouteIdRef.current ?? ''],
            1.0,
            0.60,
          ],
          'circle-color': [
            'match',
            ['get', 'level'],
            'Low', RISK_COLORS.Low,
            'Moderate', RISK_COLORS.Moderate,
            'High', RISK_COLORS.High,
            'Severe', RISK_COLORS.Severe,
            'No Travel', RISK_COLORS['No Travel'],
            '#94A3B8',
          ],
          'circle-stroke-width': [
            'case',
            ['==', ['get', 'route_id'], selectedRouteIdRef.current ?? ''],
            2.0,
            1.5,
          ],
          'circle-stroke-color': '#0F172A',
          'circle-stroke-opacity': [
            'case',
            ['==', ['get', 'route_id'], selectedRouteIdRef.current ?? ''],
            1.0,
            0.60,
          ],
        },
      });

      map.on('click', 'safehaul-checkpoints-layer', (e) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const props = (feature.properties || {}) as Record<string, unknown>;
        const geom = feature.geometry as Point;
        const coords = geom.coordinates;
        const levelColor = RISK_COLORS[props.level as keyof typeof RISK_COLORS] || '#38BDF8';

        const html = `
          <div style="font-family: Inter, sans-serif; padding: 4px; color: #F1F5F9; min-width: 220px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-weight: 700; font-size: 13px;">${props.route_label} &bull; Mile ${Number(props.mile_marker).toFixed(1)}</span>
              <span style="background: ${levelColor}; color: #0F172A; font-weight: 700; font-size: 12px; padding: 2px 6px; border-radius: 4px; text-transform: uppercase;">
                ${props.level}
              </span>
            </div>
            <div style="font-size: 12px; color: #94A3B8; margin-bottom: 6px;">
              ETA: <strong style="color: #E2E8F0;">${formatPopupEta(props.eta_local as string, props.timezone_abbr as string)}</strong>
            </div>
            <div style="font-size: 12px; color: #CBD5E1; margin-bottom: 8px; line-height: 1.4;">
              ${props.reason}
            </div>
            <div style="background: rgba(255,255,255,0.06); padding: 6px 8px; border-radius: 4px; font-size: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 4px;">
              <div>Wind: <strong>${props.wind_mph} mph</strong></div>
              <div>Gusts: <strong>${props.gust_mph} mph</strong></div>
              <div>Rain: <strong>${props.rain_in_hr} in/hr</strong></div>
              <div>Snow: <strong>${props.snow_in_hr} in/hr</strong></div>
            </div>
          </div>
        `;

        if (popupRef.current) popupRef.current.remove();

        popupRef.current = new mapboxgl.Popup({ offset: 12, closeButton: false, className: 'safehaul-map-popup' })
          .setLngLat([coords[0], coords[1]])
          .setHTML(html)
          .addTo(map);

        if (typeof props.route_id === 'string' && props.route_id !== selectedRouteIdRef.current) {
          onSelectRouteRef.current?.(props.route_id);
        }
        const targetRoute = routesRef.current.find((r) => r.id === props.route_id) || routesRef.current[0];
        const matchingCp = targetRoute?.checkpoints?.find((c: Checkpoint) => c.index === props.index) || null;
        onSelectCheckpointRef.current?.(matchingCp);
      });

      map.on('mouseenter', 'safehaul-checkpoints-layer', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'safehaul-checkpoints-layer', () => {
        map.getCanvas().style.cursor = '';
      });
    }

    // fitBounds only runs when a new analysis arrives
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, {
        padding: { top: 50, bottom: 50, left: 50, right: 50 },
        maxZoom: 12,
        duration: 900,
      });
    }
  }, [styleReady, routes]);

  // 2. Selection Restyle Effect: restyles without moving camera or recreating layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReady || !routes || routes.length === 0) return;

    routes.forEach((route) => {
      const layerId = `safehaul-route-layer-${route.id}`;
      if (map.getLayer(layerId)) {
        const isSelected = route.id === selectedRouteId;
        map.setPaintProperty(layerId, 'line-width', isSelected ? 5.5 : 3.0);
        map.setPaintProperty(layerId, 'line-opacity', isSelected ? 0.95 : 0.45);
      }
    });

    if (map.getLayer('safehaul-checkpoints-layer')) {
      const activeId = selectedRouteId ?? '';
      map.setPaintProperty('safehaul-checkpoints-layer', 'circle-radius', [
        'case',
        ['==', ['get', 'route_id'], activeId],
        7.0,
        5.5,
      ]);
      map.setPaintProperty('safehaul-checkpoints-layer', 'circle-opacity', [
        'case',
        ['==', ['get', 'route_id'], activeId],
        1.0,
        0.60,
      ]);
      map.setPaintProperty('safehaul-checkpoints-layer', 'circle-stroke-width', [
        'case',
        ['==', ['get', 'route_id'], activeId],
        2.0,
        1.5,
      ]);
      map.setPaintProperty('safehaul-checkpoints-layer', 'circle-stroke-opacity', [
        'case',
        ['==', ['get', 'route_id'], activeId],
        1.0,
        0.60,
      ]);
    }
  }, [styleReady, selectedRouteId, routes]);

  // 3. Heatmap Glow Effect (§Step 3)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReady) return;
    if (!Array.isArray(heatmapGrid)) {
      console.error('heatmapGrid must be an array, got', typeof heatmapGrid);
      return;
    }
    if (!showHeatmap || heatmapGrid.length === 0) {
      if (map.getLayer(HEATMAP_LAYER)) map.setLayoutProperty(HEATMAP_LAYER, 'visibility', 'none');
      return;
    }
    const data = buildHeatmapGeoJSON(heatmapGrid, selectedHour, routes);
    const src = map.getSource(HEATMAP_SOURCE) as mapboxgl.GeoJSONSource | undefined;
    if (src) {
      src.setData(data);
    } else {
      map.addSource(HEATMAP_SOURCE, { type: 'geojson', data });
      const firstRouteLayer = map.getStyle()?.layers?.find((l) => l.id.startsWith('safehaul-route-layer-'))?.id;
      map.addLayer(
        {
          id: HEATMAP_LAYER,
          type: 'circle',
          source: HEATMAP_SOURCE,
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 12, 6, 18, 8, 28, 10, 42],
            'circle-color': ['get', 'color'],
            'circle-opacity': [
              'case',
              ['==', ['get', 'level'], 'Low'], 0.0,
              ['==', ['get', 'level'], 'Moderate'], 0.75,
              ['==', ['get', 'level'], 'High'], 0.85,
              ['==', ['get', 'level'], 'Severe'], 0.95,
              1.0,
            ],
            'circle-blur': 0.35,
          },
        },
        firstRouteLayer
      );
    }
    map.setLayoutProperty(HEATMAP_LAYER, 'visibility', 'visible');
  }, [styleReady, showHeatmap, heatmapGrid, selectedHour, routes]);

  return (
    <Box sx={{ width: '100%', height: '100%', position: 'relative', overflow: 'hidden' }}>
      {mapError && (
        <Alert
          severity="info"
          sx={{
            position: 'absolute',
            top: 12,
            left: 12,
            right: 12,
            zIndex: 20,
            bgcolor: 'rgba(15, 23, 42, 0.95)',
            color: '#38BDF8',
            border: '1px solid rgba(56, 189, 248, 0.3)',
          }}
          onClose={() => setMapError(null)}
        >
          <Typography variant="caption">{mapError}</Typography>
        </Alert>
      )}

      {/* Mapbox container element */}
      <Box
        ref={mapContainerRef}
        sx={{
          width: '100%',
          height: '100%',
          '& .mapboxgl-popup-content': {
            bgcolor: '#0F172A',
            borderRadius: '8px',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.7)',
            p: '8px 10px',
          },
          '& .mapboxgl-popup-tip': {
            borderTopColor: '#0F172A',
          },
        }}
      />

      {/* Floating Map Legend */}
      <MapLegend />
    </Box>
  );
};

export default MapView;
