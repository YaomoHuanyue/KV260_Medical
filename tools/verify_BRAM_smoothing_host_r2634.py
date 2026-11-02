"""Portable ELF/source verification and actual ARM malformed-root refusals.

Never call either legacy open function or supply a valid root to the new one.
Malformed roots fail before FileLock, MMIO and XRT construction. This proves
host preparation only, not new hardware operation or speed.
"""
from pathlib import Path
import ctypes as C
import hashlib
import json
import os
import struct

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'dfx/smooth_speed/host_BRAM_r2634'
OLD=ROOT/'dfx/smooth_speed/host_profile_r361'
HOST='Windows' if os.name=='nt' else 'ARM'
OUT=ROOT/'results/BRAM_smoothing_host_r2634'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):
            h.update(b)
    return h.hexdigest()


def exports(path):
    # Small host library only; medical image and DCP archives remain streamed.
    elf=path.read_bytes()
    assert elf[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',elf,18)[0]==183
    offset=struct.unpack_from('<Q',elf,40)[0]
    stride,count=struct.unpack_from('<HH',elf,58)
    assert stride==64 and count>0
    sections=[struct.unpack_from('<IIQQQQIIQQ',elf,offset+j*stride) for j in range(count)]
    exported=set()
    for section in sections:
        if section[1]!=11:
            continue
        strings=sections[section[6]]
        table=elf[strings[4]:strings[4]+strings[5]]
        assert section[9]==24
        for pos in range(section[4],section[4]+section[5],section[9]):
            name,info,other,defined,value,size=struct.unpack_from('<IBBHQQ',elf,pos)
            text=table[name:table.find(b'\0',name)].decode()
            if defined and info>>4 in (1,2) and text.startswith('speed_'):
                exported.add(text)
    return sorted(exported)


def inspect():
    origin=json.loads((HERE/'derivation.json').read_text())
    build=json.loads((HERE/'build_ARM/compile_receipt.json').read_text())
    assert build['status']=='actual_ARM_compact_smoothing_XRT_host_compiled_no_Session' and build['exit_code']==0
    assert all(not build[k] for k in ('library_loaded','XRT_session_created','default_UI_or_firmware_changed','PL_accessed','production_promoted'))
    binding={**origin['source_sha256'],**build['source_sha256'],**build['artifact_sha256']}
    for n,h in binding.items():
        p=(ROOT/n).resolve()
        assert p.is_relative_to(ROOT) and sha(p)==h,n
    for row in origin['derivations']:
        text=(ROOT/row['parent']).read_text()
        for e in row['literal_edits']:
            assert text.count(e['before'])==e['occurrences']
            text=text.replace(e['before'],e['after'])
        assert text==(ROOT/row['candidate']).read_text()
    before=(OLD/'bridge.cpp').read_text()
    after=(HERE/'bridge.cpp').read_text()
    assert before[before.index('extern "C" int speed_run'):]==after[after.index('extern "C" int speed_run'):]
    for start, end in [('extern "C" int speed_restore','extern "C" int speed_run'),('extern "C" int speed_profile_snapshot','extern "C" void speed_close')]:
        assert before[before.index(start):before.index(end)]==after[after.index(start):after.index(end)]
    runtime=(HERE/'runtime.hpp').read_text()
    assert 'const std::filesystem::path medical_root;' in runtime
    assert runtime.index('const std::filesystem::path medical_root;')<runtime.index('FileLock pl_lock;')
    assert 'Session(const char* project_root=nullptr):medical_root(medical_directory(project_root))' in runtime
    assert 'require(path.is_absolute()&&std::filesystem::is_directory(path)' in runtime
    assert 'release_profile_r361' not in runtime and 'smooth_speed_profile_r361' not in runtime
    # current_path() is a read-only compatibility path for the retained legacy
    # entry points. There is no filesystem current_path(new_path) or chdir.
    assert runtime.count('std::filesystem::current_path()')==runtime.count('current_path(')==1 and 'chdir(' not in runtime
    assert 'speed_open(){try{return new Context();}' in after
    assert 'speed_open_profile(){try{return new Context(true);}' in after
    assert 'require(project_root&&*project_root,"Explicit medical project root required")' in after
    assert 'Context(measure,project_root)' in after
    assert 'Context(bool measure=false,const char* project_root=nullptr):session(project_root)' in after
    command=build['compile_command']
    assert all(v in command for v in ('-mcpu=cortex-a53','-ffp-contract=off','-pthread','-shared'))
    assert not any(v.startswith('-ffast-math') for v in command)
    expected=sorted(['speed_error','speed_open','speed_open_profile','speed_open_root','speed_profile_snapshot','speed_close','speed_restore','speed_run'])
    library=HERE/'build_ARM/libsmooth_BRAM_r2634.so'
    assert exports(library)==expected
    paths=[Path(__file__),HERE/'derivation.json',HERE/'build_ARM/compile_receipt.json']
    binding.update({p.relative_to(ROOT).as_posix():sha(p) for p in paths})
    return dict(status='actual_ARM_compact_C2_XRT_host_original_run_DMA_contract_and_absolute_root_verified',
                exported_C_API=expected,ELF64_AArch64_verified=True,
                source_and_evidence_sha256=binding,
                all22_DMA_guards_full_original_speed_run_restore_and_diagnostics_body_unchanged=True,
                legacy7_C_API_symbols_and_old_compatibility_path_retained=True,
                explicit_root_API_added_without_any_process_cwd_change=True,
                original17_register_fields_and_active_DMA_retention_unchanged=True,
                full_original100MHz_PR_and_same_input_strongestPS4_PL_speed_still_pending=True,
                XRT_session_created=False,PL_accessed=False,production_promoted=False,whole_goal_completed=False)


def main():
    result=inspect()
    target=OUT/f'verified_{HOST}.json'
    assert not target.exists()
    if HOST=='ARM':
        library=C.CDLL(str(HERE/'build_ARM/libsmooth_BRAM_r2634.so'))
        function=library.speed_open_root
        function.argtypes=[C.c_char_p,C.c_bool]
        function.restype=C.c_void_p
        library.speed_error.restype=C.c_char_p
        cwd=Path.cwd()
        assert not Path('/nonexistent-kv260-contract-r2147-root/dfx/medical').exists()
        refusals=[]
        for root,label in [(None,'null'),(b'','empty'),(b'not-an-absolute-project','relative'),(b'/nonexistent-kv260-contract-r2147-root','missing')]:
            for measure in (False,True):
                assert not function(root,measure)
                error=library.speed_error().decode()
                assert error==('Explicit medical project root required' if root in (None,b'') else 'Absolute medical project root required')
                assert Path.cwd()==cwd
                refusals.append(dict(root_kind=label,profile=measure,error=error))
        result.update(actual_ARM_library_loaded_without_valid_Session=True,all8_actual_malformed_roots_rejected_before_FileLock_MMIO_XRT=refusals,actual_cwd_unchanged=True)
    else:
        arm=json.loads((OUT/'verified_ARM.json').read_text())
        common=dict(arm)
        for key in ('host','actual_ARM_library_loaded_without_valid_Session','all8_actual_malformed_roots_rejected_before_FileLock_MMIO_XRT','actual_cwd_unchanged'):
            common.pop(key)
        assert common==result and len(arm['all8_actual_malformed_roots_rejected_before_FileLock_MMIO_XRT'])==8 and arm['actual_cwd_unchanged']
        result.update(actual_ARM_malformed_root_evidence_replayed=True,actual_ARM_refusals_sha256=sha(OUT/'verified_ARM.json'))
    result['host']=HOST
    OUT.mkdir(exist_ok=True)
    with target.open('x',encoding='utf8') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],HOST,flush=True)


if __name__=='__main__':
    main()
