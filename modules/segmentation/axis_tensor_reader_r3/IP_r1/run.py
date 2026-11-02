"""Repeat strict full159 HLS, export IP, require every exported RTL byte exact."""
from pathlib import Path,PurePosixPath
import hashlib,importlib.util,json,os,stat,sys,traceback,xml.etree.ElementTree as E,zipfile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'dfx/navigation_profile/rtl_r74'))
from job_limit_r74 import run,system_memory

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def save(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)

def package_proof(path,expected):
    members={};component=None
    with zipfile.ZipFile(path) as z:
        assert len(z.namelist())==len(set(z.namelist()))
        for info in z.infolist():
            p=PurePosixPath(info.filename.rstrip('/'))
            assert not p.is_absolute() and '\\' not in info.filename and ':' not in info.filename and '..' not in p.parts
            assert not stat.S_ISLNK(info.external_attr>>16)
            if info.is_dir():continue
            with z.open(info) as f:members[info.filename]=hashlib.file_digest(f,'sha256').hexdigest()
            if p.name=='component.xml':assert component is None;component=z.read(info)
        assert component is not None
        tree=E.fromstring(component);ns={'s':tree.tag.split('}')[0].removeprefix('{')}
        assert tree.findtext('s:name',namespaces=ns)=='ct_tensor_reader'
        registers={}
        for n in tree.findall('.//s:memoryMaps/s:memoryMap/s:addressBlock/s:register',ns):
            key=n.findtext('s:name',namespaces=ns);offset=n.findtext('s:addressOffset',namespaces=ns)
            if key and offset:registers[key]=int(offset,0)
        for name,offset in [('height',32),('width',40),('cin',48),('kernel',56),('mode',96),
            ('channels_a',104),('channels_b',112),('factor_a',120),('factor_b',128),('status',136)]:
            assert registers.get(name)==offset,(name,registers)
        assert all(off in registers.values() for off in (16,20,64,68,80,84))
        for leaf,h in expected.items():
            found=[v for n,v in members.items() if n=='hdl/verilog/'+leaf or n.endswith('/hdl/verilog/'+leaf)]
            assert found==[h],('Export differs from exact tested RTL',leaf,found)
    return dict(archive_SHA256=sha(path),archive_bytes=path.stat().st_size,
        all_members_SHA256=members,registers=registers,every_member_stream_SHA_verified=True,
        all40_exported_RTL_exact_original_HLS_and_RTL_trial=True)

def main():
    assert os.name=='nt' and not (HERE/'output').exists();(HERE/'output').mkdir()
    admission=json.loads((HERE/'admission.json').read_text());bindings=admission['source_SHA256']
    def verify():
        for n,h in bindings.items():assert sha(ROOT/n)==h,n
    verify();memory=system_memory();assert memory['free_commit_bytes']>=16*1024**3 and memory['physical_available_bytes']>=8*1024**3
    stages=[]
    try:
        source=HERE.parent/'HLS_r1/run.py'
        spec=importlib.util.spec_from_file_location('original_strict_R3_full159_HLS',source)
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        original.main()  # Exact unmodified CLI159 + direct AP159 + HLS source/flow.
        complete=json.loads((HERE.parent/'HLS_r1/output/complete.json').read_text())
        assert complete['actual159_Csim_full_frame_data_and_sidebands_exact']
        assert [s['stage'] for s in complete['actual_stages']]==['csim_cli','csim_direct','hls']
        assert all(s['receipt']['exit_code']==0 for s in complete['actual_stages'])
        component=ROOT.parent/'h/tensor';verilog=component/'hls/syn/verilog'
        actual={p.name:sha(p) for p in verilog.iterdir() if p.is_file()}
        assert actual==admission['expected_RTL_SHA256'],('Fresh HLS changed; previous RTL qualification cannot be reused',actual)
        cfg=HERE.parent/'HLS_r1/output/reader.cfg';tool=Path('D:/AMDDesignTools/2025.2.1/Vitis/bin/vitis-run.bat')
        result=run([str(tool),'--mode','hls','--package','--config',str(cfg),'--work_dir',str(component)],
            cwd=ROOT,env=dict(os.environ,PROCESSOR_ARCHITECTURE='AMD64',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),
            log=HERE/'output/package.log',started=HERE/'output/package_started.json',limit=8*1024**3)
        save(HERE/'output/package_receipt.json',result);stages.append(result)
        assert result['exit_code']==0 and result['all_owned_processes_terminal'] and result['configured_limit_verified']
        assert not result['resource_failure'] and not result['elapsed_time_abort'];verify()
        assert {p.name:sha(p) for p in verilog.iterdir() if p.is_file()}==actual
        exported=package_proof(HERE.parent/'HLS_r1/output/export.zip',actual)
        save(HERE/'output/complete.json',dict(status='actual_R3_strict159_HLS_and_identical40RTL_IP_export',
            actual_full159_CLI_and_direct_AP_HLS_and_package_exit0=True,
            all40_generated_and_exported_RTL_byte_identical_to_prior_HLS=True,
            original_control_offsets_through_status136_and_input_skip_LUT_pointers_verified=True,
            original_Csim_HLS_stages=complete['actual_stages'],package_stages=stages,export=exported,
            export_path=(HERE.parent/'HLS_r1/output/export.zip').relative_to(ROOT).as_posix(),
            source_SHA256=bindings,whole_C5_100MHz_all5PR_ARM139_system_integration_pending=True,
            PL_accessed=False,production_promoted=False,whole_goal_completed=False))
        print('PASS exact40RTL packaged IP; same whole C5/DFX/board integration remains',flush=True)
    except BaseException:
        save(HERE/'output/failure.json',dict(traceback=traceback.format_exc(),package_stages=stages,source_SHA256=bindings,
            whole_goal_completed=False));raise

if __name__=='__main__':main()
