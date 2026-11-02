"""Isolated integration tests, using actual D6/C5 and original medical stages."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1')
W=Path(__file__).resolve().parent;ROOT=W.parent.parent
assert W.parent==ROOT/'results' and W.name.startswith('owned_mixed_r30_')
sys.path.insert(0,str(ROOT))
from formal_guard import formal
from modules.segmentation.mixed_r30 import backend
from modules.segmentation.mixed_r30.admission import sha,read,verify

def save(p,v):
    with Path(p).open('x') as f:json.dump(v,f,indent=2)
def array_info(path):
    import numpy as np,SimpleITK as sitk
    path=Path(path)
    if path.suffix=='.npy':a=np.load(path,mmap_mode='r',allow_pickle=False);geometry=None
    else:
        image=sitk.ReadImage(str(path));a=sitk.GetArrayViewFromImage(image)
        geometry=dict(size=list(image.GetSize()),spacing=list(image.GetSpacing()),origin=list(image.GetOrigin()),direction=list(image.GetDirection()))
    return dict(shape=list(a.shape),dtype=str(a.dtype),array_SHA256=hashlib.sha256(memoryview(np.ascontiguousarray(a)).cast('B')).hexdigest(),geometry=geometry)

def main(name):
    import numpy as np,SimpleITK as sitk
    p=read(W/'plan.json');assert formal()==p['formal_before']
    module=ROOT/p['module'];admission=module/'candidate.json';verify(admission,p['admission_SHA256'])
    before={v:sha(ROOT/v) for v in p['firmware_paths']}
    before['/usr/lib/firmware/medical_ct_partial.bin']=sha(Path('/usr/lib/firmware/medical_ct_partial.bin'))
    expected=['lung_mask.nii.gz','airway_mask.nii.gz','nodule_mask.nii.gz','airway_mask_network.nii.gz','airway_mask_detail.nii.gz','airway_logits.npy']
    baseline=ROOT/p['baseline_segmentation']
    source=ROOT/'fixtures/own_ct/CT-chest.nrrd';assert sha(source)==p['CT_SHA256']
    fixture=W/'fixture';fixture.mkdir(exist_ok=True)
    if name=='partial7':
        image=sitk.ReadImage(str(source));small=image[:,:,66:73];ct=fixture/'CT7.nrrd';sitk.WriteImage(small,str(ct),True)
    else:ct=source
    work=W/name;work.mkdir();runs=work/'runs';runs.mkdir()
    # The parent's inherited implementation is verified before a job is started.
    # This phase neither submits a native kernel nor constructs an XRT backend.
    configured=backend.install(admission,p['admission_SHA256'],runs,1)
    save(work/'dispatch_derivation.json',configured.hybrid_dispatch_derivation)
    from modules.segmentation.mixed_r30.segmentation import derive
    _,_,_,derivation=derive();save(work/'segmentation_derivation.json',derivation)
    # Missing/incorrect identity must refuse before candidate dispatch.
    try:verify(admission,'0'*64)
    except ValueError:pass
    else:raise AssertionError('Wrong candidate SHA accepted')
    mode='segmentation' if name=='partial7' else 'all'
    args=[str(ROOT/'.venv/bin/python'),'-B',str(module/'backend.py'),'--admission',str(admission),
          '--admission-sha256',p['admission_SHA256'],'--run-parent',str(runs),'run','--input',str(ct),'--mode',mode]
    start=time.monotonic();peak=0
    with (work/'pipeline.stdout').open('xb') as out,(work/'pipeline.stderr').open('xb') as err:
        child=subprocess.Popen(args,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
        ticks=int((Path('/proc')/str(child.pid)/'stat').read_text().rsplit(')',1)[1].split()[19])
        save(work/'child.json',dict(PID=child.pid,ticks=ticks,argv=args))
        while child.poll() is None:
            try:
                for line in (Path('/proc')/str(child.pid)/'status').read_text().splitlines():
                    if line.startswith('VmHWM:'):peak=max(peak,int(line.split()[1])*1024)
            except FileNotFoundError:pass
            temp=work/'state.pending';temp.write_text(json.dumps(dict(seconds=time.monotonic()-start,child_PID=child.pid,child_ticks=ticks,controller_RSS_peak_bytes=peak,no_forced_cancel=True)));temp.replace(work/'state.json');time.sleep(.25)
        rc=child.wait()
    terminal=dict(exit_code=rc,wall_seconds=time.monotonic()-start,passed=False,case=name,formal=formal(),production_promoted=False)
    assert formal()==p['formal_before']
    for v,digest in before.items():assert sha(Path(v) if v.startswith('/') else ROOT/v)==digest
    save(work/'firmware_restored.json',dict(passed=True,before_after_SHA256=before))
    if rc!=0:
        terminal['stderr']=(work/'pipeline.stderr').read_text()[-5000:];return terminal
    folders=list(runs.iterdir());assert len(folders)==1;run=folders[0];pipeline=read(run/'pipeline.json')
    assert pipeline['status']=='passed' and pipeline['explicit_hybrid'] and pipeline['PL_cleanup_mandatory'] is False
    stages=[v['stage'] for v in pipeline['stages']]
    assert stages==(['segmentation','airway-cleanup'] if mode=='segmentation' else ['segmentation','airway-cleanup','reconstruction','navigation'])
    report=read(run/'segmentation/report.json');slices=7 if mode=='segmentation' else 139
    assert report['pl_conv_calls']==18*(1+slices) and report['pl_pool_calls']==report['pl_reader_calls']==0
    assert report['PS_airway_CCL_executed'] and report['airway_cleanup']['explicitly_selected'] and report['airway_cleanup']['PL_cleanup_invoked'] is False
    assert report['airway_cleanup']['backend']=='PS_original_clean_mask' and report['silent_PS_fallback'] is False
    assert report['actual_C5_sessions']==1 and report['qualified_original_firmware_restored']
    if mode=='all':
        pairs={}
        for filename in expected:
            actual=array_info(run/'segmentation'/filename);reference=array_info(baseline/filename)
            assert actual==reference,filename;pairs[filename]=actual
        assert report['airway_cleanup']['input_uint8_array_SHA256']=='67ac1ae360d20ba599a6b9529d10dd586b5c83099c68dec1700bff83dcf97fb9'
        assert report['airway_cleanup']['output_uint8_array_SHA256']=='c0e321d1030ba0a2145344459c76b7bc7064378bbfc4e915706ea4ad8378c9a2'
        save(work/'six_original_output_arrays_exact.json',dict(passed=True,files=pairs,baseline=str(baseline)))
        terminal['all6_original_output_arrays_exact']=True
    terminal.update(passed=True,pipeline=pipeline,segmentation_report=report,run_directory=str(run),
                    controller_peak_RSS_bytes=peak,no_new_FPGA_build=True,firmware_restored=True)
    return terminal

if __name__=='__main__':
    name=sys.argv[1];assert name in ['partial7','full139']
    try:value=main(name)
    except BaseException as e:save(W/(name+'.failure.json'),dict(error=repr(e),automatic_retry=False));raise
    save(W/(name+'.terminal.json'),value);print(json.dumps(dict(case=name,passed=value['passed'],exit_code=value['exit_code'],wall_seconds=value['wall_seconds'])),flush=True)
