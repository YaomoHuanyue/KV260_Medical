"""Actual B7 stage between closed C5 inference and PL reconstruction."""
from pathlib import Path
import argparse,hashlib,json,os,sys,time
from admission import ROOT,HERE,BINDING_SHA,verify,read,write,sha
sys.path[:0]=[str(ROOT),str(HERE.parent/'host_api_r1')]
from async_job import QualifiedBackend,RawVolume
def emit(text,**v):print(json.dumps(dict(event='progress',text=text,**v),ensure_ascii=False),flush=True)
def run(a):
    import numpy as np,SimpleITK as sitk
    from modules.image_import.partial_r1.importer import header,same_geometry
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1.entry import job_lock
    verify(a.admission,a.admission_sha256);ct=a.ct.resolve(strict=True);seg=a.segmentation.resolve(strict=True)
    if not ct.is_relative_to(ROOT)or not seg.is_relative_to(ROOT):raise ValueError('Complete-stage paths outside project')
    report=read(seg/'report.json');ct_sha=sha(ct)
    if(report.get('status')!='awaiting_PL_airway_cleanup'or report.get('input_sha256')!=ct_sha
       or report.get('PS_airway_CCL_executed')is not False or report.get('airway_cleanup_pending',{}).get('admission_SHA256')!=a.admission_sha256
       or report.get('qualified_original_firmware_restored')is not True or report.get('actual_C5_sessions')!=1):raise ValueError('Closed real C5 inference with deferred cleanup required')
    if report['airway_refinement'].get('policy')!='deferred_PL_B7':raise ValueError('PS cleanup was not deferred')
    _,geometry=header(ct);paths=[ct,seg/'report.json',seg/'deferred_worker_derivation.json']
    for name in ['lung','airway','nodule']:
        p=seg/(name+'_mask.nii.gz')
        if not same_geometry(header(p)[1],geometry):raise ValueError('Inference mask geometry differs')
    paths.extend(p for p in seg.iterdir()if p.is_file()and p.name not in ['status.json','report.json','deferred_worker_derivation.json'])
    bindings={str(p):sha(p)for p in paths};proof=seg.parent/'airway_cleanup'
    if proof.exists():raise ValueError('B7 stage requires a fresh output')
    proof.mkdir();write(proof/'input_bindings.json',bindings);write(proof/'deferred_inference_report.json',report)
    def unchanged():
        for p,h in bindings.items():
            if sha(p)!=h:raise ValueError('Inference/CT source changed during B7 cleanup')
    start=time.monotonic();raw=proof/'input.u8';image=sitk.ReadImage(str(seg/'airway_mask.nii.gz'));values=sitk.GetArrayViewFromImage(image)
    if not np.all((values==0)|(values==1)):raise ValueError('Nonbinary raw inference mask')
    np.asarray(values,dtype=np.uint8).tofile(raw);shape=tuple(values.shape)
    raw_sha=sha(raw);geometry_sha=hashlib.sha256(json.dumps(geometry,sort_keys=True).encode()).hexdigest()
    with job_lock(a.job_lock_fd):
        backend=QualifiedBackend(ROOT,HERE.parent/'runtime_binding.json',BINDING_SHA)
        job=backend.submit(RawVolume(raw,shape,raw_sha,ct_sha,geometry_sha,1));write(proof/'owner.json',dict(native_directory=str(job.directory),PID=job.process.pid));last=0;phase=None
        while True:
            if a.stop_file and a.stop_file.exists()and not job.stop_after_stage:job.request_stop_after_stage()
            s=job.status();now=time.monotonic()
            if s['phase']!=phase or now-last>2:
                emit('PL 气道清理：'+s['phase'],elapsed_seconds=now-start);write(seg/'status.json',dict(status='running',stage='PL_airway_cleanup',phase=s['phase'],elapsed_seconds=now-start));phase=s['phase'];last=now
            if s['phase']=='completed':break
            time.sleep(.05)
        verified=s['result'];unchanged();native=job.directory
        if native.parent!=ROOT/'results'or not native.name.startswith('airway_AXIS_')or job.process.poll()!=0:raise ValueError('Only completed owned native output may relocate')
        native.rename(proof/'native');write(proof/'native_relocation.json',dict(original=str(native),current=str(proof/'native'),three_done_idle=verified['PL']['all_three_done_idle'],C6_restored=verified['PL']['C6_restored']))
        result=proof/'native/mask.u8'
        if sha(result)!=verified['PL']['mask_SHA256']:raise ValueError('Relocated native output differs')
        output=np.memmap(result,mode='r',dtype=np.uint8,shape=shape);new=sitk.GetImageFromArray(output);new.CopyInformation(image)
        temp=proof/'airway_mask.nii.gz';sitk.WriteImage(new,str(temp),True)
        if not same_geometry(header(temp)[1],geometry):raise ValueError('Published B7 geometry differs')
        unchanged();temp.replace(seg/'airway_mask.nii.gz')
        # Original audit now consumes the final PL mask, not an uncleaned proxy.
        audit_seconds=0.;detail=dict(status='not_run_geometry_mismatch')
        from ui.features.airway_audit import audit_result
        logits=report.get('airway_logits');same_logits=False
        if logits:
            ref=sitk.ReadImage(str(ct));same_logits=all(np.allclose(getattr(ref,method)(),logits[key],atol=1e-6,rtol=0)for method,key in [('GetSize','size_xyz'),('GetSpacing','spacing_xyz_mm'),('GetOrigin','origin_xyz_mm'),('GetDirection','direction')])
        if logits and same_logits:
            tick=time.perf_counter();detail=audit_result(seg,ct,backend='ps');audit_seconds=time.perf_counter()-tick
        report.update(status='completed',airway_cleanup_pending=False,airway_cleanup=dict(backend='PL_B7_U8_AXIS',closing=1,verified_native=verified,mask_sha256=sha(seg/'airway_mask.nii.gz'),native_directory='airway_cleanup/native',silent_PS_fallback=False),
                      airway_refinement=dict(policy='PL_largest26_close6_fill6_largest26',input_voxels=verified['PL']['counters'][0],kept_voxels=verified['PL']['counters'][4],closing=1),airway_detail={k:v for k,v in detail.items()if k in ['status','policy','retained_components','added_voxels','mask_file','mask_sha256','default_mask_replaced','computation']})
        report['pl_operators']+='; B7 U8 AXIS whole-volume connected components, closing and hole fill'
        report['mask_foreground_voxels']['airway']=int(verified['PL']['counters'][4])
        report['ps_operators']+=', sparse discarded-candidate audit after PL cleanup'
        report['operator_assignment']['PL'].append('B7 whole-volume airway connected components/closing/hole fill over raw U8 AXIS')
        report['operator_assignment']['PS'].append('sparse discarded-candidate audit after PL cleanup')
        report['postprocess_seconds']=verified['PL']['hardware_seconds']+audit_seconds
        report['median_inference_and_postprocess_seconds']=report['median_inference_seconds']+report['postprocess_seconds']
        report['airway_cleanup_wall_seconds']=time.monotonic()-start
        report['postprocess_timing_scope']='B7 hardware plus PS sparse audit; DFX/file/verification overhead included in airway_cleanup_wall_seconds'
        report['segmentation_with_cleanup_stage_wall_seconds']=report['stage_wall_seconds']+report['airway_cleanup_wall_seconds']
        report['airway_cleanup_stopped_after_current_stage']=job.stop_after_stage
        write(seg/'report.json',report);write(proof/'verified.json',dict(passed=True,result=verified,post_PL_audit_seconds=audit_seconds,no_PS_airway_CCL=True))
        write(seg/'status.json',dict(status='completed',stage='PL_airway_cleanup',C6_restored=True));emit('PL 气道清理完成，已返回 C6')
def main():
    p=argparse.ArgumentParser();p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);p.add_argument('--ct',type=Path,required=True);p.add_argument('--segmentation',type=Path,required=True);p.add_argument('--job-lock-fd',type=int);p.add_argument('--stop-file',type=Path);run(p.parse_args())
if __name__=='__main__':main()
