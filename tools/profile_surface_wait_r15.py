"""Profile the original complete comparison CLI without touching PL or the UI."""
from pathlib import Path
import json,os,pstats,resource,subprocess,sys,traceback
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json


def main():
    checkpoint=json.loads((ROOT/'modules/surface_route/work_checkpoint_r14d.json').read_text())
    for n,h in checkpoint['source_sha256'].items():assert sha(ROOT/n)==h,n
    for n,h in checkpoint['current_board_state']['preserved_defaults_sha256'].items():assert sha(ROOT/n)==h,n
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();assert boot==checkpoint['current_board_state']['boot_id']
    out=ROOT/'modules/surface_route/results/wait_profile_ARM_r15';out.mkdir(exist_ok=False)
    scene=ROOT/'modules/surface_route/results/capability_scene_ARM_r14d/scene.json'
    case=json.loads(scene.read_text())
    argv=[str(ROOT/'.venv/bin/python'),'-m','cProfile','-o',str(out/'comparison.pstats'),
        str(ROOT/'modules/surface_route/active_backend_r14.py'),'comparison','--active-scene',str(scene),
        '--input',case['input'],'--result',case['result'],'--lesion','4','--diameter','1.8','--margin','0.3',
        '--minimum-bend','0','--output',str(out/'comparison_action')]
    started=perf_counter()
    try:
        with (out/'comparison.log').open('xb') as log:
            subprocess.run(argv,cwd=ROOT,env=dict(os.environ,OPENBLAS_NUM_THREADS='1'),stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,check=True)
        elapsed=perf_counter()-started;stats=pstats.Stats(str(out/'comparison.pstats'));rows=[]
        for (file,line,function),(primitive,calls,self_time,total_time,callers) in stats.stats.items():
            rows.append(dict(file=file,line=line,function=function,primitive_calls=primitive,calls=calls,
                self_seconds=self_time,cumulative_seconds=total_time))
        rows.sort(key=lambda x:x['cumulative_seconds'],reverse=True)
        for n,h in checkpoint['current_board_state']['preserved_defaults_sha256'].items():assert sha(ROOT/n)==h,n
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
        write_json(out/'profile.json',dict(status='original_current_surface_comparison_CLI_profiled_no_PL',argv=argv,
            profiled_elapsed_seconds=elapsed,profiler_overhead_not_subtracted=True,functions=rows,
            subprocess_peak_RSS_MiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/1024,
            source_checkpoint_sha256=sha(ROOT/'modules/surface_route/work_checkpoint_r14d.json'),
            script_sha256=sha(Path(__file__)),boot_id=boot,PL_access=False,production_promoted=False,
            top_30=rows[:30],evidence_sha256={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
        print('Original comparison profiled:',round(elapsed,3),'seconds',flush=True)
    except BaseException as error:write_json(out/'failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':main()
