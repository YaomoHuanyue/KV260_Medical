"""Same revised-route/scalar frames on accepted C9 versus optimized PS1/PS4."""
from pathlib import Path
import argparse, hashlib, json, resource, sys, time
import numpy as np

HERE=Path(__file__).resolve().parent;SYSTEM=HERE.parents[1]
sys.path.insert(0,str(SYSTEM/'dfx/surface_quality'))
from quality_runtime import QualitySession,PSReference,verify
from test_board_r7 import expanded
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def preflight():
    verify()
    folder=HERE/'results/guidance_own_CT_ARM_r5'
    manifest=json.loads((folder/'acceptance.json').read_text())
    assert manifest['status']=='eight_own_CT_R4_curves_unchanged_three_displaced_junctions_restored_same_scalar_labels_and_six_renderer_fixtures_passed'
    for name,digest in {**manifest['source_sha256'],**manifest['input_sha256']}.items():
        p=(SYSTEM/name).resolve();assert p.is_relative_to(SYSTEM) and SHA(p)==digest,name
    assert len(manifest['scenarios'])==8 and len(manifest['render_cases'])==6
    for row in manifest['scenarios']:
        assert row['R4_all_route_and_audit_arrays_and_camera_byte_exact'] and row['all_events_available']
        for name,digest in row['files_sha256'].items():assert SHA(folder/name)==digest,name
    for case in manifest['render_cases']:
        assert case['pose_arc_is_revised_route'] and case['all_scalar_depth_and_normals_unchanged_by_labels']
        for name,digest in case['files_sha256'].items():assert SHA(folder/'render_cases'/name)==digest,name
    return folder,manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--output',type=Path,default=HERE/'results/own_board_guidance_r5.json');args=parser.parse_args()
    folder,manifest=preflight()
    if args.preflight_only:
        print('Exact revised routes, scalars, six labelled scenes and accepted C9 release verified; no PL access',flush=True)
        return
    assert not args.output.exists()
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    rows=[]
    with QualitySession(experimental=False) as session:
        for case in manifest['render_cases']:
            prefix=folder/'render_cases'/case['name']
            blob=prefix.with_name(prefix.name+'.scene.bin').read_bytes()
            request=np.fromfile(prefix.with_name(prefix.name+'.request.bin'),'<i4')
            expected=np.fromfile(prefix.with_name(prefix.name+'.expected.bin'),'<u8')
            cpu=PSReference(blob)
            small,_=cpu.render(request,4);np.testing.assert_array_equal(small.ravel(),expected)
            load=session.load(blob)
            small,small_stats=session.render(request);np.testing.assert_array_equal(small.ravel(),expected)
            assert small_stats['four_4096_byte_DMA_guards_passed']
            p=expanded(request,640,363,0);assert p[2]==1023
            truth,_=cpu.render(p,1)
            selected_pixels=int(np.count_nonzero((truth>>16)&255))
            outline_pixels=int(np.count_nonzero((truth>>24)&255))
            assert selected_pixels>0 and outline_pixels>0,'The revised-route camera must actually see the selected exit'
            samples=[]
            for repeat in range(3):
                orders=((1,4,'PL'),('PL',4,1),(4,'PL',1))
                sample=dict(repeat=repeat,execution_order=orders[repeat],PS={})
                for provider in orders[repeat]:
                    if provider=='PL':
                        pixels,stats=session.render(p)
                        assert stats['four_4096_byte_DMA_guards_passed'] and stats['input_and_tokens_checked']
                        sample['PL']=stats
                    else:
                        start=time.perf_counter();pixels,compute=cpu.render(p,provider)
                        sample['PS'][str(provider)]=dict(total_seconds=time.perf_counter()-start,compute_seconds=compute)
                    np.testing.assert_array_equal(pixels,truth)
                samples.append(sample)
            ps={k:float(np.median([s['PS'][k]['total_seconds'] for s in samples])) for k in ('1','4')}
            pl=float(np.median([s['PL']['total_seconds'] for s in samples]))
            row=dict(case=case['name'],event_id=case['event_id'],selected_branch_id=case['selected_branch_id'],
                route_id=case['route_id'],scalar_sha256=case['scalar_sha256'],
                width=640,height=363,maximum_ray_steps=1023,request_int32=p.tolist(),
                full_232320_depth_normal_target_and_outline_pixels_exact=True,
                full_four_4096_byte_DMA_guards_passed=True,
                selected_pixels=selected_pixels,outline_pixels=outline_pixels,
                output_sha256=hashlib.sha256(truth.tobytes()).hexdigest(),
                PS_median_full_API_seconds=ps,PL_median_full_API_seconds=pl,
                PL_speedup_over_strongest_PS=min(ps.values())/pl,
                performance_gate_passed=pl<=min(ps.values()),scene_load=load,samples=samples)
            rows.append(row)
            print(case['name'],'PS',ps,'PL',pl,'speedup',row['PL_speedup_over_strongest_PS'],flush=True)
            del cpu,truth
    assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    preflight()
    proof=dict(status='six_revised_route_selected_branch_frames_exact_PS1_PS4_C9_compared_C6_restored',
        cases=rows,all_six_cases_faster_than_strongest_PS=all(r['performance_gate_passed'] for r in rows),
        boot_id=boot,peak_process_RSS_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        source_sha256={p.relative_to(SYSTEM).as_posix():SHA(p) for p in [
            Path(__file__),SYSTEM/'dfx/surface_quality/quality_runtime.py',
            SYSTEM/'dfx/surface_quality/test_board_r7.py',SYSTEM/'dfx/surface_quality/release/manifest.json',
            folder/'acceptance.json']},
        full_static_one_MiB_echo_and_C6_restore_passed=True,new_bitstream=False,
        production_UI_or_source_route_modified=False,production_promoted=False,
        timing_scope='Warm complete640x363frames,1023maximumsteps, identical scalar/labels/camera. PL transfer/sync/full guards/readback included; strongest PS1/PS4 integer renderer API. Cold scene upload/DFX and once-per-route preparation reported separately. Not complete UI FPS.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(proof['status'],flush=True)


if __name__=='__main__':main()
