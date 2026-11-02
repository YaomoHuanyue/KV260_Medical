"""Real guarded PoolXRT correctness trial on every original own-CT slice.

Hash validation is deliberately inside this correctness run. Its elapsed time
must not be presented as a fair PS/PL performance benchmark.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import gc
import hashlib
import json
import os
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
HOST = HERE.parents[3]/'modules/segmentation/ct_pool_fusion_r1/host_dual_r1'
ROOT = HERE.parents[3]


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def save(p, value):
    with p.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--admission', type=Path, default=CORE/'host_r1/admission.json')
    parser.add_argument('--library', type=Path, default=CORE/'host_r1/ARM_r1/collected/output/libct_tensor_reader.so')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input-proof', type=Path, default=HOST/'hardware_trial_r1/input_stage_r1/verified.json')
    a = parser.parse_args()
    a.admission = a.admission.resolve()
    a.library = a.library.resolve()
    # Refuse a missing admission before importing NumPy, loading a shared
    # library, creating outputs or changing this process's working directory.
    if not a.admission.is_file():
        raise RuntimeError('Actual sealed C5 pool hardware admission is required; no hardware or output opened')
    a.input_proof = a.input_proof.resolve()
    staged = read(a.input_proof)
    protected = read(ROOT/'results/storage_cleanup_20261015/current_dependencies.json')
    if not staged.get('all29_reopened_board_SHA256_exact'):
        raise RuntimeError('Qualified full input and CPU graph library proof required')
    for file in (Path(__file__), a.input_proof):
        if protected.get('kv260_system/'+file.relative_to(ROOT).as_posix()) != sha(file):
            raise RuntimeError('Unsealed trial entry or input proof')
    for name, expected in staged['files'].items():
        if sha(ROOT/name) != expected:
            raise RuntimeError('Board trial runtime input changed: '+name)
    out = a.output.resolve()
    if not out.is_relative_to(ROOT) or out.exists():
        raise ValueError('Fresh output directory inside this project required')
    if sys.platform != 'linux':
        raise RuntimeError('Actual ARM Linux board required')
    import resource
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['CT_PL_CLEAN_BO'] = '1'
    sys.path[:0] = [str(ROOT), str(HOST), str(CORE/'integration_r1'), str(ROOT/'modules/segmentation')]
    import numpy as np
    import SimpleITK as sitk
    from modules.segmentation.axis_tensor_reader_r3.host_r1.backend import ReaderXRT, require_reader_admission
    from modules.segmentation.axis_tensor_reader_r3.graph_r1.reader_graph import ReaderGraph, ReaderInput
    from ct_pl.stream_graph import ContextPreparer
    from airway.ct_geometry import prepare_grid

    if os.uname().machine != 'aarch64':
        raise RuntimeError('Actual aarch64 board required')
    free = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
        if line.startswith('MemAvailable:'))) * 1024
    if free < 1536 * 1024**2:
        raise RuntimeError('At least 1536MiB available board RAM required before XRT opens')
    os.chdir(ROOT/'dfx/medical')
    admission = require_reader_admission(a.admission, a.library)
    gold_path = ROOT/'modules/segmentation/ct_pool_fusion_r1/integration_r1/whole139_native/verified.json'
    gold = read(gold_path)
    if not gold['full139_test_completed'] or len(gold['cases']) != 139:
        raise RuntimeError('Original full139 model reference required')
    for name, expected in gold['source_and_evidence_SHA256'].items():
        if sha(ROOT/name) != expected:
            raise RuntimeError('Original model reference binding changed: '+name)
    source = ROOT/'fixtures/own_ct/CT-chest.nrrd'
    if sha(source) != gold['input_SHA256']:
        raise RuntimeError('Original own CT hash mismatch')
    for name, expected in admission['source_and_evidence_SHA256'].items():
        if sha(ROOT/name) != expected:
            raise RuntimeError('Admitted hardware input changed: '+name)
    resource.setrlimit(resource.RLIMIT_AS, (2048*1024**2, 2048*1024**2))
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(1)
    out.mkdir(parents=True)
    started = time.perf_counter()
    bindings = {str(p.relative_to(ROOT)):sha(p) for p in
        (Path(__file__), a.admission.resolve(), a.library.resolve(), a.input_proof, gold_path, source)}
    before_unique_logs=set((ROOT/'dfx/medical/results').glob('switches_extended_*.csv'))
    for leaf in ('switches_extended.csv',):
        old = ROOT/'dfx/medical/results'/leaf
        if old.is_file():
            (out/('before_'+leaf)).write_bytes(old.read_bytes())
    b = None
    rows = []
    graph = prepare = value = image = ct = None

    class TracedReader(ReaderXRT):
        def __init__(self):
            super().__init__(a.library, a.admission)
            self.trace = []
            self.validation_hash_seconds = 0.0
            self.validation_reader_oracle_seconds = 0.0

        def capture(self, index, x):
            tick = time.perf_counter()
            # Explicit correctness-only PS oracle. Production ReaderXRT does
            # not materialize this array; it reads original BOs in PL. This
            # run includes this cost and must never be sold as speed evidence.
            if isinstance(x,ReaderInput):
                begin=time.perf_counter();parts=[]
                for source,table in zip(x.sources,x.tables):
                    v=table[source.data.view(np.uint8)]
                    if source.factor==2:v=np.repeat(np.repeat(v,2,axis=2),2,axis=3)
                    parts.append(v)
                x=parts[0] if len(parts)==1 else np.concatenate(parts,axis=1)
                self.validation_reader_oracle_seconds+=time.perf_counter()-begin
            self.trace.append(dict(layer=index,
                input_SHA256=hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest(),
                shape=list(x.shape)))
            self.validation_hash_seconds += time.perf_counter()-tick

        def conv_quantized(self, index, x, *args):
            self.capture(index, x)
            return super().conv_quantized(index, x, *args)

        def conv_quantized_pool(self, index, x, *args):
            self.capture(index, x)
            return super().conv_quantized_pool(index, x, *args)

        def conv_quantized_reader(self,index,x,*args):
            self.capture(index,x)
            return super().conv_quantized_reader(index,x,*args)

        def conv_quantized_pool_reader(self,index,x,*args):
            self.capture(index,x)
            return super().conv_quantized_pool_reader(index,x,*args)

    try:
        image = prepare_grid(sitk.ReadImage(str(source)))
        ct = sitk.GetArrayFromImage(image)
        assert ct.shape == (139, 512, 512)
        preparation_seconds = time.perf_counter()-started
        b = TracedReader()  # Existing host acquires PL ownership without waiting.
        graph = ReaderGraph(ROOT/'modules/segmentation/outputs/ct_accuracy_v2/pl_model', b,
            library=ROOT/'modules/segmentation/ct_pl/build/libct_graph_ops.so')
        assert len(graph.fused_layers) == 8
        assert len(graph.reader_quantizations)==7
        assert [v['conv_id'] for v in graph.pl_fused_pools] == [1, 3, 5]
        prepare = ContextPreparer(graph, ct, image.GetSpacing()[2])
        for z, expected in enumerate(gold['cases']):
            assert expected['slice'] == z
            b.trace = []
            calls, pools, readers = b.calls, b.pool_calls, b.reader_calls
            value = graph(prepare(z))
            digest = hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()
            assert b.trace == expected['convolution_inputs'], ('Full convolution input mismatch', z)
            assert digest == expected['logits_SHA256'], ('Full float32 logit mismatch', z)
            assert (b.calls-calls, b.pool_calls-pools,b.reader_calls-readers) == (18,3,6)
            rows.append(dict(slice=z, convolution_inputs=b.trace, logits_SHA256=digest,
                all18_input_and_full_float32_logit_SHA256_exact=True, actual_PL_pool_calls=3,actual_PL_reader_transform_calls=6))
            print(json.dumps(dict(slice=z+1,total=139,actual_PL_conv_calls=b.calls,
                actual_PL_pool_calls=b.pool_calls,elapsed_seconds=time.perf_counter()-started)),flush=True)
        assert b.calls == 2502 and b.pool_calls == 417 and b.reader_calls==834
        hardware_seconds = b.hardware_seconds
        hash_seconds = b.validation_hash_seconds
        pooled_bytes = b.lib.ct_output_pool_bytes(b.handle)
        prepare = graph = value = image = ct = None
        gc.collect()
        b.close()
        for name, expected in bindings.items():
            assert sha(ROOT/name) == expected, name
        unique_logs=set((ROOT/'dfx/medical/results').glob('switches_extended_*.csv'))-before_unique_logs
        own_logs=[p for p in unique_logs if p.name.endswith('_'+str(os.getpid())+'.csv')]
        assert len(own_logs)==1,('One actual C5 session log required',list(map(str,own_logs)))
        switches=own_logs[0]
        (out/'actual_switches.csv').write_bytes(switches.read_bytes())
        fixed=ROOT/'dfx/medical/results/switches_extended.csv'
        if (out/'before_switches_extended.csv').exists():assert sha(fixed)==sha(out/'before_switches_extended.csv')
        save(out/'verified.json',dict(UTC=datetime.now(timezone.utc).isoformat(),
            status='actual_ARM_ReaderXRT_full139_2502_inputs139_logits417_pools834_PL_reader_transforms_exact',
            all139_completed=True,actual_PL_convolution_calls=2502,actual_PL_pool_calls=417,actual_PL_reader_transform_calls=834,
            all2502_input_SHA256_and139_full_float32_logit_SHA256_exact=True,
            no_PS_convolution_or_pool_fallback=True,no_production_PS_reader_transform_fallback=True,
            input_request_hash_for_reader_uses_explicit_correctness_only_PS_oracle=True,
            all_actual_PL_logits_full_bytes_independent_original_oracle_exact=True,
            validation_reader_oracle_seconds=b.validation_reader_oracle_seconds,
            no_per_pool_DFX_reload_requested=True,
            cases=rows,driver_hardware_seconds=hardware_seconds,validation_input_hash_seconds=hash_seconds,
            PS_input_preparation_seconds=preparation_seconds,retained_output_pool_bytes_before_close=pooled_bytes,
            process_peak_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            total_correctness_run_seconds=time.perf_counter()-started,source_and_evidence_SHA256=bindings,
            not_a_fair_PS_PL_speed_benchmark=True,
            strongest_PS1_PS4_fullskip_pool_endpoints_DFX_transfer_cold_warm_and_formal_integration_required=True,
            clinical_GT_accuracy_not_measured=True,PL_accessed=True,production_promoted=False,whole_goal_completed=False))
    except BaseException:
        save(out/'failure.json',dict(traceback=traceback.format_exc(),complete_slices=len(rows),
            source_and_evidence_SHA256=bindings,partial_results_not_full139_pass=True,
            production_promoted=False,whole_goal_completed=False))
        raise
    finally:
        prepare = graph = value = image = ct = None
        gc.collect()
        if b is not None:
            b.close()


if __name__ == '__main__':
    main()
