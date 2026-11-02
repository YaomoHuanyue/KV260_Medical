"""Independently stream every original bank of the completed new full RTL run.

This reader never runs a compiler, loads a bitstream, or replaces production.
Archive ownership/cleanup is verified separately by the terminal collector.
"""
from pathlib import Path, PurePosixPath
import argparse, ast, hashlib, itertools, json, os, re, stat, sys, zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from verify_compact_manual_post_archive_r604 import words, digest

FULL='workspace/dfx/smooth_speed/cache_RTL_r1'
HLS='workspace/dfx/smooth_speed/cache_retention_r1/HLS'
VENDOR_PROBE_SHA256='e22d4c5d03cbfa5f7e3877f82a7d807d19d01b3d08133cfa43fa0bb8f8bcc716'
EXPECTED_OFFICIAL_DLLS={'libstdc++-6.dll': '676353b7116b380fba0f878eb87a72030c22050a2fd10b8fb87b66f926052e5f', 'libgcc_s_seh-1.dll': '2c73c4d29815ab30dedd742058df08b35bff7bc83bf5ab1cb792601e0f229ff1', 'libwinpthread-1.dll': '609089f045eda398f0af1592f240f446d5ec9e1edb0de755f334a385660e3d76', 'libhlsm-GCC95-x64.dll': '616c3462d42cd1e32e63af5b41b551d6d0d4f8fa3b7e055ee15b55f4c92ebfc7', 'libhlsmc++-GCC95-x64.dll': '2753430c7be5247e4670c7b9d18072fa4c6ab119a5304642232209e50dbca78a', 'libIp_floating_point_v7_1_bitacc_cmodel.dll': '64fd4bd63d0282f68fb8ad3af12b554e1cf15991ca4969ba4fe55b4e9ee45a62', 'libgmp.dll': '6eacc4642bdc714e80433757f25d0a502cac381f58ffc77ab2e748cda10f9044', 'libmpfr.dll': '296d4a61885652cffec89024f8be9611c0edea914337a991d2859e02ecadde1a'}
BANKS=(('meta',32,131090),('coords',128,327685))


def compare_streams(raw,gold,width,count):
    checked=0
    for actual,expected in itertools.zip_longest(words(raw,width,count),words(gold,width,count)):
        assert actual==expected,(checked,actual,expected)
        checked+=1
    assert checked==7*count
    return checked


def inspect(archive,expected_sha256,expected_count):
    archive=Path(archive).resolve()
    assert archive.is_relative_to(ROOT) and len(expected_sha256)==64
    assert 0<expected_count<50000
    with archive.open('rb') as f:assert digest(f)==expected_sha256
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('outputs_manifest.json'))
        assert len(manifest)==expected_count
        assert FULL+'/job.json' in manifest and HLS+'/job.json' in manifest, 'Archive is not this exact cache-retention export'
        assert len(z.namelist())==len(set(z.namelist()))
        assert set(z.namelist())==set(manifest)|{'outputs_manifest.json'}
        for name,value in manifest.items():
            p=PurePosixPath(name)
            assert p.as_posix()==name and not p.is_absolute() and ':' not in name and '\\' not in name
            assert all(v not in ('','.','..') for v in name.split('/'))
            assert not stat.S_ISLNK(z.getinfo(name).external_attr>>16)
            with z.open(name) as f:assert digest(f)==value,name
        def read(name):return json.loads(z.read(name))
        def binding(mapping):
            for name,value in mapping.items():assert manifest['workspace/'+name]==value,name
        terminal=read('terminal.json')
        assert terminal['stage']=='terminal' and terminal['tool_gates_passed'] and terminal['failure'] is None
        assert terminal['all_owned_compiler_processes_terminal'] and terminal['full_original_test_scope_preserved']
        assert not terminal['PL_accessed'] and not terminal['production_promoted']
        job=read(FULL+'/job.json')
        assert job['stage']=='complete' and job['status']=='cache_retention_original14_full_RTL_passed'
        for key in ['ordinary_passed','random_passed','full_RTL_passed',
                    'original_all_6422850_writable_words_required',
                    'all_original_14_cases_and_6422850_words_retained']:
            assert job[key],key
        assert not any(job[k] for k in ['actual_RM_passed','route_passed','PL_accessed','production_promoted'])
        binding(job['source_and_evidence_sha256'])
        hls=read(HLS+'/job.json');binding(hls['source_and_evidence_sha256'])
        assert hls['Csim_all_seven_full_cases_passed'] and hls['Windows_and_ARM_all_144_and_18_cases_passed']
        assert hls['row_rounds_actual_II1'] and hls['requested_cached_lanes']==4
        assert hls['cached_graph_actual_read_ports']==[['0','0'],['0','1'],['1','0'],['1','1']]
        assert not hls['HLS_capacity_gate_passed']
        top=z.read(HLS+'/component/hls/syn/verilog/mesh_smooth.v').decode()
        for channel in range(5):assert f'.CH{channel}_NUM_READ_OUTSTANDING( 4 )' in top
        assert '.NUM_READ_OUTSTANDING( 20 )' in top
        prefix='workspace/dfx/smooth_speed/cache_retention_r1/'
        paired=read(prefix+'results/native_paired.json')
        binding(paired['source_and_evidence_sha256'])
        for key in ['original144_full_bank_and18_full_CT_calls_each_host_passed',
                    'all_five_banks_padding16_reports_frozen_readonly_and_guards_exact',
                    'original_SciPy_5e5_mm_gate_preserved',
                    'both_hosts28000_whole_retained_cache_requests_passed']:
            assert paired[key],key
        native=[];whole=[]
        for host in ['Windows','ARM']:
            p=read(prefix+'results/native_full_banks_'+host+'_r2586.json')
            assert p['platform']==host and len(p['cases'])==144
            binding(p['source_sha256'])
            assert p['all_five_banks_and_guards_exact_independent_std_fma']
            assert p['independent_reference_std_fma_only'] and p['original_case_generation_and_scope_preserved']
            assert p['full_report_guards_and_input_readonly_checked'] and not p['PL_access']
            for case in p['cases']:
                assert all(case[k] for k in ['all_five_raw_banks_and_padding_exact',
                    'all_ten_full_512_byte_guards_exact','all_16_report_words_exact'])
            extension='.dll' if host=='Windows' else '.so'
            assert manifest[prefix+'build_'+host+'/candidate'+extension]==p['candidate_library_sha256']
            assert manifest[prefix+'build_'+host+'/reference'+extension]==p['reference_library_sha256']
            assert manifest[prefix+'test_full_banks_r2586.py']==p['checker_sha256']
            assert manifest[prefix+'test_derivation_r2586.json']==p['origin_sha256']
            native.append(p['cases'])
            q=read(prefix+'results/own_CT_'+host+'_r2586.json')
            assert q['platform']==host and len(q['cases'])==3 and sum(len(v['tests']) for v in q['cases'])==18
            assert q['original_SciPy_tolerance_5e5_unchanged'] and not q['PL_accessed']
            assert q['candidate_library_sha256']==p['candidate_library_sha256']
            assert q['reference_receipt_sha256']=='307f20a6b7a5e2e8a64d15c7647fa7334d0228cf054f13292687694270de5768'
            for name,value in q['source_and_evidence_sha256'].items():
                if name=='results/smoothing_precision_full_r112/acceptance.json':
                    path=ROOT/name
                    assert value==q['reference_receipt_sha256']
                    with path.open('rb') as f:assert digest(f)==value
                else:assert manifest['workspace/'+name]==value,name
            for structure in q['cases']:
                for case in structure['tests']:
                    assert case['all_five_raw_buffers_and_all_16_report_words_exact_frozen_original']
                    assert case['all_twelve_full_512_byte_guards_and_readonly_inputs_checked']
            whole.append(q['cases'])
        assert native[0]==native[1] and whole[0]==whole[1]
        window=read(prefix+'results/window_verified_Windows.json')
        assert window['requests']==28000 and window['all_requested_and_retained_words_checked']
        arm=read(prefix+'results/ARM_run/passed.json')
        assert arm['status']=='all_original144_and18_ARM_calls_and28000_cache_requests_passed'
        # The completed archive predates inclusion of the vendor observation.
        # Require its original pinned bytes locally; do not infer DLL identity
        # from a Boolean or skip any of the eight per-mode actual DLL hashes.
        vendor_path=ROOT/'results/server2_smooth_post_runtime_r2415/readonly_vendor_probe.json'
        with vendor_path.open('rb') as f:assert digest(f)==VENDOR_PROBE_SHA256
        vendor=json.loads(vendor_path.read_text())
        expected_vendor=vendor['expected_by_filename']
        assert expected_vendor==EXPECTED_OFFICIAL_DLLS
        assert len(expected_vendor)==8 and len(vendor['rows'])==8
        for row in vendor['rows']:
            assert row['exists'] and row['sha256']==expected_vendor[row['path'].replace('\\','/').split('/')[-1]]
        derivation=read(FULL+'/loop_derivation.json')
        raw_source=z.read('workspace/tools/run_shared_mean_four_full_RTL_r200.py')
        assert hashlib.sha256(raw_source).hexdigest()==derivation['parent_sha256']
        source=raw_source.decode().replace('\r\n','\n')
        tree=ast.parse(source)
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        loop=next(n for n in ast.walk(main) if isinstance(n,ast.For) and ast.get_source_segment(source,n.iter)=="['ordinary','random']")
        original=ast.get_source_segment(source,loop)
        assert original==derivation['original_complete_loop']
        actual=original.replace("'-prj','full.prj'","'-prj','profile_full.prj'").replace('F:/AMDDesignTools/2025.2.1','D:/AMDDesignTools/2025.2.1').replace("'--mt','32'","'--mt','4'")
        assert actual==derivation['actual_complete_loop']
        all_banks={};receipts={}
        for mode in ['ordinary','random']:
            accepted=read(FULL+'/'+mode+'_acceptance.json')
            assert accepted['passed'] and accepted['full_seven_cases'] and accepted['all_original_inputs_preserved']
            binding(accepted['source_and_evidence_sha256'])
            assert sum(v['total_exact_words'] for v in accepted['all_full_banks_exact'].values())==3211425
            for stage in ['compile','simulate','post']:
                name=FULL+'/'+mode+'_'+stage
                rec=read(name+'_receipt.json');binding(rec['source_and_evidence_sha256'])
                r=rec['resource_receipt']
                assert r['exit_code']==0 and r['all_owned_processes_terminal']
                assert r['configured_limit_verified'] and r['actual_default_memory_API']
                assert r['configured_job_memory_limit_bytes']==r['job_memory_limit_bytes']==32*1024**3
                assert r['minimum_system_free_commit_bytes']==1536*1024**2
                assert not r['resource_failure'] and not r['elapsed_time_abort'] and not r['job_memory_limit_rejection_observed']
                assert rec['log_sha256']==manifest[name+'.log']
                receipts[mode+'_'+stage]=manifest[name+'_receipt.json']
            simlog=z.read(FULL+'/'+mode+'_simulate.log').decode()
            assert simlog.count('R157_BOUNDED_COMPLETED case=')==7
            assert 'PASS full_original_R157_independent_bounded_AXI 7/7' in simlog
            assert not any(v in simlog for v in ['ERROR:','Fatal:','Critical WARNING'])
            postlog=z.read(FULL+'/'+mode+'_post.log').decode()
            assert 'ALL FULL INTEGER FMA SEVEN STRICT CASES PASSED' in postlog
            assert 'PASS six independent native oracle invocations plus explicit invalid case' in postlog
            runtime=read(FULL+'/'+mode+'_post_runtime.json')['external_official_DLL_sha256']
            actual_vendor={name.replace('\\','/').split('/')[-1]:value for name,value in runtime.items()}
            assert len(runtime)==len(actual_vendor)==8 and actual_vendor==expected_vendor
            sv=z.read(FULL+'/'+mode+'/sim/verilog/sv_module_top.sv').decode()
            assert sv.count('Truncated ')==20 and sv.count('axi_bounded_memory #(')==5
            assert sv.count('DUT issued unsupported or malformed read request')==5
            assert sv.count('DUT issued unsupported or malformed write request')==5
            assert sv.count('axi_passive_hold_checker #(')==5 and 'if(cycles>15000000)' in sv
            origin=read(FULL+'/'+mode+'/origin.json')
            assert origin['original_all_six_inputs_byte_values_exact'] and origin['extra_overflow_case_first']
            assert origin['all_decoded_scalars_pointers_checked'] and origin['all_bundles_drained_at_done']
            assert origin['original_watchdog_cycles']==15000000 and origin['AXI_hold_and_malformed_request_assertions']
            for name,value in origin['original_RTL_sha256'].items():
                assert manifest[HLS+'/component/hls/syn/verilog/'+name]==value,name
            control=read(FULL+'/'+mode+'/control_insertion.json')
            assert len(control['exact_seventeen_actual_DUT_AXI_Lite_fields'])==17
            for name,width,count in BANKS:
                raw=FULL+f'/{mode}/sim/tv/rtldatafile/rtl.mesh_smooth.autotvout_{name}.dat'
                gold=FULL+f'/{mode}/sim/tv/cdatafile/c.mesh_smooth.autotvout_{name}.dat'
                reported=accepted['all_full_banks_exact'][name]
                assert manifest[raw]==reported['raw_sha256'] and manifest[gold]==reported['gold_sha256']
                with z.open(raw) as r,z.open(gold) as g:
                    all_banks[mode+'_'+name]=compare_streams(r,g,width,count)
        assert sum(all_banks.values())==6422850
    return dict(status='cache_retention_full14_archive_independently_verified',
        archive=archive.relative_to(ROOT).as_posix(),archive_sha256=expected_sha256,archive_entry_count=expected_count,
        all_6422850_words_compared_independently=True,all_full_banks=all_banks,
        all144_native_and18_own_CT_cases_each_host_and7_Csim_preserved=True,
        original_all5_banks20_ID_guards17_control_fields_watchdog_post_oracles_and_complete_loop_verified=True,
        all8_original_official_post_oracle_DLL_hashes_each_mode_verified=True,
        original_failed_HLS_forecast_retained=True,evidence_streamed_without_SD_extraction=True,
        ARM_did_not_execute_Windows_post_binary=True,terminal_stage_receipt_SHA256=receipts,
        full_RTL_passed=True,actual_RM_qualification_passed=False,route_passed=False,
        PL_accessed=False,production_promoted=False,whole_goal_completed=False)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('archive',type=Path);ap.add_argument('--sha256',required=True);ap.add_argument('--count',type=int,required=True)
    a=ap.parse_args();result=inspect(a.archive,a.sha256,a.count)
    host='Windows' if os.name=='nt' else 'ARM';result['host']=host
    result['verifier_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['unchanged_word_parser_sha256']=hashlib.sha256((ROOT/'tools/verify_compact_manual_post_archive_r604.py').read_bytes()).hexdigest()
    out=ROOT/'results/cache_retention_full_archive_r1';out.mkdir(exist_ok=True)
    with (out/f'verified_{host}.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
    print('PASS independent complete new14 RTL cases and6422850 words',host)


if __name__=='__main__':main()
