#!/usr/bin/env python3
"""Reverse-identify and visually context-check Whitewool LiDAR candidates."""
from __future__ import annotations
import io, json, math, time
from pathlib import Path

import pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFont

OUT = Path("whitewool_context_output")
OUT.mkdir(parents=True, exist_ok=True)
IMAGES = OUT / "satellite"
IMAGES.mkdir(exist_ok=True)

CANDIDATES = [
    (1, 51.034530844037604, -0.9517629745363576, 28.94462467703986, 1210.769000476629),
    (2, 51.02377066359864, -0.9673478099177493, 24.297978800266037, 1476.5041980672304),
    (3, 51.234095267312625, -0.39526780653953864, 23.068661166774547, 825.9122985829374),
    (4, 50.89278757195073, -0.8357673240885919, 21.21381491038791, 869.6806099057468),
    (5, 51.07727603931286, -0.9372648864643547, 21.38151704625569, 893.8172147318305),
    (6, 51.05511148170261, -0.6886045736855159, 21.082725146712093, 762.3361108776354),
    (7, 51.305587162471454, -1.5447689402476812, 20.26004005134563, 683.8957478091418),
    (8, 50.866785685899345, -0.5503076140634316, 22.408380639389424, 435.62731658041463),
    (9, 51.35058167844023, -1.4678167691499169, 20.082847027047364, 411.8033377500612),
    (10, 50.930870165090774, -0.629288058657211, 23.64794246334765, 332.5031931551276),
    (11, 51.00675579516298, -1.0066513373910888, 21.16864093456995, 412.6832371114984),
    (12, 50.91577854889782, -0.7227397498855824, 19.783827292441597, 425.5387240251969),
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Simmo-code-thermal-atlas-terrain-research/1.0 (GitHub analysis)"})

def reverse(lat, lon):
    url = "https://nominatim.openstreetmap.org/reverse"
    r = SESSION.get(url, params={"format":"jsonv2","lat":lat,"lon":lon,"zoom":16,"addressdetails":1}, timeout=60)
    r.raise_for_status()
    return r.json()

def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y

def satellite_mosaic(rank, lat, lon, z=15, radius_tiles=1):
    xf, yf = lonlat_to_tile(lon, lat, z)
    xc, yc = int(xf), int(yf)
    tile_size = 256
    side = 2 * radius_tiles + 1
    canvas = Image.new("RGB", (side*tile_size, side*tile_size), "white")
    for dy in range(-radius_tiles, radius_tiles+1):
        for dx in range(-radius_tiles, radius_tiles+1):
            x, y = xc+dx, yc+dy
            url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            rr = SESSION.get(url, timeout=60)
            rr.raise_for_status()
            tile = Image.open(io.BytesIO(rr.content)).convert("RGB")
            canvas.paste(tile, ((dx+radius_tiles)*tile_size, (dy+radius_tiles)*tile_size))
    px = (radius_tiles + (xf-xc))*tile_size
    py = (radius_tiles + (yf-yc))*tile_size
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((px-12,py-12,px+12,py+12), outline="red", width=5)
    draw.line((px-18,py,px+18,py), fill="red", width=3)
    draw.line((px,py-18,px,py+18), fill="red", width=3)
    draw.rectangle((0,0,220,30), fill=(255,255,255))
    draw.text((7,7), f"Candidate #{rank}  z{z}", fill="black")
    path = IMAGES / f"candidate_{rank:02d}.jpg"
    canvas.save(path, quality=92)
    return str(path)

def overpass_context():
    clauses=[]
    filters=[
        '["landuse"="quarry"]','["natural"="wood"]','["landuse"="forest"]',
        '["boundary"="protected_area"]','["leisure"="nature_reserve"]',
        '["power"="line"]','["power"="tower"]','["railway"="rail"]',
        '["highway"="motorway"]','["highway"="trunk"]','["highway"="primary"]',
        '["aeroway"="aerodrome"]','["place"="village"]','["place"="hamlet"]',
        '["place"="locality"]','["natural"="peak"]','["historic"]'
    ]
    for _,lat,lon,_,_ in CANDIDATES:
        for f in filters:
            clauses.append(f'nwr(around:1500,{lat},{lon}){f};')
    query='[out:json][timeout:180];('+''.join(clauses)+');out center tags;'
    r=SESSION.post('https://overpass-api.de/api/interpreter',data=query.encode(),timeout=240)
    r.raise_for_status()
    return r.json().get('elements',[])

def element_point(el):
    if 'lat' in el:return el['lat'],el['lon']
    c=el.get('center') or {}; return c.get('lat'),c.get('lon')

def haversine(lat1,lon1,lat2,lon2):
    r=6371000; p1=math.radians(lat1);p2=math.radians(lat2)
    dp=math.radians(lat2-lat1);dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))

def main():
    rows=[]
    for rank,lat,lon,angle,ridge in CANDIDATES:
        rev=reverse(lat,lon)
        addr=rev.get('address',{})
        img=satellite_mosaic(rank,lat,lon)
        rows.append({
            'rank':rank,'lat':lat,'lon':lon,'angle_deg':angle,'ridge_length_m':ridge,
            'display_name':rev.get('display_name',''),
            'road':addr.get('road',''),'hamlet':addr.get('hamlet',''),'village':addr.get('village',''),
            'town':addr.get('town',''),'county':addr.get('county',''),'postcode':addr.get('postcode',''),
            'osm_type':rev.get('type',''),'osm_category':rev.get('category',''),'satellite_image':img,
        })
        time.sleep(1.05)
    try:
        elements=overpass_context()
        (OUT/'overpass_raw.json').write_text(json.dumps(elements,indent=2))
    except Exception as exc:
        elements=[]
        (OUT/'overpass_error.txt').write_text(str(exc))
    for row in rows:
        nearby=[]
        for el in elements:
            la,lo=element_point(el)
            if la is None:continue
            d=haversine(row['lat'],row['lon'],la,lo)
            if d>1500:continue
            tags=el.get('tags',{})
            desc={k:tags[k] for k in ('name','landuse','natural','boundary','leisure','power','railway','highway','aeroway','place','historic','protect_class') if k in tags}
            if desc:nearby.append({'distance_m':round(d),'tags':desc})
        nearby.sort(key=lambda x:x['distance_m'])
        row['nearby_features_json']=json.dumps(nearby[:60],ensure_ascii=False)
    pd.DataFrame(rows).to_csv(OUT/'candidate_context.csv',index=False)
    (OUT/'candidate_context.json').write_text(json.dumps(rows,indent=2))
    # contact sheet
    thumbs=[]
    for rank,*_ in CANDIDATES:
        im=Image.open(IMAGES/f'candidate_{rank:02d}.jpg').resize((384,384))
        thumbs.append((rank,im.copy()))
    sheet=Image.new('RGB',(4*384,3*414),'white'); d=ImageDraw.Draw(sheet)
    for i,(rank,im) in enumerate(thumbs):
        x=(i%4)*384;y=(i//4)*414;sheet.paste(im,(x,y));d.text((x+8,y+389),f'Candidate #{rank}',fill='black')
    sheet.save(OUT/'candidate_satellite_contact_sheet.jpg',quality=92)
    print(f'Wrote context for {len(rows)} candidates and {len(elements)} OSM features')
if __name__=='__main__':main()
