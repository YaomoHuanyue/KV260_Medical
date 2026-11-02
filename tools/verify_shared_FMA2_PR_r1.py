"""Independently stream the complete BRAM PR archive and original route gates."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,stat,zipfile

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/shared_FMA2_PR_r1/smooth'
PREFIX='workspace/dfx/smooth_speed/route_shared_fma2_r1/'
OUT=ROOT/'results/shared_FMA2_PR_r1/independent_verified'


def digest(reader):
    h=hashlib.sha256()
    for b in iter(lambda:reader.read(1048576),b''):h.update(b)
    return h.hexdigest()


def sha(path):
    with path.open('rb') as f:return digest(f)


def verify(archive,expected_sha,count):
    archive=archive.resolve();assert archive.is_relative_to(ROOT)
    meta=json.loads((BASE/'download_verified_r2630.json').read_text())
    assert meta['archive']['sha256']==expected_sha and meta['archive']['count']==count
    assert meta['all_archived_outputs_and_closed_logs_full_SHA_verified']
    assert meta['actual_original_worker_and_all_owned_processes_terminal']
    assert archive.stat().st_size==meta['archive']['bytes'] and sha(archive)==expected_sha
    cleanup=json.loads((BASE/'cleanup_verified_r2630.json').read_text())
    for k in ['owned_root_confirmed_absent','all_results_logs_inputs_full_SHA_verified_locally',
              'task_and_all_owned_compilers_terminal_before_cleanup','original_server_files_unchanged']:
        assert cleanup[k],k
    q=json.loads((ROOT/'results/shared_FMA2_PR_r1/smooth/qualified.json').read_text())
    assert q['actual_RM_capacity_qualified']
    assert q['original14_6422850_native144_CT18_7Csim_20ID5banks17controls8DLLs_all_preserved']
    assert q['same_full_RTL_HLS_official_package_and_synthesized_wrapper_RTL_verified']
    assert q['original100MHz_setup_hold_DRC_fullPR_all5_artifacts_required']
    for name,h in q['source_and_evidence_sha256'].items():assert sha(ROOT/name)==h,name
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();m=json.loads(z.read('outputs_manifest.json'))
        assert 0<count<10000 and len(m)==count and len(names)==len(set(names))
        assert set(names)==set(m)|{'outputs_manifest.json'}
        for n,h in m.items():
            p=PurePosixPath(n)
            assert p.as_posix()==n and not p.is_absolute() and ':' not in n and '\\' not in n
            assert all(v not in ('','.','..') for v in n.split('/'))
            assert not stat.S_ISLNK(z.getinfo(n).external_attr>>16)
            with z.open(n) as f:assert digest(f)==h,n
        terminal=json.loads(z.read('terminal.json'))
        assert terminal==meta['terminal'] and terminal['tool_gates_passed'] and terminal['failure'] is None
        assert terminal['all_owned_compiler_processes_terminal'] and terminal['full_original_test_scope_preserved']
        assert not terminal['PL_accessed'] and not terminal['production_promoted']
        raw=json.loads(z.read('raw_task_receipt.json'))
        assert raw['exit_code']==0 and raw['all_owned_processes_terminal'] and raw['configured_limit_verified'] and raw['assigned_before_execution']
        assert raw['configured_job_memory_limit_bytes']==raw['job_memory_limit_bytes']==32*1024**3
        assert raw['minimum_system_free_commit_bytes']==1536*1024**2
        assert raw['resource_failure'] is None and not raw['elapsed_time_abort'] and not raw['job_memory_limit_rejection_observed']
        assert m[PREFIX+'input/qualified_shared_fma2_r1_RM.dcp']==q['candidate_DCP_SHA256']
        assert m['workspace/dfx/medical/build/static_routed.dcp']==q['source_and_evidence_sha256']['dfx/medical/build/static_routed.dcp']
        original=json.loads(z.read('evidence/full_PC_preflight.json'))
        assert original==q
        parser_path=ROOT/'dfx/smooth_speed/route_shared_fma2_r1/check_reports_r1.py'
        parser=z.read(PREFIX+'check_reports_r1.py')
        assert parser==parser_path.read_bytes()
        assert hashlib.sha256(parser).hexdigest()==q['source_and_evidence_sha256'][parser_path.relative_to(ROOT).as_posix()]
        namespace={};exec(compile(parser,'validated_original_BRAM_route_parser','exec'),namespace)
        reports=namespace['reports'](*[z.read(PREFIX+'build/'+n).decode(errors='replace') for n in
            ['timing_shared_fma2_r1.rpt','drc_shared_fma2_r1.rpt','pr_verify_shared_fma2_r1.log','utilization_shared_fma2_r1.rpt']])
        assert reports==json.loads(z.read('reports_validated.json'))
        tcl=z.read(PREFIX+'implement_shared_fma2_r1.tcl').decode()
        assert tcl==(ROOT/'dfx/smooth_speed/route_shared_fma2_r1/implement_shared_fma2_r1.tcl').read_text()
        for token in ['read_checkpoint -cell rp -strict','foreach type {max min}','pr_verify -full_check',
                      'opt_design -control_set_merge','place_design -directive Explore','write_bitstream -force -bin_file']:
            assert token in tcl,token
        artifacts={}
        for suffix in ['.dcp','.bit','.bin','_pblock_rp_partial.bit','_pblock_rp_partial.bin']:
            n=PREFIX+'build/config_smooth_shared_fma2_r1'+suffix
            assert z.getinfo(n).file_size>0;artifacts[n]=m[n]
    return dict(full_PR_passed=True,archive_sha256=expected_sha,archive_entry_count=count,
        all_archive_members_full_SHA_verified=True,qualified_same_source_DCP_sha256=q['candidate_DCP_SHA256'],
        frozen_static_sha256=q['source_and_evidence_sha256']['dfx/medical/build/static_routed.dcp'],
        primary_PC_full14_6422850_words_both_hosts_exact_source_qualification_pinned=True,
        actual_routed_reports=reports,artifact_sha256=artifacts,compilation_seconds=raw['elapsed_s'],
        peak_job_GiB=raw['reported_peak_job_bytes']/1024**3,exact_server_root_absent=True,
        verifier_sha256=sha(Path(__file__)),strongest_same_input_PS1_PS4_board_speed_still_required=True,
        PL_accessed=False,production_promoted=False,whole_goal_completed=False)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('archive',type=Path);ap.add_argument('--sha256',required=True);ap.add_argument('--count',type=int,required=True);a=ap.parse_args()
    result=verify(a.archive,a.sha256,a.count);host='Windows' if os.name=='nt' else 'ARM';OUT.mkdir(exist_ok=True)
    with (OUT/f'verified_{host}.json').open('x',encoding='utf8') as f:json.dump(dict(result,host=host),f,indent=2)
    print('PASS original100MHz setup/hold DRC fullPR all5 artifacts and complete archive',host,result['actual_routed_reports'],flush=True)
