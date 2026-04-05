import { useState, useEffect, useRef, useCallback } from "react";
import { preprocessAirspaceGeoJSON, drawAirspaceLayer, findAirspaceAtPoint } from "./airspace";

// ============================================================
// FLYING SITES DATABASE — Birmingham to South Coast
// ============================================================
const SITES = [
  { name: "Butser Hill", lat: 50.967, lon: -1.017, dir: "S-SW", region: "South Downs", club: "SSC", elev: 270 },
  { name: "Harting Down", lat: 50.958, lon: -0.875, dir: "S-SW", region: "South Downs", club: "SSC", elev: 230 },
  { name: "Whitewool", lat: 50.983, lon: -0.883, dir: "N-NE", region: "South Downs", club: "SSC", elev: 200 },
  { name: "Beacon Hill", lat: 50.970, lon: -1.008, dir: "W-NW", region: "South Downs", club: "SSC", elev: 248 },
  { name: "Cocking Down", lat: 50.939, lon: -0.748, dir: "S", region: "South Downs", club: "SSC", elev: 220 },
  { name: "Devils Dyke", lat: 50.887, lon: -0.216, dir: "N-NW", region: "South Downs", club: "SHGC", elev: 217 },
  { name: "Ditchling Beacon", lat: 50.899, lon: -0.107, dir: "N", region: "South Downs", club: "SHGC", elev: 248 },
  { name: "Mount Caburn", lat: 50.862, lon: 0.023, dir: "S-SE", region: "South Downs", club: "SHGC", elev: 148 },
  { name: "Firle Beacon", lat: 50.837, lon: 0.106, dir: "N-NW", region: "South Downs", club: "SHGC", elev: 217 },
  { name: "Bo Peep", lat: 50.835, lon: 0.137, dir: "S-SE", region: "South Downs", club: "SHGC", elev: 200 },
  { name: "High & Over", lat: 50.792, lon: 0.166, dir: "S-SW", region: "South Downs", club: "SHGC", elev: 175 },
  { name: "Box Hill", lat: 51.257, lon: -0.313, dir: "S-SE", region: "North Downs", club: "Green Dragon", elev: 172 },
  { name: "Reigate Hill", lat: 51.237, lon: -0.200, dir: "S", region: "North Downs", club: "Green Dragon", elev: 170 },
  { name: "Dunstable Downs", lat: 51.867, lon: -0.540, dir: "SW-W", region: "Chilterns", club: "DHPC", elev: 243 },
  { name: "Ivinghoe Beacon", lat: 51.842, lon: -0.609, dir: "N-NE", region: "Chilterns", club: "DHPC", elev: 249 },
  { name: "Westbury White Horse", lat: 51.277, lon: -2.153, dir: "NW-N", region: "Wiltshire", club: "Avon", elev: 230 },
  { name: "Milk Hill", lat: 51.365, lon: -1.844, dir: "N-NW", region: "Wiltshire", club: "TVHGC", elev: 295 },
  { name: "Tan Hill", lat: 51.396, lon: -1.830, dir: "S-SE", region: "Wiltshire", club: "TVHGC", elev: 294 },
  { name: "Inkpen Hill", lat: 51.359, lon: -1.465, dir: "N", region: "Thames Valley", club: "TVHGC", elev: 297 },
  { name: "Walbury Hill", lat: 51.365, lon: -1.449, dir: "S", region: "Thames Valley", club: "TVHGC", elev: 297 },
  { name: "Combe Gibbet", lat: 51.380, lon: -1.464, dir: "N-NE", region: "Thames Valley", club: "TVHGC", elev: 280 },
  { name: "Selsley Common", lat: 51.724, lon: -2.262, dir: "W-NW", region: "Cotswolds", club: "SWGC", elev: 260 },
  { name: "Frocester Hill", lat: 51.730, lon: -2.275, dir: "S-SE", region: "Cotswolds", club: "SWGC", elev: 250 },
  { name: "Leckhampton Hill", lat: 51.870, lon: -2.083, dir: "W-NW", region: "Cotswolds", club: "SWGC", elev: 305 },
  { name: "Cleeve Hill", lat: 51.938, lon: -2.002, dir: "W-SW", region: "Cotswolds", club: "SWGC", elev: 330 },
  { name: "Crook Peak", lat: 51.284, lon: -2.883, dir: "N-NW", region: "Mendips", club: "Avon", elev: 191 },
  { name: "Bossington Hill", lat: 51.222, lon: -3.592, dir: "N-NE", region: "Exmoor", club: "N Devon", elev: 310 },
  { name: "Ringstead Bay", lat: 50.636, lon: -2.344, dir: "S", region: "Dorset", club: "Wessex", elev: 130 },
  { name: "Kimmeridge", lat: 50.608, lon: -2.124, dir: "S-SW", region: "Dorset", club: "Wessex", elev: 150 },
  { name: "Compton Down", lat: 50.651, lon: -1.411, dir: "S-SW", region: "Isle of Wight", club: "IW Club", elev: 140 },
  { name: "Malvern Hills", lat: 52.103, lon: -2.336, dir: "W", region: "Malverns", club: "Malvern", elev: 425 },
  { name: "Long Mynd", lat: 52.535, lon: -2.872, dir: "W-SW", region: "Shropshire", club: "LMSC", elev: 516 },
  { name: "Hay Bluff", lat: 51.988, lon: -3.112, dir: "W-NW", region: "Black Mountains", club: "SHGPC", elev: 677 },
  { name: "Llangorse", lat: 51.918, lon: -3.268, dir: "SE", region: "Brecon Beacons", club: "SHGPC", elev: 450 },
  { name: "Rhossili Down", lat: 51.576, lon: -4.282, dir: "W-NW", region: "Gower", club: "SWPGC", elev: 193 },
];

const REGIONS = [...new Set(SITES.map((s) => s.region))];
const REGION_COLORS = {
  "South Downs": "#22cc88",
  "North Downs": "#44aacc",
  Chilterns: "#cc8844",
  Wiltshire: "#aa88cc",
  "Thames Valley": "#ccaa44",
  Cotswolds: "#88cc44",
  Mendips: "#cc6688",
  Exmoor: "#cc4466",
  Dorset: "#4488cc",
  "Isle of Wight": "#44ccaa",
  Malverns: "#cc8866",
  Shropshire: "#88aacc",
  "Black Mountains": "#aa6644",
  "Brecon Beacons": "#66aa44",
  Gower: "#6688cc",
};

// ============================================================
// KK7 THERMAL TILE CONFIG
// ============================================================
const KK7_LAYERS = {
  thermals_all_all: { label: "All Thermals", desc: "All times, all seasons" },
  thermals_apr_all: { label: "Spring", desc: "April ±1.5 months" },
  thermals_jul_all: { label: "Summer", desc: "July ±1.5 months" },
  thermals_oct_all: { label: "Autumn", desc: "October ±1.5 months" },
  thermals_all_04: { label: "Morning", desc: "All seasons, +4h after sunrise" },
  thermals_all_07: { label: "Midday", desc: "All seasons, +7h after sunrise" },
  thermals_all_10: { label: "Evening", desc: "All seasons, +10h after sunrise" },
  thermals_jul_04: { label: "Sum Morning", desc: "July, +4h sunrise" },
  thermals_jul_07: { label: "Sum Midday", desc: "July, +7h sunrise" },
  thermals_jul_10: { label: "Sum Evening", desc: "July, +10h sunrise" },
  skyways_all_all: { label: "Skyways", desc: "Common XC flight routes" },
};

// ============================================================
// BASEMAP OPTIONS
// ============================================================
const BASEMAPS = {
  osm: {
    label: "Streets",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr: "© OpenStreetMap",
    opacity: 1,
  },
  topo: {
    label: "Terrain",
    url: "https://tile.opentopomap.org/{z}/{x}/{y}.png",
    attr: "© OpenTopoMap",
    opacity: 1,
  },
  satellite: {
    label: "Satellite",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr: "© Esri",
    opacity: 1,
  },
};

const MAP_CENTER = { lat: 51.55, lon: -1.75 };

// ============================================================
// TILE & GEO MATH
// ============================================================
function latLonToPixel(lat, lon, zoom, originX, originY, ts = 256) {
  const s = Math.pow(2, zoom);
  const wx = ((lon + 180) / 360) * s * ts;
  const wy =
    ((1 -
      Math.log(
        Math.tan((lat * Math.PI) / 180) + 1 / Math.cos((lat * Math.PI) / 180)
      ) /
        Math.PI) /
      2) *
    s *
    ts;
  return { x: wx - originX, y: wy - originY };
}

function pixelToLatLon(px, py, zoom, originX, originY, ts = 256) {
  const s = Math.pow(2, zoom);
  const wx = originX + px;
  const wy = originY + py;
  const lon = (wx / (s * ts)) * 360 - 180;
  const n = Math.PI - (2 * Math.PI * wy) / (s * ts);
  const lat = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  return { lat, lon };
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function bearing(lat1, lon1, lat2, lon2) {
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const y = Math.sin(dLon) * Math.cos((lat2 * Math.PI) / 180);
  const x =
    Math.cos((lat1 * Math.PI) / 180) * Math.sin((lat2 * Math.PI) / 180) -
    Math.sin((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.cos(dLon);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

function hotspotStyle(cell, thresholdMode) {
  if (thresholdMode === "hot3") {
    if (!cell.hot3) return null;
    return { color: "#ff3a20", alpha: 0.34 };
  }
  if (cell.hot3) return { color: "#ff3218", alpha: 0.38 };
  if (cell.hot2) return { color: "#ffae32", alpha: 0.20 };
  return null;
}

function hotspotCellSize(zoom) {
  if (zoom <= 7) return 2;
  if (zoom <= 9) return 3;
  if (zoom <= 11) return 4;
  return 5;
}

function distanceBetweenTouches(a, b) {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}


function routePointHitIndex(routePoints, mx, my, zoom, ox, oy, radius = 12) {
  for (let i = routePoints.length - 1; i >= 0; i--) {
    const p = latLonToPixel(routePoints[i].lat, routePoints[i].lon, zoom, ox, oy);
    const dx = mx - p.x;
    const dy = my - p.y;
    if (Math.sqrt(dx * dx + dy * dy) <= radius) return i;
  }
  return -1;
}

function downloadTextFile(filename, content, mime = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function toCupCoord(value, isLat) {
  const hemi = isLat ? (value >= 0 ? "N" : "S") : (value >= 0 ? "E" : "W");
  const abs = Math.abs(value);
  const deg = Math.floor(abs);
  const min = (abs - deg) * 60;
  const degWidth = isLat ? 2 : 3;
  return `${String(deg).padStart(degWidth, "0")}${min.toFixed(3).padStart(6, "0")}${hemi}`;
}

function exportRouteAsCup(routePoints) {
  if (!routePoints.length) return;
  const lines = [
    'name,code,country,lat,lon,elev,style,rwdir,rwlen,freq,desc',
    ...routePoints.map((p, i) =>
      `"TP${i + 1}","TP${i + 1}","UK",${toCupCoord(p.lat, true)},${toCupCoord(p.lon, false)},"0m",1,,,,`
    ),
  ];
  downloadTextFile("thermal-atlas-route.cup", lines.join("\n"), "text/plain;charset=utf-8");
}

function exportRouteAsGpx(routePoints) {
  if (!routePoints.length) return;
  const pts = routePoints.map((p, i) => `
    <rtept lat="${p.lat.toFixed(6)}" lon="${p.lon.toFixed(6)}">
      <name>TP${i + 1}</name>
    </rtept>`).join("");
  const gpx = `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Thermal Atlas UK" xmlns="http://www.topografix.com/GPX/1/1">
  <rte>
    <name>Thermal Atlas Route</name>${pts}
  </rte>
</gpx>`;
  downloadTextFile("thermal-atlas-route.gpx", gpx, "application/gpx+xml;charset=utf-8");
}


function routesEqual(a, b) {
  return (
    Math.abs(a.lat - b.lat) < 0.000001 &&
    Math.abs(a.lon - b.lon) < 0.000001
  );
}

function ensureClosedRoute(points) {
  if (points.length < 3) return points;
  if (routesEqual(points[0], points[points.length - 1])) return points;
  return [...points, { ...points[0] }];
}

function ensureOpenRoute(points) {
  if (points.length < 2) return points;
  if (routesEqual(points[0], points[points.length - 1])) return points.slice(0, -1);
  return points;
}

function reverseRoutePoints(points) {
  if (points.length < 2) return points;
  const open = ensureOpenRoute(points);
  return [...open].reverse();
}


function parseIgcCoord(raw, hemi, isLat) {
  const degLen = isLat ? 2 : 3;
  const deg = Number(raw.slice(0, degLen));
  const mins = Number(raw.slice(degLen)) / 1000;
  const dec = deg + mins / 60;
  return hemi === "S" || hemi === "W" ? -dec : dec;
}

function parseIgcText(text) {
  const pts = [];
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    if (!line.startsWith("B") || line.length < 24) continue;
    const latRaw = line.slice(7, 14);
    const latHemi = line.slice(14, 15);
    const lonRaw = line.slice(15, 23);
    const lonHemi = line.slice(23, 24);
    const lat = parseIgcCoord(latRaw, latHemi, true);
    const lon = parseIgcCoord(lonRaw, lonHemi, false);
    if (Number.isFinite(lat) && Number.isFinite(lon)) pts.push({ lat, lon });
  }
  return pts;
}

// ============================================================
// COMPONENT
// ============================================================
export default function ThermalAtlasPro() {
  const canvasRef = useRef(null);
  const tileCache = useRef({});
  const activePointers = useRef(new Map());
  const pinchState = useRef({
    startDist: null,
    startZoom: null,
    lastStepZoom: null,
  });
  const routeDragIndexRef = useRef(null);
  const routeDragMovedRef = useRef(false);

  const [zoom, setZoom] = useState(8);
  const [center, setCenter] = useState(MAP_CENTER);
  const [basemap, setBasemap] = useState("osm");
  const [kk7Layer, setKk7Layer] = useState("thermals_all_all");
  const [showKK7, setShowKK7] = useState(true);
  const [showSites, setShowSites] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [selectedRegions, setSelectedRegions] = useState(new Set(REGIONS));
  const [hoveredSite, setHoveredSite] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState(null);
  const [loadedTiles, setLoadedTiles] = useState({});
  const [routeMode, setRouteMode] = useState(false);
  const [routePoints, setRoutePoints] = useState([]);

  const [anomalyCells, setAnomalyCells] = useState([]);
  const [anomalyMeta, setAnomalyMeta] = useState(null);
  const [showAnomaly, setShowAnomaly] = useState(true);
  const [thresholdMode, setThresholdMode] = useState("hot2");
  const [anomalyLoadState, setAnomalyLoadState] = useState("loading");
  const [airspaceFeatures, setAirspaceFeatures] = useState([]);
  const [showAirspace, setShowAirspace] = useState(false);
  const [airspaceLoadState, setAirspaceLoadState] = useState("loading");
  const [selectedAirspace, setSelectedAirspace] = useState(null);
  const [showPlannerPanel, setShowPlannerPanel] = useState(false);
  const [igcTrack, setIgcTrack] = useState([]);
  const [igcFileName, setIgcFileName] = useState("");
  const [showIgcTrack, setShowIgcTrack] = useState(true);
  const igcInputRef = useRef(null);

  const [viewportWidth, setViewportWidth] = useState(
    typeof window !== "undefined" ? window.innerWidth : 1024
  );

  const isMobile = viewportWidth < 768;
  const W = isMobile ? Math.max(320, Math.min(viewportWidth - 16, 900)) : 900;
  const H = isMobile ? 520 : 600;
  const TS = 256;

  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/anomaly_grid.json`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setAnomalyCells(data.cells || []);
        setAnomalyMeta(data);
        setAnomalyLoadState("ready");
      })
      .catch((err) => {
        console.error("Failed to load anomaly grid:", err);
        setAnomalyLoadState("error");
      });
  }, []);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/uk_airspace.geojson`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setAirspaceFeatures(preprocessAirspaceGeoJSON(data));
        setAirspaceLoadState("ready");
      })
      .catch((err) => {
        console.error("Failed to load airspace GeoJSON:", err);
        setAirspaceLoadState("error");
      });
  }, []);

  const zoomInt = Math.round(zoom);
  const s = Math.pow(2, zoomInt);
  const cwx = ((center.lon + 180) / 360) * s * TS;
  const cwy =
    ((1 -
      Math.log(
        Math.tan((center.lat * Math.PI) / 180) +
          1 / Math.cos((center.lat * Math.PI) / 180)
      ) /
        Math.PI) /
      2) *
    s *
    TS;
  const ox = cwx - W / 2;
  const oy = cwy - H / 2;
  const txs = Math.floor(ox / TS);
  const tys = Math.floor(oy / TS);
  const txe = Math.ceil((ox + W) / TS);
  const tye = Math.ceil((oy + H) / TS);

  const loadTile = useCallback((url, key) => {
    if (tileCache.current[key]) return;

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.referrerPolicy = "no-referrer";

    img.onload = () => {
      tileCache.current[key] = img;
      setLoadedTiles((p) => ({ ...p, [key]: true }));
    };

    img.onerror = (err) => {
      console.error("Tile failed:", key, url, err);
      tileCache.current[key] = "error";
    };

    tileCache.current[key] = "loading";
    img.src = url;
  }, []);

  const rStats =
    routePoints.length >= 2
      ? (() => {
          let total = 0;
          const legs = [];
          for (let i = 1; i < routePoints.length; i++) {
            const d = haversineKm(
              routePoints[i - 1].lat,
              routePoints[i - 1].lon,
              routePoints[i].lat,
              routePoints[i].lon
            );
            const b = bearing(
              routePoints[i - 1].lat,
              routePoints[i - 1].lon,
              routePoints[i].lat,
              routePoints[i].lon
            );
            total += d;
            legs.push({ dist: d, brg: b });
          }
          return { total, legs };
        })()
      : null;

  const routeClosed =
    routePoints.length >= 2 &&
    routesEqual(routePoints[0], routePoints[routePoints.length - 1]);

  const openRoutePoints = routeClosed ? routePoints.slice(0, -1) : routePoints;

  const legStats = rStats?.legs || [];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#0a1420";
    ctx.fillRect(0, 0, W, H);

    const bm = BASEMAPS[basemap];

    for (let tx = txs; tx <= txe; tx++) {
      for (let ty = tys; ty <= tye; ty++) {
        const px = tx * TS - ox;
        const py = ty * TS - oy;

        const bu = bm.url
          .replace("{z}", zoomInt)
          .replace("{x}", tx)
          .replace("{y}", ty);
        const bk = `bm_${basemap}_${zoomInt}_${tx}_${ty}`;
        loadTile(bu, bk);

        if (tileCache.current[bk] instanceof Image) {
          ctx.globalAlpha = 1;
          ctx.drawImage(tileCache.current[bk], px, py, TS, TS);
        }

        if (showKK7) {
          const tmsY = Math.pow(2, zoomInt) - 1 - ty;
          const kk = `kk7_${kk7Layer}_${zoomInt}_${tx}_${tmsY}`;
          const ku = `https://kk7-proxy.simmo-justin.workers.dev/proxy/tiles/${kk7Layer}/${zoomInt}/${tx}/${tmsY}.png`;
          loadTile(ku, kk);

          if (tileCache.current[kk] instanceof Image) {
            ctx.globalAlpha = basemap === "satellite" ? 0.5 : 0.58;
            ctx.drawImage(tileCache.current[kk], px, py, TS, TS);
            ctx.globalAlpha = 1;
          }
        }
      }
    }

    if (showAnomaly && anomalyCells.length > 0) {
      const size = hotspotCellSize(zoomInt);

      ctx.save();
      ctx.globalCompositeOperation = "source-over";

      for (let i = 0; i < anomalyCells.length; i++) {
        const cell = anomalyCells[i];
        const style = hotspotStyle(cell, thresholdMode);
        if (!style) continue;

        const p = latLonToPixel(cell.lat, cell.lon, zoomInt, ox, oy);

        if (p.x < -size || p.x > W + size || p.y < -size || p.y > H + size) {
          continue;
        }

        ctx.globalAlpha = style.alpha;
        ctx.fillStyle = style.color;
        ctx.fillRect(
          Math.round(p.x - size / 2),
          Math.round(p.y - size / 2),
          size,
          size
        );
      }

      ctx.restore();
      ctx.globalAlpha = 1;
    }

    if (showAirspace && airspaceFeatures.length > 0) {
      drawAirspaceLayer(
        ctx,
        airspaceFeatures,
        (lat, lon) => latLonToPixel(lat, lon, zoomInt, ox, oy),
        selectedAirspace?.id || null
      );
    }

    if (showIgcTrack && igcTrack.length > 1) {
      ctx.save();
      ctx.beginPath();
      igcTrack.forEach((pt, i) => {
        const p = latLonToPixel(pt.lat, pt.lon, zoomInt, ox, oy);
        if (i === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      });
      ctx.strokeStyle = "rgba(255,255,255,0.9)";
      ctx.lineWidth = isMobile ? 2.5 : 2;
      ctx.stroke();

      const start = latLonToPixel(igcTrack[0].lat, igcTrack[0].lon, zoomInt, ox, oy);
      const end = latLonToPixel(igcTrack[igcTrack.length - 1].lat, igcTrack[igcTrack.length - 1].lon, zoomInt, ox, oy);

      ctx.beginPath();
      ctx.arc(start.x, start.y, isMobile ? 5 : 4, 0, Math.PI * 2);
      ctx.fillStyle = "#7CFFB2";
      ctx.fill();

      ctx.beginPath();
      ctx.arc(end.x, end.y, isMobile ? 5 : 4, 0, Math.PI * 2);
      ctx.fillStyle = "#FFD166";
      ctx.fill();
      ctx.restore();
    }

    if (routePoints.length > 0) {
      const rpx = routePoints.map((rp) =>
        latLonToPixel(rp.lat, rp.lon, zoomInt, ox, oy)
      );

      if (rpx.length > 1) {
        ctx.beginPath();
        ctx.strokeStyle = "#00ffcc";
        ctx.lineWidth = 3;
        ctx.setLineDash([8, 4]);

        rpx.forEach((p, i) => {
          if (i === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        });

        ctx.stroke();
        ctx.setLineDash([]);

        for (let i = 1; i < rpx.length; i++) {
          const mx = (rpx[i - 1].x + rpx[i].x) / 2;
          const my = (rpx[i - 1].y + rpx[i].y) / 2;
          const d = haversineKm(
            routePoints[i - 1].lat,
            routePoints[i - 1].lon,
            routePoints[i].lat,
            routePoints[i].lon
          );
          const b = bearing(
            routePoints[i - 1].lat,
            routePoints[i - 1].lon,
            routePoints[i].lat,
            routePoints[i].lon
          );
          ctx.fillStyle = "rgba(0,0,0,0.7)";
          ctx.fillRect(mx - 28, my - 8, 56, 16);
          ctx.font = "bold 9px sans-serif";
          ctx.textAlign = "center";
          ctx.fillStyle = "#00ffcc";
          ctx.fillText(`${d.toFixed(1)}km ${b.toFixed(0)}°`, mx, my + 3);
        }
      }

      rpx.forEach((p, i) => {
        const isStart = i === 0;
        const isLast = i === rpx.length - 1;
        const isClosedFinish = routeClosed && isLast;
        const radius = isMobile ? 8 : 6;

        ctx.beginPath();
        ctx.arc(p.x, p.y, radius + 4, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(0,0,0,0.28)";
        ctx.fill();

        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fillStyle =
          isStart ? "#00ff88" :
          isClosedFinish ? "#ffd166" :
          isLast ? "#ff8844" :
          "#00ccff";
        ctx.fill();
        ctx.strokeStyle = "#001018";
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.font = isMobile ? "bold 10px sans-serif" : "bold 8px sans-serif";
        ctx.fillStyle = "#fff";
        ctx.textAlign = "center";
        ctx.fillText(`${i + 1}`, p.x, p.y + 3);
      });
    }

    if (showSites) {
      SITES.forEach((site) => {
        if (!selectedRegions.has(site.region)) return;
        const p = latLonToPixel(site.lat, site.lon, zoomInt, ox, oy);
        if (p.x < -30 || p.x > W + 30 || p.y < -30 || p.y > H + 30) return;

        const hov = hoveredSite === site.name;
        const r = hov ? 8 : 5;
        const col = REGION_COLORS[site.region] || "#44cc88";

        if (hov) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, 14, 0, Math.PI * 2);
          ctx.fillStyle = `${col}33`;
          ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fillStyle = col;
        ctx.fill();
        ctx.strokeStyle = "#000";
        ctx.lineWidth = 1.5;
        ctx.stroke();

        const dirs = { N: -90, NE: -45, E: 0, SE: 45, S: 90, SW: 135, W: 180, NW: -135 };
        const prim = site.dir.split("-")[0];

        if (dirs[prim] !== undefined) {
          const a = (dirs[prim] * Math.PI) / 180;
          const len = hov ? 14 : 10;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p.x + Math.cos(a) * len, p.y + Math.sin(a) * len);
          ctx.strokeStyle = col;
          ctx.lineWidth = 1.5;
          ctx.stroke();

          const ax = p.x + Math.cos(a) * len;
          const ay = p.y + Math.sin(a) * len;
          ctx.beginPath();
          ctx.moveTo(ax, ay);
          ctx.lineTo(ax - Math.cos(a - 0.5) * 4, ay - Math.sin(a - 0.5) * 4);
          ctx.lineTo(ax - Math.cos(a + 0.5) * 4, ay - Math.sin(a + 0.5) * 4);
          ctx.closePath();
          ctx.fillStyle = col;
          ctx.fill();
        }

        if (showLabels && (zoomInt >= 9 || hov)) {
          ctx.font = hov ? "bold 11px sans-serif" : "10px sans-serif";
          ctx.fillStyle = "#fff";
          ctx.textAlign = "left";
          ctx.strokeStyle = "#000";
          ctx.lineWidth = 2.5;
          ctx.strokeText(site.name, p.x + r + 4, p.y + 3);
          ctx.fillText(site.name, p.x + r + 4, p.y + 3);

          if (hov) {
            ctx.font = "9px sans-serif";
            ctx.fillStyle = "#aaddff";
            const info = `${site.dir} | ${site.elev}m | ${site.club}`;
            ctx.strokeText(info, p.x + r + 4, p.y + 15);
            ctx.fillText(info, p.x + r + 4, p.y + 15);
          }
        }
      });
    }

    ctx.font = "9px sans-serif";
    ctx.fillStyle = "rgba(255,255,255,0.35)";
    ctx.textAlign = "right";
    ctx.fillText(`${bm.attr} | Thermals © thermal.kk7.ch CC-BY-NC-SA`, W - 8, H - 6);
  }, [
    zoomInt,
    center,
    basemap,
    showKK7,
    kk7Layer,
    showSites,
    showLabels,
    selectedRegions,
    hoveredSite,
    loadedTiles,
    routePoints,
    ox,
    oy,
    txs,
    txe,
    tys,
    tye,
    anomalyCells,
    showAnomaly,
    thresholdMode,
    airspaceFeatures,
    showAirspace,
    selectedAirspace,
    igcTrack,
    showIgcTrack,
    loadTile,
    W,
    H,
  ]);

  const handleMouseDown = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = (e.clientX - rect.left) * (W / rect.width);
    const my = (e.clientY - rect.top) * (H / rect.height);

    if (routeMode) {
      const idx = routePointHitIndex(routePoints, mx, my, zoomInt, ox, oy, isMobile ? 18 : 12);
      if (idx >= 0) {
        routeDragIndexRef.current = idx;
        routeDragMovedRef.current = false;
      }
      return;
    }

    setIsDragging(true);
    setDragStart({
      x: e.clientX,
      y: e.clientY,
      lat: center.lat,
      lon: center.lon,
    });
  };

  const handleMouseMove = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = (e.clientX - rect.left) * (W / rect.width);
    const my = (e.clientY - rect.top) * (H / rect.height);

    if (routeMode && routeDragIndexRef.current !== null) {
      const ll = pixelToLatLon(mx, my, zoomInt, ox, oy);
      routeDragMovedRef.current = true;
      setRoutePoints((prev) =>
        prev.map((p, i) => (i === routeDragIndexRef.current ? ll : p))
      );
      return;
    }

    if (isDragging && dragStart && !routeMode) {
      const dx = e.clientX - dragStart.x;
      const dy = e.clientY - dragStart.y;
      const sr = W / rect.width;
      const ws = Math.pow(2, zoomInt) * TS;

      setCenter({
        lat: Math.max(50, Math.min(53, dragStart.lat + ((dy * sr) / ws) * 180)),
        lon: Math.max(-6, Math.min(2.5, dragStart.lon - ((dx * sr) / ws) * 360)),
      });
      return;
    }

    let found = null;
    SITES.forEach((si) => {
      if (!selectedRegions.has(si.region)) return;
      const p = latLonToPixel(si.lat, si.lon, zoomInt, ox, oy);
      if (Math.sqrt((mx - p.x) ** 2 + (my - p.y) ** 2) < 12) found = si.name;
    });
    setHoveredSite(found);
  };

  const handleMouseUp = () => {
    routeDragIndexRef.current = null;
    setIsDragging(false);
    setDragStart(null);
  };

  const handleClick = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = (e.clientX - rect.left) * (W / rect.width);
    const my = (e.clientY - rect.top) * (H / rect.height);

    if (routeMode) {
      if (routeDragMovedRef.current) {
        routeDragMovedRef.current = false;
        return;
      }

      const idx = routePointHitIndex(routePoints, mx, my, zoomInt, ox, oy, isMobile ? 18 : 12);
      if (idx >= 0) return;

      setRoutePoints((prev) => [...prev, pixelToLatLon(mx, my, zoomInt, ox, oy)]);
      return;
    }

    if (showAirspace && airspaceFeatures.length > 0) {
      const ll = pixelToLatLon(mx, my, zoomInt, ox, oy);
      setSelectedAirspace(findAirspaceAtPoint(airspaceFeatures, ll.lon, ll.lat));
    }
  };

  const handleWheel = (e) => {
    e.preventDefault();
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = (e.clientX - rect.left) * (W / rect.width);
    const my = (e.clientY - rect.top) * (H / rect.height);
    const nz = e.deltaY < 0 ? Math.min(zoomInt + 1, 13) : Math.max(zoomInt - 1, 6);
    if (nz === zoomInt) return;

    const r = Math.pow(2, nz) / Math.pow(2, zoomInt);
    const nwx = (ox + mx) * r - mx + W / 2;
    const nwy = (oy + my) * r - my + H / 2;
    const ns = Math.pow(2, nz) * TS;
    const nl = (nwx / ns) * 360 - 180;
    const nn = Math.PI - (2 * Math.PI * nwy) / ns;

    setZoom(nz);
    setCenter({
      lat: Math.max(
        50,
        Math.min(53, (180 / Math.PI) * Math.atan(0.5 * (Math.exp(nn) - Math.exp(-nn))))
      ),
      lon: Math.max(-6, Math.min(2.5, nl)),
    });
  };

  const handlePointerDown = useCallback(
    (e) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      canvas.setPointerCapture?.(e.pointerId);

      activePointers.current.set(e.pointerId, {
        x: e.clientX,
        y: e.clientY,
      });

      const rect = canvas.getBoundingClientRect();
      const mx = (e.clientX - rect.left) * (W / rect.width);
      const my = (e.clientY - rect.top) * (H / rect.height);
      const pts = Array.from(activePointers.current.values());

      if (pts.length === 1 && routeMode) {
        const idx = routePointHitIndex(routePoints, mx, my, zoomInt, ox, oy, isMobile ? 22 : 14);
        if (idx >= 0) {
          routeDragIndexRef.current = idx;
          routeDragMovedRef.current = false;
        }
        return;
      }

      if (pts.length === 1 && !routeMode) {
        setIsDragging(true);
        setDragStart({
          x: e.clientX,
          y: e.clientY,
          lat: center.lat,
          lon: center.lon,
        });
      }

      if (pts.length === 2) {
        routeDragIndexRef.current = null;
        setIsDragging(false);
        setDragStart(null);
        pinchState.current.startDist = distanceBetweenTouches(pts[0], pts[1]);
        pinchState.current.startZoom = zoomInt;
        pinchState.current.lastStepZoom = zoomInt;
      }
    },
    [W, H, center.lat, center.lon, routeMode, routePoints, zoomInt, ox, oy, isMobile]
  );

  const handlePointerMove = useCallback(
    (e) => {
      if (!activePointers.current.has(e.pointerId)) return;

      activePointers.current.set(e.pointerId, {
        x: e.clientX,
        y: e.clientY,
      });

      const rect = canvasRef.current.getBoundingClientRect();
      const mx = (e.clientX - rect.left) * (W / rect.width);
      const my = (e.clientY - rect.top) * (H / rect.height);
      const pts = Array.from(activePointers.current.values());

      if (pts.length === 2) {
        e.preventDefault();

        const dist = distanceBetweenTouches(pts[0], pts[1]);
        const startDist = pinchState.current.startDist;
        const startZoom = pinchState.current.startZoom;

        if (startDist && startZoom !== null) {
          const scaleFactor = dist / startDist;
          const zoomDelta = Math.log2(scaleFactor);
          const steppedZoom = Math.max(6, Math.min(13, Math.round(startZoom + zoomDelta)));

          if (steppedZoom !== pinchState.current.lastStepZoom) {
            pinchState.current.lastStepZoom = steppedZoom;
            setZoom(steppedZoom);
          }
        }
        return;
      }

      if (routeMode && pts.length === 1 && routeDragIndexRef.current !== null) {
        e.preventDefault();
        const ll = pixelToLatLon(mx, my, zoomInt, ox, oy);
        routeDragMovedRef.current = true;
        setRoutePoints((prev) =>
          prev.map((p, i) => (i === routeDragIndexRef.current ? ll : p))
        );
        return;
      }

      if (pts.length === 1 && isDragging && dragStart && !routeMode) {
        e.preventDefault();
        const dx = e.clientX - dragStart.x;
        const dy = e.clientY - dragStart.y;
        const sr = W / rect.width;
        const ws = Math.pow(2, zoomInt) * TS;

        setCenter({
          lat: Math.max(50, Math.min(53, dragStart.lat + ((dy * sr) / ws) * 180)),
          lon: Math.max(-6, Math.min(2.5, dragStart.lon - ((dx * sr) / ws) * 360)),
        });
        return;
      }

      let found = null;
      SITES.forEach((si) => {
        if (!selectedRegions.has(si.region)) return;
        const p = latLonToPixel(si.lat, si.lon, zoomInt, ox, oy);
        if (Math.sqrt((mx - p.x) ** 2 + (my - p.y) ** 2) < 12) found = si.name;
      });
      setHoveredSite(found);
    },
    [W, H, dragStart, isDragging, ox, oy, routeMode, selectedRegions, zoomInt]
  );

  const handlePointerUp = useCallback((e) => {
    activePointers.current.delete(e.pointerId);
    const pts = Array.from(activePointers.current.values());

    if (pts.length < 2) {
      pinchState.current.startDist = null;
      pinchState.current.startZoom = null;
      pinchState.current.lastStepZoom = null;
    }

    if (pts.length === 0) {
      routeDragIndexRef.current = null;
      setIsDragging(false);
      setDragStart(null);
    }
  }, []);

  const handlePointerCancel = useCallback((e) => {
    activePointers.current.delete(e.pointerId);
    pinchState.current.startDist = null;
    pinchState.current.startZoom = null;
    pinchState.current.lastStepZoom = null;
    routeDragIndexRef.current = null;

    if (activePointers.current.size === 0) {
      setIsDragging(false);
      setDragStart(null);
    }
  }, []);

  const handleIgcImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const content = await file.text();
    const pts = parseIgcText(content);

    setIgcTrack(pts);
    setIgcFileName(file.name);
    setShowIgcTrack(true);

    if (pts.length > 0) {
      let minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity;
      for (const p of pts) {
        if (p.lat < minLat) minLat = p.lat;
        if (p.lat > maxLat) maxLat = p.lat;
        if (p.lon < minLon) minLon = p.lon;
        if (p.lon > maxLon) maxLon = p.lon;
      }

      const centerLat = (minLat + maxLat) / 2;
      const centerLon = (minLon + maxLon) / 2;
      const spanLat = Math.max(0.01, maxLat - minLat);
      const spanLon = Math.max(0.01, maxLon - minLon);

      let nextZoom = 11;
      if (spanLat > 1.8 || spanLon > 2.5) nextZoom = 7;
      else if (spanLat > 0.9 || spanLon > 1.3) nextZoom = 8;
      else if (spanLat > 0.45 || spanLon > 0.7) nextZoom = 9;
      else if (spanLat > 0.2 || spanLon > 0.35) nextZoom = 10;

      setCenter({ lat: centerLat, lon: centerLon });
      setZoom(nextZoom);
    }

    e.target.value = "";
  };

  const toggleRegion = (r) => {
    setSelectedRegions((p) => {
      const n = new Set(p);
      if (n.has(r)) n.delete(r);
      else n.add(r);
      return n;
    });
  };

  return (
    <div
      style={{
        background: "#080e18",
        color: "#c8d4e0",
        fontFamily: "'DM Sans','Segoe UI',sans-serif",
        minHeight: "100vh",
      }}
    >
      <div style={{ maxWidth: 940, margin: "0 auto", padding: "8px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 10,
            gap: 10,
            padding: isMobile ? "10px 12px" : "12px 14px",
            borderRadius: 16,
            background: "rgba(18,28,44,0.92)",
            border: "1px solid rgba(255,255,255,0.06)",
            boxShadow: "0 10px 26px rgba(0,0,0,0.22)",
          }}
        >
          <div>
            <h1
              style={{
                fontSize: isMobile ? 18 : 16,
                color: "#7cc8ff",
                margin: 0,
                letterSpacing: 1.5,
                fontWeight: 800,
              }}
            >
              THERMAL ATLAS UK
            </h1>
            <p style={{ fontSize: isMobile ? 11 : 10, opacity: 0.55, margin: "2px 0 0 0" }}>
              Soaring planner · thermals · airspace · route tools
            </p>
          </div>
          <div
            style={{
              display: "flex",
              gap: 6,
              alignItems: "center",
              padding: "6px",
              borderRadius: 14,
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.05)",
            }}
          >
            <button onClick={() => setZoom((z) => Math.min(Math.round(z) + 1, 13))} style={btnS(isMobile)}>+</button>
            <span style={{ fontSize: 11, color: "#88aacc", minWidth: 30, textAlign: "center", fontWeight: 700 }}>z{zoomInt}</span>
            <button onClick={() => setZoom((z) => Math.max(Math.round(z) - 1, 6))} style={btnS(isMobile)}>−</button>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            gap: 6,
            marginBottom: 8,
            flexWrap: "wrap",
            alignItems: "center",
            padding: isMobile ? "8px 10px" : "9px 12px",
            borderRadius: 14,
            background: "rgba(18,28,44,0.88)",
            border: "1px solid rgba(255,255,255,0.05)",
          }}
        >
          <span style={lblS(isMobile)}>Base:</span>
          {Object.entries(BASEMAPS).map(([k, v]) => (
            <button
              key={k}
              onClick={() => setBasemap(k)}
              style={{
                ...tabS(isMobile),
                fontWeight: basemap === k ? 700 : 400,
                background: basemap === k ? "#1a3a5a" : "rgba(255,255,255,0.04)",
                color: basemap === k ? "#88bbdd" : "#556677",
              }}
            >
              {v.label}
            </button>
          ))}

          <span style={sepS}>|</span>

          <span style={lblS(isMobile)}>KK7:</span>
          {Object.entries(KK7_LAYERS).map(([k, v]) => (
            <button
              key={k}
              onClick={() => {
                setKk7Layer(k);
                setShowKK7(true);
              }}
              style={{
                ...tabS(isMobile),
                fontSize: isMobile ? 9 : 8,
                padding: isMobile ? "6px 8px" : "2px 5px",
                fontWeight: kk7Layer === k && showKK7 ? 700 : 400,
                background:
                  kk7Layer === k && showKK7 ? "#1a4a7a" : "rgba(255,255,255,0.03)",
                color: kk7Layer === k && showKK7 ? "#88ccff" : "#445566",
              }}
            >
              {v.label}
            </button>
          ))}

          <button
            onClick={() => setShowKK7(!showKK7)}
            style={{
              ...tabS(isMobile),
              background: showKK7 ? "rgba(255,100,50,0.1)" : "rgba(255,255,255,0.03)",
              color: showKK7 ? "#ff8866" : "#556677",
            }}
          >
            {showKK7 ? "Hide" : "Show"}
          </button>
        </div>



        <div
          style={{
            borderRadius: 8,
            overflow: "hidden",
            border: "1px solid rgba(120,180,255,0.12)",
            touchAction: "none",
            overscrollBehavior: "contain",
          }}
        >
          <input
            ref={igcInputRef}
            type="file"
            accept=".igc,.icg"
            onChange={handleIgcImport}
            style={{ display: "none" }}
          />
          <canvas
            ref={canvasRef}
            width={W}
            height={H}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onClick={handleClick}
            onMouseLeave={() => {
              setIsDragging(false);
              setHoveredSite(null);
            }}
            onWheel={handleWheel}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerCancel}
            onPointerLeave={handlePointerUp}
            style={{
              display: "block",
              width: "100%",
              height: "auto",
              touchAction: "none",
              overscrollBehavior: "contain",
              WebkitUserSelect: "none",
              userSelect: "none",
              cursor: routeMode ? "crosshair" : isDragging ? "grabbing" : "grab",
            }}
          />
        </div>

        {routeMode && showPlannerPanel && (
          <div
            style={{
              marginTop: 6,
              padding: isMobile ? "10px" : "10px 12px",
              background: "rgba(18,28,44,0.96)",
              borderRadius: 10,
              border: "1px solid rgba(120,180,255,0.14)",
              fontSize: 11,
              boxShadow: "0 10px 24px rgba(0,0,0,0.25)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <span style={{ fontWeight: 800, color: "#dce8f8", fontSize: 15 }}>Planner</span>
              <button onClick={() => setShowPlannerPanel(false)} style={panelCloseBtnS}>✕</button>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
              <div style={plannerStatBoxS}>
                <div style={plannerStatLabelS}>Total distance</div>
                <div style={plannerStatValueS}>{rStats ? rStats.total.toFixed(1) : "0.0"} km</div>
              </div>
              <div style={plannerStatBoxS}>
                <div style={plannerStatLabelS}>Legs</div>
                <div style={plannerStatValueS}>{legStats.length}</div>
              </div>
              <div style={plannerStatBoxS}>
                <div style={plannerStatLabelS}>Points</div>
                <div style={plannerStatValueS}>{openRoutePoints.length}</div>
              </div>
              <div style={plannerStatBoxS}>
                <div style={plannerStatLabelS}>Task</div>
                <div style={plannerStatValueS}>{routeClosed ? "Closed" : "Open"}</div>
              </div>
            </div>

            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
              <button onClick={() => setRoutePoints((p) => p.slice(0, -1))} style={{ ...tabS(isMobile), color: "#ffcc66" }}>Undo</button>
              <button onClick={() => setRoutePoints([])} style={{ ...tabS(isMobile), color: "#ff8866" }}>Clear</button>
              <button onClick={() => setRoutePoints((p) => reverseRoutePoints(p))} style={{ ...tabS(isMobile), color: "#c6b6ff" }}>Reverse</button>
              <button
                onClick={() => setRoutePoints((p) => (routeClosed ? ensureOpenRoute(p) : ensureClosedRoute(p)))}
                style={{ ...tabS(isMobile), color: routeClosed ? "#8cc8ff" : "#9ee37d" }}
              >
                {routeClosed ? "Open Task" : "Close Task"}
              </button>
              <button onClick={() => exportRouteAsCup(openRoutePoints)} style={{ ...tabS(isMobile), color: "#9ee37d" }}>Export CUP</button>
              <button onClick={() => exportRouteAsGpx(openRoutePoints)} style={{ ...tabS(isMobile), color: "#8cc8ff" }}>Export GPX</button>
            </div>

            {legStats.length > 0 && (
              <div style={{ display: "grid", gap: 6 }}>
                {legStats.map((l, i) => (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 10,
                      padding: "8px 10px",
                      borderRadius: 8,
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid rgba(255,255,255,0.05)",
                    }}
                  >
                    <span style={{ color: "#d8e4f4", fontWeight: 700 }}>Leg {i + 1}</span>
                    <span style={{ opacity: 0.82 }}>{l.dist.toFixed(1)} km</span>
                    <span style={{ opacity: 0.62 }}>{l.brg.toFixed(0)}°</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {routeMode && routePoints.length === 0 && (
          <div
            style={{
              marginTop: 4,
              padding: "5px 10px",
              background: "rgba(0,255,200,0.04)",
              borderRadius: 6,
              fontSize: 10,
              color: "#66bbaa",
            }}
          >
            Tap to add turnpoints. Drag numbered points to move them. Open the Planner panel from the bottom bar for total distance, leg breakdown, task controls, and export.
          </div>
        )}

        {routeMode && (
          <div
            style={{
              marginTop: 6,
              padding: "8px 10px",
              background: "rgba(18,28,44,0.96)",
              borderRadius: 8,
              border: "1px solid rgba(120,180,255,0.12)",
              fontSize: 11,
              display: "flex",
              gap: 10,
              flexWrap: "wrap",
              alignItems: "center",
            }}
          >
            <span style={{ fontWeight: 800, color: "#dce8f8" }}>PLANNER SUMMARY</span>
            <span style={{ opacity: 0.78 }}>Points: <b>{openRoutePoints.length}</b></span>
            <span style={{ opacity: 0.78 }}>Legs: <b>{legStats.length}</b></span>
            <span style={{ opacity: 0.95, color: "#9ee37d" }}>
              Total: <b>{rStats ? rStats.total.toFixed(1) : "0.0"} km</b>
            </span>
            {legStats.map((l, i) => (
              <span key={i} style={{ opacity: 0.7, fontSize: 10 }}>
                L{i + 1}: {l.dist.toFixed(1)} km · {l.brg.toFixed(0)}°
              </span>
            ))}
          </div>
        )}

        {selectedAirspace && !routeMode && (
          <div
            style={{
              marginTop: 4,
              padding: "6px 10px",
              background: "rgba(167,139,250,0.08)",
              borderRadius: 6,
              border: "1px solid rgba(167,139,250,0.16)",
              fontSize: 11,
              display: "flex",
              gap: 14,
              flexWrap: "wrap",
              alignItems: "center",
            }}
          >
            <span style={{ fontWeight: 700, color: "#b79cff" }}>{selectedAirspace.name}</span>
            <span>Type: <b>{selectedAirspace.type || "—"}</b></span>
            <span>Base: <b>{selectedAirspace.lower || "—"}</b></span>
            <span>Top: <b>{selectedAirspace.upper || "—"}</b></span>
          </div>
        )}

        {hoveredSite && !routeMode && (() => {
          const si = SITES.find((s) => s.name === hoveredSite);
          return si ? (
            <div
              style={{
                marginTop: 4,
                padding: "6px 10px",
                background: "rgba(34,204,136,0.08)",
                borderRadius: 6,
                border: "1px solid rgba(34,204,136,0.12)",
                fontSize: 11,
                display: "flex",
                gap: 14,
                flexWrap: "wrap",
                alignItems: "center",
              }}
            >
              <span style={{ fontWeight: 700, color: REGION_COLORS[si.region] }}>{si.name}</span>
              <span>Wind: <b>{si.dir}</b></span>
              <span>Elev: <b>{si.elev}m</b></span>
              <span>{si.region}</span>
              <span>Club: {si.club}</span>
              <span style={{ opacity: 0.5 }}>
                {si.lat.toFixed(3)}°N {Math.abs(si.lon).toFixed(3)}°{si.lon < 0 ? "W" : "E"}
              </span>
            </div>
          ) : null;
        })()}

        <div
          style={{
            position: "sticky",
            bottom: 8,
            zIndex: 20,
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            alignItems: "center",
            marginTop: 10,
            padding: "8px",
            borderRadius: 14,
            background: "rgba(16,22,34,0.94)",
            border: "1px solid rgba(255,255,255,0.06)",
            boxShadow: "0 10px 30px rgba(0,0,0,0.25)",
          }}
        >
          <button onClick={() => setShowPlannerPanel((v) => !v)} style={bottomNavBtnS(showPlannerPanel)}>
            Planner
          </button>
          <button onClick={() => setRouteMode((v) => !v)} style={bottomNavBtnS(routeMode)}>
            Route
          </button>
          <button onClick={() => setShowSites((v) => !v)} style={bottomToggleWrapS}>
            <span style={switchS(showSites)}><span style={switchKnobS(showSites)} /></span>
            Sites
          </button>
          <button onClick={() => setShowLabels((v) => !v)} style={bottomToggleWrapS}>
            <span style={switchS(showLabels)}><span style={switchKnobS(showLabels)} /></span>
            Labels
          </button>
          <button onClick={() => setShowAnomaly((v) => !v)} style={bottomToggleWrapS}>
            <span style={switchS(showAnomaly)}><span style={switchKnobS(showAnomaly)} /></span>
            Anomaly
          </button>
          <button onClick={() => setShowKK7((v) => !v)} style={bottomToggleWrapS}>
            <span style={switchS(showKK7)}><span style={switchKnobS(showKK7)} /></span>
            KK7
          </button>
          <button onClick={() => setShowAirspace((v) => !v)} style={bottomToggleWrapS}>
            <span style={switchS(showAirspace)}><span style={switchKnobS(showAirspace)} /></span>
            Airspace
          </button>
          <button onClick={() => igcInputRef.current?.click()} style={bottomNavBtnS(false)}>
            Import IGC
          </button>
          {igcTrack.length > 0 && (
            <button onClick={() => setShowIgcTrack((v) => !v)} style={bottomToggleWrapS}>
              <span style={switchS(showIgcTrack)}><span style={switchKnobS(showIgcTrack)} /></span>
              Track
            </button>
          )}
        </div>

        {igcFileName && (
          <div
            style={{
              marginTop: 6,
              padding: "7px 10px",
              background: "rgba(255,255,255,0.03)",
              borderRadius: 8,
              fontSize: 10,
              color: "#9fb4c9",
            }}
          >
            IGC loaded: <b>{igcFileName}</b> · {igcTrack.length.toLocaleString()} points
          </div>
        )}

        <div style={{ display: "flex", gap: 5, marginTop: 5, flexWrap: "wrap" }}>
          <div style={pnlS}>
            <div style={pnlT}>KK7 THERMALS</div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 3 }}>
              <div
                style={{
                  width: 55,
                  height: 8,
                  borderRadius: 2,
                  background:
                    "linear-gradient(90deg, transparent, #3344aa, #44aa44, #aacc00, #ff8800, #ff2200)",
                }}
              />
              <span style={{ fontSize: 8, opacity: 0.5 }}>Low → High</span>
            </div>
            <div style={{ fontSize: 8, opacity: 0.4, marginTop: 2 }}>{KK7_LAYERS[kk7Layer]?.desc}</div>
          </div>

          <div style={pnlS}>
            <div style={pnlT}>ANOMALY HOTSPOTS</div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 3, flexWrap: "wrap" }}>
              <div style={{ width: 12, height: 8, background: "rgba(255,174,50,0.20)", borderRadius: 2 }} />
              <span style={{ fontSize: 8, opacity: 0.65 }}>+2°C candidate</span>
              <div style={{ width: 12, height: 8, background: "rgba(255,50,24,0.38)", borderRadius: 2, marginLeft: 8 }} />
              <span style={{ fontSize: 8, opacity: 0.65 }}>+3°C strong trigger</span>
            </div>
            <div style={{ fontSize: 8, opacity: 0.45, marginTop: 2 }}>
              {anomalyLoadState === "loading" && "Loading anomaly grid..."}
              {anomalyLoadState === "error" && "Failed to load /data/anomaly_grid.json"}
              {anomalyLoadState === "ready" &&
                `${anomalyCells.length.toLocaleString()} cells loaded${anomalyMeta?.scale_m ? ` @ ${anomalyMeta.scale_m}m` : ""}`}
            </div>
          </div>

          <div style={pnlS}>
            <div style={pnlT}>AIRSPACE</div>
            <div style={{ fontSize: 8, opacity: 0.5, marginTop: 2 }}>
              {airspaceLoadState === "loading" && "Loading uk_airspace.geojson..."}
              {airspaceLoadState === "error" && "Missing /data/uk_airspace.geojson"}
              {airspaceLoadState === "ready" && `${airspaceFeatures.length.toLocaleString()} zones loaded`}
            </div>
            <div style={{ fontSize: 8, opacity: 0.4, marginTop: 2 }}>
              Tap a zone to inspect name, class, base and top.
            </div>
          </div>

          <div style={pnlS}>
            <div style={pnlT}>BASEMAP GUIDE</div>
            <div style={{ fontSize: 8, opacity: 0.5, marginTop: 2 }}>
              <b>Terrain:</b> elevation contours, hillshading, slope aspect.
              <b> Satellite:</b> land cover, quarries, bare ground, crop types, forests.
              <b> Streets:</b> roads, villages, towns, railways.
            </div>
          </div>

          <div style={pnlS}>
            <div style={pnlT}>{SITES.filter((si) => selectedRegions.has(si.region)).length} SITES</div>
            <div style={{ fontSize: 8, opacity: 0.5, marginTop: 2 }}>
              Arrow = primary launch wind. Hover = elevation, club, coords.
            </div>
          </div>
        </div>

        <div
          style={{
            marginTop: 5,
            padding: "7px 10px",
            background: "rgba(255,255,255,0.02)",
            borderRadius: 6,
            fontSize: 9,
            lineHeight: 1.6,
            opacity: 0.45,
          }}
        >
          <b>How to use:</b> Switch basemap to <b>Terrain</b> to see elevation and slope aspect, or to <b>Satellite</b> to
          identify quarries, bare ground, ploughed fields, and crop boundaries. Overlay KK7 thermal data and compare it with your
          own anomaly hotspot layer. Use <b>+2°C</b> for broader candidate triggers and <b>+3°C</b> for stronger, higher-confidence
          thermal trigger zones. Use the <b>Route Planner</b> to sketch XC legs over the hotspot structure.
        </div>
      </div>
    </div>
  );
}

const btnS = (isMobile = false) => ({
  padding: isMobile ? "10px 14px" : "6px 12px",
  minWidth: isMobile ? 44 : "auto",
  minHeight: isMobile ? 44 : "auto",
  borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.06)",
  cursor: "pointer",
  background: "rgba(255,255,255,0.06)",
  color: "#88aacc",
  fontSize: isMobile ? 16 : 13,
  fontWeight: 700,
});

const tabS = (isMobile = false) => ({
  padding: isMobile ? "8px 12px" : "5px 10px",
  minHeight: isMobile ? 38 : "auto",
  borderRadius: 999,
  border: "1px solid rgba(255,255,255,0.05)",
  cursor: "pointer",
  fontSize: isMobile ? 11 : 10,
  background: "rgba(255,255,255,0.04)",
});

const chkS = (isMobile = false) => ({
  fontSize: isMobile ? 12 : 10,
  display: "flex",
  alignItems: "center",
  gap: 4,
  cursor: "pointer",
  color: "#889aaa",
});

const toggleBtnS = (isMobile = false, active = false, activeBg = "rgba(255,255,255,0.12)", activeColor = "#c8d4e0") => ({
  ...tabS(isMobile),
  minHeight: isMobile ? 38 : "auto",
  fontWeight: 700,
  background: active ? activeBg : "rgba(255,255,255,0.04)",
  color: active ? activeColor : "#667788",
});

const lblS = (isMobile = false) => ({
  fontSize: isMobile ? 11 : 10,
  color: "#556677",
  marginRight: 2,
});

const sepS = {
  fontSize: 10,
  opacity: 0.15,
  margin: "0 3px",
};

const pnlS = {
  flex: 1,
  minWidth: 150,
  background: "rgba(255,255,255,0.03)",
  borderRadius: 6,
  padding: "5px 8px",
  border: "1px solid rgba(120,180,255,0.05)",
};

const pnlT = {
  fontSize: 9,
  fontWeight: 700,
  color: "#6699bb",
  letterSpacing: 0.5,
};


const switchS = (active = false) => ({
  width: 38,
  height: 22,
  borderRadius: 999,
  background: active ? "#8fd14f" : "rgba(255,255,255,0.14)",
  position: "relative",
  transition: "all 0.2s ease",
  display: "inline-block",
  flexShrink: 0,
});

const switchKnobS = (active = false) => ({
  position: "absolute",
  top: 3,
  left: active ? 19 : 3,
  width: 16,
  height: 16,
  borderRadius: "50%",
  background: "#fff",
  transition: "all 0.2s ease",
});

const bottomToggleWrapS = {
  display: "inline-flex",
  alignItems: "center",
  gap: 8,
  padding: "8px 10px",
  borderRadius: 12,
  border: "1px solid rgba(255,255,255,0.06)",
  background: "rgba(255,255,255,0.03)",
  color: "#d7e2f0",
  cursor: "pointer",
  fontSize: 12,
  fontWeight: 700,
};

const bottomNavBtnS = (active = false) => ({
  padding: "8px 12px",
  borderRadius: 12,
  border: "1px solid rgba(255,255,255,0.06)",
  background: active ? "rgba(143,209,79,0.18)" : "rgba(255,255,255,0.03)",
  color: active ? "#c8f08c" : "#d7e2f0",
  cursor: "pointer",
  fontSize: 12,
  fontWeight: 700,
});

const plannerStatBoxS = {
  minWidth: 110,
  padding: "8px 10px",
  borderRadius: 8,
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.05)",
};

const plannerStatLabelS = {
  fontSize: 10,
  opacity: 0.6,
};

const plannerStatValueS = {
  fontSize: 18,
  fontWeight: 800,
  color: "#e6eef8",
};

const panelCloseBtnS = {
  width: 28,
  height: 28,
  borderRadius: 999,
  border: "1px solid rgba(255,255,255,0.08)",
  background: "rgba(255,255,255,0.04)",
  color: "#d7e2f0",
  cursor: "pointer",
  fontWeight: 700,
};
