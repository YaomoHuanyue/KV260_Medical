"""Native-system B7 stage: immutable source -> PL cleanup -> new mask result.

PS performs file/geometry validation and publication. There is no CPU cleaning
provider. Existing meshes/navigation are intentionally not copied into a result
whose airway changed: the existing PL rebuild/replan actions consume this result.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,sys,time,uuid
HERE=Path(__file__).resolve().parent;MODULE=HERE.parent;ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT),str(MODULE/'host_api_r1')]
from async_job import QualifiedBackend,RawVolume,PLBackendError

def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,value):
    tmp=Path(str(p)+'.new');tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n');tmp.replace(p)
def emit(event,**values):print(json.dumps(dict(event=event,**values),ensure_ascii=False),flush=True)
def stopped(path):return path is not None and Path(path).exists()
def inside(p):
    p=Path(p).resolve(strict=True)
    if not p.is_relative_to(ROOT):raise ValueError('Input must belong to the integrated project')
    return p

def admission(ct,source,selection):
    from modules.image_import.partial_r1.importer import header,same_geometry
    from modules.image_import.partial_r1.contracts import validate_source,validate_selected_masks
    ct=inside(ct);source=inside(source);ct_sha=sha(ct);pipeline=read(source/'pipeline.json')
    if pipeline.get('status')!='passed'or pipeline.get('input_sha256')!=ct_sha:raise ValueError('Result does not belong to selected CT')
    _,geometry=header(ct);partial=validate_source(ct,source)
    if partial:validate_selected_masks(ct,source)
    segmentation=source/'segmentation';original=read(segmentation/'report.json')
    if original.get('status')!='completed'or original.get('input_sha256')!=ct_sha:raise ValueError('Incomplete/foreign segmentation report')
    names=[n for n in ['lung','airway','nodule']if(segmentation/(n+'_mask.nii.gz')).is_file()]
    if 'airway'not in names:raise ValueError('Current result has not provided an airway mask')
    selected=segmentation/('airway_mask_network.nii.gz'if selection=='network'else'airway_mask.nii.gz')
    if not selected.is_file():raise ValueError('Selected airway source was not provided; no implicit fallback')
    files={p.name:p for p in segmentation.iterdir()if p.is_file()}
    for name in names:
        _,g=header(files[name+'_mask.nii.gz'])
        if not same_geometry(g,geometry):raise ValueError('Mask geometry differs from CT')
    _,g=header(selected)
    if not same_geometry(g,geometry):raise ValueError('Selected airway geometry differs from CT')
    bindings={str(p):sha(p)for p in [ct,source/'pipeline.json',*files.values()]}
    return dict(ct=ct,source=source,ct_sha=ct_sha,geometry=geometry,names=names,selected=selected,files=files,bindings=bindings,original=original,partial=partial)

def unchanged(context):
    for p,h in context['bindings'].items():
        if sha(p)!=h:raise ValueError('Selected CT/result changed during PL operation')

def publish(context,pending,verified,selection,closing):
    """File adapter only; consumes actual verified native output, never an oracle."""
    import numpy as np
    import SimpleITK as sitk
    from modules.image_import.partial_r1.importer import geometry,same_geometry
    p=Path(verified['mask']);shape=tuple(reversed(context['geometry']['size_xyz']))
    pl=verified['PL']
    if(verified.get('backend')!='PL_B7_U8_AXIS'or verified.get('silent_PS_fallback')is not False
       or verified.get('CT_SHA256')!=context['ct_sha']or tuple(verified.get('shape_zyx',()))!=shape
       or verified.get('geometry_SHA256')!=hashlib.sha256(json.dumps(context['geometry'],sort_keys=True).encode()).hexdigest()
       or not all(pl.get(k)is True for k in ['passed','C6_restored','all_three_done_idle','guard_bytes_verified'])
       or verified.get('source_SHA256')!=context.get('raw_sha')
       or p.stat().st_size!=__import__('math').prod(shape)
       or sha(p)!=pl.get('mask_SHA256')):raise ValueError('Unverified or foreign B7 output cannot be published')
    if verified.get('outcome')!='mask_ready':raise ValueError('PL cleanup produced no airway: '+str(verified.get('outcome')))
    unchanged(context);seg=Path(pending)/'segmentation';seg.mkdir();proof=Path(pending)/'airway_cleanup';proof.mkdir()
    # Preserve scalar inference provenance and original auxiliary images; no
    # source file, probability map, lung or lesion data may be replaced in place.
    invalidated=['airway_mask_detail.nii.gz','airway_detail_report.json']
    for name,source in context['files'].items():
        if name not in ['report.json','airway_mask.nii.gz',*invalidated]:
            shutil.copy2(source,seg/name)
            if sha(seg/name)!=context['bindings'][str(source)]:raise ValueError('Copied source artifact differs')
    shutil.copy2(context['files']['report.json'],proof/'source_segmentation_report.json')
    shutil.copy2(context['selected'],proof/'input_mask.nii.gz')
    if(context['source']/'external_import.json').is_file():shutil.copy2(context['source']/'external_import.json',proof/'source_external_import.json')
    values=np.memmap(p,dtype=np.uint8,mode='r',shape=shape);image=sitk.GetImageFromArray(values)
    reference=sitk.ReadImage(str(context['selected']));image.CopyInformation(reference);sitk.WriteImage(image,str(seg/'airway_mask.nii.gz'),True)
    if not same_geometry(geometry(image),context['geometry']):raise ValueError('Published output changed geometry')
    original=context['original'];report=json.loads(json.dumps(original));report.update(fresh_inference=False,derived_PL_airway_cleanup=True,invalidated_derived_artifacts=[n for n in invalidated if n in context['files']])
    report['airway_cleanup']=dict(backend='PL_B7_U8_AXIS',selection=selection,closing=closing,source_mask_file=context['selected'].name,source_mask_sha256=context['bindings'][str(context['selected'])],source_report_sha256=context['bindings'][str(context['files']['report.json'])],output_mask_sha256=sha(seg/'airway_mask.nii.gz'),verified_native=verified)
    if context['partial']:
        report['files']['segmentation/airway_mask.nii.gz']=sha(seg/'airway_mask.nii.gz')
        report['images']['airway']['foreground_voxels']=int(pl['counters'][4])
        report['images']['airway']['postprocessing']=report['airway_cleanup']
        report['morphology_or_synthetic_bridges']=True
    else:
        # Old model-agreement numbers belong to the immutable source report;
        # do not label them as measurements of the newly postprocessed mask.
        report.pop('agreement_with_onnx',None)
        report['current_mask_files_SHA256']={n+'_mask.nii.gz':sha(seg/(n+'_mask.nii.gz'))for n in context['names']}
    write(seg/'report.json',report);write(proof/'verified_PL.json',verified)
    for name in context['names']:
        if name!='airway'and sha(seg/(name+'_mask.nii.gz'))!=context['bindings'][str(context['files'][name+'_mask.nii.gz'])]:raise ValueError('Unselected structure changed')
    unchanged(context);return report

def run(ct,source,selection,closing,stop_file,binding,binding_sha):
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1.entry import job_lock
    if type(closing)is not int or not -2147483648<=closing<=2147483647:raise ValueError('Closing count must fit signed32')
    with job_lock():
        emit('progress',text='校验当前 CT 和气道来源')
        context=admission(ct,source,selection);runs=ROOT/'ui/runs';runs.mkdir(exist_ok=True)
        output=runs/('airway_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]);pending=output.with_name(output.name+'.cleanup');pending.mkdir()
        start=time.monotonic();base=dict(schema='kv260.ui.pipeline.v1',status='running',backend='dfx_pl',mode='airway-cleanup',input=str(context['ct']),input_sha256=context['ct_sha'],source_result=str(context['source']),stages=[],silent_PS_fallback=False,new_reconstruction_or_navigation=False)
        if context['partial']:base.update(available_structures=context['names'],unavailable_structures=[n for n in ['lung','airway','nodule']if n not in context['names']])
        emit('started',output=str(output),text='PL 气道清理；保留当前病例直到新结果完成')
        try:
            if stopped(stop_file):
                write(pending/'pipeline.json',dict(base,status='stopped'));emit('completed',output=str(pending),status='stopped');return
            import numpy as np
            import SimpleITK as sitk
            image=sitk.ReadImage(str(context['selected']));a=sitk.GetArrayViewFromImage(image)
            if not np.all((a==0)|(a==1)):raise ValueError('Airway source must be binary; probability requires prior explicit thresholding')
            raw=pending/'input.u8';np.asarray(a,dtype=np.uint8).tofile(raw)
            geometry_sha=hashlib.sha256(json.dumps(context['geometry'],sort_keys=True).encode()).hexdigest();context['raw_sha']=sha(raw)
            backend=QualifiedBackend(ROOT,binding,binding_sha);descriptor=RawVolume(raw,tuple(a.shape),context['raw_sha'],context['ct_sha'],geometry_sha,closing)
            emit('stage',stage='airway-cleanup',index=0,count=1,text='PL 连通域 / 闭运算 / 填洞；整幅处理可能较久')
            job=backend.submit(descriptor);write(pending/'native_job.json',dict(directory=str(job.directory),PID=job.process.pid))
            previous=None;last=0
            while True:
                if stopped(stop_file)and not job.stop_after_stage:job.request_stop_after_stage()
                status=job.status();now=time.monotonic()
                if status['phase']!=previous or now-last>=2:
                    text={'preparing':'准备体数据和 DFX 模块','running_PL':'PL 正在处理整幅气道','verifying_output':'正在校验完成结果','retained_fault':'PL 异常，缓冲区保留，等待安全恢复','completed':'PL 清理已完成'}[status['phase']]
                    emit('progress',text=text,elapsed_seconds=now-start);previous=status['phase'];last=now
                if status['phase']=='completed':break
                time.sleep(.05)
            verified=status['result'];report=publish(context,pending,verified,selection,closing)
            base.update(status='passed',total_wall_seconds=time.monotonic()-start,stages=[dict(stage='airway-cleanup',backend='PL_B7_U8_AXIS',wall_seconds=time.monotonic()-start)],stopped_after_current_stage=job.stop_after_stage,prior_meshes_and_navigation_invalidated=True)
            if context['partial']:base['external_segmentation_report_sha256']=sha(pending/'segmentation/report.json')
            write(pending/'pipeline.json',base);unchanged(context)
            raw.unlink();pending.rename(output)
            emit('stage_done',stage='airway-cleanup',seconds=base['total_wall_seconds'])
            emit('completed',output=str(output),status='passed',seconds=base['total_wall_seconds'],stopped_after_current_stage=job.stop_after_stage)
        except BaseException as e:
            write(pending/'failure.json',dict(error=str(e),input_sha256=context['ct_sha'],accepted_source_changed=False));raise

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['run']);p.add_argument('--mode',choices=['airway-cleanup'],required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--result',type=Path,required=True);p.add_argument('--selection',choices=['current','network'],default='current');p.add_argument('--closing',type=int,default=1);p.add_argument('--stop-file',type=Path);p.add_argument('--binding',type=Path,required=True);p.add_argument('--binding-sha256',required=True);a=p.parse_args()
    run(a.input,a.result,a.selection,a.closing,a.stop_file,a.binding,a.binding_sha256)
if __name__=='__main__':
    try:main()
    except Exception as e:emit('error',text=str(e));sys.exit(1)
