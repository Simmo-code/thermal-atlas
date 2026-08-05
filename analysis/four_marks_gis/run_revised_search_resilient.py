from pathlib import Path
import os
import sys

source_path = Path("analysis/four_marks_gis/run_revised_search.py")
wrapper = source_path.read_text()
marker = "out=Path('/tmp/run_analysis_revised.py')"
if marker not in wrapper:
    raise SystemExit("Could not locate revised-script output marker")

injection = r'''# Make Environment Agency WCS access resilient and keep the exact stage within the runner limit.
s=s.replace("import json, math, os, re, shutil, time", "import json, math, os, re, shutil, time, random, threading")
gate_marker="FOUR_E,FOUR_N=TO_BNG.transform(FOUR_LON,FOUR_LAT)\n"
gate_code="""FOUR_E,FOUR_N=TO_BNG.transform(FOUR_LON,FOUR_LAT)
_WCS_GATE=threading.Lock()
_WCS_LAST=[0.0]

def wcs_throttle(min_gap=5.0):
    with _WCS_GATE:
        elapsed=time.monotonic()-_WCS_LAST[0]
        if elapsed<min_gap:
            time.sleep(min_gap-elapsed)
        _WCS_LAST[0]=time.monotonic()
"""
if gate_marker not in s:
    raise SystemExit("WCS gate insertion point not found")
s=s.replace(gate_marker,gate_code)
s=s.replace("def download(bounds,scale,path,retries=5):", "def download(bounds,scale,path,retries=15):")
request_marker="            with requests.get(wcs_url(bounds,scale),headers=headers,stream=True,timeout=(60,1800)) as r:\n"
request_code="""            wcs_throttle()
            with requests.get(wcs_url(bounds,scale),headers=headers,stream=True,timeout=(60,1800)) as r:
"""
if request_marker not in s:
    raise SystemExit("WCS request insertion point not found")
s=s.replace(request_marker,request_code)
old_except="""        except Exception as ex:
            err=ex; path.with_suffix('.part').unlink(missing_ok=True); time.sleep(min(30,2**i))
"""
new_except="""        except Exception as ex:
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
"""
if old_except not in s:
    raise SystemExit("WCS retry block not found")
s=s.replace(old_except,new_except)

# The previous run passed source and benchmark in the wrong order. That made b a string
# and caused: string indices must be integers, not 'str'.
wrong_call="futures=[ex.submit(exact_assess,*j,b) for j in jobs]"
right_call="futures=[ex.submit(exact_assess,j[0],j[1],j[2],b,j[3]) for j in jobs]"
if wrong_call not in s:
    raise SystemExit("Exact verification call site not found")
s=s.replace(wrong_call,right_call)

# A 3 km exact window already examines terrain up to 1.3 km from its centre. Cluster
# coarse hits at 1.2 km rather than 0.5 km so overlapping windows are not downloaded
# hundreds of times. The highest-scoring coarse hit in each cluster is retained.
s=s.replace("<500 for q in keep", "<1200 for q in keep")

# Keep WCS traffic gentle while allowing raster processing to overlap.
s=s.replace("with cf.ThreadPoolExecutor(max_workers=6) as ex:", "with cf.ThreadPoolExecutor(max_workers=2) as ex:")
s=s.replace("with cf.ThreadPoolExecutor(max_workers=4) as ex:", "with cf.ThreadPoolExecutor(max_workers=3) as ex:")

# Make the reduced exact workload explicit in the log.
s=s.replace("faces=[]\n    with cf.ThreadPoolExecutor(max_workers=3) as ex:", "log(f'Exact verification jobs after 1.2 km clustering: {len(jobs)}')\n    faces=[]\n    with cf.ThreadPoolExecutor(max_workers=3) as ex:")

# Remove aviation calculations. These will be checked manually after terrain ranking.
aviation_start="    ds=[]\n    for nm,(lat,lon) in AERODROMES.items():\n"
aviation_end="    near=[]\n"
aviation_i=s.find(aviation_start)
aviation_j=s.find(aviation_end,aviation_i)
if aviation_i < 0 or aviation_j < 0:
    raise SystemExit("Aviation screening block not found")
s=s[:aviation_i]+"    face.airspace_observation='Not automatically checked; manually review current aviation charts, NOTAMs, aerodromes and local procedures.'\n"+s[aviation_j:]

# Remove all per-candidate OpenStreetMap/Overpass calls. Terrain results are produced
# first; obstacles, land cover, protected land and aviation will be checked manually
# only for the final shortlist.
old_screen="""    for i,f in enumerate(final,1):
      if f.pass_terrain or f.source=='Required reassessment':osm_check(f)
      if i%8==0:log(f'OSM/aviation proximity screens {i}/{len(final)}')
"""
new_screen="""    log(f'Skipping automated OSM and aviation checks for {len(final)} terrain candidates')
    for f in final:
      f.landcover_observation='Not automatically checked; inspect aerial imagery and site conditions manually.'
      f.obstacle_observation='Not automatically checked; inspect buildings, power lines, roads, railways, trees and fences manually.'
      f.protected_observation='Not automatically checked; confirm protected-land constraints using official records.'
      f.airspace_observation='Not automatically checked; manually review current aviation charts, NOTAMs, aerodromes and local procedures.'
      f.existing_site_conflict='Not automatically checked.'
      if f.pass_terrain:
        f.launch_observation='Terrain geometry appears potentially suitable; surface, fences, rotor, access and ownership require field inspection.'
        f.landing_observation='Terrain analysis only; actual emergency landing suitability requires aerial imagery and a site visit.'
"""
if old_screen not in s:
    raise SystemExit("OSM screening loop not found")
s=s.replace(old_screen,new_screen)

s=s.replace("OpenStreetMap screening is a current obstacle pointer, not a substitute for official protected-site records, current aviation charts/NOTAMs, landowner contact, a field inspection or a formal club site assessment.", "Automated OSM and aviation screening were deliberately omitted. Obstacles, land cover, protected land, access, ownership, current aviation charts, NOTAMs, aerodromes and local procedures must be checked manually for shortlisted terrain candidates.")
'''

wrapper = wrapper.replace(marker, injection + "\n" + marker)
temp_wrapper = Path("/tmp/run_revised_search_resilient_wrapper.py")
temp_wrapper.write_text(wrapper)
compile(wrapper, str(temp_wrapper), "exec")
os.execv(sys.executable, [sys.executable, str(temp_wrapper)])
