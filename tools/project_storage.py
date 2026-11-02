"""Bound the complete source workspace to 25 decimal GB, including results.

Cleanup removes generated files in place; it does not relocate them to another
disk. Current build inputs and a running simulation are explicitly protected.
"""
from pathlib import Path
import argparse, collections, hashlib, json, os, re, stat, sys, time

PROJECT = Path(__file__).resolve().parents[2]
SYSTEM = PROJECT / 'kv260_system'
HARD_LIMIT = 25_000_000_000
SOFT_LIMIT = 23_000_000_000
RECEIPTS = SYSTEM / 'results/storage_cleanup_20261015'
PROTECTED_INPUT = Path(r'C:/Users/34457/AppData/Local/Temp/kv260_cleanup_protected_r2628.json')
BEFORE_INPUT = Path(r'C:/Users/34457/AppData/Local/Temp/kv260_size_inventory_r2628.json')
ACTIVE = 'kv260_system/modules/adaptive_heatmap/rtl_r52/full_R11_memo_local_r2481/'
CURRENT_ARCHIVES = {
    'kv260_system/results/server2_private_jobs_r2609/smooth_rtl/result.zip',
    'kv260_system/results/server2_private_jobs_r2617/smooth_rtl/result.zip',
}
CURRENT_RETENTION = RECEIPTS / 'current_dependencies.json'
SOURCE_EXT = {'.py','.pyi','.cpp','.c','.h','.hpp','.inc','.sv','.svh','.v',
              '.vhd','.vhdl','.tcl','.ps1','.sh','.bat','.cmd','.cmake','.qrc',
              '.qss','.ui','.pro','.prj','.cfg','.ini','.toml','.yaml','.yml',
              '.ipynb','.md','.txt','.json','.xci','.xpr','.xdc','.dts','.dtsi',
              '.dtso','.css','.html','.js','.ts','.frag','.vert','.glsl','.gitignore'}
SMALL_REPORT = {'.json','.rpt','.log','.txt','.md','.csv','.png','.jpg','.html'}
GEN_PART = {'.xil','__pycache__','.pytest_cache','.ipynb_checkpoints',
            '.autopilot','xsim.dir','tv','cdatafile','rtldatafile','cxxrtl',
            'cmakefiles','ip_user_files','csim','syn','sim','impl','component',
            'autopilot','_x','.ipcache'}


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024), b''):h.update(b)
    return h.hexdigest()


def files(root):
    # Never traverse junctions, symbolic links, or other reparse points.
    todo=[root]
    while todo:
        base=todo.pop()
        with os.scandir(base) as entries:
            for e in entries:
                st=e.stat(follow_symlinks=False)
                if st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                if e.is_dir(follow_symlinks=False):todo.append(Path(e.path))
                elif e.is_file(follow_symlinks=False):yield Path(e.path),st


def released_native_closure(system):
    """Retain complete declared dependencies of released native providers.

    A file under build/ can be a required runtime library or its validation
    receipt. Its directory name never makes a declared dependency disposable.
    Fail before planning when a release is already incomplete.
    """
    system=Path(system).resolve();protected={}
    for manifest in sorted((system/'dfx').glob('*/release/manifest.json')):
        module=manifest.parent.parent.resolve()
        metadata=json.loads(manifest.read_text(encoding='utf-8'))
        artifacts=metadata.get('artifact_sha256',{})
        if not any(Path(name).suffix.lower()=='.so' for name in artifacts):continue
        declared={**metadata.get('source_sha256',{}),**artifacts}
        for name,expected in declared.items():
            relative=Path(name)
            path=(module/relative).resolve()
            assert (not relative.is_absolute() and '..' not in relative.parts
                    and path.is_relative_to(module) and not (module/relative).is_symlink()), 'Invalid released dependency: '+name
            assert path.is_file(),'Missing released dependency: '+str(path)
            assert sha(path)==expected,'Changed released dependency: '+str(path)
            protected[path.relative_to(system).as_posix()]=expected
        protected[manifest.relative_to(system).as_posix()]=sha(manifest)
    return protected


def released_UI_closure(system):
    """Retain all declared runtime dependencies of the current manual UI."""
    system=Path(system).resolve();manifest=system/'ui/active_release.json'
    if not manifest.is_file():return {}
    metadata=json.loads(manifest.read_text(encoding='utf-8'))
    if metadata.get('schema') not in ('kv260.manual_feature_UI.v2','kv260.manual_feature_UI.v3','kv260.manual_structure_availability.v1'):return {}
    assert metadata.get('auto_start') is False and metadata.get('files_sha256'), 'Invalid manual UI release'
    protected={}
    for name,expected in metadata['files_sha256'].items():
        relative=Path(name);path=(system/relative).resolve()
        assert (not relative.is_absolute() and '..' not in relative.parts and ':' not in name
                and path.is_relative_to(system) and not (system/relative).is_symlink()), 'Invalid UI dependency: '+name
        assert path.is_file(), 'Missing UI dependency: '+str(path)
        assert sha(path)==expected, 'Changed UI dependency: '+str(path)
        protected[path.relative_to(system).as_posix()]=expected
    protected[manifest.relative_to(system).as_posix()]=sha(manifest)
    # A cached complete-surface view can hide a missing optional source mask
    # until the user reloads its original result. The normal CT adapter reads
    # this report whenever it exists, so its declared mask is a dependency even
    # when the cached-view release did not list it explicitly.
    folders={Path(name).parent for name in list(protected)
             if Path(name).name=='airway_mask.nii.gz'}
    for folder in folders:
        report=system/folder/'airway_detail_report.json'
        if not report.is_file():continue
        assert not report.is_symlink(),'Symbolic airway audit report'
        detail=json.loads(report.read_text(encoding='utf-8'))
        name=detail.get('mask_file');expected=detail.get('mask_sha256')
        assert (isinstance(name,str) and name and Path(name).name==name
                and '/' not in name and '\\' not in name and ':' not in name
                and name not in ('.','..')),'Invalid airway audit mask dependency'
        assert isinstance(expected,str) and re.fullmatch('[0-9a-f]{64}',expected),'Invalid airway audit mask SHA256'
        mask=report.parent/name
        assert mask.resolve().is_relative_to(system) and not mask.is_symlink(),'Escaping airway audit mask dependency'
        assert mask.is_file(),'Missing declared airway audit mask: '+str(mask)
        assert sha(mask)==expected,'Changed declared airway audit mask: '+str(mask)
        protected[report.relative_to(system).as_posix()]=sha(report)
        protected[mask.relative_to(system).as_posix()]=expected
    from ui_reload_dependencies import source_dependencies
    protected.update(source_dependencies(system, protected))
    return protected


def load_protected():
    protected={}
    if PROTECTED_INPUT.is_file():
        protected.update({'kv260_system/'+k:v for k,v in json.loads(PROTECTED_INPUT.read_text()).items()})
    elif (RECEIPTS/'protected.json').is_file():
        protected.update(json.loads((RECEIPTS/'protected.json').read_text()))
    if CURRENT_RETENTION.is_file():
        # New candidates acquire checkpoints and host libraries after the
        # original cleanup snapshot. Keep their exact necessary dependencies.
        for name, value in json.loads(CURRENT_RETENTION.read_text()).items():
            rel = Path(name)
            assert not rel.is_absolute() and '..' not in rel.parts and ':' not in name
            assert (PROJECT/rel).resolve().is_relative_to(PROJECT.resolve())
            assert len(value) == 64
            if name in protected:
                assert protected[name] == value, name
            protected[name] = value
    for name,value in {**released_native_closure(SYSTEM),**released_UI_closure(SYSTEM)}.items():
        key='kv260_system/'+name
        assert key not in protected or protected[key]==value,key
        protected[key]=value
    p=SYSTEM/'release.json'
    mismatches=[]
    for k,v in json.loads(p.read_text())['files'].items():
        if (SYSTEM/k).is_file():
            actual=sha(SYSTEM/k)
            if actual!=v:mismatches.append(dict(path=k,declared=v,before_cleanup=actual))
            protected['kv260_system/'+k]=actual
    if RECEIPTS.exists() and not (RECEIPTS/'release_manifest_preexisting_mismatches.json').exists():
        (RECEIPTS/'release_manifest_preexisting_mismatches.json').write_text(json.dumps(mismatches,indent=2),encoding='utf8')
    return protected


def reason(rel,size,protected):
    s=rel.as_posix();parts=rel.parts;lower=[v.lower() for v in parts];ext=rel.suffix.lower()
    if s in protected or s in CURRENT_ARCHIVES:return None
    if s.startswith(ACTIVE) or s.startswith(('kv260_system/results/server2_private_jobs_r2624/',
                                            'kv260_system/results/server2_private_jobs_r2630/',
                                            'kv260_system/results/BRAM_postroute_repair/')):
        return None
    if s.startswith('kv260_system/results/storage_cleanup_20261015/'):return None
    if s.startswith(('kv260_system/results/board_storage_cleanup_20261015/',
                     'kv260_system/results/full14_BRAM_checkpoint_r2632/')):
        return None  # compact deletion receipts and the current rollback record
    if parts[0]=='.venv_mc':return None
    if parts[0] in {'.h36','.h36b','.h36c','.h37a','.h37b','.h37c','.h37d','.h41r11','.r27b','.r29','.Xil'}:
        return 'retired short-path compiler workspace'
    if '.venv_ct' in lower:return 'reinstallable inactive PC training environment; requirements retained'
    if any(v in lower for v in ['__pycache__','.pytest_cache','.ipynb_checkpoints','.xil']):
        return 'regenerable interpreter or tool cache'
    if s.startswith('kv260_system/tools/') and ext in {'.zip','.gz','.tar','.7z'}:
        return 'obsolete transfer bundle; source and useful verification reports retained'
    if 'fixtures' in lower or 'resources' in lower or 'data' in lower or 'models' in lower:
        # nnU-Net pretrained weights themselves live in a directory called
        # results; that directory is an input asset, not a test result.
        if not s.startswith('kv260_system/results/'):
            return None
    if 'results' in lower or any(v=='runs' or v.endswith('_runs') for v in lower[:-1]):
        if ext in SMALL_REPORT and size<=2_000_000:
            # One compact report is useful; copied compiler reports are not.
            if 'download' not in lower or ext=='.json' or any(t in rel.name.lower() for t in ['timing','utilization','terminal','acceptance','vivado','xsim','failure','stderr','stdout']):
                return None
        return 'historical raw result, redundant source copy, archive or compiler intermediate'
    if s.startswith('kv260_system/ui/exports/'):
        return None if ext in {'.json','.txt','.log'} and size<2_000_000 else 'regenerable UI export test media'
    if s.startswith('kv260_system/ui/cache/'):
        return None if size<1_000_000 and ext in {'.json','.txt','.log'} else 'regenerable UI scene cache'
    if 'release' in lower or any(v.startswith('release_') for v in lower):
        return None
    if s=='kv260_system/ui/releases/feature_completion_r6/build_breathing_fps_candidate_r330/medical_ui':return None
    if s.startswith('kv260_system/dfx/medical/build/') and len(parts)==5:
        return None  # frozen static and original RP references, direct reports
    is_build=any(v in GEN_PART or v.endswith(('.cache','.gen','.runs','.sim')) or
        re.match(r'^(build(?:_|$)|hls_synth_|pre_hls_|vivado(?:_|$))',v) for v in lower[:-1])
    if is_build:
        return 'regenerable compiler workspace; protected current inputs retained'
    if 'package' in lower:return None
    if parts[:2]==('kv260_system','dfx') and ext=='.csv' and size>2_000_000:
        return 'obsolete per-cycle profiling trace; acceptance summaries retained'
    if s.startswith('kv260_system/dfx/composite/docs/') and ext not in SOURCE_EXT and size>2_000_000:
        return 'historical UI demonstration capture; source and reports retained'
    if s.startswith('kv260_system/dfx/live_effects/') and ext=='.bin' and size>2_000_000:
        return 'redundant historical C9 board or simulator input/output dump'
    if ext in {'.dat','.wdb','.wcfg','.bc','.adb','.o','.obj','.pdb','.sdb','.dbg','.normalized','.jou','.pb','.rdb','.str'}:
        return 'generated simulation data or compiler database'
    if ext in {'.hex','.mem','.f32','.u32','.u64','.f64','.i32'}:
        return 'generated simulation vector; protected current fixtures retained'
    if ext in {'.zip','.tar','.gz','.7z'} and 'outputs' not in lower:
        return 'obsolete local intermediate archive'
    if ext in {'.dcp','.bit'}:
        return 'retired checkpoint or bitstream; released firmware and current inputs retained'
    if 'outputs' in lower:
        return None if ext in SMALL_REPORT and size<2_000_000 else 'regenerable historical inference output'
    if ext in SOURCE_EXT:return None
    return None


def plan():
    RECEIPTS.mkdir(parents=True,exist_ok=True)
    protected=load_protected()
    with (RECEIPTS/'protected.json').open('w',encoding='utf8') as f:json.dump(protected,f,indent=2)
    if BEFORE_INPUT.is_file() and not (RECEIPTS/'before.json').exists():
        (RECEIPTS/'before.json').write_bytes(BEFORE_INPUT.read_bytes())
    counts=collections.Counter();reasons=collections.Counter();kept=collections.Counter();total=0;n=0
    dest=RECEIPTS/'plan.jsonl';temp=dest.with_suffix('.pending')
    with temp.open('w',encoding='utf8') as f:
        for p,st in files(PROJECT):
            rel=p.relative_to(PROJECT);s=rel.as_posix();size=st.st_size;total+=size;n+=1
            why=reason(rel,size,protected)
            if why:
                f.write(json.dumps([s,size,st.st_mtime_ns,why],ensure_ascii=False,separators=(',',':'))+'\n')
                counts[why]+=1;reasons[why]+=size
            else:kept['/'.join(rel.parts[:3])]+=size
    os.replace(temp,dest)
    summary=dict(hard_limit_bytes=HARD_LIMIT,workspace=str(PROJECT),before_bytes=total,before_files=n,
        proposed_delete_bytes=sum(reasons.values()),projected_retained_bytes=total-sum(reasons.values()),
        reasons=dict(reasons),files_per_reason=dict(counts),largest_retained=kept.most_common(60),
        plan_sha256=sha(dest),protected_files=len(protected),moves_or_hidden_external_archives=False)
    (RECEIPTS/'plan_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(summary,indent=2))


def apply(expected):
    planpath=RECEIPTS/'plan.jsonl';assert sha(planpath)==expected
    protected=load_protected();deleted=0;count=0;start=time.monotonic()
    existing_log=RECEIPTS/'deleted.jsonl';already_deleted=set()
    if existing_log.exists():
        with existing_log.open(encoding='utf8') as f:
            for line in f:
                row=json.loads(line);deleted+=row[1];count+=1;already_deleted.add(row[0])
    with planpath.open(encoding='utf8') as source,(RECEIPTS/'deleted.jsonl').open('a',encoding='utf8') as log:
        for line in source:
            name,size,mtime,why=json.loads(line)
            if name in already_deleted:continue
            p=PROJECT/name
            # Additional exact current dependencies discovered by read-only
            # qualification checks may extend preservation after planning.
            if name in protected:continue
            assert not name.startswith(ACTIVE)
            assert reason(Path(name),size,protected)==why
            if not p.exists():continue
            resolved=p.resolve();assert resolved.is_relative_to(PROJECT.resolve()) and resolved!=PROJECT.resolve()
            st=p.lstat();assert not st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
            if st.st_size!=size or st.st_mtime_ns!=mtime:
                with (RECEIPTS/'changed_since_plan_preserved.jsonl').open('a',encoding='utf8') as changed:
                    changed.write(json.dumps(dict(path=name,current_bytes=st.st_size,planned_bytes=size,preserved=True))+'\n')
                continue
            try:p.unlink()
            except PermissionError:
                os.chmod(p,stat.S_IWRITE|stat.S_IREAD);p.unlink()
            log.write(json.dumps([name,size,why],ensure_ascii=False,separators=(',',':'))+'\n')
            deleted+=size;count+=1
            if count%10000==0:
                log.flush();print(json.dumps(dict(deleted_files=count,deleted_GB=round(deleted/1e9,3),elapsed_s=round(time.monotonic()-start))),flush=True)
    # Empty folders only; every path is checked again, never a recursive delete.
    for dp,ds,fs in os.walk(PROJECT,topdown=False,followlinks=False):
        p=Path(dp)
        if p==PROJECT or p.is_symlink():continue
        assert p.resolve().is_relative_to(PROJECT.resolve())
        try:p.rmdir()
        except OSError:pass
    summary=dict(deleted_bytes=deleted,deleted_files=count,elapsed_s=time.monotonic()-start,
                 applied_plan_sha256=expected,no_files_moved_elsewhere=True)
    (RECEIPTS/'applied.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(summary,indent=2))


def check(reserve):
    assert reserve>=0,'Additional peak storage reservation must be nonnegative'
    bytop=collections.Counter();total=0;n=0
    for p,st in files(PROJECT):
        total+=st.st_size;n+=1;bytop[p.relative_to(PROJECT).parts[0]]+=st.st_size
    result=dict(workspace=str(PROJECT),bytes=total,decimal_GB=total/1e9,GiB=total/2**30,
        files=n,hard_limit_bytes=HARD_LIMIT,reserve_bytes=reserve,
        within_limit=total+reserve<HARD_LIMIT,remaining_bytes=HARD_LIMIT-total,
        by_top_directory=dict(bytop))
    print(json.dumps(result,indent=2))
    if RECEIPTS.exists():(RECEIPTS/'latest_size.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    if not result['within_limit']:sys.exit(2)


def verify():
    # Completed duplicate extractions may be retained once in a sealed archive.
    # The reader hashes that complete archive and every required member; changed
    # physical files are always refused instead of falling back to old contents.
    from verify_storage_retention import verify as verify_retention
    result=verify_retention()
    (RECEIPTS/'protected_verified.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2));assert result['all_original_SHA256_unchanged']


if __name__=='__main__':
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='command',required=True)
    sub.add_parser('plan');a=sub.add_parser('apply');a.add_argument('--plan-sha256',required=True)
    a=sub.add_parser('check');a.add_argument('--reserve-bytes',type=int,default=0)
    sub.add_parser('verify');args=ap.parse_args()
    if args.command=='plan':plan()
    elif args.command=='apply':apply(args.plan_sha256)
    elif args.command=='check':check(args.reserve_bytes)
    else:verify()
