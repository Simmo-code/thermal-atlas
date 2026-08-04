from pathlib import Path
p=Path('analysis/four_marks_gis/output_v3/run_analysis.py')
s=p.read_text()
# Output default
s=s.replace("OUT=Path(os.environ.get('GIS_OUTPUT','analysis/four_marks_gis/output'))", "OUT=Path(os.environ.get('GIS_OUTPUT','analysis/four_marks_gis/output_revised'))")
# Add dataclass fields
s=s.replace("    source:str=''; name:str=''; status:str=''; easting:float=0; northing:float=0\n", "    source:str=''; name:str=''; status:str=''; category:str='Rejected'; easting:float=0; northing:float=0\n")
s=s.replace("    gaps_count:int=0; largest_gap_m:float=0; percent_face_at_benchmark:float=0\n", "    gaps_count:int=0; largest_gap_m:float=0; percent_face_at_benchmark:float=0\n    percent_face_8deg:float=0; percent_face_9_5deg:float=0; ridge_8deg_m:float=0; ridge_9_5deg_m:float=0\n")
# Sustained distances + formula
s=s.replace("def sustained(z,res,azimuths,distances=(40,80,120,160,240,300)):", "def sustained(z,res,azimuths,distances=(40,80,120,160,200,240)):")
s=s.replace("        a160=np.degrees(np.arctan2(ds[3],160));a240=np.degrees(np.arctan2(ds[4],240));a300=np.degrees(np.arctan2(ds[5],300))\n        ang=np.minimum(a160,np.minimum(a240+1.0,a300+1.5))\n", "        a120=np.degrees(np.arctan2(ds[2],120));a160=np.degrees(np.arctan2(ds[3],160));a200=np.degrees(np.arctan2(ds[4],200))\n        # The revised screen measures the sustained upper/middle face over 120-200 m.\n        # Small tolerances prevent a single rounded lower section from hiding an otherwise continuous face.\n        ang=np.minimum(a120,np.minimum(a160+0.7,a200+1.2))\n")
# select_face base/rel/broad/threshold/relief/return
s=s.replace("        base=np.isfinite(ang)&(dist<600)&(drops[240]>=28)&(ang>=7)", "        base=np.isfinite(ang)&(dist<600)&(drops[200]>=24)&(ang>=7)")
s=s.replace("        b=benchmark; base=np.isfinite(ang)&(dist<1300)&(drops[240]>=max(20,b['vertical_relief_m']*.55))&(ang>=b['representative_slope_deg']-1.2)\n        base&=(local_slope>=max(5,b['median_local_slope_deg']*.55))", "        # Deliberately broader than Whitewool: retain potentially soarable inland faces.\n        base=np.isfinite(ang)&(dist<1300)&(drops[160]>=18)&(drops[200]>=20)&(ang>=5.5)\n        base&=(local_slope>=4.5)")
s=s.replace("        rel=float(np.nanmedian(drops[240][m]))", "        rel=float(np.nanmedian(drops[200][m]))")
s=s.replace("    threshold=float(np.nanmedian(ang[m])) if white else float(benchmark['representative_slope_deg'])\n    broad=np.isfinite(ang)&(dist<(650 if white else 1400))&(drops[240]>=max(16,(np.nanmedian(drops[240][m])*.45)))&(ang>=max(4,threshold*.58))\n", "    threshold=float(np.nanmedian(ang[m])) if white else 8.0\n    broad=np.isfinite(ang)&(dist<(650 if white else 1400))&(drops[160]>=max(12,(np.nanmedian(drops[160][m])*.40)))&(ang>=max(4.5,threshold*.58))\n")
s=s.replace("    relief=float(np.nanmedian(drops[240][m])); run=240.0", "    relief=float(np.nanmedian(drops[200][m])); run=200.0")
s=s.replace("    pct=float(100*np.sum(m & (ang>=threshold))/max(1,np.sum(broad)));poly=polygon_from_mask(broad,tr)\n", "    pct=float(100*np.sum(broad & (ang>=threshold))/max(1,np.sum(broad)))\n    pct8=float(100*np.sum(broad & (ang>=8.0))/max(1,np.sum(broad)))\n    pct95=float(100*np.sum(broad & (ang>=9.5))/max(1,np.sum(broad)))\n    def qualifying_width(qmask):\n        labs,nq=ndimage.label(qmask,np.ones((3,3),dtype='uint8'))\n        choices=[]\n        for qi in range(1,nq+1):\n            qm=labs==qi\n            if qm.sum()<20:continue\n            qx=x[qm];qy=y[qm];_,qw,_,_=project_spans(qx,qy,asp);choices.append((qm.sum(),float(qw)))\n        return max(choices,key=lambda q:q[0])[1] if choices else 0.0\n    ridge8=qualifying_width(broad & (ang>=8.0));ridge95=qualifying_width(broad & (ang>=9.5))\n    poly=polygon_from_mask(broad,tr)\n")
s=s.replace("        percent_face_at_benchmark=pct,polygon=poly,easting=e,northing=n)", "        percent_face_at_benchmark=pct,percent_face_8deg=pct8,percent_face_9_5deg=pct95,ridge_8deg_m=ridge8,ridge_9_5deg_m=ridge95,polygon=poly,easting=e,northing=n)")
# Whitewool methodology text
s=s.replace("methodology='Continuous face selected automatically near SU650204 using sustained 160–300 m downhill profiles; 4 m averaged DTM suppresses one-metre banks and ditches.'", "methodology='Continuous face selected automatically near SU650204 using sustained 120–200 m downhill profiles; 4 m averaged DTM suppresses one-metre banks and ditches. Whitewool is retained as a quality reference, not the minimum pass threshold.'")
# Coarse screen thresholds
s=s.replace("size=max(9,int(round(260/res)))", "size=max(9,int(round(220/res)))")
s=s.replace("mask=np.isfinite(sl)&(sl>=max(5.5,b['median_local_slope_deg']*.55))&(asp>=135)&(asp<=225)&(rel>=b['minimum_relief_m']*.65)", "mask=np.isfinite(sl)&(sl>=5.0)&(asp>=135)&(asp<=225)&(rel>=18.0)")
s=s.replace("      if m.sum()<120:continue", "      if m.sum()<70:continue")
s=s.replace("      if cross<140 or relief<b['minimum_relief_m']*.55:continue", "      if cross<120 or relief<18.0:continue")
# exact no-face status
s=s.replace("status='Failed terrain threshold'", "status='Rejected terrain'", 1)
s=s.replace("reason='No contiguous south-east to south-west face in the 3 km verification window met the sustained-slope and relief pre-filter.'", "reason='No contiguous south-east to south-west face in the 3 km verification window met the revised 120–200 m sustained-profile pre-filter.'")
# Replace classification block in exact_assess
old="""    passed=(f['representative_slope_deg']>=b['minimum_representative_slope_deg'] and f['vertical_relief_m']>=b['minimum_relief_m'] and f['ridge_length_m']>=b['minimum_ridge_length_m'] and f['percent_face_at_benchmark']>=b['minimum_face_percentage'])
    terrain=100*(.25*min(1.25,f['representative_slope_deg']/b['representative_slope_deg'])+.15*min(1.25,f['vertical_relief_m']/b['vertical_relief_m'])+.15*min(1.25,f['ridge_length_m']/b['ridge_length_m'])+.10*max(0,1-abs(f['aspect']-180)/45)+.10*min(1.25,max(0,f['lip_sharpness_deg']+5)/10)+.10*min(1.25,f['connected_area_ha']/max(.1,b['connected_area_ha']))+.05*min(1.25,f['percent_face_at_benchmark']/max(1,b['percent_face_at_benchmark'])))/.90
    status='Passed terrain threshold' if passed else 'Failed terrain threshold'
    reason=(f\"Representative sustained slope {f['representative_slope_deg']:.1f}° versus Whitewool {b['representative_slope_deg']:.1f}°; relief {f['vertical_relief_m']:.0f} m versus {b['vertical_relief_m']:.0f} m; continuous ridge {f['ridge_length_m']:.0f} m versus {b['ridge_length_m']:.0f} m; {f['percent_face_at_benchmark']:.0f}% of the broader face reaches the benchmark threshold.\")
"""
new="""    likely=(f['representative_slope_deg']>=9.5 and f['vertical_relief_m']>=30 and f['ridge_8deg_m']>=400 and f['percent_face_8deg']>=30)
    marginal=(f['representative_slope_deg']>=8.0 and f['vertical_relief_m']>=25 and f['ridge_8deg_m']>=300 and f['percent_face_8deg']>=20)
    thermal=(f['representative_slope_deg']>=6.0 and f['vertical_relief_m']>=20 and f['ridge_length_m']>=250)
    if likely: category='Likely ridge-soarable';status='Likely ridge-soarable';passed=True
    elif marginal: category='Marginal — inspect carefully';status='Marginal terrain candidate';passed=True
    elif thermal: category='Thermal trigger only';status='Thermal-trigger terrain';passed=False
    else: category='Rejected';status='Rejected terrain';passed=False
    terrain=100*(.28*min(1.25,f['representative_slope_deg']/9.5)+.18*min(1.25,f['vertical_relief_m']/30)+.18*min(1.25,f['ridge_8deg_m']/400)+.10*max(0,1-abs(f['aspect']-180)/45)+.08*min(1.25,max(0,f['lip_sharpness_deg']+5)/10)+.08*min(1.25,f['connected_area_ha']/3.0)+.10*min(1.25,f['percent_face_8deg']/30))
    reason=(f\"Sustained 120–200 m slope {f['representative_slope_deg']:.1f}°; relief {f['vertical_relief_m']:.0f} m; qualifying ridge at ≥8° {f['ridge_8deg_m']:.0f} m; {f['percent_face_8deg']:.0f}% of the broader face reaches 8° and {f['percent_face_9_5deg']:.0f}% reaches 9.5°. Category: {category}.\")
"""
if old not in s:
    raise SystemExit('classification block not found')
s=s.replace(old,new)
# Face constructor add category and fields
s=s.replace("face=Face(source=source,name=name,status=status,easting=e2", "face=Face(source=source,name=name,status=status,category=category,easting=e2")
s=s.replace("percent_face_at_benchmark=f['percent_face_at_benchmark'],whitewool_slope_percent", "percent_face_at_benchmark=f['percent_face_at_benchmark'],percent_face_8deg=f['percent_face_8deg'],percent_face_9_5deg=f['percent_face_9_5deg'],ridge_8deg_m=f['ridge_8deg_m'],ridge_9_5deg_m=f['ridge_9_5deg_m'],whitewool_slope_percent")
# Map and outputs headings/layers
s=s.replace("Four Marks Whitewool benchmark terrain analysis", "Four Marks revised minimum-profile terrain analysis")
s=s.replace("passed=sorted([f for f in faces if f.pass_terrain],key=lambda f:f.terrain_score,reverse=True)", "passed=sorted([f for f in faces if f.pass_terrain],key=lambda f:f.terrain_score,reverse=True)")
s=s.replace("layers={n:folium.FeatureGroup(name=n,show=(n not in {'Aviation concerns','Protected or impractical land'})) for n in ['Passed terrain threshold','Failed terrain threshold','Existing flying sites','Aviation concerns','Protected or impractical land']}", "layers={n:folium.FeatureGroup(name=n,show=(n not in {'Thermal trigger only','Rejected terrain','Aviation concerns','Protected or impractical land'})) for n in ['Likely ridge-soarable','Marginal — inspect carefully','Thermal trigger only','Rejected terrain','Existing flying sites','Aviation concerns','Protected or impractical land']}")
s=s.replace("      layer=layers['Passed terrain threshold'] if f.pass_terrain else layers['Failed terrain threshold'];color='red' if f.pass_terrain else 'gray';folium.Marker", "      layer=layers.get(f.category,layers['Rejected terrain']);color={'Likely ridge-soarable':'red','Marginal — inspect carefully':'orange','Thermal trigger only':'lightblue','Rejected':'gray'}.get(f.category,'gray');folium.Marker")
s=s.replace("Representative slope {f.representative_slope_deg:.1f}°<br>Relief", "Sustained 120–200 m slope {f.representative_slope_deg:.1f}°<br>≥8° ridge {f.ridge_8deg_m:.0f} m; face {f.percent_face_8deg:.0f}%<br>Relief")
# Report heading and threshold paragraph
start="lines=['# Four Marks 30-mile paragliding terrain analysis','', '## Completion statement'"
s=s.replace(start, "lines=['# Four Marks 30-mile revised minimum-profile paragliding terrain analysis','', '## Completion statement'")
old_para="'Pass threshold: representative sustained slope at least {:.1f}°, relief at least {:.1f} m, continuous ridge at least {:.0f} m, and at least {:.0f}% of the broader face at the Whitewool representative angle.'.format(b['minimum_representative_slope_deg'],b['minimum_relief_m'],b['minimum_ridge_length_m'],b['minimum_face_percentage'])"
new_para="'Revised categories: likely ridge-soarable = sustained slope ≥9.5°, relief ≥30 m, ≥8° ridge ≥400 m and ≥30% face at 8°; marginal = slope ≥8°, relief ≥25 m, ≥8° ridge ≥300 m and ≥20% face at 8°; thermal-trigger only = slope ≥6°, relief ≥20 m and broad ridge ≥250 m.'"
s=s.replace(old_para,new_para)
s=s.replace("No new south-east to south-west face met every Whitewool terrain threshold.", "No new south-east to south-west face met the revised likely or marginal terrain thresholds.")
# stats names/counts
s=s.replace("stats['one_metre_verified_total']=len(faces);stats['genuinely_equal_or_exceed_whitewool']=len(passed);stats['passed_names']=[f.name for f in passed]", "stats['one_metre_verified_total']=len(faces);stats['likely_ridge_soarable']=sum(f.category=='Likely ridge-soarable' for f in faces);stats['marginal_candidates']=sum(f.category=='Marginal — inspect carefully' for f in faces);stats['thermal_trigger_only']=sum(f.category=='Thermal trigger only' for f in faces);stats['rejected']=sum(f.category=='Rejected' for f in faces);stats['passed_names']=[f.name for f in passed]")
# main prelim threshold
s=s.replace("prelim=[r for r in prelim if r['coarse_local_slope']>=max(6,b['median_local_slope_deg']*.60) and r['coarse_relief_m']>=b['minimum_relief_m']*.60]", "prelim=[r for r in prelim if r['coarse_local_slope']>=5.2 and r['coarse_relief_m']>=18.0 and r['coarse_width_m']>=120]")
# Update report per candidate line to include category
s=s.replace("f\"### {i}. {f.name}\"", "f\"### {i}. {f.name} — {f.category}\"")
s=s.replace('Median 240 m drop:', 'Median 200 m drop:')
out=Path('/tmp/run_analysis_revised.py')
out.write_text(s)
compile(s,str(out),'exec')
import os,sys
os.execv(sys.executable,[sys.executable,str(out)])
