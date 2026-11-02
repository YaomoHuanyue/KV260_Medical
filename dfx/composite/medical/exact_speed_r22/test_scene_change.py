"""Reject changed cached scene metadata using a private copy of the own-CT scene."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    source=ROOT/'ui/cache/6714348fb2275d154633f3ae/scene.json'
    digest=sha(source);copy=source.with_name('scene_cache_change_fixture_r1.json')
    assert not copy.exists();copy.write_bytes(source.read_bytes())
    env=os.environ.copy();env.pop('QT_QPA_PLATFORM',None);env['LD_PRELOAD']='/usr/lib/aarch64-linux-gnu/mali/wayland/libMali.so.9.0'
    try:
        with tempfile.TemporaryDirectory(prefix='scene_cache_check_',dir='/run/kv260-ui-runtime') as temp:
            with (HERE/'scene_change.log').open('xb') as log:
                p=subprocess.Popen([str(HERE/'worker'),str(copy),str(Path(temp)/'frame.rgba'),'baseline','1'],cwd=ROOT/'dfx/medical',env=env,
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
                def event(wanted):
                    while True:
                        line=p.stdout.readline()
                        assert line,'Worker exited before expected event'
                        try:r=json.loads(line)
                        except json.JSONDecodeError:continue
                        if not isinstance(r,dict) or 'event' not in r:continue
                        if r['event']==wanted:return r
                        assert r['event']!='error',r
                try:
                    event('ready')
                    request=dict(command='frame',sequence=1,width=32,height=16,full_lung=False)
                    p.stdin.write(json.dumps(request)+'\n');p.stdin.flush();first=event('frame')
                    assert first['report']['scene_sha256']==digest
                    with copy.open('ab') as f:f.write(b'\n')
                    request['sequence']=2;p.stdin.write(json.dumps(request)+'\n');p.stdin.flush();error=event('error')
                    assert error['text']=='Scene metadata changed; restart the worker'
                    assert p.wait()==1
                finally:
                    if p.poll() is None:
                        p.stdin.write('{"command":"stop"}\n');p.stdin.flush();p.wait()
        assert sha(source)==digest
        out=HERE/'scene_change.json';assert not out.exists()
        out.write_text(json.dumps(dict(status='changed_scene_rejected_before_second_frame',original_scene_sha256=digest,
            original_scene_unchanged=True,source_sha256=sha(Path(__file__)),worker_sha256=sha(HERE/'worker'),
            expected_error=error['text'],no_force_termination=True),indent=2)+'\n')
    finally:
        assert copy.parent==source.parent and copy.is_relative_to(ROOT/'ui/cache')
        copy.unlink();assert sha(source)==digest
if __name__=='__main__':main()
