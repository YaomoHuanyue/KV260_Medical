"""Same-input ARM PS1/PS4 and guarded C9 PL rendering. No UI/static-shell reload."""
from pathlib import Path
import argparse,hashlib,json,resource,time
import numpy as np
from quality_runtime import PSReference,QualitySession,ROOT,sha


def expanded(request,width,height,pose):
    old=np.asarray(request,np.int64);p=old.copy()
    center=old[7:10]+((old[0]-1)/2)*old[10:13]+((old[1]-1)/2)*old[13:16]
    horizontal=np.rint(old[10:13]*old[0]/width).astype(np.int64)
    vertical=np.rint(old[13:16]*old[1]/height).astype(np.int64)
    center+=old[10:13]*pose*.35
    p[0:2]=width,height;p[3]=1000+pose
    p[7:10]=np.rint(center-((width-1)/2)*horizontal-((height-1)/2)*vertical).astype(np.int64)
    p[10:13]=horizontal;p[13:16]=vertical
    if np.any(p<-2147483648) or np.any(p>2147483647):raise ValueError('Expanded camera overflow')
    return p.astype('<i4')


def main():
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--ps-only',action='store_true');mode.add_argument('--hardware',action='store_true')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args();args.output=args.output.resolve()
    if args.output.exists() or not 2<=args.repeats<=5:raise RuntimeError('Fresh receipt and 2–5 repetitions required')
    compiled=json.loads((ROOT/'build/host_compiled_r7.json').read_text())
    for name,digest in compiled['source_sha256'].items():assert sha(ROOT/name)==digest,name
    for name,digest in compiled['library_sha256'].items():assert sha(ROOT/'build'/name)==digest,name
    original_boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    manifest=json.loads((ROOT/'fixtures/manifest.json').read_text());cases=manifest['cases']
    oracle=json.loads((ROOT/'results/ARM_reference_r7.json').read_text());identity={c['case']:c for c in oracle['cases']}
    rows=[];validation=[];restored=False

    def inputs(case):
        name=case['name'];scene_path=ROOT/'fixtures'/f'{name}.scene.bin'
        request_path=ROOT/'fixtures'/f'{name}.request.bin';expected_path=ROOT/'fixtures'/f'{name}.expected.bin'
        assert sha(scene_path)==identity[name]['scene_sha256']
        assert sha(request_path)==identity[name]['request_sha256']
        assert sha(expected_path)==identity[name]['dense_expected_sha256']
        return scene_path.read_bytes(),np.fromfile(request_path,'<i4'),np.fromfile(expected_path,'<u8')

    def full_frames(session):
        full=['own_CT_network_probability_high','own_CT_native_support_Q5','own_CT_native_support_Q6']
        for case in cases:
            if case['name'] not in full:continue
            blob,base,_=inputs(case);start=time.perf_counter();cpu=PSReference(blob);cpu_preparation=time.perf_counter()-start
            load=session.load(blob) if session else None
            for pose in [-1,0,1]:
                p=expanded(base,640,363,pose);one,one_seconds=cpu.render(p,1)
                assert np.count_nonzero((one&65535)!=65535)>0,'Camera sees no surface'
                samples=[]
                for repeat in range(args.repeats):
                    # Alternate order to avoid always rewarding the warmed CPU.
                    def ps():
                        t=time.perf_counter();pixels,seconds=cpu.render(p,4);elapsed=time.perf_counter()-t
                        np.testing.assert_array_equal(pixels,one)
                        return dict(compute_seconds=seconds,end_to_end_seconds=elapsed)
                    def pl():
                        pixels,stats=session.render(p);np.testing.assert_array_equal(pixels,one);return stats
                    if session and repeat%2:pl_stats=pl();ps_stats=ps()
                    else:ps_stats=ps();pl_stats=pl() if session else None
                    samples.append(dict(PS4=ps_stats,PL=pl_stats))
                ps_seconds=float(np.median([s['PS4']['end_to_end_seconds'] for s in samples]))
                pl_seconds=float(np.median([s['PL']['total_seconds'] for s in samples])) if session else None
                row=dict(case=case['name'],shape=[363,640],pose=pose,request_int32=p.tolist(),
                    request_sha256=hashlib.sha256(p.tobytes()).hexdigest(),pixels_sha256=hashlib.sha256(one.tobytes()).hexdigest(),
                    scene_sha256=hashlib.sha256(blob).hexdigest(),all_pixels_normals_targets_contours_exact=True,
                    PS1_compute_seconds=one_seconds,PS4_median_seconds=ps_seconds,PL_median_seconds=pl_seconds,
                    PL_over_PS4_speedup=ps_seconds/pl_seconds if session else None,
                    CPU_dense_unpack_seconds=cpu_preparation,PL_scene_load=load,samples=samples,
                    target_scope='synthetic_sampler_flag_not_clinical_branch_label' if case.get('synthetic_target_mask_for_sampler_only') else 'all_positive_field_voxels')
                rows.append(row);print(json.dumps({k:v for k,v in row.items() if k not in ('samples','request_int32')}),flush=True)
                del one
            del cpu

    if args.hardware:
        with QualitySession(experimental=True) as session:
            for case in cases:
                blob,p,expected=inputs(case);load=session.load(blob)
                for attempt in range(3):
                    pixels,stats=session.render(p);np.testing.assert_array_equal(pixels.ravel(),expected)
                validation.append(dict(case=case['name'],renders=3,all_pixels_exact=True,scene_load=load,latest_frame=stats))
                print('PL fixture passed '+case['name'],flush=True)
            full_frames(session)
        restored=True
    else:full_frames(None)
    assert original_boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    files=['test_board_r7.py','quality_runtime.py','prepare.py','fixtures/manifest.json','results/ARM_reference_r7.json',
           'results/ARM_host_validator_r7.json','build/host_compiled_r7.json']
    proof=dict(status='guarded_C9_board_rendering_exact_full_resolution_PS4_PL_compared_C6_restored' if args.hardware else
        'ARM_PS1_PS4_full_resolution_exact_PL_pending',validation=validation,full_resolution_cases=rows,
        source_and_artifact_sha256={name:sha(ROOT/name) for name in files},boot_id=original_boot,
        peak_test_process_RSS_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        PL_accessed=args.hardware,full_static_1MiB_echo_and_C6_restore_passed=restored,
        static_shell_reloaded=False,PS_Marching_Cubes_used=False,production_UI_promoted=False,
        performance_scope='Warm640x363frames; PL includes transfer/sync/guards; PS includes Python/validation/output and1/4core integer renderer. Coldscene/decode reported separately. Not complete navigation UI FPS.',
        clinical_labels_validated=False)
    if args.hardware:proof['release_manifest_sha256']=sha(ROOT/'release/manifest.json')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=proof['status'],frames=len(rows),C6_restored=restored)),flush=True)


if __name__=='__main__':main()
