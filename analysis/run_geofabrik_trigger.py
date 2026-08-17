import json, glob, math
from collections import defaultdict
import pandas as pd
from shapely.geometry import shape, Point, LineString, MultiLineString, Polygon, MultiPolygon
from shapely.ops import transform
from pyproj import Transformer
from scipy.stats import fisher_exact, mannwhitneyu

PTS='analysis/thermal_trigger_matched.csv'
OUT='analysis/thermal_trigger_geofabrik_metrics.csv'
SUM='analysis/thermal_trigger_geofabrik_summary.json'
MAJOR={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link'}
AGRI={'farmland','meadow','grass','orchard','vineyard'}
URBAN={'residential','industrial','commercial','retail'}
tr=Transformer.from_crs('EPSG:4326','EPSG:27700',always_xy=True)
def P(g): return transform(tr.transform,g)

roads=[]; ag=[]; urban=[]; woods=[]; places=[]; seen=set(); roundabouts=[]
for fn in glob.glob('/tmp/osm/*-subset.geojson'):
    with open(fn) as fh: data=json.load(fh)
    for i,ft in enumerate(data.get('features',[])):
        props=ft.get('properties') or {}; fid=str(ft.get('id') or props.get('@id') or (fn,i))
        key=(fid,ft.get('geometry',{}).get('type'))
        if key in seen: continue
        seen.add(key)
        try:g=shape(ft['geometry'])
        except:continue
        if g.is_empty:continue
        h=props.get('highway')
        if h and g.geom_type in ('LineString','MultiLineString'):
            gp=P(g); roads.append((gp,props,fid))
            if props.get('junction')=='roundabout':roundabouts.append((gp.centroid,h in MAJOR))
            continue
        lu=props.get('landuse'); nat=props.get('natural')
        if g.geom_type in ('Polygon','MultiPolygon'):
            gp=P(g)
            if lu in AGRI: ag.append(gp)
            if lu in URBAN: urban.append(gp)
            if lu=='forest' or nat=='wood': woods.append(gp)
        if props.get('place') in {'city','town','village'} and g.geom_type=='Point':places.append(P(g))
print('features roads',len(roads),'agri',len(ag),'urban',len(urban),'woods',len(woods),'places',len(places))

# Junctions from shared road vertices. Named/ref roads use signature; unnamed nodes require >=3 ways.
node_fids=defaultdict(set); node_sigs=defaultdict(set); node_major=defaultdict(set); node_xy={}
for g,p,fid in roads:
    sig=p.get('ref') or p.get('name') or None
    geoms=[g] if g.geom_type=='LineString' else list(g.geoms)
    for ls in geoms:
        for x,y in ls.coords:
            nk=(round(x,1),round(y,1)); node_xy[nk]=(x,y); node_fids[nk].add(fid)
            if sig:node_sigs[nk].add(sig)
            if p.get('highway') in MAJOR: node_major[nk].add(fid)
junc=[]; mjunc=[]
for nk,fids in node_fids.items():
    if len(fids)>=3 or len(node_sigs[nk])>=2:junc.append(Point(*node_xy[nk]))
    if len(node_major[nk])>=2:mjunc.append(Point(*node_xy[nk]))
for pt,ismajor in roundabouts:
    junc.append(pt)
    if ismajor:mjunc.append(pt)
majorroads=[g for g,p,f in roads if p.get('highway') in MAJOR]; allroads=[g for g,p,f in roads]

def md(pt,gs):return float(min((pt.distance(g) for g in gs),default=99999))
def pinfo(pt,ps):
    d=99999.; inside=False; big=False
    for p in ps:
        dd=pt.distance(p.boundary) if pt.within(p) else pt.distance(p)
        if dd<d:d=float(dd)
        if pt.within(p):inside=True
        if p.area>=100000 and pt.distance(p)<=300:big=True
    return d,inside,big

pts=pd.read_csv(PTS); rows=[]
for _,r in pts.iterrows():
    pt=P(Point(float(r.lon),float(r.lat))); da,ai,big=pinfo(pt,ag);du,ui,_=pinfo(pt,urban);dw,wi,_=pinfo(pt,woods)
    x=dict(r);x.update(d_junction_m=md(pt,junc),d_major_junction_m=md(pt,mjunc),d_any_road_m=md(pt,allroads),d_major_road_m=md(pt,majorroads),d_agri_edge_m=da,d_urban_edge_m=du,d_wood_edge_m=dw,d_place_m=md(pt,places),agri_inside=int(ai),urban_inside=int(ui),big_agri_near300=int(big))
    x.update(junction_300=int(x['d_junction_m']<=300),junction_500=int(x['d_junction_m']<=500),major_junction_500=int(x['d_major_junction_m']<=500),major_road_300=int(x['d_major_road_m']<=300),any_road_150=int(x['d_any_road_m']<=150),agri_edge_300=int(da<=300),wood_edge_300=int(dw<=300),urban_near500=int(ui or du<=500),place_near2000=int(x['d_place_m']<=2000),road_agri_boundary=int(x['d_any_road_m']<=150 and da<=300),surface_boundary_300=int(min(da,du,dw)<=300))
    rows.append(x)
r=pd.DataFrame(rows); r.to_csv(OUT,index=False)

def binstat(df,c):
    t=df[df.k=='t'][c].astype(bool); q=df[df.k=='c'][c].astype(bool); a=int(t.sum()); b=len(t)-a; cc=int(q.sum()); dd=len(q)-cc
    _,p=fisher_exact([[a,b],[cc,dd]]); oh=((a+.5)*(dd+.5))/((b+.5)*(cc+.5))
    return {'thermal_pct':round(100*a/max(1,len(t)),1),'control_pct':round(100*cc/max(1,len(q)),1),'odds_ratio':round(float(oh),2),'p':round(float(p),4),'counts':[a,b,cc,dd]}
def cont(df,c):
    t=df[df.k=='t'][c].replace(99999,float('nan')).dropna();q=df[df.k=='c'][c].replace(99999,float('nan')).dropna();p=mannwhitneyu(t,q).pvalue if len(t) and len(q) else None
    return {'thermal_median_m':round(float(t.median()),1) if len(t) else None,'control_median_m':round(float(q.median()),1) if len(q) else None,'p':round(float(p),4) if p is not None else None}
B=['junction_300','junction_500','major_junction_500','major_road_300','any_road_150','agri_inside','agri_edge_300','big_agri_near300','wood_edge_300','urban_inside','urban_near500','place_near2000','road_agri_boundary','surface_boundary_300']
C=['d_junction_m','d_major_junction_m','d_any_road_m','d_major_road_m','d_agri_edge_m','d_wood_edge_m','d_urban_edge_m','d_place_m']
def pack(df):return {'n_thermal':int((df.k=='t').sum()),'n_control':int((df.k=='c').sum()),'binary':{c:binstat(df,c) for c in B},'continuous':{c:cont(df,c) for c in C}}
s={'all':pack(r),'low_entry':pack(r[r.low==1]),'by_flight':{},'mere_thermals':[]}
for f,g in r.groupby('f'):s['by_flight'][str(int(f))]=pack(g)
for _,z in r[(r.f==4)&(r.k=='t')].iterrows():
    s['mere_thermals'].append({k:(round(float(z[k]),1) if k.startswith('d_') else int(z[k]) if k in ['e','low'] else float(z[k]) if k in ['lat','lon','alt'] else z[k]) for k in ['e','lat','lon','alt','low','d_junction_m','d_major_junction_m','d_any_road_m','d_major_road_m','d_agri_edge_m','d_wood_edge_m','d_urban_edge_m','d_place_m']})
with open(SUM,'w') as fh:json.dump(s,fh,indent=2)
print(json.dumps(s,indent=2))
