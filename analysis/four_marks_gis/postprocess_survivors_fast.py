#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

import analysis.four_marks_gis.postprocess_survivors as review

# Keep this independent from the slower, more comprehensive review.
review.OUTPUT = Path("analysis/four_marks_gis/survivor_review_fast")
review.OUTPUT.mkdir(parents=True, exist_ok=True)
(review.OUTPUT / "imagery").mkdir(exist_ok=True)

# Three most decision-relevant official layers. Any timeout is reported, never treated as no designation.
review.ARCGIS_LAYERS = {
    "sssi": "https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/SSSI_England/FeatureServer/0/query",
    "national_landscape": "https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/Areas_of_Outstanding_Natural_Beauty_England/FeatureServer/0/query",
    "scheduled_monument": "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/ArcGIS/rest/services/National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer/6/query",
}


def quick_reverse(lat: float, lon: float) -> dict[str, Any]:
    try:
        response = review.SESSION.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 16, "addressdetails": 1},
            timeout=15,
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


def quick_overpass(lat: float, lon: float) -> dict[str, Any]:
    query = f'''[out:json][timeout:25];(
      nwr["natural"="wood"](around:1600,{lat},{lon});
      nwr["landuse"~"forest|quarry|residential|industrial"](around:1600,{lat},{lon});
      way["building"](around:800,{lat},{lon});
      way["power"~"line|minor_line"](around:1600,{lat},{lon});
      node["power"="tower"](around:1600,{lat},{lon});
      way["highway"~"motorway|trunk|primary|secondary"](around:1600,{lat},{lon});
      way["railway"](around:1600,{lat},{lon});
      nwr["leisure"="nature_reserve"](around:1600,{lat},{lon});
      nwr["boundary"="protected_area"](around:1600,{lat},{lon});
    );out center tags;'''
    for endpoint in ("https://overpass.kumi.systems/api/interpreter", "https://overpass-api.de/api/interpreter"):
        try:
            response = review.SESSION.get(endpoint, params={"data": query}, timeout=35)
            response.raise_for_status()
            elements = response.json().get("elements", [])
            counts: dict[str, int] = {}
            names: dict[str, list[str]] = {}
            for element in elements:
                tags = element.get("tags", {})
                category = None
                if tags.get("natural") == "wood" or tags.get("landuse") == "forest": category = "woodland"
                elif tags.get("landuse") == "quarry": category = "quarry"
                elif tags.get("landuse") in {"residential", "industrial"}: category = tags["landuse"]
                elif "building" in tags: category = "building"
                elif tags.get("power") in {"line", "minor_line", "tower"}: category = "power"
                elif tags.get("highway") in {"motorway", "trunk", "primary", "secondary"}: category = "major_road"
                elif "railway" in tags: category = "railway"
                elif tags.get("leisure") == "nature_reserve" or tags.get("boundary") == "protected_area": category = "mapped_protected"
                if category:
                    counts[category] = counts.get(category, 0) + 1
                    value = tags.get("name") or tags.get("ref")
                    if value:
                        names.setdefault(category, [])
                        if value not in names[category] and len(names[category]) < 6: names[category].append(value)
            return {"endpoint": endpoint, "counts": counts, "named_features": names, "elements_returned": len(elements)}
        except Exception as exc:
            last_error = repr(exc)
    return {"error": last_error}


def quick_arcgis(url: str, geom_wgs) -> dict[str, Any]:
    minx, miny, maxx, maxy = geom_wgs.bounds
    try:
        response = review.SESSION.get(
            url,
            params={
                "f": "json",
                "where": "1=1",
                "geometry": f"{minx},{miny},{maxx},{maxy}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "*",
                "returnGeometry": "false",
                "resultRecordCount": 20,
            },
            timeout=18,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload: return {"error": payload["error"]}
        records = []
        for feature in payload.get("features", []):
            attrs = feature.get("attributes", {})
            chosen = {key: value for key, value in attrs.items() if value not in (None, "") and any(token in key.lower() for token in ("name", "title", "ref", "site", "list"))}
            records.append(chosen or attrs)
        return {"count": len(records), "records": records}
    except Exception as exc:
        return {"error": repr(exc)}


review.reverse_geocode = quick_reverse
review.overpass_context = quick_overpass
review.arcgis_context = quick_arcgis
review.main()
