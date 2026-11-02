"""Native CT recovery review attached to an immutable current surface scene.

Recovery proposals remain review overlays. They never replace the C1 mesh,
C9 scalar field, accepted masks, route, camera or guidance.
"""
from pathlib import Path
from time import perf_counter
import copy,json,os,shutil,tempfile
import numpy as np
import SimpleITK as sitk
from modules.surface_route.bundle_r8 import write_json
from modules.surface_route.verification_session_r15 import sha
from modules.surface_route.quality_validation_r16 import verify_active_scene as verify_surface
from modules.surface_route.ui_bridge_r9 import asset_path,ROOT
from modules.airway_detail.case_io import load_inputs,save_outputs,geometry
from modules.airway_detail.recovery import recover_distal_components
from ui.features.airway_audit import validate_geometry

OUTPUTS={'experimental_merged.nii.gz','high.nii.gz','review.nii.gz','evidence.nii.gz'}

def validate_review(scene,binding):
    report_path=asset_path(ROOT,binding['report']);report=json.loads(report_path.read_text(encoding='utf-8'))
    if (sha(report_path)!=binding['report_sha256'] or report!=scene.get('distal_recovery') or
        report.get('schema')!='kv260.airway_detail.recovery.v1' or report.get('status')!='completed' or
        report.get('input_sha256')!=scene['input_sha256'] or report.get('accepted_mask_changed') is not False or
        report.get('default_reconstruction_navigation_mask_replaced') is not False or set(report['files'])!=OUTPUTS or
        binding['scope']!='native_CT_network_fragment_review_only' or binding['model_navigation_replaced'] is not False):
        raise ValueError('Mixed recovery review, current CT or accepted model')
    source=Path(scene['result']).resolve();ct=Path(scene['input']).resolve()
    g=scene['geometry'];expected_geometry=dict(size_xyz=g['size_xyz'],spacing_xyz_mm=g['spacing_xyz'],
        origin_lps_mm=g['origin_lps_mm'],direction=g['direction'])
    if set(report['geometry'])!=set(expected_geometry) or any(not np.allclose(report['geometry'][k],v,rtol=0,atol=1e-6) for k,v in expected_geometry.items()):
        raise ValueError('Recovery geometry differs from current CT')
    expected={str(ct)}|{str(source/'segmentation'/n) for n in ('report.json','airway_logits.json','airway_logits.npy',
        'airway_mask_network.nii.gz','airway_mask.nii.gz','nodule_mask.nii.gz')}
    if set(report['inputs_sha256'])!=expected:raise ValueError('Recovery input set differs from selected segmentation')
    for n,h in report['inputs_sha256'].items():
        if sha(asset_path(ROOT,n))!=h:raise ValueError('Changed recovery input: '+n)
    if binding['target_index']!=report['candidate_index_zero_based']:raise ValueError('Mixed recovery target')
    candidates=[c for c in scene['candidates'] if c['index']==binding['target_index']]
    if len(candidates)!=1 or candidates[0]['voxel_count']!=report['candidate_voxels']:raise ValueError('Recovery candidate differs from CT catalogue')
    for n,h in report['files'].items():
        if sha(report_path.parent/n)!=h or binding['outputs_sha256'].get(str(report_path.parent/n))!=h:
            raise ValueError('Changed recovery output: '+n)
    if len(binding['outputs_sha256'])!=4:raise ValueError('Unexpected recovery output binding')
    return report

def verify_active_scene(path):
    scene=verify_surface(path);binding=scene.get('distal_recovery_binding')
    if binding is not None:validate_review(scene,binding)
    return scene

def append_masks(packed,image,report,folder):
    for name in sorted(OUTPUTS):
        other=sitk.ReadImage(str(folder/name));validate_geometry(image,other);values=sitk.GetArrayViewFromImage(other)
        if name=='evidence.nii.gz':
            if not np.isfinite(values).all() or values.min()<0 or values.max()>1:raise ValueError('Invalid recovery evidence range')
            continue
        if np.any((values!=0)&(values!=1)):raise ValueError('Nonbinary recovery mask')
        bit={'high.nii.gz':32,'review.nii.gz':64,'experimental_merged.nii.gz':128}[name]
        for z in range(len(values)):
            selected=values[z]>0
            if bit==32:selected=selected|((packed[z]&2)>0)
            packed[z]|=selected.astype(np.uint8)*bit

def produce(active_path,output,target,event=lambda *a,**k:None):
    begin=perf_counter();active_path=Path(active_path).resolve();output=Path(output).resolve()
    if output.exists() or not output.is_relative_to(ROOT/'ui/cache'):raise ValueError('Fresh UI-cache action output required')
    scene=verify_active_scene(active_path);prepared=json.loads((active_path.parent/'prepared.json').read_text(encoding='utf-8'))
    if type(target)is not int or target not in [c['index'] for c in scene['candidates']]:raise ValueError('Explicit current candidate required')
    output.mkdir(exist_ok=False);event('progress',text='正在审核所选目标附近的原始 CT、网络碎片及连接证据')
    image,ct,airway,lesion,probability,identity=load_inputs(scene['input'],Path(scene['result'])/'segmentation',target)
    if identity['input_sha256']!=scene['input_sha256']:raise ValueError('Recovery CT differs from current scene')
    results=recover_distal_components(airway,ct,lesion,image.GetSpacing(),probability)
    source_names=['modules/airway_detail/'+n for n in ['active_scene_r20.py','case_io.py','recovery.py','evidence.py']]
    report=save_outputs(output/'recovery',image,results,identity,perf_counter()-begin,{n:sha(ROOT/n) for n in source_names})
    del results,ct,airway,lesion,probability
    binding=dict(schema='kv260.active_recovery_review.v1',report=str(output/'recovery/report.json'),
        report_sha256=sha(output/'recovery/report.json'),outputs_sha256={str(output/'recovery'/n):h for n,h in report['files'].items()},
        target_index=target,scope='native_CT_network_fragment_review_only',model_navigation_replaced=False,
        display_at_generation={k:scene['complete_surface'][k] for k in ('bundle','revision','route_id','scalar_sha256')},
        source_scene=str(active_path),source_scene_sha256=sha(active_path))
    final=output/'UI';stage=Path(tempfile.mkdtemp(prefix='.UI-',dir=output));next_scene=copy.deepcopy(scene)
    try:
        original=np.memmap(asset_path(active_path.parent,scene['masks']),np.uint8,'r',shape=tuple(image.GetSize()[::-1]))
        packed=np.memmap(stage/'masks.u8',np.uint8,'w+',shape=original.shape)
        # Remove only prior review layers before publishing a new review.
        for z in range(len(original)):packed[z]=original[z]&31
        append_masks(packed,image,report,output/'recovery')
        for z in range(len(original)):
            if not np.array_equal(packed[z]&31,original[z]&31):raise ValueError('Accepted/native mask bits changed')
        packed.flush();del packed,original
        attribute=asset_path(active_path.parent,scene['meshes']['airway']['attributes']['file'])
        shutil.copyfile(attribute,stage/'airway.attributes')
        next_scene['meshes']['airway']['attributes']['file']=str(final/'airway.attributes')
        next_scene['masks']=str(final/'masks.u8');next_scene['distal_recovery']=report;next_scene['distal_recovery_binding']=binding
        next_scene.setdefault('airway_masks',{}).update(recovery_high=dict(bit=32),recovery_review=dict(bit=64),recovery_experimental=dict(bit=128))
        write_json(stage/'scene.json',next_scene)
        next_prepared=copy.deepcopy(prepared);next_prepared.update(base_scene=str(active_path),base_scene_sha256=sha(active_path),
            output_sha256={n:sha(stage/n) for n in ('scene.json','airway.attributes')},recovery_review=binding,
            recovery_producer_source_sha256=sha(Path(__file__)),total_seconds=perf_counter()-begin)
        next_prepared['retained_assets_sha256'][str(final/'masks.u8')]=sha(stage/'masks.u8')
        for n,h in {str(output/'recovery/report.json'):binding['report_sha256'],**binding['outputs_sha256'],**report['inputs_sha256']}.items():
            next_prepared['case_files_sha256'][Path(n).relative_to(ROOT).as_posix()]=h
        write_json(stage/'prepared.json',next_prepared);os.rename(stage,final)
    finally:
        if stage.exists():
            assert stage.parent==output and stage.name.startswith('.UI-');shutil.rmtree(stage)
    result=verify_active_scene(final/'scene.json')
    for key in ('complete_surface','navigation','candidates','available_structures','structure_foreground_voxels'):
        if result[key]!=scene[key]:raise ValueError('Recovery changed accepted scene: '+key)
    write_json(output/'activation.json',dict(status='current_CT_recovery_review_published_without_model_route_swap',
        current_scene=str(final/'scene.json'),target_index=target,review_binding=binding,total_seconds=perf_counter()-begin,
        backend='PS_ROI_sparse',new_bitstream=False,model_navigation_replaced=False))
    return final/'scene.json'
