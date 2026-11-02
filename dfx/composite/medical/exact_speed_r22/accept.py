"""Full own-CT control equality, same-input composition and warm ABBA timings."""
from pathlib import Path
import fcntl,hashlib,json,os,statistics,subprocess,tempfile,time
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
OLD_ACCEPTANCE=ROOT/'dfx/composite/medical/exact_speed_r14/acceptance.json'

def main():
    chosen=dict(mode='single_VBO_paired_ID_color_async',options=['baseline','1'],batch_vertices=96000)
    out=HERE/'acceptance';assert not out.exists();out.mkdir()
    scene_path=ROOT/'ui/cache/6714348fb2275d154633f3ae/scene.json';scene=json.loads(scene_path.read_text())
    center=(np.array(scene['meshes']['airway']['bounds_min'])+scene['meshes']['airway']['bounds_max'])/2
    candidate=scene['candidates'][0];radius=max(12,float(np.linalg.norm(np.array(candidate['bounds_max'])-candidate['bounds_min']))*1.2)
    base=json.loads((ROOT/'ui/releases/feature_completion_r6/evidence_transparent_r1/interaction/transparent_interaction_UI.json').read_text())['baseline_request']
    controls=[('default',{}),('no_lung',dict(lung_opacity=0)),('airway_only',dict(layers=dict(lung=False,airway=True,nodule=False))),
      ('nodule_only',dict(layers=dict(lung=False,airway=False,nodule=True))),('all_hidden',dict(layers=dict(lung=False,airway=False,nodule=False))),
      *[(n,dict(layers=dict(lung=False,airway=True,nodule=False),color_mode=m,required_radius_mm=.7,resolution_margin_mm=1.36)) for n,m in [('generation',1),('reachability',2),('confidence',3)]],
      *[(f'clip_{a}',dict(layers=dict(lung=False,airway=True,nodule=True),clipping=dict(enabled=True,axis=a,value_mm=float(center[a])))) for a in range(3)],
      ('clip_analysis',dict(layers=dict(lung=False,airway=True,nodule=False),color_mode=2,required_radius_mm=.7,resolution_margin_mm=1.36,clipping=dict(enabled=True,axis=2,value_mm=float(center[2])))),
      ('zoom',dict(layers=dict(lung=False,airway=True,nodule=True),zoom=1.7)),('focus',dict(layers=dict(lung=False,airway=False,nodule=True),center_lps_mm=candidate['centroid_lps_mm'],radius_mm=radius)),
      ('opacity',dict(lung_opacity=.4)),('preview',dict(full_lung=False)),('return_full',{})]
    controls.extend([(f'lung_clip_{axis}',dict(clipping=dict(enabled=True,axis=axis,value_mm=float(center[axis])))) for axis in range(3)])
    controls.extend([('lung_zoom',dict(zoom=1.4)),('narrow_viewport',dict(width=320,height=144,yaw_degrees=35,pitch_degrees=10)),('lung_analysis',dict(color_mode=2,required_radius_mm=.7,resolution_margin_mm=1.36))])
    build=json.loads((HERE/'build.json').read_text());old_build=json.loads((ROOT/'dfx/composite/medical/exact_speed_r14/build.json').read_text())
    for b in (build,old_build):
        for group in ('source_sha256','shared_source_sha256','library_sha256'):
            for n,d in b.get(group,{}).items():assert sha(ROOT/n)==d,n
    env=os.environ.copy();env.pop('QT_QPA_PLATFORM',None);env['LD_PRELOAD']='/usr/lib/aarch64-linux-gnu/mali/wayland/libMali.so.9.0'
    references={};trials=[];status='failed';boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    with open('/tmp/kv260-ct-pl.lock','rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
      for block,kind in enumerate(('old','new','new','old')):
        binary=ROOT/'dfx/composite/medical/exact_speed_r14/worker' if kind=='old' else HERE/'worker'
        assert sha(binary)==(old_build if kind=='old' else build)['binary_sha256']
        options=['baseline','1'] if kind=='old' else chosen['options'];d=out/f'{block}_{kind}';d.mkdir();transport=tempfile.TemporaryDirectory(prefix='exact_ABBA_',dir='/run/kv260-ui-runtime');frame=Path(transport.name)/'frame.rgba'
        with (d/'stderr.log').open('w') as stderr:
          p=subprocess.Popen([str(binary),str(scene_path),str(frame),*options],cwd=ROOT/'dfx/medical',env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,bufsize=1)
          events=[];cases=[]
          def event(kind):
            while True:
              line=p.stdout.readline()
              if not line:raise RuntimeError('Worker ended before '+kind)
              try:r=json.loads(line)
              except json.JSONDecodeError:continue
              if not isinstance(r,dict) or 'event' not in r:continue
              events.append(r)
              if r['event']=='error':raise RuntimeError(r['text'])
              if r['event']==kind:return r
          def run(label,extra=None,capture=False,strong=False):
            request=dict(base,command='frame',sequence=len(cases)+1);request.update(extra or {})
            if capture:request['capture_path']=str(d/label)
            if strong:request['strong_PS_benchmark']=True
            start=time.perf_counter();p.stdin.write(json.dumps(request)+'\n');p.stdin.flush();r=event('frame');elapsed=time.perf_counter()-start
            report=r['report'];live=report['live_shared_composition'];assert live['guards_unchanged'] and not report['thirty_two_layer_overflow']
            assert report['scene_sha256']==sha(scene_path) and report['ct_sha256']==scene['input_sha256']
            assert r['sequence']==request['sequence'] and frame.stat().st_size==request['width']*request['height']*4
            target=d/(label+'.rgba');target.write_bytes(frame.read_bytes());digest=sha(target)
            if block==0:references[label]=dict(final=digest)
            else:assert digest==references[label]['final'],(block,label,'RGBA mismatch')
            hashes={}
            if capture:
              assert live['all_pixels_exact']
              hashes={f.name:sha(f) for f in (d/label).iterdir() if f.suffix in ('.ids','.rgba')}
              if block==0:references[label]['layers']=hashes
              else:assert hashes==references[label]['layers'],(block,label,'Identifier or color layer mismatch')
            cases.append(dict(label=label,request=request,elapsed_seconds=elapsed,event=r,final_sha256=digest,capture_sha256=hashes))
            print(json.dumps(dict(block=block,mode=kind,case=label,seconds=elapsed,geometry=report['gpu_geometry_seconds'],triangles=report['submitted_triangles'])),flush=True)
          try:
            event('ready');run('cold_excluded')
            if block<2:
              for label,extra in controls:run(label,extra,capture=True,strong=label=='default')
            if block<2:
              for a in (0,1,2,51,102,254,255):run('alpha_boundary_'+str(a),dict(lung_opacity=a/255),capture=True)
            # Complete numerical-capture writes before isolated warm UI-transport timing.
            os.sync();run('warm_excluded')
            for i in range(3):run('same_'+str(i))
            for i,a in enumerate((61,117,203)):run('opacity_warm_'+str(i),dict(lung_opacity=a/255))
            for i in range(3):run('rotate_'+str(i),dict(yaw_degrees=15*(i+1),pitch_degrees=-5*(i+1)))
            p.stdin.write('{"command":"stop"}\n');p.stdin.flush();r=event('stopped');assert r['surface_restored'] and r['normal_completion'] and p.wait()==0
          finally:
            if p.poll() is None:p.stdin.write('{"command":"stop"}\n');p.stdin.flush();p.wait()
            receipt=dict(block=block,kind=kind,cases=cases,events=events,returncode=p.returncode,binary_sha256=sha(binary),options=options)
            (d/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');trials.append(receipt);transport.cleanup()
      timing={}
      for kind in ('old','new'):
        timing[kind]={category:statistics.median(c['elapsed_seconds'] for t in trials if t['kind']==kind for c in t['cases'] if c['label'].startswith(category+'_')) for category in ('same','rotate','opacity_warm')}
      speed={c:timing['old'][c]/timing['new'][c] for c in ('same','rotate','opacity_warm')}
      speed_passed=speed['opacity_warm']>.9 and speed['rotate']>1.02
      status='passed_exact_layers_opacity_recomposition_speedup' if speed_passed else 'exact_but_not_faster_not_promoted'
      acceptance=dict(status=status,build=build,chosen=chosen,baseline_build=old_build,timing_seconds=timing,speedup=speed,exact_FPS={k:{c:1/s for c,s in v.items()} for k,v in timing.items()},
        controls_compared=17,additional_transparent_geometry_cases=6,opacity_boundary_cases=7,unchanged_camera_timing_reuses_full_exact_layers=True,rotation_timing_always_recomputes_geometry=True,all_complete_layers_and_final_pixels_bit_exact=True,source_sha256=sha(Path(__file__)),scene_sha256=sha(scene_path),
        baseline_acceptance_sha256=sha(OLD_ACCEPTANCE),boot_id=boot,trials=[dict(path=(out/f"{t['block']}_{t['kind']}/receipt.json").relative_to(ROOT).as_posix(),sha256=sha(out/f"{t['block']}_{t['kind']}/receipt.json")) for t in trials],
        cold_start_excluded_from_warm_speedup=True,warm_transport='actual_UI_tmpfs_after_capture_sync',no_mesh_layer_or_resolution_reduction=True,new_PL_bitstream=False,production_UI_promoted=False)
      (HERE/'acceptance.json').write_text(json.dumps(acceptance,indent=2)+'\n');print(json.dumps(dict(status=status,timing=timing,speedup=speed)),flush=True)
    finally:
      assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
      (HERE/'acceptance_completion.json').write_text(json.dumps(dict(status=status,completed_blocks=len(trials),source_sha256=sha(Path(__file__))),indent=2)+'\n')
if __name__=='__main__':main()
