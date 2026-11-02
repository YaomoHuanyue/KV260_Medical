"""Compare all five raw work banks, reports and guards against immutable R8 C."""
from pathlib import Path
import ctypes as C
import hashlib
import json
import subprocess
import os
from pathlib import PurePosixPath
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
EDGE = np.dtype([('index', '<u4'), ('weight', '<f4')])


def main():
    platform='Windows' if os.name=='nt' else 'ARM'
    output = HERE / f'results/native_full_banks_{platform}_r2586.json'
    output.parent.mkdir(exist_ok=True)
    assert not output.exists()
    origin=json.loads((HERE/'test_derivation_r2586.json').read_text())
    for key in ['source_and_reference_sha256','candidate_source_sha256']:
        for n,d in origin[key].items():assert sha(ROOT/n)==d,n
    build=HERE/f'build_{platform}';build.mkdir(exist_ok=True)
    ext='.dll' if os.name=='nt' else '.so'
    compiler=(Path('F:/AMDDesignTools/2025.2.1/Vitis/tps/mingw/8.3.0/win64.o/nt/bin/g++.exe') if os.name=='nt' else 'g++')
    flags=[str(compiler),'-std=c++14','-O3','-ffp-contract=off','-DSMOOTH_NATIVE','-shared']
    flags+=['-static-libgcc','-static-libstdc++'] if os.name=='nt' else ['-mcpu=cortex-a53','-fPIC']
    reference_lib=build/('reference'+ext);library=build/('candidate'+ext)
    assert not reference_lib.exists() and not library.exists()
    for cpp,dest in [('reference.cpp',reference_lib),('mesh_smooth.cpp',library)]:
        subprocess.run(flags+[str(HERE/cpp),'-o',str(dest)],check=True)
    directories=[os.add_dll_directory(str(compiler.parent)),os.add_dll_directory(str(build))] if os.name=='nt' else []
    kernels = [C.CDLL(str(p)).mesh_smooth for p in (reference_lib, library)]
    for k in kernels:
        k.argtypes = [C.c_void_p]*11 + [C.c_uint]*3 + [C.c_float, C.c_uint]
        k.restype = None
    cases = []

    def check(name, inputs, nv, nf, nnz, limit, iterations):
        # Guard words and nonzero padding catch writes outside nv and work-bank
        # mistakes, including inactive data left by an orientation-only retry.
        rng = np.random.default_rng(9142026 + len(cases))
        initial = [rng.integers(0, 2**32, size=(nv+64, 4), dtype=np.uint32) for _ in range(5)]
        fingerprints=[hashlib.sha256(v.tobytes()).hexdigest() for v in inputs]
        outputs = []
        for kernel in kernels:
            owned = [v.copy() for v in initial]
            banks = [v[32:32+nv].view(np.float32) for v in owned]
            status_owned=np.full(16+256,0xa5a5a5a5,np.uint32)
            report=status_owned[128:-128];report[:]=0xdeadbeef
            kernel(*[v.ctypes.data for v in inputs+banks], report.ctypes.data,
                   nv, nf, nnz, limit, iterations)
            for actual, seed in zip(owned, initial):
                np.testing.assert_array_equal(actual[:32], seed[:32])
                np.testing.assert_array_equal(actual[32+nv:], seed[32+nv:])
            assert np.all(status_owned[:128]==0xa5a5a5a5) and np.all(status_owned[-128:]==0xa5a5a5a5)
            assert [hashlib.sha256(v.tobytes()).hexdigest() for v in inputs]==fingerprints
            outputs.append((owned, report.copy()))
        for a, b in zip(outputs[0][0], outputs[1][0]): np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(outputs[0][1], outputs[1][1])
        r = outputs[1][1]
        item = dict(name=name, vertices=nv, faces=nf, edges=nnz, iterations=iterations,
                    accepted=int(r[1]), attempts=int(r[4]), all_five_raw_banks_and_padding_exact=True,
                    all_ten_full_512_byte_guards_exact=True, all_16_report_words_exact=True)
        cases.append(item)
        print(json.dumps(item), flush=True)

    for nv in (1, 2, 17, 67, 129, 513, 1031):
        for seed in range(4):
            rng = np.random.default_rng(nv*19+seed)
            points = np.zeros((nv, 4), np.float32)
            points[:, :3] = rng.normal(size=(nv, 3)).astype(np.float32)
            points[:, 3] = np.float32(3.25)
            degrees = rng.integers(0, 10, nv)
            if seed == 3 and nv == 17: degrees[0] = 257
            rows = np.r_[0, np.cumsum(degrees)].astype(np.uint32)
            graph = np.zeros(int(rows[-1]), EDGE)
            graph['index'] = rng.integers(0, nv, len(graph), dtype=np.uint32)
            for v in range(nv):
                if degrees[v]: graph['weight'][rows[v]:rows[v+1]] = np.float32(1.0/degrees[v])
            frozen = (rng.random(nv) < (1.0 if seed == 2 else .13)).astype(np.uint32)
            triangles = np.zeros((0 if seed % 2 else nv // 3, 4), np.uint32)
            if len(triangles): triangles[:, :3] = rng.integers(0, nv, (len(triangles), 3), dtype=np.uint32)
            inputs = [points, rows, graph, frozen, triangles]
            for iterations in (1, 2, 3, 8, 16):
                check(f'synthetic_nv{nv}_seed{seed}_iterations{iterations}', inputs,
                      nv, len(triangles), len(graph), .31, iterations)
    empty = [np.empty((0, 4), np.float32), np.zeros(1, np.uint32), np.empty(0, EDGE),
             np.empty(0, np.uint32), np.empty((0, 4), np.uint32)]
    check('invalid_nv_zero', empty, 0, 0, 0, .31, 1)
    ui = json.loads((ROOT / 'ui/candidates/external_import_r1/HDMI_r1/import_UI.json').read_text())
    actual=ROOT/str(PurePosixPath(ui['reconstructed_result']).relative_to('/home/ubuntu/jupyter_notebooks/KV260_System'))
    for name in ('lung', 'airway', 'nodule'):
        layer = actual / 'reconstruction' / name
        config = (layer / 'config.txt').read_text().split()
        nv, nf, nnz = map(int, config[:3])
        inputs = [np.fromfile(layer / f'{n}.bin', d) for n, d in
                  [('original', '<f4'), ('rows', '<u4'), ('edges', EDGE), ('frozen', '<u4'), ('faces', '<u4')]]
        check('own_CT_'+name, inputs, nv, nf, nnz, float(config[3]), int(config[4]))
    assert len(cases) == 144
    assert any(c['accepted'] > 1 for c in cases)
    assert any(c['accepted'] == 0 and c['attempts'] >= 4 for c in cases)
    assert any(c['attempts'] > c['accepted'] for c in cases)
    record = dict(status='full_integer_medical_core_original_144_complete_bank_cases_exact_independent_std_fma_reference',
                  all_five_banks_and_guards_exact_independent_std_fma=True, cases=cases,
                  candidate_library_sha256=sha(library), reference_library_sha256=sha(reference_lib),
                  source_sha256=origin['candidate_source_sha256'],
                  checker_sha256=sha(Path(__file__)), origin_sha256=sha(HERE / 'test_derivation_r2586.json'),
                  independent_reference_std_fma_only=True,original_case_generation_and_scope_preserved=True,
                  full_report_guards_and_input_readonly_checked=True,platform=platform,
                  PL_access=False, hardware_overlap_verified=False, hardware_speed_measured=False)
    output.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(record['status'], flush=True)


if __name__=='__main__':
    if os.name=='nt':
        import threading,concurrent.futures
        threading.stack_size(64*1024**2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(main).result()
    else:main()

