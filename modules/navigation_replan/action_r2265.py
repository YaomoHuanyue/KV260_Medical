"""Replan the original weighted forest on the current reviewed triangle walls.

No reconstruction, mask changes or automatic swaps. The original physical
wall/crop/mask and bend-prefix gates are retained. An optional actual PL
auditor can be injected for full same-input comparisons; normal execution
uses the measured native audit provider until an accelerated provider passes.
"""
from pathlib import Path
from time import perf_counter
import copy,json,os,shutil,tempfile
import numpy as np
import SimpleITK as sitk
from modules.airway_detail.active_scene_r20 import verify_active_scene
from modules.surface_route.active_actions_r15 import target_binding
from modules.surface_route.bundle_r8 import arrays,build_bundle,write_json
from modules.surface_route.verification_session_r15 import sha,verify_bundle
from modules.surface_route.guidance_r5 import ScalarField,build_guidance
from modules.surface_route.curve_guidance_r5 import GuidanceSurfaceBendPlanner
from modules.surface_route.bend_replan_r3 import checked_replan
from modules.surface_route.audit import MeshRegion
from modules.surface_route.ui_bridge_r9 import asset_path
from dfx.surface_quality.prepare import unpack_scene

ROOT=Path(__file__).resolve().parents[2]

def options_checked(scene,options):
    if set(options)!={'lesion','diameter','margin','minimum_bend'}:
        raise ValueError('Explicit target and all physical constraints required')
    if type(options['lesion']) is not int or options['lesion'] not in [c['index'] for c in scene['candidates']]:
        raise ValueError('Target is absent from the current CT catalogue')
    values=np.asarray([options[k] for k in ('diameter','margin','minimum_bend')],float)
    if any(isinstance(options[k],bool) for k in ('diameter','margin','minimum_bend')) or not np.isfinite(values).all() or values[0]<=0 or np.any(values[1:]<0):
        raise ValueError('Finite positive diameter and nonnegative physical margins required')
    return dict(lesion=options['lesion'],**{k:float(options[k]) for k in ('diameter','margin','minimum_bend')})

def publish(active_path,output,bundle,options,receipt_path):
    scene=verify_active_scene(active_path)
    old=json.loads((Path(active_path).parent/'prepared.json').read_text(encoding='utf8'))
    meta=verify_bundle(bundle);previous=Path(scene['complete_surface']['bundle'])
    if output.exists() or not output.is_relative_to(ROOT):raise ValueError('Fresh project UI output required')
    for n in ('mesh.npz','airway.vertices'):
        if sha(bundle/n)!=sha(previous/n):raise ValueError('Replanning changed the C1 mesh')
    if meta['renderer_scalar_sha256']!=scene['complete_surface']['scalar_sha256']:
        raise ValueError('Replanning changed the current scalar')
    route,camera=[arrays(bundle/n) for n in ('route.npz','camera.npz')]
    report=json.loads((bundle/'route.json').read_text())
    if report['target']['index']!=options['lesion']:raise ValueError('New route belongs to another target')
    report.update(branch_guidance=json.loads((bundle/'guidance.json').read_text()),
        complete_scene_revision=meta['revision'],native_UI_selection_integration_pending=False,
        branch_guidance_and_current_complete_UI_integration_pending=False)
    new=copy.deepcopy(scene)
    new['complete_surface'].update(bundle=str(bundle),revision=meta['revision'],route_id=meta['route_id'],
        explicit_replan=dict(receipt=str(receipt_path),receipt_sha256=sha(receipt_path),options=options,revision=meta['revision']),
        new_field_comparisons_available=False)
    # Saved old comparisons remain on disk, but cannot describe changed
    # constraints/target. Recompute them only on an explicit comparison action.
    new['complete_surface'].pop('comparison',None)
    new['meshes']['airway'].update(file=str(bundle/'airway.vertices'),scene_revision=meta['revision'])
    new['navigation']=dict(points=route['points_lps_mm'].tolist(),arc=route['arc_mm'].tolist(),radius=route['radius_mm'].tolist(),
        positions=camera['position_lps_mm'].tolist(),forward=camera['forward_lps'].tolist(),up=camera['up_lps'].tolist(),report=report,
        hud=json.loads((bundle/'hud.json').read_text()))
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.'+output.name+'-',dir=output.parent))
    try:
        attributes=asset_path(Path(active_path).parent,scene['meshes']['airway']['attributes']['file'])
        if sha(attributes)!=old['output_sha256']['airway.attributes']:raise ValueError('Changed C1 analysis attributes')
        shutil.copyfile(attributes,stage/'airway.attributes')
        new['meshes']['airway']['attributes']['file']=str(output/'airway.attributes')
        write_json(stage/'scene.json',new)
        prepared=copy.deepcopy(old);prepared.pop('active_comparison',None)
        prepared.update(base_scene=str(active_path),base_scene_sha256=sha(active_path),
            bundle=str(bundle),bundle_sha256=sha(bundle/'scene.json'),revision=meta['revision'],
            airway_vertices_sha256=sha(bundle/'airway.vertices'),
            active_replan=new['complete_surface']['explicit_replan'],
            output_sha256={n:sha(stage/n) for n in ('scene.json','airway.attributes')})
        write_json(stage/'prepared.json',prepared)
        os.rename(stage,output)
    finally:
        if stage.exists():
            assert stage.parent==output.parent
            for p in stage.iterdir():
                assert p.is_file();p.unlink()
            stage.rmdir()
    verify_replan(output/'scene.json')
    return output/'scene.json'

def verify_replan(path):
    scene=verify_active_scene(path);entry=scene['complete_surface'].get('explicit_replan')
    if entry is None:return scene
    prepared=json.loads((Path(path).parent/'prepared.json').read_text())
    if entry!=prepared.get('active_replan'):raise ValueError('Mixed explicit replan identity')
    receipt=asset_path(ROOT,entry['receipt'])
    if sha(receipt)!=entry['receipt_sha256']:raise ValueError('Changed replan receipt')
    proof=json.loads(receipt.read_text())
    # Later comparison/selected-path actions may retain this immutable
    # receipt as history. Its explicit revision prevents stale controls.
    bundle=asset_path(ROOT,proof['bundle_metadata']).parent;meta=verify_bundle(bundle)
    report=json.loads((bundle/'route.json').read_text())
    if (proof['schema']!='kv260.current_surface.replan.v1' or proof['input_sha256']!=scene['input_sha256']
        or proof['options']!=entry['options'] or proof['revision']!=meta['revision'] or entry['revision']!=meta['revision']
        or proof['scalar_sha256']!=meta['renderer_scalar_sha256'] or proof['mesh_sha256']!=sha(bundle/'mesh.npz')
        or report['target']['index']!=entry['options']['lesion']):
        raise ValueError('Replan belongs to another case, surface or target')
    for key,source in [('diameter','scope_diameter_mm'),('margin','safety_margin_mm'),('minimum_bend','minimum_bend_radius_mm')]:
        if report[source]!=entry['options'][key]:raise ValueError('Replan constraints differ')
    return scene

def produce(active,output,options,event=lambda *a,**k:None,*,auditor=None,oracle=None):
    start=perf_counter();active=Path(active).resolve();output=Path(output).resolve()
    if not active.is_relative_to(ROOT) or not output.is_relative_to(ROOT/'ui/cache') or output.exists():
        raise ValueError('Existing project scene and fresh UI-cache action output required')
    scene=verify_replan(active);options=options_checked(scene,options)
    parent=Path(scene['complete_surface']['bundle']);meta=verify_bundle(parent)
    mesh=arrays(parent/'mesh.npz');scalar,_=unpack_scene((parent/'scene_-1.bin').read_bytes())
    field=ScalarField(scalar,meta['geometry'],meta['bits'])
    if field.sha256!=meta['renderer_scalar_sha256']:raise ValueError('Scalar packet differs from current surface')
    c,target=target_binding(scene,options['lesion']);region=MeshRegion(mesh['points'],mesh['faces'],meta['geometry'])
    if oracle is None:
        if os.name=='nt':
            from modules.surface_quality.mesh_clearance_batch import BatchedMeshClearance
            oracle=BatchedMeshClearance(mesh['points'],mesh['faces'])
        else:
            from modules.surface_quality.mesh_clearance_native import NativeMeshClearance
            oracle=NativeMeshClearance(mesh['points'],mesh['faces'])
    output.mkdir();event('progress',text='正在按当前管壁、目标和器械约束重新规划导航')
    before=perf_counter()
    planner=GuidanceSurfaceBendPlanner(c,region,oracle,auditor=auditor)
    report,route,camera=checked_replan(planner,target,scope_diameter_mm=options['diameter'],
        safety_margin_mm=options['margin'],minimum_bend_radius_mm=options['minimum_bend'],forward_window_mm=10.)
    planning=perf_counter()-before
    if not len(route["arc_mm"]):
        from modules.navigation_replan.no_route_r2265 import publish as blocked
        return blocked(active,output,options,scene,meta,report,route,camera,planner.history)
    report.update(explicit_current_surface_replanning=True,automatic_quality_changes=False,
        original_replanning_edge_weight_rule_preserved=True)
    before=perf_counter()
    guidance,targets=build_guidance(c,route,field,sitk.ReadImage(str(Path(scene['result'])/'segmentation/airway_mask.nii.gz')))
    guidance_seconds=perf_counter()-before
    provenance=copy.deepcopy(meta['identity']['provenance'])
    provenance.update(parent_revision=meta['revision'],parent_route_id=meta['route_id'],
        explicit_current_surface_replan=options,topology_reextracted=False,
        current_replan_audit_backend=planner.auditor.backend)
    provenance['input_sha256'].update({active.relative_to(ROOT).as_posix():sha(active),
        Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__))})
    updated=build_bundle(output/'bundle',scalar=scalar,geometry=meta['geometry'],bits=meta['bits'],
        points=mesh['points'],faces=mesh['faces'],mesh_proof=meta['identity']['mesh_proof'],
        route=route,report=report,camera=camera,guidance=guidance,targets=targets,provenance=provenance)
    proof=dict(schema='kv260.current_surface.replan.v1',input_sha256=scene['input_sha256'],
        parent_scene=str(active),parent_scene_sha256=sha(active),parent_revision=meta['revision'],
        revision=updated['revision'],bundle_metadata=str(output/'bundle/scene.json'),options=options,scalar_sha256=field.sha256,
        mesh_sha256=sha(output/'bundle/mesh.npz'),planning_seconds=planning,guidance_seconds=guidance_seconds,
        point_count=report['point_count'],camera_count=len(camera['position_lps_mm']),
        bend_prefix_queries=len(report['query_trace']),audit_backend=planner.auditor.backend,
        original_full_wall_crop_mask_edge_weight_bend_prefix_and_camera_gates_retained=True,
        model_or_mask_changed=False,topology_reextracted=False,new_bitstream=False,
        actual_PL_audit=auditor is not None and str(planner.auditor.backend).startswith('PL'),
        original_weighted_replanning_not_profile_weighting=True,
        total_before_UI_seconds=perf_counter()-start,production_promoted=False)
    write_json(output/'replan.json',proof)
    return publish(active,output/'UI',output/'bundle',options,output/'replan.json')
