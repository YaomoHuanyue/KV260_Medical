"""Add one selected-path action; retain all accepted R6 import/stage actions."""
from pathlib import Path
import argparse,os,sys,time,uuid
import backend_r6 as accepted
import backend_core_r6 as backend

def main():
    if len(sys.argv)<2 or sys.argv[1]!='selected-path':return accepted.main()
    parser=argparse.ArgumentParser()
    parser.add_argument('action');parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--group',type=int,required=True);parser.add_argument('--candidate',type=int,required=True)
    a=parser.parse_args()
    os.environ.setdefault('ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS','2')
    os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
    if hasattr(os,'nice'):os.nice(10)
    sys.path.insert(0,str(backend.ROOT/'modules/navigation_comparison'))
    from selected_pipeline_r1 import run
    import fcntl
    backend.RUNS.mkdir(parents=True,exist_ok=True)
    with (backend.RUNS/'.runner.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        output=backend.RUNS/('selected_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
        return run(a.input,a.result,output,a.group,a.candidate,emit=backend.emit)
if __name__=='__main__':
    try:main()
    except Exception as error:backend.emit('error',text=str(error));sys.exit(1)
