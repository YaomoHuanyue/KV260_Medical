"""Bind native comparison/selected-path actions to the current complete surface."""
from pathlib import Path
from types import SimpleNamespace
import copy,json,os,shutil,tempfile
import numpy as np
from scipy.spatial import cKDTree
from modules.surface_route.bundle_r8 import sha,write_json,arrays
from modules.surface_route.bundle_reader_r9 import verify_bundle
from modules.surface_route.ui_bridge_r9 import verify_prepared
from modules.surface_route.surface_actions_r13 import Comparison,prepare_comparison,prepare_selected,verify_comparison,verify_sources
from modules.navigation.navigation.pipeline import load_prepared,choose_target

ROOT=Path(__file__).resolve().parents[2]


def target_binding(scene,index):
    result=Path(scene['result']);c=load_prepared(result/'navigation')
    target=choose_target(c,lesion_path=result/'segmentation/nodule_mask.nii.gz',lesion_index=index)
    return c,target


def validate_bound_comparison(scene,entry,bound):
    file=Path(entry['receipt']).resolve()
    if not file.is_relative_to(ROOT) or file.name!='comparison.json' or sha(file)!=entry['receipt_sha256']:
        raise ValueError('Changed current-surface comparison receipt')
    proof=json.loads(file.read_text(encoding='utf-8'));binding=copy.deepcopy(proof['binding'])
    c,target=target_binding(scene,entry['options']['lesion'])
    bundle=Path(scene['complete_surface']['bundle'])
    sources={n:bound[n] for n in binding['source_files_sha256'] if n in bound}
    binding.update(mesh_sha256=sha(bundle/'mesh.npz'),scalar_sha256=scene['complete_surface']['scalar_sha256'],
        CT_input_sha256=scene['input_sha256'],centerline_id=c.metadata['centerline_id'],
        source_files_sha256=sources,target=target.metadata)
    verify_comparison(file.parent,SimpleNamespace(binding=binding))
    for key,name in (('whole_instrument_profiles','whole_instrument_profiles.json'),('whole_alternative_routes','whole_alternative_routes.json')):
        value=json.loads((file.parent/name).read_text(encoding='utf-8'))
        if scene['navigation'].get(key)!=value:raise ValueError('Displayed comparison differs from complete saved report')
        if (value['safety_margin_mm']!=entry['options']['margin'] or value['minimum_bend_radius_mm']!=entry['options']['minimum_bend']):
            raise ValueError('Displayed comparison constraints differ')
    if entry['options']['diameter'] not in [g['scope_diameter_mm'] for g in scene['navigation']['whole_alternative_routes']['groups']]:
        raise ValueError('Requested instrument missing from complete comparison')


def verify_active_scene(path):
    path=Path(path).resolve();scene=verify_prepared(path)
    entry=scene['complete_surface'].get('comparison')
    if entry is None:return scene
    receipt=json.loads((path.parent/'prepared.json').read_text(encoding='utf-8'))
    if entry!=receipt.get('active_comparison'):raise ValueError('Mixed active comparison identity')
    validate_bound_comparison(scene,entry,receipt['case_files_sha256'])
    return scene


def comparison_context(scene,index):
    comp=Comparison.from_bundle(scene['complete_surface']['bundle'],scene['result'],scene['input'],native=os.name!='nt')
    if index!=comp.target.metadata['index']:
        _,target=target_binding(scene,index)
        comp.target=target;comp.binding=dict(comp.binding,target=target.metadata)
        comp.gaps=cKDTree(target.points_lps_mm).query(comp.c.points_lps_mm)[0]
    return comp


def publish(active_path,output,bundle,comparison,options):
    """Reuse only verified identical mesh attributes; publish one complete Qt scene."""
    active_path=Path(active_path).resolve();output=Path(output).resolve();bundle=Path(bundle).resolve();comparison=Path(comparison).resolve()
    scene=verify_active_scene(active_path);old=json.loads((active_path.parent/'prepared.json').read_text(encoding='utf-8'))
    meta=verify_bundle(bundle);previous=Path(scene['complete_surface']['bundle'])
    if not output.is_relative_to(ROOT) or output.exists():raise ValueError('New project scene output required')
    for name in ('mesh.npz','airway.vertices'):
        if sha(bundle/name)!=sha(previous/name):raise ValueError('Cannot reuse attributes for a changed C1 mesh')
    if meta['renderer_scalar_sha256']!=scene['complete_surface']['scalar_sha256']:raise ValueError('Action changed scalar')
    compare_proof=json.loads((comparison/'comparison.json').read_text(encoding='utf-8'))
    if compare_proof['binding']['target']['index']!=options['lesion']:raise ValueError('Wrong target in new comparison')
    next_scene=copy.deepcopy(scene)
    next_scene['complete_surface'].update(bundle=str(bundle),revision=meta['revision'],route_id=meta['route_id'],
        new_field_comparisons_available=True,comparison=dict(receipt=str(comparison/'comparison.json'),
            receipt_sha256=sha(comparison/'comparison.json'),options=options))
    next_scene['complete_surface']['pending_operations']=['active_quality_and_generic_new_case','active_batch_video_recovery_dispatch']
    next_scene['meshes']['airway'].update(file=str(bundle/'airway.vertices'),scene_revision=meta['revision'])
    if bundle!=previous:
        route,camera=[arrays(bundle/name) for name in ('route.npz','camera.npz')]
        report=json.loads((bundle/'route.json').read_text(encoding='utf-8'))
        report.update(branch_guidance=json.loads((bundle/'guidance.json').read_text(encoding='utf-8')),
            complete_scene_revision=meta['revision'],native_UI_selection_integration_pending=False,
            branch_guidance_and_current_complete_UI_integration_pending=False)
        next_scene['navigation']=dict(points=route['points_lps_mm'].tolist(),arc=route['arc_mm'].tolist(),radius=route['radius_mm'].tolist(),
            positions=camera['position_lps_mm'].tolist(),forward=camera['forward_lps'].tolist(),up=camera['up_lps'].tolist(),report=report,
            hud=json.loads((bundle/'hud.json').read_text(encoding='utf-8')))
    for key,name in (('whole_instrument_profiles','whole_instrument_profiles.json'),('whole_alternative_routes','whole_alternative_routes.json')):
        next_scene['navigation'][key]=json.loads((comparison/name).read_text(encoding='utf-8'))
    validate_bound_comparison(next_scene,next_scene['complete_surface']['comparison'],old['case_files_sha256'])
    attr=Path(scene['meshes']['airway']['attributes']['file']).resolve()
    if not attr.is_relative_to(ROOT) or sha(attr)!=old['output_sha256']['airway.attributes']:raise ValueError('Changed C1 attributes')
    output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.'+output.name+'-',dir=output.parent))
    try:
        shutil.copyfile(attr,stage/'airway.attributes')
        next_scene['meshes']['airway']['attributes']['file']=str(output/'airway.attributes')
        write_json(stage/'scene.json',next_scene)
        receipt=copy.deepcopy(old);receipt.update(base_scene=str(active_path),base_scene_sha256=sha(active_path),
            bundle=str(bundle),bundle_sha256=sha(bundle/'scene.json'),revision=meta['revision'],
            airway_vertices_sha256=sha(bundle/'airway.vertices'),active_comparison=next_scene['complete_surface']['comparison'],
            output_sha256={name:sha(stage/name) for name in ('scene.json','airway.attributes')},
            selected_target_may_differ_from_previous_route=True,action_source_sha256=sha(Path(__file__)),
            analysis_attributes_reused_only_after_identical_mesh_and_stream_SHA_check=True)
        write_json(stage/'prepared.json',receipt);os.rename(stage,output)
    finally:
        if stage.exists():
            assert stage.parent==output.parent and stage!=output.parent
            shutil.rmtree(stage)
    verify_active_scene(output/'scene.json')
    return next_scene


def compare_action(active,output,options):
    scene=verify_active_scene(active);comp=comparison_context(scene,options['lesion'])
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT):raise ValueError('Project comparison output required')
    output.mkdir(parents=True,exist_ok=False)
    prepare_comparison(comp,output/'comparison',diameters=sorted({1.,1.2,1.8,2.8,4.,options['diameter']}),
        margin=options['margin'],bend=options['minimum_bend'])
    return publish(active,output/'UI',scene['complete_surface']['bundle'],output/'comparison',options)


def selected_action(active,output,group,candidate):
    scene=verify_active_scene(active);entry=scene['complete_surface'].get('comparison')
    if not entry:raise ValueError('Compute current-surface comparison first')
    comp=comparison_context(scene,entry['options']['lesion']);folder=Path(entry['receipt']).parent
    options=copy.deepcopy(entry['options'])
    alt=json.loads((folder/'whole_alternative_routes.json').read_text(encoding='utf-8'))
    if type(group)!=int or not 0<=group<len(alt['groups']):raise ValueError('Invalid current instrument group')
    options['diameter']=float(alt['groups'][group]['scope_diameter_mm'])
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT):raise ValueError('Project selected output required')
    output.mkdir(parents=True,exist_ok=False)
    prepare_selected(comp,scene['complete_surface']['bundle'],folder,group,candidate,output/'bundle')
    return publish(active,output/'UI',output/'bundle',folder,options)
