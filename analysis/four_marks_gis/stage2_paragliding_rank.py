#!/usr/bin/env python3
from __future__ import annotations
import json, math
from pathlib import Path

import numpy as np
import pandas as pd
import folium
from folium.plugins import Fullscreen, MeasureControl

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'output_revised' / 'all_measured_candidates.csv'
BENCH = ROOT / 'output_revised' / 'whitewool_benchmark.json'
OUT = ROOT / 'output_stage2'
OUT.mkdir(parents=True, exist_ok=True)

# Search intent: usable inland ridge-soaring terrain, with preference for broad
# SE-S-SW faces. Scores are terrain-only; access, ownership, surface, obstacles,
# protected land and aviation remain manual checks for the final shortlist.
TARGET_ASPECT = 180.0


def clip01(x):
    return max(0.0, min(1.0, float(x)))


def ramp(v, lo, hi):
    if not np.isfinite(v): return 0.0
    if hi <= lo: return 1.0 if v >= hi else 0.0
    return clip01((v-lo)/(hi-lo))


def ideal_band(v, lo, sweet_lo, sweet_hi, hi):
    if not np.isfinite(v): return 0.0
    if v < lo or v > hi: return 0.0
    if sweet_lo <= v <= sweet_hi: return 1.0
    if v < sweet_lo: return ramp(v, lo, sweet_lo)
    return ramp(hi-v, 0, hi-sweet_hi)


def aspect_diff(a, b=TARGET_ASPECT):
    return abs((float(a)-b+180.0)%360.0-180.0)


def compass16(d):
    names=['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
    return names[int(((float(d)%360)+11.25)//22.5)%16]


def score_row(r, white):
    slope=float(r.get('representative_slope_deg', np.nan))
    relief=float(r.get('vertical_relief_m', np.nan))
    ridge8=float(r.get('ridge_8deg_m', np.nan))
    ridge95=float(r.get('ridge_9_5deg_m', np.nan))
    width=float(r.get('ridge_length_m', np.nan))
    pct8=float(r.get('percent_face_8deg', np.nan))
    pct95=float(r.get('percent_face_9_5deg', np.nan))
    area=float(r.get('connected_area_ha', np.nan))
    rough=float(r.get('roughness_m', np.nan))
    gaps=float(r.get('gaps_count', 0) or 0)
    lgap=float(r.get('largest_gap_m', 0) or 0)
    lip=float(r.get('lip_sharpness_deg', np.nan))
    aspect=float(r.get('aspect_deg', np.nan))
    down=float(r.get('downslope_span_m', np.nan))

    # Core flying-face geometry.
    slope_s = ideal_band(slope, 6.0, 10.0, 22.0, 32.0)
    relief_s = ramp(relief, 20, 110)
    ridge_s = ramp(max(ridge8, width if np.isfinite(width) else 0), 220, 1000)
    continuity_s = 0.65*ramp(pct8, 18, 65) + 0.35*ramp(pct95, 8, 45)

    # Broad exposure proxy from terrain already measured. This is deliberately
    # conservative: Stage 2 does not claim obstacle/airflow clearance without
    # a dedicated upwind raster sweep.
    exposure_s = 0.55*ramp(down, 120, 450) + 0.45*ramp(relief, 25, 100)

    # Launch/crest proxy: reward moderate lips and consistent terrain, penalise
    # rough/noisy faces and large breaks. Final launch inspection is still manual.
    lip_s = ideal_band(lip, -8, -1, 8, 18) if np.isfinite(lip) else 0.5
    rough_s = 1.0-ramp(rough, 3.0, 12.0) if np.isfinite(rough) else 0.5
    gap_s = max(0.0, 1.0 - min(1.0, gaps/5.0)*0.45 - min(1.0, lgap/180.0)*0.55)
    launch_proxy = 0.35*lip_s + 0.35*rough_s + 0.30*gap_s

    area_s = ramp(area, 1.0, 8.0)
    aspect_s = max(0.0, 1.0-aspect_diff(aspect)/55.0) if np.isfinite(aspect) else 0.0

    # Whitewool similarity: use the same exact-verification metrics when available.
    sim_parts=[]
    for key, scale in [
        ('representative_slope_deg', 8.0), ('vertical_relief_m', 55.0),
        ('ridge_length_m', 650.0), ('percent_face_8deg', 45.0),
        ('connected_area_ha', 5.0), ('lip_sharpness_deg', 10.0)]:
        a=float(r.get(key, np.nan)); b=float(white.get(key, np.nan))
        if np.isfinite(a) and np.isfinite(b): sim_parts.append(max(0.0,1.0-abs(a-b)/scale))
    white_sim = float(np.mean(sim_parts)) if sim_parts else 0.0

    # Paragliding Suitability Score, terrain-only.
    total = 100.0*(
        0.20*slope_s +
        0.15*relief_s +
        0.15*ridge_s +
        0.15*exposure_s +
        0.10*continuity_s +
        0.10*launch_proxy +
        0.05*area_s +
        0.05*aspect_s +
        0.05*white_sim
    )

    # Hard ideal geometry. These are intentionally demanding, but the output
    # always fills to 100 with the best near-matches if fewer than 100 qualify.
    ideal = (
        slope >= 9.5 and relief >= 35 and
        max(ridge8, width if np.isfinite(width) else 0) >= 400 and
        pct8 >= 30 and aspect_diff(aspect) <= 55 and gap_s >= 0.45
    )
    strong = (
        slope >= 8.0 and relief >= 28 and
        max(ridge8, width if np.isfinite(width) else 0) >= 300 and
        pct8 >= 22 and aspect_diff(aspect) <= 67.5
    )
    good = (
        slope >= 6.5 and relief >= 22 and
        max(ridge8, width if np.isfinite(width) else 0) >= 240 and
        pct8 >= 15
    )
    tier = 'Ideal' if ideal else 'Strong near-match' if strong else 'Good near-match' if good else 'Best available fallback'
    return pd.Series({
        'paragliding_score':total,'ideal_match':ideal,'selection_tier':tier,
        'slope_score':100*slope_s,'relief_score':100*relief_s,'ridge_score':100*ridge_s,
        'exposure_proxy_score':100*exposure_s,'continuity_score':100*continuity_s,
        'launch_proxy_score':100*launch_proxy,'aspect_score':100*aspect_s,
        'whitewool_similarity_pct':100*white_sim,'facing':compass16(aspect),
        'aspect_error_from_south_deg':aspect_diff(aspect)
    })


def deduplicate(df, distance_m=600.0, aspect_tol=30.0):
    # Greedy best-first clustering: nearby candidates on the same face become one hill.
    keep=[]
    for idx,row in df.iterrows():
        e=float(row.easting); n=float(row.northing); a=float(row.aspect_deg)
        duplicate=False
        for k in keep:
            q=df.loc[k]
            if math.hypot(e-float(q.easting), n-float(q.northing)) < distance_m:
                da=abs((a-float(q.aspect_deg)+180)%360-180)
                if da <= aspect_tol:
                    duplicate=True; break
        if not duplicate: keep.append(idx)
    return df.loc[keep].copy()


def make_map(top):
    m=folium.Map(location=[top.latitude.median(),top.longitude.median()],zoom_start=9,tiles=None,control_scale=True)
    folium.TileLayer('OpenStreetMap',name='OpenStreetMap',show=True).add_to(m)
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery',name='Satellite',show=False).add_to(m)
    folium.TileLayer(
        tiles='https://snapshots.openflightmaps.org/live/2608/tiles/world/noninteractive/epsg3857/aero/512/latest/{z}/{x}/{y}.png',
        attr='OpenFlightMaps — verify against current UK AIP and NOTAMs',
        name='Airspace overlay (AIRAC 2608)',overlay=True,control=True,show=False,
        opacity=.72,tile_size=512,zoom_offset=-1,max_native_zoom=11,max_zoom=18).add_to(m)

    groups={}
    for tier in ['Ideal','Strong near-match','Good near-match','Best available fallback']:
        c=int((top.selection_tier==tier).sum())
        groups[tier]=folium.FeatureGroup(name=f'{tier} ({c})',show=True).add_to(m)

    marker_meta=[]
    for _,r in top.iterrows():
        rank=int(r.rank);lat=float(r.latitude);lon=float(r.longitude)
        earth=f'https://earth.google.com/web/@{lat:.7f},{lon:.7f},500a,1200d,35y,0h,0t,0r'
        popup=f'''<div style="font-family:Arial;min-width:280px"><h4 style="margin:0 0 7px">#{rank} — {r.selection_tier}</h4>
        <b>{r['name']}</b><br><b>Score:</b> {r.paragliding_score:.1f}/100<br><b>Facing:</b> {r.facing} ({r.aspect_deg:.0f}°)<br>
        <b>Sustained slope:</b> {r.representative_slope_deg:.1f}°<br><b>Relief:</b> {r.vertical_relief_m:.0f} m / {r.vertical_relief_ft:.0f} ft<br>
        <b>Ridge ≥8°:</b> {r.ridge_8deg_m:.0f} m<br><b>Face ≥8°:</b> {r.percent_face_8deg:.0f}%<br>
        <b>Whitewool similarity:</b> {r.whitewool_similarity_pct:.0f}%<br><b>Grid:</b> {r.grid_ref}<br><br>
        <a href="{earth}" target="_blank">Open in Google Earth</a><br><small>Terrain-only ranking; manually verify airspace, obstacles, surface, access, ownership and landing.</small></div>'''
        color={'Ideal':'green','Strong near-match':'blue','Good near-match':'orange','Best available fallback':'red'}[r.selection_tier]
        mk=folium.Marker([lat,lon],tooltip=f'#{rank} {r.facing} score {r.paragliding_score:.1f}',popup=folium.Popup(popup,max_width=400),
            icon=folium.DivIcon(html=f'<div style="width:34px;height:34px;border-radius:50%;background:{color};color:white;border:2px solid white;display:flex;align-items:center;justify-content:center;font:bold 11px Arial">{rank}</div>',icon_size=(34,34),icon_anchor=(17,17)))
        mk.add_to(groups[r.selection_tier]);marker_meta.append((mk.get_name(),rank))

    folium.LayerControl(position='topright',collapsed=False).add_to(m);Fullscreen(position='topleft').add_to(m);MeasureControl(position='topleft',primary_length_unit='miles').add_to(m)
    m.fit_bounds([[top.latitude.min(),top.longitude.min()],[top.latitude.max(),top.longitude.max()]],padding=(20,20))

    opts=''.join(f'<option value="{a}-{min(a+24,len(top))}">Ranks {a}–{min(a+24,len(top))}</option>' for a in range(1,len(top)+1,25))
    m.get_root().html.add_child(folium.Element(f'''<div id="batch" style="position:fixed;left:12px;top:60px;z-index:9999;background:white;border:1px solid #555;border-radius:6px;padding:8px;font:13px Arial"><b>Show ranked batch</b><br><select id="batchsel" style="margin-top:4px">{opts}</select></div>'''))
    js='['+','.join(f'{{m:{v},r:{rank}}}' for v,rank in marker_meta)+']'
    mapname=m.get_name()
    m.get_root().html.add_child(folium.Element(f'''<script>document.addEventListener('DOMContentLoaded',function(){{const mp={mapname},sites={js},sel=document.getElementById('batchsel');function f(){{const p=sel.value.split('-').map(Number);sites.forEach(s=>{{const on=s.r>=p[0]&&s.r<=p[1],has=mp.hasLayer(s.m);if(on&&!has)s.m.addTo(mp);if(!on&&has)mp.removeLayer(s.m);}});}}sel.addEventListener('change',f);f();}});</script>'''))
    m.save(OUT/'top100_paragliding_map.html')


def main():
    df=pd.read_csv(SRC)
    df=df[np.isfinite(pd.to_numeric(df.latitude,errors='coerce')) & np.isfinite(pd.to_numeric(df.longitude,errors='coerce'))].copy()
    white=json.loads(BENCH.read_text()) if BENCH.exists() else {}
    scored=pd.concat([df,df.apply(lambda r:score_row(r,white),axis=1)],axis=1)
    scored=scored.sort_values(['paragliding_score','representative_slope_deg','vertical_relief_m'],ascending=False,kind='mergesort')
    unique=deduplicate(scored,600,30)

    # Progressive selection: Ideal first; if <100, Strong; then Good; then best remaining.
    selected=[]
    for tier in ['Ideal','Strong near-match','Good near-match','Best available fallback']:
        for idx in unique.index[unique.selection_tier==tier]:
            if idx not in selected:selected.append(idx)
            if len(selected)>=100:break
        if len(selected)>=100:break
    top=unique.loc[selected[:100]].copy().reset_index(drop=True)
    top['rank']=np.arange(1,len(top)+1)

    cols=['rank','selection_tier','ideal_match','paragliding_score','name','grid_ref','facing','aspect_deg','distance_miles',
          'representative_slope_deg','vertical_relief_m','vertical_relief_ft','ridge_length_m','ridge_8deg_m','ridge_9_5deg_m',
          'percent_face_8deg','percent_face_9_5deg','connected_area_ha','downslope_span_m','roughness_m','gaps_count','largest_gap_m',
          'slope_score','relief_score','ridge_score','exposure_proxy_score','continuity_score','launch_proxy_score','aspect_score','whitewool_similarity_pct',
          'latitude','longitude','easting','northing','category','status']
    top[cols].to_csv(OUT/'top100_paragliding_sites.csv',index=False)
    unique.to_csv(OUT/'all_stage2_ranked_candidates.csv',index=False)
    geo={'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[float(r.longitude),float(r.latitude)]},'properties':{k:(v.item() if isinstance(v,np.generic) else v) for k,v in r[cols[:-4]].to_dict().items()}} for _,r in top.iterrows()]}
    (OUT/'top100_paragliding_sites.geojson').write_text(json.dumps(geo,indent=2,default=str))
    make_map(top)

    summary={
        'source_candidates':int(len(df)),'unique_hills_after_600m_same-face_dedup':int(len(unique)),
        'ideal_matches_available':int((unique.selection_tier=='Ideal').sum()),
        'strong_near_matches_available':int((unique.selection_tier=='Strong near-match').sum()),
        'good_near_matches_available':int((unique.selection_tier=='Good near-match').sum()),
        'top100_returned':int(len(top)),
        'top100_tier_counts':top.selection_tier.value_counts().to_dict(),
        'method':'Terrain-only Stage 2 paragliding suitability score. Ideal sites are selected first; thresholds are progressively relaxed until 100 unique hills are returned. Nearby candidates within 600 m and 30 degrees aspect are treated as the same hill.',
        'manual_checks_required':['current airspace/AIP/NOTAMs','surface/land cover','trees and obstacles','power lines','roads/railways','launch access','ownership/permission','landing fields','protected land','site-specific rotor/turbulence']
    }
    (OUT/'stage2_summary.json').write_text(json.dumps(summary,indent=2))
    (OUT/'README.md').write_text('# Four Marks Stage 2 paragliding suitability search\n\n'+json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
