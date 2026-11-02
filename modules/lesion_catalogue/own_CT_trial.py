"""Same original CT-mask catalogue vs frozen Python, alternating PS4 samples."""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
import numpy as np
import SimpleITK as sitk

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.lesion_catalogue.catalogue import catalogue
from modules.lesion_catalogue.oracle import component_report
from modules.lesion_catalogue.export import export_catalogue,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--export',type=Path,required=True)
    p.add_argument('--mask',type=Path,required=True)
    p.add_argument('--ct',type=Path,default=ROOT/'fixtures/own_ct/CT-chest.nrrd')
    a=p.parse_args()
    target=a.output.resolve();out=a.export.resolve();here=Path(__file__).resolve().parent
    assert target.is_relative_to(here/'results') and out.is_relative_to(here/'results')
    assert not target.exists() and not out.exists()
    ct=a.ct.resolve();mask=a.mask.resolve()
    assert ct.is_relative_to(ROOT) and mask.is_relative_to(ROOT)
    before={n.relative_to(ROOT).as_posix():sha(n) for n in (ct,mask)}
    image=sitk.ReadImage(str(mask));reference=sitk.ReadImage(str(ct));view=sitk.GetArrayViewFromImage(image)
    assert image.GetSize()==reference.GetSize()
    previous_threads=sitk.ProcessObject.GetGlobalDefaultNumberOfThreads()
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    cases=[]
    try:
        for minimum in (0.,14.):
            samples=[]
            for repeat in range(3):
                measurements={};results={}
                order=('legacy','new') if repeat%2==0 else ('new','legacy')
                for kind in order:
                    start=time.perf_counter()
                    result=component_report(view,image,minimum) if kind=='legacy' else catalogue(view,image,minimum,True)
                    measurements[kind]=time.perf_counter()-start;results[kind]=result
                expected,rows=results['legacy'];report,actual=results['new']
                np.testing.assert_array_equal(actual,expected);assert len(rows)==len(report['rows'])
                for old,new in zip(rows,report['rows']):
                    assert old['id']==new['id'] and old['bbox_xyz_size']==new['bbox_xyz_size']
                    np.testing.assert_allclose(old['centroid_xyz_mm'],new['centroid_xyz_mm'],rtol=0,atol=1e-7)
                    assert abs(old['volume_mm3']-new['volume_mm3'])<1e-7
                    assert abs(old['equivalent_sphere_diameter_mm']-new['equivalent_sphere_diameter_mm'])<1e-7
                samples.append(dict(order=order,legacy_PS4_seconds=measurements['legacy'],new_PS_seconds=measurements['new']))
            case=dict(minimum_volume_mm3=minimum,raw_components=report['raw_component_count'],retained_components=len(rows),
                samples=samples,median_legacy_PS4_seconds=statistics.median(s['legacy_PS4_seconds'] for s in samples),
                median_new_PS_seconds=statistics.median(s['new_PS_seconds'] for s in samples),
                full_uint16_label_array_exact_original_Python=True,all_legacy_fields_match=True,
                label_array_sha256=hashlib.sha256(actual.tobytes()).hexdigest(),catalogue=report)
            cases.append(case);print(json.dumps({k:case[k] for k in ('minimum_volume_mm3','raw_components','retained_components','median_legacy_PS4_seconds','median_new_PS_seconds')}),flush=True)
    finally:
        sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(previous_threads)
    exported=export_catalogue(mask,out,14.,reference)
    _,expected=catalogue(view,image,14.,True)
    for file in ('lesion_labels.nii.gz','lesion_labels.nrrd'):
        im=sitk.ReadImage(str(out/file));np.testing.assert_array_equal(sitk.GetArrayFromImage(im),expected)
        assert im.GetSize()==image.GetSize() and im.GetPixelID()==sitk.sitkUInt16
        for x,y in ((im.GetSpacing(),image.GetSpacing()),(im.GetOrigin(),image.GetOrigin()),(im.GetDirection(),image.GetDirection())):
            np.testing.assert_allclose(x,y,rtol=0,atol=1e-5)
    binary=sitk.GetArrayFromImage(sitk.ReadImage(str(out/'lesion_filtered_mask.nii.gz')))
    np.testing.assert_array_equal(binary,expected>0)
    for n,d in before.items():assert sha(ROOT/n)==d
    record=dict(status='own_CT_catalogue_exact_original_Python_and_full_label_export_roundtrip_passed',
        platform=platform.platform(),cases=cases,export=exported,
        input_sha256=before,source_sha256={q.relative_to(ROOT).as_posix():sha(q) for q in sorted(here.glob('*.py'))},
        reference_origin_sha256=sha(here/'reference_origin.json'),same_input_PS4_comparison=True,
        PL_accessed=False,PL_catalogue_kernel_implemented=False,clinical_accuracy_validated=False,
        old_UI_and_masks_changed=False,no_cached_results=True,
        timed_scope='connected components, size filtering, full-sized labels and physical catalogue; input reading and file output separate')
    target.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n',encoding='utf-8');print(record['status'],flush=True)


if __name__=='__main__':main()
