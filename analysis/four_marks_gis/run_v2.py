#!/usr/bin/env python3
"""Stricter coarse screening wrapper for the Four Marks terrain analysis.

It keeps the original one-metre verifier, but replaces the permissive local-
slope coarse filter with sampled 80–300 m sustained profiles. A component only
reaches one-metre verification when a broad portion of its upper face is nearly
Whitewool-steep over a genuine hillside-length run.
"""
from __future__ import annotations
import numpy as np
from scipy import ndimage
from scipy.ndimage import map_coordinates
import analysis.four_marks_gis.run_analysis as r


def sampled_sustained(z, res, rows, cols, azimuths=np.arange(135, 226, 5)):
    rows=np.asarray(rows,dtype='float32');cols=np.asarray(cols,dtype='float32')
    base=z[rows.astype(int),cols.astype(int)]
    best=np.full(rows.shape,-999,dtype='float32');best_az=np.full(rows.shape,np.nan,dtype='float32')
    best_d240=np.full(rows.shape,np.nan,dtype='float32');best_d300=np.full(rows.shape,np.nan,dtype='float32')
    best_mono=np.zeros(rows.shape,dtype='float32');distances=(40,80,120,160,240,300)
    for az in azimuths:
        rad=np.radians(az);de=np.sin(rad);dn=np.cos(rad);vals=[]
        for d in distances:
            vals.append(map_coordinates(z,[rows-dn*d/res,cols+de*d/res],order=1,mode='constant',cval=np.nan,prefilter=False))
        drops=[base-v for v in vals];intervals=[base-vals[0]]+[vals[i-1]-vals[i] for i in range(1,len(vals))]
        mono=np.mean(np.stack([x>=-0.7 for x in intervals[:4]]),axis=0)
        a160=np.degrees(np.arctan2(drops[3],160));a240=np.degrees(np.arctan2(drops[4],240));a300=np.degrees(np.arctan2(drops[5],300))
        sustained=np.minimum(a160,np.minimum(a240+0.8,a300+1.2))
        valid=np.isfinite(sustained)&(drops[4]>0)&(drops[5]>0)&(mono>=.75);improve=valid&(sustained>best)
        best[improve]=sustained[improve];best_az[improve]=az;best_d240[improve]=drops[4][improve];best_d300[improve]=drops[5][improve];best_mono[improve]=mono[improve]
    best[best<-100]=np.nan
    return best,best_az,best_d240,best_d300,best_mono


def process_coarse_v2(item,b):
    e0,n0,e1,n1,ce0,cn0,ce1,cn1=item;key=f'E{ce0}_N{cn0}'
    p=r.download((e0,n0,e1,n1),.1,r.CACHE/'coarse10_v2'/f'{key}.tif')
    z,tr,res=r.read_raster(p);zs=r.smooth_valid(z,1.4);sl,asp=r.slope_aspect(zs,res)
    window=max(11,int(round(300/res)));hi=ndimage.maximum_filter(zs,size=window,mode='nearest');lo=ndimage.minimum_filter(zs,size=window,mode='nearest');rel=hi-lo
    local_min=max(6.5,b['median_local_slope_deg']*.68);relief_min=max(30,b['minimum_relief_m']*.72)
    mask=np.isfinite(sl)&(sl>=local_min)&(asp>=135)&(asp<=225)&(rel>=relief_min)
    x,y=r.centres(tr,z.shape);mask&=(x>=ce0)&(x<ce1)&(y>=cn0)&(y<cn1)&((x-r.FOUR_E)**2+(y-r.FOUR_N)**2<=r.RADIUS_M**2)
    mask=ndimage.binary_opening(mask,np.ones((2,2)));mask=ndimage.binary_closing(mask,np.ones((5,5)))
    lab,nlab=ndimage.label(mask,np.ones((3,3),dtype='uint8'));rows=[]
    for i in range(1,nlab+1):
        m=lab==i;count=int(m.sum())
        if count<150:continue
        rr,cc=np.where(m);xx=x[m];yy=y[m];component_aspect=r.circular_mean(asp[m]);down_span,cross_span,_,_=r.project_spans(xx,yy,component_aspect)
        relief=float(np.nanpercentile(z[m],97)-np.nanpercentile(z[m],3))
        if cross_span<420 or down_span<120 or relief<max(34,b['minimum_relief_m']*.75):continue
        top_cut=np.nanpercentile(z[m],48);slope_cut=np.nanpercentile(sl[m],45);sample_mask=m&(z>=top_cut)&(sl>=slope_cut);sr,sc=np.where(sample_mask)
        if len(sr)<24:continue
        cross_values=x[sample_mask]*np.cos(np.radians(component_aspect))-y[sample_mask]*np.sin(np.radians(component_aspect));order=np.argsort(cross_values)
        take=np.unique(np.linspace(0,len(order)-1,min(160,len(order))).astype(int));pick=order[take];sr=sr[pick];sc=sc[pick]
        angles,azs,d240,d300,mono=sampled_sustained(zs,res,sr,sc);valid=np.isfinite(angles)
        if valid.sum()<20:continue
        angles=angles[valid];azs=azs[valid];d240=d240[valid];d300=d300[valid];sr=sr[valid];sc=sc[valid]
        strict=(angles>=b['representative_slope_deg']-0.9)&(d240>=b['vertical_relief_m']*.72)&(d300>=b['vertical_relief_m']*.82)
        strict_count=int(strict.sum());strict_fraction=strict_count/len(angles);representative=float(np.nanmedian(angles));p65=float(np.nanpercentile(angles,65));median_drop=float(np.nanmedian(d240))
        if strict_count<18 or strict_fraction<.24:continue
        if p65<b['representative_slope_deg']-0.55 or median_drop<b['vertical_relief_m']*.68:continue
        weights=np.clip(angles[strict]-(b['representative_slope_deg']-1)+.2,.2,None);se=x[sr[strict],sc[strict]];sn=y[sr[strict],sc[strict]]
        e=float(np.average(se,weights=weights));n=float(np.average(sn,weights=weights))
        rows.append(dict(easting=e,northing=n,coarse_local_slope=float(np.nanmedian(sl[m])),coarse_sustained_slope=representative,coarse_p65_sustained_slope=p65,coarse_relief_m=relief,coarse_profile_drop240_m=median_drop,coarse_width_m=float(cross_span),coarse_downslope_span_m=float(down_span),coarse_area_ha=float(count*res*res/10000),coarse_aspect_deg=r.circular_mean(azs[strict]),strict_profile_count=strict_count,strict_profile_fraction=strict_fraction,tile=key))
    return rows


r.process_coarse=process_coarse_v2
if __name__ == '__main__':
    r.main()
