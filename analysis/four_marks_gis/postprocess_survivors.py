#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

import folium
import requests
from folium.plugins import Fullscreen, MeasureControl
from pyproj import Transformer
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path("analysis/four_marks_gis")
INPUT = ROOT / "output_v3" / "candidates.geojson"
OUTPUT = ROOT / "survivor_review"
OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / "imagery").mkdir(exist_ok=True)

TO_BNG = Transformer.from_crs(4326, 27700, always_xy=True)
TO_WGS = Transformer.from_crs(27700, 4326, always_xy=True)
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "FourMarksParaglidingTerrainReview/1.0 contact-via-github",
        "Accept": "application/json,text/plain,*/*",
    }
)

EXISTING_SITES = {
    "Park Hill": (50.998, -1.026),
    "Whitewool": (50.979, -1.076),
    "Butser West": (50.983, -0.984),
    "Butser North/NE": (50.973, -0.978),
    "Butser South": (50.977, -0.987),
    "Harting": (50.959, -0.870),
    "Mercury": (50.974, -1.038),
    "Chalton": (50.930, -0.954),
    "Matterley Bowl": (51.048, -1.248),
    "Meon Shore": (50.821, -1.253),
    "Oxenbourne": (50.972, -0.992),
}

AERODROMES = {
    "Lasham Gliding Centre": (51.1867, -1.0335),
    "Popham Airfield": (51.1939, -1.2347),
    "Southampton Airport": (50.9503, -1.3568),
    "Solent Airport": (50.8153, -1.2096),
    "Farnborough Airport": (51.2758, -0.7763),
    "Fairoaks Airport": (51.3480, -0.5589),
    "Redhill Aerodrome": (51.2136, -0.1386),
    "London Gatwick": (51.1481, -0.1903),
}

ARCGIS_LAYERS = {
    "sssi": "https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/SSSI_England/FeatureServer/0/query",
    "nnr": "https://services-eu1.arcgis.com/SuC1rPA4UP1jdgwy/arcgis/rest/services/National_Nature_Reserves_England/FeatureServer/0/query",
    "national_park": "https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/National_Parks_England/FeatureServer/0/query",
    "national_landscape": "https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/Areas_of_Outstanding_Natural_Beauty_England/FeatureServer/0/query",
    "scheduled_monument": "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/ArcGIS/rest/services/National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer/6/query",
}


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    e1, n1 = TO_BNG.transform(lon1, lat1)
    e2, n2 = TO_BNG.transform(lon2, lat2)
    return math.hypot(e1 - e2, n1 - n2)


def reverse_geocode(lat: float, lon: float) -> dict[str, Any]:
    try:
        response = SESSION.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "format": "jsonv2",
                "lat": lat,
                "lon": lon,
                "zoom": 16,
                "addressdetails": 1,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "display_name": data.get("display_name", ""),
            "name": data.get("name", ""),
            "type": data.get("type", ""),
            "address": data.get("address", {}),
        }
    except Exception as exc:
        return {"error": repr(exc)}


def overpass_context(lat: float, lon: float) -> dict[str, Any]:
    query = f"""[out:json][timeout:120];(
      nwr[\"natural\"=\"wood\"](around:1800,{lat},{lon});
      nwr[\"landuse\"~\"forest|quarry|residential|industrial\"](around:1800,{lat},{lon});
      nwr[\"natural\"=\"scrub\"](around:1200,{lat},{lon});
      way[\"building\"](around:900,{lat},{lon});
      way[\"power\"~\"line|minor_line\"](around:1800,{lat},{lon});
      node[\"power\"=\"tower\"](around:1800,{lat},{lon});
      way[\"highway\"~\"motorway|trunk|primary|secondary\"](around:1800,{lat},{lon});
      way[\"railway\"](around:1800,{lat},{lon});
      nwr[\"leisure\"=\"nature_reserve\"](around:1800,{lat},{lon});
      nwr[\"boundary\"=\"protected_area\"](around:1800,{lat},{lon});
      nwr[\"aeroway\"](around:3000,{lat},{lon});
    );out center tags;"""
    endpoints = [
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass-api.de/api/interpreter",
    ]
    last_error = None
    for endpoint in endpoints:
        try:
            response = SESSION.get(endpoint, params={"data": query}, timeout=180)
            response.raise_for_status()
            elements = response.json().get("elements", [])
            counts = Counter()
            named: dict[str, list[str]] = {}
            for element in elements:
                tags = element.get("tags", {})
                category = None
                if tags.get("natural") == "wood" or tags.get("landuse") == "forest":
                    category = "woodland"
                elif tags.get("landuse") == "quarry":
                    category = "quarry"
                elif tags.get("landuse") in {"residential", "industrial"}:
                    category = tags.get("landuse")
                elif tags.get("natural") == "scrub":
                    category = "scrub"
                elif "building" in tags:
                    category = "building"
                elif tags.get("power") in {"line", "minor_line", "tower"}:
                    category = "power"
                elif tags.get("highway") in {"motorway", "trunk", "primary", "secondary"}:
                    category = "major_road"
                elif "railway" in tags:
                    category = "railway"
                elif tags.get("leisure") == "nature_reserve" or tags.get("boundary") == "protected_area":
                    category = "mapped_protected"
                elif "aeroway" in tags:
                    category = "aeroway"
                if category:
                    counts[category] += 1
                    name = tags.get("name") or tags.get("ref")
                    if name:
                        named.setdefault(category, [])
                        if name not in named[category] and len(named[category]) < 8:
                            named[category].append(name)
            return {
                "endpoint": endpoint,
                "counts": dict(counts),
                "named_features": named,
                "elements_returned": len(elements),
            }
        except Exception as exc:
            last_error = repr(exc)
    return {"error": last_error}


def arcgis_context(url: str, geom_wgs) -> dict[str, Any]:
    minx, miny, maxx, maxy = geom_wgs.bounds
    params = {
        "f": "json",
        "where": "1=1",
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
        "resultRecordCount": 25,
    }
    try:
        response = SESSION.get(url, params=params, timeout=90)
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            return {"error": payload["error"]}
        records = []
        for feature in payload.get("features", []):
            attrs = feature.get("attributes", {})
            selected = {}
            for key, value in attrs.items():
                low = key.lower()
                if any(token in low for token in ("name", "title", "ref", "list", "park", "sssi", "site")):
                    if value not in (None, ""):
                        selected[key] = value
            records.append(selected or attrs)
        return {"count": len(records), "records": records}
    except Exception as exc:
        return {"error": repr(exc)}


def export_imagery(cluster_id: int, geom_wgs) -> str:
    minx, miny, maxx, maxy = geom_wgs.bounds
    dx = max(0.012, (maxx - minx) * 0.25)
    dy = max(0.008, (maxy - miny) * 0.25)
    bbox = f"{minx-dx},{miny-dy},{maxx+dx},{maxy+dy}"
    path = OUTPUT / "imagery" / f"cluster_{cluster_id:02d}_satellite.png"
    try:
        response = SESSION.get(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export",
            params={
                "bbox": bbox,
                "bboxSR": 4326,
                "imageSR": 4326,
                "size": "1400,1000",
                "format": "png32",
                "transparent": "false",
                "f": "image",
            },
            timeout=180,
        )
        response.raise_for_status()
        path.write_bytes(response.content)
        return str(path.relative_to(ROOT))
    except Exception as exc:
        return f"ERROR: {exc!r}"


def cluster_passes(features: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    remaining = features[:]
    clusters: list[list[dict[str, Any]]] = []
    while remaining:
        seed = remaining.pop(0)
        group = [seed]
        changed = True
        while changed:
            changed = False
            group_union = unary_union([item["geom_bng"] for item in group])
            for candidate in remaining[:]:
                # Overlapping verification polygons are one terrain face. A short gap below
                # 150 m is also treated as one practical ridge section.
                if group_union.intersects(candidate["geom_bng"]) or group_union.distance(candidate["geom_bng"]) < 150:
                    group.append(candidate)
                    remaining.remove(candidate)
                    changed = True
        clusters.append(group)
    return clusters


def safe_filename(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def main() -> None:
    collection = json.loads(INPUT.read_text(encoding="utf-8"))
    passed = []
    failed_named = []
    for feature in collection["features"]:
        props = feature["properties"]
        if props.get("pass_terrain"):
            geom_wgs = shape(feature["geometry"])
            geom_bng = shp_transform(lambda x, y, z=None: TO_BNG.transform(x, y), geom_wgs)
            passed.append({"feature": feature, "geom_wgs": geom_wgs, "geom_bng": geom_bng})
        elif props.get("source") == "Required reassessment":
            failed_named.append(feature)

    clusters = cluster_passes(passed)
    results = []
    for cluster_id, group in enumerate(clusters, 1):
        union_bng = unary_union([item["geom_bng"] for item in group])
        union_wgs = shp_transform(lambda x, y, z=None: TO_WGS.transform(x, y), union_bng)
        centroid = union_wgs.representative_point()
        lon, lat = centroid.x, centroid.y
        member_props = [item["feature"]["properties"] for item in group]
        best = max(member_props, key=lambda p: (p.get("terrain_score", 0), p.get("representative_slope_deg", 0)))
        nearby_sites = []
        for name, (slat, slon) in EXISTING_SITES.items():
            distance = distance_m(lat, lon, slat, slon)
            if distance < 8000:
                nearby_sites.append({"name": name, "distance_m": distance, "distance_miles": distance / 1609.344})
        nearby_sites.sort(key=lambda item: item["distance_m"])
        aerodromes = []
        for name, (alat, alon) in AERODROMES.items():
            distance = distance_m(lat, lon, alat, alon)
            aerodromes.append({"name": name, "distance_miles": distance / 1609.344})
        aerodromes.sort(key=lambda item: item["distance_miles"])

        reverse = reverse_geocode(lat, lon)
        time.sleep(1.1)
        overpass = overpass_context(lat, lon)
        protected = {key: arcgis_context(url, union_wgs) for key, url in ARCGIS_LAYERS.items()}
        imagery = export_imagery(cluster_id, union_wgs)
        name_hint = reverse.get("name") or reverse.get("address", {}).get("hamlet") or reverse.get("address", {}).get("village") or best["name"]
        existing_conflict = nearby_sites[0] if nearby_sites and nearby_sites[0]["distance_m"] < 1600 else None
        results.append(
            {
                "cluster_id": cluster_id,
                "working_name": f"{name_hint} south-facing ridge",
                "member_count": len(group),
                "member_names": [p["name"] for p in member_props],
                "representative_latitude": lat,
                "representative_longitude": lon,
                "best_terrain_record": best,
                "combined_area_ha": union_bng.area / 10000,
                "geometry": mapping(union_wgs),
                "reverse_geocode": reverse,
                "osm_context": overpass,
                "official_designations": protected,
                "nearby_existing_sites": nearby_sites,
                "existing_site_conflict": existing_conflict,
                "nearest_aerodromes": aerodromes[:4],
                "satellite_image": imagery,
            }
        )

    (OUTPUT / "survivor_context.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": result["geometry"],
                "properties": {
                    "cluster_id": result["cluster_id"],
                    "working_name": result["working_name"],
                    "member_count": result["member_count"],
                    "member_names": result["member_names"],
                    "terrain_score": result["best_terrain_record"]["terrain_score"],
                    "representative_slope_deg": result["best_terrain_record"]["representative_slope_deg"],
                    "vertical_relief_m": result["best_terrain_record"]["vertical_relief_m"],
                    "ridge_length_m": result["best_terrain_record"]["ridge_length_m"],
                    "aspect_deg": result["best_terrain_record"]["aspect_deg"],
                    "existing_site_conflict": result["existing_site_conflict"],
                },
            }
            for result in results
        ],
    }
    (OUTPUT / "clustered_survivors.geojson").write_text(json.dumps(geojson, indent=2), encoding="utf-8")

    lines = [
        "# Terrain survivors - context review",
        "",
        f"Six raw terrain passes collapsed into **{len(results)} distinct ridge clusters** after polygon overlap and a 150 m face-gap test.",
        "",
    ]
    for result in results:
        best = result["best_terrain_record"]
        counts = result["osm_context"].get("counts", {})
        designations = []
        for key, value in result["official_designations"].items():
            if value.get("count", 0):
                designations.append(f"{key}: {value['count']}")
            elif "error" in value:
                designations.append(f"{key}: query error")
        lines.extend(
            [
                f"## Cluster {result['cluster_id']}: {result['working_name']}",
                f"Members: {', '.join(result['member_names'])}.",
                f"Representative point: {result['representative_latitude']:.6f}, {result['representative_longitude']:.6f}.",
                f"Terrain: {best['representative_slope_deg']:.1f}° representative slope; {best['vertical_relief_m']:.1f} m ({best['vertical_relief_ft']:.0f} ft) relief; {best['ridge_length_m']:.0f} m ridge; {best['percent_face_at_benchmark']:.0f}% of broader face at benchmark; aspect {best['aspect_text']} ({best['aspect_deg']:.0f}°).",
                f"Reverse geocode: {result['reverse_geocode'].get('display_name', result['reverse_geocode'])}.",
                f"OSM within review radius: {dict(counts)}.",
                f"Official designation intersections: {', '.join(designations) if designations else 'none returned'}.",
                f"Existing-site conflict: {result['existing_site_conflict'] or 'none within 1 km'}.",
                "Nearest aerodromes: " + ", ".join(f"{item['name']} {item['distance_miles']:.1f} mi" for item in result["nearest_aerodromes"]) + ".",
                f"Satellite review image: {result['satellite_image']}.",
                "",
            ]
        )
    (OUTPUT / "survivor_context.md").write_text("\n".join(lines), encoding="utf-8")

    # Reviewed map - original measured polygons, failed named locations and reference sites.
    map_obj = folium.Map([51.10735, -1.04945], zoom_start=10, tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(map_obj)
    folium.TileLayer(
        "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attr="OpenTopoMap / OpenStreetMap contributors",
        name="Topographic contours",
    ).add_to(map_obj)
    folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite imagery",
    ).add_to(map_obj)
    folium.Circle([51.10735, -1.04945], radius=30 * 1609.344, color="blue", fill=False, dash_array="8 6", tooltip="30-mile search radius").add_to(map_obj)

    terrain_layer = folium.FeatureGroup(name="Distinct terrain survivors", show=True).add_to(map_obj)
    duplicate_layer = folium.FeatureGroup(name="Raw overlapping passes", show=False).add_to(map_obj)
    failed_layer = folium.FeatureGroup(name="Failed named locations", show=False).add_to(map_obj)
    existing_layer = folium.FeatureGroup(name="Existing flying sites", show=True).add_to(map_obj)
    aviation_layer = folium.FeatureGroup(name="Aviation concerns", show=False).add_to(map_obj)
    protected_layer = folium.FeatureGroup(name="Protected or impractical land", show=False).add_to(map_obj)

    for result in results:
        best = result["best_terrain_record"]
        designation_text = "; ".join(
            f"{key}={value.get('count', 'error')}" for key, value in result["official_designations"].items()
        )
        popup = (
            f"<b>Cluster {result['cluster_id']}: {result['working_name']}</b><br>"
            f"Raw passes combined: {result['member_count']}<br>"
            f"Slope {best['representative_slope_deg']:.1f}°; relief {best['vertical_relief_m']:.0f} m / {best['vertical_relief_ft']:.0f} ft; ridge {best['ridge_length_m']:.0f} m; aspect {best['aspect_text']} {best['aspect_deg']:.0f}°<br>"
            f"Designations: {designation_text}<br>"
            f"Existing conflict: {result['existing_site_conflict'] or 'none within 1 km'}<br>"
            f"<a href='https://www.google.com/maps/search/?api=1&query={result['representative_latitude']},{result['representative_longitude']}' target='_blank'>Open aerial map</a>"
        )
        folium.GeoJson(
            {"type": "Feature", "geometry": result["geometry"], "properties": {}},
            tooltip=f"Cluster {result['cluster_id']}: {result['working_name']}",
            popup=folium.Popup(popup, max_width=500),
            style_function=lambda _: {"color": "red", "weight": 3, "fillOpacity": 0.18},
        ).add_to(terrain_layer)
        if any(value.get("count", 0) for value in result["official_designations"].values()):
            folium.Marker(
                [result["representative_latitude"], result["representative_longitude"]],
                tooltip=f"Cluster {result['cluster_id']}: protected-land review required",
                icon=folium.Icon(color="orange", icon="info-sign"),
            ).add_to(protected_layer)

    for item in passed:
        props = item["feature"]["properties"]
        folium.GeoJson(
            item["feature"],
            tooltip=props["name"],
            style_function=lambda _: {"color": "purple", "weight": 1, "fillOpacity": 0.05},
        ).add_to(duplicate_layer)

    for feature in failed_named:
        props = feature["properties"]
        geom = shape(feature["geometry"])
        point = geom.representative_point()
        folium.CircleMarker(
            [point.y, point.x],
            radius=4,
            color="gray",
            fill=True,
            tooltip=f"{props['name']}: failed terrain threshold",
            popup=props.get("reason", ""),
        ).add_to(failed_layer)

    for name, (lat, lon) in EXISTING_SITES.items():
        folium.Marker([lat, lon], tooltip=f"{name} - existing/reference site", icon=folium.Icon(color="green")).add_to(existing_layer)
    for name, (lat, lon) in AERODROMES.items():
        folium.Marker([lat, lon], tooltip=name, icon=folium.Icon(color="blue", icon="plane")).add_to(aviation_layer)

    Fullscreen().add_to(map_obj)
    MeasureControl().add_to(map_obj)
    folium.LayerControl(collapsed=False).add_to(map_obj)
    map_obj.save(OUTPUT / "interactive_map_reviewed.html")

    print(json.dumps({"raw_passes": len(passed), "distinct_clusters": len(results)}, indent=2))


if __name__ == "__main__":
    main()
