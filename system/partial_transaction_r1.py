"""Durable compare-and-swap of a qualified partial's two firmware files.

The caller owns the task and idle-PL locks. This module never opens a device,
loads a bitstream, stops another owner, or changes an unrecognized file.
"""
from pathlib import Path
import hashlib,json,os,re,shutil,uuid


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def owner():
    fields=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split() if os.name!='nt' else None
    if fields:
        return dict(PID=os.getpid(),start_ticks=int(fields[19]),boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    # Windows filesystem tests use the OS process handle, not a fabricated PID.
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    handle=kernel.OpenProcess(0x1000,False,os.getpid());assert handle
    times=[wintypes.FILETIME() for _ in range(4)]
    try:assert kernel.GetProcessTimes(handle,*[ctypes.byref(v) for v in times])
    finally:kernel.CloseHandle(handle)
    return dict(PID=os.getpid(),start_ticks=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime,boot='Windows_process_creation_FILETIME')


def live(row):
    if os.name!='nt':
        if row['boot']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():return False
        p=Path('/proc',str(row['PID']))
        try:fields=(p/'stat').read_text().rsplit(')',1)[1].split()
        except FileNotFoundError:return False
        return int(fields[19])==row['start_ticks'] and fields[0]!='Z'
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    handle=kernel.OpenProcess(0x101000,False,row['PID'])
    if not handle:return False
    times=[wintypes.FILETIME() for _ in range(4)]
    try:
        state=kernel.WaitForSingleObject(handle,0)
        if state==0:return False
        if state!=258:raise OSError(ctypes.get_last_error())
        if not kernel.GetProcessTimes(handle,*[ctypes.byref(v) for v in times]):raise OSError(ctypes.get_last_error())
        return ((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)==row['start_ticks']
    finally:kernel.CloseHandle(handle)


class Transaction:
    SCHEMA='kv260.qualified_partial_file_transaction.v1'

    def __init__(self,ledger,targets,original,candidate,old_sha,new_sha):
        self.ledger=Path(ledger).absolute();self.targets=tuple(Path(p).absolute() for p in targets)
        self.original=Path(original).absolute();self.candidate=Path(candidate).absolute()
        self.old_sha=old_sha;self.new_sha=new_sha
        if len(self.targets)!=2 or len(set(self.targets))!=2 or self.original in self.targets or self.candidate in self.targets:
            raise ValueError('Two distinct firmware targets and separate immutable assets required')
        if old_sha==new_sha or not all(re.fullmatch('[0-9a-f]{64}',h) for h in (old_sha,new_sha)):
            raise ValueError('Distinct exact qualified asset hashes required')

    def validate_assets(self,*,original_only=False):
        assets=((self.original,self.old_sha),) if original_only else ((self.original,self.old_sha),(self.candidate,self.new_sha))
        for p,h in assets:
            if p.is_symlink() or not p.is_file() or sha(p)!=h:raise ValueError('Changed immutable partial asset: '+str(p))

    def read(self):
        if self.ledger.is_symlink():raise ValueError('Invalid transaction ledger')
        data=json.loads(self.ledger.read_text())
        expected=dict(schema=self.SCHEMA,targets=[str(p) for p in self.targets],original=str(self.original),
            candidate=str(self.candidate),old_sha=self.old_sha,new_sha=self.new_sha)
        if set(data)!=set(expected)|{'owner','nonce'} or any(data[k]!=v for k,v in expected.items()):
            raise ValueError('Transaction belongs to another configuration')
        if not re.fullmatch('[0-9a-f]{32}',data['nonce']) or set(data['owner'])!={'PID','start_ticks','boot'}:
            raise ValueError('Malformed transaction owner')
        return data

    def _write(self,data):
        if self.ledger.exists():raise FileExistsError('A pending partial transaction already exists')
        temporary=self.ledger.with_name(self.ledger.name+'.'+data['nonce']+'.tmp')
        with temporary.open('x',encoding='utf-8') as f:
            json.dump(data,f,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(temporary,self.ledger)
        self._sync_parent(self.ledger)

    @staticmethod
    def _sync_parent(path):
        if os.name=='nt':return
        fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)

    def _copy(self,source,target,expected,nonce):
        if target.is_symlink() or not target.is_file() or sha(target)!=expected:
            raise ValueError('Firmware changed outside this transaction: '+str(target))
        temporary=target.with_name(target.name+'.owned_DFX_'+nonce)
        st=target.stat()
        with Path(source).open('rb') as src,temporary.open('xb') as dst:
            shutil.copyfileobj(src,dst,1048576);dst.flush();os.fsync(dst.fileno())
        if hasattr(os,'chown'):os.chown(temporary,st.st_uid,st.st_gid)
        os.chmod(temporary,st.st_mode&0o7777)
        if sha(temporary)!=sha(source) or sha(target)!=expected:raise ValueError('Atomic partial copy changed')
        os.replace(temporary,target);self._sync_parent(target)

    def begin(self):
        self.validate_assets()
        if self.ledger.exists():raise FileExistsError('Recover or wait for the pending transaction first')
        if any(p.is_symlink() or not p.is_file() or sha(p)!=self.old_sha for p in self.targets):
            raise ValueError('Formal firmware does not match the accepted original')
        data=dict(schema=self.SCHEMA,targets=[str(p) for p in self.targets],original=str(self.original),
            candidate=str(self.candidate),old_sha=self.old_sha,new_sha=self.new_sha,owner=owner(),nonce=uuid.uuid4().hex)
        self._write(data)
        for p in self.targets:self._copy(self.candidate,p,self.old_sha,data['nonce'])
        return data

    def restore(self,*,abandoned=False):
        self.validate_assets(original_only=True)
        if not self.ledger.exists():return dict(pending=False,restored_targets=0)
        data=self.read()
        if abandoned:
            if live(data['owner']):raise RuntimeError('The original partial owner is still live')
        elif data['owner']!=owner():raise RuntimeError('Only the original live transaction may restore itself')
        # Validate both before modifying either. Never overwrite unrelated bytes.
        for p in self.targets:
            if p.is_symlink() or not p.is_file() or sha(p) not in (self.old_sha,self.new_sha):
                raise ValueError('Unrecognized partial file during recovery: '+str(p))
        restored=0
        for p in reversed(self.targets):
            temporary=p.with_name(p.name+'.owned_DFX_'+data['nonce'])
            if temporary.exists():
                if temporary.is_symlink() or not temporary.is_file():raise ValueError('Invalid owned copy temporary')
                # A killed copy can be incomplete; its exact ledger nonce and
                # fixed target directory establish exclusive ownership.
                temporary.unlink()
            if sha(p)==self.new_sha:self._copy(self.original,p,self.new_sha,data['nonce']);restored+=1
        if any(sha(p)!=self.old_sha for p in self.targets):raise RuntimeError('Original firmware was not restored')
        self.ledger.unlink();self._sync_parent(self.ledger)
        return dict(pending=True,restored_targets=restored,original_owner_terminal=abandoned,all_original_bytes_exact=True)
