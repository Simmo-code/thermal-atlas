#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures as cf
import csv
import json
import math
import os
import shutil
from dataclasses import fields
from pathlib import Path

import numpy as np

import analysis.four_marks_gis.run_analysis as r


OUT = Path(os.environ.get("GIS_OUTPUT", "analysis/four_marks_gis/output_v3"))
CACHE = Path(os.environ.get("GIS_CACHE", "/tmp/four_marks_exact_cache"))
CHECKPOINT = Path(
    os.environ.get(
        "GIS_CHECKPOINT",
        "analysis/four_marks_gis/v2_coarse_checkpoint/preliminary_components.csv",
    )
)


def make_json_safe(face: r.Face) -> r.Face:
    """Convert NumPy scalar values left by raster calculations to Python scalars."""
    for item in fields(face):
        value = getattr(face, item.name)
        if isinstance(value, np.generic):
            setattr(face, item.name, value.item())
    return face


def read_checkpoint() -> list[dict[str, float | str]]:
    with CHECKPOINT.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    parsed: list[dict[str, float | str]] = []
    for row in rows:
        parsed.append(
            {
                "easting": float(row["easting"]),
                "northing": float(row["northing"]),
                "coarse_local_slope": float(row["coarse_local_slope"]),
                "coarse_relief_m": float(row["coarse_relief_m"]),
                "tile": row.get("tile", ""),
            }
        )
    return parsed


def main() -> None:
    r.OUT = OUT
    r.CACHE = CACHE
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "profiles").mkdir(exist_ok=True)

    r.log("Benchmarking Whitewool from original one-metre DTM")
    benchmark, _, _, _ = r.benchmark_whitewool()

    prelim = read_checkpoint()
    r.log(f"Loaded {len(prelim)} sustained-profile candidates from the completed 10 m checkpoint")

    jobs: list[tuple[str, float, float, str]] = []
    for row in prelim:
        easting = float(row["easting"])
        northing = float(row["northing"])
        jobs.append(
            (
                r.nearest_label(easting, northing),
                easting,
                northing,
                "Coarse-screen discovery",
            )
        )

    for name, (latitude, longitude) in r.FORCED_WGS.items():
        easting, northing = r.TO_BNG.transform(longitude, latitude)
        jobs.append((name, easting, northing, "Required reassessment"))

    faces: list[r.Face] = []
    failures: list[dict[str, str]] = []
    with cf.ThreadPoolExecutor(max_workers=6) as executor:
        future_map = {
            executor.submit(
                r.exact_assess,
                name,
                easting,
                northing,
                benchmark,
                source,
            ): (name, easting, northing, source)
            for name, easting, northing, source in jobs
        }
        for index, future in enumerate(cf.as_completed(future_map), 1):
            name, easting, northing, source = future_map[future]
            try:
                faces.append(make_json_safe(future.result()))
            except Exception as exc:  # preserve every failed window explicitly
                failures.append(
                    {
                        "name": name,
                        "source": source,
                        "easting": str(easting),
                        "northing": str(northing),
                        "error": repr(exc),
                    }
                )
                r.log(f"Exact verification failed for {name}: {exc!r}")
            if index % 5 == 0 or index == len(future_map):
                r.log(f"One-metre verification {index}/{len(future_map)}")

    # Remove duplicated discovery windows while retaining all specifically requested reassessments.
    final: list[r.Face] = []
    for face in sorted(
        faces,
        key=lambda value: (
            value.source != "Required reassessment",
            value.terrain_score,
        ),
        reverse=True,
    ):
        if face.source != "Required reassessment" and any(
            existing.source != "Required reassessment"
            and math.hypot(
                face.easting - existing.easting,
                face.northing - existing.northing,
            )
            < 400
            for existing in final
        ):
            continue
        final.append(face)

    # Run OSM/aerodrome proximity checks only for terrain survivors. Failed terrain does not
    # need repeated network checks and remains clearly labelled as terrain-derived only.
    survivors = [face for face in final if face.pass_terrain]
    for index, face in enumerate(survivors, 1):
        r.osm_check(face)
        make_json_safe(face)
        r.log(f"Obstacle/aviation proximity screen {index}/{len(survivors)}: {face.name}")

    coarse_summary_path = Path(
        "analysis/four_marks_gis/v2_coarse_checkpoint/coarse_summary.json"
    )
    coarse_summary = json.loads(coarse_summary_path.read_text(encoding="utf-8"))
    stats = {
        "search_centre_bng": [float(r.FOUR_E), float(r.FOUR_N)],
        "search_radius_m": float(r.RADIUS_M),
        "search_area_sq_km": float(math.pi * r.RADIUS_M**2 / 1e6),
        "coarse_resolution_m": 10,
        "coarse_tile_count": int(coarse_summary["coarse_tiles"]),
        "raw_sustained_components": int(coarse_summary["raw_sustained_components"]),
        "preliminary_terrain_areas_after_dedup": int(
            coarse_summary["deduplicated_components"]
        ),
        "coarse_candidates_sent_to_one_metre": len(prelim),
        "required_named_locations_verified": len(r.FORCED_WGS),
        "one_metre_jobs_attempted": len(jobs),
        "one_metre_jobs_succeeded": len(faces),
        "one_metre_jobs_failed": len(failures),
        "deduplicated_one_metre_results": len(final),
        "failed_verification_windows": failures,
    }

    r.write_outputs(benchmark, final, stats)
    shutil.copy2(__file__, OUT / "run_exact_checkpoint.py")
    shutil.copy2(
        "analysis/four_marks_gis/run_analysis.py",
        OUT / "run_analysis.py",
    )
    (OUT / "verification_failures.json").write_text(
        json.dumps(failures, indent=2), encoding="utf-8"
    )
    r.log(f"COMPLETE {OUT}")


if __name__ == "__main__":
    main()
