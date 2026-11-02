"""Geometric adversaries that discrete-point-only review cannot detect."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import numpy as np

SYSTEM = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SYSTEM))
from modules.surface_route.audit import MeshRegion, audit_polyline, round_down_float32
from modules.surface_quality.mesh_clearance import MeshClearance


def cube(offset=(0, 0, 0)):
    p = np.array([[0,0,0],[2,0,0],[2,2,0],[0,2,0],
                  [0,0,2],[2,0,2],[2,2,2],[0,2,2]], float)+offset
    f = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],
                  [0,1,5],[0,5,4],[1,2,6],[1,6,5],
                  [2,3,7],[2,7,6],[3,0,4],[3,4,7]], np.int32)
    return p, f


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    geometry = dict(size_xyz=[3,3,3],spacing_xyz=[1.,1.,1.],
                    origin_lps_mm=[0.,0.,0.],direction=np.eye(3).ravel().tolist())
    p, f = cube()
    tests = []
    for name, faces in [('closed_cube', f), ('crop_open_cube', np.delete(f, [2,3], axis=0))]:
        region = MeshRegion(p, faces, geometry)
        route = np.array([[.8,1,1],[1.2,1,1]])
        d = MeshClearance(p, faces).distance(route)[0]
        report, arrays = audit_polyline(region, route, d, required_radius_mm=.3, resolution_margin_mm=.1)
        assert report['reviewed_prefix_points'] == 2 and abs(abs(report['root_winding']['value'])-1) < 1e-12
        assert np.all(arrays['conservative_radius_mm'] <= d)
        tests.append(dict(name=name, status='passed'))
    # Both endpoints are in separate enclosed chambers. Discrete membership
    # and endpoint radii pass, but the straight connection crosses walls.
    p2, f2 = cube((4,0,0))
    vertices = np.vstack((p,p2)); faces = np.vstack((f,f2+len(p)))
    large = dict(geometry, size_xyz=[7,3,3])
    region = MeshRegion(vertices, faces, large)
    route = np.array([[1.,1.,1.],[5.,1.,1.]])
    distance = MeshClearance(vertices, faces).distance(route)[0]
    assert np.all(distance > .4)
    report, _ = audit_polyline(region, route, distance, required_radius_mm=.3, resolution_margin_mm=.1)
    assert report['point_failures'] == 0 and report['segment_failures'] == 1 and report['reviewed_prefix_points'] == 1
    tests.append(dict(name='inside_endpoints_do_not_bridge_disconnected_chambers',status='passed'))
    exterior = np.array([[3.,1.,1.],[3.,1.,1.1]])
    report, _ = audit_polyline(region, exterior, MeshClearance(vertices,faces).distance(exterior)[0],
                               required_radius_mm=.1, resolution_margin_mm=0.)
    assert not report['root_winding']['inside_unit_winding_region'] and report['reviewed_prefix_points'] == 0
    tests.append(dict(name='exterior_root_rejected_even_with_large_unsigned_distance',status='passed'))
    # A crop opening is never treated as unlimited free space above the scan.
    opened = np.delete(f, [2,3], axis=0); region = MeshRegion(p,opened,geometry)
    route = np.array([[1.,1.,1.],[1.,1.,3.]])
    report, _ = audit_polyline(region,route,MeshClearance(p,opened).distance(route)[0],
                               required_radius_mm=.1,resolution_margin_mm=0.)
    assert report['point_failures'] == 1 and report['reviewed_prefix_points'] == 1
    tests.append(dict(name='crop_opening_exit_blocked_without_fabricating_a_wall',status='passed'))
    # Removing a vertical face creates an opening at x=2 (a legitimate crop
    # plane); removing only one triangle leaves a nonplanar boundary: refuse.
    corruptions = [('orientation', np.vstack((f[:1,::-1],f[1:]))),
                   ('nonplanar_internal_hole', np.delete(f,[2,4],axis=0)),
                   ('duplicate_face', np.vstack((f,f[:1])))]
    for name, bad in corruptions:
        try: MeshRegion(p,bad,geometry)
        except ValueError: pass
        else: raise AssertionError(name+' accepted')
        tests.append(dict(name=name,status='rejected_as_expected'))
    angle = .37
    rot = np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1.]])
    origin = np.array([-12.,7.,-5.])
    gp = dict(geometry, origin_lps_mm=origin.tolist(),direction=rot.ravel().tolist())
    region = MeshRegion(p@rot.T+origin,opened,gp)
    assert region.root_winding((np.array([1.,1.,1.])@rot.T+origin))['inside_unit_winding_region']
    tests.append(dict(name='oblique_physical_affine_crop_and_winding',status='passed'))
    samples = np.r_[0.,np.linspace(1e-9,10000,100001),np.finfo(np.float32).max]
    rounded = round_down_float32(samples)
    assert np.all(rounded.astype(float) <= samples)
    tests.append(dict(name='100003_protocol_radii_never_round_up',status='passed'))
    for value in (np.array([np.nan]),np.array([-1.]),np.array([np.inf])):
        try:round_down_float32(value)
        except ValueError:pass
        else:raise AssertionError('Invalid radius accepted')
    tests.append(dict(name='nonfinite_negative_radii_refused',status='passed'))
    files = ['modules/surface_route/audit.py','modules/surface_route/test_audit.py',
             'modules/surface_quality/mesh_clearance.py']
    record = dict(status='continuous_surface_route_adversarial_geometry_tests_passed',cases=tests,
        source_sha256={n:hashlib.sha256((SYSTEM/n).read_bytes()).hexdigest() for n in files},
        platform=sys.platform,PL_access=False,production_changed=False,PS_Marching_Cubes_used=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(record['status'],len(tests))


if __name__ == '__main__':main()
