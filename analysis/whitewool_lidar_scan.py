#!/usr/bin/env python3
"""EA 1 m DTM scan: retain only SE-S-SW slopes at least as steep as Whitewool."""
from __future__ import annotations
import argparse, json, math, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import rasterio
import requests
from pyproj import Transformer
from scipy import ndimage
from scipy.spatial import cKDTree

WCS = "https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs"
COVERAGE = "13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m"
FOUR_MARKS = (-1.04945, 51.10735)   # lon, lat
WHITEWOOL = (-1.0755, 50.9788)
WHITEWOOL_TTB_M = 60.96
TO_BNG = Transformer.from_crs(4326, 27700, always_xy=True)
TO_WGS = Transformer.from_crs(27700, 4326, always_xy=True)

@dataclass
class Benchmark:
    length_m: int
    grade: float
    angle_deg: float
    drop_m: float
    direction_deg: float
    official_ttb_m: float = WHITEWOOL_TTB_M

@dataclass
class Candidate:
    easting: float
    northing: float
    lon: float
    lat: float
    direction_deg: float
    grade: float
    angle_deg: float
    drop_m: float
    relief_350m: float
    ridge_length_m: float
    area_m2: float
    whitewool_ratio: float
    distance_miles: float
    source_tile: str
    score: float = 0.0
    status: str = "coarse"

def params(bounds, scale=None):
    e0,n0,e1,n1=bounds
    p=[("service","WCS"),("version","2.0.1"),("request","GetCoverage"),
       ("coverageId",COVERAGE),("subset",f"E({e0:.2f},{e1:.2f})"),
       ("subset",f"N({n0:.2f},{n1:.2f})"),("format","image/tiff")]
    if scale is not None: p.append(("scaleFactor",f"{scale:.8f}"))
    return p

def fetch(bounds, path:Path, scale=None, retries=5):
    if path.exists() and path.stat().st_size>10000:
        try:
            with rasterio.open(path) as ds:
                if ds.width>10 and ds.height>10:return path
        except Exception: path.unlink(missing_ok=True)
    path.parent.mkdir(parents=True,exist_ok=True)
    last=None
    for attempt in range(retries):
        try:
            r=requests.get(WCS,params=params(bounds,scale),timeout=(30,300),
                headers={"User-Agent":"WhitewoolTerrainScreen/1.1","Accept":"image/tiff,*/*;q=.1"})
            r.raise_for_status()
            if len(r.content)<10000 or r.content[:2] not in (b"II",b"MM"):
                raise RuntimeError("WCS did not return GeoTIFF: "+r.text[:250])
            tmp=path.with_suffix(".part"); tmp.write_bytes(r.content)
            with rasterio.open(tmp) as ds:
                if ds.width<10 or ds.height<10: raise RuntimeError("tiny raster")
            tmp.replace(path); return path
        except Exception as exc:
            last=exc
            if attempt+1<retries: time.sleep(min(30,2**(attempt+1)))
    raise RuntimeError(f"download failed: {last}")

def read(path):
    with rasterio.open(path) as ds:
        a=ds.read(1).astype("float32"); nd=ds.nodata
        if nd is not None:a[np.isclose(a,nd)]=np.nan
        a[(a<-100)|(a>1000)]=np.nan
        return a,ds.transform,float(abs(ds.transform.a))

def drop_dir(a,res,direction,length):
    r=math.radians(direction)
    dc=math.sin(r)*length/res; dr=math.cos(r)*length/res
    dest=ndimage.shift(a,(-dr,-dc),order=1,mode="constant",cval=np.nan,prefilter=False)
    return a-dest

def best_metric(a,res,directions,length):
    bg=np.full(a.shape,-np.inf,dtype="float32")
    bd=np.full(a.shape,np.nan,dtype="float32")
    br=np.full(a.shape,np.nan,dtype="float32")
    for d in directions:
        dp=drop_dir(a,res,d,length); g=dp/length
        use=np.isfinite(g)&(g>bg)
        bg[use]=g[use]; bd[use]=dp[use]; br[use]=d
    bg[~np.isfinite(bg)]=np.nan
    return bg,bd,br

def max_relief(a,res,directions,length=350):
    out=np.full(a.shape,-np.inf,dtype="float32")
    for d in directions:
        x=drop_dir(a,res,d,length)
        use=np.isfinite(x)&(x>out); out[use]=x[use]
    out[~np.isfinite(out)]=np.nan
    return out

def xy(transform,rows,cols):
    x=transform.c+(cols+.5)*transform.a+(rows+.5)*transform.b
    y=transform.f+(cols+.5)*transform.d+(rows+.5)*transform.e
    return x,y

def dist_miles(e0,n0,e1,n1): return math.hypot(e1-e0,n1-n0)/1609.344

def components(mask,transform,res,grade,drop,direction,relief,source,centre,min_area,min_length):
    labels,n=ndimage.label(mask,np.ones((3,3),dtype="uint8")); out=[]
    for i,obj in enumerate(ndimage.find_objects(labels),1):
        if obj is None:continue
        local=labels[obj]==i; count=int(local.sum()); area=count*res*res
        if area<min_area:continue
        rl,cl=np.nonzero(local); rr=rl+obj[0].start; cc=cl+obj[1].start
        xs,ys=xy(transform,rr,cc); pts=np.column_stack((xs,ys)); centred=pts-pts.mean(0)
        if len(pts)<3:continue
        vals=np.linalg.eigvalsh(np.cov(centred,rowvar=False)); major=4*math.sqrt(max(float(vals[-1]),0))
        if major<min_length:continue
        j=int(np.nanargmax(grade[rr,cc])); row=int(rr[j]); col=int(cc[j])
        ex,ny=xy(transform,np.array([row]),np.array([col])); e=float(ex[0]); n0=float(ny[0])
        lon,lat=TO_WGS.transform(e,n0); g=float(grade[row,col])
        out.append(Candidate(e,n0,float(lon),float(lat),float(direction[row,col]),g,
            math.degrees(math.atan(g)),float(drop[row,col]),float(relief[row,col]),major,area,
            0.0,dist_miles(centre[0],centre[1],e,n0),source))
    return out

def benchmark(outdir:Path,length:int):
    e,n=TO_BNG.transform(*WHITEWOOL); half=900
    p=fetch((e-half,n-half,e+half,n+half),outdir/"cache/whitewool_1m.tif")
    a,t,res=read(p); fill=float(np.nanmedian(a)); smooth=ndimage.gaussian_filter(np.where(np.isfinite(a),a,fill),6)
    directions=np.arange(20,100.1,2); grade,drop,direction=best_metric(smooth,res,directions,length)
    rows,cols=np.indices(a.shape); xs,ys=xy(t,rows,cols)
    valid=((xs-e)**2+(ys-n)**2<=500**2)&np.isfinite(grade)&(drop>0)
    if valid.sum()<100:raise RuntimeError("insufficient Whitewool data")
    q=float(np.nanpercentile(grade[valid],99.5)); top=valid&(grade>=q*.98)
    g=float(np.nanmedian(grade[top])); d=float(np.nanmedian(direction[top]))
    b=Benchmark(length,g,math.degrees(math.atan(g)),g*length,d)
    (outdir/"whitewool_benchmark.json").write_text(json.dumps(asdict(b),indent=2))
    return b

def tiles(centre,radius,size,overlap):
    ce,cn=centre; min_e=math.floor((ce-radius)/size)*size; max_e=math.ceil((ce+radius)/size)*size
    min_n=math.floor((cn-radius)/size)*size; max_n=math.ceil((cn+radius)/size)*size; out=[]
    for e0 in range(min_e,max_e,size):
        for n0 in range(min_n,max_n,size):
            dx=max(abs(e0+size/2-ce)-size/2,0); dy=max(abs(n0+size/2-cn)-size/2,0)
            if math.hypot(dx,dy)>radius:continue
            out.append((f"E{e0}_N{n0}",(e0-overlap,n0-overlap,e0+size+overlap,n0+size+overlap)))
    return out

def coarse_tile(name,bounds,outdir,b,centre,radius,scale,min_area,min_length):
    p=fetch(bounds,outdir/f"cache/coarse/{name}.tif",scale)
    a,t,res=read(p)
    if np.isfinite(a).sum()<1000:return []
    fill=float(np.nanmedian(a)); smooth=ndimage.gaussian_filter(np.where(np.isfinite(a),a,fill),max(1,12/res))
    directions=np.arange(135,225.1,5); grade,drop,direction=best_metric(smooth,res,directions,b.length_m)
    relief=max_relief(smooth,res,directions)
    rows,cols=np.indices(a.shape); xs,ys=xy(t,rows,cols)
    valid=np.isfinite(a)&((xs-centre[0])**2+(ys-centre[1])**2<=radius**2)
    mask=valid&(grade>=b.grade)&(drop>=b.drop_m)&(relief>=max(35,b.drop_m*1.05))
    iterations=max(1,int(round(12/res))); st=ndimage.generate_binary_structure(2,2)
    mask=ndimage.binary_opening(mask,st,iterations=iterations); mask=ndimage.binary_closing(mask,st,iterations=iterations)
    result=components(mask,t,res,grade,drop,direction,relief,name,centre,min_area,min_length)
    for c in result:c.whitewool_ratio=c.grade/b.grade
    return result

def dedupe(items,distance=500):
    keep=[]; points=[]
    for c in sorted(items,key=lambda x:(x.grade,x.ridge_length_m),reverse=True):
        if points and cKDTree(np.asarray(points)).query_ball_point([c.easting,c.northing],distance):continue
        keep.append(c); points.append((c.easting,c.northing))
    return keep

def verify(c,index,outdir,b,centre):
    half=900; p=fetch((c.easting-half,c.northing-half,c.easting+half,c.northing+half),outdir/f"cache/native/candidate_{index:03d}.tif")
    a,t,res=read(p)
    if np.isfinite(a).sum()<1000:return None
    fill=float(np.nanmedian(a)); smooth=ndimage.gaussian_filter(np.where(np.isfinite(a),a,fill),6)
    directions=np.arange(135,225.1,2); grade,drop,direction=best_metric(smooth,res,directions,b.length_m); relief=max_relief(smooth,res,directions)
    rows,cols=np.indices(a.shape); xs,ys=xy(t,rows,cols)
    near=(xs-c.easting)**2+(ys-c.northing)**2<=650**2
    mask=near&np.isfinite(a)&(grade>=b.grade)&(drop>=b.drop_m)&(relief>=max(35,b.drop_m*1.05))
    mask=ndimage.binary_opening(mask,np.ones((5,5),bool),iterations=2); mask=ndimage.binary_closing(mask,np.ones((5,5),bool),iterations=2)
    found=components(mask,t,res,grade,drop,direction,relief,c.source_tile,centre,25000,300)
    if not found:return None
    z=max(found,key=lambda x:(x.grade,x.ridge_length_m)); z.whitewool_ratio=z.grade/b.grade; z.status="verified_1m"
    z.score=50*min(z.whitewool_ratio,1.6)/1.6+25*min(z.relief_350m/max(b.official_ttb_m,1),1.6)/1.6+25*min(z.ridge_length_m/1000,1)
    return z

def write_outputs(outdir,b,coarse,verified,radius_miles):
    pd.DataFrame([asdict(x) for x in coarse]).to_csv(outdir/"coarse_candidates.csv",index=False)
    ranked=sorted(verified,key=lambda x:x.score,reverse=True); rows=[]
    for i,c in enumerate(ranked,1):r=asdict(c);r["rank"]=i;rows.append(r)
    pd.DataFrame(rows).to_csv(outdir/"verified_candidates.csv",index=False)
    features=[]
    for i,c in enumerate(ranked,1):
        prop=asdict(c);prop["rank"]=i
        features.append({"type":"Feature","geometry":{"type":"Point","coordinates":[c.lon,c.lat]},"properties":prop})
    (outdir/"verified_candidates.geojson").write_text(json.dumps({"type":"FeatureCollection","features":features},indent=2))
    lon,lat=FOUR_MARKS; m=folium.Map([lat,lon],zoom_start=10,tiles=None,control_scale=True)
    folium.TileLayer("OpenStreetMap",show=False,name="Street").add_to(m)
    folium.TileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",attr="OpenTopoMap",show=True,name="Topographic").add_to(m)
    folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",attr="Esri",show=False,name="Satellite").add_to(m)
    folium.Circle([lat,lon],radius=radius_miles*1609.344,color="#3455db",fill=False,dash_array="8,8").add_to(m)
    folium.Marker([lat,lon],tooltip="Four Marks",icon=folium.Icon(color="blue",icon="home",prefix="fa")).add_to(m)
    folium.Marker([WHITEWOOL[1],WHITEWOOL[0]],tooltip=f"Whitewool benchmark {b.angle_deg:.1f}° over {b.length_m}m",icon=folium.Icon(color="green",icon="flag",prefix="fa")).add_to(m)
    for i,c in enumerate(ranked,1):
        txt=(f"<b>#{i} — native 1 m verified</b><br>Coordinates: {c.lat:.6f}, {c.lon:.6f}<br>"
             f"Sustained angle: {c.angle_deg:.1f}°<br>Whitewool ratio: {c.whitewool_ratio:.2f}×<br>"
             f"Drop over {b.length_m} m: {c.drop_m:.1f} m<br>Relief over 350 m: {c.relief_350m:.1f} m<br>"
             f"Steep-face length: {c.ridge_length_m:.0f} m<br>Downhill aspect: {c.direction_deg:.0f}°<br>"
             f"Distance: {c.distance_miles:.1f} miles<br>Score: {c.score:.1f}/100")
        folium.Marker([c.lat,c.lon],tooltip=f"#{i}: {c.whitewool_ratio:.2f}× Whitewool",popup=folium.Popup(txt,max_width=420),icon=folium.Icon(color="red",icon="map-marker",prefix="fa")).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m); m.save(outdir/"whitewool_lidar_candidates_map.html")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,default=Path("whitewool_scan_output")); ap.add_argument("--radius-miles",type=float,default=30)
    ap.add_argument("--profile-length",type=int,default=200); ap.add_argument("--coarse-resolution",type=float,default=10); ap.add_argument("--tile-size",type=int,default=6000)
    ap.add_argument("--tile-overlap",type=int,default=400); ap.add_argument("--workers",type=int,default=4); ap.add_argument("--min-area",type=float,default=30000)
    ap.add_argument("--min-ridge",type=float,default=300); ap.add_argument("--max-native",type=int,default=50); args=ap.parse_args()
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True); centre=TO_BNG.transform(*FOUR_MARKS); radius=args.radius_miles*1609.344
    print("1/5 Benchmarking Whitewool at native 1 m",flush=True); b=benchmark(out,args.profile_length)
    print(f"Whitewool: {b.angle_deg:.2f}° ({b.grade*100:.1f}%), {b.drop_m:.1f} m / {b.length_m} m",flush=True)
    work=tiles(centre,radius,args.tile_size,args.tile_overlap); print(f"2/5 {len(work)} regional tiles",flush=True)
    allc=[]; failures=[]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        fut={ex.submit(coarse_tile,n,bo,out,b,centre,radius,1/args.coarse_resolution,args.min_area,args.min_ridge):n for n,bo in work}
        for k,f in enumerate(as_completed(fut),1):
            try:allc.extend(f.result())
            except Exception as e:failures.append(f"{fut[f]}: {e}")
            if k%10==0 or k==len(fut):print(f"3/5 {k}/{len(fut)} tiles, {len(allc)} raw survivors, {len(failures)} failures",flush=True)
    coarse=dedupe(allc)[:args.max_native]; pd.DataFrame([asdict(x) for x in coarse]).to_csv(out/"coarse_candidates.csv",index=False)
    print(f"4/5 Native 1 m verification of {len(coarse)} survivors",flush=True); verified=[]
    for i,c in enumerate(coarse,1):
        try:
            z=verify(c,i,out,b,centre)
            if z:verified.append(z);print(f"PASS {i}: {z.angle_deg:.1f}°, {z.whitewool_ratio:.2f}×, ridge {z.ridge_length_m:.0f}m",flush=True)
            else:print(f"reject {i}",flush=True)
        except Exception as e:failures.append(f"candidate {i}: {e}");print(f"error {i}: {e}",flush=True)
    verified=dedupe(verified); print(f"5/5 Writing {len(verified)} verified results",flush=True); write_outputs(out,b,coarse,verified,args.radius_miles)
    if failures:(out/"failures.txt").write_text("\n".join(failures))
    print(f"DONE: {len(verified)} native-1m candidates in {out}",flush=True)
if __name__=="__main__":main()
