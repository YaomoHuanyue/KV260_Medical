"""Explicit PL smoothing; no bit switching or silent CPU fallback."""
from pathlib import Path
import fcntl,hashlib,json,subprocess,tempfile,time
import numpy as np
from scipy import sparse
from .smooth_host import prepare

def available(root):
    root=Path(root);firmware=Path('/sys/firmware/devicetree/base/fpga-region/firmware-name')
    return firmware.is_file() and firmware.read_bytes().rstrip(b'\0')==b'kv260_mc_smooth.bit.bin' and (root/'fpga/build/smooth_xrt').is_file()

class SmoothSession:
    """Reuse an idle XRT context only for the caller's reconstruction task."""
    def __init__(self,root):
        self.root=Path(root).resolve();self.process=None;self.closed=False

    def __enter__(self):return self

    def run(self,metadata,work):
        if self.closed:raise RuntimeError('Smoothing session is closed')
        if self.process is None:
            self.process=subprocess.Popen([str(self.root/'fpga/build/smooth_xrt'),'--session',str(metadata)],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1,cwd=self.root)
            if self.process.stdout.readline().strip()!='READY':
                raise RuntimeError('Smoothing session did not start')
        paths=[str(work),str(work/'points.f32'),str(work/'report.json')]
        if any(any(c in path for c in '\t\r\n') for path in paths):raise ValueError('Invalid session path')
        self.process.stdin.write('\t'.join(paths)+'\n');self.process.stdin.flush()
        if self.process.stdout.readline().strip()!='DONE':
            raise RuntimeError('Smoothing session failed; see native diagnostic')

    def __exit__(self,*error):
        self.closed=True
        if self.process is not None:
            try:self.process.stdin.close()
            except BrokenPipeError:pass
            # Never kill a timed-out accelerator's process: it retains DMA BOs.
            code=self.process.wait();self.process.stdout.close()
            if code and error[0] is None:raise RuntimeError(f'Smoothing session exit code {code}')

def smooth(points,faces,limit,root,iterations=8,session=None):
    root=Path(root).resolve()
    if not available(root):raise RuntimeError('PL smoothing firmware is not loaded; no automatic switching')
    folder=root/'fpga/smooth/package';manifest=json.loads((folder/'manifest.json').read_text())
    bit=Path('/run/kv260-mc-loaded.sha256').read_text().strip()
    metadata=folder/'kv260_mc_smooth.xclbin'
    if bit!=manifest['bit_bin_sha256'] or hashlib.sha256(metadata.read_bytes()).hexdigest()!=manifest['xclbin_sha256']:
        raise RuntimeError('Smoothing firmware/metadata hashes do not match')
    started=time.perf_counter();inputs=prepare(points,faces,limit,iterations)
    prepared_seconds=time.perf_counter()-started
    runtime=root/'outputs/xrt';runtime.mkdir(parents=True,exist_ok=True)
    with (runtime/'.hardware.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix='.smooth-',dir=runtime) as temporary:
            work=Path(temporary)
            for name in ('original','rows','edges','frozen','faces'):inputs[name].tofile(work/f'{name}.bin')
            (work/'config.txt').write_text(f"{len(points)} {len(faces)} {len(inputs['edges'])} {limit:.17g} {iterations}\n")
            if session is None:
                subprocess.run([str(root/'fpga/build/smooth_xrt'),str(metadata),str(work),str(work/'points.f32'),str(work/'report.json')],check=True,cwd=root)
            else:
                if session.root!=root:raise ValueError('Smoothing session belongs to another project')
                session.run(metadata,work)
            padded=np.fromfile(work/'points.f32',np.float32).reshape(len(points),4)
            result=np.ascontiguousarray(padded[:,:3]);hardware=json.loads((work/'report.json').read_text())
    original=np.asarray(points,np.float32)
    if not np.isfinite(result).all():raise RuntimeError('Nonfinite PL smoothing output')
    np.testing.assert_array_equal(result[inputs['frozen']!=0],original[inputs['frozen']!=0])
    movement=np.linalg.norm(result-original,axis=1)
    if movement.max()>limit+1e-4:raise RuntimeError('PL smoothing exceeds displacement bound')
    # One final independent PS geometry audit before publishing the mesh.
    before=original[faces];after=result[faces]
    n0=np.cross(before[:,1]-before[:,0],before[:,2]-before[:,0]);n1=np.cross(after[:,1]-after[:,0],after[:,2]-after[:,0])
    if not np.all(np.einsum('ij,ij->i',n0,n1)[np.linalg.norm(n0,axis=1)>1e-12]>0):raise RuntimeError('PL smoothing triangle inversion')
    average=sparse.csr_matrix((inputs['edges']['weight'],inputs['edges']['index'],inputs['rows']),shape=(len(points),len(points)))
    roughness_before=float(np.mean(np.linalg.norm(average@original-original,axis=1)))
    roughness_after=float(np.mean(np.linalg.norm(average@result-result,axis=1)))
    if roughness_after>roughness_before+1e-7:raise RuntimeError('PL smoothing increased roughness')
    info=dict(method='bounded_taubin',backend='pl',iterations=iterations,accepted_iterations=hardware['accepted_iterations'],
        coefficients=[.5,-.53],displacement_limit_mm=float(limit),max_displacement_mm=float(movement.max()),
        mean_displacement_mm=float(movement.mean()),frozen_vertices=int(np.count_nonzero(inputs['frozen'])),
        roughness_before_mm=roughness_before,roughness_after_mm=roughness_after,
        faces_unchanged=True,topology_unchanged=True,final_ps_orientation_audit=True,final_ps_roughness_audit=True,
        topology_prepare_seconds=prepared_seconds,hardware=hardware,total_seconds=time.perf_counter()-started)
    return result,info
