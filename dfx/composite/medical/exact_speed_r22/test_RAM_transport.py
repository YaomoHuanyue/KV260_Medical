"""Measure the actual UI tmpfs transport, separating opacity updates and rotation."""
from pathlib import Path
import hashlib,json,os,statistics,subprocess,tempfile,time
ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    accepted=json.loads((HERE/'acceptance.json').read_text())
    assert accepted['status']=='passed_exact_layers_opacity_recomposition_speedup'
    scene=ROOT/'ui/cache/6714348fb2275d154633f3ae/scene.json'
    assert sha(scene)==accepted['scene_sha256']
    base=json.loads((ROOT/'ui/releases/feature_completion_r6/evidence_transparent_r1/interaction/transparent_interaction_UI.json').read_text())['baseline_request']
    env=os.environ.copy();env.pop('QT_QPA_PLATFORM',None);env['LD_PRELOAD']='/usr/lib/aarch64-linux-gnu/mali/wayland/libMali.so.9.0'
    references={};blocks=[]
    out=HERE/'RAM_transport.json';assert not out.exists()
    for index,kind in enumerate(('old','new','new','old')):
        binary=ROOT/'dfx/composite/medical/exact_speed_r14/worker' if kind=='old' else HERE/'worker'
        build=json.loads((binary.parent/'build.json').read_text())
        assert sha(binary)==build['binary_sha256']
        for key in ('source_sha256','shared_source_sha256','library_sha256'):
            for n,d in build[key].items():assert sha(ROOT/n)==d,n
        with tempfile.TemporaryDirectory(prefix='exact_opacity_probe_',dir='/run/kv260-ui-runtime') as staging:
            frame=Path(staging)/'frame.rgba'
            with (HERE/f'RAM_block_{index}.log').open('xb') as log:
                p=subprocess.Popen([str(binary),str(scene),str(frame),'baseline','1'],cwd=ROOT/'dfx/medical',env=env,
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
                trials=[]
                def event(kind):
                    while True:
                        line=p.stdout.readline()
                        if not line:raise RuntimeError('Worker ended before '+kind)
                        try:r=json.loads(line)
                        except json.JSONDecodeError:continue
                        if not isinstance(r,dict) or 'event' not in r:continue
                        if r['event']=='error':raise RuntimeError(r['text'])
                        if r['event']==kind:return r
                def run(name,extra):
                    request=dict(base,command='frame',sequence=len(trials)+1);request.update(extra)
                    start=time.perf_counter();p.stdin.write(json.dumps(request)+'\n');p.stdin.flush();r=event('frame');elapsed=time.perf_counter()-start
                    assert r['sequence']==request['sequence'] and r['report']['live_shared_composition']['guards_unchanged']
                    assert r['report']['scene_sha256']==sha(scene) and frame.stat().st_size==640*288*4
                    digest=sha(frame)
                    if index==0:references[name]=digest
                    else:assert digest==references[name],(kind,name,'pixels changed')
                    if kind=='new' and name.startswith('opacity_'):assert r['report']['exact_geometry_cache_hit']
                    if kind=='new' and name.startswith('rotate_'):assert not r['report']['exact_geometry_cache_hit']
                    trials.append(dict(name=name,seconds=elapsed,final_sha256=digest,event=r))
                    print(json.dumps(dict(block=index,mode=kind,case=name,seconds=elapsed)),flush=True)
                try:
                    event('ready');run('cold_excluded',{})
                    for i,a in enumerate((61,117,203,51,102,254)):run('opacity_'+str(i),dict(lung_opacity=a/255))
                    for i in range(2):run('rotate_'+str(i),dict(yaw_degrees=15*(i+1),pitch_degrees=-5*(i+1)))
                    p.stdin.write('{"command":"stop"}\n');p.stdin.flush();r=event('stopped')
                    assert r['normal_completion'] and r['surface_restored'] and p.wait()==0
                finally:
                    if p.poll() is None:p.stdin.write('{"command":"stop"}\n');p.stdin.flush();p.wait()
                blocks.append(dict(mode=kind,trials=trials,binary_sha256=sha(binary)))
    timing={k:{c:statistics.median(t['seconds'] for b in blocks if b['mode']==k for t in b['trials'] if t['name'].startswith(c+'_')) for c in ('opacity','rotate')} for k in ('old','new')}
    speed={c:timing['old'][c]/timing['new'][c] for c in ('opacity','rotate')}
    assert speed['opacity']>.9 and speed['rotate']>1.02
    record=dict(status='actual_UI_RAM_transport_exact_pixels_opacity_and_rotation_measured',
        timing_seconds=timing,speedup=speed,FPS={k:{c:1/v for c,v in t.items()} for k,t in timing.items()},
        blocks=blocks,source_sha256=sha(Path(__file__)),worker_acceptance_sha256=sha(HERE/'acceptance.json'),
        unchanged_input_scene_sha256=sha(scene),no_resolution_mesh_or_layer_reduction=True,
        opacity_updates_reuse_exact_layers=True,rotation_recomputes_all_geometry=True,
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    out.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(dict(timing=timing,speedup=speed)),flush=True)
if __name__=='__main__':main()
