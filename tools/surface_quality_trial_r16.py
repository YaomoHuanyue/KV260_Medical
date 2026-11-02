"""Actual quality UI, four own-CT regenerations, new-case and PS/PL controls."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic,perf_counter,sleep
import fcntl,json,os,signal,subprocess,sys,traceback
import numpy as np
import SimpleITK as sitk
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json
from modules.surface_route.verification_session_r15 import VerificationSession
from modules.surface_route.quality_action_r16 import produce
from modules.surface_route.quality_validation_r16 import verify_active_scene

OUT=ROOT/'modules/surface_route/results/quality_trial_ARM_r16'

def close_review():
    previous=json.loads((ROOT/'modules/surface_route/results/native_active_surface_review_ARM_r15/started.json').read_text())
    pid=previous['PID'];cmd=Path(f'/proc/{pid}/cmdline')
    if cmd.exists():
        assert cmd.read_bytes().rstrip(b'\0').split(b'\0')==[s.encode() for s in previous['argv']]
        assert not Path(f'/proc/{pid}/task/{pid}/children').read_text().strip()
        write_json(OUT/'close_requested.json',dict(PID=pid,argv=previous['argv'],signal='SIGTERM',forced=False))
        os.kill(pid,signal.SIGTERM);deadline=monotonic()+45
        while cmd.exists() and monotonic()<deadline:sleep(.25)
        if cmd.exists():raise RuntimeError('Supported UI drain unfinished; no forced termination')
    return Path(previous['scene'])

def UI_environment(scene,test=False):
    runtime=Path('/run/kv260-ui-runtime');runtime.mkdir(mode=0o700,exist_ok=True);runtime.chmod(0o700)
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),LD_PRELOAD='/usr/lib/aarch64-linux-gnu/mali/wayland/libMali.so.9.0',
        QT_QPA_PLATFORM='eglfs',QT_QPA_EGLFS_INTEGRATION='eglfs_kms',QT_QPA_EGLFS_KMS_CONFIG=str(ROOT/'ui/kms.json'),
        QT_QPA_EGLFS_KMS_ATOMIC='0',QT_QPA_EGLFS_FORCE888='1',KV260_SCOPE_MODULE='surface',
        KV260_COMPLETE_SCENE=str(scene),OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8')
    for n in list(env):
        if n.startswith('KV260_') and (n.endswith('_TEST') or n.endswith('_UI_TEST')):env.pop(n)
    if test:env['KV260_SURFACE_QUALITY_UI_TEST']='1'
    return env

def launch(scene,test=False,old=False):
    out=OUT/('GUI' if test else 'review');out.mkdir(exist_ok=False)
    binary=ROOT/('ui/releases/feature_completion_r6/build_complete_scene_r15/medical_ui' if old else 'ui/releases/feature_completion_r6/build_complete_scene_r16/medical_ui')
    proof=json.loads((binary.parent/'build.json').read_text());assert sha(binary)==proof['binary_sha256']
    argv=[str(binary),'--root',str(ROOT),'--input',str(ROOT/'fixtures/own_ct/CT-chest.nrrd'),'--evidence',str(out)]
    with (out/'UI.log').open('xb') as log:p=subprocess.Popen(argv,cwd=ROOT,env=UI_environment(scene,test),
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    write_json(out/'started.json',dict(PID=p.pid,argv=argv,scene=str(scene),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),binary_sha256=sha(binary)))
    return p,out

def new_case():
    folder=OUT/'rotated_new_case';folder.mkdir();result=folder/'completed';seg=result/'segmentation';seg.mkdir(parents=True)
    z,y,x=np.indices((52,48,50));points=[]
    for zz in range(9,29):points.append((zz,24,25))
    for side in (-1,1):
        for zz in range(27,43):points.append((zz,24,25+side*(zz-27)*.65))
    airway=np.zeros(z.shape,bool)
    for zz,yy,xx in points:airway|=(z-zz)**2+(y-yy)**2+(x-xx)**2<3.6**2
    lung=((z-26)/24)**2+((y-24)/20)**2+((x-25)/22)**2<1
    nodule=(z-44)**2+(y-24)**2+(x-37)**2<2.3**2
    ct=sitk.GetImageFromArray(np.where(lung,-850,100).astype(np.int16));ct.SetOrigin((13.,-7.,5.))
    ct.SetDirection((0.,-1.,0.,1.,0.,0.,0.,0.,1.));ct.SetSpacing((1.,1.,1.))
    ct_path=folder/'different_CT.nrrd';sitk.WriteImage(ct,str(ct_path))
    for name,mask in [('lung',lung),('airway',airway),('nodule',nodule)]:
        image=sitk.GetImageFromArray(mask.astype(np.uint8));image.CopyInformation(ct);sitk.WriteImage(image,str(seg/(name+'_mask.nii.gz')))
    write_json(seg/'report.json',dict(status='completed',input_sha256=sha(ct_path),model_sha256='0'*64,synthetic_contract_fixture_not_model_accuracy=True))
    write_json(result/'pipeline.json',dict(status='passed',input_sha256=sha(ct_path),synthetic_contract_fixture_not_model_accuracy=True))
    from modules.navigation.navigation.pipeline import prepare
    prepare(seg/'airway_mask.nii.gz',result/'navigation',root_lps_mm=ct.TransformIndexToPhysicalPoint((25,24,11)))
    ct_array=sitk.GetArrayFromImage(ct);ct_array.astype('<f4').tofile(folder/'ct.f32')
    packed=lung.astype(np.uint8)|(airway.astype(np.uint8)<<1)|(nodule.astype(np.uint8)<<2);packed.tofile(folder/'masks.u8')
    from ui.features.analysis import candidates
    base=dict(schema='kv260.ui.scene.v1',input=str(ct_path),input_sha256=sha(ct_path),result=str(result),
        geometry=dict(size_xyz=list(ct.GetSize()),spacing_xyz=list(ct.GetSpacing()),origin_lps_mm=list(ct.GetOrigin()),direction=list(ct.GetDirection())),
        volume='ct.f32',masks='masks.u8',meshes={},navigation=None,candidates=candidates(nodule,ct),results=[],source='synthetic_completed_test')
    write_json(folder/'base.json',base)
    with VerificationSession():scene=produce(folder/'base.json',folder/'generated','accepted_binary','high',
        dict(lesion=0,diameter=1.,margin=.2,minimum_bend=0.))
    active=verify_active_scene(scene)
    assert active['input_sha256']==sha(ct_path) and active['input_sha256']!=sha(ROOT/'fixtures/own_ct/CT-chest.nrrd')
    assert active['complete_surface']['quality']['source']=='accepted_binary'
    assert active['geometry']['direction']==list(ct.GetDirection())
    assert active['navigation']['report']['target']['index']==0
    return dict(scene=str(scene),extraction=str(folder/'generated/extraction'),synthetic_not_accuracy_claim=True,
        changed_CT_path_and_geometry_without_own_case_names=True)

def topology_AB(folder,output):
    sys.path.insert(0,str(ROOT/'dfx/medical'));sys.path.insert(0,str(ROOT/'dfx/edt_volume'))
    from dfx.medical.prepare_inputs import mc_reference
    from runtime_extended import Session
    from volume_runtime import VolumeSession
    folder=Path(folder);output.mkdir();shape=tuple(map(int,(folder/'dimensions.txt').read_text().split()))[::-1]
    binary=np.fromfile(folder/'mask.u8',np.uint8).reshape(shape)
    expected=np.fromfile(folder/'vertices.u64','<u8')
    cuts=np.linspace(0,len(binary)-1,5,dtype=int)
    def threaded(pool):
        def work(pair):
            lo,hi=pair;w,_=mc_reference(np.ascontiguousarray(binary[lo:hi+1]));return w+(np.uint64(2*lo)<<np.uint64(32))
        return np.concatenate(list(pool.map(work,zip(cuts[:-1],cuts[1:]))))
    ps1=[];ps4=[];pl=[];records=[];before=Path.cwd()
    try:
        with VolumeSession(experimental=False) as lifecycle:lifecycle.return_to_scope()
        with ThreadPoolExecutor(4) as pool,Session() as session:
            for repeat in range(3):
                t=perf_counter();one,_=mc_reference(binary);ps1.append(perf_counter()-t)
                t=perf_counter();four=threaded(pool);ps4.append(perf_counter()-t)
                np.testing.assert_array_equal(one,expected);np.testing.assert_array_equal(four,expected)
                t=perf_counter();trial=session.run('mc',folder,output/f'PL_{repeat}.u64',output/f'PL_{repeat}.json');pl.append(perf_counter()-t)
                np.testing.assert_array_equal(np.fromfile(output/f'PL_{repeat}.u64','<u8'),expected);records.append(trial)
            session.echo();session.report(output/'session.json')
    finally:os.chdir(before)
    best=min(float(np.median(ps1)),float(np.median(ps4)));hardware=float(np.median(pl))
    receipt=dict(PS1_seconds=ps1,PS4_seconds=ps4,PL_seconds=pl,trials=records,all_words_exact=True,
        strongest_PS_median_seconds=best,PL_median_seconds=hardware,PL_over_strongest_PS_speedup=best/hardware,
        PS_scope='native same-algorithm extraction including output allocation/copy; four concurrent disjoint z-cell slabs, no duplicate cells',
        PL_scope='legacy full host API including file input/output, BO and partial selection; excludes common field preparation',
        test_oracle_only_not_production_fallback=True,reference_library_sha256=sha(ROOT/'dfx/medical/host/libmedical_reference.so'))
    write_json(output/'acceptance.json',receipt);return receipt

def main():
    OUT.mkdir(exist_ok=False);previous=None;candidate=None;review_restored=False
    checkpoint=json.loads((ROOT/'modules/surface_route/work_checkpoint_r15.json').read_text())
    state=checkpoint['current_board_state'];boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    try:
        assert boot==state['boot_id']
        for n,h in state['preserved_defaults_sha256'].items():assert sha(ROOT/n)==h,n
        with (OUT/'unit.log').open('xb') as log:subprocess.run([sys.executable,'-m','unittest','modules.surface_route.test_quality_action_r16','-v'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        subprocess.run([sys.executable,str(ROOT/'modules/surface_route/board_native_build_r16.py')],cwd=ROOT,check=True)
        previous=close_review()
        p,gui=launch(previous,test=True);code=p.wait();actual=json.loads((gui/'quality_UI.json').read_text())
        assert code==0 and actual['status'].startswith('passed_') and all(r['passed'] for r in actual['checks'])
        candidate=Path(actual['scene']);cases=[]
        for row in actual['trials']:
            scene=verify_active_scene(row['scene']);proof=Path(scene['complete_surface']['quality']['receipt']);info=json.loads(proof.read_text())
            cases.append(dict(source=info['source'],tier=info['tier'],scene=row['scene'],folder=str(proof.parent)))
        for source,tier in [('accepted_binary','high'),('network_probability','ultra')]:
            folder=OUT/(source+'_'+tier)
            with VerificationSession():path=produce(previous,folder,source,tier,dict(lesion=4,diameter=1.8,margin=.3,minimum_bend=0.))
            cases.append(dict(source=source,tier=tier,scene=str(path),folder=str(folder)))
        from modules.surface_route.original_surface_mesh_r6 import load_bound
        for row in cases:
            folder=Path(row['folder']);field=np.load(folder/'field/field.npz',allow_pickle=False)
            original=ROOT/f"modules/surface_quality/results/own_CT_board_r2/{row['source']}_{row['tier']}_ported/field.npz"
            with np.load(original,allow_pickle=False) as oracle:
                for name in field.files:np.testing.assert_array_equal(field[name],oracle[name])
            field.close();row['regenerated_all_field_arrays_exact_original']=True
            row['topology_AB']=topology_AB(folder/'extraction',OUT/(row['source']+'_'+row['tier']+'_AB'))
        generic=new_case();generic['topology_AB']=topology_AB(generic['extraction'],OUT/'generic_AB')
        from tools.active_surface_GUI_trial_r15 import replay
        replays=[]
        for i,row in enumerate(actual['trials']):
            folder=OUT/f'C9_replay_{i}';folder.mkdir();replays.append(replay(row,folder))
        for n,h in state['preserved_defaults_sha256'].items():assert sha(ROOT/n)==h,n
        assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        assert Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()==state['medical_shell_marker_sha256']
        write_json(OUT/'acceptance.json',dict(status='four_quality_regenerations_generic_case_actual_Qt_C1_and_C9_PS_PL_verified',
            cases=cases,generic=generic,actual_UI=actual,C9_replays=replays,boot_id=boot,production_promoted=False,
            new_bitstream=False,static_shell_reload=False,driver_unload=False,physical_user_review=False))
        p,review=launch(candidate);sleep(2);assert p.poll() is None;review_restored=True
        print('R16 complete quality trial passed; manual review PID',p.pid,flush=True)
    except BaseException as error:
        write_json(OUT/'failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise
    finally:
        if previous is not None and not review_restored:
            active=[]
            for p in Path('/proc').iterdir():
                try:
                    if p.name.isdigit() and (p/'comm').read_text().strip()=='medical_ui':active.append(int(p.name))
                except FileNotFoundError:pass
            if not active:
                p,review=launch(previous,old=True);print('Previous tested review restored',p.pid,flush=True)

if __name__=='__main__':main()
