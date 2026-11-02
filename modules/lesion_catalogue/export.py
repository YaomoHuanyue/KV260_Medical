"""Original-grid labels, selected binary mask and legacy-compatible rows."""
from pathlib import Path
import hashlib
import json
import time
import numpy as np
import SimpleITK as sitk
from .catalogue import catalogue

ROOT=Path(__file__).resolve().parents[2]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def export_catalogue(mask_path,destination,minimum_volume_mm3=14.0,expected_geometry=None):
    path=Path(mask_path).resolve();destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError(destination)
    if destination==path or path in destination.parents:
        raise ValueError('Export cannot replace source')
    before=sha(path);image=sitk.ReadImage(str(path))
    origin_encoding_roundoff=False
    if expected_geometry is not None:
        ref=expected_geometry
        origin_equal=np.allclose(ref.GetOrigin(),image.GetOrigin(),rtol=0,atol=1e-6)
        # A NIfTI header stores the affine origin in float32. Accept exactly
        # that encoding of the CT origin, rather than an arbitrary larger
        # coordinate tolerance; the exported labels retain the input mask grid.
        if not origin_equal and path.name.lower().endswith(('.nii','.nii.gz')):
            encoded=np.asarray(ref.GetOrigin(),np.float32).astype(np.float64)
            origin_encoding_roundoff=np.allclose(encoded,image.GetOrigin(),rtol=0,atol=1e-6)
        if ref.GetSize()!=image.GetSize() or not (origin_equal or origin_encoding_roundoff) or any(not np.allclose(a,b,rtol=0,atol=1e-6) for a,b in
            ((ref.GetSpacing(),image.GetSpacing()),(ref.GetDirection(),image.GetDirection()))):
            raise ValueError('CT/mask physical grid mismatch; no implicit resampling')
    start=time.perf_counter()
    report,labels=catalogue(sitk.GetArrayViewFromImage(image),image,minimum_volume_mm3,make_labels=True)
    compute=time.perf_counter()-start
    destination.mkdir(parents=True,exist_ok=False)
    labeled=sitk.GetImageFromArray(labels);labeled.CopyInformation(image)
    binary=sitk.GetImageFromArray((labels>0).astype(np.uint8));binary.CopyInformation(image)
    sitk.WriteImage(labeled,str(destination/'lesion_labels.nii.gz'),True)
    sitk.WriteImage(labeled,str(destination/'lesion_labels.nrrd'),True)
    sitk.WriteImage(binary,str(destination/'lesion_filtered_mask.nii.gz'),True)
    rows=report['rows']
    (destination/'lesion_candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    assert sha(path)==before,'Input mask changed during export'
    report.update(source_mask_sha256=before,compute_seconds=compute,elapsed_seconds=time.perf_counter()-start,
        CT_origin_matches_input_exact_float32_NIfTI_encoding=bool(origin_encoding_roundoff),
        physical_grid=dict(size_xyz=list(image.GetSize()),spacing_xyz_mm=list(image.GetSpacing()),
            origin_lps_mm=list(image.GetOrigin()),direction=list(image.GetDirection())),
        files={p.name:sha(p) for p in destination.iterdir() if p.is_file()},
        source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in (Path(__file__),Path(__file__).with_name('catalogue.py'))},
        PL_used_for_catalogue=False,clinical_accuracy_validated=False)
    (destination/'catalogue_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report
