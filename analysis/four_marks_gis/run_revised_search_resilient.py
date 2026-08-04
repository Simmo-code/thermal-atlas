from pathlib import Path
import os
import sys

source_path = Path("analysis/four_marks_gis/run_revised_search.py")
wrapper = source_path.read_text()
marker = "out=Path('/tmp/run_analysis_revised.py')"
if marker not in wrapper:
    raise SystemExit("Could not locate revised-script output marker")

injection = '# Make Environment Agency WCS access resilient to temporary throttling.\ns=s.replace("import json, math, os, re, shutil, time", "import json, math, os, re, shutil, time, random, threading")\ngate_marker="FOUR_E,FOUR_N=TO_BNG.transform(FOUR_LON,FOUR_LAT)\\n"\ngate_code="""FOUR_E,FOUR_N=TO_BNG.transform(FOUR_LON,FOUR_LAT)\n_WCS_GATE=threading.Lock()\n_WCS_LAST=[0.0]\n\ndef wcs_throttle(min_gap=5.0):\n    with _WCS_GATE:\n        elapsed=time.monotonic()-_WCS_LAST[0]\n        if elapsed<min_gap:\n            time.sleep(min_gap-elapsed)\n        _WCS_LAST[0]=time.monotonic()\n"""\nif gate_marker not in s:\n    raise SystemExit("WCS gate insertion point not found")\ns=s.replace(gate_marker,gate_code)\ns=s.replace("def download(bounds,scale,path,retries=5):", "def download(bounds,scale,path,retries=15):")\nrequest_marker="            with requests.get(wcs_url(bounds,scale),headers=headers,stream=True,timeout=(60,1800)) as r:\\n"\nrequest_code="""            wcs_throttle()\n            with requests.get(wcs_url(bounds,scale),headers=headers,stream=True,timeout=(60,1800)) as r:\n"""\nif request_marker not in s:\n    raise SystemExit("WCS request insertion point not found")\ns=s.replace(request_marker,request_code)\nold_except="""        except Exception as ex:\n            err=ex; path.with_suffix(\'.part\').unlink(missing_ok=True); time.sleep(min(30,2**i))\n"""\nnew_except="""        except Exception as ex:\n            err=ex\n            path.with_suffix(\'.part\').unlink(missing_ok=True)\n            response=getattr(ex,\'response\',None)\n            retry_after=response.headers.get(\'Retry-After\') if response is not None else None\n            try:\n                delay=float(retry_after) if retry_after else min(300.0,15.0*(i+1))\n            except (TypeError,ValueError):\n                delay=min(300.0,15.0*(i+1))\n            delay+=random.uniform(0.0,3.0)\n            log(f\'WCS attempt {i+1}/{retries} failed for {bounds} scale={scale}: {ex}; retrying in {delay:.0f}s\')\n            time.sleep(delay)\n"""\nif old_except not in s:\n    raise SystemExit("WCS retry block not found")\ns=s.replace(old_except,new_except)\ns=s.replace("with cf.ThreadPoolExecutor(max_workers=6) as ex:", "with cf.ThreadPoolExecutor(max_workers=2) as ex:")\ns=s.replace("with cf.ThreadPoolExecutor(max_workers=4) as ex:", "with cf.ThreadPoolExecutor(max_workers=2) as ex:")\n'
wrapper = wrapper.replace(marker, injection + "\n" + marker)
temp_wrapper = Path("/tmp/run_revised_search_resilient_wrapper.py")
temp_wrapper.write_text(wrapper)
compile(wrapper, str(temp_wrapper), "exec")
os.execv(sys.executable, [sys.executable, str(temp_wrapper)])
