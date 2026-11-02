"""One explicit Conv15 boundary probe, using the admitted D6/C5 transaction.

Local read-only preflight: python -B tools/ct_reader_probe.py inspect --root ROOT
Board, only after the controller stages and pins this file as worker.py:
  python -B WORK/worker.py probe --plan WORK/plan.json --plan-sha256 SHA256
The controller owns namespace setup, transfer, process lifecycle and collection.
This worker neither connects to a host nor replaces production files/admissions.
"""
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
import argparse
import ast
import copy
import gc
import hashlib
import importlib.util
import inspect
import json
import math
import os
import re
import statistics
import sys
import threading
import time
import traceback
import zipfile

SCHEMA = 'kv260.conv15.reader_probe.v1'
PHASE = 'reader_operator'
CT = 'fixtures/own_ct/CT-chest.nrrd'
CT_SHA = '4507b664690840abb6cb9af2d919377ffc4ef75b167cb6fd0f747befdb12e38e'
MODEL = 'modules/segmentation/outputs/ct_accuracy_v2/pl_model'
MODEL_PINS = {
    'graph.json': '038ecc73f6fe6805a64af153f31e222453d2bfe7d90a7cddf076862904329eb3',
    'tensors.npz': '9c57169691fe8f961f71d595f2b0acfe03c9742de9e7c222e0d3a2dd9b6898ad',
}
LUT_SHA = (
    '1e839df23766b4e382460c49acede7223eb0fe975da9c70a1f75e36a1da7093b',
    '2acb03ba7520467636273208563f8e733494748f4aa5ac2dba89d9560050da79',
)
Q_INPUT = '/up0/Concat_output_0_QuantizeLinear_Output'
Q_SCALE = '/up0/Concat_output_0_scale'
Q_ZERO = '/up0/Concat_output_0_zero_point'
ADMISSION = 'modules/segmentation/mixed_r30/candidate_r2.json'
SETUP_OPTIONS = dict(rounds=8, min_MemAvailable_bytes=1536*1024**2,
    min_CmaFree_bytes=128*1024**2, max_output_BO_pool_bytes=192*1024**2,
    boundary_BO_budget_bytes=32*1024**2)
PHASES = ('input_copy', 'input_sync', 'control', 'pl_wait', 'output_sync',
          'output_copy', 'output_prepare_sync')
EXTRA_SOURCES = {
    ADMISSION, 'modules/segmentation/mixed_r30/admission.py',
    'modules/segmentation/mixed_r30/segmentation.py',
    'modules/segmentation/ct_pl/runtime.py',
    'modules/segmentation/ct_pl/native_graph.py',
    'modules/segmentation/ct_pl/quantized_runtime.py',
    'modules/segmentation/ct_pl/stream_graph.py',
    'modules/segmentation/ct_pl/fused_graph.py',
    'modules/segmentation/ct_pl/build/libct_graph_ops.so',
    'modules/segmentation/axis_tensor_reader_r3/graph_r1/reader_graph.py',
    'modules/segmentation/axis_tensor_reader_r3/host_r1/backend.py',
    'modules/segmentation/axis_tensor_reader_r3/host_r1/admission.json',
    'modules/segmentation/axis_tensor_reader_r3/host_r1/ARM_r1/collected/output/libct_tensor_reader.so',
    'modules/segmentation/axis_tensor_reader_r3/streaming_r1/entry.py',
    'modules/segmentation/axis_tensor_reader_r3/streaming_r1/functional.py',
    'modules/segmentation/ct_pool_fusion_r1/R7_board_r1/backend.py',
    'modules/ct_preprocess/axis_hu_32_r2/integrated_r1/pl_context.py',
    'modules/ct_preprocess/axis_hu_32_r2/integrated_r1/prepare.py',
    'modules/ct_preprocess/axis_hu_32_r2/bounded_volume_r3/runtime.py',
    'modules/ct_preprocess/axis_hu_32_r2/bounded_volume_r2/runtime.py',
    'system/partial_transaction_r1.py', 'ui/v2/runtime.py', 'ui/v2/manifest.json',
    'ui/active_release.json', 'ui/run.sh', *(MODEL+'/'+n for n in MODEL_PINS),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def relative_name(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name,
            'A simple project-relative POSIX path is required')
    p = PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and str(p) == name,
            'Unnormalized or escaping source path')
    return name


def bound(root, name):
    p = root / relative_name(name)
    require(not p.is_symlink(), 'Symlink source is forbidden: '+name)
    p = p.resolve(strict=True)
    require(p.is_relative_to(root) and p.is_file(), 'Unbound source: '+name)
    return p


def required_sources(root):
    return sorted(EXTRA_SOURCES | set(read(root/ADMISSION)['source_SHA256']))


def plan_values(plan, work, root, script_name, required):
    require(work.parent == root/'results' and work.name.startswith('owned_ct_baseline_reader_'),
            'An owned reader-probe results directory is required')
    require(plan.get('owned_root') == str(work), 'Plan belongs to another owned root')
    require(plan.get('worker_schema') == SCHEMA and plan.get('phase') == PHASE,
            'Wrong worker schema or phase')
    require(plan.get('CT_SHA256') == CT_SHA, 'Only the original own CT is admitted')
    require(plan.get('new_FPGA_build') is False and plan.get('new_bit') is False
            and plan.get('production_promoted') is False, 'Same-bit unpromoted probe required')
    rounds = plan.get('rounds')
    require(type(rounds) is int and 1 <= rounds <= 32, 'rounds must be from1 to32')
    for key in ('min_MemAvailable_bytes', 'min_CmaFree_bytes', 'boundary_BO_budget_bytes'):
        require(type(plan.get(key)) is int and plan[key] >= SETUP_OPTIONS[key],
                'Memory floor cannot be lowered: '+key)
    require(type(plan.get('max_output_BO_pool_bytes')) is int
            and 32*1024**2 <= plan['max_output_BO_pool_bytes'] <= 256*1024**2,
            'Invalid bounded output-pool budget')
    require(plan.get('boundary_BO_budget_bytes') == 32*1024**2,
            'The fixed boundary reserve is32MiB')
    owner = plan.get('observed_UI', {})
    require(all(type(owner.get(k)) is int and owner[k] > 0 for k in ('PID', 'ticks')),
            'Exact UI PID/start ticks required')
    require(re.fullmatch('[0-9a-f]{64}', owner.get('SHA256', '')) is not None,
            'Exact UI ELF SHA required')
    require(isinstance(plan.get('boot'), str) and len(plan['boot']) == 36, 'Boot identity required')
    sources, staged = plan.get('source_SHA256', {}), plan.get('staged_files_SHA256', {})
    require(set(required) <= set(sources), 'Source closure is incomplete')
    require({script_name, 'namespace.py'} <= set(staged), 'Worker/namespace pins required')
    for mapping in (sources, staged):
        require(isinstance(mapping, dict), 'Source hashes must be a mapping')
        for name, digest in mapping.items():
            relative_name(name)
            require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest) is not None,
                    'Invalid source hash: '+name)


def source_checks(root):
    """Parse current interfaces without importing NumPy, CDLL, XRT or a backend."""
    evidence = []
    tests = [
        ('modules/segmentation/axis_tensor_reader_r3/host_r1/backend.py', 'ReaderXRT',
         'conv_quantized_reader', ['self','index','x','w','bias','scale','qscale','zero']),
        ('modules/segmentation/ct_pl/stream_graph.py', 'StreamGraph',
         'quantize', ['self','value','scale','zero','axis']),
        ('modules/ct_preprocess/axis_hu_32_r2/integrated_r1/pl_context.py',
         'PLContextPreparer', '__init__', ['self','graph','quantized','metadata','spacing_z']),
    ]
    for name, cls, method, arguments in tests:
        p = bound(root, name);tree = ast.parse(p.read_text())
        c = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
        f = next(n for n in c.body if isinstance(n, ast.FunctionDef) and n.name == method)
        require([a.arg for a in f.args.args] == arguments, 'Changed real interface: '+method)
        evidence.append(dict(path=name, line=f.lineno, signature=arguments, SHA256=sha(p)))
    stage = bound(root, 'modules/segmentation/axis_tensor_reader_r3/streaming_r1/entry.py')
    tree = ast.parse(stage.read_text());run = next(n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == 'run')
    text = ast.get_source_segment(stage.read_text(), run)
    require(text.count('report=qualified.run_worker(args,prepared,record)') == 1,
            'Changed sealed transaction callback')
    for leaf, expected in MODEL_PINS.items():
        require(sha(bound(root, MODEL+'/'+leaf)) == expected, 'Changed frozen model')
    model = read(root/MODEL/'graph.json')
    conv = [n for n in model['nodes'] if n.get('integer',{}).get('id') == 15]
    require(len(conv) == 1 and conv[0]['op'] == 'Conv', 'Exactly one model Conv15 required')
    c = conv[0]['integer']
    require({'id','input','weights','bias','input_scale','weight_scale','kernel'} <= set(c)
            and c['input'] == Q_INPUT and c['input_scale'] == Q_SCALE and c['kernel'] == 3,
            'Changed model Conv15 integer boundary')
    require(conv[0]['attrs'] == dict(dilations=[1,1],group=1,kernel_shape=[3,3],
            pads=[1,1,1,1],strides=[1,1]), 'Changed model Conv15 attrs')
    q = [n for n in model['nodes'] if Q_INPUT in n['outputs']]
    require(len(q) == 1 and q[0]['op'] == 'QuantizeLinear'
            and q[0]['inputs'] == ['/up0/Concat_output_0',Q_SCALE,Q_ZERO],
            'Changed model join quantizer')
    join = [n for n in model['nodes'] if '/up0/Concat_output_0' in n['outputs']]
    require(len(join) == 1 and join[0]['op'] == 'Concat' and join[0]['attrs'] == {'axis':1}
            and join[0]['inputs'] == ['/up0/reduce/Conv_output_0_DequantizeLinear_Output',
                                     '/enc0/enc0.5/Relu_output_0'], 'Changed model source order')
    with zipfile.ZipFile(root/MODEL/'tensors.npz') as archive:
        require({n+'.npy' for n in (c['weights'],c['bias'],c['input_scale'],c['weight_scale'],Q_ZERO)}
                <= set(archive.namelist()), 'Model parameter key missing')
    evidence.append(dict(path=MODEL+'/graph.json',layer=15,integer_input=Q_INPUT,
                         exact_attrs_and_source_order_checked=True,parameter_keys_present=True))
    evidence.append(dict(path=str(stage.relative_to(root)).replace('\\','/'),
        line=run.lineno, callback_count=1, SHA256=sha(stage)))
    return evidence


def guard_selfcheck(root, required):
    """Reject plan/path mutations without files, processes, imports or hardware."""
    work = root/'results/owned_ct_baseline_reader_selfcheck'
    p = dict(owned_root=str(work), worker_schema=SCHEMA, phase=PHASE, CT_SHA256=CT_SHA,
        new_FPGA_build=False, new_bit=False, production_promoted=False,
        observed_UI=dict(PID=1,ticks=1,SHA256='0'*64),boot='0'*36,
        source_SHA256={n:'0'*64 for n in required},
        staged_files_SHA256={'worker.py':'0'*64,'namespace.py':'0'*64}, **SETUP_OPTIONS)
    plan_values(p, work, root, 'worker.py', required)
    mutations = [('phase','pipeline'),('CT_SHA256','1'*64),('new_bit',True),
        ('production_promoted',True),('rounds',0),('rounds',True),
        ('min_CmaFree_bytes',0),('max_output_BO_pool_bytes',1024**3),
        ('boundary_BO_budget_bytes',0),('source_SHA256',{}),
        ('staged_files_SHA256',{'worker.py':'0'*64}),('owned_root',str(root))]
    for key, value in mutations:
        q = copy.deepcopy(p);q[key] = value
        try:plan_values(q, work, root, 'worker.py', required)
        except (ValueError, TypeError):pass
        else:raise AssertionError('Guard accepted mutation: '+key)
    for bad in ('../escape','/absolute','C:/escape','dir\\escape','dir/../escape'):
        try:relative_name(bad)
        except ValueError:pass
        else:raise AssertionError('Guard accepted path: '+bad)
    return dict(valid_plan_accepted=True, negative_plan_cases=len(mutations),
        negative_path_cases=5, hardware_opened=False, files_written=False)


def inspect_local(root):
    root = Path(root).resolve(strict=True);required = required_sources(root)
    return dict(worker_schema=SCHEMA, phase=PHASE, required_sources=required,
        setup_options=SETUP_OPTIONS, CT_relative=CT, CT_SHA256=CT_SHA,
        required_plan_fields=['owned_root','worker_schema','phase','source_SHA256',
            'staged_files_SHA256','CT_SHA256','observed_UI','boot','new_FPGA_build',
            'new_bit','production_promoted',*SETUP_OPTIONS],
        interface_evidence=source_checks(root), guard_selfcheck=guard_selfcheck(root,required),
        execution='probe --plan WORK/plan.json --plan-sha256 SHA256',
        worker_SHA256=sha(__file__), production_modified=False)


def memory_sample(backend=None):
    import resource
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.split(':')[0] in ('MemAvailable','CmaFree','CmaTotal'):
            values[line.split(':')[0]+'_bytes'] = int(line.split()[1])*1024
    values['process_RSS_bytes'] = int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
    values['process_RSS_peak_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    if backend is not None:
        values['output_BO_pool_bytes'] = int(backend.lib.ct_output_pool_bytes(backend.handle))
    return values


def memory_guard(plan, backend=None, allocation_reserve=0):
    v = memory_sample(backend)
    require(v['MemAvailable_bytes'] >= plan['min_MemAvailable_bytes'], 'Insufficient available RAM')
    require(v['CmaFree_bytes'] >= plan['min_CmaFree_bytes']+allocation_reserve,
            'Insufficient CMA reserve; leave the UI and other jobs alone')
    if backend is not None:
        require(v['output_BO_pool_bytes'] <= plan['max_output_BO_pool_bytes'], 'BO-pool budget exceeded')
    return v


def load_v2(root):
    spec = importlib.util.spec_from_file_location('reader_probe_v2_runtime',root/'ui/v2/runtime.py')
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def check_ui(plan, root):
    v2 = load_v2(root);manifest = v2.verify(installed=True);rows = v2.running()
    require(len(rows) == 1, 'One unchanged current V2 UI is required')
    row = rows[0];expected = plan['observed_UI']
    require(all(row[k] == expected[k] for k in ('PID','ticks','SHA256'))
            and row['SHA256'] == manifest['binary_sha256'], 'UI identity changed')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == plan['boot'], 'Board rebooted')
    ui = Path('/proc')/str(row['PID'])
    require(all(not (t/'children').read_text().strip() for t in (ui/'task').iterdir()),
            'The UI has an active child task')
    require(not any('/libxrt' in s or '/dev/dri/render' in s
                    for s in (ui/'maps').read_text().splitlines()), 'The live UI is using PL/GPU rendering')
    return {k:row[k] for k in ('PID','ticks','SHA256','exe')}


def verify_plan(path, digest):
    work = Path(__file__).resolve().parent;root = work.parent.parent
    path = Path(path).resolve(strict=True)
    require(path == work/'plan.json' and sha(path) == digest, 'Original owned plan SHA required')
    plan = read(path);plan_values(plan,work,root,Path(__file__).name,required_sources(root))
    for base, mapping in ((root,plan['source_SHA256']),(work,plan['staged_files_SHA256'])):
        for name, expected in mapping.items():
            require(sha(bound(base,name)) == expected, 'Changed bound source: '+name)
    require(sha(bound(root,CT)) == CT_SHA, 'Own CT changed')
    source_checks(root)
    sys.path[:0] = [str(root),str(root/'modules/segmentation'),str(root/'dfx/medical')]
    from modules.segmentation.mixed_r30.admission import verify
    verify(root/ADMISSION,plan['source_SHA256'][ADMISSION])
    return work,root,plan


def lease_present(array, backend):
    pending = [array];seen = set()
    while pending:
        value = pending.pop()
        if id(value) in seen:continue
        seen.add(id(value));lease = getattr(value,'_lease',None)
        if lease is not None:
            return bool(lease.handle) and lease.lib is backend.lib
        for name in ('base','obj'):
            x = getattr(value,name,None)
            if x is not None:pending.append(x)
    return False


def probe_worker(args, prepared, record, root, work, plan):
    import numpy as np
    from ct_pl.fused_graph import FusedGraph
    from ct_pl.quantized_runtime import Concatenated
    from ct_pl.stream_graph import Deferred
    from ct_pl.runtime import pack_input
    from modules.segmentation.axis_tensor_reader_r3.graph_r1.reader_graph import ReaderGraph,ReaderInput
    from modules.segmentation.axis_tensor_reader_r3.host_r1 import backend as native
    from modules.ct_preprocess.axis_hu_32_r2.integrated_r1.pl_context import PLContextPreparer

    require(prepared['quantized'].shape == (139,512,512), 'Original full139 CT grid required')
    owner_thread = threading.get_ident();cap = {};samples = [];rows = []
    backend = graph = context = cat = original_x = oracle = None
    def fingerprint(a):
        hwc = a[0].transpose(1,2,0)
        require(hwc.flags.c_contiguous, 'Captured BO must retain HWC-contiguous storage')
        return hashlib.sha256(memoryview(hwc).cast('B')).hexdigest()
    class CapturingReader(native.ReaderXRT):
        capture_active = True
        budget_checks_in_allocation = True
        def _mapped_array(self,shape):
            if self.budget_checks_in_allocation:
                samples.append(memory_guard(plan,self,int(np.prod(shape))+plan['boundary_BO_budget_bytes']))
            value = super()._mapped_array(shape)
            if self.budget_checks_in_allocation:samples.append(memory_guard(plan,self))
            return value
        def conv_quantized(self,index,x,*other):
            require(threading.get_ident() == owner_thread, 'Probe must remain single-threaded')
            y = super().conv_quantized(index,x,*other)
            if self.capture_active and index == 15:
                require('params' not in cap and x is cap.get('joined'), 'Ambiguous Conv15 capture')
                cap.update(params=other,output=y)
            return y
    class CapturingGraph(FusedGraph):
        capture_active = True
        join_calls = 0
        def quantize(self,value,scale,zero,axis=1):
            selected = scale is self.arrays[Q_SCALE] and zero is self.arrays[Q_ZERO]
            if selected:
                require(isinstance(value,Concatenated) and value.axis == axis == 1
                        and len(value.values) == 2, 'Changed Conv15 channel join')
                self.join_calls += 1
                if self.capture_active:
                    require('cat' not in cap, 'Repeated Conv15 quantizer capture')
                    cap.update(cat=value,source_before=[fingerprint(v.data) for v in value.values])
            result = super().quantize(value,scale,zero,axis)
            if selected and self.capture_active:cap['joined'] = result
            return result
    try:
        samples.append(memory_guard(plan,allocation_reserve=plan['boundary_BO_budget_bytes']))
        backend = CapturingReader(root/record['pool_library'],root/record['proofs']['pool_hardware_admission']['path'])
        require(hasattr(backend.lib,'ct_last_phase'), 'Seven native timing phases required')
        graph = CapturingGraph(root/MODEL,backend,root/'modules/segmentation/ct_pl/build/libct_graph_ops.so')
        conv = [n for n in graph.nodes if n.get('integer',{}).get('id') == 15]
        require(len(conv) == 1 and conv[0]['op'] == 'Conv' and conv[0].get('fused_activation')
                and conv[0]['integer']['input'] == Q_INPUT, 'Changed fused Conv15 boundary')
        require(len(graph.fused_layers) == 8 and sum(n['op']=='PoolQuantize' for n in graph.nodes) == 3,
                'Original eight activations and three PS pool boundaries required')
        require(conv[0]['attrs'] == dict(dilations=[1,1],group=1,kernel_shape=[3,3],pads=[1,1,1,1],strides=[1,1]),
                'Changed Conv15 convolution attrs')
        graph.return_quantized = True
        context = PLContextPreparer(graph,prepared['quantized'],prepared['metadata'],prepared['image'].GetSpacing()[2])
        prediction = graph(context(69));del prediction;context = None
        backend.capture_active = graph.capture_active = False
        require(backend.calls == 18 and backend.pool_calls == backend.reader_calls == 0
                and graph.join_calls == 1 and set(cap) == {'cat','source_before','joined','params','output'},
                'Exactly one original18-convolution capture required')
        cat,original_x = cap['cat'],cap['joined'];params = cap['params']
        require(original_x.shape == (1,32,512,512) and original_x.dtype == np.int8, 'Changed reference input')
        require(params[0].shape == (16,32,3,3) and params[0].dtype == np.int8, 'Changed Conv15 weights')
        require(params[1].shape == (16,) and params[1].dtype == np.int32
                and params[2].shape == (16,) and params[2].dtype == np.float32,
                'Changed captured bias/FP32 scale')
        require(cap['output'].shape == (1,16,512,512) and cap['output'].dtype == np.int8,
                'Changed original Conv15 output')
        oracle = np.array(cap.pop('output'),copy=True,order='C');oracle.flags.writeable = False
        qs,qz = graph.arrays[Q_SCALE],graph.arrays[Q_ZERO]
        require(qs.dtype == np.float32 and qs.size == 1 and float(qs.item()) == 0.06644701212644577
                and qz.dtype == np.int8 and qz.size == 1 and qz.item() == 0, 'Changed join quantization')
        expected_scales = (0.03798731416463852,0.06644701212644577)
        for i,v in enumerate(cat.values):
            require(v.data.shape == (1,16,512,512) and v.data.dtype == np.int8
                    and getattr(v,'factor',1) == 1 and bool(getattr(v,'clamp',False)) == bool(i),
                    'Changed source order, shape, factor or ReLU clamp')
            require(v.scale.dtype == np.float32 and v.scale.size == v.zero.size == 1
                    and v.zero.dtype == np.int8 and v.zero.item() == 0
                    and float(v.scale.item()) == expected_scales[i], 'Changed source quantization')
            require(lease_present(v.data,backend) and not v.data.flags.writeable, 'Original native source lease required')
        require([fingerprint(v.data) for v in cat.values] == cap['source_before'],
                'A captured source changed during the rest of the graph')
        original_hash = fingerprint(original_x)
        require(lease_present(original_x,backend), 'Original joined input lease required')
        require(pack_input(original_x).ctypes.data == original_x.ctypes.data, 'Reference input must be the mapped join')
        original_x.flags.writeable = False
        tables = np.stack([graph.table(v,qs,qz)[1] for v in cat.values])
        require(tuple(hashlib.sha256(t.tobytes()).hexdigest() for t in tables) == LUT_SHA, 'Changed exact source LUTs')
        parameters_hash = [hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest() for v in params]
        source_hashes = [fingerprint(v.data) for v in cat.values]

        def request():
            result = ReaderInput(tuple(ReaderGraph.source(v) for v in cat.values),
                                 np.stack([graph.table(v,qs,qz)[1] for v in cat.values]))
            require(result.mode == 2 and result.shape == (1,32,512,512), 'Dual source request changed')
            return result

        def one(variant,timed):
            samples.append(memory_guard(plan,backend))
            before = backend.calls,backend.pool_calls,backend.reader_calls;joins = graph.join_calls
            with backend.execution_lock:
                wall = time.perf_counter_ns();cpu = time.process_time_ns()
                x = graph.quantize(cat,qs,qz) if variant == 'reference' else request()
                y = (backend.conv_quantized(15,x,*params) if variant == 'reference'
                     else backend.conv_quantized_reader(15,x,*params))
                cpu_ns = time.process_time_ns()-cpu;wall_ns = time.perf_counter_ns()-wall
                # Snapshot after stopping both clocks, while the same RLock is held.
                phases = {n:float(backend.lib.ct_last_phase(backend.handle,i)) for i,n in enumerate(PHASES)}
                require(all(math.isfinite(v) and v >= 0 for v in phases.values()), 'Invalid native phase')
            require(backend.calls-before[0] == 1 and backend.pool_calls == before[1] == 0
                    and backend.reader_calls-before[2] == int(variant=='reader'), 'Actual operator path differs')
            require(graph.join_calls-joins == int(variant=='reference'), 'Reference must execute a new PS join')
            if variant == 'reference':
                require(x is not original_x and x.ctypes.data != original_x.ctypes.data
                        and np.array_equal(x,original_x), 'Fresh reference join differs or reused captured join')
            require(y.dtype == np.int8 and y.shape == oracle.shape and np.array_equal(y,oracle),
                    'Complete Conv15 INT8 output mismatch')
            del x,y
            samples.append(memory_guard(plan,backend))
            return dict(variant=variant,timed=timed,wall_ns=wall_ns,CPU_ns=cpu_ns,phases_seconds=phases)

        # One warm operation per variant uploads fixed tables and warms both BO paths.
        warm = [one('reference',False),one('reader',False)];gc.collect()
        backend.budget_checks_in_allocation = False
        warm_pool = int(backend.lib.ct_output_pool_bytes(backend.handle))
        for block in range(plan['rounds']):
            for order,variant in enumerate(('reference','reader','reader','reference')):
                row = one(variant,True);row.update(block=block,order=order);rows.append(row)
            # Explicit GC, reports and any fingerprints are outside all timings.
            gc.collect()
        require(backend.calls == 20+4*plan['rounds'] and backend.reader_calls == 1+2*plan['rounds']
                and backend.pool_calls == 0, 'Total real PL calls differ')
        require([fingerprint(v.data) for v in cat.values] == source_hashes
                and fingerprint(original_x) == original_hash, 'Captured source/reference input changed')
        require([hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest() for v in params] == parameters_hash,
                'Captured original convolution parameters changed')
        require(not backend.pool_tables and not backend.pool_uploaded, 'PL pooling was configured unexpectedly')
        medians = {kind:{key:statistics.median(r[key] for r in rows if r['variant']==kind)
                         for key in ('wall_ns','CPU_ns')} for kind in ('reference','reader')}
        result = dict(passed=True,worker_schema=SCHEMA,slice=69,layer=15,
            input_shape=[1,32,512,512],output_shape=[1,16,512,512],rounds=plan['rounds'],
            all_complete_INT8_outputs_exact=True,source_and_original_join_bytes_unchanged=True,
            source_LUT_SHA256=list(LUT_SHA),source_HWC_SHA256=source_hashes,
            original_join_HWC_SHA256=original_hash,original_parameter_SHA256=parameters_hash,
            output_INT8_SHA256=hashlib.sha256(oracle.tobytes()).hexdigest(),
            original_activation_LUT_retained=True,formal_FusedGraph_L14_order_retained=True,
            actual_PL_convolution_calls=backend.calls,actual_PL_reader_transform_calls=backend.reader_calls,
            actual_PL_pool_calls=0,all_calls_one_native_context=True,
            warmup=warm,rows=rows,median=medians,
            reader_wall_change_fraction=medians['reader']['wall_ns']/medians['reference']['wall_ns']-1,
            timing_scope='Q15 PS join or ReaderInput construction through complete Conv15 return; Python wall and process CPU. One thread; outer execution_lock also covers the seven phase reads after timers stop.',
            excluded='D6/setup/admission/prefix capture/uploads/warmup/hash/exact comparisons/explicit GC/reporting/DFX restoration. Native phase0 does not include PS join; phase3 is launch/wait, not isolated MAC cycles.',
            memory=dict(samples=samples,warm_output_BO_pool_bytes=warm_pool,
                sampled_output_BO_pool_max_bytes=max(x.get('output_BO_pool_bytes',0) for x in samples),
                sampled_system_CmaFree_min_bytes=min(x['CmaFree_bytes'] for x in samples),
                process_RSS_peak_bytes=max(x['process_RSS_peak_bytes'] for x in samples),
                boundary_BO_budget_bytes=plan['boundary_BO_budget_bytes'],
                scope='Boundary samples outside timed rows; process RSS excludes UI. CMA is a separate system sample, not a continuous or simultaneous whole-pipeline peak. Original two source leases and original join retained; one4MiB CPU output oracle; no prefix tensors saved.'),
            PS_fallback=False,new_FPGA_build=False,new_bit=False,production_promoted=False,
            whole_network_or_interactive_UI_speed_qualified=False,
            historical_R3_correctness_elapsed_not_used_as_speed_baseline=True)
        save(work/'reader_probe.json',result)
        return dict(pl_conv_calls=backend.calls,pl_pool_calls=0,pl_reader_calls=backend.reader_calls,
                    reader_probe='reader_probe.json',benchmark_only=True,production_promoted=False)
    finally:
        cap.clear();cat=original_x=oracle=context=graph=v=None
        gc.collect()
        if backend is not None:backend.close()
        backend=None;gc.collect()


def run_probe(work,root,plan):
    require(sys.platform == 'linux' and os.uname().machine == 'aarch64' and os.geteuid() == 0,
            'Only the actual admitted ARM/root transaction may execute the probe')
    os.environ.update(PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4',
                      CT_PS_POOL_FUSION='1',CT_PL_WAIT_MODE='adaptive',CT_PL_CLEAN_BO='1')
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1 import entry as stage
    require(not (stage.HERE/'pending_transaction.json').exists(), 'Leave an existing pending transaction untouched')
    source = inspect.getsource(stage.run)
    before = 'report=qualified.run_worker(args,prepared,record)'
    after = 'report=_reader_probe_worker(args,prepared,record)'
    require(source.count(before) == 1 and source.count(after) == 0, 'Changed transaction callback')
    selected = source.replace(before,after)
    require(selected.replace(after,before) == source, 'Transaction derivation must reverse exactly')
    ast.parse(selected)
    namespace = dict(vars(stage),_reader_probe_worker=lambda a,p,r:probe_worker(a,p,r,root,work,plan))
    exec(compile(selected,str(Path(__file__))+':sealed_transaction_callback','exec'),namespace)
    args = SimpleNamespace(input=root/CT,output=work/'stage',reference_dir=None,
                           repeats=1,preview=False,job_lock_fd=None)
    targets = (root/'dfx/medical/release/medical_ct_partial.bin',Path('/lib/firmware/medical_ct_partial.bin'))
    with stage.job_lock() as lock_fd:
        args.job_lock_fd=lock_fd
        ui = check_ui(plan,root);memory_guard(plan,allocation_reserve=plan['boundary_BO_budget_bytes'])
        with stage.idle_pl():pass
        original_firmware = {str(p):sha(p) for p in targets}
        save(work/'derivation.json',dict(parent_stage_SHA256=sha(stage.__file__),
            parent_run_function_SHA256=hashlib.sha256(source.encode()).hexdigest(),
            selected_function_SHA256=hashlib.sha256(selected.encode()).hexdigest(),
            literal_edit=[before,after],reverse_exact=True,
            original_stage_admission_and_D6_C5_transaction_preserved=True,
            original_stage_lifecycle_ReaderXRT_tracker_retained=True,
            no_functional_module_callback_reassignment=True))
        namespace['run'](args)
        report = read(work/'reader_probe.json');stage_report = read(work/'stage/report.json')
        require(report['passed'] and stage_report['qualified_original_firmware_restored']
                and stage_report['actual_C5_sessions'] == 1, 'Missing restored-stage proof')
        require(not (stage.HERE/'pending_transaction.json').exists(), 'Transaction ledger still pending')
        require(all(sha(Path(p)) == h for p,h in original_firmware.items()), 'Formal firmware was not restored')
        require(check_ui(plan,root) == ui, 'UI changed during probe')
        for n,h in plan['source_SHA256'].items():require(sha(bound(root,n)) == h, 'Source changed: '+n)
        save(work/'postflight.json',dict(passed=True,source_unchanged=True,
            original_firmware_restored=True,UI_unchanged=True,global_runner_lock_held_through_postflight=True,
            one_D6_and_one_C5_session_verified_by_original_stage=True,
            no_pending_transaction=True,production_promoted=False))
    return dict(passed=True,conv_calls=report['actual_PL_convolution_calls'],
                pool_calls=0,reader_calls=report['actual_PL_reader_transform_calls'])


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('inspect');q.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    q=sub.add_parser('probe');q.add_argument('--plan',type=Path,required=True);q.add_argument('--plan-sha256',required=True)
    a=p.parse_args()
    if a.action == 'inspect':
        print(json.dumps(inspect_local(a.root),indent=2));return
    work,root,plan = verify_plan(a.plan,a.plan_sha256)
    require(not (work/'terminal.json').exists() and not (work/'stage').exists(), 'Never repeat or overwrite a probe')
    started=time.perf_counter()
    try:
        result=run_probe(work,root,plan)
        save(work/'terminal.json',dict(passed=True,result=result,seconds=time.perf_counter()-started))
        print(json.dumps(result),flush=True)
    except BaseException as error:
        save(work/'terminal.json',dict(passed=False,error=repr(error),traceback=traceback.format_exc(),
                                     seconds=time.perf_counter()-started,production_promoted=False))
        raise


if __name__ == '__main__':
    main()
