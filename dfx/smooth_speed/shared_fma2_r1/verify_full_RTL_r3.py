"""Read every current 16K output word, retaining the original per-mode gates.

The checker blocks are bound to their exact original source. Native checker
source addresses refer to their retained originals instead of nonexistent copies
under the candidate. Every predicate and the complete RTL mode block are kept.
"""
from pathlib import Path,PurePosixPath
import ast
import hashlib
import json
import os
import stat
import sys
import textwrap
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import verify_cache_retention_full_archive_r1 as original

DONOR_SHA='c747fb3c706a2b063c154883cf470355c94e8d3027221eb33418b83df397a43a'
OUT=ROOT/'results/shared_FMA2_full_RTL_r1/smooth_rtl'
FULL='workspace/dfx/smooth_speed/shared_fma2_RTL_r1'
HLS='workspace/dfx/smooth_speed/shared_fma2_r1/HLS'
PREFIX='workspace/dfx/smooth_speed/shared_fma2_r1/'

def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def run_original_blocks(scope):
    donor=ROOT/'tools/verify_cache_retention_full_archive_r1.py'
    assert sha(donor)==DONOR_SHA
    source=donor.read_text()
    anchors=[('        native=[];whole=[]','        window=read('),
             ("        derivation=read(FULL+'/loop_derivation.json')",'        all_banks={};receipts={}'),
             ('        all_banks={};receipts={}','    return dict(status=')]
    proof=[]
    for index,(start,end) in enumerate(anchors):
        assert source.count(start)==1
        begin=source.index(start); finish=source.index(end,begin)
        block=source[begin:finish]
        edits=[]
        actual=block
        if index==0:
            edits=[
                ("manifest[prefix+'test_full_banks_r2586.py']",
                 "sha(ROOT/'dfx/smooth_speed/cache_retention_r1/test_full_banks_r2586.py')"),
                ("manifest[prefix+'test_derivation_r2586.json']",
                 "sha(ROOT/'dfx/smooth_speed/shared_fma2_r1/test_derivation_r2586.json')"),
                ("else:assert manifest['workspace/'+name]==value,name", "else:binding({name:value})")]
            for before,after in edits:
                assert actual.count(before)==1
                actual=actual.replace(before,after)
        exec(compile(textwrap.dedent(actual),str(donor),'exec'),scope)
        proof.append(dict(start=start.strip(),end=end.strip(),original_sha256=hashlib.sha256(block.encode()).hexdigest(),
            executed_sha256=hashlib.sha256(actual.encode()).hexdigest(),
            source_address_edits=[dict(before=a,after=b,occurrences=1) for a,b in edits],
            qualification_predicates_unchanged=True))
    assert sum(scope['all_banks'].values())==6422850
    return proof

def inspect():
    receipt=json.loads((OUT/'download_verified_r2617.json').read_text())
    assert receipt['all_archived_outputs_and_closed_logs_full_SHA_verified']
    assert receipt['actual_original_worker_and_all_owned_processes_terminal']
    assert json.loads((OUT/'cleanup_verified_r2617.json').read_text())['owned_root_confirmed_absent']
    archive=OUT/'result.zip'; meta=receipt['archive']
    assert archive.stat().st_size==meta['bytes'] and sha(archive)==meta['sha256']
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('outputs_manifest.json'))
        assert len(manifest)==meta['count']==1969
        assert len(z.namelist())==len(set(z.namelist()))
        assert set(z.namelist())==set(manifest)|{'outputs_manifest.json'}
        for name,h in manifest.items():
            p=PurePosixPath(name)
            assert p.as_posix()==name and not p.is_absolute() and ':' not in name and '\\' not in name
            assert all(v not in ('','.','..') for v in name.split('/'))
            assert not stat.S_ISLNK(z.getinfo(name).external_attr>>16)
            with z.open(name) as f: assert hashlib.file_digest(f,'sha256').hexdigest()==h,name
        def read(name): return json.loads(z.read(name))
        external_prior_evidence={}
        def binding(mapping):
            for name,h in mapping.items():
                if 'workspace/'+name in manifest: assert manifest['workspace/'+name]==h,name
                else:
                    assert sha(ROOT/name)==h,name
                    external_prior_evidence[name]=h
        terminal=read('terminal.json')
        assert terminal['tool_gates_passed'] and terminal['failure'] is None
        assert terminal['all_owned_compiler_processes_terminal'] and terminal['full_original_test_scope_preserved']
        job=read(FULL+'/job.json')
        assert job['stage']=='complete' and job['status']=='actual16K_original14_full_RTL_passed'
        for key in ['ordinary_passed','random_passed','full_RTL_passed',
                    'original_all_6422850_writable_words_required','all_original_14_cases_and_6422850_words_retained']:
            assert job[key],key
        assert not any(job[k] for k in ['actual_RM_passed','route_passed','PL_accessed','production_promoted'])
        # Every actual input of this new RTL job must be in its own archive.
        assert all('workspace/'+n in manifest for n in job['source_and_evidence_sha256'])
        binding(job['source_and_evidence_sha256'])
        setup=read(PREFIX+'RTL_setup_r1/acceptance.json')
        assert setup['status']=='actual16K_HLS_database_official_setup_and_all7_Csim_passed'
        for key in ['actual_SYN_RTL_identical_before_after_and_SIM','fresh_hierarchy_and_dependency_monitors',
                    'original7_Csim_6_independent_native_oracles_overflow_circular_and_invalid_passed',
                    'original_HLS_component_unchanged','no_old_simulation_results_reused']:
            assert setup[key],key
        # Setup also bound thousands of temporary HLS database files. They were
        # fully collected/hashed before user-required curation. Check their
        # exact original manifest identities, and stream every retained member;
        # do not restore discarded compiler caches just to read their hashes.
        setup_dir=ROOT/'results/shared_FMA2_RTL_setup_r1/smooth_rtl'
        curated=json.loads((setup_dir/'curation.json').read_text())
        assert curated['all_original_members_stream_SHA_verified'] and curated['original_member_count']==7633
        assert curated['all7_original_Csim_passed'] and curated['exact_owned_server_root_absent']
        setup_archive=setup_dir/'current_candidate.zip'
        assert sha(setup_archive)==curated['current_candidate_archive_sha256']
        with zipfile.ZipFile(setup_archive) as prior:
            retained=json.loads(prior.read('outputs_manifest.json'))
            assert len(retained)==curated['retained_members']==541
            assert set(prior.namelist())==set(retained)|{'outputs_manifest.json'}
            for name,h in retained.items():
                with prior.open(name) as f: assert hashlib.file_digest(f,'sha256').hexdigest()==h,name
            original_manifest=json.loads(prior.read('collection/original_outputs_manifest.json'))
            assert len(original_manifest)==7633
            for name,h in setup['source_and_evidence_sha256'].items():
                assert original_manifest['workspace/'+name]==h,name
            assert retained[PREFIX+'RTL_setup_r1/acceptance.json']==manifest[PREFIX+'RTL_setup_r1/acceptance.json']
        for name,h in setup['actual_SYN_RTL_sha256'].items():
            assert manifest[HLS+'/component/hls/syn/verilog/'+name]==h,name
        top=z.read(HLS+'/component/hls/syn/verilog/mesh_smooth.v').decode()
        for channel in range(5): assert f'.CH{channel}_NUM_READ_OUTSTANDING( 4 )' in top
        assert '.NUM_READ_OUTSTANDING( 20 )' in top
        paired=read(PREFIX+'results/native_paired.json')
        assert paired['full_native_cases_per_host']==144 and paired['complete_own_CT_calls_per_host']==18
        assert paired['all_original_case_generators_and_oracles_unchanged']
        binding(paired['source_sha256']); binding(paired['evidence_sha256'])
        boundaries=read(PREFIX+'results/boundaries_paired.json')
        assert boundaries['all_original144plus18_still_required']
        assert boundaries['extra_boundary_cases_each']==16 and boundaries['window_requests_each']==32000
        external_boundaries={}
        for name,h in boundaries['source_and_evidence_sha256'].items():
            if 'workspace/'+name in manifest: assert manifest['workspace/'+name]==h,name
            else:
                assert sha(ROOT/name)==h,name
                external_boundaries[name]=h
        admission=read('workspace/results/shared_FMA2_full_RTL_r1/smooth_rtl/admission.json')
        assert admission['HLS_forecast_failure_preserved']
        assert admission['native144_full_CT18_both_hosts_and7_typed_Csim_passed']
        binding(admission['source_and_evidence_sha256'])
        vendor_path=ROOT/'results/server2_smooth_post_runtime_r2415/readonly_vendor_probe.json'
        assert sha(vendor_path)==original.VENDOR_PROBE_SHA256
        vendor=json.loads(vendor_path.read_text()); expected_vendor=vendor['expected_by_filename']
        assert expected_vendor==original.EXPECTED_OFFICIAL_DLLS and len(vendor['rows'])==8
        for row in vendor['rows']:
            assert row['exists'] and row['sha256']==expected_vendor[row['path'].replace('\\','/').split('/')[-1]]
        scope=dict(z=z,manifest=manifest,read=read,binding=binding,ROOT=ROOT,
            prefix=PREFIX,FULL=FULL,HLS=HLS,expected_vendor=expected_vendor,
            BANKS=original.BANKS,compare_streams=original.compare_streams,ast=ast,hashlib=hashlib,sha=sha,
            digest=original.digest)
        blocks=run_original_blocks(scope)
        proof=dict(schema='kv260.actual16K.full14.independent_reader.v1',status='full14_complete_archive_verified',
            archive_sha256=meta['sha256'],archive_members=1969,all_original_members_stream_SHA_checked=True,
            all_6422850_words_compared_independently=True,all_banks=scope['all_banks'],
            original_checker_source_sha256=DONOR_SHA,checker_block_derivation=blocks,
            all144_native_and18_own_CT_each_host_and7_official_Csim_preserved=True,
            all5_banks20_ID_guards17_control_fields_watchdogs_and8_vendor_DLLs_each_mode_checked=True,
            additional16_boundaries_and32000_window_requests_each_host_preserved=True,
            separately_retained_boundary_source_and_evidence_sha256=external_boundaries,
            separately_retained_prior_native_source_and_evidence_sha256=external_prior_evidence,
            fresh_actual16K_SYN_and_SIM_identity_verified=True,
            failed_HLS_forecast_preserved=True,precision_or_case_scope_changed=False,
            every_owned_server_file_collected_before_exact_root_removal=True,
            server_root='D:/k26-r2617-e03886599e444645',owned_server_root_confirmed_absent=True,
            full_RTL_passed=True,route_and_fullPR_passed=False,board_PL_tested=False,
            current_default_firmware_replaced=False,
            verifier_sha256=sha(Path(__file__)),word_parser_sha256=sha(ROOT/'tools/verify_compact_manual_post_archive_r604.py'))
    return proof

def main():
    host='Windows' if os.name=='nt' else 'ARM'
    result=inspect(); result['host']=host
    path=OUT/('verified_full14_'+host+'.json')
    with path.open('x',encoding='utf-8') as f: json.dump(result,f,indent=2); f.write('\n')
    print('PASS',host,'actual16K all14 RTL,6422850 words, original guards and oracles',flush=True)

if __name__=='__main__': main()
