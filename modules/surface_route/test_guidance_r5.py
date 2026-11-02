"""Geometric and ownership regressions for displaced selected-branch cues."""
from pathlib import Path
from dataclasses import replace
import argparse, copy, json, sys
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.navigation.navigation.geometry import Geometry
from modules.navigation.navigation.centerline import Centerline, branch_tree
from modules.navigation.navigation.planner import densify
from modules.surface_route.curve_quality_r4 import gaussian_candidate
from modules.surface_route.curve_guidance_r5 import gaussian_candidate_with_parameter
from modules.surface_route.guidance_r5 import ScalarField, source_node_arcs, build_guidance


def fixture():
    geometry = Geometry((41, 41, 41), (1., 1., 1.), (-20., -20., -20.), tuple(np.eye(3).ravel()))
    indices = np.array([[5,20,20],[10,20,20],[15,20,20],
                        [20,15,20],[25,10,20],[20,25,20],[25,30,20]], np.int32)
    points = geometry.to_lps(indices)
    edges = np.array([[0,1],[1,2],[2,3],[3,4],[2,5],[5,6]], np.int32)
    dense = np.vstack([densify(points[e], .2) for e in edges])
    voxels = np.indices((41,41,41)).reshape(3,-1).T
    mask = (cKDTree(dense).query(geometry.to_lps(voxels))[0] < 3.8).reshape(41,41,41)
    inside = ndi.distance_transform_edt(mask)
    q = np.rint((inside-ndi.distance_transform_edt(~mask))*32).clip(-128,4095).astype('<i2')
    c = Centerline(geometry, np.zeros(3,dtype=int), mask, inside.astype(np.float32), indices,
        points, inside[tuple(indices.T)], edges, np.zeros(7,np.int32), 0, {})
    image = sitk.GetImageFromArray(mask.astype(np.uint8)); image.SetOrigin(geometry.origin_lps_mm)
    fg = dict(size_xyz=list(geometry.size_xyz), spacing_xyz=list(geometry.spacing_xyz),
        origin_lps_mm=list(geometry.origin_lps_mm), direction=list(geometry.direction))
    ids = np.array([0,1,2,3,4],np.int32)
    reference = densify(points[ids], .2)
    out, _, parameter = gaussian_candidate_with_parameter(reference, .2, 1.5)
    arc = lambda p: np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))]
    route = dict(points_lps_mm=out, arc_mm=arc(out), centerline_point_ids=ids,
        guidance_reference_points_lps_mm=reference, guidance_reference_arc_mm=arc(reference),
        guidance_source_parameter_mm=parameter)
    return c, route, ScalarField(q,fg,5), image


def refused(function):
    try:
        function()
    except ValueError:
        return
    raise AssertionError('Expected rejection')


def run():
    c, route, field, image = fixture()
    old, _ = gaussian_candidate(route['guidance_reference_points_lps_mm'], .2, 1.5)
    np.testing.assert_array_equal(old, route['points_lps_mm'])
    mapped, _ = source_node_arcs(c,route)
    assert np.all(np.diff(mapped)>0) and mapped[0]==0 and mapped[-1]==route['arc_mm'][-1]
    cues, targets = build_guidance(c,route,field,image)
    assert len(cues['events'])==1 and not cues['unavailable_events']
    event = cues['events'][0]
    assert event['junction_point_ids']==[2] and event['selected_exit_point_id']==3
    branches = branch_tree(c)['branches']
    chosen = next(b for b in branches if b['id']==event['selected_branch_id'])
    sibling = next(b for b in branches if b['start']==2 and b['point_ids'][1]==5)
    assert chosen['point_ids'][1]==3 and sibling['id'] not in event['lumen']['branch_ids']
    for target in targets.values():
        assert target.any() and not np.any(target & (field.values<=0))
        locations = np.argwhere(target)
        _, owners = cKDTree(c.points_lps_mm).query(c.geometry.to_lps(locations))
        # The accepted source-coverage threshold may clip ownership boundaries;
        # the distant opposite daughter must never be annotated.
        assert not np.any(np.isin(owners,[5,6]))
    assert event['aperture']['scalar_sha256']==field.sha256
    assert np.all(field.sample(np.array(event['aperture']['sample_points_lps_mm']))>0)
    tests = ['unchanged_R4_Gaussian_geometry_and_ordered_source_arc',
             'selected_daughter_excludes_sibling_and_clips_same_scalar']
    angle=.73
    rotation=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
    offset=np.array([17.,-8.,3.])
    transformed_geometry=replace(c.geometry,
        origin_lps_mm=tuple(rotation@np.array(c.geometry.origin_lps_mm)+offset),
        direction=tuple(rotation.ravel()))
    transformed=replace(c,geometry=transformed_geometry,points_lps_mm=c.points_lps_mm@rotation.T+offset)
    moved=copy.deepcopy(route)
    for key in ('points_lps_mm','guidance_reference_points_lps_mm'):
        moved[key]=moved[key]@rotation.T+offset
    moved_field=ScalarField(field.values,dict(field.geometry,
        origin_lps_mm=list(transformed_geometry.origin_lps_mm), direction=list(transformed_geometry.direction)),5)
    np.testing.assert_allclose(source_node_arcs(transformed,moved)[0],mapped,rtol=0,atol=1e-10)
    probes=np.array([[0.,0.,-10.],[0.,-5.,1.],[2.,-8.,4.]])
    np.testing.assert_allclose(moved_field.sample(probes@rotation.T+offset),field.sample(probes),rtol=0,atol=1e-10)
    tests.append('rigid_LPS_rotation_translation_scalar_and_arc_invariance')
    root={k:v[:1].copy() for k,v in route.items()}
    root['points_lps_mm']=root['guidance_reference_points_lps_mm'].copy()
    root['arc_mm'][:]=0;root['guidance_reference_arc_mm'][:]=0;root['guidance_source_parameter_mm'][:]=0
    empty, masks=build_guidance(c,root,field,image)
    assert not empty['events'] and not masks
    tests.append('root_only_route_has_no_forward_exit_cue')
    bad=copy.deepcopy(route);bad['centerline_point_ids']=np.array([0,1,2,5,4])
    refused(lambda:source_node_arcs(c,bad))
    bad=copy.deepcopy(route);bad['guidance_source_parameter_mm'][10]=0
    refused(lambda:source_node_arcs(c,bad))
    bad=copy.deepcopy(route);bad['guidance_reference_points_lps_mm'][20]+=10
    refused(lambda:source_node_arcs(c,bad))
    tests.append('wrong_graph_edge_nonmonotone_parameter_and_false_reference_refused')
    other=sitk.Image(image);other.SetOrigin((1.,2.,3.))
    refused(lambda:build_guidance(c,route,field,other))
    altered=sitk.GetArrayFromImage(image);altered[tuple(c.indices_zyx[1])]=0
    other=sitk.GetImageFromArray(altered);other.CopyInformation(image)
    refused(lambda:build_guidance(c,route,field,other))
    outside=ScalarField(np.full_like(field.values,-128),field.geometry,5)
    refused(lambda:build_guidance(c,route,outside,image))
    tests.append('wrong_source_mask_geometry_or_scalar_route_membership_refused')
    bad_geometry=dict(field.geometry,spacing_xyz=[0.,1.,1.])
    refused(lambda:ScalarField(field.values,bad_geometry,5))
    refused(lambda:ScalarField(field.values.astype(np.int32),field.geometry,5))
    tests.append('invalid_scalar_type_and_physical_spacing_refused')
    return dict(status='all_displaced_guidance_geometry_ownership_and_negative_cases_passed',
        platform=sys.platform,tests=tests,PL_access=False,production_promoted=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    assert not args.output.exists()
    record=run();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(record['status'],len(record['tests']))
