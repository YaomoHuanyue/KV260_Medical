"""Full own-CT new-C2 trial: original SciPy precision and strongest PS4 API speed."""
from pathlib import Path
import ctypes as C
import hashlib
import json
import resource
import sys
import time
import numpy as np
from trial_backend_FMA2_r1 import Session, verify

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sys.path.insert(0, str(ROOT/'modules/reconstruction'))
from airway.mesh_smoothing import smooth_mesh


def preflight():
    verify()
    old = read(ROOT/'modules/reconstruction/benchmarks/results/own_CT_CPU_board_r1.json')
    legacy = ROOT/'modules/reconstruction/benchmarks/build/libsmooth_cpu_r1.so'
    assert sha(legacy) == old['library_sha256']
    fma_path = ROOT/'results/smoothing_precision_full_r112/acceptance.json'
    fma = read(fma_path)
    assert fma['diagnostic_all_three_within_original_SciPy_tolerance'] and fma['original_5e5_mm_tolerance_unchanged']
    for mapping in [old['source_sha256'], fma['source_and_input_sha256']]:
        for n, d in mapping.items():
            assert sha(ROOT/n) == d, n
    library = ROOT/'results/smoothing_precision_full_r112/libdiagnostic_fma.so'
    assert sha(library) == fma['library_sha256']
    ui = ROOT/'results/pending_external_UI_r96b/full/import_UI.json'
    actual = Path(read(ui)['reconstructed_result'])
    assert actual.is_relative_to(ROOT)
    layers = []
    for name, nv_expected in [('lung', 430918), ('airway', 23280), ('nodule', 3516)]:
        p = actual/'reconstruction'/name
        c = (p/'config.txt').read_text().split()
        nv, nf, nnz = map(int, c[:3])
        assert nv == nv_expected
        limit, iterations = float(c[3]), int(c[4])
        files = [p/'config.txt', *[p/(n+'.bin') for n in ['original', 'rows', 'edges', 'frozen', 'faces']], p/'mesh_before.npz']
        for v in files:
            assert fma['source_and_input_sha256'][v.relative_to(ROOT).as_posix()] == sha(v)
        layers.append((name, p, nv, nf, nnz, limit, iterations, files))
    return old, fma, legacy, library, ui, layers


def main():
    if '--preflight-only' in sys.argv:
        preflight()
        print('Full three-structure inputs, original SciPy/FMA and legacy PS4, full new route and all host gates passed; no PL access', flush=True)
        return
    output = HERE/'results/own_CT_board_FMA2_r1.json'
    assert not output.exists()
    old, fma, legacy, library, ui, layers = preflight()
    L, F = C.CDLL(str(legacy)), C.CDLL(str(library))
    functions = {'legacy': L.smooth_cpu_r1, 'FMA': F.diagnostic_smooth_fma_r112}
    for fn in functions.values():
        fn.argtypes = [C.c_void_p]*11+[C.c_uint32]*3+[C.c_float, C.c_uint32, C.c_int]
        fn.restype = C.c_int
    def actual_clock():
        lines=Path('/sys/kernel/debug/clk/clk_summary').read_text().splitlines()
        found=[line.split() for line in lines if line.split() and line.split()[0]=='pl0_ref']
        assert len(found)==1 and int(found[0][1])>0 and int(found[0][2])>0
        rate=int(found[0][4]);assert abs(rate-100000000)<=100
        return dict(name='pl0_ref',actual_Hz=rate,raw_row=' '.join(found[0]))
    clock_before=actual_clock()
    cases = []
    cold = time.perf_counter()
    session = Session(profile=True)
    restored = False
    try:
        with session:
            open_seconds = time.perf_counter()-cold
            for name, layer, nv, nf, nnz, limit, iterations, files in layers:
                inputs = [np.fromfile(layer/(n+'.bin'), dtype) for n, dtype in
                    [('original', '<f4'), ('rows', '<u4'), ('edges', np.dtype([('index', '<u4'), ('weight', '<f4')])),
                     ('frozen', '<u4'), ('faces', '<u4')]]
                hashes = [hashlib.sha256(v.tobytes()).hexdigest() for v in inputs]
                original = inputs[0].reshape(nv, 4)
                with np.load(layer/'mesh_before.npz', allow_pickle=False) as mesh:
                    points, faces = mesh['points'], mesh['faces']
                np.testing.assert_array_equal(points, original[:, :3])
                np.testing.assert_array_equal(faces, inputs[4].reshape(nf, 4)[:, :3])
                scipy_points, scipy_info = smooth_mesh(points, faces, limit, iterations)
                raw = [np.full(nv*4+128, 0xa5a5a5a5, dtype='<u4') for _ in range(5)]
                buffers = [v[64:-64].view('<f4').reshape(nv, 4) for v in raw]
                rs = np.full(16+128, 0xa5a5a5a5, dtype='<u4')
                status = rs[64:-64]
                target = np.empty((nv, 4), dtype=np.float32)
                report = np.zeros(16, dtype=np.uint32)
                args = [v.ctypes.data for v in inputs+buffers]+[status.ctypes.data]

                def invoke(fn, threads):
                    start = time.perf_counter()
                    rc = fn(*args, nv, nf, nnz, limit, iterations, threads)
                    elapsed = time.perf_counter()-start
                    assert rc == 0 and status[0] == 0
                    for v in raw+[rs]:
                        assert np.all(v[:64] == 0xa5a5a5a5) and np.all(v[-64:] == 0xa5a5a5a5)
                    for v in buffers:
                        assert np.isfinite(v).all() and np.all(v[:, 3] == 0)
                    assert hashes == [hashlib.sha256(v.tobytes()).hexdigest() for v in inputs]
                    return elapsed, buffers[0].copy(), status.copy()

                _, expected, expected_report = invoke(functions['FMA'], 4)
                assert float(np.abs(expected[:, :3]-scipy_points).max(initial=0)) <= 5e-5
                start = time.perf_counter()
                initial = session.run(inputs, target, report, nv, nf, nnz, limit, iterations)
                first_call = time.perf_counter()-start
                first_profile=session.profile_snapshot()
                np.testing.assert_array_equal(target, expected)
                np.testing.assert_array_equal(report, expected_report)
                samples = []
                for repeat in range(3):
                    ps, legacy_error = {}, None
                    for mode, fn in functions.items():
                        for threads in [1, 4]:
                            elapsed, value, words = invoke(fn, threads)
                            ps[mode+str(threads)] = elapsed
                            if mode == 'FMA':
                                delta = np.abs(value[:, :3]-scipy_points)
                                assert float(delta.max(initial=0)) <= 5e-5
                                assert int(words[1]) == scipy_info['accepted_iterations']
                                np.testing.assert_array_equal(value[inputs[3] != 0], original[inputs[3] != 0])
                                np.testing.assert_array_equal(value, expected)
                                np.testing.assert_array_equal(words, expected_report)
                            else:
                                legacy_error = float(np.abs(value[:, :3]-scipy_points).max(initial=0))
                    start = time.perf_counter()
                    phases = session.run(inputs, target, report, nv, nf, nnz, limit, iterations)
                    api = time.perf_counter()-start
                    snapshot=session.profile_snapshot()
                    observation_seconds=snapshot['observation_cycles']/clock_before['actual_Hz']
                    np.testing.assert_array_equal(target, expected)
                    np.testing.assert_array_equal(report, expected_report)
                    assert float(np.abs(target[:, :3]-scipy_points).max(initial=0)) <= 5e-5
                    np.testing.assert_array_equal(target[inputs[3] != 0], original[inputs[3] != 0])
                    assert hashes == [hashlib.sha256(v.tobytes()).hexdigest() for v in inputs]
                    samples.append(dict(repeat=repeat, PS_seconds=ps, PL_adapter_seconds=api, PL_phases_seconds=phases,
                        passive_AXI_counters=snapshot,observation_window_seconds=observation_seconds,
                        observation_includes_host_start_stop_latency=True,wait_counters_may_overlap_and_are_not_a_compute_time_partition=True,
                        full_padded_coordinates_and_all_16_words_exact_FMA=True, original_SciPy_5e5_mm_passed=True,
                        original_legacy_SciPy_error_mm=legacy_error, all_CPU_guards_and_readonly_inputs_passed=True))
                # First call includes allocation and DFX; warm medians never hide this cost.
                ps4 = min(float(np.median([s['PS_seconds'][k] for s in samples])) for k in ['legacy4', 'FMA4'])
                pl = float(np.median([s['PL_adapter_seconds'] for s in samples]))
                cases.append(dict(structure=name, vertices=nv, faces=nf, edges=nnz, samples=samples,
                    first_call_seconds=first_call, first_call_phases=initial, first_call_passive_AXI_counters=first_profile,
                    warm_PL_API_median_seconds=pl, strongest_PS4_median_seconds=ps4,
                    PL_API_speedup_vs_strongest_PS4=ps4/pl, performance_passed=pl <= ps4,
                    original_5e5_mm_SciPy_gate_passed=True, maximum_coordinate_error_vs_FMA_mm=0.0,
                    all_22_full_4096_byte_DMA_red_zones_checked_every_call=True,
                    input_files_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in files}))
                print(json.dumps({k: cases[-1][k] for k in ['structure', 'strongest_PS4_median_seconds', 'warm_PL_API_median_seconds',
                                                          'PL_API_speedup_vs_strongest_PS4', 'performance_passed']}), flush=True)
            saved = int(inputs[1][-1])
            inputs[1][-1] = saved+1
            try:
                session.run(inputs, target, report, nv, nf, nnz, limit, iterations)
                raise AssertionError('Bad CSR was accepted')
            except RuntimeError as e:
                assert 'CSR endpoint' in str(e)
            finally:
                inputs[1][-1] = saved
            session.restore()
            restored = True
    finally:
        if not restored:
            # Only reached after the native DMA call is terminal; it retains active buffers on a timeout.
            sys.path.insert(0, str(ROOT/'dfx/edt_volume'))
            from volume_runtime import VolumeSession
            with VolumeSession(experimental=False) as rescue:
                rescue.return_to_scope()
    clock_after=actual_clock();assert clock_after==clock_before
    passed = all(v['performance_passed'] for v in cases)
    source_files = [Path(__file__), HERE/'runtime_FMA2_r1.py', HERE/'trial_backend_FMA2_r1.py', HERE/'host_streaming_r2140/client.py', legacy, library,
                   ROOT/'modules/reconstruction/airway/mesh_smoothing.py',
                   ROOT/'results/smoothing_precision_full_r112/acceptance.json', ui]
    result = dict(status='all_three_full_SciPy_exact_new_PL_faster_than_strongest_PS4' if passed else
                  'full_SciPy_exact_but_new_PL_still_slower_than_strongest_PS4_on_some_structures', cases=cases,
        actual_clock_before=clock_before,actual_clock_after=clock_after,
        diagnostics_explicitly_enabled=True,profiled_host_API_seconds_include_observer_start_stop=True,
        passive_counter_readout_after_API_timer=True,no_inferred_compute_time_from_overlapping_wait_counters=True,
        single_background_XRT_owner_and_bounded_queue2=True,
        PL_API_timer_includes_enqueue_worker_execution_and_result_delivery=True,
        benchmark_harness_waits_application_submit_close_nonblocking=True,
        cold_verification_and_session_open_seconds=open_seconds, release_manifest_sha256=sha(HERE/'release_FMA2_r1/manifest.json'),
        host_build_sha256=sha(HERE/'host_FMA2_r1/build_ARM/compile_receipt.json'), source_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in source_files},
        original_separate_PS4_precision_failure_retained=True, strongest_PS4_gate_uses_faster_legacy_or_FMA_median=True,
        original_5e5_mm_tolerance_unchanged=True, actual_new_partial_used=True, no_result_cache=True,
        full_static_echo_and_C6_restored=True, malformed_CSR_rejected_before_PL_launch=True,
        peak_process_RSS_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), production_promoted=False, whole_goal_completed=False)
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(result['status'], flush=True)


if __name__ == '__main__':
    main()
