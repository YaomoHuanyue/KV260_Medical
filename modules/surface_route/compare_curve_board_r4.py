# Derived from the sealed R2 comparison for nonzero bend query inputs; see curve_C4_derivation_r4.json.
"""Actual C4 and optimized native PS comparison for the same new-wall HUD.

Wall distances, winding and continuous bounds are common PS preparation. Only
the existing C4 bend/window audit is compared here. Standalone fixed DMA time
is reported honestly; this is not a new PL geometric distance accelerator.
"""
from pathlib import Path
import argparse
import ctypes
import hashlib
import json
import statistics
import sys
from time import perf_counter
import numpy as np

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parents[1]
SHA = lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--review',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    assert sys.platform == 'linux'
    assert not args.output.exists()
    review = json.loads((args.review/'acceptance.json').read_text(encoding='utf-8'))
    assert review['platform'] == 'linux' and review['status'] == 'own_CT_Q5_Q6_physical_curve_quality_bend_wall_mask_camera_passed'
    for n,d in review['source_sha256'].items():assert SHA(SYSTEM/n) == d
    reference = json.loads((SYSTEM/'dfx/route_audit/docs/arm_cpu_baseline.json').read_text())
    library = SYSTEM/reference['reference_library_archive']
    assert SHA(library) == reference['reference_library_sha256']
    lib = ctypes.CDLL(str(library))
    lib.audit_native.argtypes = [ctypes.c_void_p]*3+[ctypes.c_uint]+[ctypes.c_double]*4+[ctypes.c_void_p]
    lib.audit_native.restype = ctypes.c_int
    sys.path.insert(0,str(SYSTEM/'dfx/route_audit_speed'))
    from audit_runtime import AuditSession,verify,validate_diagnostic
    manifest = verify()
    output = args.output.resolve()
    output.mkdir(parents=True)
    records = []
    with AuditSession() as session:
        for case in review['cases']:
            file = args.review/case['arrays_file'];assert SHA(file) == case['arrays_sha256']
            for n,d in case['source_binding_sha256'].items():assert SHA(SYSTEM/n) == d
            a = dict(np.load(file,allow_pickle=False))
            p = np.ascontiguousarray(a['points_lps_mm'],'<f8')
            arc = np.ascontiguousarray(a['arc_mm'],'<f8')
            radius = np.ascontiguousarray(a['conservative_radius_mm'],'<f4')
            params = case['instrument_parameters']
            values = [params[k] for k in ('forward_window_mm','resolution_margin_mm',
                'required_radius_mm','minimum_bend_radius_mm')]
            data = np.zeros((len(p)+1,8),np.uint64)
            data[0,:2] = 0x4155444954303031,len(p)
            data.view(np.float64)[0,2:6] = values
            data.view(np.float64)[1:,:3] = p
            data.view(np.float64)[1:,3] = arc
            data.view(np.float64)[1:,4] = radius
            validate_diagnostic(data)
            expected = np.empty((len(p),5),np.float64)
            def ps():
                start = perf_counter()
                code = lib.audit_native(p.ctypes.data,arc.ctypes.data,radius.ctypes.data,
                    len(p),*values,expected.ctypes.data)
                elapsed = perf_counter()-start
                assert code == 0
                return elapsed
            ps()
            def pl():
                start = perf_counter()
                actual,job = session.run_route(data,2)
                elapsed = perf_counter()-start
                assert actual.shape == (8706,8) and actual.dtype == np.uint64
                np.testing.assert_array_equal(actual[0,:2],[0,len(p)])
                assert actual[0,2] == 0x4155444954303031
                np.testing.assert_array_equal(actual[0,3:],0)
                rows = actual.view(np.float64)[1:len(p)+1,:5]
                np.testing.assert_array_equal(np.isinf(rows),np.isinf(expected))
                np.testing.assert_allclose(rows,expected,rtol=2e-9,atol=1e-7)
                np.testing.assert_array_equal(rows[:,4],expected[:,4])
                np.testing.assert_array_equal(actual[1:len(p)+1,5:],0)
                np.testing.assert_array_equal(actual[len(p)+1:],0)
                return elapsed,job,actual
            cold_time,cold_job,_=pl()  # Cold DFX is separated from warm API trials.
            trials=[]
            for i in range(12):
                if i%2:
                    pt,job,actual=pl();st=ps()
                else:
                    st=ps();pt,job,actual=pl()
                trials.append(dict(order='PL_then_PS' if i%2 else 'PS_then_PL',
                    PS_seconds=st,PL_complete_API_seconds=pt,PL_job=job))
            tier=case['tier'];actual.tofile(output/(tier+'_PL_full_output.bin'))
            expected.tofile(output/(tier+'_PS_output.bin'));data.tofile(output/(tier+'_input.bin'))
            sm=statistics.median(x['PS_seconds'] for x in trials)
            pm=statistics.median(x['PL_complete_API_seconds'] for x in trials)
            records.append(dict(tier=tier,points=len(p),parameters=values,
                input_sha256=hashlib.sha256(data.tobytes()).hexdigest(),all_8706_output_words_checked=True,
                float_statistics_tolerance=dict(atol=1e-7,rtol=2e-9),all_states_exact=True,
                PS_median_seconds=sm,PL_complete_API_median_seconds=pm,PS_over_PL_speedup=sm/pm,
                warm_samples=trials,PL_recommended_for_standalone_stage=bool(pm<sm),
                cold_API_seconds=cold_time,cold_job=cold_job,
                shared_wall_distance_winding_and_continuous_bound_preparation_on='PS'))
            print(tier,'PS',sm,'PL_API',pm,'speedup',sm/pm,flush=True)
        session.select('scope')
        session.report(output/'C4_session.json')
    record=dict(status='actual_C4_physical_curve_quality_same_input_native_PS_PL_compared_no_promotion',
        cases=records,review_receipt_sha256=SHA(args.review/'acceptance.json'),
        C4_manifest_sha256=SHA(SYSTEM/'dfx/route_audit_speed/release/manifest.json'),
        reference_library_sha256=SHA(library),source_sha256=SHA(Path(__file__)),
        source_algorithm_unchanged=True,new_PL_bitstream=False,new_surface_default_promoted=False,
        includes_warm_XRT_API_and_complete_output_buffer_allocation=True,
        comparison_excludes_common_PS_mesh_preparation_and_file_IO=True,
        cold_DFX_excluded_from_warm_medians=True,
        files_sha256={p.name:SHA(p) for p in output.iterdir() if p.is_file()})
    (output/'acceptance.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(record['status'],flush=True)


if __name__ == '__main__':main()
