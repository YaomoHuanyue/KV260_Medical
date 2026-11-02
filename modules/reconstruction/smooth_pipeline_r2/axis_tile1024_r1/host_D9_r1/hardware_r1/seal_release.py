"""Seal only the actual independently routed D9 partial; no firmware install or PL access."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[5]
CORE=HERE.parents[1]
RELEASE=HERE/'release_r1'
PARTIAL='medical_smooth_D9_axis_r1_partial.bin'
MARKER=b'KV260_D9_AXIS_HARDWARE_OFFLINE\n'
ROUTE=ROOT/'results/smooth_AXIS_D9_PR_r1/smooth'
ARTIFACT='config_smooth_D9_r1_pblock_rp_partial.bin'
SCHEMA='kv260.D9_AXIS.manual_trial.v1'


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):return json.loads(path.read_text())


def route_gate(value):
    if value.get('status')!='independent_PC_D9_actual100MHz_route_five_fullPR_and_five_artifacts_verified':
        raise ValueError('Actual independently verified D9 physical route required')
    if not value.get('all_owned_bytes_stream_verified_and_exact_remote_root_absent'):
        raise ValueError('D9 physical result collection incomplete')
    if value.get('clock_MHz')!=100 or value.get('WNS_ns',-1)<0 or value.get('WHS_ns',-1)<0:
        raise ValueError('D9 original100MHz setup and hold gate failed')
    refs=value.get('five_reference_full_PR',[])
    if [row.get('reference') for row in refs]!=['mc','smooth','edt','route','ct'] or not all(row.get('full_check_passed') for row in refs):
        raise ValueError('All five original fullPR references required')
    expected=value.get('artifact_SHA256',{}).get(ARTIFACT,'')
    if len(expected)!=64 or any(char not in '0123456789abcdef' for char in expected):
        raise ValueError('Missing actual qualified D9 partial SHA256')
    return expected


def verify(installed=False):
    if not (RELEASE/'manifest.json').is_file():
        raise RuntimeError('D9 fully qualified manual release missing; no hardware access')
    value=read(RELEASE/'manifest.json')
    if (value.get('schema')!=SCHEMA or value.get('identity')!=217 or value.get('ABI')!=12 or
        value.get('clock_MHz')!=100 or value.get('offline_verified') is not True):
        raise ValueError('Wrong or unqualified D9 release identity')
    if value.get('production_accepted') is not False or value.get('board_geometry_and_PS4_speed_verified') is not False:
        raise ValueError('This package authorizes a manual candidate trial only')
    expected=route_gate(value['route'])
    if value.get('partial_SHA256')!=expected or sha(RELEASE/PARTIAL)!=expected:
        raise ValueError('Changed D9 partial')
    if (RELEASE/'native_guard.txt').read_bytes()!=MARKER:
        raise ValueError('Wrong D9 native guard')
    for name,digest in value['portable_source_and_evidence_SHA256'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or sha(path)!=digest:
            raise ValueError('Changed/missing portable D9 source: '+name)
    if read(ROUTE/'verified_Windows.json')!=value['route']:
        raise ValueError('Embedded D9 route proof differs from the bound physical result')
    if sha(ROOT/'dfx/medical/release/manifest.json')!=value['static_base_manifest_SHA256']:
        raise ValueError('Frozen medical shell manifest changed')
    if installed:
        if os.name=='nt' or os.uname().machine!='aarch64':
            raise ValueError('Actual ARM installation required')
        if sha(Path('/lib/firmware')/PARTIAL)!=expected:
            raise ValueError('Installed D9 firmware differs from qualified partial')
    return value


def prepare():
    assert os.name=='nt' and not RELEASE.exists()
    sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'dfx/smooth_speed/route_D9_r1')]
    import project_storage
    # Includes the other active R11 recovery's80MB collection peak.
    project_storage.check(112_000_000)
    path=ROOT/'dfx/smooth_speed/route_D9_r1/preflight.py'
    spec=importlib.util.spec_from_file_location('D9_actual_preboarding_gate',path)
    gates=importlib.util.module_from_spec(spec);spec.loader.exec_module(gates)
    admitted=gates.admit()
    route_path=ROUTE/'verified_Windows.json'
    if not route_path.is_file():
        raise RuntimeError('D9 actual physical route still pending; no release created')
    route=read(route_path)
    expected=route_gate(route)
    assert route['candidate_DCP_SHA256']==admitted['candidate_DCP_SHA256']
    assert route['frozen_static_SHA256']==admitted['frozen_static_SHA256']
    for name,digest in route['source_and_evidence_SHA256'].items():assert sha(ROOT/name)==digest,name
    arm_path=CORE/'arm_native_r1/PC_verified.json'
    arm=read(arm_path)
    assert arm['original144_complete_bank_cases_exact'] and arm['original_CT18_full5_banks16_reports_guards_exact']
    assert arm['Windows_ARM_same_original_case_results_paired'] and not arm['actual_D9_PL_accessed']
    host_path=HERE.parent/'PC_ARM_verified.json'
    host=read(host_path)
    assert host['status']=='PC_verified_actual_D9_ARM_complete_XRT_compile_and_paired78_control110_memory_checks'
    assert host['original8_pre_hardware_root_refusals_passed'] and host['actual_78_control_and110_memory_cases_paired_Windows_ARM']
    assert sha(HERE/'build_ARM_r1/libD9_XRT.so')==host['actual_AArch64_XRT_bridge_ELF_SHA256']
    wrappers=read(HERE/'wrapper_paired_verified.json')
    assert len(wrappers['original20_negative_cases'])==20 and wrappers['actual_missing_release_refused_before_CDLL']
    assert wrappers['actual_native_D9_candidate_used_for_math'] and wrappers['actual_XRT_C_API_transport_emulated_only_in_test']
    for proof in (host,wrappers):
        for name,digest in proof['source_and_evidence_SHA256'].items():assert sha(ROOT/name)==digest,name
    portable={}
    def bind(path):portable[path.relative_to(ROOT).as_posix()]=sha(path)
    for name,digest in read(HERE/'build_ARM_r1/verified.json')['source_and_input_SHA256'].items():
        assert sha(ROOT/name)==digest,name
        portable[name]=digest
    for path in (Path(__file__),HERE/'runtime.py',HERE/'test_runtime.py',HERE/'wrapper_derivation.json',
        HERE/'wrapper_paired_verified.json',HERE/'runtime_wrapper_Windows_r1.json',HERE/'runtime_wrapper_ARM_r1.json',
        HERE/'build_ARM_r1/libD9_XRT.so',HERE/'build_ARM_r1/verified.json',HERE/'build_inputs_r1.json',
        host_path,arm_path,route_path,ROOT/'dfx/medical/release/manifest.json'):
        bind(path)
    archive=ROUTE/'current_candidate.zip'
    assert sha(archive)==route['archive_SHA256']
    member='workspace/dfx/smooth_speed/route_D9_r1/build/'+ARTIFACT
    with zipfile.ZipFile(archive) as source:
        manifest=json.loads(source.read('outputs_manifest.json'))
        # A changed kernel's newly routed partial must be a retained real artifact.
        assert manifest[member]==expected
        size=source.getinfo(member).file_size
        project_storage.check(80_000_000+size+6_000_000)
        RELEASE.mkdir()
        with source.open(member) as inp,(RELEASE/PARTIAL).open('xb') as output:
            for chunk in iter(lambda:inp.read(1048576),b''):output.write(chunk)
    assert sha(RELEASE/PARTIAL)==expected
    value=dict(schema=SCHEMA,identity=217,ABI=12,clock_MHz=100,offline_verified=True,
        partial_SHA256=expected,route=route,static_base_manifest_SHA256=sha(ROOT/'dfx/medical/release/manifest.json'),
        portable_source_and_evidence_SHA256=portable,
        original_native144_CT18_Csim_monitored14_malformed40_and_frozen_DFX_gates_preserved=True,
        actual_ARM_native_and_complete_XRT_bridge_compilation_verified=True,
        actual_D9_PL_execution_and_same_precision_PS4_speed_still_required=True,
        board_geometry_and_PS4_speed_verified=False,production_accepted=False,
        no_formal_default_change=True,whole_goal_completed=False)
    with (RELEASE/'manifest.json').open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    (RELEASE/'native_guard.txt').write_bytes(MARKER)
    verify(installed=False)
    print('PASS actual routed D9 manual candidate sealed; no firmware installed or PL session opened')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','verify'))
    action=parser.parse_args().action
    if action=='prepare':prepare()
    else:verify(installed=os.name!='nt');print('PASS exact D9 manual release bindings')
