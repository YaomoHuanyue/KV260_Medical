"""Exact NIfTI origin encoding accepted; a neighboring float32 value rejected."""
from pathlib import Path
import json
import sys
import tempfile
import numpy as np
import SimpleITK as sitk

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.lesion_catalogue.test_catalogue import fixture,SCRATCH
from modules.lesion_catalogue.export import export_catalogue,sha


def main():
    output=Path(sys.argv[1]).resolve();assert output.is_relative_to(ROOT/'modules/lesion_catalogue/results') and not output.exists()
    SCRATCH.mkdir(parents=True,exist_ok=True);assert SCRATCH.resolve().is_relative_to(ROOT)
    with tempfile.TemporaryDirectory(dir=SCRATCH) as name:
        folder=Path(name).resolve();assert folder.is_relative_to(SCRATCH.resolve())
        a,reference=fixture();source=folder/'correct.nii.gz';sitk.WriteImage(reference,str(source),True)
        result=export_catalogue(source,folder/'correct',14.,reference)
        assert result['CT_origin_matches_input_exact_float32_NIfTI_encoding']
        altered=sitk.Image(reference);origin=list(reference.GetOrigin())
        origin[0]=float(np.nextafter(np.float32(origin[0]),np.float32(np.inf)))
        altered.SetOrigin(origin);wrong=folder/'wrong.nii.gz';sitk.WriteImage(altered,str(wrong),True)
        try:export_catalogue(wrong,folder/'wrong',14.,reference)
        except ValueError as e:assert 'physical grid mismatch' in str(e)
        else:raise AssertionError('Neighboring float32 origin must not be silently accepted')
        assert not (folder/'wrong').exists()
    record=dict(status='exact_NIfTI_origin_roundoff_only_accepted_adjacent_origin_rejected_before_write',
        source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in (Path(__file__),ROOT/'modules/lesion_catalogue/export.py')},
        formal_external_import_geometry_gate_changed=False,grid_resampling=False,PL_accessed=False)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(record['status'],flush=True)


if __name__=='__main__':main()
