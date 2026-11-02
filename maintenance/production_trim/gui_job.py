"""Six real EGLFS/PL target views plus retained C7 transparency regression."""
from pathlib import Path
import importlib.util,json,os,shutil,subprocess,time,traceback
import numpy as np
import SimpleITK as sitk
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OUT=HERE/'gui_validation';SERVICE='kv260-medical-ui.service'
def read(p):return json.loads(p.read_bytes())
def save(n,v):p=OUT/n;p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v,indent=2)+'\n')
def main():
 assert os.geteuid()==0;OUT.mkdir(exist_ok=True);assert read(HERE/'status.json')['passed']
 if(OUT/'verified.json').exists():
  prior=read(OUT/'verified.json');current=read(HERE/'compiled.json')
  assert prior['ELF_SHA256']!=current['ELF_SHA256'],'Already tested this candidate'
  history=read(HERE/'prior_GUI_qualified.json')if(HERE/'prior_GUI_qualified.json').exists()else[]
  history.append(prior);(HERE/'prior_GUI_qualified.json').write_text(json.dumps(history,indent=2)+'\n');(OUT/'verified.json').unlink()
 data=read(HERE/'distal_board/verified.json');assert data['passed'];compiled=read(HERE/'compiled.json');assert compiled['passed']
 if(OUT/'status.json').exists()and read(OUT/'status.json').get('passed')is False:
  history=read(HERE/'gui_failures.json')if(HERE/'gui_failures.json').exists()else[]
  old=read(OUT/'status.json');old['note']='Prior failed candidate check; preserved before retry.';history.append(old)
  (HERE/'gui_failures.json').write_text(json.dumps(history,indent=2)+'\n')
 spec=importlib.util.spec_from_file_location('runtime',ROOT/'ui/v2/runtime.py');runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
 parent_manifest=runtime.sha(ROOT/'ui/v2/manifest.json');assert runtime.sha(HERE/'medical_ui')==compiled['ELF_SHA256']
 state=subprocess.check_output(['systemctl','show','-p','ActiveState','--value',SERVICE],text=True).strip();active=state in ('active','activating')
 rows=[];save('status.json',dict(stage='releasing_current_UI',passed=None,PID=os.getpid()))
 try:
  if active:subprocess.run(['systemctl','stop',SERVICE],check=True,timeout=120)
  assert not runtime.running()
  for row in data['targets']:
   target=row['target'];folder=OUT/('target_'+str(target));folder.mkdir(exist_ok=True)
   save('status.json',dict(stage='actual_PL_HDMI_target',target=target,passed=None))
   command=[str(HERE/'medical_ui'),'--root',str(ROOT),'--input',data['input'],'--result',row['result'],'--navigation-test','--evidence',str(folder)]
   with(folder/'UI.log').open('wb')as log:rc=subprocess.run(command,cwd=ROOT,env=runtime.environment(),stdout=log,stderr=subprocess.STDOUT,timeout=200).returncode
   report=read(folder/'ui_acceptance.json');end=report.get('navigation_interaction',{}).get('synthetic_wall_endpoint_frame',{})
   image=folder/'07_synthetic_wall_target_viewport.png';red=0
   if image.exists():
    pixels=sitk.GetArrayFromImage(sitk.ReadImage(str(image))).astype(np.float32);red=int(np.sum((pixels[:,:,0]>=100)&(pixels[:,:,1]<pixels[:,:,0]*.42)&(pixels[:,:,2]<pixels[:,:,0]*.36)))
   checks=dict(clean_exit=rc==0,UI_passed=report['status']=='passed',GPU_error_empty=not report['scope']['error'],PL_frames=report['pl_scope_frames']>20,target_endpoint_ready=report['navigation_interaction'].get('synthetic_wall_endpoint_ready')is True,red_surface_visible=red>100)
   value=dict(target=target,passed=all(checks.values()),checks=checks,red_pixels=red,actual_update_fps=report['navigation_interaction']['actual_update_fps'],fragment_uniform_vectors=report['scope'].get('fragment_uniform_vectors'),result=row['result'],evidence=str(folder/'ui_acceptance.json'))
   rows.append(value);save('progress.json',rows);print(json.dumps(value),flush=True);assert value['passed'],value
   if target!=0:
    cache=Path(report['scene']).parent.resolve();assert cache.parent==(ROOT/'ui/cache').resolve();meta=read(cache/'scene.json');assert meta['input']==data['input']and meta['result']==row['result'];shutil.rmtree(cache)
  # A retained display feature must keep its real PL path after source pruning.
  folder=OUT/'PL_transparency';folder.mkdir(exist_ok=True);env=runtime.environment();env['KV260_COMPOSITE_UI_TEST']='1'
  save('status.json',dict(stage='actual_C7_transparency',passed=None))
  with(folder/'UI.log').open('wb')as log:rc=subprocess.run([str(HERE/'medical_ui'),'--root',str(ROOT),'--input',data['input'],'--result',data['targets'][0]['result'],'--smoke','--evidence',str(folder)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240).returncode
  report=read(folder/'ui_acceptance.json');checks=dict(clean_exit=rc==0,UI_passed=report['status']=='passed',PL_composite_frames=report.get('composite_frames',0)>0,overview_error_empty=not report['overview']['error'])
  save('C7_verified.json',dict(passed=all(checks.values()),checks=checks,frames=report.get('composite_frames')));assert all(checks.values()),checks
  assert runtime.sha(ROOT/'ui/v2/manifest.json')==parent_manifest
  save('verified.json',dict(passed=True,ELF_SHA256=compiled['ELF_SHA256'],targets=rows,real_C7_transparency_passed=True,parent_manifest_unchanged=True,physical_manual_acceptance=False,new_bitstream=False))
  save('status.json',dict(stage='passed',passed=True))
 finally:
  if active:subprocess.run(['systemctl','start',SERVICE],check=True,timeout=180)
if __name__=='__main__':
 try:main()
 except BaseException as e:OUT.mkdir(exist_ok=True);save('status.json',dict(stage='failed',passed=False,error=str(e)));traceback.print_exc()
