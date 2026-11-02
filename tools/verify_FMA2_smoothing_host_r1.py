"""Verify the FMA2 ARM host without permitting a valid hardware context."""
from pathlib import Path
import ctypes as C
import json
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from verify_BRAM_smoothing_host_r2634 import sha,exports
HERE=ROOT/'dfx/smooth_speed/host_FMA2_r1'
OUT=ROOT/'results/FMA2_smoothing_host_r1'


def inspect():
    origin=json.loads((HERE/'derivation.json').read_text());build=json.loads((HERE/'build_ARM/compile_receipt.json').read_text())
    assert build['exit_code']==0 and not build['library_loaded'] and not build['XRT_session_created'] and not build['PL_accessed']
    binding={**origin['source_sha256'],**build['source_sha256'],**build['artifact_sha256']}
    for n,h in binding.items():assert sha(ROOT/n)==h,n
    for row in origin['derivations']:
        source=(ROOT/row['parent']).read_text()
        for edit in row['literal_edits']:
            assert source.count(edit['before'])==edit['occurrences'];source=source.replace(edit['before'],edit['after'])
        assert source==(ROOT/row['candidate']).read_text()
    old=(ROOT/'dfx/smooth_speed/host_BRAM_r2634/bridge.cpp').read_text();new=(HERE/'bridge.cpp').read_text()
    anchor='extern "C" int speed_run'
    assert old[old.index(anchor):]==new[new.index(anchor):]
    header=(HERE/'runtime.hpp').read_text()
    assert header.index('const std::filesystem::path medical_root;')<header.index('FileLock pl_lock;')
    assert 'Session(const char* project_root=nullptr):medical_root(medical_directory(project_root))' in header
    assert 'release_FMA2_r1' in header and 'KV260_FMA2_100MHZ_FULLPR_PAIRED_MANUAL_RELEASE\\n' in header
    assert 'Canonical absolute FMA2 root required before hardware access' in header
    assert 'std::filesystem::current_path(' not in header and 'chdir(' not in header
    expected=sorted(['speed_error','speed_open','speed_open_profile','speed_open_root','speed_profile_snapshot','speed_close','speed_restore','speed_run'])
    assert exports(HERE/'build_ARM/libsmooth_FMA2_r1.so')==expected
    assert all(s in build['compile_command'] for s in ['-mcpu=cortex-a53','-ffp-contract=off','-pthread','-shared'])
    assert not any(s.startswith('-ffast-math') for s in build['compile_command'])
    for p in [Path(__file__),ROOT/'tools/verify_BRAM_smoothing_host_r2634.py',HERE/'derivation.json',HERE/'build_ARM/compile_receipt.json']:
        binding[p.relative_to(ROOT).as_posix()]=sha(p)
    return dict(status='FMA2_actual_ARM_same_ABI_host_complete_run_and22_DMA_guards_verified',
        source_and_evidence_SHA256=binding,exported_C_API=expected,
        original_full_speed_run_and22_DMA_guards_and17_control_fields_unchanged=True,
        explicit_qualified_canonical_root_gate_before_FileLock_MMIO_XRT=True,
        original_three_structure_full_trial_and_strongest_PS4_required=True,
        no_actual_PL_context_or_firmware_or_UI_change=True,production_promoted=False,whole_goal_completed=False)


def main():
    host='Windows' if os.name=='nt' else 'ARM';value=inspect();target=OUT/('verified_'+host+'.json');assert not target.exists()
    assert not (ROOT/'dfx/smooth_speed/release_FMA2_r1').exists()
    if host=='ARM':
        from modules.mask_evaluation.ui.actual_pl_r3.check_ARM import review_identity
        before=(ROOT/'tools/storage_runtime_identity.json').read_bytes();review_identity(json.loads(before));cwd=Path.cwd()
        lib=C.CDLL(str(HERE/'build_ARM/libsmooth_FMA2_r1.so'));lib.speed_error.restype=C.c_char_p
        lib.speed_open_root.argtypes=[C.c_char_p,C.c_bool];lib.speed_open_root.restype=C.c_void_p
        refusals=[]
        for root in [None,b'',b'not-an-absolute-project',b'/nonexistent-kv260-contract-r2147-root',b'/tmp',
                     os.fsencode(ROOT),os.fsencode(ROOT/'fixtures'),os.fsencode(ROOT/'modules')]:
            for profile in [False,True]:
                assert not lib.speed_open_root(root,profile)
                error=lib.speed_error().decode();assert 'before hardware access' in error or error=='Explicit medical project root required',error
                refusals.append(dict(root=None if root is None else os.fsdecode(root),profile=profile,error=error))
        for name in ['speed_open','speed_open_profile']:
            call=getattr(lib,name);call.argtypes=[];call.restype=C.c_void_p
            assert not call() and b'before hardware access' in lib.speed_error()
        lib.speed_restore.argtypes=[C.c_void_p];lib.speed_restore.restype=C.c_int
        assert lib.speed_restore(None)==-1 and lib.speed_error()==b'Null smoothing context'
        lib.speed_profile_snapshot.argtypes=[C.c_void_p,C.c_void_p];lib.speed_profile_snapshot.restype=C.c_int
        assert lib.speed_profile_snapshot(None,None)==-1 and lib.speed_error()==b'Null profile snapshot argument'
        lib.speed_run.argtypes=[C.c_void_p]*8+[C.c_uint]*3+[C.c_float,C.c_uint,C.c_void_p];lib.speed_run.restype=C.c_int
        assert lib.speed_run(*([None]*8),0,0,0,1.,1,None)==-1 and lib.speed_error()==b'Null smoothing argument'
        lib.speed_close.argtypes=[C.c_void_p];lib.speed_close.restype=None;lib.speed_close(None)
        assert before==(ROOT/'tools/storage_runtime_identity.json').read_bytes() and cwd==Path.cwd();review_identity(json.loads(before))
        value.update(actual_ARM_root_refusals=refusals,legacy_opens_refused=2,null_requests_refused=3,
            null_close_safe=True,current_UI_identity_unchanged=True)
    else:
        actual=json.loads((OUT/'verified_ARM.json').read_text());common={k:v for k,v in actual.items() if k not in
            ['host','actual_ARM_root_refusals','legacy_opens_refused','null_requests_refused','null_close_safe','current_UI_identity_unchanged']}
        assert common==value and len(actual['actual_ARM_root_refusals'])==16
        value.update(actual_ARM_refusal_receipt_SHA256=sha(OUT/'verified_ARM.json'),actual_ARM_refusals_replayed=True)
    value['host']=host;OUT.mkdir(exist_ok=True);target.write_text(json.dumps(value,indent=2)+'\n')
    print('PASS',host,'same ABI, complete original run and22 DMA guards, actual ARM16 roots+2 legacy opens+3 null refusals; no valid context')


if __name__=='__main__':
    sys.path.insert(0,str(ROOT));main()
