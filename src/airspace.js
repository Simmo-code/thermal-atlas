function flattenCoords(coords, out = []) {
  if (!Array.isArray(coords)) return out;
  if (typeof coords[0] === "number" && typeof coords[1] === "number") {
    out.push(coords);
    return out;
  }
  for (const item of coords) flattenCoords(item, out);
  return out;
}

function computeBBox(geometry) {
  const pts = flattenCoords(geometry?.coordinates || []);
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
  for (const [lon, lat] of pts) {
    if (lon < minLon) minLon = lon;
    if (lon > maxLon) maxLon = lon;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }
  return { minLon, minLat, maxLon, maxLat };
}

function polygonSetsFromGeometry(geometry) {
  if (!geometry) return [];
  if (geometry.type === "Polygon") return [geometry.coordinates];
  if (geometry.type === "MultiPolygon") return geometry.coordinates;
  return [];
}

function pointInRing(lon, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    const intersect = (yi > lat) !== (yj > lat) &&
      lon < ((xj - xi) * (lat - yi)) / ((yj - yi) || 1e-12) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function pointInPolygonSet(lon, lat, polygon) {
  if (!polygon?.length) return false;
  if (!pointInRing(lon, lat, polygon[0])) return false;
  for (let i = 1; i < polygon.length; i++) {
    if (pointInRing(lon, lat, polygon[i])) return false;
  }
  return true;
}

function pointInFeature(lon, lat, feature) {
  const { minLon, minLat, maxLon, maxLat } = feature.bbox || {};
  if (
    minLon === undefined ||
    lon < minLon || lon > maxLon ||
    lat < minLat || lat > maxLat
  ) return false;

  for (const poly of polygonSetsFromGeometry(feature.geometry)) {
    if (pointInPolygonSet(lon, lat, poly)) return true;
  }
  return false;
}

function airspaceStyle(type) {
  const t = String(type || "").toUpperCase();
  if (t.includes("CTR")) return { stroke: "#ff5a5a", fill: "rgba(255,90,90,0.12)" };
  if (t.includes("TMA") || t === "A" || t.includes("CLASS A")) return { stroke: "#ff9f43", fill: "rgba(255,159,67,0.10)" };
  if (t === "D" || t.includes("CLASS D")) return { stroke: "#4dabf7", fill: "rgba(77,171,247,0.10)" };
  if (t === "C" || t.includes("CLASS C")) return { stroke: "#a78bfa", fill: "rgba(167,139,250,0.10)" };
  if (t.includes("TMZ")) return { stroke: "#ffd43b", fill: "rgba(255,212,59,0.10)" };
  if (t.includes("RMZ")) return { stroke: "#63e6be", fill: "rgba(99,230,190,0.10)" };
  return { stroke: "#94a3b8", fill: "rgba(148,163,184,0.08)" };
}

export function preprocessAirspaceGeoJSON(data) {
  const features = Array.isArray(data?.features) ? data.features : [];
  return features
    .filter((f) => f?.geometry?.type === "Polygon" || f?.geometry?.type === "MultiPolygon")
    .map((f, i) => {
      const p = f.properties || {};
      return {
        id: p.id || p.ID || `airspace_${i}`,
        name: p.name || p.NAME || p.title || p.Title || `Airspace ${i + 1}`,
        type: p.class || p.CLASS || p.type || p.TYPE || p.category || p.CATEGORY || "",
        lower: p.lower || p.LOWER || p.lowerLimit || p.lower_limit || "",
        upper: p.upper || p.UPPER || p.upperLimit || p.upper_limit || "",
        geometry: f.geometry,
        bbox: computeBBox(f.geometry),
        properties: p,
      };
    });
}

export function drawAirspaceLayer(ctx, features, project, selectedId) {
  for (const feature of features) {
    const style = airspaceStyle(feature.type);
    const selected = feature.id === selectedId;
    const polygons = polygonSetsFromGeometry(feature.geometry);

    ctx.save();
    ctx.strokeStyle = style.stroke;
    ctx.fillStyle = style.fill;
    ctx.lineWidth = selected ? 2.2 : 1.1;
    ctx.globalAlpha = selected ? 0.95 : 0.9;

    for (const polygon of polygons) {
      if (!polygon.length) continue;
      ctx.beginPath();
      polygon.forEach((ring) => {
        ring.forEach(([lon, lat], idx) => {
          const p = project(lat, lon);
          if (idx === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        });
        ctx.closePath();
      });
      ctx.fill("evenodd");
      ctx.stroke();
    }

    ctx.restore();
  }
}

export function findAirspaceAtPoint(features, lon, lat) {
  for (let i = features.length - 1; i >= 0; i--) {
    if (pointInFeature(lon, lat, features[i])) return features[i];
  }
  return null;
}
