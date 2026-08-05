#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures as cf
import json, math, os, re, shutil, time, random, threading
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import rasterio
from rasterio.enums import Resampling
from rasterio.features import shapes
from scipy import ndimage
from scipy.ndimage import map_coordinates
from pyproj import Transformer
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import transform as shp_transform
import folium
from folium.plugins import Fullscreen, MeasureControl
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

WCS='https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs'
COVERAGE='13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m'
FOUR_LAT, FOUR_LON = 51.10735, -1.04945
RADIUS_M = 30*1609.344
WHITE_E, WHITE_N = 465000.0, 120400.0
OUT=Path(os.environ.get('GIS_OUTPUT','analysis/four_marks_gis/output_revised'))
CACHE=Path(os.environ.get('GIS_CACHE','/tmp/four_marks_gis_cache'))
TO_BNG=Transformer.from_crs(4326,27700,always_xy=True)
TO_WGS=Transformer.from_crs(27700,4326,always_xy=True)
FOUR_E,FOUR_N=TO_BNG.transform(FOUR_LON,FOUR_LAT)
_WCS_GATE=threading.Lock()
_WCS_LAST=[0.0]
_ORIGINAL_JSON_DEFAULT=json.JSONEncoder.default

def _numpy_json_default(self,obj):
    if isinstance(obj,np.generic):
        return obj.item()
    if isinstance(obj,np.ndarray):
        return obj.tolist()
    return _ORIGINAL_JSON_DEFAULT(self,obj)

json.JSONEncoder.default=_numpy_json_default

def wcs_throttle(min_gap=5.0):
    with _WCS_GATE:
        elapsed=time.monotonic()-_WCS_LAST[0]
        if elapsed<min_gap:
            time.sleep(min_gap-elapsed)
        _WCS_LAST[0]=time.monotonic()

FORCED_WGS = {
 'Pidham Hill': (51.001758,-1.011611),
 'Henwood Down': (50.9938,-1.05882),
 'Barn Lane and Kingswood Rise': (51.10715,-1.06074),
 'Bighton Hill': (51.09017,-1.10026),
 'Neatham Down': (51.1485,-0.9501),
 'Longwood Warren': (51.03128,-1.21851),
 'Gander Down': (51.0385,-1.2160),
 'Axford slopes': (51.0435,-1.1455),
 'Bramdean slopes': (51.0300,-1.1200),
 'Candover Valley': (51.1826,-1.1335),
 'Tunworth Down': TO_WGS.transform(469300,149000)[::-1],
 'Weston Corbett': (51.2225,-1.0245),
 'Upton Grey': (51.2372,-1.0045),
 'Farleigh Hill': TO_WGS.transform(462400,146300)[::-1],
 'Semaphore Farm and Headmore': (51.1024,-1.0318),
 'Holybourne slopes': (51.18002,-0.95321),
 'Bentworth slopes': (51.1555,-1.0545),
 'Chawton Park': (51.1270,-1.0120),
 'Windmill Down': (50.9398,-1.0801),
}
EXISTING_SITES = {
 'Whitewool': TO_WGS.transform(WHITE_E,WHITE_N)[::-1],
 'Park Hill': (50.994732,-1.031709),
 'Butser West': (50.9778,-0.9842),
 'Butser East': (50.9789,-0.9655),
 'Harting': (50.9689,-0.8895),
 'Mercury': (50.9780,-1.0620),
 'Chalton': (50.94035,-0.9816),
 'Matterley Bowl': (51.0605,-1.2550),
 'Meon Shore': (50.8158,-1.2190),
}
AERODROMES = {
 'Lasham Gliding Centre': (51.1867,-1.0335),
 'Popham Airfield': (51.1939,-1.2347),
 'Southampton Airport': (50.9503,-1.3568),
 'Solent Airport': (50.8153,-1.2096),
}

@dataclass
class Face:
    source:str=''; name:str=''; status:str=''; category:str='Rejected'; easting:float=0; northing:float=0
    latitude:float=0; longitude:float=0; grid_ref:str=''; distance_miles:float=0
    aspect_deg:float=float('nan'); aspect_text:str=''; representative_slope_deg:float=float('nan')
    median_local_slope_deg:float=float('nan'); max_robust_slope_deg:float=float('nan')
    mean_upper_slope_deg:float=float('nan'); vertical_relief_m:float=float('nan')
    vertical_relief_ft:float=float('nan'); horizontal_run_m:float=float('nan')
    face_width_m:float=float('nan'); ridge_length_m:float=float('nan')
    downslope_span_m:float=float('nan'); connected_area_ha:float=float('nan')
    lip_sharpness_deg:float=float('nan'); roughness_m:float=float('nan')
    gaps_count:int=0; largest_gap_m:float=0; percent_face_at_benchmark:float=0
    percent_face_8deg:float=0; percent_face_9_5deg:float=0; ridge_8deg_m:float=0; ridge_9_5deg_m:float=0
    whitewool_slope_percent:float=0; whitewool_relief_percent:float=0
    pass_terrain:bool=False; terrain_score:float=0; overall_score:float=0
    landcover_observation:str='Not yet checked'; launch_observation:str='Terrain-derived only'
    landing_observation:str='Terrain-derived only'; obstacle_observation:str='Not yet checked'
    airspace_observation:str='Not yet checked'; protected_observation:str='Not yet checked'
    existing_site_conflict:str='None identified'; confidence:str='Medium'; reason:str=''
    polygon_wkt:str=''; profile_file:str=''

def log(s): print(s,flush=True)
def wcs_url(bounds,scale=1.0):
    e0,n0,e1,n1=bounds
    u=(f'{WCS}?service=WCS&version=2.0.1&request=GetCoverage&coverageId={COVERAGE}'
       f'&subset=E({int(e0)},{int(e1)})&subset=N({int(n0)},{int(n1)})&format=image/tiff')
    if scale != 1.0: u += f'&scaleFactor={scale:g}'
    return u

def download(bounds,scale,path,retries=15):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.stat().st_size>1000:
        try:
            with rasterio.open(path) as ds:
                if ds.width>2 and ds.height>2:return path
        except: path.unlink(missing_ok=True)
    headers={'User-Agent':'FourMarksParaglidingTerrainAnalysis/1.0','Accept':'image/tiff,*/*;q=0.1'}
    err=None
    for i in range(retries):
        try:
            tmp=path.with_suffix('.part')
            wcs_throttle()
            with requests.get(wcs_url(bounds,scale),headers=headers,stream=True,timeout=(60,1800)) as r:
                r.raise_for_status()
                with tmp.open('wb') as f:
                    for block in r.iter_content(4*1024*1024):
                        if block:f.write(block)
            if tmp.stat().st_size<1000:
                raise RuntimeError('WCS returned undersized response')
            with tmp.open('rb') as fh:
                if fh.read(20).lstrip().startswith(b'<'):raise RuntimeError('WCS returned XML')
            with rasterio.open(tmp) as ds:
                if ds.width<3:raise RuntimeError('bad raster')
            tmp.replace(path);return path
        except Exception as ex:
            err=ex
            path.with_suffix('.part').unlink(missing_ok=True)
            response=getattr(ex,'response',None)
            retry_after=response.headers.get('Retry-After') if response is not None else None
            try:
                delay=float(retry_after) if retry_after else min(300.0,15.0*(i+1))
            except (TypeError,ValueError):
                delay=min(300.0,15.0*(i+1))
            delay+=random.uniform(0.0,3.0)
            log(f'WCS attempt {i+1}/{retries} failed for {bounds} scale={scale}: {ex}; retrying in {delay:.0f}s')
            time.sleep(delay)
    raise RuntimeError(f'WCS failure {bounds} scale={scale}: {err}')

def read_raster(path,target_res=None):
    with rasterio.open(path) as ds:
        if target_res and target_res>ds.res[0]:
            ow=max(2,round(ds.width*ds.res[0]/target_res)); oh=max(2,round(ds.height*ds.res[1]/target_res))
            a=ds.read(1,out_shape=(oh,ow),resampling=Resampling.average).astype('float32')
            tr=ds.transform*ds.transform.scale(ds.width/ow,ds.height/oh)
        else:a=ds.read(1).astype('float32');tr=ds.transform
        if ds.nodata is not None:a[np.isclose(a,ds.nodata)]=np.nan
        a[a<-1e20]=np.nan
    return a,tr,abs(tr.a)

def smooth_valid(a,sigma):
    v=np.isfinite(a); filled=np.where(v,a,0)
    w=ndimage.gaussian_filter(v.astype('float32'),sigma,mode='nearest')
    z=ndimage.gaussian_filter(filled.astype('float32'),sigma,mode='nearest')
    return np.divide(z,w,out=np.full_like(z,np.nan),where=w>0.5)

def slope_aspect(z,res):
    gr,gc=np.gradient(z,res,res)
    slope=np.degrees(np.arctan(np.hypot(gc,gr)))
    aspect=(np.degrees(np.arctan2(-gc,gr))+360)%360
    slope[~np.isfinite(z)]=np.nan; aspect[~np.isfinite(z)]=np.nan
    return slope,aspect

def circular_mean(v):
    v=np.asarray(v);v=v[np.isfinite(v)]
    if not len(v):return np.nan
    r=np.radians(v);return (np.degrees(np.arctan2(np.mean(np.sin(r)),np.mean(np.cos(r))))+360)%360

def aspect_name(d):
    if not np.isfinite(d):return ''
    names=['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
    return names[int((d+11.25)//22.5)%16]

def sustained(z,res,azimuths,distances=(40,80,120,160,200,240)):
    rr,cc=np.indices(z.shape,dtype='float32'); best=np.full(z.shape,-999,dtype='float32')
    baz=np.full(z.shape,np.nan,dtype='float32'); drops={d:np.full(z.shape,np.nan,dtype='float32') for d in distances}
    mono_best=np.zeros(z.shape,dtype='float32')
    for az in azimuths:
        rad=np.radians(az); de=np.sin(rad); dn=np.cos(rad); vals=[]
        for d in distances:
            vals.append(map_coordinates(z,[rr-dn*d/res,cc+de*d/res],order=1,mode='constant',cval=np.nan,prefilter=False))
        ds=[z-v for v in vals]
        intervals=[z-vals[0]]+[vals[i-1]-vals[i] for i in range(1,len(vals))]
        mono=np.mean(np.stack([x>=-0.6 for x in intervals[:4]]),axis=0)
        a120=np.degrees(np.arctan2(ds[2],120));a160=np.degrees(np.arctan2(ds[3],160));a200=np.degrees(np.arctan2(ds[4],200))
        # The revised screen measures the sustained upper/middle face over 120-200 m.
        # Small tolerances prevent a single rounded lower section from hiding an otherwise continuous face.
        ang=np.minimum(a120,np.minimum(a160+0.7,a200+1.2))
        valid=np.isfinite(ang)&(ds[3]>0)&(ds[4]>0)&(mono>=.75)
        imp=valid&(ang>best);best[imp]=ang[imp];baz[imp]=az;mono_best[imp]=mono[imp]
        for d,arr in zip(distances,ds):drops[d][imp]=arr[imp]
    best[best<-100]=np.nan
    return best,baz,drops,mono_best

def centres(tr,shape):
    rr,cc=np.indices(shape);x=tr.c+(cc+.5)*tr.a;y=tr.f+(rr+.5)*tr.e;return x,y

def project_spans(x,y,az):
    r=np.radians(az);along=x*np.sin(r)+y*np.cos(r);cross=x*np.cos(r)-y*np.sin(r)
    return np.ptp(along),np.ptp(cross),along,cross

def polygon_from_mask(mask,tr):
    geoms=[]
    for g,val in shapes(mask.astype('uint8'),mask=mask,transform=tr):
        if val==1:geoms.append(shape(g))
    if not geoms:return None
    from shapely.ops import unary_union
    p=unary_union(geoms)
    if p.geom_type=='MultiPolygon':p=max(p.geoms,key=lambda q:q.area)
    return p.simplify(8)

def gridref(e,n,digits=8):
    e=int(e);n=int(n);e100=e//100000;n100=n//100000
    l1=(19-n100)-(19-n100)%5+(e100+10)//5;l2=(19-n100)*5%25+e100%5
    if l1>7:l1+=1
    if l2>7:l2+=1
    letters=chr(l1+65)+chr(l2+65);half=digits//2;f=10**(5-half)
    return f'{letters} {(e%100000)//f:0{half}d} {(n%100000)//f:0{half}d}'

def select_face(z,tr,res,azimuths,near_e,near_n,benchmark=None,white=False):
    zs=smooth_valid(z,max(1,8/res)); local_slope,local_aspect=slope_aspect(zs,res)
    ang,az,drops,mono=sustained(zs,res,azimuths)
    x,y=centres(tr,z.shape);dist=np.hypot(x-near_e,y-near_n)
    if white:
        base=np.isfinite(ang)&(dist<600)&(drops[200]>=24)&(ang>=7)
        base=ndimage.binary_opening(base,np.ones((2,2)));base=ndimage.binary_closing(base,np.ones((5,5)))
    else:
        # Deliberately broader than Whitewool: retain potentially soarable inland faces.
        base=np.isfinite(ang)&(dist<1300)&(drops[160]>=18)&(drops[200]>=20)&(ang>=5.5)
        base&=(local_slope>=4.5)
        base=ndimage.binary_opening(base,np.ones((2,2)));base=ndimage.binary_closing(base,np.ones((5,5)))
    labels,nlab=ndimage.label(base,np.ones((3,3),dtype='uint8'));options=[]
    for i in range(1,nlab+1):
        m=labels==i;pix=m.sum()
        if pix<max(30,int(0.4*10000/(res*res))):continue
        xx=x[m];yy=y[m];aa=ang[m];asp=circular_mean(az[m]);along,cross,_,_=project_spans(xx,yy,asp)
        rel=float(np.nanmedian(drops[200][m]))
        if white:
            score=(1/(1+np.nanmin(dist[m])/150))*0.25 + min(1,rel/60)*.35+min(1,cross/500)*.25+min(1,pix*res*res/60000)*.15
        else:score=np.nanmedian(aa)+rel/8+cross/300
        options.append((score,m,asp,along,cross))
    if not options:return None
    score,m,asp,along_span,cross_span=max(options,key=lambda t:t[0])
    threshold=float(np.nanmedian(ang[m])) if white else 8.0
    broad=np.isfinite(ang)&(dist<(650 if white else 1400))&(drops[160]>=max(12,(np.nanmedian(drops[160][m])*.40)))&(ang>=max(4.5,threshold*.58))
    bl,n=ndimage.label(broad,np.ones((3,3),dtype='uint8'));ids=np.unique(bl[m]);ids=ids[ids>0];broad=np.isin(bl,ids) if len(ids) else m
    vals=ang[m]; rep=float(np.nanmedian(vals)); p95=float(np.nanpercentile(local_slope[m],95)); medloc=float(np.nanmedian(local_slope[m]))
    ztop=np.nanpercentile(z[m],60); upper=m&(z>=ztop);meanup=float(np.nanmean(ang[upper]))
    relief=float(np.nanmedian(drops[200][m])); run=200.0
    xx=x[m];yy=y[m];down,cross,alongv,crossv=project_spans(xx,yy,asp)
    bins=np.arange(crossv.min(),crossv.max()+20,20);occ=np.histogram(crossv,bins)[0]>0;gaps=[];start=None
    for j,v in enumerate(occ):
        if not v and start is None:start=j
        if v and start is not None:gaps.append((j-start)*20);start=None
    if start is not None:gaps.append((len(occ)-start)*20)
    gaps=[g for g in gaps if g>=20];rough=float(np.nanstd(local_slope[m]))
    lip=float(np.nanmedian(np.degrees(np.arctan2(drops[40][m],40)) - np.degrees(np.arctan2(drops[120][m]-drops[40][m],80))))
    pct=float(100*np.sum(broad & (ang>=threshold))/max(1,np.sum(broad)))
    pct8=float(100*np.sum(broad & (ang>=8.0))/max(1,np.sum(broad)))
    pct95=float(100*np.sum(broad & (ang>=9.5))/max(1,np.sum(broad)))
    def qualifying_width(qmask):
        labs,nq=ndimage.label(qmask,np.ones((3,3),dtype='uint8'))
        choices=[]
        for qi in range(1,nq+1):
            qm=labs==qi
            if qm.sum()<20:continue
            qx=x[qm];qy=y[qm];_,qw,_,_=project_spans(qx,qy,asp);choices.append((qm.sum(),float(qw)))
        return max(choices,key=lambda q:q[0])[1] if choices else 0.0
    ridge8=qualifying_width(broad & (ang>=8.0));ridge95=qualifying_width(broad & (ang>=9.5))
    poly=polygon_from_mask(broad,tr)
    weights=np.clip(ang[m]-np.nanmin(ang[m])+.1,.1,None);e=float(np.average(xx,weights=weights));n=float(np.average(yy,weights=weights))
    return dict(mask=m,broad=broad,z=zs,local_slope=local_slope,ang=ang,az=az,drops=drops,aspect=asp,
        representative_slope_deg=rep,median_local_slope_deg=medloc,max_robust_slope_deg=p95,mean_upper_slope_deg=meanup,
        vertical_relief_m=relief,horizontal_run_m=run,face_width_m=cross_span,ridge_length_m=cross_span,downslope_span_m=down,
        connected_area_ha=float(m.sum()*res*res/10000),lip_sharpness_deg=lip,roughness_m=rough,gaps_count=len(gaps),largest_gap_m=max(gaps or [0]),
        percent_face_at_benchmark=pct,percent_face_8deg=pct8,percent_face_9_5deg=pct95,ridge_8deg_m=ridge8,ridge_9_5deg_m=ridge95,polygon=poly,easting=e,northing=n)

def profiles(face,tr,res,name,outdir):
    m=face['mask'];z=face['z'];x,y=centres(tr,z.shape);asp=face['aspect'];xx=x[m];yy=y[m]
    _,_,_,cross=project_spans(xx,yy,asp);targets=np.quantile(cross,[.2,.5,.8]);inds=np.where(m);cross_all=x[m]*np.cos(np.radians(asp))-y[m]*np.sin(np.radians(asp));origins=[]
    for t in targets:
        k=np.argmin(np.abs(cross_all-t));origins.append((inds[0][k],inds[1][k]))
    ds=np.arange(0,321,4);fig,ax=plt.subplots(figsize=(9,5));records=[]
    for idx,(r,c) in enumerate(origins,1):
        rad=np.radians(asp);vals=map_coordinates(z,[r-np.cos(rad)*ds/res,c+np.sin(rad)*ds/res],order=1,mode='constant',cval=np.nan)
        ax.plot(ds,vals,label=f'Profile {idx}')
        for d,v in zip(ds,vals):records.append({'profile':idx,'distance_m':float(d),'elevation_m':float(v) if np.isfinite(v) else None})
    ax.set(title=f'{name}: DTM profiles along {aspect_name(asp)} ({asp:.0f}°)',xlabel='Horizontal distance downslope (m)',ylabel='Elevation (m ODN)');ax.grid(True,alpha=.3);ax.legend();fig.tight_layout()
    safe=re.sub(r'[^A-Za-z0-9_-]+','_',name).strip('_').lower();outdir.mkdir(parents=True,exist_ok=True);png=outdir/f'{safe}_profile.png';fig.savefig(png,dpi=160);plt.close(fig)
    pd.DataFrame(records).to_csv(outdir/f'{safe}_profile.csv',index=False);return str(png.relative_to(OUT))

def benchmark_whitewool():
    p=download((463500,118900,466500,121900),1.0,CACHE/'whitewool_1m.tif')
    z,tr,res=read_raster(p,4.0);f=select_face(z,tr,res,np.arange(20,101,5),WHITE_E,WHITE_N,white=True)
    if not f:raise RuntimeError('Whitewool face not found')
    f['profile_file']=profiles(f,tr,res,'Whitewool',OUT/'profiles')
    b={k:(float(v) if isinstance(v,(np.floating,float)) else int(v) if isinstance(v,(np.integer,int)) else v) for k,v in f.items() if k not in {'mask','broad','z','local_slope','ang','az','drops','polygon'}}
    b.update(reference_easting=WHITE_E,reference_northing=WHITE_N,reference_grid_ref='SU 6500 2040',dataset='Environment Agency LIDAR Composite DTM 1m',analysis_resolution_m=res,
             minimum_representative_slope_deg=f['representative_slope_deg']-.25,minimum_relief_m=max(35,f['vertical_relief_m']*.80),minimum_ridge_length_m=max(180,f['ridge_length_m']*.70),minimum_face_percentage=max(35,f['percent_face_at_benchmark']*.70),
             methodology='Continuous face selected automatically near SU650204 using sustained 160–300 m downhill profiles; 4 m averaged DTM suppresses one-metre banks and ditches. Robust maximum is the 95th percentile local slope, not the steepest pixel.')
    b['polygon_geojson']=mapping(f['polygon']) if f['polygon'] else None;(OUT/'whitewool_benchmark.json').write_text(json.dumps(b,indent=2));return b,f,tr,res

def coarse_tiles(tile=8000,overlap=320):
    x0=math.floor((FOUR_E-RADIUS_M)/tile)*tile;x1=math.ceil((FOUR_E+RADIUS_M)/tile)*tile;y0=math.floor((FOUR_N-RADIUS_M)/tile)*tile;y1=math.ceil((FOUR_N+RADIUS_M)/tile)*tile
    out=[];circle=Point(FOUR_E,FOUR_N).buffer(RADIUS_M)
    for e in range(int(x0),int(x1),tile):
      for n in range(int(y0),int(y1),tile):
        core=Polygon([(e,n),(e+tile,n),(e+tile,n+tile),(e,n+tile)])
        if core.intersects(circle):out.append((e-overlap,n-overlap,e+tile+overlap,n+tile+overlap,e,n,e+tile,n+tile))
    return out

def process_coarse(item,b):
    e0,n0,e1,n1,ce0,cn0,ce1,cn1=item;key=f'E{ce0}_N{cn0}';p=download((e0,n0,e1,n1),.1,CACHE/'coarse10'/f'{key}.tif')
    z,tr,res=read_raster(p);zs=smooth_valid(z,1.2);sl,asp=slope_aspect(zs,res);size=max(9,int(round(220/res)));hi=ndimage.maximum_filter(zs,size=size,mode='nearest');lo=ndimage.minimum_filter(zs,size=size,mode='nearest');rel=hi-lo
    mask=np.isfinite(sl)&(sl>=5.0)&(asp>=135)&(asp<=225)&(rel>=18.0)
    x,y=centres(tr,z.shape);mask&=(x>=ce0)&(x<ce1)&(y>=cn0)&(y<cn1)&((x-FOUR_E)**2+(y-FOUR_N)**2<=RADIUS_M**2)
    mask=ndimage.binary_opening(mask,np.ones((2,2)));mask=ndimage.binary_closing(mask,np.ones((4,4)));lab,nlab=ndimage.label(mask,np.ones((3,3),dtype='uint8'));rows=[]
    for i in range(1,nlab+1):
      m=lab==i
      if m.sum()<70:continue
      xx=x[m];yy=y[m];a=circular_mean(asp[m]);down,cross,_,_=project_spans(xx,yy,a);relief=float(np.nanpercentile(z[m],95)-np.nanpercentile(z[m],5))
      if cross<120 or relief<18.0:continue
      weights=np.clip(sl[m]-np.nanmin(sl[m])+.1,.1,None);e=float(np.average(xx,weights=weights));n=float(np.average(yy,weights=weights))
      rows.append(dict(easting=e,northing=n,coarse_local_slope=float(np.nanmedian(sl[m])),coarse_relief_m=relief,coarse_width_m=float(cross),coarse_area_ha=float(m.sum()*res*res/10000),coarse_aspect_deg=a,tile=key))
    return rows

def dedup(rows):
    rows=sorted(rows,key=lambda r:(r['coarse_relief_m']+r['coarse_width_m']/20+r['coarse_local_slope']),reverse=True);keep=[]
    for r in rows:
      if any(math.hypot(r['easting']-q['easting'],r['northing']-q['northing'])<1200 for q in keep):continue
      keep.append(r)
    return keep

def nearest_label(e,n):
    choices=[]
    for name,(lat,lon) in FORCED_WGS.items():
      ee,nn=TO_BNG.transform(lon,lat);choices.append((math.hypot(e-ee,n-nn),name))
    d,name=min(choices);return name if d<1800 else f'Unnamed face near {gridref(e,n,6)}'

def exact_assess(name,e,n,b,source):
    safe=re.sub('[^A-Za-z0-9]+','_',name);p=download((math.floor(e-1500),math.floor(n-1500),math.ceil(e+1500),math.ceil(n+1500)),1.0,CACHE/'exact'/f'{safe}_{int(e)}_{int(n)}.tif')
    z,tr,res=read_raster(p,4.0);f=select_face(z,tr,res,np.arange(135,226,5),e,n,benchmark=b)
    if not f:
      lon,lat=TO_WGS.transform(e,n);return Face(source=source,name=name,status='Rejected terrain',easting=e,northing=n,latitude=lat,longitude=lon,grid_ref=gridref(e,n),distance_miles=math.hypot(e-FOUR_E,n-FOUR_N)/1609.344,pass_terrain=False,reason='No contiguous south-east to south-west face in the 3 km verification window met the revised 120–200 m sustained-profile pre-filter.')
    e2,n2=f['easting'],f['northing'];lon,lat=TO_WGS.transform(e2,n2)
    likely=(f['representative_slope_deg']>=9.5 and f['vertical_relief_m']>=30 and f['ridge_8deg_m']>=400 and f['percent_face_8deg']>=30)
    marginal=(f['representative_slope_deg']>=8.0 and f['vertical_relief_m']>=25 and f['ridge_8deg_m']>=300 and f['percent_face_8deg']>=20)
    thermal=(f['representative_slope_deg']>=6.0 and f['vertical_relief_m']>=20 and f['ridge_length_m']>=250)
    if likely: category='Likely ridge-soarable';status='Likely ridge-soarable';passed=True
    elif marginal: category='Marginal — inspect carefully';status='Marginal terrain candidate';passed=True
    elif thermal: category='Thermal trigger only';status='Thermal-trigger terrain';passed=False
    else: category='Rejected';status='Rejected terrain';passed=False
    terrain=100*(.28*min(1.25,f['representative_slope_deg']/9.5)+.18*min(1.25,f['vertical_relief_m']/30)+.18*min(1.25,f['ridge_8deg_m']/400)+.10*max(0,1-abs(f['aspect']-180)/45)+.08*min(1.25,max(0,f['lip_sharpness_deg']+5)/10)+.08*min(1.25,f['connected_area_ha']/3.0)+.10*min(1.25,f['percent_face_8deg']/30))
    reason=(f"Sustained 120–200 m slope {f['representative_slope_deg']:.1f}°; relief {f['vertical_relief_m']:.0f} m; qualifying ridge at ≥8° {f['ridge_8deg_m']:.0f} m; {f['percent_face_8deg']:.0f}% of the broader face reaches 8° and {f['percent_face_9_5deg']:.0f}% reaches 9.5°. Category: {category}.")
    face=Face(source=source,name=name,status=status,category=category,easting=e2,northing=n2,latitude=lat,longitude=lon,grid_ref=gridref(e2,n2),distance_miles=math.hypot(e2-FOUR_E,n2-FOUR_N)/1609.344,aspect_deg=f['aspect'],aspect_text=aspect_name(f['aspect']),representative_slope_deg=f['representative_slope_deg'],median_local_slope_deg=f['median_local_slope_deg'],max_robust_slope_deg=f['max_robust_slope_deg'],mean_upper_slope_deg=f['mean_upper_slope_deg'],vertical_relief_m=f['vertical_relief_m'],vertical_relief_ft=f['vertical_relief_m']*3.28084,horizontal_run_m=f['horizontal_run_m'],face_width_m=f['face_width_m'],ridge_length_m=f['ridge_length_m'],downslope_span_m=f['downslope_span_m'],connected_area_ha=f['connected_area_ha'],lip_sharpness_deg=f['lip_sharpness_deg'],roughness_m=f['roughness_m'],gaps_count=f['gaps_count'],largest_gap_m=f['largest_gap_m'],percent_face_at_benchmark=f['percent_face_at_benchmark'],percent_face_8deg=f['percent_face_8deg'],percent_face_9_5deg=f['percent_face_9_5deg'],ridge_8deg_m=f['ridge_8deg_m'],ridge_9_5deg_m=f['ridge_9_5deg_m'],whitewool_slope_percent=100*f['representative_slope_deg']/b['representative_slope_deg'],whitewool_relief_percent=100*f['vertical_relief_m']/b['vertical_relief_m'],pass_terrain=passed,terrain_score=min(100,terrain),overall_score=min(100,terrain),reason=reason,polygon_wkt=f['polygon'].wkt if f['polygon'] else '')
    face.profile_file=profiles(f,tr,res,name,OUT/'profiles');return face

def osm_check(face):
    q=f'''[out:json][timeout:90];(way["natural"="wood"](around:1200,{face.latitude},{face.longitude});way["landuse"="forest"](around:1200,{face.latitude},{face.longitude});way["building"](around:800,{face.latitude},{face.longitude});way["power"="line"](around:1200,{face.latitude},{face.longitude});node["power"="tower"](around:1200,{face.latitude},{face.longitude});way["highway"~"motorway|trunk|primary"](around:1200,{face.latitude},{face.longitude});way["railway"](around:1200,{face.latitude},{face.longitude});relation["boundary"="protected_area"](around:1500,{face.latitude},{face.longitude});way["leisure"="nature_reserve"](around:1500,{face.latitude},{face.longitude}););out center tags;'''
    try:
      r=requests.post('https://overpass-api.de/api/interpreter',data=q,timeout=120);r.raise_for_status();els=r.json()['elements'];counts={'wood':0,'buildings':0,'power':0,'major_roads':0,'railway':0,'protected':0}
      for e in els:
        t=e.get('tags',{})
        if t.get('natural')=='wood' or t.get('landuse')=='forest':counts['wood']+=1
        if 'building' in t:counts['buildings']+=1
        if t.get('power') in {'line','tower'}:counts['power']+=1
        if t.get('highway') in {'motorway','trunk','primary'}:counts['major_roads']+=1
        if 'railway' in t:counts['railway']+=1
        if t.get('boundary')=='protected_area' or t.get('leisure')=='nature_reserve':counts['protected']+=1
      face.landcover_observation=f"OSM within 1.2 km: {counts['wood']} mapped woodland polygons; field/crop condition still requires site inspection."
      face.obstacle_observation=f"OSM screen: {counts['buildings']} building ways within 800 m, {counts['power']} power features, {counts['major_roads']} major-road ways and {counts['railway']} railway ways within 1.2 km."
      face.protected_observation=f"OSM mapped protected/nature-reserve features within 1.5 km: {counts['protected']}; confirm against official Natural England and Historic England records."
      penalty=min(20,counts['wood']*2+counts['power']*3+counts['major_roads']*2+counts['railway']*3+counts['protected']*3);face.overall_score=max(0,face.terrain_score-penalty)
    except Exception as ex:face.obstacle_observation=f'OSM query failed: {ex}';face.confidence='Low'
    face.airspace_observation='Not automatically checked; manually review current aviation charts, NOTAMs, aerodromes and local procedures.'
    near=[]
    for nm,(lat,lon) in EXISTING_SITES.items():
      e,n=TO_BNG.transform(lon,lat);d=math.hypot(face.easting-e,face.northing-n)/1609.344
      if d<2.0:near.append(f'{nm} ({d:.1f} mi)')
    face.existing_site_conflict=', '.join(near) if near else 'No listed recognised site within 2 miles'
    if face.pass_terrain:
      face.launch_observation='Upper face appears large enough geometrically; surface, fences, rotor and ownership require field inspection.'
      face.landing_observation='DTM shows downslope continuation; actual emergency landing suitability requires aerial imagery and a site visit.'

def kml_escape(s):return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
def write_outputs(b,faces,stats):
    OUT.mkdir(parents=True,exist_ok=True);rows=[asdict(f) for f in faces];pd.DataFrame(rows).to_csv(OUT/'all_measured_candidates.csv',index=False)
    passed=sorted([f for f in faces if f.pass_terrain],key=lambda f:f.terrain_score,reverse=True)
    for i,f in enumerate(passed,1):f.reason=f'Rank {i} terrain-only. '+f.reason
    feats=[]
    for f in faces:
      if f.polygon_wkt:
        from shapely import wkt
        p=wkt.loads(f.polygon_wkt);p=shp_transform(lambda x,y,z=None: TO_WGS.transform(x,y),p);geom=mapping(p)
      else:geom=mapping(Point(f.longitude,f.latitude))
      prop=asdict(f);prop.pop('polygon_wkt',None);feats.append({'type':'Feature','geometry':geom,'properties':prop})
    (OUT/'candidates.geojson').write_text(json.dumps({'type':'FeatureCollection','features':feats},indent=2))
    parts=['<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Four Marks revised minimum-profile terrain analysis</name>']
    for f in faces:
      desc=kml_escape(f'{f.status}; {f.reason} Obstacles: {f.obstacle_observation} Airspace: {f.airspace_observation}');parts.append(f'<Placemark><name>{kml_escape(f.name)}</name><description>{desc}</description><Point><coordinates>{f.longitude},{f.latitude},0</coordinates></Point></Placemark>')
    parts.append('</Document></kml>');(OUT/'four_marks_candidates.kml').write_text(''.join(parts))
    m=folium.Map([FOUR_LAT,FOUR_LON],zoom_start=10,tiles=None,control_scale=True);folium.TileLayer('OpenStreetMap',name='OpenStreetMap').add_to(m);folium.TileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',attr='OpenTopoMap / OpenStreetMap contributors',name='Topographic contours').add_to(m);folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',attr='Esri World Imagery',name='Satellite imagery').add_to(m)
    folium.Circle([FOUR_LAT,FOUR_LON],radius=RADIUS_M,color='#2457c5',fill=False,dash_array='8 6',tooltip='30-mile search radius').add_to(m)
    layers={n:folium.FeatureGroup(name=n,show=(n not in {'Thermal trigger only','Rejected terrain','Aviation concerns','Protected or impractical land'})) for n in ['Likely ridge-soarable','Marginal — inspect carefully','Thermal trigger only','Rejected terrain','Existing flying sites','Aviation concerns','Protected or impractical land']}
    for g in layers.values():g.add_to(m)
    for nm,(lat,lon) in EXISTING_SITES.items():folium.CircleMarker([lat,lon],radius=5,color='green',fill=True,tooltip=f'{nm} — existing/reference site').add_to(layers['Existing flying sites'])
    for f in faces:
      popup=(f'<b>{f.name}</b><br>{f.status}<br>Terrain score {f.terrain_score:.0f}<br>Aspect {f.aspect_text} {f.aspect_deg:.0f}°<br>Sustained 120–200 m slope {f.representative_slope_deg:.1f}°<br>≥8° ridge {f.ridge_8deg_m:.0f} m; face {f.percent_face_8deg:.0f}%<br>Relief {f.vertical_relief_m:.0f} m / {f.vertical_relief_ft:.0f} ft<br>Ridge {f.ridge_length_m:.0f} m<br>{f.reason}<br>{f.obstacle_observation}<br>{f.airspace_observation}<br><a href="https://www.google.com/maps/search/?api=1&query={f.latitude},{f.longitude}" target="_blank">Open aerial map</a>')
      layer=layers.get(f.category,layers['Rejected terrain']);color={'Likely ridge-soarable':'red','Marginal — inspect carefully':'orange','Thermal trigger only':'lightblue','Rejected':'gray'}.get(f.category,'gray');folium.Marker([f.latitude,f.longitude],tooltip=f.name,popup=folium.Popup(popup,max_width=450),icon=folium.Icon(color=color)).add_to(layer)
      folium.Circle([f.latitude,f.longitude],radius=1000,color='blue',fill=False,weight=1,tooltip=f'{f.name}: aviation review zone').add_to(layers['Aviation concerns'])
    Fullscreen().add_to(m);MeasureControl().add_to(m);folium.LayerControl(collapsed=False).add_to(m);m.save(OUT/'interactive_map.html')
    stats['one_metre_verified_total']=len(faces);stats['likely_ridge_soarable']=sum(f.category=='Likely ridge-soarable' for f in faces);stats['marginal_candidates']=sum(f.category=='Marginal — inspect carefully' for f in faces);stats['thermal_trigger_only']=sum(f.category=='Thermal trigger only' for f in faces);stats['rejected']=sum(f.category=='Rejected' for f in faces);stats['passed_names']=[f.name for f in passed];(OUT/'filtering_summary.json').write_text(json.dumps(stats,indent=2))
    lines=['# Four Marks 30-mile revised minimum-profile paragliding terrain analysis','', '## Completion statement',f"The complete 30-mile circle was screened at 10 m using server-resampled cells from the same Environment Agency 1 m DTM. {len(faces)} locations were then downloaded from the original 1 m DTM and analysed on a 4 m averaged working grid to suppress one-metre banks and ditches.",'','## Whitewool benchmark',f"Representative sustained slope: **{b['representative_slope_deg']:.1f}°**. Robust maximum local slope: **{b['max_robust_slope_deg']:.1f}°**. Median local slope: **{b['median_local_slope_deg']:.1f}°**. Median 200 m drop: **{b['vertical_relief_m']:.1f} m ({b['vertical_relief_m']*3.28084:.0f} ft)**. Continuous ridge width: **{b['ridge_length_m']:.0f} m**. Dominant downslope aspect: **{aspect_name(b['aspect'])} ({b['aspect']:.0f}°)**.",'', 'Revised categories: likely ridge-soarable = sustained slope ≥9.5°, relief ≥30 m, ≥8° ridge ≥400 m and ≥30% face at 8°; marginal = slope ≥8°, relief ≥25 m, ≥8° ridge ≥300 m and ≥20% face at 8°; thermal-trigger only = slope ≥6°, relief ≥20 m and broad ridge ≥250 m.','','## Terrain-only shortlist']
    if passed:
      for i,f in enumerate(passed,1):lines += [f"### {i}. {f.name} — {f.category}",f"{f.reason} Terrain score {f.terrain_score:.0f}/100. Aspect {f.aspect_text} ({f.aspect_deg:.0f}°). Location {f.latitude:.6f}, {f.longitude:.6f}; {f.grid_ref}. Distance {f.distance_miles:.1f} miles.",f"Land/obstacle screen: {f.obstacle_observation}",f"Airspace screen: {f.airspace_observation}",'']
    else:lines += ['No new south-east to south-west face met the revised likely or marginal terrain thresholds.','']
    lines += ['## Reassessed named locations']
    for f in [x for x in faces if x.source=='Required reassessment']:lines += [f"- **{f.name}: {f.status}.** {f.reason}"]
    lines += ['','## Limitations','The DTM is bare earth and cannot establish current crops, fences, livestock, trees, buildings, ownership, permission or safe flying conditions. Automated OSM and aviation screening were deliberately omitted. Obstacles, land cover, protected land, access, ownership, current aviation charts, NOTAMs, aerodromes and local procedures must be checked manually for shortlisted terrain candidates.'];(OUT/'report.md').write_text('\n'.join(lines))

def main():
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'profiles').mkdir(exist_ok=True);log('Benchmarking Whitewool');b,wf,wtr,wres=benchmark_whitewool();log(json.dumps({k:b[k] for k in ['representative_slope_deg','vertical_relief_m','ridge_length_m','aspect']},indent=2))
    tiles=coarse_tiles();log(f'Coarse tiles: {len(tiles)}');allrows=[]
    with cf.ThreadPoolExecutor(max_workers=2) as ex:
      fut=[ex.submit(process_coarse,t,b) for t in tiles]
      for i,f in enumerate(cf.as_completed(fut),1):
        allrows.extend(f.result())
        if i%10==0:log(f'Processed coarse tiles {i}/{len(fut)}')
    prelim=dedup(allrows);log(f'Preliminary coarse components after dedup: {len(prelim)}');prelim=[r for r in prelim if r['coarse_local_slope']>=5.2 and r['coarse_relief_m']>=18.0 and r['coarse_width_m']>=120];log(f'Preliminary areas sent to 1m verification: {len(prelim)}')
    jobs=[(nearest_label(r['easting'],r['northing']),r['easting'],r['northing'],'Coarse-screen discovery') for r in prelim]
    for name,(lat,lon) in FORCED_WGS.items():e,n=TO_BNG.transform(lon,lat);jobs.append((name,e,n,'Required reassessment'))
    log(f'Exact verification jobs after 1.2 km clustering: {len(jobs)}')
    faces=[]
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
      futures=[ex.submit(exact_assess,j[0],j[1],j[2],b,j[3]) for j in jobs]
      for i,fu in enumerate(cf.as_completed(futures),1):
        try:faces.append(fu.result())
        except Exception as exn:log(f'Exact verification failed: {exn}')
        if i%5==0:log(f'1m verification {i}/{len(futures)}')
    final=[]
    for f in sorted(faces,key=lambda x:(x.source!='Required reassessment',x.terrain_score),reverse=True):
      if f.source!='Required reassessment' and any(q.source!='Required reassessment' and math.hypot(f.easting-q.easting,f.northing-q.northing)<400 for q in final):continue
      final.append(f)
    log(f'Skipping automated OSM and aviation checks for {len(final)} terrain candidates')
    for f in final:
      f.landcover_observation='Not automatically checked; inspect aerial imagery and site conditions manually.'
      f.obstacle_observation='Not automatically checked; inspect buildings, power lines, roads, railways, trees and fences manually.'
      f.protected_observation='Not automatically checked; confirm protected-land constraints using official records.'
      f.airspace_observation='Not automatically checked; manually review current aviation charts, NOTAMs, aerodromes and local procedures.'
      f.existing_site_conflict='Not automatically checked.'
      if f.pass_terrain:
        f.launch_observation='Terrain geometry appears potentially suitable; surface, fences, rotor, access and ownership require field inspection.'
        f.landing_observation='Terrain analysis only; actual emergency landing suitability requires aerial imagery and a site visit.'
    stats={'search_centre_bng':[FOUR_E,FOUR_N],'search_radius_m':RADIUS_M,'search_area_sq_km':math.pi*RADIUS_M**2/1e6,'coarse_resolution_m':10,'coarse_tile_count':len(tiles),'coarse_cells_processed_approx':sum(((t[2]-t[0])/10)*((t[3]-t[1])/10) for t in tiles),'raw_coarse_components':len(allrows),'preliminary_terrain_areas_after_dedup':len(prelim),'required_named_locations_verified':len(FORCED_WGS),'rejected_at_coarse_component_filter':max(0,len(allrows)-len(prelim))}
    write_outputs(b,final,stats);shutil.copy2(__file__,OUT/'run_analysis.py');log('COMPLETE '+str(OUT))
if __name__=='__main__':main()
