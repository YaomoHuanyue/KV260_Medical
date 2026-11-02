"""Independently check all398 complete hardware transactions, without bulk extraction."""
from pathlib import Path
from contextlib import ExitStack
import argparse,hashlib,importlib.util,io,json,re,zipfile
HERE=Path(__file__).resolve().parent;CORE=HERE.parent;ROOT=CORE.parents[2]
OUT=ROOT/'results/CT_pool_full199_RTL_20261021_r6/axis_rtl'
OLD=ROOT/'results/CT_pool_full199_RTL_20261021_r5/axis_rtl'
FIXTURE=CORE/'full_RTL_r1/fixtures_r1.zip'
CODEC=ROOT/'modules/reconstruction/smooth_pipeline_r2/axis_fma3_area_r14/flow_RTL_r1/verify_collected.py'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def codec_module():
    spec=importlib.util.spec_from_file_location('pool_complete398_closed_capture',CODEC)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def check_capture(stream,fixture,transactions):
    cases=json.loads(fixture.read('cases.json'))['cases'];manifest=json.loads(fixture.read('outputs_manifest.json'))
    digest=hashlib.sha256();rows=[]
    def line():
        raw=stream.readline();assert raw,'Truncated capture';digest.update(raw);return raw.strip()
    for index,kind in transactions:
        if index==1000:status=0;sizes=[32,0]
        else:
            case=cases[index];status=case['expected_status'];sizes=[case['blobs'][bank]['bytes'] for bank in ('full','pooled')]
        expected=f'CASE {index} KIND {kind} STATUS {status} FULL {sizes[0]//32} POOL {sizes[1]//32}'.encode()
        assert line()==expected,('Header mismatch',index,kind)
        words=0
        for bank,size in zip(('full','pooled'),sizes):
            if index==1000:
                gold=io.BytesIO((0x12345678).to_bytes(32,'little') if bank=='full' else b'');expected_digest=None
            else:
                member=f'case{index:03d}/{bank}.bin';gold=fixture.open(member);expected_digest=manifest[member]
            reference_digest=hashlib.sha256()
            with gold:
                for offset in range(0,size,32):
                    original=gold.read(32);assert len(original)==32
                    reference_digest.update(original);actual=line()
                    assert re.fullmatch(rb'[0-9a-fA-F]{64}',actual),('Malformed output',index,bank,offset)
                    assert int(actual,16)==int.from_bytes(original,'little'),('Word differs',index,kind,bank,offset//32)
                    words+=1
                assert not gold.read(1),('Reference size differs',index,bank)
            if expected_digest is not None:assert reference_digest.hexdigest()==expected_digest
        assert line()==f'END_CASE {index}'.encode(),('Missing transaction end',index,kind)
        rows.append(dict(index=index,kind=kind,status=status,full_bytes=sizes[0],pool_bytes=sizes[1],all_words_exact=words))
    tail=stream.read();digest.update(tail);assert not tail.strip(),'Unexpected capture tail'
    return rows,digest.hexdigest()

def preflight():
    codec=codec_module()
    with ExitStack() as stack:
        view=codec.View(stack,OLD/'current_candidate.zip');fixture=stack.enter_context(zipfile.ZipFile(FIXTURE))
        raw=view.read('s/ordinary/p/pool_sim.sim/sim_1/behav/xsim/actual_output.dat')
        transactions=[(i,0) for i in range(3)];rows,_=check_capture(io.BytesIO(raw),fixture,transactions)
        assert len(rows)==3
        normalized=b'\n'.join(x.strip() for x in raw.splitlines() if x.strip())+b'\n'
        first_hex=re.search(rb'(?m)^[0-9a-f]{64}$',normalized);assert first_hex
        mutated=normalized[:first_hex.start()]+f'{int(first_hex[0],16)^1:064x}'.encode()+normalized[first_hex.end():]
        negatives={
            'one_output_bit_corrupted':mutated,
            'status_changed':normalized.replace(b'CASE 0 KIND 0 STATUS 0',b'CASE 0 KIND 0 STATUS 1',1),
            'transaction_reordered':normalized.replace(b'CASE 0 KIND 0',b'CASE 1 KIND 0',1),
            'last_transaction_truncated':normalized.rsplit(b'END_CASE 2',1)[0],
            'extra_capture_payload':normalized+b'12345678\n'}
        for name,bad in negatives.items():
            try:check_capture(io.BytesIO(bad),fixture,transactions)
            except AssertionError:pass
            else:raise AssertionError('Checker admitted '+name)
    return dict(status='same_full_capture_checker_accepts_real3_case_prefix_refuses5_corruptions_not_full_RTL_pass',
        actual_closed_early3_positive=True,checker_negative_refusals=list(negatives),
        full199_each_mode_not_yet_verified=True,whole_goal_completed=False)

def verify_progress_edit(raw,monitor,contract):
    assert hashlib.sha256(raw).hexdigest()==monitor['actual_SV_SHA256']
    assert monitor['original_SV_SHA256']==contract['generated_SV_SHA256']
    text=raw.decode('ascii')
    if '\r\n' in text:
        assert text.count('\r\n')==text.count('\n') and '\r' not in text.replace('\r\n','')
        before=monitor['literal_edit']['before'].replace('\n','\r\n')
        after=monitor['literal_edit']['after'].replace('\n','\r\n')
        newline='CRLF'
    else:
        assert '\r' not in text
        before=monitor['literal_edit']['before'];after=monitor['literal_edit']['after'];newline='LF'
    assert text.count(after)==1
    restored=text.replace(after,before).encode('ascii')
    assert hashlib.sha256(restored).hexdigest()==contract['generated_SV_SHA256']
    return dict(actual_newline=newline,actual_raw_SHA256=hashlib.sha256(raw).hexdigest(),
        exact_original_raw_SHA256=hashlib.sha256(restored).hexdigest(),only_recorded_progress_literal_removed=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preflight',action='store_true');args=parser.parse_args()
    if args.preflight:
        target=HERE/'checker_preflight_r1.json';assert not target.exists();record=preflight()
        record['source_and_evidence_SHA256']={p.relative_to(ROOT).as_posix():sha(p) for p in
            (Path(__file__),CODEC,OLD/'closed_failure_audit_r2.json',CORE/'full_RTL_r1/fixtures_verified_r1.json')}
        with target.open('x') as f:json.dump(record,f,indent=2)
        print('PASS independent full-capture checker real3 prefix and5 corruptions refused; NOT full RTL qualification',flush=True);return
    target=OUT/'verified_Windows.json';assert not target.exists();assert preflight()['actual_closed_early3_positive']
    collection=json.loads((OUT/'stream_collection_verified.json').read_text());cleanup=json.loads((OUT/'cleanup_verified_stream.json').read_text())
    assert collection['all_original_members_stream_SHA_verified_locally'] and collection['original_complete_archive_not_written_locally']
    assert cleanup['owned_root_confirmed_absent'] and cleanup['all_owned_member_bytes_and_closed_logs_stream_SHA_verified_locally']
    archive=OUT/'current_candidate.zip';assert sha(archive)==collection['compact_archive_SHA256']
    fixture_proof=json.loads((CORE/'full_RTL_r1/fixtures_verified_r1.json').read_text());assert sha(FIXTURE)==fixture_proof['archive_SHA256']
    codec=codec_module();prefix='workspace/'+HERE.relative_to(ROOT).as_posix()+'/'
    captured={};stages=[]
    with ExitStack() as stack:
        view=codec.View(stack,archive);fixture=stack.enter_context(zipfile.ZipFile(FIXTURE))
        assert len(view.z.namelist())==len(set(view.z.namelist()))
        for name,digest in view.names.items():
            with view.z.open(name) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==digest,name
        terminal=json.loads(view.read('terminal.json'));assert terminal['tool_gates_passed'] and terminal['all_owned_compiler_processes_terminal']
        complete=json.loads(view.read(prefix+'complete.json'))
        for key in ('original193_each_mode_plus2_trailing4_recoveries_total199_retained',
            'four_actual_global_reset_targets_and_all_recovery_words_checked',
            'actual_input_AXIStream321bit_and_all5_AXI_channels_holds_bounds_ID_guards',
            'no_duplicate_DDR_writes_full_outputs_padding_status_checked',
            'all_three_original_real_floating_operator_IPs_and_original_HLS_RTL_unchanged',
            'all_original_RAM_initializers_at_actual_CWD_no_missing_readmem_warning',
            'all193_gold_bytes_and_input_vectors_from_frozen_fixture_archive',
            'both_fresh_simulators_compiled_before_long_run'):
            assert complete[key],key
        assert complete['fixture_archive_SHA256']==sha(FIXTURE)
        admission=json.loads(view.read(prefix+'admission.json'))
        for name,digest in admission['source_and_evidence_SHA256'].items():
            assert sha(ROOT/name)==digest,name
            with view.stream('workspace/'+name) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==digest,name
        generated=admission['generated_HLS_assets_SHA256'];base='modules/segmentation/ct_pool_fusion_r1/HLS_probe_r6/component/'
        expected_component={name.removeprefix(base):digest for name,digest in generated.items()}
        assert all(name.startswith(base) for name in generated) and expected_component==complete['actual_HLS_component_SHA256']
        assert len([n for n in expected_component if n.startswith('hls/syn/verilog/') and n.endswith('.v')])==54
        assert len([n for n in expected_component if n.startswith('hls/syn/verilog/') and n.endswith('_ip.tcl')])==3
        for name,digest in expected_component.items():
            with view.stream(prefix+'source_component/'+name) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==digest,name
        order=[i for i in range(193) if i not in (16,17)]+[16,17]
        transactions=[(i,0) for i in order]+[(43,20),(1000,21)]+[(43,10+i) for i in range(4)]
        assert len(transactions)==199
        for mode in ('ordinary','random'):
            for stage in ('setup','compile','elaborate','simulate'):
                tool=json.loads(view.read(prefix+f'run/{mode}/{stage}_receipt.json'))
                assert tool['exit_code']==0 and tool['all_owned_processes_terminal'] and tool['configured_limit_verified']
                assert tool['job_memory_limit_bytes']==16*1024**3 and not tool['resource_failure'] and not tool['elapsed_time_abort']
                stages.append(dict(mode=mode,stage=stage,elapsed_s=tool['elapsed_s'],peak_job_bytes=tool['reported_peak_job_bytes']))
            log=view.read(prefix+f'run/{mode}/simulate.log').decode(errors='replace')
            actual_cases=re.findall(r'POOL_RTL_CASE case=(\d+) kind=(\d+) ',log)
            assert [(int(i),int(k)) for i,k in actual_cases]==transactions
            resets=re.findall(r'POOL_ACTUAL_RESET stage=(\d+) input=(\d+) stable=(\d+)',log)
            assert [int(row[0]) for row in resets]==list(range(4))
            assert int(resets[0][1])>=8 and all(int(row[2])>=3 for row in resets[1:]) and int(resets[1][1])>0
            assert log.count('POOL_TRAILING_TWO_CALLS_NO_RESET_EXACT')==1 and 'PASS POOL_FULL193_TRAILING2_RESET4_RECOVERY4 completed=199' in log
            assert not any(t in log for t in ('ERROR:','Fatal:','FATAL:','cannot be opened for reading'))
            if mode=='random':
                counts=re.search(r'completed=199 input_stalls=(\d+) read_stalls=(\d+) write_stalls=(\d+)',log)
                assert counts and all(int(n)>0 for n in counts.groups())
            tbraw=view.read(prefix+f'run/{mode}/tb.sv')
            monitor=json.loads(view.read(prefix+f'run/{mode}/progress_monitor_derivation.json'))
            contract=json.loads(view.read(prefix+f'run/{mode}/harness_contract.json'))
            verify_progress_edit(tbraw,monitor,contract)
            assert contract['case_order']==order
            assert contract['main_watchdog_cycles']=='send_words*64+250000'
            assert contract['all_original193_plus2_no_reset_trailing_calls_plus4_full_recoveries_required']==199
            member=f's/{mode}/p/pool_sim.sim/sim_1/behav/xsim/actual_output.dat'
            with view.stream(member) as f:rows,digest=check_capture(f,fixture,transactions)
            assert digest==view.original[member]
            captured[mode]=dict(transactions=rows,total_words=sum(row['all_words_exact'] for row in rows),
                actual_capture_SHA256=digest,reset_markers=resets)
    assert captured['ordinary']['transactions']==captured['random']['transactions']
    proof=dict(status='independent_actual_R6_all398_full_transactions_and4_resets_each_mode_verified_not_DFX_or_board',
        original193_plus2_trailing4_recoveries_total199_each_mode=199,
        all398_full_outputs_padding_status_and_next_marker_independently_exact=True,
        real4_global_resets_each_mode_not_live_DFX_abort_qualification=True,
        actual_321bit_AXIS_and_all_AXI_channels_random_backpressure_ID_bounds_guards_checked=True,
        original54_HLS_modules_and_all3_real_FP_IP_settings_and_initializer_assets_exact=True,
        actual_diagnostics_and_watchdog_and_test_scope_unchanged=True,
        all_owned_member_bytes_closed_logs_collected_and_exact_root_absent=True,
        captured=captured,stages=stages,archive_SHA256=sha(archive),
        whole_C5_RM100MHz_all5PR_ARM_full139_model_strongestPS_board_and_integration_pending=True,
        source_and_evidence_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in
            (Path(__file__),CODEC,CORE/'full_RTL_r1/fixtures_verified_r1.json',HERE/'checker_preflight_r1.json',
             OUT/'stream_collection_verified.json',OUT/'cleanup_verified_stream.json')},
        PL_accessed=False,production_promoted=False,whole_goal_completed=False)
    with target.open('x',encoding='utf-8') as f:json.dump(proof,f,indent=2)
    print('PASS independent398 full hardware transactions and8 resets; whole C5/DFX/board speed pending',flush=True)

if __name__=='__main__':main()
