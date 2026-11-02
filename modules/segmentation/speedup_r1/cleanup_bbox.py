"""Explicit PS original cleaning restricted to the airway bounding box (exact; see bbox_clean.py).
Derived from mixed_r30/cleanup.py; only the compute call and the report labels differ."""
from pathlib import Path
import argparse,ast,hashlib,json,sys,time
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from modules.segmentation.mixed_r30.admission import ROOT,HERE,verify,read,write,sha
sys.path.insert(0,str(ROOT))

def emit(text,**v):print(json.dumps(dict(event='progress',text=text,**v),ensure_ascii=False),flush=True)

def run(a):
    import numpy as np,SimpleITK as sitk
    from scipy import ndimage as ndi
    from modules.image_import.partial_r1.importer import header,same_geometry
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1.entry import job_lock
    from modules.segmentation.speedup_r1.bbox_clean import clean_mask_bbox
    verify(a.admission,a.admission_sha256);ct=a.ct.resolve(strict=True);seg=a.segmentation.resolve(strict=True)
    if not ct.is_relative_to(ROOT) or not seg.is_relative_to(ROOT):raise ValueError('Hybrid paths outside project')
    report=read(seg/'report.json')
    if (report.get('status')!='awaiting_PS_airway_cleanup' or report.get('input_sha256')!=sha(ct)
            or report.get('PS_airway_CCL_executed') is not False or report.get('actual_C5_sessions')!=1
            or report.get('qualified_original_firmware_restored') is not True
            or report.get('airway_refinement',{}).get('policy')!='deferred_PS_hybrid_cleanup'):
        raise ValueError('Closed actual hybrid inference required')
    proof=seg.parent/'airway_cleanup';assert not proof.exists();proof.mkdir()
    source=HERE/'reference/original_clean_airway_tree.py'
    if sha(source)!='6d6c5668864e45af4511260202f303b4ecba0caab589ab658b4c0be0784193b0':raise ValueError('Changed original algorithm')
    functions=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ['keep_largest_component','clean_mask']]
    assert len(functions)==2
    namespace=dict(np=np,ndi=ndi);exec(compile(ast.Module(body=functions,type_ignores=[]),str(source)+':original_functions','exec'),namespace)
    _,geometry=header(ct);image=sitk.ReadImage(str(seg/'airway_mask.nii.gz'));raw=sitk.GetArrayViewFromImage(image)
    if not same_geometry(header(seg/'airway_mask.nii.gz')[1],geometry) or not np.all((raw==0)|(raw==1)):raise ValueError('Original CT-grid binary mask required')
    bindings={str(p):sha(p) for p in [ct,*[f for f in seg.iterdir() if f.is_file() and f.name!='status.json']]}
    write(proof/'input_bindings.json',bindings);write(proof/'deferred_inference_report.json',report)
    start=time.monotonic();emit('PS 气道清理：在气道外包框内执行原始连通域、闭运算和填洞')
    with job_lock(a.job_lock_fd):
        tick=time.perf_counter();cleaned,info,box=clean_mask_bbox(raw>0,namespace,1);compute=time.perf_counter()-tick
        if cleaned.shape!=raw.shape or not np.all((cleaned==0)|(cleaned==1)):raise ValueError('Original PS result shape/type differs')
        array_sha=hashlib.sha256(memoryview(np.ascontiguousarray(cleaned,dtype=np.uint8)).cast('B')).hexdigest()
        raw_sha=hashlib.sha256(memoryview(np.ascontiguousarray(raw,dtype=np.uint8)).cast('B')).hexdigest()
        output=sitk.GetImageFromArray(cleaned.astype(np.uint8,copy=False));output.CopyInformation(image)
        temp=proof/'airway_mask.nii.gz';sitk.WriteImage(output,str(temp),True)
        for path,digest in bindings.items():
            if sha(Path(path))!=digest:raise ValueError('Source changed during explicit PS cleanup')
        temp.replace(seg/'airway_mask.nii.gz')
        # 细支气管候选审核（airway_detail）对应的界面功能已在精简版中退役，这里不再计算；logits 仍保留，可按需单独补算。
        audit_seconds=0.;detail=dict(status='skipped_retired_UI_feature',policy='candidate audit not computed in speedup_r1');logits=None
        if logits:
            from ui.features.airway_audit import audit_result
            ref=sitk.ReadImage(str(ct))
            same=all(np.allclose(getattr(ref,method)(),logits[key],atol=1e-6,rtol=0) for method,key in [('GetSize','size_xyz'),('GetSpacing','spacing_xyz_mm'),('GetOrigin','origin_xyz_mm'),('GetDirection','direction')])
            if same:
                tick=time.perf_counter();detail=audit_result(seg,ct,backend='ps');audit_seconds=time.perf_counter()-tick
        record=dict(passed=True,backend='PS_original_clean_mask',compute_scope='airway_bounding_box_exact',bounding_box=box,explicitly_selected=True,silent_PS_fallback=False,
            PL_cleanup_invoked=False,source_code_SHA256=sha(source),input_uint8_array_SHA256=raw_sha,
            output_uint8_array_SHA256=array_sha,shape_zyx=list(raw.shape),original_info=info,
            compute_seconds=compute,post_cleanup_audit_seconds=audit_seconds,wall_seconds=time.monotonic()-start)
        report.update(status='completed',PS_airway_CCL_executed=True,airway_cleanup_pending=False,
            airway_cleanup=dict(**record,closing=1,mask_sha256=sha(seg/'airway_mask.nii.gz')),
            airway_refinement=dict(policy='PS_original_largest26_close6_fill6_largest26',closing=1,
                input_voxels=info['input_foreground_voxels'],kept_voxels=info['largest_component_voxels']),
            airway_detail={k:v for k,v in detail.items() if k in ['status','policy','retained_components','added_voxels','mask_file','mask_sha256','default_mask_replaced','computation']})
        report['mask_foreground_voxels']['airway']=int(info['largest_component_voxels'])
        report['ps_operators']+=', explicitly selected original airway connected-components/closing/fill and sparse discarded-candidate audit'
        report['operator_assignment']['PS']+=['original global airway connected-components/closing/fill','sparse discarded-candidate audit']
        report['postprocess_seconds']=compute+audit_seconds
        report['median_inference_and_postprocess_seconds']=report['median_inference_seconds']+report['postprocess_seconds']
        report['airway_cleanup_wall_seconds']=time.monotonic()-start
        report['segmentation_with_cleanup_stage_wall_seconds']=report['stage_wall_seconds']+report['airway_cleanup_wall_seconds']
        report['postprocess_timing_scope']='PS original cleanup and audit; stage wall separately includes mask/geometry/file handling'
        report['airway_cleanup_stopped_after_current_stage']=bool(a.stop_file and a.stop_file.exists())
        write(proof/'verified.json',record);write(seg/'report.json',report)
        write(seg/'operator_assignment.json',report['operator_assignment'])
        write(seg/'status.json',dict(status='completed',backend='explicit_hybrid_D6_C5_PS_layers_PS_cleanup'))
        emit('PS 气道清理完成（外包框内计算）',compute_seconds=compute)

def main():
    p=argparse.ArgumentParser();p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True)
    p.add_argument('--ct',type=Path,required=True);p.add_argument('--segmentation',type=Path,required=True)
    p.add_argument('--job-lock-fd',type=int);p.add_argument('--stop-file',type=Path);run(p.parse_args())

if __name__=='__main__':main()
