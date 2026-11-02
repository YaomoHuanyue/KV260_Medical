"""Actual same-context D7/FMA2 and full/airway-only entry regression."""
from pathlib import Path
import argparse
import ctypes as C
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
MODULE=HERE.parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'modules/reconstruction'))
from modules.reconstruction.axis_mc_8_r2.host_pooled_r2.runtime import Session,verify_release,sha
from modules.reconstruction.axis_mc_8_r2.benchmark_board import PS
from modules.reconstruction.axis_mc_8_r2.integrated_pooled_r3.reconstruction import write_smooth_inputs
from fpga.mc_host import to_mesh
from fpga.smooth_host import prepare
from airway.mesh_smoothing import smooth_mesh


def expected_smooth(folder,info,*,all_vertices_frozen=False):
    nv,nf,nnz,limit,iterations=(folder/'config.txt').read_text().split()
    nv,nf,nnz,iterations=int(nv),int(nf),int(nnz),int(iterations);limit=float(limit)
    inputs=[np.fromfile(folder/(name+'.bin'),dtype) for name,dtype in [
        ('original','<f4'),('rows','<u4'),('edges',np.dtype([('index','<u4'),('weight','<f4')])),
        ('frozen','<u4'),('faces','<u4')]]
    raw=[np.full(nv*4+128,0xa5a5a5a5,'<u4') for _ in range(5)]
    buffers=[v[64:-64].view('<f4').reshape(nv,4) for v in raw]
    rs=np.full(16+128,0xa5a5a5a5,'<u4');status=rs[64:-64]
    path=ROOT/'results/smoothing_precision_full_r112/libdiagnostic_fma.so'
    receipt=json.loads((ROOT/'results/smoothing_precision_full_r112/acceptance.json').read_text())
    assert sha(path)==receipt['library_sha256']
    library=C.CDLL(str(path));fn=library.diagnostic_smooth_fma_r112
    fn.argtypes=[C.c_void_p]*11+[C.c_uint32]*3+[C.c_float,C.c_uint32,C.c_int];fn.restype=C.c_int
    started=time.perf_counter()
    assert fn(*[v.ctypes.data for v in inputs+buffers],status.ctypes.data,nv,nf,nnz,limit,iterations,4)==0
    elapsed=time.perf_counter()-started
    for v in raw+[rs]:assert np.all(v[:64]==0xa5a5a5a5) and np.all(v[-64:]==0xa5a5a5a5)
    actual=np.fromfile(folder/'points.f32','<f4').reshape(nv,4)
    np.testing.assert_array_equal(actual,buffers[0]);np.testing.assert_array_equal(status,np.asarray(info['report_words'],'<u4'))
    assert info['DMA_red_zones_checked']==22 and info['kernel']=='FMA2' and status[0]==0
    with np.load(folder/'mesh_before.npz',allow_pickle=False) as mesh:
        points,faces=mesh['points'],mesh['faces']
    if all_vertices_frozen:
        # This fixture adds constraints absent from smooth_mesh's API. Its
        # independent analytic answer is identity, with zero accepted steps.
        assert np.all(inputs[3]==1)
        np.testing.assert_array_equal(points,inputs[0].reshape(nv,4)[:,:3])
        reference=points
        reference_info=dict(accepted_iterations=0)
        np.testing.assert_array_equal(actual,inputs[0].reshape(nv,4))
    else:
        reference,reference_info=smooth_mesh(points,faces,limit,iterations)
    error=float(np.abs(reference-actual[:,:3]).max(initial=0))
    assert error<=5e-5 and int(status[1])==reference_info['accepted_iterations']
    return dict(all_padded_coordinates_and_16_words_exact_FMA=True,CPU_guards_passed=True,
        all22_DMA_red_zones_passed=True,original_SciPy_max_error_mm=None if all_vertices_frozen else error,reference_max_error_mm=error,
        strongest_precision_matched_PS4_compute_seconds=elapsed,PS_timer_includes_guarded_core_only=True,
        PS_timer_not_comparable_to_file_entry_end_to_end=True,vertices=nv,faces=nf,edges=nnz,
        original_SciPy_reference_used=not all_vertices_frozen,analytic_all_frozen_reference_used=all_vertices_frozen,
        points_SHA256=sha(folder/'points.f32'),report_words=list(map(int,status)))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    assert os.geteuid()==0 and os.uname().machine=='aarch64'
    initial_switch_logs={p.name for p in (MODULE/'host_pooled_r2/results').glob('switches_reconstruction_*.csv')}
    manifest=verify_release();ps=PS()
    full=ROOT/'ui/runs/20261017_010952_60e5dd83/segmentation'
    partial=ROOT/'ui/runs/20261016_164114_1e06ceb6/segmentation'
    ct=ROOT/'fixtures/own_ct/CT-chest.nrrd'
    from modules.image_import.partial_r1.contracts import validate_selected_masks
    declaration,_=validate_selected_masks(ct,partial.parent);assert declaration['declared_structures']==['airway']
    bound=[ct,*[full/f'{n}_mask.nii.gz' for n in ['lung','airway','nodule']],partial/'report.json',partial/'airway_mask.nii.gz']
    for path in bound:assert path.is_file()
    if args.preflight_only:print('PASS combined release/firmware/full/partial preflight; PL not accessed',flush=True);return
    assert args.output is not None
    output=args.output.resolve();assert output.is_relative_to(ROOT/'results') and not output.exists()
    work=output.parent/'jobs';assert not work.exists();work.mkdir()
    boot=Path('/proc/sys/kernel/random/boot_id').read_text();static=Path('/run/kv260-dfx-medical-loaded.sha256').read_text()
    started=time.perf_counter()
    mask=np.zeros((16,16,16),np.uint8);mask[4:12,4:12,4:12]=1
    expected,_=ps.run(mask,4);tiny=work/'small';tiny.mkdir()
    with Session() as session:
        vertices,details=session.reconstruct(mask);np.testing.assert_array_equal(vertices,expected)
        points,faces=to_mesh(vertices,(1,1,1),(0,0,0),np.eye(3),np.zeros(3,int))
        np.savez(tiny/'mesh_before.npz',points=points,faces=faces)
        write_smooth_inputs(tiny,prepare(points,faces,.1,8))
        info=session.run('smooth',tiny,tiny/'points.f32',tiny/'smooth.json')
        small_smooth=expected_smooth(tiny,info)
        from modules.reconstruction.axis_mc_8_r2.integrated_pooled_r3.pool_checks import exercise_pool
        pool_checks=exercise_pool(session,tiny,info,ps,expected_smooth,work)
        again,_=session.reconstruct(mask);np.testing.assert_array_equal(again,expected)
        small_context=session.report(tiny/'session.json')
        assert small_context['partial_switches']==3 and small_context['xrt_metadata_loads']==1
    print('PASS actual same-context D7 -> FMA2 -> D7, full guards and exact outputs',flush=True)
    rows=[]
    expected_own=json.loads((MODULE/'native_ARM_r1/verified.json').read_text())['own_CT']
    for name,source,entry,names in [('full',full,'run_reconstruction.py',['lung','airway','nodule']),
            ('airway_only',partial,'run_partial.py',['airway'])]:
        destination=work/name;command=[sys.executable,'-B','-X','utf8',str(HERE/entry),
            '--ct',str(ct),'--mask-dir',str(source),'--output',str(destination)]
        start=time.perf_counter()
        with (work/(name+'.log')).open('xb') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        wall=time.perf_counter()-start
        report=json.loads((destination/'report.json').read_text());context=json.loads((destination/'session.json').read_text())
        assert report['status']=='completed' and list(report['layers'])==names
        assert context['partial_switches']==2 and context['xrt_metadata_loads']==1
        assert context['mc_backend']=='DFX_PL_MC_AXIS_D7' and context['smooth_backend']=='DFX_PL_FMA2'
        assert context['boot_id']==boot.strip()
        layers=[]
        for structure in names:
            folder=destination/structure;mc=report['layers'][structure]['mc'];smooth=report['layers'][structure]['smooth']
            dims=tuple(map(int,(folder/'dimensions.txt').read_text().split()))
            data=np.fromfile(folder/'mask.u8',np.uint8).reshape(dims[::-1]);reference,_=ps.run(data,4)
            actual=np.fromfile(folder/'vertices.u64','<u8');np.testing.assert_array_equal(actual,reference)
            assert mc['kernel']=='AXIS_D7' and mc['generation_passes']==2 and actual.size==mc['triangles']*3
            if name=='full':
                old=next(v for v in expected_own if Path(v['mask']).name==structure+'_mask.nii.gz')
                assert sha(folder/'vertices.u64')==old['case']['produce'][0]['vertices_SHA256']
            assert smooth['intermediate_input_vector_bytes']==0
            expected_allocations=11 if structure==names[0] else 0
            assert smooth['pool_allocations_this_call']==expected_allocations
            assert smooth['pool_reused_buffers_this_call']==11-expected_allocations
            assert smooth['host_scope_includes_input_read_validation_and_heap_release']
            assert all(np.isfinite(value) and value>=0 for value in smooth['phase_seconds'].values())
            regression=expected_smooth(folder,smooth)
            with np.load(destination/(structure+'.npz'),allow_pickle=False) as model:
                np.testing.assert_array_equal(model['points'],np.fromfile(folder/'points.f32','<f4').reshape(-1,4)[:,:3])
                assert np.isfinite(model['normals']).all() and model['faces'].shape==(mc['triangles'],3)
            layers.append(dict(name=structure,MC_exact_optimized_PS4=True,MC_SHA256=sha(folder/'vertices.u64'),
                smoothing=regression,MC=mc,PL_smoothing=smooth,geometry_audit=report['layers'][structure]['audit']))
        if name=='airway_only':
            for absent in ['lung','nodule']:assert not (destination/(absent+'.npz')).exists()
        rows.append(dict(name=name,command=command,process_wall_seconds=wall,report=report,session=context,layers=layers,
            unavailable_structures_preserved=name=='airway_only',report_SHA256=sha(destination/'report.json')))
        print('PASS actual reconstruction',name,'wall seconds',wall,'internal',report['total_seconds'],flush=True)
    assert boot==Path('/proc/sys/kernel/random/boot_id').read_text() and static==Path('/run/kv260-dfx-medical-loaded.sha256').read_text()
    switch_logs=sorted(p for p in (MODULE/'host_pooled_r2/results').glob('switches_reconstruction_*.csv') if p.name not in initial_switch_logs)
    assert len(switch_logs)==3
    sources=[Path(__file__),HERE/'reconstruction.py',HERE/'run_reconstruction.py',HERE/'run_partial.py',HERE/'pool_checks.py',HERE/'derivation.json',MODULE/'host_pooled_r2/runtime.py',*switch_logs]
    record=dict(actual_D7_FMA2_same_context_passed=True,actual_full_and_partial_entries_passed=True,
        full_three_layers_exact_MC_FMA_and_original_SciPy=True,airway_only_missing_structures_not_fabricated=True,
        DFX_switch_logs=[p.relative_to(ROOT).as_posix() for p in switch_logs],tiny_transition=['D7','FMA2','D7'],tiny_context=small_context,tiny_smoothing=small_smooth,pool_checks=pool_checks,cases=rows,
        input_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in bound},
        source_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in sources},
        release_manifest_SHA256=sha(MODULE/'host_pooled_r2/release_r1/manifest.json'),
        boot_and_static_unchanged=True,total_test_seconds=time.perf_counter()-started,
        controller_process_peak_RSS_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        production_promoted=False,whole_goal_completed=False)
    output.write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':main()
