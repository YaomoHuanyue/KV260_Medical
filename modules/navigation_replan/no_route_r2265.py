"""Typed zero-route result; never invent a root point to satisfy a bundle ABI."""
from pathlib import Path
from dataclasses import dataclass
import json
import numpy as np
from modules.navigation_replan.action import verify_replan,options_checked
from modules.surface_route.active_actions_r15 import target_binding
from modules.surface_route.verification_session_r15 import sha,verify_bundle
from modules.surface_route.bundle_r8 import arrays,write_json
from modules.surface_route.bend_replan_r3 import validate_stored_audit
from modules.surface_route.audit import MeshRegion
from modules.surface_route.refine_r1 import _query
from modules.surface_quality.mesh_clearance_native import NativeMeshClearance

ROOT=Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class NoRoute:
    receipt:Path
    report:dict
    options:dict
    parent_scene:Path


def verify(path):
    path=Path(path).resolve();proof=json.loads(path.read_text());folder=path.parent
    if not path.is_relative_to(ROOT/'ui/cache') or proof['schema']!='kv260.current_surface.no_route.v1':
        raise ValueError('Bound project no-route receipt required')
    parent=Path(proof['parent_scene']);scene=verify_replan(parent);options=options_checked(scene,proof['options'])
    if sha(parent)!=proof['parent_scene_sha256'] or proof['input_sha256']!=scene['input_sha256']:
        raise ValueError('Changed no-route source scene')
    for n,h in proof['outputs_sha256'].items():
        if n not in ('report.json','route.npz','camera.npz','diagnostics.npz') or sha(folder/n)!=h:
            raise ValueError('Changed no-route evidence')
    if set(proof['outputs_sha256'])!={'report.json','route.npz','camera.npz','diagnostics.npz'}:
        raise ValueError('Incomplete original zero-route evidence')
    report=json.loads((folder/'report.json').read_text());route=arrays(folder/'route.npz');camera=arrays(folder/'camera.npz')
    if (report['status']!='unreachable' or report['reason']!='insufficient_new_surface_root_clearance'
        or report['selected_endpoint_id'] is not None or report['reachable_centerline_points']!=0
        or report['point_count']!=0 or report['length_mm']!=0 or len(route['arc_mm'])!=0
        or route['points_lps_mm'].shape!=(0,3) or any(len(v) for v in camera.values())
        or report['source_graph_edges_or_mask_changed'] or report['synthetic_bridge_edges']!=0):
        raise ValueError('No-route receipt contains an accepted path or changed graph')
    for key,name in [('diameter','scope_diameter_mm'),('margin','safety_margin_mm'),('minimum_bend','minimum_bend_radius_mm')]:
        if report[name]!=options[key]:raise ValueError('No-route constraints differ')
    if report['required_radius_mm']!=options['diameter']*.5+options['margin']:
        raise ValueError('No-route radius rule differs')
    validate_stored_audit(route,report)
    c,target=target_binding(scene,options['lesion'])
    if target.metadata!=report['target']:raise ValueError('No-route target differs from original CT')
    if (report['resolution_margin_mm']!=(c.resolution_margin_mm if report['required_radius_mm']>0 else 0.)
        or report['total_centerline_points']!=len(c.points_lps_mm) or report['original_edges']!=len(c.edges)
        or proof['source_sha256']!=sha(Path(__file__))
        or proof['PL_accessed']!=str(report['route_audit']['backend']).startswith('PL')):
        raise ValueError('No-route original geometry, source or backend binding differs')
    meta=verify_bundle(scene['complete_surface']['bundle']);mesh=arrays(Path(scene['complete_surface']['bundle'])/'mesh.npz')
    if proof['mesh_sha256']!=sha(Path(scene['complete_surface']['bundle'])/'mesh.npz') or proof['scalar_sha256']!=meta['renderer_scalar_sha256']:
        raise ValueError('No-route result belongs to another wall')
    region=MeshRegion(mesh['points'],mesh['faces'],meta['geometry']);oracle=NativeMeshClearance(mesh['points'],mesh['faces'])
    # Check every original graph node, retaining the full diagnostic arrays.
    actual=_query(oracle,c.points_lps_mm);effective=np.minimum(actual,region.crop_clearance(c.points_lps_mm))
    diag=arrays(folder/'diagnostics.npz')
    np.testing.assert_array_equal(diag['node_wall_distance_mm'],actual)
    np.testing.assert_array_equal(diag['node_effective_distance_mm'],effective)
    if (diag['all_costs'].shape!=(len(c.points_lps_mm),) or diag['all_parents'].shape!=(len(c.points_lps_mm),)
        or diag['allowed_edges'].shape!=(len(c.edges),) or diag['allowed_edges'].dtype!=np.dtype(bool)
        or int(diag['allowed_edges'].sum())!=report['accepted_edges']):
        raise ValueError('No-route diagnostic graph shape differs')
    if np.isfinite(diag['all_costs']).any():raise ValueError('No-route result retains a reachable node')
    winding=region.root_winding(c.points_lps_mm[c.root])
    if winding!=report['root_winding']:raise ValueError('Root containment proof differs')
    root_ok=(winding['inside_unit_winding_region'] and c.inside(c.points_lps_mm[[c.root]])[0]
        and effective[c.root]-1e-6>=report['required_radius_mm']+report['resolution_margin_mm'])
    if root_ok:raise ValueError('No-route result falsely refuses a valid root')
    return NoRoute(path,report,options,parent)


def publish(parent,output,options,scene,meta,report,route,camera,history):
    if len(route['arc_mm']) or not history:raise ValueError('Actual original empty result required')
    report=dict(report,explicit_current_surface_replanning=True,automatic_quality_changes=False,
        original_replanning_edge_weight_rule_preserved=True,no_reference_root_inserted=True)
    write_json(output/'report.json',report);np.savez_compressed(output/'route.npz',**route)
    np.savez_compressed(output/'camera.npz',**camera)
    diagnostics=history[-1]['diagnostics']
    np.savez_compressed(output/'diagnostics.npz',**{k:diagnostics[k] for k in
        ('node_wall_distance_mm','node_effective_distance_mm','allowed_edges','all_costs','all_parents')})
    write_json(output/'no_route.json',dict(schema='kv260.current_surface.no_route.v1',parent_scene=str(parent),
        parent_scene_sha256=sha(parent),input_sha256=scene['input_sha256'],options=options,
        scalar_sha256=meta['renderer_scalar_sha256'],mesh_sha256=sha(Path(scene['complete_surface']['bundle'])/'mesh.npz'),
        outputs_sha256={n:sha(output/n) for n in ('report.json','route.npz','camera.npz','diagnostics.npz')},
        current_model_and_last_successful_saved_scene_unchanged=True,new_scene_or_route_not_fabricated=True,
        root_reference_not_inserted=True,navigation_usable=False,PL_accessed=str(report['route_audit']['backend']).startswith('PL'),new_bitstream=False,
        source_sha256=sha(Path(__file__)),clinical_safety_certified=False))
    return verify(output/'no_route.json')
