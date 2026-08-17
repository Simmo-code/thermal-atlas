import json, math, time, random
from collections import defaultdict
import pandas as pd
import numpy as np
import requests
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import transform
from pyproj import Transformer
from scipy.stats import fisher_exact, mannwhitneyu
import statsmodels.formula.api as smf

POINTS='analysis/thermal_trigger_points_min.csv'
OUT='analysis/thermal_trigger_metrics.csv'
SUMMARY='analysis/thermal_trigger_summary.json'
MERE='analysis/mere_thermal_trigger_metrics.csv'

RADIUS=900
PLACE_RADIUS=3000
MAJOR={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link'}
AGRI={'farmland','meadow','grass','orchard','vineyard'}
URBAN={'residential','industrial','commercial','retail'}
ENDPOINTS=['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter']

to_bng=Transformer.from_crs('EPSG:4326','EPSG:27700',always_xy=True)

def project_geom(g):
    return transform(to_bng.transform,g)

def overpass(query):
    last=None
    for attempt in range(6):
        for url in ENDPOINTS:
            try:
                r=requests.post(url,data={'data':query},timeout=180,headers={'User-Agent':'thermal-trigger-study/1.0'})
                if r.status_code==200:
                    return r.json()
                last=f'{url} status {r.status_code}: {r.text[:200]}'
            except Exception as e:
                last=repr(e)
        time.sleep(5+attempt*5)
    raise RuntimeError(last)

def make_query(batch):
    clauses=[]
    for _,p in batch.iterrows():
        lat=float(p.lat); lon=float(p.lon)
        clauses += [
            f'way(around:{RADIUS},{lat},{lon})["highway"];',
            f'way(around:{RADIUS},{lat},{lon})["landuse"~"^(farmland|meadow|grass|orchard|vineyard|residential|industrial|commercial|retail)$"];',
            f'way(around:{RADIUS},{lat},{lon})["natural"="wood"];',
            f'way(around:{RADIUS},{lat},{lon})["landuse"="forest"];',
            f'node(around:{PLACE_RADIUS},{lat},{lon})["place"~"^(city|town|village)$"];',
        ]
    return '[out:json][timeout:150];(' + ''.join(clauses) + ');out geom;'

def road_signature(tags,wid):
    return (tags.get('ref') or tags.get('name') or f'__{wid}', tags.get('highway',''))

def parse_elements(elements):
    roads=[]; major=[]; agri=[]; urban=[]; wood=[]; places=[]
    node_ways=defaultdict(set); node_sigs=defaultdict(set); node_major=defaultdict(set); node_xy={}
    roundabouts=[]; major_roundabouts=[]
    seen=set()
    for e in elements:
        key=(e.get('type'),e.get('id'))
        if key in seen: continue
        seen.add(key)
        tags=e.get('tags',{})
        if e.get('type')=='node':
            if tags.get('place') in {'city','town','village'} and 'lat' in e:
                places.append((project_geom(Point(e['lon'],e['lat'])),tags.get('place')))
            continue
        geom=e.get('geometry') or []
        if len(geom)<2: continue
        coords=[(q['lon'],q['lat']) for q in geom if 'lat' in q and 'lon' in q]
        if len(coords)<2: continue
        if 'highway' in tags:
            try: ls=project_geom(LineString(coords))
            except Exception: continue
            roads.append((ls,tags,e.get('id')))
            is_major=tags.get('highway') in MAJOR
            if is_major: major.append((ls,tags,e.get('id')))
            sig=road_signature(tags,e.get('id'))
            for lon,lat in coords:
                nk=(round(lat,7),round(lon,7))
                node_xy[nk]=(lon,lat)
                node_ways[nk].add(e.get('id'))
                node_sigs[nk].add(sig)
                if is_major: node_major[nk].add(e.get('id'))
            if tags.get('junction')=='roundabout':
                rp=ls.centroid
                roundabouts.append(rp)
                if is_major: major_roundabouts.append(rp)
            continue
        closed=(coords[0]==coords[-1]) or (abs(coords[0][0]-coords[-1][0])<1e-7 and abs(coords[0][1]-coords[-1][1])<1e-7)
        if not closed or len(coords)<4: continue
        try:
            poly=project_geom(Polygon(coords))
            if not poly.is_valid: poly=poly.buffer(0)
            if poly.is_empty: continue
        except Exception: continue
        lu=tags.get('landuse')
        if lu in AGRI: agri.append((poly,lu,e.get('id')))
        if lu in URBAN: urban.append((poly,lu,e.get('id')))
        if tags.get('natural')=='wood' or lu=='forest': wood.append((poly,'wood',e.get('id')))
    junctions=[]; major_junctions=[]
    for nk,wids in node_ways.items():
        # Require >=3 way objects, or >=2 road signatures; this removes many harmless geometry splits.
        if len(wids)>=3 or len(node_sigs[nk])>=2:
            lon,lat=node_xy[nk]; junctions.append(project_geom(Point(lon,lat)))
        if len(node_major[nk])>=2:
            lon,lat=node_xy[nk]; major_junctions.append(project_geom(Point(lon,lat)))
    junctions += roundabouts
    major_junctions += major_roundabouts
    return roads,major,agri,urban,wood,places,junctions,major_junctions

def mindist(pt, geoms, default=99999.0):
    if not geoms: return default
    return float(min(pt.distance(g) for g in geoms))

def poly_metrics(pt, polys):
    if not polys: return 99999.0,False,False,99999.0
    best=99999.; inside=False; big_near=False; best_area=0.
    for poly,kind,oid in polys:
        d=float(pt.distance(poly.boundary)) if pt.within(poly) else float(pt.distance(poly))
        if d<best:
            best=d; best_area=float(poly.area)
        if pt.within(poly): inside=True
        if poly.area>=100000 and pt.distance(poly)<=300: big_near=True
    return best,inside,big_near,best_area

def odds_binary(df,col):
    t=df[df.k=='t'][col].astype(bool); c=df[df.k=='c'][col].astype(bool)
    a=int(t.sum()); b=int((~t).sum()); cc=int(c.sum()); d=int((~c).sum())
    or_raw,p=fisher_exact([[a,b],[cc,d]])
    or_h=((a+0.5)*(d+0.5))/((b+0.5)*(cc+0.5))
    return {'thermal_pct':100*a/max(1,len(t)),'control_pct':100*cc/max(1,len(c)),'odds_ratio':float(or_h),'fisher_p':float(p),'n_thermal':len(t),'n_control':len(c)}

def fixed_effect_or(df,col):
    z=df.copy(); z['y']=(z.k=='t').astype(int)
    try:
        model=smf.logit(f'y ~ {col} + C(f)',data=z).fit(disp=0,maxiter=200)
        beta=float(model.params[col]); se=float(model.bse[col]); p=float(model.pvalues[col])
        return {'or_flight_adjusted':math.exp(beta),'ci95_low':math.exp(beta-1.96*se),'ci95_high':math.exp(beta+1.96*se),'p_flight_adjusted':p}
    except Exception as e:
        return {'or_flight_adjusted':None,'ci95_low':None,'ci95_high':None,'p_flight_adjusted':None,'error':str(e)}

def continuous(df,col):
    t=df[df.k=='t'][col].replace(99999,np.nan).dropna(); c=df[df.k=='c'][col].replace(99999,np.nan).dropna()
    if not len(t) or not len(c): return {}
    try: p=float(mannwhitneyu(t,c,alternative='two-sided').pvalue)
    except Exception: p=None
    return {'thermal_median_m':float(t.median()),'control_median_m':float(c.median()),'mw_p':p}

df=pd.read_csv(POINTS)
# Primary analysis uses only the robust all-flight background set. Downsample to 3 controls per thermal within each flight.
base=df[df.g=='a'].copy()
parts=[]
for f,g in base.groupby('f'):
    t=g[g.k=='t']; c=g[g.k=='c']
    n=min(len(c),3*len(t))
    c=c.sample(n=n,random_state=1000+int(f)) if len(c)>n else c
    parts.append(pd.concat([t,c]))
work=pd.concat(parts,ignore_index=True)
work['pid']=range(len(work))

all_elems={}
BATCH=8
for s in range(0,len(work),BATCH):
    batch=work.iloc[s:s+BATCH]
    q=make_query(batch)
    data=overpass(q)
    for e in data.get('elements',[]): all_elems[(e.get('type'),e.get('id'))]=e
    print('batch',s,'/',len(work),'elements total',len(all_elems),flush=True)
    time.sleep(1.0)

roads,major,agri,urban,wood,places,junctions,major_junctions=parse_elements(list(all_elems.values()))
road_geoms=[x[0] for x in roads]; major_geoms=[x[0] for x in major]
agri_polys=agri; urban_polys=urban; wood_polys=wood
place_geoms=[x[0] for x in places]

metrics=[]
for _,r in work.iterrows():
    pt=project_geom(Point(float(r.lon),float(r.lat)))
    da,ai,abig,aarea=poly_metrics(pt,agri_polys)
    du,ui,ubig,uarea=poly_metrics(pt,urban_polys)
    dw,wi,wbig,warea=poly_metrics(pt,wood_polys)
    m=dict(r)
    m.update({
        'd_any_road_m':mindist(pt,road_geoms),
        'd_major_road_m':mindist(pt,major_geoms),
        'd_junction_m':mindist(pt,junctions),
        'd_major_junction_m':mindist(pt,major_junctions),
        'd_agri_edge_m':da,'agri_inside':int(ai),'big_agri_near300':int(abig),
        'd_urban_edge_m':du,'urban_inside':int(ui),
        'd_wood_edge_m':dw,'wood_inside':int(wi),
        'd_place_m':mindist(pt,place_geoms),
    })
    m['junction_300']=int(m['d_junction_m']<=300)
    m['junction_500']=int(m['d_junction_m']<=500)
    m['major_junction_500']=int(m['d_major_junction_m']<=500)
    m['major_road_300']=int(m['d_major_road_m']<=300)
    m['any_road_150']=int(m['d_any_road_m']<=150)
    m['agri_edge_300']=int(m['d_agri_edge_m']<=300)
    m['wood_edge_300']=int(m['d_wood_edge_m']<=300)
    m['urban_near500']=int(m['urban_inside'] or m['d_urban_edge_m']<=500)
    m['place_near2000']=int(m['d_place_m']<=2000)
    m['road_agri_boundary']=int(m['d_any_road_m']<=150 and m['d_agri_edge_m']<=300)
    m['surface_boundary_300']=int(min(m['d_agri_edge_m'],m['d_wood_edge_m'],m['d_urban_edge_m'])<=300)
    metrics.append(m)
res=pd.DataFrame(metrics)
res.to_csv(OUT,index=False)
res[(res.f==4)&(res.k=='t')].to_csv(MERE,index=False)

binary=['junction_300','junction_500','major_junction_500','major_road_300','any_road_150','agri_inside','agri_edge_300','big_agri_near300','wood_edge_300','urban_inside','urban_near500','place_near2000','road_agri_boundary','surface_boundary_300']
cont=['d_junction_m','d_major_junction_m','d_major_road_m','d_any_road_m','d_agri_edge_m','d_wood_edge_m','d_urban_edge_m','d_place_m']
summary={'n_thermal':int((res.k=='t').sum()),'n_control':int((res.k=='c').sum()),'binary':{},'continuous':{},'by_flight':{},'notes':[
    'Thermals: gain >=150 m and duration >=90 s from the prior IGC detection pass.',
    'Controls: non-thermal gliding/searching points sampled within the same flight; three controls per thermal.',
    'OSM way polygons are used for farmland/urban/woodland; multipolygon relations may be under-counted.',
    'Ground feature position is the thermal encounter position, not a fully wind-backtracked source; interpret high-entry thermals cautiously.'
]}
for col in binary:
    s=odds_binary(res,col); s.update(fixed_effect_or(res,col)); summary['binary'][col]=s
for col in cont: summary['continuous'][col]=continuous(res,col)
for f,g in res.groupby('f'):
    summary['by_flight'][str(int(f))]={'n_thermal':int((g.k=='t').sum()),'n_control':int((g.k=='c').sum())}
with open(SUMMARY,'w') as fh: json.dump(summary,fh,indent=2)
print(json.dumps(summary,indent=2))
