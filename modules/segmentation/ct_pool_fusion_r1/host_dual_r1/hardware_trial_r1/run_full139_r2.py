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
HOST = HERE.parent
CORE = HOST.parent
ROOT = HERE.parents[4]


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
    parser.add_argument('--admission', type=Path, default=HERE/'admission.json')
    parser.add_argument('--library', type=Path, default=HOST/'ARM/libct_pool_candidate.so')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input-proof', type=Path, default=HERE/'input_stage_r1/verified.json')
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
    sys.path[:0] = [str(HOST), str(CORE/'integration_r1'), str(ROOT/'modules/segmentation')]
    import numpy as np
    import SimpleITK as sitk
    from backend import PoolXRT, require_trial_admission
    from pool_graph import PoolGraph
    from ct_pl.stream_graph import ContextPreparer
    from airway.ct_geometry import prepare_grid

    if os.uname().machine != 'aarch64':
        raise RuntimeError('Actual aarch64 board required')
    free = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
        if line.startswith('MemAvailable:'))) * 1024
    if free < 1536 * 1024**2:
        raise RuntimeError('At least 1536MiB available board RAM required before XRT opens')
    os.chdir(ROOT/'dfx/medical')
    admission = require_trial_admission(a.admission, a.library)
    gold_path = CORE/'integration_r1/whole139_native/verified.json'
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
    for leaf in ('switches_extended.csv',):
        old = ROOT/'dfx/medical/results'/leaf
        if old.is_file():
            (out/('before_'+leaf)).write_bytes(old.read_bytes())
    b = None
    rows = []
    graph = prepare = value = image = ct = None

    class TracedPool(PoolXRT):
        def __init__(self):
            super().__init__(a.library, a.admission)
            self.trace = []
            self.validation_hash_seconds = 0.0

        def capture(self, index, x):
            tick = time.perf_counter()
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

    try:
        image = prepare_grid(sitk.ReadImage(str(source)))
        ct = sitk.GetArrayFromImage(image)
        assert ct.shape == (139, 512, 512)
        preparation_seconds = time.perf_counter()-started
        b = TracedPool()  # Existing host acquires PL ownership without waiting.
        graph = PoolGraph(ROOT/'modules/segmentation/outputs/ct_accuracy_v2/pl_model', b,
            library=ROOT/'modules/segmentation/ct_pl/build/libct_graph_ops.so')
        assert len(graph.fused_layers) == 8
        assert [v['conv_id'] for v in graph.pl_fused_pools] == [1, 3, 5]
        prepare = ContextPreparer(graph, ct, image.GetSpacing()[2])
        for z, expected in enumerate(gold['cases']):
            assert expected['slice'] == z
            b.trace = []
            calls, pools = b.calls, b.pool_calls
            value = graph(prepare(z))
            digest = hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()
            assert b.trace == expected['convolution_inputs'], ('Full convolution input mismatch', z)
            assert digest == expected['logits_SHA256'], ('Full float32 logit mismatch', z)
            assert (b.calls-calls, b.pool_calls-pools) == (18, 3)
            rows.append(dict(slice=z, convolution_inputs=b.trace, logits_SHA256=digest,
                all18_input_and_full_float32_logit_SHA256_exact=True, actual_PL_pool_calls=3))
            print(json.dumps(dict(slice=z+1,total=139,actual_PL_conv_calls=b.calls,
                actual_PL_pool_calls=b.pool_calls,elapsed_seconds=time.perf_counter()-started)),flush=True)
        assert b.calls == 2502 and b.pool_calls == 417
        hardware_seconds = b.hardware_seconds
        hash_seconds = b.validation_hash_seconds
        pooled_bytes = b.lib.ct_output_pool_bytes(b.handle)
        prepare = graph = value = image = ct = None
        gc.collect()
        b.close()
        for name, expected in bindings.items():
            assert sha(ROOT/name) == expected, name
        switches = ROOT/'dfx/medical/results/switches_extended.csv'
        if switches.is_file():
            (out/'actual_switches.csv').write_bytes(switches.read_bytes())
        save(out/'verified.json',dict(UTC=datetime.now(timezone.utc).isoformat(),
            status='actual_ARM_PoolXRT_full139_2502_inputs139_logits417_pool_calls_exact',
            all139_completed=True,actual_PL_convolution_calls=2502,actual_PL_pool_calls=417,
            all2502_input_SHA256_and139_full_float32_logit_SHA256_exact=True,
            no_PS_convolution_or_pool_fallback=True, no_per_pool_DFX_reload_requested=True,
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
