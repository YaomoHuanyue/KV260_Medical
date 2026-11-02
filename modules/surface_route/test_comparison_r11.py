"""Independent box distances, heap costs, raw-node and Pareto regression tests."""
from pathlib import Path
import argparse, heapq, json, math, os, sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.surface_route.comparison_r11 import Comparison, MemoWall, solve_all, checked_outputs
from modules.surface_route.test_audit import cube
from modules.surface_route.audit import MeshRegion
from modules.surface_route.guidance_r5 import ScalarField
from modules.surface_quality.mesh_clearance_batch import BatchedMeshClearance
from modules.navigation.navigation.geometry import Geometry
from modules.navigation.navigation.centerline import Centerline
from modules.navigation.navigation.planner import Target
from modules.surface_route.bundle_r8 import sha
from profile_session_r2 import ProfilePS
from legacy_pareto_r1 import _pareto_route_summaries


def heap_oracle(g,diameters,margin,weight):
    costs=np.full((len(diameters),len(g.radii_mm)),np.inf,np.float64)
    parents=np.full(costs.shape,-1,np.int32)
    for j,diameter in enumerate(diameters):
        scope=max(diameter/2.,.1);required=scope+margin
        costs[j,g.root]=0.;todo=[(0.,g.root)]
        while todo:
            cost,u=heapq.heappop(todo)
            if cost>costs[j,u]+1e-9:continue
            for edge in range(int(g.rows[u]),int(g.rows[u+1])):
                v=int(g.neighbors[edge]);r=max(min(g.radii_mm[u],g.radii_mm[v]),.2)
                if r+1e-9<required:continue
                ratio=scope/r;excess=max(0.,ratio-.65)
                value=cost+g.lengths[edge]*(1.+weight*(excess*excess))
                if value+1e-9<costs[j,v]:
                    costs[j,v]=value;parents[j,v]=u;heapq.heappush(todo,(value,v))
    return costs,parents


def fixture(indices=None,*,n=201):
    indices=np.asarray(indices if indices is not None else [[2,2,x] for x in range(n)],np.int32)
    shape=tuple((indices.max(axis=0)+3).tolist())
    g=Geometry(tuple(shape[::-1]),(1.,1.,1.),(-1.,-2.,-2.),tuple(np.eye(3).ravel()))
    mask=np.ones(shape,bool);points=g.to_lps(indices);count=len(points)
    c=Centerline(g,np.zeros(3,np.int32),mask,np.full(shape,100,np.float32),indices,points,
        np.full(count,100,np.float32),np.column_stack((np.arange(count-1),np.arange(1,count))).astype(np.int32),
        np.zeros(count,np.int32),0,dict(centerline_id='synthetic-original-node-order'))
    low=np.array([-5.,-5.,-5.]);high=np.array([max(5.,points[:,0].max()+5),5.,5.])
    vertices,faces=cube();vertices=low+vertices*(high-low)*.5
    mg=dict(size_xyz=[int(high[0]+7),13,13],spacing_xyz=[1.,1.,1.],origin_lps_mm=[-6.,-6.,-6.],direction=np.eye(3).ravel().tolist())
    region=MeshRegion(vertices,faces,mg);field=ScalarField(np.full(tuple(mg['size_xyz'][::-1]),32,np.int16),mg,5)
    oracle=BatchedMeshClearance(vertices,faces)
    target=Target('manual_point',points[[-1]]+np.array([1.,0.,0.]),{})
    return c,target,field,region,oracle,low,high


def verify_native_model():
    path=ROOT/'dfx/navigation_profile';platform='Windows' if os.name=='nt' else 'ARM'
    proof=json.loads((path/f'results/native_{platform}_build_r4.json').read_text())
    for name,expected in proof['source_sha256'].items():assert sha(path/name)==expected,name
    library=path/'build'/('profile_native_r4.dll' if os.name=='nt' else 'libprofile_native_r4.so')
    assert sha(library)==proof['library_sha256']
    sys.path.insert(0,str(path))
    from protocol_fast_r4 import NativeR4
    return NativeR4(),proof['library_sha256']


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    assert not args.output.exists()
    tests=[];cpu=ProfilePS();model,library_sha=verify_native_model()
    def compare(q):
        expected=solve_all(q,heap_oracle)
        for threads in (1,4):
            actual=solve_all(q,lambda g,d,m,w:cpu.solve(g,d,m,w,threads)[1:])
            for a,b in zip(actual,expected):np.testing.assert_array_equal(a,b)
        actual=solve_all(q,model.solve)
        for a,b in zip(actual,expected):np.testing.assert_array_equal(a,b)
        return expected
    c,t,f,r,o,low,high=fixture()
    random=np.random.default_rng(491).uniform(low-2,high+2,(300,3))
    outside=np.maximum(np.maximum(low-random,random-high),0.)
    expected=np.linalg.norm(outside,axis=1)
    inside=np.all((random>=low)&(random<=high),axis=1)
    expected[inside]=np.minimum(random[inside]-low,high-random[inside]).min(axis=1)
    np.testing.assert_allclose(o.distance(random)[0],expected,rtol=0,atol=2e-12)
    tests.append('triangle_oracle_matches_independent_inside_and_outside_box_formula')
    memo=MemoWall(o,capacity=2);p=c.points_lps_mm[:3]
    np.testing.assert_array_equal(memo.distance(np.vstack((p,p)))[0],np.tile(o.distance(p)[0],2))
    memo.distance(p);assert memo.metrics()['retained_points']==2 and memo.metrics()['computed_points']==4
    near=p[0].copy();near[0]=np.nextafter(near[0],np.inf)
    memo.distance(near[None]);assert memo.metrics()['computed_points']==5
    tests.append('bounded_memo_deduplicates_exact_coordinates_without_rounding')
    comp=Comparison(c,t,f,r,o,binding=dict(test='line_201'))
    assert np.all(comp.radii<6) and np.all(comp.radii<=comp.node_effective-comp.resolution)
    q=comp.queries([.2,1.,2.,8.,20.],.1);d,p=compare(q)
    whole,alternative,saved=comp.produce(q,d,p,candidate_slack_mm=100.)
    group=alternative['groups'][1];records=group['candidates']
    assert len(records)==80 and {row['endpoint_id'] for row in records}==set(range(121,201))
    assert sum(row['endpoint_id'] not in (0,200) for row in records)==79
    expected_front=_pareto_route_summaries(records)
    actual_front=[{k:v for k,v in row.items() if k!='candidate_id'} for row in group['pareto']]
    assert actual_front==expected_front and len(actual_front)<=8
    assert all(row['whole_curve_actual_wall_review']['whole_curve_accepted'] for row in records)
    assert all(0<=row['radius_mm'][0]<=comp.node_effective[0]-comp.resolution for row in records)
    assert not whole['profiles'][-1]['reachable'] and alternative['groups'][-1]['candidate_count']==0
    json.dumps(whole,allow_nan=False);json.dumps(alternative,allow_nan=False)
    tests.append('all_original_nodes_internal_endpoints_80_candidate_cap_8_Pareto_and_single_resolution_margin')
    bad=d.copy();bad[0,2]+=.01
    try:checked_outputs(q,bad,p)
    except ValueError:pass
    else:raise AssertionError('Corrupt weighted parent cost accepted')
    badp=p.copy();badp[0,2]=2
    try:checked_outputs(q,d,badp)
    except ValueError:pass
    else:raise AssertionError('Parent cycle accepted')
    tests.append('invalid_parent_cycle_and_corrupt_cost_are_refused')
    # Eight original 26-neighbor nodes have 28 undirected edges, not seven MST edges.
    indices=np.array([[z,y,x] for z in (2,3) for y in (2,3) for x in (2,3)],np.int32)
    c,t,f,r,o,_,_=fixture(indices)
    comp=Comparison(c,t,f,r,o,binding={});q=comp.queries([.2,1.],.1);compare(q)
    assert len(comp.edges)==28 and len(c.edges)==7 and np.all(q[0].allowed_edges)
    tests.append('raw_26_neighbor_cycles_preserved_and_PS1_PS4_R4_C_model_exact')
    # A diagonal segment can leave the source union even though both node cells are foreground.
    c.mask[:]=False
    for at in c.indices_zyx:c.mask[tuple(at)]=True
    c.mask[2,2,2]=False
    comp=Comparison(c,t,f,r,o,binding={});q=comp.queries([.2],0.);d,p=compare(q)
    assert not q[0].root_passed and not np.isfinite(d).any() and np.all(p==-1)
    tests.append('source_mask_root_failure_never_manufactures_zero_length_reachable_route')
    c,t,f,r,o,_,_=fixture(n=8)
    c.mask[:,:,3]=False
    comp=Comparison(c,t,f,r,o,binding={});q=comp.queries([.2],.1);d,p=compare(q)
    assert np.isfinite(d[0,:3]).all() and not np.isfinite(d[0,3:]).any()
    tests.append('background_source_mask_barrier_cannot_be_bridged')
    c,t,f,r,o,_,_=fixture(n=8)
    xyz=np.rint(((c.points_lps_mm-f.origin)@f.direction)/f.spacing).astype(int)
    f.values[tuple(xyz[4,::-1])]=-32
    comp=Comparison(c,t,f,r,o,binding={});q=comp.queries([.2],.1);d,p=compare(q)
    assert not np.isfinite(d[0,4:]).any()
    tests.append('active_scalar_negative_node_blocks_old_large_radius_route')
    for invalid in (([],.1),([float('nan')],.1),([1.],-.1),([0.],.1)):
        try:comp.queries(*invalid)
        except ValueError:pass
        else:raise AssertionError('Invalid constraints accepted')
    tests.append('invalid_queries_refused')
    names=['modules/surface_route/comparison_r11.py','modules/surface_route/test_comparison_r11.py',
           'modules/navigation_comparison/profile_ps_r1.cpp','modules/navigation_comparison/legacy_pareto_r1.py']
    proof=dict(status='independent_geometry_and_full_original_node_PS1_PS4_R4_C_model_tests_passed',
        platform=sys.platform,tests=tests,tests_passed=len(tests),PL_access=False,
        R4_C_model_library_sha256=library_sha,source_sha256={p:sha(ROOT/p) for p in names},production_promoted=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(proof['status'],len(tests),flush=True)


if __name__=='__main__':main()
