"""Whole original raw-node profiles and Pareto paths on the active C1 surface.

All 26-neighbor source edges are retained before explicit geometric filtering.
The original weighted-profile rule and all-node/80-candidate/8-Pareto rule remain
unchanged. Actual triangle/crop/mask review replaces old-grid radius sampling.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import math
import sys
from time import perf_counter
import numpy as np
import SimpleITK as sitk
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'modules/navigation_comparison'))
from profile_r1 import Graph, graph, report as profile_report
from path_rules_r1 import resample_polyline, smooth_route_constrained, turn_cost, route_curvature
from pareto_r1 import select as pareto_select
from modules.surface_route.bundle_r8 import arrays, canonical, digest, unpack_scene
from modules.surface_route.verification_session_r15 import sha,verify_bundle
from modules.surface_route.guidance_r5 import ScalarField
from modules.surface_route.audit import MeshRegion, round_down_float32
from modules.surface_route.refine_r1 import _query, refine_segments
from modules.surface_route.replan_r1 import mask_segments_inside, review_curve
from modules.navigation.navigation.planner import densify
from modules.navigation.navigation.pipeline import load_prepared, choose_target


class MemoWall:
    """Bounded exact-coordinate reuse within one immutable mesh computation."""
    def __init__(self, base, capacity=200000):
        self.base, self.capacity = base, capacity
        self.values = {}
        self.requested = self.computed = self.calls = 0

    def distance(self, points):
        p = np.ascontiguousarray(points, '<f8')
        if p.ndim != 2 or p.shape[1:] != (3,) or not np.isfinite(p).all():
            raise ValueError('Finite physical query points required')
        keys = [row.tobytes() for row in p]
        missing = {}
        for i,key in enumerate(keys):
            if key not in self.values and key not in missing:
                missing[key] = i
        fresh = {}
        if missing:
            ids = list(missing.values())
            d = _query(self.base, p[ids])
            for key,value in zip(missing,d):
                fresh[key] = float(value)
                if len(self.values) < self.capacity:
                    self.values[key] = float(value)
            self.computed += len(ids)
            self.calls += 1
        result = np.asarray([self.values[key] if key in self.values else fresh[key] for key in keys],np.float64)
        self.requested += len(p)
        return result, None, None, dict(exact_coordinate_memoization=True)

    def metrics(self):
        return dict(requested_points=self.requested, computed_points=self.computed,
                    reused_exact_points=self.requested-self.computed,
                    retained_points=len(self.values), capacity=self.capacity,
                    rounded_or_approximate_point_keys=False)


@dataclass
class Query:
    diameter: float
    margin: float
    required: float
    threshold: float
    data: Graph
    root_passed: bool
    allowed_edges: np.ndarray
    edge_report: dict
    edge_arrays: dict


class Comparison:
    def __init__(self, centerline, target, field, region, oracle, *, binding):
        start = perf_counter()
        self.c, self.target, self.field, self.region, self.base = centerline,target,field,region,oracle
        self.binding = binding
        self.memo = MemoWall(oracle)
        coordinates = centerline.indices_zyx-centerline.offset_zyx
        self.raw = graph(coordinates, np.asarray(centerline.radii_mm,np.float64),centerline.root,
                         centerline.geometry.spacing_xyz[::-1])
        # Original voxel transform and original sorted node identities are kept.
        np.testing.assert_allclose(centerline.points_lps_mm,centerline.geometry.to_lps(centerline.indices_zyx),rtol=0,atol=1e-10)
        source = np.repeat(np.arange(len(coordinates)),np.diff(self.raw.rows.astype(np.int64)))
        pairs = np.sort(np.column_stack((source,self.raw.neighbors)),axis=1)
        self.edges,self.directed_to_edge = np.unique(pairs,axis=0,return_inverse=True)
        self.mask_edges = mask_segments_inside(centerline,centerline.points_lps_mm,segments=self.edges)
        self.node_wall = _query(self.memo,centerline.points_lps_mm)
        self.node_effective = np.minimum(self.node_wall,region.crop_clearance(centerline.points_lps_mm))
        self.node_inside = (field.sample(centerline.points_lps_mm)>0)&centerline.inside(centerline.points_lps_mm)
        self.resolution = centerline.resolution_margin_mm
        self.radii = round_down_float32(np.maximum(0.,self.node_effective-self.resolution-1e-6)).astype(np.float64)
        self.winding = region.root_winding(centerline.points_lps_mm[centerline.root])
        self.gaps = cKDTree(target.points_lps_mm).query(centerline.points_lps_mm)[0]
        self.preparation_seconds = perf_counter()-start

    @classmethod
    def from_bundle(cls,bundle,result,image,*,native=False):
        bundle,result,image = [Path(p).resolve() for p in (bundle,result,image)]
        if not all(p.is_relative_to(ROOT) for p in (bundle,result,image)):
            raise ValueError('Bound integration scene/result/CT required')
        meta = verify_bundle(bundle)
        bound = meta['identity']['provenance']['input_sha256']
        pipeline = json.loads((result/'pipeline.json').read_text(encoding='utf-8'))
        if (pipeline.get('status')!='passed' or pipeline.get('input_sha256')!=sha(image)
                or bound.get(image.relative_to(ROOT).as_posix())!=sha(image)):
            raise ValueError('Scene belongs to another CT')
        files = {}
        for name in ('segmentation/report.json','segmentation/airway_mask.nii.gz',
                     'segmentation/nodule_mask.nii.gz','navigation/centerline.json','navigation/centerline.npz'):
            p = result/name
            rel = p.relative_to(ROOT).as_posix()
            if bound.get(rel)!=sha(p):
                raise ValueError('Changed/different original result: '+name)
            files[rel] = sha(p)
        c = load_prepared(result/'navigation')
        route = json.loads((bundle/'route.json').read_text(encoding='utf-8'))
        target = choose_target(c,lesion_path=result/'segmentation/nodule_mask.nii.gz',
                               lesion_index=route['target']['index'])
        if target.metadata!=route['target']:
            raise ValueError('Active target differs')
        mesh = arrays(bundle/'mesh.npz')
        scalar,_ = unpack_scene((bundle/'scene_-1.bin').read_bytes())
        field = ScalarField(scalar,meta['geometry'],meta['bits'])
        region = MeshRegion(mesh['points'],mesh['faces'],meta['geometry'])
        if native:
            from modules.surface_quality.mesh_clearance_native import NativeMeshClearance
            base = NativeMeshClearance(mesh['points'],mesh['faces'])
            class FourThreads:
                def distance(self,p):return base.distance(p,threads=4)
            oracle = FourThreads()
        else:
            from modules.surface_quality.mesh_clearance_batch import BatchedMeshClearance
            oracle = BatchedMeshClearance(mesh['points'],mesh['faces'])
        binding = dict(revision=meta['revision'],route_id=meta['route_id'],scalar_sha256=field.sha256,
            mesh_sha256=sha(bundle/'mesh.npz'),bundle_metadata_sha256=sha(bundle/'scene.json'),
            CT_input_sha256=sha(image),source_result=str(result),source_files_sha256=files,
            target=target.metadata,centerline_id=c.metadata['centerline_id'],
            node_id_policy='complete_original_argwhere_order_no_leaf_substitution',
            topology_producer='PL_C1_binary_Marching_Cubes')
        return cls(c,target,field,region,oracle,binding=binding)

    def queries(self,diameters,margin):
        values = np.asarray(sorted(set(map(float,diameters))),np.float64)
        if (values.ndim!=1 or not 1<=len(values)<=64 or not np.isfinite(values).all()
                or np.any(values<=0) or not math.isfinite(margin) or margin<0):
            raise ValueError('Finite positive instrument diameters and nonnegative margin required')
        start = perf_counter()
        rows = []
        lookup = {tuple(edge):i for i,edge in enumerate(self.edges)}
        for diameter in values:
            required = max(diameter*.5,.1)+margin
            threshold = required+self.resolution
            report,details = refine_segments(self.region,self.c.points_lps_mm,self.edges,self.node_wall,
                                            self.memo,threshold_mm=threshold)
            allowed = details['accepted']&self.mask_edges&np.all(self.node_inside[self.edges],axis=1)
            directed = allowed[self.directed_to_edge]
            counts = np.bincount(np.repeat(np.arange(len(self.radii)),np.diff(self.raw.rows.astype(np.int64)))[directed],
                                 minlength=len(self.radii))
            csr = np.r_[0,np.cumsum(counts)].astype(np.uint32)
            half = []
            for offset,step,pairs in self.raw.half_edges:
                good = np.asarray([allowed[lookup[tuple(sorted(pair))]] for pair in pairs],bool)
                half.append((offset,step,pairs[good]))
            data = Graph(self.raw.coordinates_zyx,csr,self.raw.neighbors[directed].copy(),
                self.raw.lengths[directed].copy(),self.radii.copy(),self.raw.spacing_zyx,self.raw.root,tuple(half))
            root = self.raw.root
            root_passed = bool(self.node_inside[root] and self.winding['inside_unit_winding_region']
                               and self.node_effective[root]-1e-6>=threshold)
            report = dict(report,raw_source_edges=len(self.edges),geometry_mask_sign_allowed_edges=int(allowed.sum()),
                          source_mask_rejected_edges=int((~self.mask_edges).sum()),
                          source_field_sign_rejected_edges=int((~np.all(self.node_inside[self.edges],axis=1)).sum()))
            rows.append(Query(float(diameter),float(margin),float(required),float(threshold),data,root_passed,
                              allowed,report,details))
        self.query_preparation_seconds = perf_counter()-start
        return rows

    def produce(self,queries,distances,parents,*,minimum_bend_radius_mm=0.,candidate_slack_mm=4.):
        start = perf_counter()
        if not np.isfinite([minimum_bend_radius_mm,candidate_slack_mm]).all() or min(minimum_bend_radius_mm,candidate_slack_mm)<0:
            raise ValueError('Finite nonnegative original path options required')
        distances,parents = checked_outputs(queries,distances,parents)
        oracle = MemoWall(self.base)  # No result cache is shared across complete report trials.
        image = sitk.Image(list(map(int,self.c.mask.shape[::-1])),sitk.sitkUInt8)
        image.SetSpacing(tuple(self.c.geometry.spacing_xyz));image.SetDirection(tuple(self.c.geometry.direction))
        image.SetOrigin(tuple(self.c.geometry.to_lps(self.c.offset_zyx.reshape(1,3))[0]))
        tree = cKDTree(self.target.points_lps_mm)
        profiles,groups = [],[]
        saved = dict(diameters_mm=np.asarray([q.diameter for q in queries]),distances=distances,parents=parents,
                     raw_coordinates_zyx=self.raw.coordinates_zyx,node_wall_distance_mm=self.node_wall,
                     node_effective_distance_mm=self.node_effective,node_adjusted_radius_mm=self.radii,
                     raw_edges=self.edges,node_inside=self.node_inside)
        for gi,q in enumerate(queries):
            profile = profile_report(q.data,image,tree,[q.diameter],distances[gi:gi+1],parents[gi:gi+1])[0]
            profile.update(root_geometry_passed=q.root_passed,allowed_raw_edges=int(q.allowed_edges.sum()))
            profiles.append(profile)
            ids = np.flatnonzero(np.isfinite(distances[gi]))
            chosen_ids = ids[self.gaps[ids]<=float(self.gaps[ids].min())+candidate_slack_mm] if len(ids) else ids
            if len(chosen_ids)>80:
                chosen_ids = chosen_ids[np.argsort(self.gaps[chosen_ids])[:80]]
            records = []
            for node in chosen_ids:
                chain = [int(node)]
                while chain[-1]!=self.raw.root:
                    prior = int(parents[gi,chain[-1]])
                    if prior<0 or prior>=len(self.radii) or prior in chain:
                        raise ValueError('Invalid raw-node candidate parent chain')
                    chain.append(prior)
                chain.reverse()
                raw = self.c.points_lps_mm[chain]
                proposal = resample_polyline(raw,.8)
                if len(proposal)>4096:
                    raise ValueError('Candidate exceeds original route capacity; never downsample')
                _,nearest = cKDTree(raw).query(proposal)
                proposal = smooth_route_constrained(proposal,self.radii[np.asarray(chain)[nearest]])
                valid,audit,detail = review_curve(self.c,self.region,oracle,proposal,q.threshold)
                fallback = False
                if not valid:
                    proposal = densify(raw,min(.5,min(self.c.geometry.spacing_xyz)*.25))
                    if len(proposal)>4096:
                        raise ValueError('Candidate exceeds original route capacity; never downsample')
                    valid,audit,detail = review_curve(self.c,self.region,oracle,proposal,q.threshold)
                    fallback = True
                if not valid:
                    raise RuntimeError('Reviewed source graph path failed whole actual-wall review')
                conservative = np.maximum(0.,detail['effective_distance_mm']-1e-6)
                bounds = detail['accepted_lower_bound_mm']
                if len(bounds):
                    conservative[:-1] = np.minimum(conservative[:-1],bounds)
                    conservative[1:] = np.minimum(conservative[1:],bounds)
                radii = round_down_float32(np.maximum(0.,conservative-self.resolution)).astype(np.float64)
                bend = turn_cost(proposal)
                _,bend_radius = route_curvature(proposal)
                row = dict(candidate_id=len(records),endpoint_id=int(node),end_zyx=self.raw.coordinates_zyx[node].tolist(),
                    endpoint_xyz_mm=self.c.points_lps_mm[node].tolist(),gap_mm=float(self.gaps[node]),
                    bend_radians=float(bend),path_length_mm=float(np.linalg.norm(np.diff(proposal,axis=0),axis=1).sum()),
                    minimum_diameter_mm=float(2*radii.min()),minimum_bend_radius_mm=float(bend_radius),
                    score=float(distances[gi,node]+8.*self.gaps[node]+8.*bend),
                    original_diameter_bend_eligible=bool(2*radii.min()+1e-6>=q.diameter+2*q.margin
                        and (minimum_bend_radius_mm<=0 or bend_radius+1e-6>=minimum_bend_radius_mm)),
                    points_lps_mm=proposal.tolist(),radius_mm=radii.tolist(),whole_curve_actual_wall_review=audit,
                    unsafe_original_smoothing_replaced_by_reviewed_raw_path=fallback,
                    original_parent_node_ids=chain,root_only=len(chain)==1)
                records.append(row)
                prefix=f'profile_{gi}_candidate_{row["candidate_id"]}_'
                saved[prefix+'path_xyz']=proposal;saved[prefix+'path_zyx']=self.raw.coordinates_zyx[chain]
                saved[prefix+'radii']=radii;saved[prefix+'actual_wall_distance_mm']=detail['wall_distance_mm']
                saved[prefix+'conservative_actual_radius_mm']=conservative
            front = pareto_select(records)
            lookup = {tuple(r['endpoint_xyz_mm']):r['candidate_id'] for r in records}
            for row in front:
                row['candidate_id']=lookup[tuple(row['airway_endpoint_xyz_mm'])]
            eligible = [r for r in records if r['original_diameter_bend_eligible']]
            selected = min(eligible or records,key=lambda r:r['score'])['candidate_id'] if records else None
            for row in records:
                row['bend_radius_unbounded']=math.isinf(row['minimum_bend_radius_mm'])
                if row['bend_radius_unbounded']:row['minimum_bend_radius_mm']=None
            groups.append(dict(scope_diameter_mm=q.diameter,candidate_count=len(records),selected_candidate_id=selected,
                candidates=records,pareto=front,root_geometry_passed=q.root_passed,edge_review=q.edge_report,
                no_route_reason=None if records else 'active_surface_root_or_instrument_constraint'))
            saved[f'profile_{gi}_allowed_raw_edges']=q.allowed_edges
        common = dict(schema='kv260.surface_route.comparison.v1',binding=self.binding,
            raw_nodes=len(self.radii),raw_undirected_edges=len(self.edges),source_forest_edges=len(self.c.edges),
            cycles_preserved_before_explicit_geometry_filter=True,source_mask_or_graph_modified=False,
            resolution_margin_mm=self.resolution,radius_semantics='actual continuous-wall/crop lower bound minus one original resolution margin',
            minimum_bend_radius_mm=float(minimum_bend_radius_mm),safety_margin_mm=queries[0].margin,
            original_rules=dict(candidate_slack_mm=candidate_slack_mm,maximum_candidates=80,maximum_Pareto=8,
                                path_sample_mm=.8,gap_weight=8.,bend_weight=8.),
            audited_active_navigation_route_replaced=False,clinical_safety_certified=False,
            PS_Marching_Cubes_used=False,production_promoted=False,
            geometry_preparation_seconds=self.preparation_seconds,
            query_geometry_preparation_seconds=self.query_preparation_seconds,
            candidate_and_report_seconds=perf_counter()-start,exact_wall_query_reuse=oracle.metrics())
        whole = dict(common,kind='whole_original_raw_skeleton_on_active_surface',profiles=profiles)
        alternatives = dict(common,kind='all_reachable_nodes_on_active_surface',groups=groups)
        json.dumps(whole,allow_nan=False);json.dumps(alternatives,allow_nan=False)
        return whole,alternatives,saved


def checked_outputs(queries,distances,parents):
    if not queries:
        raise ValueError('At least one bound geometry query required')
    d,p = np.asarray(distances),np.asarray(parents)
    shape=(len(queries),len(queries[0].data.radii_mm))
    if any(len(q.data.radii_mm)!=shape[1] for q in queries):
        raise ValueError('All queries must retain the same original node identities')
    if d.shape!=shape or p.shape!=shape or d.dtype!=np.float64 or p.dtype!=np.int32 or np.isnan(d).any() or np.any(d<0):
        raise ValueError('Complete FP64 costs and int32 raw parent IDs required')
    d,p = d.copy(),p.copy()
    for i,q in enumerate(queries):
        if not q.root_passed:
            d[i]=np.inf;p[i]=-1
            continue
        ids=np.flatnonzero(np.isfinite(d[i]));nonroot=ids[ids!=q.data.root]
        if np.any(p[i,~np.isfinite(d[i])]!=-1):
            raise ValueError('Unreachable nodes must have no parent')
        if d[i,q.data.root]!=0 or p[i,q.data.root]!=-1 or np.any(p[i,nonroot]<0) or np.any(p[i,nonroot]>=shape[1]):
            raise ValueError('Invalid root or parent IDs')
        for child in nonroot:
            parent=int(p[i,child])
            first,last=map(int,q.data.rows[parent:parent+2])
            edges=np.flatnonzero(q.data.neighbors[first:last]==child)+first
            if len(edges)!=1 or not np.isfinite(d[i,parent]) or d[i,parent]>=d[i,child]:
                raise ValueError('Parent is not an allowed predecessor with smaller cost')
            radius=max(min(q.data.radii_mm[parent],q.data.radii_mm[child]),.2)
            scope_radius=max(q.diameter*.5,.1)
            expected=d[i,parent]+q.data.lengths[edges[0]]*(1.+2.*max(0.,scope_radius/radius-.65)**2)
            if radius+1e-9<q.required or abs(d[i,child]-expected)>1e-9:
                raise ValueError('Parent cost differs from the original weighted profile rule')
    return d,p


def solve_all(queries,provider):
    distances,parents=[],[]
    for query in queries:
        d,p=provider(query.data,[query.diameter],query.margin,2.)
        distances.append(d[0]);parents.append(p[0])
    return checked_outputs(queries,np.asarray(distances,np.float64),np.asarray(parents,np.int32))
