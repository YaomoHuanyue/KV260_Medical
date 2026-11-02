"""Serial, full unprofiled CLI A/B; unchanged C1, CT and selected polyline."""
from pathlib import Path
from time import perf_counter,sleep
import json,os,subprocess,sys,traceback
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json,arrays


def semantic(value):
    if isinstance(value,dict):
        return {k:semantic(v) for k,v in value.items() if not k.endswith('_seconds')}
    if isinstance(value,list):return [semantic(v) for v in value]
    return value


def exact_arrays(left,right):
    a,b=arrays(left),arrays(right);assert set(a)==set(b)
    for key in a:
        assert a[key].dtype==b[key].dtype and a[key].shape==b[key].shape,key
        np.testing.assert_array_equal(a[key],b[key],err_msg=key)
    return {k:dict(dtype=str(a[k].dtype),shape=list(a[k].shape)) for k in a}


def main():
    closure=ROOT/'modules/surface_route/wait_source_closure_r15.json'
    bound=json.loads(closure.read_text())['files_sha256']
    for n,h in bound.items():assert sha(ROOT/n)==h,n
    checkpoint=json.loads((ROOT/'modules/surface_route/work_checkpoint_r14d.json').read_text())
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot==checkpoint['current_board_state']['boot_id']
    for n,h in checkpoint['current_board_state']['preserved_defaults_sha256'].items():assert sha(ROOT/n)==h,n
    out=ROOT/'modules/surface_route/results/wait_benchmark_ARM_r15';out.mkdir(exist_ok=False)
    scene=ROOT/'modules/surface_route/results/capability_scene_ARM_r14d/scene.json'
    case=json.loads(scene.read_text());samples=[]

    def run(revision,action,source,extra):
        output=out/(revision+'_'+action)
        argv=[str(ROOT/'.venv/bin/python'),str(ROOT/f'modules/surface_route/active_backend_{revision}.py'),
            action,'--active-scene',str(source),'--input',case['input'],'--result',case['result'],
            '--output',str(output),*extra]
        started=perf_counter();peak=0
        with (out/(revision+'_'+action+'.log')).open('xb') as log:
            child=subprocess.Popen(argv,cwd=ROOT,env=dict(os.environ,OPENBLAS_NUM_THREADS='1'),
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
            write_json(out/'running.json',dict(PID=child.pid,argv=argv,action=action,revision=revision))
            while child.poll() is None:
                try:
                    for line in (Path('/proc')/str(child.pid)/'status').read_text().splitlines():
                        if line.startswith('VmHWM:'):peak=max(peak,int(line.split()[1])/1024)
                except FileNotFoundError:pass
                sleep(.25)
            if child.returncode:raise RuntimeError('CLI failed: '+str(argv))
        elapsed=perf_counter()-started
        rows=[json.loads(line) for line in (out/(revision+'_'+action+'.log')).read_text().splitlines() if line.startswith('{')]
        assert rows[-1]==dict(event='completed',status='passed')
        reuse=next((r for r in rows if r['event']=='verification_reuse'),None)
        sample=dict(revision=revision,action=action,elapsed_seconds=elapsed,peak_RSS_MiB=peak,argv=argv,
            verification_reuse=reuse,full_CLI_including_startup_input_validation_computation_publish_and_final_validation=True)
        samples.append(sample);write_json(out/'samples.json',samples)
        print(revision,action,round(elapsed,3),'seconds',flush=True)
        return output

    try:
        subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'modules/surface_route/test_verification_session_r15.py'),
            '--output',str(out/'verification_guards_ARM_r15.json')],cwd=ROOT,check=True)
        options=['--lesion','4','--diameter','1.8','--margin','0.3','--minimum-bend','0']
        old=run('r14','comparison',scene,options);new=run('r15','comparison',scene,options)
        proofs=dict(comparison_arrays=exact_arrays(old/'comparison/whole_comparison_arrays.npz',new/'comparison/whole_comparison_arrays.npz'))
        for name in ('whole_instrument_profiles.json','whole_alternative_routes.json'):
            a,b=[json.loads((p/'comparison'/name).read_text()) for p in (old,new)]
            assert semantic(a)==semantic(b),name
        # Both selected-path trials consume the exact same original comparison,
        # rather than comparisons whose independent timing fields change hashes.
        source=old/'UI/scene.json'
        old_selected=run('r14','selected-path',source,['--group','2','--candidate','0'])
        new_selected=run('r15','selected-path',source,['--group','2','--candidate','0'])
        for name in ('route.npz','camera.npz','mesh.npz'):
            proofs[name]=exact_arrays(old_selected/'bundle'/name,new_selected/'bundle'/name)
        a,b=[json.loads((p/'bundle/scene.json').read_text()) for p in (old_selected,new_selected)]
        assert a['renderer_scalar_sha256']==b['renderer_scalar_sha256']
        assert a['route_id']==b['route_id'] and a['scenes']==b['scenes']
        packets=[]
        for name in ['airway.vertices',*[entry['file'] for entry in a['scenes'].values()]]:
            assert sha(old_selected/'bundle'/name)==sha(new_selected/'bundle'/name),name;packets.append(name)
        for name in ('route.json','guidance.json','hud.json'):
            a,b=[json.loads((p/'bundle'/name).read_text()) for p in (old_selected,new_selected)]
            assert semantic(a)==semantic(b),name
        for n,h in bound.items():assert sha(ROOT/n)==h,n
        for n,h in checkpoint['current_board_state']['preserved_defaults_sha256'].items():assert sha(ROOT/n)==h,n
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
        write_json(out/'acceptance.json',dict(status='full_original_and_scoped_CLI_same_input_semantics_and_packets_passed',
            samples=samples,comparison_and_selected_arrays_exact=proofs,all_selected_scalar_target_packets_and_vertex_stream_byte_exact=packets,
            comparison_route_guidance_HUD_semantics_exact_excluding_only_seconds_fields=True,
            single_serial_sample_per_action_not_a_statistical_distribution=True,
            source_closure_sha256=sha(closure),test_source_sha256=sha(Path(__file__)),boot_id=boot,
            PL_access=False,new_bitstream=False,production_promoted=False,
            evidence_sha256={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
        print('Full original/scoped comparison and selection equivalence passed',flush=True)
    except BaseException as error:write_json(out/'failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':main()
