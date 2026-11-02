"""Independently verify all986 outputs, eight resets and actual AXI burst receipts."""
from pathlib import Path
from contextlib import ExitStack
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import io
import json
import re
import sys

from fixture_view import Fixtures

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
ROOT = CORE.parents[2]
sys.path.insert(0, str(ROOT/'tools'))
import project_storage

OUT = ROOT/'results/CT_pool_full493_RTL_20261021_r7/axis_rtl'
FIXTURE = CORE/'full_RTL_r1/fixtures_r1.zip'
PARENT = CORE/'full_RTL_r2/verify_collected_r2.py'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def parent():
    spec = importlib.util.spec_from_file_location('unchanged_C5_full_capture_checker', PARENT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def transactions():
    order = [i for i in range(487) if i not in (16, 17)]+[16, 17]
    return [(i, 0) for i in order]+[(43, 20), (1000, 21)]+[(43, 10+i) for i in range(4)]


BURST = re.compile(r'POOL_AXI_BURSTS case=(\d+) kind=(\d+) full_req=(\d+) pool_req=(\d+) '
    r'full_beats=(\d+) pool_beats=(\d+) full_multi=(\d+) pool_multi=(\d+) full_base=(\d+) pool_base=(\d+)')


def check_bursts(log, cases, calls, require_final=True):
    rows = [list(map(int, row)) for row in BURST.findall(log)]
    assert len(rows) == len(calls)
    assert [(row[0], row[1]) for row in rows] == calls
    for row in rows:
        index, kind, fr, pr, fb, pb, fm, pm, fbase, pbase = row
        if index == 1000:
            full_bytes, pool_bytes, mode = 32, 0, 0
        else:
            case = cases[index]
            full_bytes, pool_bytes = [case['blobs'][bank]['bytes'] for bank in ('full', 'pooled')]
            mode = case['mode']
        assert (fb*32, pb*32) == (full_bytes, pool_bytes)
        for requests, beats, multi in ((fr, fb, fm), (pr, pb, pm)):
            assert 0 <= multi <= requests <= beats
            assert (requests == 0) == (beats == 0)
            assert beats >= requests+multi
            assert beats <= requests*64
        if mode > 0 and full_bytes >= 64:
            assert fm > 0, ('No full multi-beat burst', index)
        if pool_bytes >= 64:
            assert pm > 0, ('No pooled multi-beat burst', index)
        if index < 193 or index == 1000:
            full_offset = pool_offset = 0
        else:
            full_offset = 4064 if index%3 == 0 else (32 if index%3 == 1 else 0)
            pool_offset = 4064 if index%3 == 1 else (96 if index%3 == 2 else 0)
        assert fbase == 4096+full_offset
        assert pbase == 4096+16777216+4096+pool_offset
        assert fbase+full_bytes < 0x80000000 and pbase+pool_bytes < 0x80000000
    if require_final:
        matches = re.findall(r'POOL_NORMAL_BURSTS_VERIFIED cases=487 full_multi=(\d+) pool_multi=(\d+) boundary_ends=(\d+)', log)
        assert len(matches) == 1
        fm, pm, ends = map(int, matches[0])
        assert (fm, pm) == (sum(row[6] for row in rows[:487]), sum(row[7] for row in rows[:487]))
        assert fm > 0 and pm > 0 and ends > 0
    return rows


def preflight():
    legacy = parent()
    real = legacy.preflight()
    assert real['actual_closed_early3_positive'] and len(real['checker_negative_refusals']) == 5
    with Fixtures(FIXTURE) as fixture:
        cases = json.loads(fixture.read('cases.json'))['cases']
        calls = [(247, 0)]
        row = cases[247]
        sizes = [row['blobs'][bank]['bytes'] for bank in ('full', 'pooled')]
        pieces = [f"CASE 247 KIND 0 STATUS {row['expected_status']} FULL {sizes[0]//32} POOL {sizes[1]//32}\n".encode()]
        for bank in ('full', 'pooled'):
            raw = fixture.read('case247/'+bank+'.bin')
            pieces.extend(f'{int.from_bytes(raw[i:i+32], "little"):064x}\n'.encode() for i in range(0, len(raw), 32))
        pieces.append(b'END_CASE 247\n')
        captured, _ = legacy.check_capture(io.BytesIO(b''.join(pieces)), fixture, calls)
        assert captured[0]['all_words_exact'] == sum(sizes)//32
        base = 4096+16777216+4096
        fr, pr = sizes[0]//32, sizes[1]//32
        requests_full, requests_pool = (fr+63)//64, (pr+63)//64
        log = (f'POOL_AXI_BURSTS case=247 kind=0 full_req={requests_full} pool_req={requests_pool} full_beats={fr} pool_beats={pr} '
               f'full_multi=1 pool_multi=1 full_base=4128 pool_base={base+4064}')
        assert check_bursts(log, cases, calls, False)
        negatives = {
            'missing_burst_receipt': '',
            'duplicate_burst_receipt': log+'\n'+log,
            'wrong_full_beats': log.replace(f'full_beats={fr}', 'full_beats=0'),
            'wrong_pool_beats': log.replace(f'pool_beats={pr}', 'pool_beats=0'),
            'no_full_multibeat': log.replace('full_multi=1', 'full_multi=0'),
            'no_pool_multibeat': log.replace('pool_multi=1', 'pool_multi=0'),
            'wrong_near4K_full_base': log.replace('full_base=4128', 'full_base=4096'),
            'wrong_near4K_pool_base': log.replace(f'pool_base={base+4064}', f'pool_base={base}'),
            'wrong_case': log.replace('case=247', 'case=248'),
            'impossible_request_capacity': log.replace(f'full_req={requests_full}', 'full_req=1'),
        }
        for name, bad in negatives.items():
            try:
                check_bursts(bad, cases, calls, False)
            except AssertionError:
                pass
            else:
                raise AssertionError('Burst checker admitted '+name)
    return dict(actual_old_three_case_capture_and_five_corruptions_checked=True,
        new_pooled_carry_case_capture_parser_checked=True, burst_checker_negative_refusals=list(negatives),
        new_positive_capture_and_burst_receipt_are_synthetic_checker_tests_not_new_actual_RTL=True,
        full986_actual_outputs_and_all8resets_still_required=True, whole_goal_completed=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    project_storage.check(110_000_000)
    if args.preflight:
        target = HERE/'checker_preflight_r1.json'
        assert not target.exists()
        proof = preflight()
        proof['source_and_evidence_SHA256'] = {p.relative_to(ROOT).as_posix():sha(p) for p in
            (Path(__file__), HERE/'fixture_view.py', HERE/'fixtures_verified_r7.json', PARENT)}
        with target.open('x', encoding='utf-8') as stream:
            json.dump(proof, stream, indent=2)
        print('PASS real old3 capture/five negatives plus new carry parser/nine burst negatives; no new RTL pass claim')
        return
    target = OUT/'verified_Windows.json'
    assert not target.exists()
    legacy = parent()
    codec = legacy.codec_module()
    collection = json.loads((OUT/'stream_collection_verified.json').read_text())
    cleanup = json.loads((OUT/'cleanup_verified_stream.json').read_text())
    assert collection['all_original_members_stream_SHA_verified_locally'] and collection['original_complete_archive_not_written_locally']
    assert cleanup['owned_root_confirmed_absent'] and cleanup['all_owned_member_bytes_and_closed_logs_stream_SHA_verified_locally']
    archive = OUT/'current_candidate.zip'
    assert sha(archive) == collection['compact_archive_SHA256']
    prefix = 'workspace/'+HERE.relative_to(ROOT).as_posix()+'/'
    captured = {}
    bursts = {}
    with ExitStack() as stack:
        view = codec.View(stack, archive)
        fixture = stack.enter_context(Fixtures(FIXTURE))
        cases = json.loads(fixture.read('cases.json'))['cases']
        calls = transactions()
        assert len(calls) == 493
        terminal = json.loads(view.read('terminal.json'))
        assert terminal['tool_gates_passed'] and terminal['all_owned_compiler_processes_terminal']
        complete = json.loads(view.read(prefix+'complete.json'))
        for key in ('original193_plus294_each_mode_plus2_trailing4_recoveries_total493_retained',
            'four_actual_global_reset_targets_and_all_recovery_words_checked',
            'actual_input_AXIStream321bit_and_all5_AXI_channels_holds_bounds_ID_guards',
            'no_duplicate_DDR_writes_full_outputs_padding_status_checked',
            'actual_full_pool_multi_beat_AXI_bursts_near4K_offsets_and_all493_eachmode_checked',
            'all_three_original_real_floating_operator_IPs_and_original_HLS_RTL_unchanged',
            'all_original_RAM_initializers_at_actual_CWD_no_missing_readmem_warning',
            'all487_gold_bytes_and_input_vectors_from_original_and_delta_fixture_archives',
            'both_fresh_simulators_compiled_before_long_run'):
            assert complete[key], key
        assert complete['fixture_archive_SHA256'] == sha(FIXTURE)
        assert complete['delta_fixture_archive_SHA256'] == sha(HERE/'fixtures_delta_r7.zip')
        admission = json.loads(view.read(prefix+'admission.json'))
        for name, digest in admission['source_and_evidence_SHA256'].items():
            assert sha(ROOT/name) == digest
            with view.stream('workspace/'+name) as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == digest
        generated = admission['generated_HLS_assets_SHA256']
        base = 'modules/segmentation/ct_pool_fusion_r1/HLS_probe_r7/component/'
        expected = {name.removeprefix(base):digest for name, digest in generated.items()}
        assert all(name.startswith(base) for name in generated)
        assert expected == complete['actual_HLS_component_SHA256']
        assert sum(name.startswith('hls/syn/verilog/') and name.endswith('.v') for name in expected) == 57
        assert sum(name.startswith('hls/syn/vhdl/') and name.endswith('_ip.tcl') for name in expected) == 3
        for name, digest in expected.items():
            with view.stream(prefix+'source_component/'+name) as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == digest
        for mode in ('ordinary', 'random'):
            for stage in ('setup', 'compile', 'elaborate', 'simulate'):
                receipt = json.loads(view.read(prefix+f'run/{mode}/{stage}_receipt.json'))
                assert receipt['exit_code'] == 0 and receipt['all_owned_processes_terminal'] and receipt['configured_limit_verified']
                assert receipt['job_memory_limit_bytes'] == 16*1024**3
                assert not receipt['resource_failure'] and not receipt['elapsed_time_abort']
            log = view.read(prefix+f'run/{mode}/simulate.log').decode(errors='replace')
            assert [(int(i), int(k)) for i, k in re.findall(r'POOL_RTL_CASE case=(\d+) kind=(\d+) ', log)] == calls
            resets = re.findall(r'POOL_ACTUAL_RESET stage=(\d+) input=(\d+) stable=(\d+)', log)
            assert [int(row[0]) for row in resets] == list(range(4))
            assert int(resets[0][1]) >= 8 and int(resets[1][1]) > 0 and all(int(row[2]) >= 3 for row in resets[1:])
            assert log.count('POOL_TRAILING_TWO_CALLS_NO_RESET_EXACT') == 1
            assert 'PASS POOL_FULL487_TRAILING2_RESET4_RECOVERY4 completed=493' in log
            assert not any(token in log for token in ('ERROR:', 'Fatal:', 'FATAL:', 'cannot be opened for reading'))
            if mode == 'random':
                stalls = re.search(r'completed=493 input_stalls=(\d+) read_stalls=(\d+) write_stalls=(\d+)', log)
                assert stalls and all(int(value) > 0 for value in stalls.groups())
            bursts[mode] = check_bursts(log, cases, calls)
            contract = json.loads(view.read(prefix+f'run/{mode}/harness_contract.json'))
            monitor = json.loads(view.read(prefix+f'run/{mode}/progress_monitor_derivation.json'))
            legacy.verify_progress_edit(view.read(prefix+f'run/{mode}/tb.sv'), monitor, contract)
            assert contract['case_order'] == [index for index, kind in calls[:487]]
            assert contract['main_watchdog_cycles'] == 'send_words*64+250000'
            assert contract['all_original193_plus294_plus2_no_reset_trailing_calls_plus4_full_recoveries_required'] == 493
            member = f's/{mode}/p/pool_sim.sim/sim_1/behav/xsim/actual_output.dat'
            with view.stream(member) as stream:
                rows, digest = legacy.check_capture(stream, fixture, calls)
            assert digest == view.original[member]
            assert sum(row['all_words_exact'] for row in rows) == 932725
            captured[mode] = dict(transactions=rows, total_words=932725, actual_capture_SHA256=digest, resets=resets)
    assert captured['ordinary']['transactions'] == captured['random']['transactions']
    proof = dict(UTC=datetime.now(timezone.utc).isoformat(), all986_full_transactions_1865450_words_exact=True,
        original193_plus294_plus2trailing4recoveries493_eachmode=True, all8_actual_global_resets_and_recoveries=True,
        actual_full_and_pool_multibeat_AXI_requests_lowDDR4K_bounds_and_new_near4K_offsets_verified=True,
        all_original_AXIS_AXIL_AXI_holds_padding_status_guards_nextpacket_and_watchdog_retained=True,
        actual57_original_HLS_modules_three_real_FP_IPs_and_actual_CWD_initializers_exact=True,
        every_owned_byte_closed_log_collected_and_exact_task_root_absent=True,
        captured=captured, actual_bursts=bursts, archive_SHA256=sha(archive),
        source_and_evidence_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in
            (Path(__file__), HERE/'fixture_view.py', HERE/'fixtures_verified_r7.json', PARENT,
             HERE/'checker_preflight_r1.json', OUT/'stream_collection_verified.json', OUT/'cleanup_verified_stream.json')},
        whole_C5_RM100MHz_all5PR_actual_ARM_full139_strongest_PS_and_formal_integration_still_required=True,
        PL_accessed=False, production_promoted=False, whole_goal_completed=False)
    with target.open('x', encoding='utf-8') as stream:
        json.dump(proof, stream, indent=2)
    print('PASS actual986 full transactions1865450 words/eight resets and real full+pool bursts; route/board pending')


if __name__ == '__main__':
    main()
