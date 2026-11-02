"""Actual C4 audit and C9 rendering for newly selected current-surface routes."""
from pathlib import Path
import json,resource,sys,traceback
from time import perf_counter
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json,arrays,digest
from modules.surface_route.surface_actions_r13 import verify_sources
from modules.surface_route.scene_runtime_r9 import SceneSnapshot
from modules.surface_route.bend_replan_r3 import NativeAuditor


def audit_cases(cases,output):
    sys.path.insert(0,str(ROOT/'dfx/route_audit_speed'))
    from audit_runtime import AuditSession,validate_diagnostic
    cpu=NativeAuditor();rows=[]
    with AuditSession() as session:
        for index,case in enumerate(cases):
            folder=ROOT/case['bundle'];report=json.loads((folder/'route.json').read_text(encoding='utf-8'))
            route=arrays(folder/'route.npz');p=route['points_lps_mm'];arc=route['arc_mm'];radius=route['radius_mm']
            values=[report[k] for k in ('forward_window_mm','resolution_margin_mm','required_radius_mm','minimum_bend_radius_mm')]
            data=np.zeros((len(p)+1,8),np.uint64);data[0,:2]=0x4155444954303031,len(p)
            data.view(np.float64)[0,2:6]=values;data.view(np.float64)[1:,:3]=p
            data.view(np.float64)[1:,3]=arc;data.view(np.float64)[1:,4]=radius
            validate_diagnostic(data);expected=cpu(p,arc,radius,values)
            samples=[]
            def software():
                start=perf_counter();value=cpu(p,arc,radius,values);elapsed=perf_counter()-start
                np.testing.assert_array_equal(value,expected);return elapsed
            def hardware():
                start=perf_counter();out,timing=session.run_route(data,2);elapsed=perf_counter()-start
                assert out.shape==(8706,8) and out.dtype==np.uint64
                np.testing.assert_array_equal(out[0,:3],[0,len(p),0x4155444954303031]);np.testing.assert_array_equal(out[0,3:],0)
                values=out.view(np.float64)[1:len(p)+1,:5]
                np.testing.assert_array_equal(np.isinf(values),np.isinf(expected))
                np.testing.assert_allclose(values,expected,rtol=2e-9,atol=1e-7)
                np.testing.assert_array_equal(values[:,4],expected[:,4])
                np.testing.assert_array_equal(out[1:len(p)+1,5:],0);np.testing.assert_array_equal(out[len(p)+1:],0)
                return out,elapsed,timing
            _,cold,_=hardware()
            for repeat in range(5):
                if repeat%2:out,pl,timing=hardware();ps=software()
                else:ps=software();out,pl,timing=hardware()
                samples.append(dict(PS_complete_call_seconds=ps,PL_complete_API_seconds=pl,PL_job=timing))
            out.tofile(output/f'audit_{index}.u64');data.tofile(output/f'audit_{index}_input.u64')
            ps=float(np.median([s['PS_complete_call_seconds'] for s in samples]));pl=float(np.median([s['PL_complete_API_seconds'] for s in samples]))
            rows.append(dict(bundle=case['bundle'],points=len(p),all_8706_output_words_and_states_checked=True,
                floating_tolerance=dict(atol=1e-7,rtol=2e-9),PS_complete_call_median_seconds=ps,
                PL_complete_API_median_seconds=pl,PL_over_PS_speedup=ps/pl,cold_API_seconds=cold,samples=samples,
                actual_PL_output_sha256=sha(output/f'audit_{index}.u64'),input_sha256=sha(output/f'audit_{index}_input.u64')))
            print('C4',case['label'],case['kind'],'PS/PL',round(ps/pl,3),flush=True)
        session.select('scope');session.report(output/'C4_session.json')
    return rows


def render_cases(cases,output):
    quality=ROOT/'dfx/surface_quality';sys.path.insert(0,str(quality))
    from quality_runtime import QualitySession,PSReference
    helper=ROOT/'dfx/surface/prepare.py';encoder={'__file__':str(helper),'__name__':'selected_R13_frame_encoder'}
    exec(compile(helper.read_text(encoding='utf-8'),str(helper),'exec'),encoder)
    rows=[];sequence=0
    with QualitySession() as session:
        for case in (c for c in cases if c['kind']=='full'):
            snapshot=SceneSnapshot(ROOT/case['bundle']);events=[e for e in snapshot.guidance['events'] if e['available']]
            for event in events:
                distance=float(event['junction_arc_mm']);cpu=None
                for manual in ([False,True] if event==events[0] else [False]):
                    sequence+=1;pose=snapshot.pose(distance,17. if manual else 0.,-6. if manual else 0.)
                    request=dict(revision=snapshot.revision,width=640,height=363,sequence=sequence,arc_mm=distance,
                        camera=pose['position_lps_mm'],forward=pose['forward_lps'],up=pose['up_lps'])
                    plan=snapshot.frame_plan(request)
                    assert plan['branch_event']==event['id']
                    params,view=encoder['frame_parameters'](plan['camera'],plan['forward'],plan['up'],
                        snapshot.meta['geometry'],np.zeros(3),640,363,sequence)
                    cold={}
                    if cpu is None:
                        start=perf_counter();cpu=PSReference(plan['scene']);cold['PS_dense_unpack_seconds']=perf_counter()-start
                        cold['PL_scene_upload']=session.load(plan['scene'])
                    expected,one=cpu.render(params,1);samples=[]
                    for repeat in range(3):
                        def software():
                            start=perf_counter();pixels,compute=cpu.render(params,4);elapsed=perf_counter()-start
                            np.testing.assert_array_equal(pixels,expected);return dict(compute_seconds=compute,full_call_seconds=elapsed)
                        def hardware():
                            start=perf_counter();pixels,timing=session.render(params);elapsed=perf_counter()-start
                            np.testing.assert_array_equal(pixels,expected)
                            assert timing['four_4096_byte_DMA_guards_passed'] and timing['input_and_tokens_checked']
                            return pixels,dict(timing,full_call_seconds=elapsed)
                        if repeat%2:pixels,pl=hardware();ps=software()
                        else:ps=software();pixels,pl=hardware()
                        samples.append(dict(PS4=ps,PL=pl))
                    hit=int(np.count_nonzero((pixels&65535)!=65535))
                    coverage=int(np.count_nonzero(((pixels>>np.uint64(16))&255)>0));outline=int(np.count_nonzero(((pixels>>np.uint64(24))&255)>0))
                    assert hit>0 and coverage>0 and outline>0
                    folder=output/f'frame_{sequence}';folder.mkdir()
                    pixels.tofile(folder/'PL.u64');params.tofile(folder/'request.i32');write_json(folder/'request.json',request)
                    ps=float(np.median([s['PS4']['full_call_seconds'] for s in samples]));pl=float(np.median([s['PL']['full_call_seconds'] for s in samples]))
                    row=dict(label=case['label'],revision=snapshot.revision,route_id=snapshot.meta['route_id'],event=event['id'],
                        actual_manual_camera_preserved=manual,width=640,height=363,max_steps=int(params[2]),
                        all_depth_normal_coverage_outline_64bit_words_exact_PS1_PS4_actual_PL=True,
                        scene_sha256=digest(plan['scene']),pixels_sha256=sha(folder/'PL.u64'),request_sha256=sha(folder/'request.i32'),
                        surface_pixels=hit,target_pixels=coverage,outline_pixels=outline,
                        PS4_median_full_call_seconds=ps,PL_median_full_call_seconds=pl,PL_over_PS4_speedup=ps/pl,
                        PS1_compute_seconds=one,cold=cold,samples=samples)
                    write_json(folder/'report.json',row);rows.append(row)
                    print('C9',case['label'],'event',event['id'],'manual',manual,'exact',round(ps/pl,2),'x',flush=True)
                del cpu
    return rows


def main():
    source=verify_sources();output=ROOT/'modules/surface_route/results/selected_actual_PL_ARM_r13';output.mkdir(exist_ok=False)
    review_path=ROOT/'modules/surface_route/results/selected_own_CT_ARM_r13/acceptance.json'
    review=json.loads(review_path.read_text(encoding='utf-8'))
    assert review['status']=='four_current_CT_fields_selected_full_curve_prefix_root_camera_cues_bundles_passed'
    for name,h in review['evidence_sha256'].items():assert sha(review_path.parent/name)==h,name
    for p in Path('/proc').iterdir():
        try:
            if p.name.isdigit() and (p/'comm').read_text().strip()=='medical_ui':raise RuntimeError('Medical UI active')
        except FileNotFoundError:pass
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();marker=Path('/run/kv260-dfx-medical-loaded.sha256').read_text()
    start=perf_counter();audit=[];frames=[]
    try:
        audit=audit_cases(review['cases'],output);frames=render_cases(review['cases'],output)
        assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        assert marker==Path('/run/kv260-dfx-medical-loaded.sha256').read_text()
        for name,h in review['default_files_unchanged_sha256'].items():assert sha(ROOT/name)==h,name
        write_json(output/'acceptance.json',dict(status='selected_current_surface_C4_and_all_branch_C9_PS_PL_checked_C6_restored',
            audit_cases=audit,render_cases=frames,all_C9_frames_faster_than_PS4=all(r['PL_over_PS4_speedup']>1 for r in frames),
            C4_promotion=False,C9_existing_accepted_core_reused=True,full_static_1MiB_echo_and_C6_restore_passed=True,
            boot_id=boot,review_sha256=sha(review_path),source_closure_sha256=source,
            test_source_sha256=sha(Path(__file__)),PL_access=True,new_bitstream=False,production_promoted=False,
            peak_hardware_test_RSS_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,total_test_seconds=perf_counter()-start,
            performance_scope='Warm complete hardware API versus ARM native PS API, includes copies sync guards checks; excludes common surface/path/guidance preparation and scene upload, recorded separately; not HDMI FPS',
            evidence_sha256={str(p.relative_to(output)).replace('\\','/'):sha(p) for p in output.rglob('*') if p.is_file()}))
        print('selected path actual PL acceptance passed',flush=True)
    except BaseException as error:
        write_json(output/'failure.json',dict(error=str(error),audit_cases=audit,completed_render_cases=frames,traceback=traceback.format_exc()));raise


if __name__=='__main__':main()
