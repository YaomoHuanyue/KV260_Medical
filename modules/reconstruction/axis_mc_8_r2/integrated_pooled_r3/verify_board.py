"""Review bound actual combined regression and independently reconcile switch logs."""
from pathlib import Path
import csv
import hashlib
import json
import math
import os

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUT=ROOT/'results/MC_AXIS8_FMA2_pooled_board_r3'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):return json.loads(Path(path).read_text())


def main():
    platform='Windows' if os.name=='nt' else 'ARM';destination=OUT/f'verified_{platform}.json'
    assert not destination.exists()
    complete=read(OUT/'complete.json');benchmark=read(OUT/'benchmark.json');receipt=read(OUT/'benchmark_receipt.json')
    assert complete['actual_D7_FMA2_combined_board_executed'] and complete['correctness_passed']
    assert complete['exact_reviewed_case_restored'] and complete['boot_and_static_unchanged']
    assert receipt['exit_code']==0 and receipt['log_SHA256']==sha(OUT/'benchmark.log')
    assert benchmark['actual_D7_FMA2_same_context_passed'] and benchmark['actual_full_and_partial_entries_passed']
    assert benchmark['airway_only_missing_structures_not_fabricated'] and benchmark['boot_and_static_unchanged']
    for field in ['input_SHA256','source_SHA256']:
        for name,digest in benchmark[field].items():assert sha(ROOT/name)==digest,name
    host=ROOT/'modules/reconstruction/axis_mc_8_r2/host_pooled_r2'
    manifest=read(host/'release_r1/manifest.json');assert benchmark['release_manifest_SHA256']==sha(host/'release_r1/manifest.json')
    for name,digest in manifest['runtime_files_SHA256'].items():assert sha(ROOT/name)==digest,name
    assert manifest['smoothing_transport'].startswith('AXI-MM') # Do not call the whole reconstruction AXIS.
    grade=read(HERE.parent/'board_qualification.json');assert grade['actual_board_correctness_passed']
    pool=benchmark['pool_checks']
    assert pool['capacity_grow_then_reuse_passed'] and pool['same_shape_changed_data_then_original_passed']
    assert len(pool['malformed_inputs_refused_before_DMA'])==9
    assert pool['all_FMA_outputs_and16_words_exact'] and pool['all22_red_zones_retained']
    changed=pool['changed_data_reference']
    assert changed['analytic_all_frozen_reference_used'] and not changed['original_SciPy_reference_used']
    assert changed['original_SciPy_max_error_mm'] is None and changed['reference_max_error_mm']==0
    assert changed['report_words'][1]==0
    counts=dict(lung=860680,airway=46520,nodule=6996)
    records=[]
    assert [r['name'] for r in benchmark['cases']]==['full','airway_only']
    for row in benchmark['cases']:
        report=row['report'];session=row['session'];names=['lung','airway','nodule'] if row['name']=='full' else ['airway']
        assert report['status']=='completed' and list(report['layers'])==names
        assert report['mc_kernel']=='AXIS_D7' and report['smoothing_kernel']=='FMA2'
        assert report['mc_scan_voxels_per_iteration']==8
        assert report['partial_switches']==session['partial_switches']==2 and session['xrt_metadata_loads']==1
        assert report['PL_context_reused_for_MC_and_smoothing']
        assert all(math.isfinite(v) and v>0 for v in [report['total_seconds'],report['session_open_seconds'],row['process_wall_seconds']])
        assert row['process_wall_seconds']>report['total_seconds']
        for layer in row['layers']:
            name=layer['name'];s=layer['smoothing'];mc=layer['MC'];smooth=layer['PL_smoothing'];audit=layer['geometry_audit']
            assert layer['MC_exact_optimized_PS4'] and mc['triangles']==counts[name] and mc['generation_passes']==2
            assert s['all_padded_coordinates_and_16_words_exact_FMA'] and s['all22_DMA_red_zones_passed']
            assert 0<=s['original_SciPy_max_error_mm']<=5e-5 and s['CPU_guards_passed']
            assert len(s['report_words'])==16 and s['report_words']==smooth['report_words'] and s['report_words'][0]==0
            assert smooth['kernel']=='FMA2' and smooth['DMA_red_zones_checked']==22
            assert audit['orientation_preserved'] and audit['frozen_vertices_unchanged']
            assert audit['roughness_after_mm']<=audit['roughness_before_mm']+1e-7
            if row['name']=='full':
                expected=next(v for v in grade['full_own_masks'] if v['name']==name)
                assert expected['triangles']==mc['triangles']
                frozen=next(v for v in read(HERE.parent/'native_ARM_r1/verified.json')['own_CT'] if Path(v['mask']).name==name+'_mask.nii.gz')
                assert layer['MC_SHA256']==frozen['case']['produce'][0]['vertices_SHA256']
        records.append(dict(name=row['name'],internal_reconstruction_seconds=report['total_seconds'],
            process_wall_seconds=row['process_wall_seconds'],context_open_seconds=report['session_open_seconds'],
            actual_process_peak_RSS_MiB=session['peak_rss_kib']/1024,partial_switches=2))
    switches={}
    declared=benchmark['DFX_switch_logs'];assert len(declared)==len(set(declared))==3
    for name in declared:
        path=(ROOT/name).resolve();assert path.parent==(host/'results').resolve() and path.name.startswith('switches_reconstruction_')
        rows=list(csv.DictReader(path.open()));mode=[r['rm'] for r in rows]
        for r in rows:
            assert float(r['partial_ms'])>0 and float(r['switch_ms'])>=float(r['partial_ms'])
        assert len({r['sentinel_address'] for r in rows})==1
        if mode==['axis_mc','smooth','axis_mc']:
            kind='tiny';assert int(rows[1]['static_transactions'])-int(rows[0]['static_transactions'])==2
            assert rows[1]['static_transactions']==rows[2]['static_transactions']
        else:
            assert mode==['axis_mc','smooth'];delta=int(rows[1]['static_transactions'])-int(rows[0]['static_transactions'])
            assert delta in [2,6];kind='full' if delta==6 else 'airway_only'
        assert kind not in switches;switches[kind]=dict(path=path.relative_to(ROOT).as_posix(),rows=rows,SHA256=sha(path))
    assert set(switches)=={'tiny','full','airway_only'}
    assert int(switches['full']['rows'][0]['static_transactions'])==int(switches['tiny']['rows'][-1]['static_transactions'])+2
    assert switches['full']['rows'][-1]['static_transactions']==switches['airway_only']['rows'][0]['static_transactions']
    assert read(OUT/'selected_case_timestamps_restored.json')['contents_and_timestamps_restored']
    before=read(OUT/'runtime_identity_before.json');after=read(OUT/'runtime_identity_after.json')
    assert {k for k in set(before)|set(after) if before.get(k)!=after.get(k)}=={'UI_PID','UI_start_ticks','argv'}
    assert after['UI_PID']==complete['restored_UI_PID'] and before['argv'][:-1]==after['argv'][:-1]
    evidence=ROOT/Path(after['argv'][-1]).relative_to('/home/ubuntu/jupyter_notebooks/KV260_System')
    assert read(evidence/'started.json')['runtime']==after and read(evidence/'owned_child.json')['PID']==after['UI_PID']
    paths=[Path(__file__),OUT/'benchmark.json',OUT/'benchmark.log',OUT/'benchmark_receipt.json',OUT/'complete.json',
        OUT/'runtime_identity_before.json',OUT/'runtime_identity_after.json',OUT/'selected_case_timestamps_restored.json',
        host/'release_r1/manifest.json',evidence/'started.json',evidence/'owned_child.json']
    paths += [ROOT/v['path'] for v in switches.values()]
    result=dict(status='actual_combined_D7_FMA2_full_partial_and_restore_verified',platform=platform,
        actual_combined_board_correctness_passed=True,full_and_airway_only_original_voxel_entries_passed=True,
        actual_DFX_switch_log_reconciled=True,completed_static_MC_DMA_frames=12,
        one_XRT_metadata_context_per_reconstruction=True,full_reconstruction_partial_switches=2,
        original_5e5_mm_SciPy_tolerance_unchanged=True,all22_smoothing_DMA_guards_passed=True,
        cases=records,restored_UI_PID=after['UI_PID'],same_reviewed_case_scene_and_ELF_restored=True,
        MC_external_transport='AXIS512',smoothing_external_transport='AXI-MM',
        speed_gate_passed=False,formal_UI_integration_still_pending=True,whole_goal_completed=False,
        evidence_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in paths})
    destination.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
