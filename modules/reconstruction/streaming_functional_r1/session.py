"""Qualified D7 MC followed by real D9 AXIS smoothing; exclusive stage owners.

The two existing native drivers retain their original guards and DFX lifecycle.
No PS smoother or fallback is present. Full-bank readback is an explicit option
for the first integrated numerical qualification, not a hidden PS calculation.
"""
from pathlib import Path
import csv,hashlib,json,os,time
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
D9_REL='modules/reconstruction/smooth_pipeline_r2/axis_tile1024_r1/host_D9_r1/hardware_r1'
EDGE=np.dtype([('index','<u4'),('weight','<f4')])


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def load_inputs(folder):
    values=(folder/'config.txt').read_text().split()
    if len(values)!=5:raise ValueError('Smoothing requires the original five configuration fields')
    nv,nf,nnz=int(values[0]),int(values[1]),int(values[2]);limit=float(values[3]);iterations=int(values[4])
    if not (1<=nv<=1_000_000 and 0<=nf<=2_000_000 and 0<=nnz<=12_000_000 and
            1<=iterations<=16 and np.isfinite(limit) and limit>0):raise ValueError('Invalid bounded smoothing configuration')
    arrays=[]
    for name,dtype,count in [('original','<f4',nv*4),('rows','<u4',nv+1),('edges',EDGE,nnz),('frozen','<u4',nv),('faces','<u4',nf*4)]:
        path=folder/(name+'.bin');dtype=np.dtype(dtype)
        if path.is_symlink() or path.stat().st_size!=count*dtype.itemsize:raise ValueError('Exact smoothing source size required: '+name)
        arrays.append(np.fromfile(path,dtype))
    points,rows,edges,frozen,faces=arrays
    if (rows[0]!=0 or rows[-1]!=nnz or np.any(rows[1:]<rows[:-1]) or np.any(rows>nnz) or
        np.any(frozen>1) or not np.isfinite(points.reshape(-1,4)[:,:3]).all() or
        (nnz and (np.any(edges['index']>=nv) or not np.isfinite(edges['weight']).all() or np.any(edges['weight']<=0))) or
        (nf and np.any(faces.reshape(-1,4)[:,:3]>=nv))):raise ValueError('Invalid smoothing graph/geometry before D9 opens')
    return arrays,(nv,nf,nnz,limit,iterations)


class Session:
    def __init__(self,report_dir,*,retain_full_banks=False):
        self.report_dir=Path(report_dir).resolve();self.retain_full_banks=retain_full_banks
        self.mc=None;self.smooth=None;self.mc_summary=None;self.jobs=[];self.open_seconds=0;self.metadata_loads=0
        self.closed=False;self._entered=False;self.log_path=ROOT/D9_REL/'results'/('switches_D9_'+str(os.getpid())+'.csv')
    def __enter__(self):
        if self._entered:raise RuntimeError('Composite reconstruction session is single-use')
        if not self.report_dir.is_relative_to(ROOT):raise ValueError('Owned reconstruction report directory required')
        from modules.reconstruction.axis_mc_8_r2.integration_guard import require_board_grade
        from modules.reconstruction.smooth_pipeline_r2.axis_tile1024_r1.host_D9_r1.hardware_r1.seal_release import verify
        require_board_grade();self.d9_manifest=verify(installed=True)
        if self.log_path.exists():raise FileExistsError('Preserve an existing D9 log for this PID')
        self.log_path.parent.mkdir(exist_ok=True)
        from modules.reconstruction.axis_mc_8_r2.host_pooled_r2.runtime import Session as MC
        started=time.perf_counter();self.mc=MC();self.mc.__enter__()
        self.open_seconds=time.perf_counter()-started;self.metadata_loads=1;self._entered=True
        return self
    def _handoff(self):
        if self.smooth is not None:return
        if self.mc is None:raise RuntimeError('MC stage owner missing')
        self.mc_summary=self.mc.report(self.report_dir/'MC_session.json')
        self.mc.close();self.mc=None
        # Native close has drained and isolated the first stage and released
        # its BOs/PL lock before a distinct XRT owner can be constructed.
        from modules.reconstruction.smooth_pipeline_r2.axis_tile1024_r1.host_D9_r1.hardware_r1.runtime import Session as Smooth
        started=time.perf_counter();smooth=Smooth();smooth.__enter__();self.smooth=smooth
        self.smoothing_open_seconds=time.perf_counter()-started;self.metadata_loads+=1
    def run(self,operation,folder,output,report):
        if not self._entered or self.closed:raise RuntimeError('Open composite stage owner required')
        folder=Path(folder).resolve(strict=True);output=Path(output).resolve();report=Path(report).resolve()
        if (not folder.is_relative_to(self.report_dir) or not output.is_relative_to(folder) or
            not report.is_relative_to(folder) or output.exists() or report.exists() or output==report):
            raise ValueError('Fresh distinct owned reconstruction outputs required')
        if operation=='mc':
            if self.smooth is not None or self.mc is None:raise RuntimeError('MC cannot run after smoothing begins')
            return self.mc.run(operation,folder,output,report)
        if operation!='smooth':raise ValueError('Unsupported reconstruction operation')
        arrays,config=load_inputs(folder);nv,nf,nnz,limit,iterations=config
        input_sha={name:sha(folder/(name+'.bin')) for name in ('original','rows','edges','frozen','faces')}
        self._handoff();started=time.perf_counter()
        if self.retain_full_banks:
            owners=[np.full(nv*4+256,0xa5a5a5a5,'<u4') for _ in range(5)]
            banks=[v[128:-128].view('<f4').reshape(nv,4) for v in owners]
            report_owner=np.full(272,0xa5a5a5a5,'<u4');status=report_owner[128:-128]
            metrics=self.smooth.run_full(arrays,banks,status,nv,nf,nnz,limit,iterations)
            for owner in [*owners,report_owner]:
                if not (np.all(owner[:128]==0xa5a5a5a5) and np.all(owner[-128:]==0xa5a5a5a5)):
                    raise RuntimeError('D9 Python output red zone damaged')
            hashes=[hashlib.sha256(v.tobytes()).hexdigest() for v in banks]
            for i,bank in enumerate(banks):bank.tofile(folder/('D9_work'+str(i)+'.f32'))
            final=banks[0]
        else:
            final=np.empty((nv,4),'<f4');status=np.zeros(16,'<u4')
            metrics=self.smooth.run(arrays,final,status,nv,nf,nnz,limit,iterations)
            hashes=[hashlib.sha256(final.tobytes()).hexdigest()]
        if status[0]!=0 or metrics['stream_errors']!=0 or (nnz and metrics['graph_requests']<=0):
            raise RuntimeError('D9 did not complete the actual graph/AXIS protocol')
        if metrics['graph_beats']!=metrics['graph_requests']*((nnz+7)//8):raise RuntimeError('D9 graph payload count differs')
        if input_sha!={name:sha(folder/(name+'.bin')) for name in input_sha}:raise RuntimeError('Smoothing input file changed')
        final.tofile(output)
        info=dict(backend='dfx_pl',kernel='D9_AXIS',transport='AXIS512',DMA_red_zones_checked=24,
            full_bank_readback=self.retain_full_banks,all_work_bank_SHA256=hashes,report_words=status.tolist(),
            input_SHA256=input_sha,vertices=nv,faces=nf,edges=nnz,limit_mm=limit,iterations=iterations,
            phases=metrics,host_seconds=time.perf_counter()-started,no_PS_smoothing_or_fallback=True,
            previous_MC_owner_drained_isolated_closed=True,known_PS4_speed_gate_failed_preserved=True)
        report.write_text(json.dumps(info,indent=2)+'\n');self.jobs.append(info)
        return info
    def close(self):
        if not self._entered or self.closed:return
        if self.mc is not None:
            if self.report_dir.is_dir() and not (self.report_dir/'MC_session.json').exists():
                self.mc_summary=self.mc.report(self.report_dir/'MC_session.json')
            self.mc.close();self.mc=None
        if self.smooth is not None:
            self.smooth.__exit__(None,None,None);self.smooth=None
        self.closed=True
    def report(self,path):
        if not self.closed:raise RuntimeError('Report the complete DFX lifecycle after both owners close')
        path=Path(path).resolve()
        if not path.is_relative_to(self.report_dir) or path.exists():raise ValueError('Fresh owned session report required')
        rows=[]
        if self.jobs:
            rows=list(csv.DictReader(self.log_path.open()))
            if [r['rm'] for r in rows]!=['axis_smooth','smooth']:raise RuntimeError('D9 restore lifecycle not complete')
            count=sum(j['phases']['graph_requests']+1 for j in self.jobs)
            if (int(rows[1]['static_transactions'])-int(rows[0]['static_transactions']))%65536!=count:
                raise RuntimeError('D9 actual static/header count does not cover all jobs')
        result=dict(status='completed',MC_context=self.mc_summary,xrt_metadata_loads=self.metadata_loads,
            partial_switches=(self.mc_summary or {}).get('partial_switches',0)+len(rows),
            MC_and_smoothing_context_reused=False,stage_owners_serial_drained_and_closed=True,
            D9_switches=rows,D9_switch_log=self.log_path.relative_to(ROOT).as_posix() if rows else None,
            D9_jobs=len(self.jobs),actual_D9_graph_headers=sum(j['phases']['graph_requests']+1 for j in self.jobs))
        path.write_text(json.dumps(result,indent=2)+'\n');return result
    def __exit__(self,*exception):self.close()
