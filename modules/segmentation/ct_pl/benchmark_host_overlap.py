"""Sequential, isolated full-CT A/B measurements; never kill an active DMA job."""
import sys, os, json, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    output=ROOT/'outputs/ct_accuracy_v2/host_overlap_comparison'
    output.mkdir(parents=True,exist_ok=False)
    rows=[]
    variants=[('baseline',0,'sleep',50),('pool',1,'sleep',50),('poll10',1,'sleep',10),('adaptive',1,'adaptive',10)]
    for name,fusion,mode,poll in variants:
        env=os.environ.copy();env.update(CT_PS_POOL_FUSION=str(fusion),CT_PL_WAIT_MODE=mode,CT_PL_POLL_US=str(poll))
        folder=ROOT/'outputs/ct_accuracy_v2'/('board_host_'+name);folder.mkdir(exist_ok=False)
        (output/'status.json').write_text(json.dumps(dict(status='running',variant=name,pid=os.getpid())))
        cmd=[sys.executable,str(ROOT/'ct_pl/run.py'),'_worker','--output',str(folder),'--model-dir',str(ROOT/'outputs/ct_accuracy_v2/pl_model'),'--scheduler','fused','--slice-workers','2','--repeats','3']
        with (folder/'run.log').open('w') as log:
            result=subprocess.run(cmd,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:
            (output/'status.json').write_text(json.dumps(dict(status='failed',variant=name,code=result.returncode)))
            raise RuntimeError('Benchmark failed: '+name)
        r=json.loads((folder/'report.json').read_text())
        if rows:
            assert r['repeat_raw_mask_sha256']==rows[0]['report']['repeat_raw_mask_sha256']
        assert all(r['agreement_with_pc'][n]['dice']==1 for n in ['lung','airway','nodule'])
        rows.append(dict(variant=name,report=r))
        (output/'report.json').write_text(json.dumps(dict(status='running',variants=rows),indent=2))
        print(name,r['median_inference_seconds'],r['repeat_pl_wait_seconds'],r['repeat_process_cpu_seconds'],flush=True)
    (output/'report.json').write_text(json.dumps(dict(status='completed',variants=rows),indent=2))
    (output/'status.json').write_text(json.dumps(dict(status='completed')))
if __name__=='__main__':main()
