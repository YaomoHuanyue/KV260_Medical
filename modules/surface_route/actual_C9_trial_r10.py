"""Replay exact R8 original-CT packets/requests on C9 against current ARM PS4."""
from pathlib import Path
import json
import resource
import sys
from time import perf_counter
import traceback
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,digest,write_json
from modules.surface_route.scene_runtime_r9 import SceneSnapshot


def main():
    output=ROOT/'modules/surface_route/results/actual_C9_ARM_r10';output.mkdir(exist_ok=False)
    oracle_root=ROOT/'modules/surface_route/results/reference_frames_ARM_r8'
    oracle=json.loads((oracle_root/'acceptance.json').read_text())
    prior=json.loads((ROOT/'modules/surface_route/work_checkpoint_r8.json').read_text())
    assert sha(oracle_root/'acceptance.json')==prior['evidence_sha256']['modules/surface_route/results/reference_frames_ARM_r8/acceptance.json']
    assert oracle['status']=='eight_original_field_new_route_full_resolution_PS1_PS4_reference_frames_passed'
    for name,expected in {**oracle['source_sha256'],**oracle['reference_bound_files']}.items():
        assert sha(ROOT/name)==expected,name
    qroot=ROOT/'dfx/surface_quality';sys.path.insert(0,str(qroot))
    from quality_runtime import QualitySession,PSReference,verify
    release=verify()
    assert len(oracle['cases'])==8
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    marker=Path('/run/kv260-dfx-medical-loaded.sha256').read_text()
    rows=[];snapshots={};cpu=None;current_blob=None
    start=perf_counter()
    try:
        with QualitySession() as session:
            for original in oracle['cases']:
                label=original['label'];folder=oracle_root/label
                record=json.loads((folder/'report.json').read_text());assert record==original
                for name,expected in record['files_sha256'].items():assert sha(folder/name)==expected,name
                params=np.fromfile(folder/'request.i32','<i4')
                expected=np.fromfile(folder/'reference.u64','<u8').reshape(363,640)
                assert sha(folder/'request.i32')==record['request_sha256'] and sha(folder/'reference.u64')==record['pixels_sha256']
                bundle=ROOT/'modules/surface_route/results/complete_bundles_ARM_r8'/record['bundle_label']
                if str(bundle) not in snapshots:snapshots[str(bundle)]=SceneSnapshot(bundle,record['revision'])
                snapshot=snapshots[str(bundle)]
                request=json.loads((folder/'request.json').read_text());plan=snapshot.frame_plan(request)
                assert digest(plan['scene'])==record['scene_sha256'] and plan['branch_event']==record['scene_event']
                scene_load={};cold_ps=0.
                if record['scene_sha256']!=current_blob:
                    before=perf_counter();cpu=PSReference(plan['scene']);cold_ps=perf_counter()-before
                    scene_load=session.load(plan['scene']);current_blob=record['scene_sha256']
                samples=[];pixels=None
                for repeat in range(3):
                    def ps():
                        before=perf_counter();value,compute=cpu.render(params,4);full=perf_counter()-before
                        np.testing.assert_array_equal(value,expected)
                        return dict(compute_seconds=compute,full_call_seconds=full)
                    def pl():
                        before=perf_counter();value,timing=session.render(params);full=perf_counter()-before
                        np.testing.assert_array_equal(value,expected)
                        assert timing['four_4096_byte_DMA_guards_passed'] and timing['input_and_tokens_checked']
                        return value,dict(timing,measured_full_call_seconds=full)
                    if repeat%2: pixels,hardware=pl();software=ps()
                    else: software=ps();pixels,hardware=pl()
                    samples.append(dict(PS4=software,PL=hardware))
                ps_seconds=float(np.median([s['PS4']['full_call_seconds'] for s in samples]))
                pl_seconds=float(np.median([s['PL']['measured_full_call_seconds'] for s in samples]))
                case=output/label;case.mkdir();pixels.tofile(case/'PL.u64')
                row=dict(label=label,revision=snapshot.revision,route_id=snapshot.meta['route_id'],
                    renderer_scalar_sha256=snapshot.meta['renderer_scalar_sha256'],
                    source_reference_report_sha256=sha(folder/'report.json'),
                    scene_sha256=record['scene_sha256'],request_sha256=record['request_sha256'],
                    expected_pixels_sha256=record['pixels_sha256'],actual_PL_pixels_sha256=sha(case/'PL.u64'),
                    width=640,height=363,max_steps=int(params[2]),every_64bit_depth_normal_coverage_outline_word_exact=True,
                    repeats=3,samples=samples,PS4_median_full_call_seconds=ps_seconds,
                    PL_median_full_call_seconds=pl_seconds,PL_over_PS4_speedup=ps_seconds/pl_seconds,
                    PL_faster_than_PS4=pl_seconds<ps_seconds,cold_PS_dense_unpack_seconds=cold_ps,
                    PL_scene_upload=scene_load,normal_computation='PL_C9',
                    actual_manual_camera_preserved=record['actual_manual_camera_preserved'])
                write_json(case/'report.json',row);rows.append(row)
                print(label,'exact',round(ps_seconds/pl_seconds,2),'x',flush=True)
                del expected,pixels
        assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        assert marker==Path('/run/kv260-dfx-medical-loaded.sha256').read_text()
        proof=dict(status='eight_original_CT_new_route_C9_frames_exact_PS4_compared_C6_restored',
            cases=rows,PL_all_frames_faster_than_PS4=all(r['PL_faster_than_PS4'] for r in rows),
            full_static_1MiB_echo_and_C6_restore_passed=True,PL_access=True,
            release_manifest_sha256=sha(qroot/'release/manifest.json'),
            source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),
                ROOT/'modules/surface_route/scene_runtime_r9.py',ROOT/'modules/surface_route/bundle_reader_r9.py',
                qroot/'quality_runtime.py',qroot/'prepare.py',qroot/'build/host_compiled_r7.json']},
            original_reference_sha256=sha(oracle_root/'acceptance.json'),boot_id=boot,
            peak_test_process_RSS_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
            total_test_seconds=perf_counter()-start,new_bitstream_generated=False,static_shell_reloaded_during_trial=False,
            production_UI_promoted=False,performance_scope='Warm complete 640x363 C9 API vs ARM PS4 API, including copies/sync/guards; excludes scene preparation, file writes and UI display; cold upload/unpack reported separately')
        write_json(output/'acceptance.json',proof)
        print(proof['status'],flush=True)
    except BaseException as error:
        write_json(output/'failure.json',dict(status='trial_failed',error=str(error),completed_cases=rows,traceback=traceback.format_exc()))
        raise


if __name__=='__main__':main()
