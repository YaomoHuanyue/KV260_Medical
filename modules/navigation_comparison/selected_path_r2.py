"""Selected-path audit with original target semantics and immutable bindings.

R1 geometry and its numerical evidence stay unchanged. This wrapper makes the
linear C4 endpoint query distinct from the user's original candidate target.
"""
from pathlib import Path
import hashlib
from scipy.spatial import cKDTree
from selected_path_r1 import Selection,load_selection,linear_scene,verify_polyline_prefix
from selected_path_r1 import audit_selection as geometry_audit

def audit_selection(context,target,selection,session,**options):
    report,route,camera=geometry_audit(context,target,selection,session,**options)
    internal=dict(kind='manual_point_at_selected_polyline_end',
        requested_endpoint_id=report['requested_endpoint_id'],
        selected_endpoint_id=report['selected_endpoint_id'],
        closest_centerline_gap_mm=report['closest_centerline_gap_mm'])
    report['internal_linear_scene_query']=internal
    report['requested_endpoint_id']=int(selection.original_node_ids[-1])
    report['selected_endpoint_id']=None
    report['selected_endpoint_identity']='dense point on audited original selected polyline'
    report['closest_centerline_gap_mm']=float(cKDTree(target.points_lps_mm).query(selection.points[-1])[0])
    if not report['reason']:
        report['status']='airway_approach' if target.kind=='lesion_candidate' else 'route_found'
    if target.kind=='lesion_candidate':
        report['warnings'].append('Route approaches the candidate inside the airway; it does not reach an external lesion')
    here=Path(__file__).parent
    report['selection_adapter_source_sha256']={n:hashlib.sha256((here/n).read_bytes()).hexdigest()
        for n in ('selected_path_r1.py','selected_path_r2.py')}
    return report,route,camera
