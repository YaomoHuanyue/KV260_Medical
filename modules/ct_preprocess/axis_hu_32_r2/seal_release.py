"""Seal only real D6 PR artifacts and the paired, pre-release-qualified host."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
from verify import verify

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
HOST=HERE/'host_r1'


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(4*1024**2),b''):h.update(block)
    return h.hexdigest()


def main():
    subprocess.run([r'C:/Python314/python.exe','-B','-X','utf8',str(ROOT/'tools/project_storage.py'),
        'check','--reserve-bytes','25000000'],cwd=ROOT.parent,check=True,stdout=subprocess.DEVNULL)
    release=HERE/'dfx_r1/release_r1';assert not release.exists()
    current=verify()
    for host in ['Windows','ARM']:assert json.loads((HERE/('verified_'+host+'.json')).read_text())==dict(current,verifier_SHA256=sha(HERE/'verify.py'))
    physical_path=HERE/'dfx_r1/PR_r1/complete.json';physical=json.loads(physical_path.read_text())
    assert physical['full_PR_passed'] and physical['clock_MHz']==100 and physical['WNS_ns']>=0 and physical['WHS_ns']>=0
    for field in ['inputs_SHA256','artifacts_SHA256']:
        for n,h in physical[field].items():assert sha(ROOT/n)==h,n
    native=[json.loads((HOST/('native_'+host+'_r2/verified.json')).read_text()) for host in ['Windows','ARM']]
    assert native[0]['source_SHA256']==native[1]['source_SHA256'] and native[0]['tests']==native[1]['tests']
    for host,value in zip(['Windows','ARM'],native):
        assert value['PL_accessed'] is False
        for field in ['source_SHA256','artifacts_SHA256']:
            for n,h in value[field].items():assert sha(ROOT/n)==h,n
        folder=HOST/('native_'+host+'_r2')
        original=json.loads((folder/'run_test_original_queue.log').read_text())
        assert original['complete_requests']==32000 and original['negative_cases']==17
        assert 'PASS HU_NONBLOCKING_PIPELINE_86' in (folder/'run_test_pipeline.log').read_text()
    assert native[1]['native']['actual_AArch64_compilation'] and native[1]['native']['no_FileLock_MMIO_XRT_or_PL_entered']
    wrappers=[json.loads((HOST/('runtime_verified_'+host+'.json')).read_text()) for host in ['Windows','ARM']]
    assert {k:v for k,v in wrappers[0].items() if k!='host'}=={k:v for k,v in wrappers[1].items() if k!='host'}
    assert wrappers[0]['positive_cases']==18 and wrappers[0]['rejected_calls']==47
    for n,h in wrappers[0]['source_SHA256'].items():assert sha(HOST/n)==h
    # Confirm actual ARM compiler project inputs, rather than just a list of
    # files that a manifest intended the compiler to use.
    dep=(HOST/'native_ARM_r2/bridge.d').read_text().replace('\\\n',' ').split()[1:]
    prefix='/home/ubuntu/jupyter_notebooks/KV260_System/'
    project_deps={s[len(prefix):] for s in dep if s.startswith(prefix)}
    assert project_deps and any(n.endswith('/session.hpp') for n in project_deps)
    for n in project_deps:assert native[1]['source_SHA256'][n]==sha(ROOT/n),n
    hls=json.loads((HERE/'HLS_r1/hls/complete.json').read_text())
    assert hls['estimated_clock_ns']<=10 and hls['actual_loop_II']['ct_hu_axis_Pipeline_convert_words_csynth.xml:convert_words']=='1'
    release.mkdir()
    partial=release/'medical_hu_D6_32_r2_partial.bin'
    shutil.copyfile(HERE/'dfx_r1/PR_r1/config_hu_D6_pblock_rp_partial.bin',partial)
    assert sha(partial)==sha(HERE/'dfx_r1/PR_r1/config_hu_D6_pblock_rp_partial.bin') and partial.stat().st_size==7868904
    guard=release/'native_guard.txt';guard.write_bytes(b'KV260_HU_AXIS32_D6_100MHZ_FULLPR_PAIRED\n')
    runtime_files={n:sha(ROOT/n) for n in native[1]['source_SHA256']}
    runtime_files.update({(HOST/n).relative_to(ROOT).as_posix():h for n,h in wrappers[0]['source_SHA256'].items()})
    for p in [partial,guard,HOST/'native_ARM_r2/libhu_dfx.so',HERE/'model_lut.bin',HERE/'quantization.py',
              HERE/'hu_axis.cpp',HERE/'hu_axis.hpp',HERE/'dfx_r1/rm_medical.v',Path(__file__)]:
        runtime_files[p.relative_to(ROOT).as_posix()]=sha(p)
    value=dict(schema='kv260.HU_D6.offline.v1',identity=0xd6,clock_MHz=100,full_PR_passed=True,
        parallel_HU_lanes=32,input_word_loop_II=1,input_word_bits=512,
        WNS_ns=physical['WNS_ns'],WHS_ns=physical['WHS_ns'],RP_resources=physical['RP_resources'],
        whole_resources=physical['whole_resources'],remaining_RP=physical['remaining_RP'],
        complete_original_medical_full_PR_comparisons=['ct','mc','smooth','edt','route'],
        native_requests_each_host=32000,native_negative_cases_each_host=17,new_nonblocking_scheduler_cases_each_host=86,
        Python_positive_cases_each_host=18,Python_negative_cases_each_host=47,
        actual_compiler_project_dependencies=sorted(project_deps),runtime_files_SHA256=runtime_files,
        offline_proofs_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in [physical_path,
            HERE/'verified_Windows.json',HERE/'verified_ARM.json',HOST/'native_Windows_r2/verified.json',
            HOST/'native_ARM_r2/verified.json',HOST/'runtime_verified_Windows.json',HOST/'runtime_verified_ARM.json']},
        partial_SHA256=sha(partial),actual_PL_board_tested=False,production_promoted=False,
        no_new_static_shell_or_XRT_metadata_required=True,whole_goal_completed=False)
    (release/'manifest.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({k:v for k,v in value.items() if k not in ['runtime_files_SHA256','offline_proofs_SHA256','actual_compiler_project_dependencies']},indent=2),flush=True)


if __name__=='__main__':main()
