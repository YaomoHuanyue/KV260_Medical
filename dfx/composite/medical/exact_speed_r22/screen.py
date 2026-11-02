"""Single complete captured own-CT frame gate before the larger ABBA trial."""
from pathlib import Path
import hashlib,json,os,subprocess,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    b=json.loads((HERE/'build.json').read_text())
    for key in ('source_sha256','shared_source_sha256','library_sha256'):
        for n,d in b[key].items():assert sha(ROOT/n)==d,n
    assert sha(HERE/'worker')==b['binary_sha256']
    prior=ROOT/'dfx/composite/medical/exact_speed_r14/acceptance/1_new/receipt.json'
    r=json.loads(prior.read_text());assert r['returncode']==0
    baseline=next(c for c in r['cases'] if c['label']=='default')
    old=json.loads((ROOT/'dfx/composite/medical/exact_speed_r14/build.json').read_text())
    assert r['binary_sha256']==old['binary_sha256']
    request=dict(baseline['request']);request['sequence']=1
    directory=HERE/'screen';assert not directory.exists();directory.mkdir()
    request['capture_path']=str(directory/'full')
    scene=ROOT/'ui/cache/6714348fb2275d154633f3ae/scene.json'
    assert sha(scene)==baseline['event']['report']['scene_sha256']
    env=os.environ.copy();env.pop('QT_QPA_PLATFORM',None);env['LD_PRELOAD']='/usr/lib/aarch64-linux-gnu/mali/wayland/libMali.so.9.0'
    events=[];status='failed';error=None
    with (directory/'stderr.log').open('xb') as log:
        child=subprocess.Popen([str(HERE/'worker'),str(scene),str(directory/'frame.rgba'),'baseline','1'],cwd=ROOT/'dfx/medical',env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
        def event(kind):
            while True:
                line=child.stdout.readline();assert line,'Worker exited unexpectedly'
                try:r=json.loads(line)
                except ValueError:continue
                if not isinstance(r,dict) or 'event' not in r:continue
                events.append(r);assert r['event']!='error',r
                if r['event']==kind:return r
        try:
            event('ready');start=time.perf_counter();child.stdin.write(json.dumps(request)+'\n');child.stdin.flush();frame=event('frame');elapsed=time.perf_counter()-start
            hashes={f.name:sha(f) for f in (directory/'full').iterdir() if f.suffix in ('.ids','.rgba')}
            assert hashes==baseline['capture_sha256'],'Complete identifier/color layer mismatch'
            assert sha(directory/'frame.rgba')==baseline['final_sha256'],'Final pixels differ'
            child.stdin.write('{"command":"stop"}\n');child.stdin.flush();stopped=event('stopped');assert stopped['surface_restored'] and child.wait()==0
            status='passed_complete_identifiers_colors_and_final_exact'
        except Exception as exc:
            error=str(exc);raise
        finally:
            if child.poll() is None:child.stdin.write('{"command":"stop"}\n');child.stdin.flush();child.wait()
            (HERE/'screen.json').write_text(json.dumps(dict(status=status,error=error,events=events,returncode=child.returncode,
                baseline_receipt_sha256=sha(prior),binary_sha256=sha(HERE/'worker'),source_sha256=sha(Path(__file__))),indent=2)+'\n')
if __name__=='__main__':main()
