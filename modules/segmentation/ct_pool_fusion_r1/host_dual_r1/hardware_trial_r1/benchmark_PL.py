"""Balanced real-PL and optimized PS whole-producer endpoint comparison.

Requires the actual admitted full139 board proof first. No test backend or
software fallback can replace PoolXRT, and no option installs firmware.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import csv
import ctypes as C
import gc
import hashlib
import json
import os
import statistics
import sys
import time
import traceback
import zipfile

HERE=Path(__file__).resolve().parent;HOST=HERE.parent;CORE=HOST.parent;ROOT=HERE.parents[4]
PS=CORE/'producer_PS_baseline_r1'
PHASES=('input_copy','input_cache_flush','registers_and_first_quant_setup','DMA_compute_completion_wait',
        'output_cache_invalidate','optional_output_copy','output_dirty_cache_flush')


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(p):return json.loads(p.read_text(encoding='utf-8'))


def save(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)


def provider_order(repeat,providers):
    offset=repeat%len(providers);order=list(providers[offset:])+list(providers[:offset])
    return order[::-1] if repeat%2 else order


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--admission',type=Path,default=HERE/'admission.json')
    p.add_argument('--full139-proof',type=Path,default=HERE/'full139_actual_ARM_r2/verified.json')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.admission=a.admission.resolve();a.full139_proof=a.full139_proof.resolve();out=a.output.resolve()
    if not a.full139_proof.is_file():
        raise RuntimeError('Actual admitted full139 PL numerical proof is required before benchmark imports, output or hardware')
    if not out.is_relative_to(ROOT) or out.exists():raise ValueError('Fresh project output directory required')
    protected=read(ROOT/'results/storage_cleanup_20261015/current_dependencies.json')
    def retained(path):
        path=path.resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():raise RuntimeError('Missing project dependency')
        digest=sha(path)
        if protected.get('kv260_system/'+path.relative_to(ROOT).as_posix())!=digest:raise RuntimeError('Unsealed benchmark dependency: '+str(path))
        return digest
    for file in (Path(__file__),a.admission,a.full139_proof,PS/'verified_PC_ARM.json',PS/'ARM_library_extracted.json',PS/'fixture_verified.json'):
        retained(file)
    full=read(a.full139_proof);admission=read(a.admission)
    if not full.get('all139_completed') or full.get('actual_PL_convolution_calls')!=2502 or full.get('actual_PL_pool_calls')!=417:
        raise RuntimeError('Original full139 real PL scope is not qualified')
    if full['source_and_evidence_SHA256'].get(a.admission.relative_to(ROOT).as_posix())!=sha(a.admission):
        raise RuntimeError('Full139 proof belongs to a different admission')
    fixture=PS/'fixture.zip';pslib=PS/'producer_PS_ARM.so';pllib=HOST/'ARM/libct_pool_candidate.so'
    for file in (fixture,pslib,pllib):retained(file)
    if sha(fixture)!=read(PS/'fixture_verified.json')['fixture_SHA256']:raise RuntimeError('Producer fixture mismatch')
    if sha(pslib)!=read(PS/'ARM_library_extracted.json')['library_SHA256']:raise RuntimeError('PS library mismatch')
    if sys.platform!='linux' or os.uname().machine!='aarch64':raise RuntimeError('Actual ARM board required')
    os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['CT_PL_CLEAN_BO']='1'
    sys.path[:0]=[str(HOST),str(ROOT/'modules/segmentation')]
    import numpy as np
    import resource
    from backend import PoolXRT,require_trial_admission
    os.chdir(ROOT/'dfx/medical');require_trial_admission(a.admission,pllib)
    free=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
    if free<1024**3:raise RuntimeError('At least1GiB available RAM required before PL opens')
    resource.setrlimit(resource.RLIMIT_AS,(2048*1024**2,2048*1024**2))
    values=[]
    with zipfile.ZipFile(fixture) as archive:
        manifest=json.loads(archive.read('members_SHA256.json'))
        assert len(archive.namelist())==len(set(archive.namelist())) and set(archive.namelist())==set(manifest)|{'members_SHA256.json'}
        for name,wanted in manifest.items():assert hashlib.sha256(archive.read(name)).hexdigest()==wanted
        meta=json.loads(archive.read('fixture.json'));assert meta['all18_convolution_inputs_and_full_slice_logits_match_original139_reference']
        assert [c['layer'] for c in meta['cases']]==[1,3,5]
        for case in meta['cases']:
            arrays={k:np.frombuffer(archive.read(v['member']),np.dtype(v['dtype'])).reshape(v['shape']) for k,v in case['arrays'].items()}
            qx=arrays['input'][:,:,:case['cin']].transpose(2,0,1)[None]
            guarded=[]
            for name in ('full','pooled'):
                buffer=np.full(arrays[name].nbytes+128,0xA7,np.uint8)
                guarded.append((buffer,buffer[64:-64].view(np.int8).reshape(arrays[name].shape)))
            values.append((case,arrays,qx,guarded))
    L=C.CDLL(str(pslib));ptr=C.c_void_p;u=C.c_uint
    L.producer_create.argtypes=[ptr,ptr,ptr,C.c_float,C.c_int,ptr]+[u]*7;L.producer_create.restype=ptr
    L.producer_execute.argtypes=[ptr,ptr,ptr,ptr];L.producer_execute.restype=C.c_int
    L.producer_close.argtypes=[ptr];L.producer_close.restype=None;L.producer_error.restype=C.c_char_p
    L.producer_neon.restype=u;assert L.producer_neon()==1
    out.mkdir(parents=True);switch_file=ROOT/'dfx/medical/results/switches_extended.csv'
    if switch_file.exists():(out/'before_switches_extended.csv').write_bytes(switch_file.read_bytes())
    bindings={file.relative_to(ROOT).as_posix():sha(file) for file in
        (Path(__file__),a.admission,a.full139_proof,fixture,pslib,pllib,PS/'verified_PC_ARM.json')}
    contexts={};setups={};b=None;started=time.perf_counter();rows={};orders=[];cold={};pl_phases=[]
    providers=('PS_scalar1','PS_scalar4','PS_NEON1','PS_NEON4','PL')
    provider_options={'PS_scalar1':(0,1),'PS_scalar4':(0,4),'PS_NEON1':(1,1),'PS_NEON4':(1,4)}
    try:
        tick=time.perf_counter();b=PoolXRT(pllib,a.admission);pl_open_seconds=time.perf_counter()-tick
        b.lib.ct_last_phase.argtypes=[ptr,u];b.lib.ct_last_phase.restype=C.c_double
        for case,arrays,_,_ in values:b.configure_pool(case['layer'],arrays['table'])
        for provider,(mode,threads) in provider_options.items():
            tick=time.perf_counter()
            for index,(case,data,_,_) in enumerate(values):
                context=L.producer_create(data['weights'].ctypes.data,data['bias'].ctypes.data,data['scale'].ctypes.data,
                    case['qscale'],case['zero'],data['table'].ctypes.data,case['cin'],case['cout'],case['kernel'],
                    case['height'],case['width'],threads,mode)
                assert context,L.producer_error().decode();contexts[(provider,index)]=context
            setups[provider]=time.perf_counter()-tick
        for repeat in range(9):
            order=provider_order(repeat,providers);orders.append(order)
            for provider in order:
                sample=[]
                for index,(case,data,qx,guarded) in enumerate(values):
                    tick=time.perf_counter()
                    if provider=='PL':
                        full_output,pool_output=b.conv_quantized_pool(case['layer'],qx,data['weights'],data['bias'],data['scale'],
                            np.asarray(case['qscale'],np.float32),np.asarray(case['zero'],np.int8))
                        elapsed=time.perf_counter()-tick
                        phase={name:b.lib.ct_last_phase(b.handle,i) for i,name in enumerate(PHASES)}
                        np.testing.assert_array_equal(full_output[0].transpose(1,2,0),data['full'])
                        np.testing.assert_array_equal(pool_output[0].transpose(1,2,0),data['pooled'])
                        full_output=pool_output=None
                    else:
                        rc=L.producer_execute(contexts[(provider,index)],data['input'].ctypes.data,
                            guarded[0][1].ctypes.data,guarded[1][1].ctypes.data)
                        elapsed=time.perf_counter()-tick;assert rc==0,L.producer_error().decode();phase=None
                        for name,(buffer,result) in zip(('full','pooled'),guarded):
                            np.testing.assert_array_equal(result,data[name]);assert np.all(buffer[:64]==0xA7) and np.all(buffer[-64:]==0xA7)
                    sample.append(dict(layer=case['layer'],full_API_seconds=elapsed,native_phases=phase,
                        fullskip_and_pool_exact=True))
                if repeat==0:cold[provider]=sample
                if repeat>=2:rows.setdefault(provider,[]).append(sample)
                print(json.dumps(dict(repeat=repeat+1,provider=provider,group_seconds=sum(x['full_API_seconds'] for x in sample),outputs_exact=True)),flush=True)
        assert b.calls==b.pool_calls==27
        hardware_seconds=b.hardware_seconds;output_pool_bytes=b.lib.ct_output_pool_bytes(b.handle)
        gc.collect();b.close()
        for name,wanted in bindings.items():assert sha(ROOT/name)==wanted,name
        for case,data,_,_ in values:
            for key,meta in case['arrays'].items():assert hashlib.sha256(data[key].tobytes()).hexdigest()==meta['SHA256']
        (out/'actual_switches_extended.csv').write_bytes(switch_file.read_bytes())
        switches=list(csv.DictReader(switch_file.read_text().splitlines()))
        assert len(switches)==1 and switches[0]['rm']=='ct'
        assert 0<float(switches[0]['partial_ms'])<=float(switches[0]['switch_ms'])
        medians={provider:statistics.median(sum(x['full_API_seconds'] for x in group) for group in samples) for provider,samples in rows.items()}
        strongest=min(provider_options,key=lambda n:medians[n]);ratio=medians[strongest]/medians['PL']
        result=dict(UTC=datetime.now(timezone.utc).isoformat(),
            status='actual_balanced_full3_producer_PS_PL_same_precision_complete_dual_outputs_verified',
            samples=rows,warmup_first_calls=cold,balanced_provider_orders=orders,
            median_group_seconds=medians,strongest_PS=strongest,PL_over_strongest_PS_speedup=ratio,
            warm_endpoint_performance_passed=medians['PL']<=medians[strongest],
            PS_context_weight_pack_and_persistent_thread_setup_seconds=setups,
            PL_context_DFX_and_static_device_open_seconds=pl_open_seconds,actual_DFX_rows=switches,
            PL_driver_hardware_wait_seconds=hardware_seconds,PL_native_phase_names=list(PHASES),
            completion_wait_is_DMA_compute_and_polling_not_pure_kernel_counter=True,
            retained_PL_output_pool_bytes_before_close=output_pool_bytes,
            peak_process_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            includes_full_producer_convolution_original_quant_fullskip_and_pool_outputs=True,
            seven_measured_groups_plus_two_warmups_each_and_all_full_outputs_exact=True,
            API_times_include_input_layout_checks_copy_cache_sync_registers_DMA_and_output_visibility=True,
            initialization_and_DFX_reported_separately_not_hidden=True,no_per_pool_partial_reload=True,
            no_whole139_or_complete_system_speedup_claim=True,formal_integration_still_required=True,
            source_and_evidence_SHA256=bindings,total_validation_and_benchmark_seconds=time.perf_counter()-started,
            PL_accessed=True,production_promoted=False,whole_goal_completed=False)
        save(out/'verified.json',result)
    except BaseException:
        save(out/'failure.json',dict(traceback=traceback.format_exc(),source_and_evidence_SHA256=bindings,
            completed_samples=rows,not_complete_performance_qualification=True,
            production_promoted=False,whole_goal_completed=False));raise
    finally:
        if b is not None:b.close()
        for context in contexts.values():L.producer_close(context)


if __name__=='__main__':main()
