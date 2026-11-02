"""Actual board correctness, boundary rejection and equal-precision benchmarks."""
from pathlib import Path
import argparse, ctypes, hashlib, json, resource, statistics, time
import numpy as np
from prepare import ROOT, frame_parameters, unpack_scene, write_json, sha
from runtime import Session

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--scene', type=Path, default=ROOT/'fixtures/own_ct_normals')
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True, exist_ok=False)
    cpu=ctypes.CDLL(str(ROOT/'host/libsurface_reference.so'))
    cpu.surface_reference.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]
    matrix=None
    def reference(q,target,p,threads=4):
        q=np.ascontiguousarray(q,np.int16);target=np.ascontiguousarray(target,np.uint8)
        result=np.empty(int(p[0])*int(p[1]),np.uint64);nz,ny,nx=q.shape
        begin=time.perf_counter();cpu.surface_reference(q.ctypes.data,target.ctypes.data,nx,ny,nz,p.ctypes.data,matrix.ctypes.data,result.ctypes.data,threads)
        return result,time.perf_counter()-begin
    def pixels(output):return output[16:].view(np.uint64)
    def load_scene(scene):
        nonlocal matrix
        matrix=np.frombuffer(scene,'<i4',count=16)[6:15].copy()
        return unpack_scene(scene)
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();synthetic=[];real=[];guards=[];pose_checks=[]
    meta=json.loads((args.scene/'scene.json').read_text());result=args.result.resolve()
    assert sha(result/'segmentation/airway_mask.nii.gz')==meta['airway_sha256']
    with np.load(result/'navigation/camera.npz') as f:camera={k:f[k] for k in f.files}
    with np.load(result/'navigation/route.npz') as f:arcs=f['arc_mm']
    with Session() as session:
        for name in ('tube','blocked','filled','empty','anisotropic','zero_normal','lastbrick','outside'):
            scene=(ROOT/f'fixtures/{name}.scene.bin').read_bytes();q,target=load_scene(scene)
            ack,_=session.transfer(scene,0,1);assert ack[2]==123
            p=np.fromfile(ROOT/f'fixtures/{name}.request.bin','<i4');expected=np.fromfile(ROOT/f'fixtures/{name}.expected.bin','<u8')
            for threads in (1,4):np.testing.assert_array_equal(reference(q,target,p,threads)[0],expected)
            for repeat in range(3):np.testing.assert_array_equal(pixels(session.transfer(p,1,1+expected.nbytes//64)[0]),expected)
            synthetic.append(dict(name=name,status='passed',repeats=3))
        # Invalid packets must be rejected in host code before selecting/starting DMA.
        good_scene=(ROOT/'fixtures/tube.scene.bin').read_bytes();good_p=np.fromfile(ROOT/'fixtures/tube.request.bin','<i4')
        session.transfer(good_scene,0,1)
        bad_id=bytearray(good_scene);bad_id[64:66]=b'\xff\xff'
        bad_count=bytearray(good_scene);np.frombuffer(bad_count,'<i4',count=16)[5]=4097
        bad_frame=good_p.copy();bad_frame[0]=31
        overflow=good_p.copy();overflow[7]=2147483647
        bad_matrix=bytearray(good_scene);np.frombuffer(bad_matrix,'<i4',count=16)[6]=32768
        for name,source,op,words in [('map_id',bytes(bad_id),0,1),('capacity',bytes(bad_count),0,1),('normal_matrix',bytes(bad_matrix),0,1),('viewport',bad_frame,1,65),('ray_overflow',overflow,1,65)]:
            try:session.transfer(source,op,words)
            except RuntimeError as exc:guards.append(dict(name=name,error=str(exc)))
            else:raise AssertionError('Unsafe input accepted: '+name)
        np.testing.assert_array_equal(pixels(session.transfer(good_p,1,65)[0]),np.fromfile(ROOT/'fixtures/tube.expected.bin','<u8'))
        for event in meta['events']:
            key=str(event['id']);info=meta['scenes'][key];path=args.scene/info['file'];assert sha(path)==info['sha256']
            scene=path.read_bytes();q,target=load_scene(scene);ack,upload=session.transfer(scene,0,1);assert ack[2]==info['token']
            distance=(event['show_from_mm']+event['hide_after_mm'])/2;index=min(int(np.searchsorted(arcs,distance)),len(arcs)-1)
            p,view=frame_parameters(camera['position_lps_mm'][index],camera['forward_lps'][index],camera['up_lps'][index],meta['geometry'],np.array(meta['offset_xyz']),128,80,event['id']+10)
            ref,cpu_time=reference(q,target,p);pl,timing=session.transfer(p,1,1+ref.nbytes//64);np.testing.assert_array_equal(pixels(pl),ref)
            pixels(pl).tofile(output/f'event_{key}_128x80.paired.bin')
            real.append(dict(event=event['id'],camera_index=index,view=view,cpu4_seconds=cpu_time,pl=timing,upload=upload,selected_pixels=int(np.count_nonzero((ref>>16)&255)),outline_pixels=int(np.count_nonzero((ref>>24)&255))))
        event=max(real,key=lambda r:r['selected_pixels']);info=meta['scenes'][str(event['event'])]
        scene=(args.scene/info['file']).read_bytes();q,target=load_scene(scene);session.transfer(scene,0,1);index=event['camera_index']
        for i in np.unique(np.linspace(0,len(arcs)-1,9).astype(int)):
            for yaw in (-35,0,35):
                f=camera['forward_lps'][i];u=camera['up_lps'][i];u=u/np.linalg.norm(u);radians=np.deg2rad(yaw)
                rotated=f*np.cos(radians)+np.cross(u,f)*np.sin(radians)+u*np.dot(u,f)*(1-np.cos(radians))
                p,_=frame_parameters(camera['position_lps_mm'][i],rotated,u,meta['geometry'],np.array(meta['offset_xyz']),64,37,102)
                ref,_=reference(q,target,p);got,_=session.transfer(p,1,1+ref.nbytes//64);np.testing.assert_array_equal(pixels(got),ref)
                pose_checks.append(dict(camera_index=int(i),yaw_degrees=yaw,width=64,height=37))
        checks=[]
        for width,height in [(640,512),(160,101),(192,123),(224,143),(256,163),(320,205),(384,245),(512,325),(640,363)]:
            p,view=frame_parameters(camera['position_lps_mm'][index],camera['forward_lps'][index],camera['up_lps'][index],meta['geometry'],np.array(meta['offset_xyz']),width,height,101)
            ref,_=reference(q,target,p);got,_=session.transfer(p,1,1+ref.nbytes//64);np.testing.assert_array_equal(pixels(got),ref);checks.append([width,height])
        # Warm both implementations; alternate the order to limit clock/thermal bias.
        reference(q,target,p,4);session.transfer(p,1,1+ref.nbytes//64)
        pl_times=[];cpu1=[];cpu4=[]
        for repeat in range(5):
            order=['pl','cpu4','cpu1'] if repeat%2 else ['cpu1','cpu4','pl']
            for implementation in order:
                if implementation=='pl':
                    got,t=session.transfer(p,1,1+ref.nbytes//64);np.testing.assert_array_equal(pixels(got),ref);pl_times.append(t)
                else:
                    got,t=reference(q,target,p,4 if implementation=='cpu4' else 1);np.testing.assert_array_equal(got,ref);(cpu4 if implementation=='cpu4' else cpu1).append(t)
        got,_=session.transfer(p,1,1+ref.nbytes//64)
        np.ascontiguousarray(got[16:].reshape(-1,2)[:,0]).tofile(output/'surface_640x363.rgba')
        np.ascontiguousarray(got[16:].reshape(-1,2)[:,1]).tofile(output/'normal_640x363.rgba');write_json(output/'view.json',view)
    assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    pl_median=statistics.median(x['host_seconds'] for x in pl_times)
    benchmark=dict(pl=pl_times,cpu1_seconds=cpu1,cpu4_seconds=cpu4,pl_host_median=pl_median,pl_hardware_median=statistics.median(x['hardware_seconds'] for x in pl_times),cpu4_median=statistics.median(cpu4),speedup_cpu4=statistics.median(cpu4)/pl_median)
    report=dict(status='passed',kind='actual_kv260_surface_dfx',boot_id=boot,airway_sha256=meta['airway_sha256'],release_manifest_sha256=sha(ROOT/'release/manifest.json'),synthetic=synthetic,host_guards=guards,own_ct=real,pose_checks=pose_checks,adaptive_viewports=checks,viewport=view,benchmark=benchmark,peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    write_json(output/'report.json',report);print(json.dumps(benchmark,indent=2),flush=True)
if __name__=='__main__':main()
