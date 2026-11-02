"""A/B final PS changes, with common wait settings and immutable PL outputs."""
import sys, os, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    output=ROOT/'outputs/ct_accuracy_v2/host_final_comparison';output.mkdir(exist_ok=False)
    first=json.loads((ROOT/'outputs/ct_accuracy_v2/host_overlap_comparison/report.json').read_text())
    winner=min(first['variants'],key=lambda r:r['report']['median_inference_seconds'])['report']
    mode=winner['wait_mode'];poll=winner['poll_microseconds']
    reference=first['variants'][0]['report']['repeat_raw_mask_sha256'];rows=[]
    for name,pool,clean,direct in [('vector',0,0,0),('vector_pool',1,0,0),('clean',1,1,0),('direct',1,1,1)]:
        env=os.environ.copy();env.update(CT_PS_POOL_FUSION=str(pool),CT_PL_CLEAN_BO=str(clean),CT_PS_DIRECT_MASK=str(direct),CT_PL_WAIT_MODE=mode,CT_PL_POLL_US=str(poll))
        folder=ROOT/'outputs/ct_accuracy_v2'/('board_host_'+name);folder.mkdir(exist_ok=False)
        (output/'status.json').write_text(json.dumps(dict(status='running',variant=name,pid=os.getpid())))
        cmd=[sys.executable,str(ROOT/'ct_pl/run.py'),'_worker','--output',str(folder),'--model-dir',str(ROOT/'outputs/ct_accuracy_v2/pl_model'),'--scheduler','fused','--slice-workers','2','--repeats','3']
        with (folder/'run.log').open('w') as log:
            result=subprocess.run(cmd,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError('Failed: '+name)
        r=json.loads((folder/'report.json').read_text());assert r['repeat_raw_mask_sha256']==reference
        assert all(r['agreement_with_pc'][n]['dice']==1 for n in ['lung','airway','nodule'])
        rows.append(dict(variant=name,report=r));print(name,r['median_inference_seconds'],r['repeat_process_cpu_seconds'],flush=True)
        (output/'report.json').write_text(json.dumps(dict(status='running',variants=rows),indent=2))
    (output/'report.json').write_text(json.dumps(dict(status='completed',variants=rows),indent=2))
    (output/'status.json').write_text(json.dumps(dict(status='completed')))
if __name__=='__main__':main()
