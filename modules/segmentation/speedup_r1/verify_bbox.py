"""逐体素核对：整幅原始 clean_mask 与外包框版本。
   用法：python3 verify_bbox.py <分割目录或 airway_mask_network.nii.gz> ...
   输出每例两者的 SHA、info 是否一致和耗时；任一不一致则返回 1。"""
from pathlib import Path
import ast,hashlib,json,sys,time
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
import numpy as np,SimpleITK as sitk
from scipy import ndimage as ndi
from modules.segmentation.speedup_r1.bbox_clean import clean_mask_bbox
SOURCE=ROOT/'modules/segmentation/mixed_r30/reference/original_clean_airway_tree.py'
EXPECTED='6d6c5668864e45af4511260202f303b4ecba0caab589ab658b4c0be0784193b0'
def functions():
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==EXPECTED,'Changed original algorithm'
    body=[n for n in ast.parse(SOURCE.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ['keep_largest_component','clean_mask']]
    ns=dict(np=np,ndi=ndi);exec(compile(ast.Module(body=body,type_ignores=[]),str(SOURCE)+':original_functions','exec'),ns);return ns
def digest(a):return hashlib.sha256(memoryview(np.ascontiguousarray(a,dtype=np.uint8)).cast('B')).hexdigest()
def cases(args):
    """真实掩膜原样一例；--stress N 时再基于第一个掩膜生成 N 个扰动例（噪声、空洞、远处碎块、贴体数据边界的结构）。"""
    stress=0
    if '--stress' in args:i=args.index('--stress');stress=int(args[i+1]);args=args[:i]+args[i+2:]
    base=None
    for arg in args:
        p=Path(arg);p=p/'airway_mask_network.nii.gz' if p.is_dir() else p
        if not p.exists():yield str(p),None;continue
        raw=sitk.GetArrayFromImage(sitk.ReadImage(str(p)))>0
        if base is None:base=raw
        yield str(p),raw
    rng=np.random.default_rng(20261101)
    for k in range(stress):
        m=base.copy();Z,Y,X=m.shape
        m|=rng.random(m.shape)<rng.choice([1e-5,1e-4,5e-4])            # 椒盐噪声
        idx=np.argwhere(m);drop=idx[rng.random(len(idx))<0.02];m[tuple(drop.T)]=False  # 随机空洞
        for _ in range(int(rng.integers(3,12))):                        # 远处或贴边的小球/板
            c=[int(rng.integers(0,s)) for s in m.shape];r=int(rng.integers(1,6))
            if rng.random()<0.4:ax=int(rng.integers(0,3));c[ax]=0 if rng.random()<0.5 else m.shape[ax]-1   # 贴体数据边界
            zz,yy,xx=np.ogrid[:Z,:Y,:X];m|=((zz-c[0])**2+(yy-c[1])**2+(xx-c[2])**2)<=r*r
        if k%3==0:m[0:2,Y//2-20:Y//2+20,X//2-20:X//2+20]=True   # 顶层贴边块
        if k%3==1:                                                      # 主树内部人为封闭空腔
            zc,yc,xc=[int(v) for v in np.argwhere(base).mean(0)];m[zc-3:zc+4,yc-3:yc+4,xc-3:xc+4]=True;m[zc-1:zc+2,yc-1:yc+2,xc-1:xc+2]=False
        yield 'stress_%d'%k,m
def main():
    ns=functions();rows=[];ok=True
    for name,raw in cases(sys.argv[1:]):
        p=name
        if raw is None:rows.append(dict(path=name,missing=True));continue
        t=time.perf_counter();full,info_full=ns['clean_mask'](raw,1);tf=time.perf_counter()-t
        t=time.perf_counter();fast,info_fast,box=clean_mask_bbox(raw,ns,1);tb=time.perf_counter()-t
        same=bool(full.dtype==fast.dtype and full.shape==fast.shape and np.array_equal(full,fast)) and info_full==info_fast
        ok=ok and same
        rows.append(dict(path=str(p),identical=same,sha_full=digest(full),sha_bbox=digest(fast),info_equal=info_full==info_fast,
                         full_seconds=round(tf,2),bbox_seconds=round(tb,2),box=box,input_voxels=info_full['input_foreground_voxels']))
        print(json.dumps(rows[-1],ensure_ascii=False),flush=True)
    print(json.dumps(dict(all_identical=ok,cases=len([r for r in rows if not r.get('missing')]))))
    raise SystemExit(0 if ok else 1)
if __name__=='__main__':main()
