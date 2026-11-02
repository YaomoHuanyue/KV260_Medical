"""Bounded publication and compact collection, using the pinned board transport."""
import argparse,json,shlex,subprocess,sys
import paramiko
from transport import ROOT,HERE,REMOTE,work
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['publish','publish-status','collect-release','post','post-status','collect-post','collect-results','service-check','service-status']);a=p.parse_args()
 if a.action not in ('publish-status','post-status'):
  subprocess.run([sys.executable,'-B','-X','utf8',str(ROOT/'tools/project_storage.py'),'check','--reserve-bytes','250000000'],cwd=ROOT.parent,check=True,stdout=subprocess.DEVNULL)
 with work.connect()as t,paramiko.SFTPClient.from_transport(t)as s:
  if a.action in ('publish','post','service-check'):
   with s.open(REMOTE+'/status.json')as f:assert json.loads(f.read()).get('passed')is True,'Owned compilation has not completed'
   stem={'publish':'publish','post':'post_cleanup','service-check':'service_check'}[a.action];job=stem+'_job.py'
   s.put(str(HERE/job),REMOTE+'/'+job)
   script="import subprocess;from pathlib import Path;p=Path("+repr(REMOTE)+");f=(p/"+repr(stem+'.log')+").open('wb');c=subprocess.Popen(["+repr(work.REMOTE+'/.venv/bin/python')+",'-B',str(p/"+repr(job)+")],cwd=p,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);print(c.pid)"
   print(work.sudo_python(t,script));return
  if a.action in ('publish-status','post-status','service-status'):
   name='publish_status.json'if a.action=='publish-status'else('service_check'if a.action=='service-status'else'post_cleanup')+'/status.json'
   with s.open(REMOTE+'/'+name)as f:print(f.read().decode())
   log='service_check/UI.log'if a.action=='service-status'else('publish'if a.action=='publish-status'else'post_cleanup')+'.log'
   print(work.run(t,'tail -n 12 '+shlex.quote(REMOTE+'/'+log)));return
  def get(n):
   dest=ROOT/n;dest.parent.mkdir(parents=True,exist_ok=True);s.get(work.REMOTE+'/'+n,str(dest))
  if a.action=='collect-release':
   with s.open(REMOTE+'/published.json')as f:assert json.loads(f.read())['passed']
   for n in ('ui/v2/manifest.json','ui/active_release.json','system/autostart/profile.json','maintenance/production_trim/published.json'):get(n)
   m=json.loads((ROOT/'ui/v2/manifest.json').read_bytes())
   for n,h in {**m['files_sha256'],m['binary']:m['binary_sha256']}.items():get(n);assert work.sha(ROOT/n)==h,n
   return
  if a.action=='collect-post':
   for n in ('verified.json','status.json','full_CT_result.json','full_CT_events.json','full_CT.log','C7/ui_acceptance.json'):
    try:get('maintenance/production_trim/post_cleanup/'+n)
    except FileNotFoundError:pass
   state=json.loads((HERE/'post_cleanup/verified.json').read_bytes())
   for n in ('pipeline.json','segmentation/report.json','reconstruction/report.json','navigation/dfx_report.json'):
    source=state['original_CT_result']+'/'+n;dest=HERE/'post_cleanup/native_reports'/n;dest.parent.mkdir(exist_ok=True,parents=True);s.get(source,str(dest))
   return
  data=json.loads((HERE/'distal_board/verified.json').read_bytes());files=[]
  def walk(folder):
   for item in s.listdir_attr(folder):
    name=folder+'/'+item.filename
    if __import__('stat').S_ISDIR(item.st_mode):yield from walk(name)
    else:yield name,item.st_size
  for row in data['targets']:
   for name,size in walk(row['result']):
    n=name[len(work.REMOTE)+1:];get(n);files.append(dict(path=n,bytes=size,SHA256=work.sha(ROOT/n)))
  work.save(HERE/'collected_results.json',dict(passed=True,files=files,bytes=sum(r['bytes']for r in files)))
  print(json.dumps(dict(files=len(files),bytes=sum(r['bytes']for r in files))))
if __name__=='__main__':main()
