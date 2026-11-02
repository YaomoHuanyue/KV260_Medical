"""Small runtime manifest for the already qualified cf5 reader candidate.

PC preparation replays the full physical/board chain. Runtime checks the exact
installed bit, library, model and source files, not compiler archives. Mutable
firmware targets are checked separately at the original transaction boundaries.
"""
from pathlib import Path,PurePosixPath
import copy,hashlib,json,os,re,time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SCHEMA='kv260.reader_burst.runtime_candidate.v1'
QUAL_SCHEMA='kv260.reader_burst.compact_qualification.v1'
PARTIAL_SHA='cf5e4ede2dbba66553e44d205095c05d5672d24aaf012540becabc457f42d44a'
ORIGINAL_SHA='f6984b755def971a6c5a1c8487c0bc3376fa4ffe69b16cdfb6838857a60d888e'
LIBRARY_SHA='8c431fcaa56948635642aa3fb9016e65662005d04f3ff83f132be8bcd571bbbf'
STATIC_SHA='a70ae87c8551b07ab4a586bbd04b0a22ed5f13a84931111bed1ad2d10b92a192'
STATIC_DCP_SHA='285f3d4a50af45cbea7f503f1f32789b0d84b55214163750a301267e2e72fcb9'
LEGACY_PATH='modules/segmentation/mixed_r30/candidate_r2.json'
LEGACY_SHA='5c0cb67ea0254ce382e80049cdda402b52ff63725d1c0b8b03928c199caa28fc'
MODEL_PINS={
 'modules/segmentation/outputs/ct_accuracy_v2/pl_model/graph.json':'038ecc73f6fe6805a64af153f31e222453d2bfe7d90a7cddf076862904329eb3',
 'modules/segmentation/outputs/ct_accuracy_v2/pl_model/tensors.npz':'9c57169691fe8f961f71d595f2b0acfe03c9742de9e7c222e0d3a2dd9b6898ad'}
OWN_FILES={f'modules/segmentation/reader_burst/{n}.py'for n in
           ('admission','native','segmentation','graph','worker','backend')}
REQUIRED_FILES=OWN_FILES|set(MODEL_PINS)|{
 'system/partial_transaction_r1.py',
 'modules/segmentation/axis_tensor_reader_r3/host_r1/backend.py',
 'modules/segmentation/axis_tensor_reader_r3/graph_r1/reader_graph.py',
 'modules/segmentation/axis_tensor_reader_r3/streaming_r1/entry.py',
 'modules/segmentation/mixed_r30/segmentation.py',
 'modules/segmentation/mixed_r30/admission.py',LEGACY_PATH,
 'modules/segmentation/ct_pl/runtime.py','modules/segmentation/ct_pl/fused_graph.py',
 'modules/segmentation/ct_pl/quantized_runtime.py','modules/segmentation/ct_pl/slice_pipeline.py',
 'modules/ct_preprocess/axis_hu_32_r2/bounded_volume_r3/runtime.py',
 'modules/ct_preprocess/axis_hu_32_r2/bounded_volume_r3/derivation.json'}
POLICY=dict(clock_MHz=100,reader_ABI=0xc5030001,RP_bits=1830,
    reader_control_address_bits=8,writer_control_address_bits=8,
    Q15_only=True,PS_pool_chains=3,fused_activations=8,L14_original_order=True,
    PS_fallback=False,cleanup_backend='PS_original_clean_mask')
ROLES={'partial','original','library','static_manifest','xclbin','qualification'}


def need(ok,text):
    if not ok:raise ValueError(text)


def digest(v):return isinstance(v,str)and re.fullmatch('[0-9a-f]{64}',v)is not None


def sha(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def binding(pins):
    return hashlib.sha256(json.dumps(pins,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def confined(root,name):
    need(isinstance(name,str)and '\\'not in name and ':'not in name,'Relative POSIX path required')
    rel=PurePosixPath(name)
    need(name and not rel.is_absolute()and '..'not in rel.parts and str(rel)==name,'Escaping or unnormalized runtime path')
    p=root/name
    for q in (p,*p.parents):
        if q==root:break
        need(not q.is_symlink()and not getattr(q,'is_junction',lambda:False)(),'Runtime symlink/reparse path refused')
    resolved=p.resolve(strict=True)
    need(resolved.is_relative_to(root)and resolved.is_file(),'Missing runtime file: '+name)
    return resolved


def read_small(path):
    need(Path(path).stat().st_size<=262144,'Runtime JSON exceeds256KiB')
    return json.loads(Path(path).read_text(encoding='utf-8'))


def stamp(path):
    st=path.stat()
    return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns,st.st_mode)


def verified_json(path,expected_sha):
    before=stamp(path)
    need(before[2]<=262144,'Runtime JSON exceeds256KiB')
    data=Path(path).read_bytes()
    need(len(data)<=262144 and hashlib.sha256(data).hexdigest()==expected_sha
         and stamp(path)==before,'Runtime JSON changed or differs from declared SHA')
    return json.loads(data.decode('utf-8')),before


def schema_contract(a):
    need(a.get('schema')==SCHEMA and a.get('policy')==POLICY,'Wrong reader runtime policy/schema')
    need(a.get('production_promoted')is False and a.get('PS_fallback')is False,'Explicit unpromoted PL candidate required')
    need(a.get('legacy_hybrid')==dict(path=LEGACY_PATH,SHA256=LEGACY_SHA),'Original cleanup/full-system selector required')
    rows=a.get('artifacts',{});need(set(rows)==ROLES,'Exact runtime artifact roles required')
    for role,row in rows.items():
        need(set(row)=={'path','bytes','SHA256'}and type(row['bytes'])is int and row['bytes']>0
             and digest(row['SHA256']),'Invalid runtime artifact: '+role)
    for role,h in (('partial',PARTIAL_SHA),('original',ORIGINAL_SHA),('library',LIBRARY_SHA)):
        need(rows[role]['SHA256']==h,'Unqualified artifact: '+role)
    need(rows['partial']['bytes']==7_868_904,'Exact RP partial required')
    pins=a.get('runtime_files',{})
    need(isinstance(pins,dict)and REQUIRED_FILES<=set(pins)and len(pins)<=128,'Complete bounded runtime closure required')
    need(all(digest(h)for h in pins.values())and all(pins.get(n)==h for n,h in MODEL_PINS.items()),'Frozen model/runtime binding required')
    need(pins.get(LEGACY_PATH)==LEGACY_SHA,'Unchanged legacy selector binding required')
    need('dfx/medical/release/medical_ct_partial.bin'not in pins,'Mutable target belongs to original transaction')
    return a


def qualification_contract(q,a):
    need(q.get('schema')==QUAL_SCHEMA and q.get('runtime_files_binding_SHA256')==binding(a['runtime_files']),
         'Compact qualification/source closure mismatch')
    need(q.get('partial_SHA256')==PARTIAL_SHA and q.get('library_SHA256')==LIBRARY_SHA
         and q.get('static_image_SHA256')==STATIC_SHA and q.get('static_DCP_SHA256')==STATIC_DCP_SHA,
         'Exact physical identity required')
    need(q.get('clock_MHz')==100 and q.get('RP_bits')==1830 and q.get('tool_version')=='2025.2.1',
         'Frozen static/tool/100MHz qualification required')
    for k in ('actual_RTL_passed','actual_route_passed','actual_all5_PR_passed',
              'actual_bit_generation_passed','actual_full139_inputs_logits_exact',
              'actual_four_original_stages_outputs_exact','actual_firmware_restorations_passed'):
        need(q.get(k)is True,'Missing completed prerequisite: '+k)
    need(type(q.get('WNS_ns'))in(int,float)and q['WNS_ns']>=0
         and type(q.get('WHS_ns'))in(int,float)and q['WHS_ns']>=0,'Routed setup/hold failed')
    evidence=q.get('evidence_SHA256',{})
    need({'physical','five_PR','bit','full139','formal_stage'}<=set(evidence)
         and all(digest(h)for h in evidence.values()),'Completed proof bindings required')
    return q


class Certificate:
    def __init__(self,path,expected_sha,root,mode):
        started=time.perf_counter();self.root=Path(root).resolve(strict=True)
        need(mode in('pc','board')and digest(expected_sha),'Explicit runtime verification mode/SHA required')
        self.mode=mode;self.path=confined(self.root,Path(path).absolute().relative_to(self.root).as_posix())
        document,manifest_stamp=verified_json(self.path,expected_sha);self.digest=expected_sha
        self._record=schema_contract(document);self._paths={};self._stamps={};self._pins={}
        sources=self._record.get('deployment_sources',{})
        need(isinstance(sources,dict)and set(sources)<=set(r['path']for r in self._record['artifacts'].values()),
             'Deployment source map is artifact-only')
        pins=dict(self._record['runtime_files'])
        for row in self._record['artifacts'].values():
            name=row['path'];need(name not in pins or pins[name]==row['SHA256'],'Conflicting runtime binding')
            pins[name]=row['SHA256']
        total=0
        for name,h in pins.items():
            actual=sources.get(name,name)if mode=='pc'else name
            p=confined(self.root,actual);total+=p.stat().st_size
            self._paths[name]=p;self._pins[name]=h
        need(total<=32*1024**2,'Runtime verification unexpectedly includes bulk compiler/CT files')
        for role,row in self._record['artifacts'].items():
            need(self._paths[row['path']].stat().st_size==row['bytes'],'Artifact byte count changed: '+role)
        self._verify_all(capture=True)
        need(self._manifest_stamp==manifest_stamp,'Runtime certificate state changed during initialization')
        q,_=verified_json(self.artifact('qualification'),self._record['artifacts']['qualification']['SHA256'])
        qualification_contract(q,self._record)
        static,_=verified_json(self.artifact('static_manifest'),self._record['artifacts']['static_manifest']['SHA256'])
        need(static.get('bit_bin_sha256')==STATIC_SHA and static.get('static_routed_sha256')==STATIC_DCP_SHA
             and static.get('clock_hz')==100_000_000,'Frozen static manifest differs')
        self.check_unchanged()
        self.load_seconds=time.perf_counter()-started;self.verified_bytes=total

    @property
    def record(self):return copy.deepcopy(self._record)

    def artifact(self,role):return self._paths[self._record['artifacts'][role]['path']]

    def _verify_all(self,capture=False):
        started=time.perf_counter()
        before=stamp(self.path)
        need(sha(self.path)==self.digest and stamp(self.path)==before,'Runtime certificate changed while hashing')
        if capture:self._manifest_stamp=before
        for name,p in self._paths.items():
            confined(self.root,p.relative_to(self.root).as_posix())
            before=stamp(p)
            need(sha(p)==self._pins[name]and stamp(p)==before,'Changed runtime file or file state: '+name)
            if capture:self._stamps[name]=before
        return time.perf_counter()-started

    def verify_all(self):return self._verify_all()

    def check_unchanged(self):
        need(stamp(self.path)==self._manifest_stamp,'Runtime certificate state changed')
        confined(self.root,self.path.relative_to(self.root).as_posix())
        for name,p in self._paths.items():
            confined(self.root,p.relative_to(self.root).as_posix())
            need(stamp(p)==self._stamps[name],'Runtime source state changed: '+name)

    def targets(self):
        need(self.mode=='board','PC source verification cannot access hardware targets')
        return (self.root/'dfx/medical/release/medical_ct_partial.bin',Path('/lib/firmware/medical_ct_partial.bin'))

    def require_pair(self,new=False):
        self.check_unchanged();h=PARTIAL_SHA if new else ORIGINAL_SHA
        for p in self.targets():need(not p.is_symlink()and p.is_file()and sha(p)==h,'Firmware pair differs from declared transaction state')

    def stage_inputs(self):
        return dict(original_asset=self._record['artifacts']['original']['path'],
                    qualified_template=self.path.relative_to(self.root).as_posix())

    def stage_record(self):
        return dict(pool_library=self._record['artifacts']['library']['path'],
            pool_partial=self._record['artifacts']['partial']['path'],
            old_partial_SHA256=ORIGINAL_SHA,new_partial_SHA256=PARTIAL_SHA,
            proofs=dict(pool_hardware_admission=dict(path=self.path.relative_to(self.root).as_posix())))

    def verify_original(self,path):
        need(Path(path).resolve()==self.path,'Exact candidate template required');self.require_pair(False)
        return self.stage_record()

    def require_xrt(self,path,library):
        need(Path(path).resolve()==self.path and Path(library).resolve()==self.artifact('library'),'Exact native admission/library required')
        self.require_pair(True)
        need(Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()==STATIC_SHA,'Wrong loaded static shell')
        need(Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating','FPGA manager not operating')
        need(Path.cwd().resolve()==self.root/'dfx/medical','Open native context from declared DFX directory')
        return self.record


def load(path,expected_sha,*,root=ROOT,mode='board'):
    return Certificate(path,expected_sha,root,mode)
