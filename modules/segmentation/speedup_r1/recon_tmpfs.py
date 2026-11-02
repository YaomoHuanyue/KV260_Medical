"""在内存盘中运行原版重建，只把最终结果写回 SD 卡。

板载 SD 卡顺序写入约 4.7 MB/s。原版重建在结果目录下写约 130 MB 的 D7/D9 中间缓冲
（edges.bin、vertices.u64、mask.u8、mesh_before.npz 等），这些只在重建进程内部使用；
后续导航、界面和重规划只读取重建目录顶层文件（*.npz、report.json 等）。
本脚本：
  1 在工程目录内的 tmpfs（ui/scratch，原版要求输出位于工程目录内）运行未修改的 run_reconstruction.py；
  2 成功后把顶层文件和子目录中的小型文本/JSON 证据（≤1 MiB）复制到正式输出目录，逐个核对 SHA256；
  3 删除内存盘中的工作目录。重建算法、固件和 DFX 生命周期都不改变。"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,uuid
ROOT=Path(__file__).resolve().parents[3]
SCRATCH=ROOT/'ui/scratch'
ORIGINAL=ROOT/'modules/reconstruction/streaming_functional_r1/run_reconstruction.py'
SMALL=1<<20
def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def mounted_tmpfs(path):
    real=str(path.resolve())
    return any(line.split()[1]==real and line.split()[2]=='tmpfs' for line in open('/proc/mounts'))
def ensure_scratch():
    SCRATCH.mkdir(mode=0o700,exist_ok=True)
    if not mounted_tmpfs(SCRATCH):
        subprocess.run(['mount','-t','tmpfs','-o','size=1024m,mode=0700','kv260_scratch',str(SCRATCH)],check=True)
    if not mounted_tmpfs(SCRATCH):raise RuntimeError('tmpfs scratch is not mounted')
def main():
    args=sys.argv[1:]
    i=args.index('--output');final=Path(args[i+1]).resolve()
    if final.exists():raise FileExistsError('Fresh reconstruction output required')
    ensure_scratch()
    work=SCRATCH/('recon_'+uuid.uuid4().hex);work.mkdir(mode=0o700)
    temp=work/'reconstruction';args[i+1]=str(temp)
    try:
        rc=subprocess.run([sys.executable,'-B',str(ORIGINAL),*args],cwd=ROOT).returncode
        if rc!=0:raise SystemExit(rc)
        final.mkdir();copied={}
        for src in sorted(temp.rglob('*')):
            if not src.is_file() or src.is_symlink():continue
            rel=src.relative_to(temp)
            if len(rel.parts)>1 and src.stat().st_size>SMALL:continue   # 大块中间缓冲不写回 SD 卡
            dst=final/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
            if sha(dst)!=sha(src):raise RuntimeError('Copy mismatch: '+str(rel))
            copied[str(rel)]=dst.stat().st_size
        dropped=sum(p.stat().st_size for p in temp.rglob('*') if p.is_file() and str(p.relative_to(temp)) not in copied)
        (final/'scratch_transfer.json').write_text(json.dumps(dict(
            policy='original reconstruction executed in tmpfs; top-level results and small evidence copied with SHA check',
            copied_files=len(copied),copied_bytes=sum(copied.values()),intermediate_bytes_not_written_to_SD=dropped),indent=2)+'\n')
    finally:
        shutil.rmtree(work,ignore_errors=True)
if __name__=='__main__':main()
