"""Verify or prepare a same-ABI FMA2 manual release; never load firmware."""
from pathlib import Path
import hashlib
import json
import os
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/'dfx/smooth_speed/release_FMA2_r1'
PARTIAL='medical_smooth_speed_FMA2_r1_partial.bin'
MARKER='KV260_FMA2_100MHZ_FULLPR_PAIRED_MANUAL_RELEASE\n'


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(p):return json.loads(Path(p).read_text())


def paired_route():
    rows=[]
    for host in ['Windows','ARM']:
        value=read(ROOT/('results/shared_FMA2_PR_r1/independent_verified/verified_'+host+'.json'))
        assert value.pop('host')==host
        assert value['full_PR_passed'] and value['all_archive_members_full_SHA_verified'] and value['exact_server_root_absent']
        assert value['primary_PC_full14_6422850_words_both_hosts_exact_source_qualification_pinned']
        assert value['verifier_sha256']==sha(ROOT/'tools/verify_shared_FMA2_PR_r1.py')
        reports=value['actual_routed_reports']
        assert reports['clock_MHz']==100 and min(reports['WNS_ns'],reports['WHS_ns'])>=0
        assert reports['timing_constraints_and_DRC_and_full_PR_checked']
        rows.append(value)
    assert rows[0]==rows[1]
    return rows[0]


def paired_RTL():
    rows=[]
    for host in ['Windows','ARM']:
        value=read(ROOT/('results/shared_FMA2_full_RTL_r1/smooth_rtl/verified_current_full14_'+host+'.json'))
        assert value.pop('host')==host
        assert value['full_RTL_passed'] and value['all_6422850_words_compared_independently']
        assert value['all144_native_and18_own_CT_each_host_and7_official_Csim_preserved']
        assert value['all5_banks20_ID_guards17_control_fields_watchdogs_and8_vendor_DLLs_each_mode_checked']
        assert value['additional16_boundaries_and32000_window_requests_each_host_preserved']
        assert value['owned_server_root_confirmed_absent'] and not value['precision_or_case_scope_changed']
        assert value['verifier_sha256']==sha(ROOT/'dfx/smooth_speed/shared_fma2_r1/verify_full_RTL_current_r1.py')
        rows.append(value)
    assert rows[0]==rows[1]
    return rows[0]


def verify_release():
    path=RELEASE/'manifest.json'
    if not path.is_file():raise RuntimeError('No complete compact C2 full-PR release; hardware access refused')
    value=read(path)
    assert value['schema']=='kv260.FMA2.smoothing.manual_release.v1' and value['identity']==0xc2
    assert value['offline_verified'] and not value['production_accepted'] and not value['board_geometry_and_speed_verified']
    assert value['route']==paired_route() and value['full_RTL']==paired_RTL()
    assert value['full_original_three_structures_SciPy5e5_strongest_PS1_PS4_required']
    for name,h in value['portable_source_and_evidence_SHA256'].items():
        p=(ROOT/name).resolve();assert p.is_relative_to(ROOT) and not (ROOT/name).is_symlink() and sha(p)==h,name
    assert sha(RELEASE/PARTIAL)==value['partial_bin_sha256']
    assert (RELEASE/'native_guard.txt').read_text()==MARKER
    assert sha(ROOT/'dfx/medical/release/manifest.json')==value['static_base_manifest_SHA256']
    return value


def prepare():
    assert os.name=='nt' and not RELEASE.exists()
    sys.path.insert(0,str(ROOT/'tools'))
    from project_storage import check
    from verify_shared_FMA2_PR_r1 import verify
    check(20_000_000)
    route=paired_route();rtl=paired_RTL()
    archive=ROOT/'results/shared_FMA2_PR_r1/smooth/result.zip'
    assert verify(archive,route['archive_sha256'],route['archive_entry_count'])==route
    bindings={}
    for host in ['Windows','ARM']:
        native=read(ROOT/('results/FMA2_smoothing_host_r1/verified_'+host+'.json'))
        assert native['host']==host and native['original_full_speed_run_and22_DMA_guards_and17_control_fields_unchanged']
        assert native['no_actual_PL_context_or_firmware_or_UI_change'] and not native['production_promoted']
        if host=='ARM':assert len(native['actual_ARM_root_refusals'])==16 and native['legacy_opens_refused']==2 and native['null_requests_refused']==3
        runtime=read(ROOT/('results/FMA2_smoothing_runtime_r1/'+host+'.json'))
        assert runtime['actual_unsealed_release_refused_before_CDLL_or_XRT'] and len(runtime['cases'])==2
        for case in runtime['cases']:
            assert case['all23_original_dtype_size_stride_and_output_writeability_refusals']
            assert case['all4_foreign_thread_operations_refused']
            assert case['terminal_native_error_reported_without_PS_fallback']
            assert case['close_returned_while_restore_held_then_closed_in_same_owner']
        for n,h in native['source_and_evidence_SHA256'].items():
            assert sha(ROOT/n)==h,n;bindings[n]=h
        for n,h in runtime['source_and_evidence_sha256'].items():
            assert sha(ROOT/n)==h,n;bindings[n]=h
    names=[Path(__file__).relative_to(ROOT).as_posix(),'dfx/medical/release/manifest.json']
    for host in ['Windows','ARM']:
        names += ['results/shared_FMA2_PR_r1/independent_verified/verified_'+host+'.json',
            'results/shared_FMA2_full_RTL_r1/smooth_rtl/verified_current_full14_'+host+'.json',
            'results/FMA2_smoothing_host_r1/verified_'+host+'.json','results/FMA2_smoothing_runtime_r1/'+host+'.json']
    names += ['tools/verify_shared_FMA2_PR_r1.py','dfx/smooth_speed/shared_fma2_r1/verify_full_RTL_current_r1.py']
    for n in names:bindings[n]=sha(ROOT/n)
    member='workspace/dfx/smooth_speed/route_shared_fma2_r1/build/config_smooth_shared_fma2_r1_pblock_rp_partial.bin'
    RELEASE.mkdir()
    with zipfile.ZipFile(archive) as z,z.open(member) as src,(RELEASE/PARTIAL).open('xb') as dst:
        for block in iter(lambda:src.read(1048576),b''):dst.write(block)
    assert sha(RELEASE/PARTIAL)==route['artifact_sha256'][member]
    (RELEASE/'native_guard.txt').write_text(MARKER,encoding='utf-8',newline='\n')
    value=dict(schema='kv260.FMA2.smoothing.manual_release.v1',identity=0xc2,offline_verified=True,
        production_accepted=False,board_geometry_and_speed_verified=False,route=route,full_RTL=rtl,
        portable_source_and_evidence_SHA256=bindings,partial_bin_sha256=sha(RELEASE/PARTIAL),
        static_base_manifest_SHA256=sha(ROOT/'dfx/medical/release/manifest.json'),
        full_original_three_structures_SciPy5e5_strongest_PS1_PS4_required=True,
        real_board_speedup_unproven=True,PL_accessed=False,whole_goal_completed=False)
    (RELEASE/'manifest.json').write_text(json.dumps(value,indent=2)+'\n')
    assert verify_release()==value
    print('SEALED qualified FMA2 manual release; no firmware staged or PL loaded')


if __name__=='__main__':
    {'prepare':prepare,'verify':verify_release}[sys.argv[1]]()
