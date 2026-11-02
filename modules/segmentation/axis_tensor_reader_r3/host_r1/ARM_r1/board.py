"""Exclusive, bounded, asynchronous ARM compile task with full owned-file collection."""
from pathlib import Path
import argparse,hashlib,json,shlex,stat,sys,uuid
import paramiko
HERE=Path(__file__).resolve().parent;HOST=HERE.parent;ROOT=HOST.parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import project_storage
from test_R15_wrapper_ARM_20261020 import board,REMOTE

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)
def read(p):return json.loads(p.read_text('utf-8'))
def execute(t,code):
    out,_=board.execute(t,'/usr/bin/python3 -B -c '+shlex.quote(code));return json.loads(out)
def launch():
    project_storage.check(5_000_000);assert not (HERE/'dispatch.json').exists()
    pc=read(HOST/'native_Windows_r3/verified.json')
    paths=[ROOT/n for n in pc['source_and_evidence_SHA256'] if (ROOT/n).suffix in ('.cpp','.hpp','.h')]
    paths+=[ROOT/n for n in ('modules/runtime_audit/C5_pool_host_r1/shared_session.hpp','modules/runtime_audit/session_log_r1/runtime.hpp','modules/runtime_audit/session_log_r1/switch_log.hpp')]
    bindings={p.relative_to(ROOT).as_posix():sha(p) for p in paths};assert sum(p.stat().st_size for p in paths)<500_000
    planned=dict(sources=bindings,PC_rows=[pc['legacy'],pc['reader']],PC_proof_SHA256=sha(HOST/'native_Windows_r3/verified.json'))
    if (HERE/'owner.json').exists():
        # The previous attempt failed creating the root before uploading or
        # spawning anything. Continue that same exclusive task; never restart.
        assert read(HERE/'inputs.json')==planned;owner=read(HERE/'owner.json');remote=owner['exact_board_root']
    else:
        save(HERE/'inputs.json',planned);remote=REMOTE+'/results/owned_R3host_'+uuid.uuid4().hex
        owner=dict(exact_board_root=remote,nonce=uuid.uuid4().hex);save(HERE/'owner.json',owner)
    uploads={'worker.py':HERE/'worker.py','owner.json':HERE/'owner.json','inputs.json':HERE/'inputs.json'}
    uploads.update({'source/'+n:ROOT/n for n in bindings})
    upload_plan={n:dict(SHA256=sha(p),local=p.relative_to(ROOT).as_posix()) for n,p in uploads.items()}
    if (HERE/'uploads.json').exists():assert read(HERE/'uploads.json')==upload_plan
    else:save(HERE/'uploads.json',upload_plan)
    t=board.connect()
    try:
        before=board.identity(t)
        if (HERE/'formal_before.json').exists():assert read(HERE/'formal_before.json')==before
        else:save(HERE/'formal_before.json',before)
        assert remote.startswith(REMOTE+'/results/owned_R3host_') and len(remote.rsplit('_',1)[1])==32
        create="from pathlib import Path;import os,pwd;p=Path("+repr(remote)+");assert p.parent==Path("+repr(REMOTE+'/results')+");assert p.parent.is_dir() and not p.exists() and not p.is_symlink();p.mkdir();u=pwd.getpwnam('ubuntu');os.chown(p,u.pw_uid,u.pw_gid)"
        board.execute(t,'/usr/bin/python3 -B -c '+shlex.quote(create),sudo=True)
        with paramiko.SFTPClient.from_transport(t) as s:
            for n,p in uploads.items():
                parent=remote
                for part in Path(n).parts[:-1]:
                    parent+='/'+part
                    try:s.stat(parent)
                    except FileNotFoundError:s.mkdir(parent)
                with s.open(remote+'/'+n,'wx') as f:f.write(p.read_bytes())
                with s.open(remote+'/'+n,'rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==sha(p),n
        code='''from pathlib import Path
import subprocess,json,time
r=Path(REMOTE)
with (r/'stdout.log').open('xb') as out,(r/'stderr.log').open('xb') as err:
 p=subprocess.Popen(['nice','-n','10','/usr/bin/python3','-B',str(r/'worker.py')],stdout=out,stderr=err,start_new_session=True)
 proc=Path('/proc')/str(p.pid)
 print(json.dumps(dict(PID=p.pid,ticks=int((proc/'stat').read_text().rsplit(')',1)[1].split()[19]),boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip())))
'''.replace('Path(REMOTE)', 'Path('+repr(remote)+')')
        actual=execute(t,code);save(HERE/'dispatch.json',actual);print(json.dumps(actual),flush=True)
    finally:t.close()

def snapshot():
    owner=read(HERE/'owner.json');actual=read(HERE/'dispatch.json');t=board.connect()
    try:
        code='''from pathlib import Path
import json
r=Path(REMOTE);a=ACTUAL;p=Path('/proc')/str(a['PID'])
same=p.exists() and int((p/'stat').read_text().rsplit(')',1)[1].split()[19])==a['ticks'] and Path('/proc/sys/kernel/random/boot_id').read_text().strip()==a['boot']
terminal=json.loads((r/'terminal.json').read_text()) if (r/'terminal.json').is_file() else None
print(json.dumps(dict(actual_original_worker_live=same,terminal=terminal)))
'''.replace('Path(REMOTE)','Path('+repr(owner['exact_board_root'])+')').replace('a=ACTUAL','a='+repr(actual))
        v=execute(t,code);print(json.dumps(dict(actual_original_worker_live=v['actual_original_worker_live'],terminal=None if v['terminal'] is None else dict(passed=v['terminal']['passed'],all_children_reaped=v['terminal']['all_children_reaped']))),flush=True)
    finally:t.close()

def collect():
    project_storage.check(5_000_000);assert not (HERE/'paired_verified.json').exists()
    owner=read(HERE/'owner.json');uploads=read(HERE/'uploads.json');remote=owner['exact_board_root'];t=board.connect()
    try:
        assert remote.startswith(REMOTE+'/results/owned_R3host_') and len(remote.rsplit('_',1)[1])==32
        inventory={};directories=[]
        with paramiko.SFTPClient.from_transport(t) as s:
            with s.open(remote+'/terminal.json','rb') as f:terminal=json.load(f)
            assert terminal['all_children_reaped']
            with s.open(remote+'/owner.json','rb') as f:assert json.load(f)==owner
            def walk(base):
                for item in s.listdir_attr(base):
                    assert item.filename not in ('.','..') and '/' not in item.filename and '\\' not in item.filename
                    p=base+'/'+item.filename;assert p.startswith(remote+'/') and not stat.S_ISLNK(item.st_mode)
                    if stat.S_ISDIR(item.st_mode):directories.append(p);walk(p)
                    else:
                        assert stat.S_ISREG(item.st_mode) and item.st_size<2_000_000
                        with s.open(p,'rb') as f:raw=f.read(2_000_001)
                        assert len(raw)==item.st_size;digest=hashlib.sha256(raw).hexdigest();n=p.removeprefix(remote+'/')
                        with s.open(p,'rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==digest
                        if n in uploads:assert digest==uploads[n]['SHA256']==sha(ROOT/uploads[n]['local'])
                        else:
                            dest=HERE/'collected'/n;dest.parent.mkdir(parents=True,exist_ok=True)
                            with dest.open('xb') as f:f.write(raw)
                        inventory[n]=dict(bytes=len(raw),SHA256=digest)
            walk(remote);assert set(uploads)<=set(inventory)
            for n,h in terminal['output_SHA256'].items():assert inventory[n]['SHA256']==h
            save(HERE/'all_owned_bytes_verified.json',dict(owner=owner,inventory=inventory,all_uploaded_generated_bytes_verified=True))
            # Only this terminal task's exact root is removed after collection.
            with s.open(remote+'/owner.json','rb') as f:assert json.load(f)==owner
            for n in sorted(inventory):s.remove(remote+'/'+n)
            for p in sorted(directories,key=len,reverse=True):s.rmdir(p)
            s.rmdir(remote)
            try:s.stat(remote)
            except FileNotFoundError:pass
            else:raise AssertionError('Owned root still exists')
        after=board.identity(t);assert after==read(HERE/'formal_before.json')
    finally:t.close()
    publish(terminal,after,remote)

def publish(terminal,after,remote):
    assert terminal['passed'],read(HERE/'collected/output/failure.json')
    accepted=read(HERE/'collected/output/verified.json')
    assert accepted['PC_ARM_exact_rows']==read(HERE/'inputs.json')['PC_rows']
    paths=[Path(__file__),HERE/'worker.py',HERE/'inputs.json',HERE/'owner.json',HERE/'dispatch.json',HERE/'formal_before.json',HERE/'uploads.json',HERE/'all_owned_bytes_verified.json',HOST/'native_Windows_r3/verified.json',*HERE.joinpath('collected').rglob('*')]
    save(HERE/'paired_verified.json',dict(status='PC_ARM_reader_native_contract_and_real_XRT_compile_verified',verified=accepted,
        all_owned_ARM_files_collected_and_SHA_verified_then_exact_root_removed=True,exact_removed_root=remote,
        formal_GUI_identity_unchanged=after,source_and_evidence_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in paths if p.is_file()},
        PL_accessed=False,production_promoted=False,whole_goal_completed=False))
    print(json.dumps(dict(paired=True,reader_cases=128,reader_refusals=31,actual_C_API_exports=len(accepted['C_API_exports']),owned_root_cleaned=True)),flush=True)

def finish_collection():
    # All bytes were verified/collected and children removed. The containing
    # results directory is root-owned, so only the final empty rmdir needs sudo.
    assert not (HERE/'paired_verified.json').exists()
    receipt=read(HERE/'all_owned_bytes_verified.json');owner=read(HERE/'owner.json');assert receipt['owner']==owner
    uploads=read(HERE/'uploads.json');remote=owner['exact_board_root']
    assert remote.startswith(REMOTE+'/results/owned_R3host_') and len(remote.rsplit('_',1)[1])==32
    for n,v in receipt['inventory'].items():
        local=ROOT/uploads[n]['local'] if n in uploads else HERE/'collected'/n
        assert sha(local)==v['SHA256'] and local.stat().st_size==v['bytes'],n
    terminal=read(HERE/'collected/terminal.json');assert terminal['all_children_reaped']
    t=board.connect()
    try:
        code="from pathlib import Path;p=Path("+repr(remote)+");assert p.parent==Path("+repr(REMOTE+'/results')+");assert p.is_dir() and not p.is_symlink() and not any(p.iterdir());p.rmdir()"
        board.execute(t,'/usr/bin/python3 -B -c '+shlex.quote(code),sudo=True)
        with paramiko.SFTPClient.from_transport(t) as s:
            try:s.lstat(remote)
            except FileNotFoundError:pass
            else:raise AssertionError('Owned root still exists')
        after=board.identity(t);assert after==read(HERE/'formal_before.json')
    finally:t.close()
    publish(terminal,after,remote)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('launch','snapshot','collect','finish_collection'));a=p.parse_args();globals()[a.action]()
