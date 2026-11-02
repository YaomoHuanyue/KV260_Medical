"""Pinned existing board transport, bounded candidate, asynchronous checks."""
from pathlib import Path
import argparse,copy,hashlib,json,re,shlex,subprocess,sys,tarfile
import paramiko
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tools'));import board_remote as work
REMOTE=work.REMOTE+'/maintenance/production_trim'
try:promoted=json.loads((HERE/'published.json').read_bytes()).get('passed')is True
except (FileNotFoundError,json.JSONDecodeError):promoted=False
SRC=ROOT/'ui/v2/src'if promoted else HERE/'candidate/ui/v2/src'
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def package():
    subprocess.run([sys.executable,'-B','-X','utf8',str(ROOT/'tools/project_storage.py'),'check','--reserve-bytes','120000000'],cwd=ROOT.parent,stdout=subprocess.DEVNULL,check=True)
    main_source=(SRC/'main.cpp').read_text(encoding='utf8')
    assert 'developer-mode'not in main_source and 'breathingBox'not in main_source and 'glowToggle'not in main_source,'Retired UI implementation supplied as production source'
    names=set();base=ROOT if SRC==ROOT/'ui/v2/src'else HERE/'candidate'
    def visit(p):
        p=p.resolve();assert p.is_relative_to(SRC.resolve()),p
        name=p.relative_to(base).as_posix()
        if name in names:return
        names.add(name)
        for item in re.findall(r'^\s*#include\s*"([^"\n]+)"',p.read_text(encoding='utf8'),re.M):
            child=p.parent/item
            assert child.is_file(),child
            visit(child)
    for cpp in ('main.cpp','views.cpp','pl_scope.cpp','pl_composite.cpp'):visit(SRC/cpp)
    assert len(names)==29,'Unexpected production source closure; review the manifest'
    manifest=json.loads((ROOT/'ui/v2/manifest.json').read_bytes());manifest['name']='native_UI_V2_production';manifest['files_sha256']={n:work.sha(base/n)for n in sorted(names)}
    extras=('ui/v2/runtime.py','ui/v2/build.py','ui/releases/feature_completion_r6/backend_core_r6.py')
    manifest['files_sha256'].update({n:work.sha(ROOT/n)for n in extras});manifest['CXX_source_files']=29;manifest['launch_backend_dependencies']=list(extras)
    manifest['presentation_policy'].update(retired_code_physically_removed=True,developer_mode=False)
    save(HERE/'candidate_manifest.json',manifest)
    with tarfile.open(HERE/'source.tar','w')as f:
        for n in sorted(names):f.add(base/n,arcname=n,recursive=False)
        for n in extras:f.add(ROOT/n,arcname=n,recursive=False)
        f.add(HERE/'board_job.py',arcname='board_job.py')
    retired={n for n in json.loads((ROOT/'ui/v2/manifest.json').read_bytes())['files_sha256']if n not in names}
    if(HERE/'source_closure.json').exists():retired.update(json.loads((HERE/'source_closure.json').read_bytes())['retired'])
    retired.difference_update(names);retired.difference_update(extras)
    save(HERE/'source_closure.json',dict(files=sorted(names),count=len(names),retired=sorted(retired)))
    print(json.dumps(dict(source_files=len(names),archive_bytes=(HERE/'source.tar').stat().st_size)))
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['package','syntax','build','status','collect','start-gui','gui-status','collect-gui']);a=p.parse_args()
    if a.action=='package':package();return
    if a.action in ('syntax','build'):package()
    if a.action in ('collect','start-gui','collect-gui'):
        subprocess.run([sys.executable,'-B','-X','utf8',str(ROOT/'tools/project_storage.py'),'check','--reserve-bytes','60000000'],cwd=ROOT.parent,stdout=subprocess.DEVNULL,check=True)
    with work.connect()as t,paramiko.SFTPClient.from_transport(t)as s:
        if a.action=='start-gui':
            with s.open(REMOTE+'/status.json')as f:assert json.loads(f.read())['passed']
            s.put(str(HERE/'gui_job.py'),REMOTE+'/gui_job.py')
            launch="import subprocess;from pathlib import Path;p=Path("+repr(REMOTE)+");f=(p/'gui_job.log').open('wb');c=subprocess.Popen(["+repr(work.REMOTE+'/.venv/bin/python')+",'-B',str(p/'gui_job.py')],cwd=p,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);print(c.pid)"
            print(work.sudo_python(t,launch));return
        if a.action=='gui-status':
            with s.open(REMOTE+'/gui_validation/status.json')as f:print(f.read().decode())
            print(work.run(t,'tail -n 8 '+shlex.quote(REMOTE+'/gui_job.log')));return
        if a.action=='collect-gui':
            dest=HERE/'gui_validation';dest.mkdir(exist_ok=True)
            for n in ('verified.json','status.json','progress.json','C7_verified.json'):
                try:s.get(REMOTE+'/gui_validation/'+n,str(dest/n))
                except FileNotFoundError:pass
            for name in ['target_'+str(i)for i in range(6)]+['PL_transparency']:
                folder=dest/name;folder.mkdir(exist_ok=True)
                for n in s.listdir(REMOTE+'/gui_validation/'+name):
                    if n in ('ui_acceptance.json','UI.log')or(n.endswith('.png')and(n.startswith('07_')or n=='final.png')):s.get(REMOTE+'/gui_validation/'+name+'/'+n,str(folder/n))
            return
        if a.action in ('syntax','build'):
            work.run(t,'mkdir -p '+shlex.quote(REMOTE))
            try:
                with s.open(REMOTE+'/status.json')as f:state=json.loads(f.read())
                assert state.get('passed')is not None,'Previous owned compiler/check is still active'
            except FileNotFoundError:pass
            for n in ('source.tar','candidate_manifest.json'):s.put(str(HERE/n),REMOTE+'/'+n)
            assert work.run(t,'sha256sum '+shlex.quote(REMOTE+'/source.tar')).split()[0]==work.sha(HERE/'source.tar')
            work.run(t,'cd '+shlex.quote(REMOTE)+' && tar -xf source.tar')
            launch="import subprocess;from pathlib import Path;p=Path("+repr(REMOTE)+");f=(p/'job.log').open('wb');c=subprocess.Popen(['/usr/bin/python3','-u',str(p/'board_job.py'),"+repr(a.action)+"],cwd=p,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);print(c.pid)"
            print(work.run(t,'/usr/bin/python3 -c '+shlex.quote(launch)))
        elif a.action=='status':
            with s.open(REMOTE+'/status.json')as f:v=json.loads(f.read())
            print(json.dumps(v));print(work.run(t,'tail -n 18 '+shlex.quote(REMOTE+'/job.log')))
            if v.get('passed')is False:
                for n in ('main','views'):
                    try:
                        s.get(REMOTE+'/'+n+'.log',str(HERE/(n+'_syntax.log')))
                        errors=[line for line in(HERE/(n+'_syntax.log')).read_text().splitlines()if 'error:'in line]
                        print('\n'.join(errors[:45]))
                    except FileNotFoundError:pass
        elif a.action=='collect':
            for n in ('status.json','compiled.json','simplification.json','candidate_manifest.json','medical_ui'):s.get(REMOTE+'/'+n,str(HERE/n))
            assert work.sha(HERE/'medical_ui')==json.loads((HERE/'compiled.json').read_bytes())['ELF_SHA256']
if __name__=='__main__':main()
