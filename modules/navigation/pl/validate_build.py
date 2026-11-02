"""Record offline numerical/RTL validation and routed timing before deployment."""
from pathlib import Path
import hashlib,json,re
import numpy as np
from scipy.ndimage import distance_transform_edt
from navigation.geometry import read_mask
from pl.runtime import NativeModel,distance_transform

ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    mask,g=read_mask(ROOT/'data/own_ct/airway_mask.nii.gz')
    ranges=[np.flatnonzero(np.any(mask,axis=tuple(j for j in range(3) if j!=i))) for i in range(3)]
    crop=np.pad(mask[tuple(slice(r[0],r[-1]+1) for r in ranges)],2)
    actual,stats=distance_transform(crop,g.spacing_xyz[::-1],NativeModel())
    expected=distance_transform_edt(crop,sampling=g.spacing_xyz[::-1]);error=np.abs(actual-expected)
    assert error.max()<1e-4
    cosim=(ROOT/'pl/build_cosim.log').read_text(errors='replace')
    assert 'C/RTL co-simulation finished: PASS' in cosim and '20 line/protocol cases passed' in cosim
    timing=(ROOT/'pl/release/timing_summary.rpt').read_text()
    match=re.search(r'WNS\(ns\).*?\n\s*-+.*?\n\s*([-\d.]+)\s+[-\d.]+\s+\d+\s+\d+\s+([-\d.]+)',timing,re.S)
    assert match,'Timing summary not found';wns,whs=map(float,match.groups());assert min(wns,whs)>=0
    files=['pl/hls/types.hpp','pl/hls/edt.cpp','pl/hls/movers.cpp','pl/tests/testbench.cpp','pl/vivado/overlay.tcl','pl/vivado/navigation.dts','pl/xrt_bridge.cpp','pl/packing.cpp','pl/runtime.py']
    report=dict(status='offline_passed_board_pending',wns_ns=wns,whs_ns=whs,clock_hz=100000000,lanes=8,rtl_cases=20,crop_shape_zyx=list(crop.shape),field_max_abs_error_mm=float(error.max()),field_mean_abs_error_mm=float(error.mean()),native_stats=stats,bit_sha256=digest(ROOT/'pl/release/kv260_navigation.bit'),source_sha256={name:digest(ROOT/name) for name in files})
    (ROOT/'docs/pl_offline_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
