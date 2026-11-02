"""Bind accepted selected-path geometry to original anatomical branch guidance."""
from pathlib import Path
import hashlib,sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'modules/navigation'))
sys.path.insert(0,str(ROOT/'dfx/route_audit_speed'))
from protocol import validate_stored_audit
from navigation.guidance import branch_guidance,guidance_route_id

def attach(context,selection,report,route):
    """Keep the original branch IDs and reject unsupported cycle-edge mappings.

    No nearest-node replacement is used: raw parent IDs come from the bound
    complete candidate arrays. Existing guidance only marks exits actually
    matched by the retained path, including a conservative truncated prefix.
    """
    validate_stored_audit(route,report)
    if (report['selection']!=selection.binding or
        report['selection']['input_sha256']!=context.metadata['input_sha256'] or
        report['selection']['centerline_id']!=context.metadata['centerline_id']):
        raise ValueError('Selected audit belongs to another anatomy or candidate')
    forest={frozenset(map(int,e)) for e in context.edges}
    ids=selection.original_node_ids
    if any(frozenset((int(a),int(b))) not in forest for a,b in zip(ids[:-1],ids[1:])):
        raise ValueError('Raw-cycle route needs an explicit branch-tree mapping before UI application')
    mapped=dict(route,selected_polyline_scene_ids=route['centerline_point_ids'].copy(),
        centerline_point_ids=ids.copy())
    report=dict(report)
    report['branch_guidance']=branch_guidance(context,mapped)
    assert report['branch_guidance']['route_id']==guidance_route_id(mapped)
    report['branch_guidance_original_parent_ids_retained']=True
    report['branch_guidance_application_pending']=False
    report['actual_UI_route_replaced']=False
    report['guidance_adapter_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    validate_stored_audit(mapped,report)
    return report,mapped
