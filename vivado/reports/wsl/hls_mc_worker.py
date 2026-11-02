from pathlib import Path
import subprocess,json,os
r=Path(__file__).resolve().parent;p=r/'workspace';stages=[]
for stage in ['csim','csynth','package']:
 q=subprocess.run(['/usr/bin/python3','-B',str(p/'scripts/run_hls.py'),'mc',stage,'--tools','/opt/Xilinx/2025.2.1/Vitis'],cwd=p);stages.append(dict(stage=stage,exit_code=q.returncode))
 if q.returncode:break
(r/'hls_mc_terminal.json').write_text(json.dumps(dict(passed=len(stages)==3 and all(x['exit_code']==0 for x in stages),stages=stages),indent=2)+'\n')
