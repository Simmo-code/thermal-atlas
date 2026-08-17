import json,time,math
from collections import defaultdict
import pandas as pd
import requests
from shapely.geometry import Point,LineString,Polygon
from shapely.ops import transform
from pyproj import Transformer
from scipy.stats import fisher_exact,mannwhitneyu

INP='analysis/thermal_trigger_points_min.csv'
OUT='analysis/thermal_trigger_fast_metrics.csv'
SUM='analysis/thermal_trigger_fast_summary.json'
R=700; PR=2200
MAJOR={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link'}
AGRI={'farmland','meadow','grass','orchard','vineyard'}; URBAN={'residential','industrial','commercial','retail'}
EPS=['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter']
tr=Transformer.from_crs('EPSG:4326','EPSG:27700',always_xy=True)
def P(g): return transform(tr.transform,g)
def qbatch(b):
  x=[]
  for _,p in b.iterrows():
    a=float(p.lat);o=float(p.lon)
    x += [f'way(around:{R},{a},{o})["highway"];',f'way(around:{R},{a},{o})["landuse"~"^(farmland|meadow|grass|orchard|vineyard|residential|industrial|commercial|retail|forest)$"];',f'way(around:{R},{a},{o})["natural"="wood"];',f'node(around:{PR},{a},{o})["place"~"^(city|town|village)$"];']
  return '[out:json][timeout:90];('+''.join(x)+');out geom;'
def get(q):
  err=''
  for k in range(3):
    for u in EPS:
      try:
        r=requests.post(u,data={'data':q},timeout=100,headers={'User-Agent':'thermal-trigger-study/1.0'})
        if r.status_code==200:return r.json()
        err=f'{r.status_code} {r.text[:120]}'
      except Exception as e:err=str(e)
    time.sleep(3+4*k)
  raise RuntimeError(err)
def md(pt,gs): return min([pt.distance(g) for g in gs],default=99999.)
def polyinfo(pt,ps):
  d=99999.;inside=False;big=False
  for p in ps:
    dd=pt.distance(p.boundary) if pt.within(p) else pt.distance(p)
    d=min(d,dd);inside|=pt.within(p);big|=(p.area>=100000 and pt.distance(p)<=300)
  return float(d),inside,big

d=pd.read_csv(INP); d=d[d.g=='a'].copy()
# one deterministic same-flight control per thermal, sampled without replacement where possible
parts=[]
for f,g in d.groupby('f'):
  t=g[g.k=='t']; c=g[g.k=='c'].sample(frac=1,random_state=700+int(f))
  c=c.iloc[:min(len(t),len(c))]
  parts.append(pd.concat([t,c]))
w=pd.concat(parts,ignore_index=True)
E={}
for s in range(0,len(w),12):
  z=get(qbatch(w.iloc[s:s+12]));
  for e in z.get('elements',[]):E[(e.get('type'),e.get('id'))]=e
  print('batch',s,'of',len(w),'features',len(E),flush=True);time.sleep(.5)
roads=[];major=[];ag=[];ur=[];wo=[];places=[];nodeways=defaultdict(set);nodemajor=defaultdict(set);xy={}
for e in E.values():
  tags=e.get('tags',{})
  if e.get('type')=='node':
    if tags.get('place') in {'city','town','village'} and 'lat' in e:places.append(P(Point(e['lon'],e['lat'])))
    continue
  gg=e.get('geometry') or []; co=[(x['lon'],x['lat']) for x in gg if 'lat'in x and 'lon'in x]
  if len(co)<2:continue
  if 'highway' in tags:
    try:l=P(LineString(co))
    except:continue
    roads.append(l); mj=tags.get('highway') in MAJOR
    if mj:major.append(l)
    for lon,lat in co:
      n=(round(lat,7),round(lon,7));xy[n]=(lon,lat);nodeways[n].add(e.get('id'))
      if mj:nodemajor[n].add(e.get('id'))
    continue
  if len(co)>=4 and abs(co[0][0]-co[-1][0])<1e-7 and abs(co[0][1]-co[-1][1])<1e-7:
    try:p=P(Polygon(co));p=p if p.is_valid else p.buffer(0)
    except:continue
    if p.is_empty:continue
    lu=tags.get('landuse')
    if lu in AGRI:ag.append(p)
    if lu in URBAN:ur.append(p)
    if lu=='forest' or tags.get('natural')=='wood':wo.append(p)
junc=[P(Point(*xy[n])) for n,v in nodeways.items() if len(v)>=3]
mjunc=[P(Point(*xy[n])) for n,v in nodemajor.items() if len(v)>=2]
rows=[]
for _,r in w.iterrows():
  pt=P(Point(float(r.lon),float(r.lat))); da,ai,big=polyinfo(pt,ag);du,ui,_=polyinfo(pt,ur);dw,wi,_=polyinfo(pt,wo)
  x=dict(r);x.update(d_junc=md(pt,junc),d_mjunc=md(pt,mjunc),d_road=md(pt,roads),d_major=md(pt,major),d_agri=da,d_urban=du,d_wood=dw,d_place=md(pt,places),agri_inside=int(ai),urban_inside=int(ui),big_agri=int(big))
  x.update(junction_300=int(x['d_junc']<=300),junction_500=int(x['d_junc']<=500),major_junction_500=int(x['d_mjunc']<=500),major_road_300=int(x['d_major']<=300),any_road_150=int(x['d_road']<=150),agri_edge_300=int(da<=300),wood_edge_300=int(dw<=300),urban_near500=int(ui or du<=500),place_near2000=int(x['d_place']<=2000),road_agri=int(x['d_road']<=150 and da<=300),surface_boundary=int(min(da,du,dw)<=300))
  rows.append(x)
r=pd.DataFrame(rows);r.to_csv(OUT,index=False)
def binstat(c):
  t=r[r.k=='t'][c].astype(bool);q=r[r.k=='c'][c].astype(bool);a=int(t.sum());b=len(t)-a;cc=int(q.sum());dd=len(q)-cc
  o,p=fisher_exact([[a,b],[cc,dd]]);oh=((a+.5)*(dd+.5))/((b+.5)*(cc+.5))
  return {'thermal_pct':round(100*a/len(t),1),'control_pct':round(100*cc/len(q),1),'odds_ratio':round(float(oh),3),'p':round(float(p),5),'counts':[a,b,cc,dd]}
def cont(c):
  t=r[r.k=='t'][c].replace(99999,float('nan')).dropna();q=r[r.k=='c'][c].replace(99999,float('nan')).dropna();p=mannwhitneyu(t,q).pvalue if len(t) and len(q) else None
  return {'thermal_median_m':round(float(t.median()),1) if len(t) else None,'control_median_m':round(float(q.median()),1) if len(q) else None,'p':round(float(p),5) if p is not None else None}
B=['junction_300','junction_500','major_junction_500','major_road_300','any_road_150','agri_inside','agri_edge_300','big_agri','wood_edge_300','urban_inside','urban_near500','place_near2000','road_agri','surface_boundary']
C=['d_junc','d_mjunc','d_road','d_major','d_agri','d_urban','d_wood','d_place']
s={'n_thermal':int((r.k=='t').sum()),'n_control':int((r.k=='c').sum()),'binary':{c:binstat(c) for c in B},'continuous':{c:cont(c) for c in C}}
with open(SUM,'w') as f:json.dump(s,f,indent=2)
print(json.dumps(s,indent=2))
