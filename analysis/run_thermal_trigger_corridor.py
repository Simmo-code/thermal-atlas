import json, time, math
from collections import defaultdict
import pandas as pd
import requests
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import transform
from pyproj import Transformer
from scipy.stats import fisher_exact, mannwhitneyu

INP='analysis/thermal_trigger_points_min.csv'
OUT='analysis/thermal_trigger_corridor_metrics.csv'
SUM='analysis/thermal_trigger_corridor_summary.json'
R=900
PR=3000
ROUTES={
0:'51.37308,-1.85897,51.39488,-1.81300,51.41165,-1.76195,51.43158,-1.71385,51.43897,-1.65727,51.46812,-1.62315,51.49803,-1.59083,51.52422,-1.55090,51.55042,-1.51125,51.58108,-1.48082,51.60352,-1.43545,51.62987,-1.39597,51.65998,-1.36402,51.68400,-1.32058,51.71053,-1.28127,51.73332,-1.23627,51.76650,-1.21322,51.78802,-1.16637,51.80380,-1.11393,51.82755,-1.07005,51.85023,-1.02470,51.87013,-0.97603,51.89702,-0.93703,51.92170,-0.89460,51.94970,-0.85772,51.97803,-0.82158,52.01328,-0.80975,52.04582,-0.78477,52.07950,-0.76377,52.06890,-0.79667',
1:'51.51782,-1.70052,51.49780,-1.65225,51.47473,-1.60777,51.44637,-1.57220,51.41862,-1.53542,51.39742,-1.48877,51.36487,-1.46413,51.35833,-1.48363',
2:'50.95943,-0.86990,50.95970,-0.86907',
3:'51.35890,-1.48063,51.32533,-1.45935,51.29727,-1.42310,51.28015,-1.37243,51.24792,-1.34673,51.23827,-1.29137,51.21575,-1.24647,51.19447,-1.19997,51.16795,-1.16117,51.14583,-1.11588,51.12215,-1.07272,51.08832,-1.05320,51.06017,-1.01740,51.02755,-0.99320,50.99787,-0.96088,50.96842,-0.92790,50.93275,-0.92017,50.92710,-0.86378,50.92952,-0.80682,50.92690,-0.74982,50.89713,-0.71768,50.88440,-0.66422,50.88288,-0.60718,50.89137,-0.55170,50.88455,-0.49570,50.88467,-0.43855,50.89020,-0.38215,50.89670,-0.32593,50.88475,-0.27200,50.88007,-0.21527,50.88072,-0.15817,50.89098,-0.10340,50.91877,-0.06713,50.92692,-0.06757',
4:'51.10852,-2.27075,51.14225,-2.25062,51.17825,-2.25417,51.21237,-2.23567,51.24595,-2.21470,51.27990,-2.19557,51.31583,-2.19118,51.35027,-2.17438,51.38630,-2.17273,51.42205,-2.16610,51.45750,-2.15628,51.49212,-2.14023,51.52712,-2.12613,51.56232,-2.11405,51.59837,-2.11053,51.63318,-2.12588,51.66843,-2.11423,51.70438,-2.11112,51.74007,-2.10318,51.77303,-2.07983,51.80792,-2.06520,51.84390,-2.06208,51.87915,-2.05033,51.91503,-2.05482,51.95087,-2.04838,51.98658,-2.04035,52.01343,-2.07930,52.00358,-2.10612'
}
ENDPOINTS=['https://overpass.private.coffee/api/interpreter','https://overpass-api.de/api/interpreter']
MAJOR={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link'}
AGRI={'farmland','meadow','grass','orchard','vineyard'}
URBAN={'residential','industrial','commercial','retail'}
tr=Transformer.from_crs('EPSG:4326','EPSG:27700',always_xy=True)
def P(g): return transform(tr.transform,g)
def fetch(q):
  err=''
  for attempt in range(4):
    for u in ENDPOINTS:
      try:
        r=requests.post(u,data={'data':q},timeout=180,headers={'User-Agent':'thermal-trigger-study/1.0'})
        if r.status_code==200:return r.json()
        err=f'{u} {r.status_code} {r.text[:200]}'
      except Exception as e:err=repr(e)
    time.sleep(4+5*attempt)
  raise RuntimeError(err)
def query(route):
  return f'''[out:json][timeout:150];(
way(around:{R},{route})["highway"];
way(around:{R},{route})["landuse"~"^(farmland|meadow|grass|orchard|vineyard|residential|industrial|commercial|retail|forest)$"];
way(around:{R},{route})["natural"="wood"];
node(around:{PR},{route})["place"~"^(city|town|village)$"];
);out geom;'''
def md(pt,geoms): return float(min((pt.distance(g) for g in geoms),default=99999))
def polyinfo(pt,ps):
  d=99999.;inside=False;big=False
  for p in ps:
    dd=pt.distance(p.boundary) if pt.within(p) else pt.distance(p)
    d=min(d,float(dd));inside=inside or pt.within(p);big=big or (p.area>=100000 and pt.distance(p)<=300)
  return d,inside,big

df=pd.read_csv(INP); df=df[df.g=='a'].copy()
# keep 3 deterministic controls per thermal in each flight
parts=[]
for f,g in df.groupby('f'):
  t=g[g.k=='t']; c=g[g.k=='c']; n=min(len(c),3*len(t)); c=c.sample(n=n,random_state=3000+int(f)) if len(c)>n else c
  parts.append(pd.concat([t,c]))
work=pd.concat(parts,ignore_index=True)
rows=[]
for f,gp in work.groupby('f'):
  data=fetch(query(ROUTES[int(f)])); E=data.get('elements',[]);print('flight',f,'features',len(E),flush=True)
  roads=[];major=[];ag=[];ur=[];wo=[];places=[];nodeways=defaultdict(set);nodemajor=defaultdict(set);xy={};roundabouts=[];mround=[]
  for e in E:
    tags=e.get('tags',{})
    if e.get('type')=='node':
      if tags.get('place') in {'city','town','village'} and 'lat'in e:places.append(P(Point(e['lon'],e['lat'])))
      continue
    gg=e.get('geometry') or []; co=[(x['lon'],x['lat']) for x in gg if 'lat'in x and 'lon'in x]
    if len(co)<2:continue
    if 'highway'in tags:
      try:l=P(LineString(co))
      except:continue
      roads.append(l);maj=tags.get('highway') in MAJOR
      if maj:major.append(l)
      for lon,lat in co:
        n=(round(lat,7),round(lon,7));xy[n]=(lon,lat);nodeways[n].add(e.get('id'))
        if maj:nodemajor[n].add(e.get('id'))
      if tags.get('junction')=='roundabout':
        roundabouts.append(l.centroid)
        if maj:mround.append(l.centroid)
      continue
    if len(co)>=4 and abs(co[0][0]-co[-1][0])<1e-7 and abs(co[0][1]-co[-1][1])<1e-7:
      try:p=P(Polygon(co));p=p if p.is_valid else p.buffer(0)
      except:continue
      if p.is_empty:continue
      lu=tags.get('landuse')
      if lu in AGRI:ag.append(p)
      if lu in URBAN:ur.append(p)
      if lu=='forest' or tags.get('natural')=='wood':wo.append(p)
  junc=[P(Point(*xy[n])) for n,v in nodeways.items() if len(v)>=3]+roundabouts
  mjunc=[P(Point(*xy[n])) for n,v in nodemajor.items() if len(v)>=2]+mround
  for _,r in gp.iterrows():
    pt=P(Point(float(r.lon),float(r.lat)));da,ai,big=polyinfo(pt,ag);du,ui,_=polyinfo(pt,ur);dw,wi,_=polyinfo(pt,wo)
    x=dict(r);x.update(d_junction_m=md(pt,junc),d_major_junction_m=md(pt,mjunc),d_any_road_m=md(pt,roads),d_major_road_m=md(pt,major),d_agri_edge_m=da,d_urban_edge_m=du,d_wood_edge_m=dw,d_place_m=md(pt,places),agri_inside=int(ai),urban_inside=int(ui),big_agri_near300=int(big))
    x.update(junction_300=int(x['d_junction_m']<=300),junction_500=int(x['d_junction_m']<=500),major_junction_500=int(x['d_major_junction_m']<=500),major_road_300=int(x['d_major_road_m']<=300),any_road_150=int(x['d_any_road_m']<=150),agri_edge_300=int(da<=300),wood_edge_300=int(dw<=300),urban_near500=int(ui or du<=500),place_near2000=int(x['d_place_m']<=2000),road_agri_boundary=int(x['d_any_road_m']<=150 and da<=300),surface_boundary_300=int(min(da,du,dw)<=300))
    rows.append(x)
  time.sleep(1)
r=pd.DataFrame(rows);r.to_csv(OUT,index=False)
def bs(c):
 t=r[r.k=='t'][c].astype(bool);q=r[r.k=='c'][c].astype(bool);a=int(t.sum());b=len(t)-a;cc=int(q.sum());dd=len(q)-cc;o,p=fisher_exact([[a,b],[cc,dd]]);oh=((a+.5)*(dd+.5))/((b+.5)*(cc+.5));return {'thermal_pct':round(100*a/len(t),1),'control_pct':round(100*cc/len(q),1),'odds_ratio':round(float(oh),2),'p':round(float(p),4),'counts':[a,b,cc,dd]}
def cs(c):
 t=r[r.k=='t'][c].replace(99999,float('nan')).dropna();q=r[r.k=='c'][c].replace(99999,float('nan')).dropna();p=mannwhitneyu(t,q).pvalue if len(t) and len(q) else None;return {'thermal_median_m':round(float(t.median()),1) if len(t) else None,'control_median_m':round(float(q.median()),1) if len(q) else None,'p':round(float(p),4) if p is not None else None}
B=['junction_300','junction_500','major_junction_500','major_road_300','any_road_150','agri_inside','agri_edge_300','big_agri_near300','wood_edge_300','urban_inside','urban_near500','place_near2000','road_agri_boundary','surface_boundary_300']
C=['d_junction_m','d_major_junction_m','d_any_road_m','d_major_road_m','d_agri_edge_m','d_wood_edge_m','d_urban_edge_m','d_place_m']
s={'n_thermal':int((r.k=='t').sum()),'n_control':int((r.k=='c').sum()),'binary':{c:bs(c) for c in B},'continuous':{c:cs(c) for c in C},'mere':{}}
m=r[(r.f==4)&(r.k=='t')]
for c in C:s['mere'][c]={'median_m':round(float(m[c].replace(99999,float('nan')).median()),1),'values_m':[round(float(x),1) for x in m[c].replace(99999,float('nan')).dropna()]}
with open(SUM,'w') as fh:json.dump(s,fh,indent=2)
print(json.dumps(s,indent=2))
