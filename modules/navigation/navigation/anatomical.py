"""Carina-anchored topology generations on a sparse, unchanged voxel skeleton.

Port of the original Python rules, using point-index arrays instead of a
whole-volume predecessor/distance field or repeated full-volume labels.
This is heuristic topology, not confirmed lobe/anatomical nomenclature.
"""
from pathlib import Path
import hashlib,heapq,json,math,time
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from .centerline import _edges


def adjacency(indices,shape,spacing):
    edges=_edges(indices,shape)
    delta=(indices[edges[:,0]]-indices[edges[:,1]])*spacing
    weights=np.sqrt(np.sum(delta*delta,axis=1))
    return coo_matrix((np.r_[weights,weights],(np.r_[edges[:,0],edges[:,1]],np.r_[edges[:,1],edges[:,0]])),shape=(len(indices),)*2).tocsr()


def groups(graph,active):
    ids=np.flatnonzero(active);labels=np.full(len(active),-1,np.int32)
    if len(ids): _,labels[ids]=connected_components(graph[ids][:,ids],directed=False)
    return labels


def prune(graph,root,threshold,max_iter=20):
    active=np.ones(graph.shape[0],bool);removed=0
    for _ in range(max_iter):
        degree=np.asarray(graph.astype(bool).dot(active.astype(np.int32))).ravel()
        to_remove=set()
        for ep in np.flatnonzero(active&(degree<=1)):
            if ep==root:continue
            path=[int(ep)];prev=-1;cur=int(ep);length=0.;junction=False
            while True:
                if cur!=ep and degree[cur]>=3:junction=True;break
                begin,end=graph.indptr[cur:cur+2];nb=graph.indices[begin:end];w=graph.data[begin:end]
                valid=active[nb]&(nb!=prev);nb=nb[valid];w=w[valid]
                if not len(nb):break
                if len(nb)>1:junction=True;break
                length+=float(w[0]);prev,cur=cur,int(nb[0]);path.append(cur)
                if length>=threshold:break
            if junction and length<threshold:to_remove.update(p for p in path[:-1] if p!=root)
        if not to_remove:break
        active[list(to_remove)]=False;removed+=len(to_remove)
    labels=groups(graph,active);active&=labels==labels[root]
    return active,removed


def distances(graph,active,root):
    # Stable original heap tie ordering, with original 1e-9 comparison epsilon.
    distance=np.full(len(active),np.inf);parent=np.full(len(active),-1,np.int32)
    distance[root]=0.;heap=[(0.,int(root))]
    while heap:
        d,p=heapq.heappop(heap)
        if d!=distance[p]:continue
        for j in range(graph.indptr[p],graph.indptr[p+1]):
            q=int(graph.indices[j])
            if not active[q]:continue
            nd=d+float(graph.data[j])
            if nd+1e-9<distance[q]:distance[q]=nd;parent[q]=p;heapq.heappush(heap,(nd,q))
    return distance,parent


def analyze(c,*,max_display=7,min_spur_mm=4.,min_trachea_mm=20.,carina_child_mm=20.,min_child_mm=5.):
    start=time.perf_counter();coords=np.asarray(c.indices_zyx);n=len(coords)
    if coords.shape!=(n,3) or n<1 or not np.issubdtype(coords.dtype,np.integer) or not 0<=c.root<n:
        raise ValueError('Invalid indexed skeleton/root')
    shape=tuple(c.geometry.size_xyz[::-1]);spacing=np.asarray(c.geometry.spacing_xyz[::-1],float)
    linear=np.ravel_multi_index(coords.T,shape)
    if np.any(np.diff(linear)<=0):raise ValueError('Require unique raster-ordered skeleton indices')
    if not np.allclose(c.geometry.to_lps(coords),c.points_lps_mm,atol=1e-6,rtol=0):raise ValueError('Skeleton physical geometry mismatch')
    values=[min_spur_mm,min_trachea_mm,carina_child_mm,min_child_mm]
    if not np.isfinite(values).all() or min(values)<0 or not isinstance(max_display,int) or not 0<=max_display<=32767:
        raise ValueError('Invalid generation policy')
    graph=adjacency(coords,shape,spacing);active,removed=prune(graph,c.root,min_spur_mm)
    degree=np.asarray(graph.astype(bool).dot(active.astype(np.int32))).ravel()
    junction=active&(degree>=3);labels=groups(graph,junction)+1
    labels[~junction]=0
    distance,parent=distances(graph,active,c.root)
    infos=[]
    for label in sorted(set(labels[labels>0])):
        cluster=labels==label;outside=active&~cluster;component=groups(graph,outside)+1;component[~outside]=0
        border=(np.asarray(graph.astype(bool).dot(cluster.astype(np.int32))).ravel()>0)&outside
        root_component=int(component[c.root]);center=coords[cluster].mean(0);children=[];has_parent=False
        for number in sorted(set(component[border])):
            if number==0:continue
            if number==root_component:has_parent=True;continue
            ids=np.flatnonzero(component==number);delta=(coords[ids]-center)*spacing
            children.append(dict(component=int(number),extent_mm=float(np.linalg.norm(delta,axis=1).max()),voxels=len(ids)))
        infos.append(dict(label=int(label),root_distance_mm=float(distance[cluster].min()),parent_component_present=has_parent,children=children))
    infos.sort(key=lambda row:row['root_distance_mm']);carina=None;method='none'
    for threshold,name in [(carina_child_mm,'major_children'),(min_child_mm,'nontrivial_children_fallback')]:
        for row in infos:
            if row['root_distance_mm']>=min_trachea_mm and sum(v['extent_mm']>=threshold for v in row['children'])>=2:
                carina=row;method=name;break
        if carina is not None:break
    if carina is None and infos:carina=infos[0];method='earliest_junction_unqualified_fallback'
    significant=set()
    if carina is not None:
        significant.add(carina['label'])
        for row in infos:
            if row['root_distance_mm']>carina['root_distance_mm']+1e-6 and sum(v['extent_mm']>=min_child_mm for v in row['children'])>=2:
                significant.add(row['label'])
    generation=np.full(n,-1,np.int16);generation[c.root]=0
    for p in np.argsort(distance):
        if p==c.root or not active[p] or not np.isfinite(distance[p]):continue
        prev=parent[p]
        if prev<0 or generation[prev]<0:continue
        step=int(labels[prev] in significant and labels[p]!=labels[prev])
        generation[p]=min(int(generation[prev])+step,max_display)
    valid=active&(generation>=0);carina_points=coords[labels==carina['label']] if carina else np.empty((0,3))
    carina_center=carina_points.mean(0) if len(carina_points) else None
    result=dict(schema='kv260.navigation.anatomical_generations.v1',status='completed',
                kind='carina_anchored_heuristic_topology_not_confirmed_anatomical_names',root_point_id=int(c.root),
                root_selection='existing_navigation_root_preserved',root_lps_mm=c.points_lps_mm[c.root].tolist(),
                root_radius_mm=float(c.radii_mm[c.root]),carina_selection=method,
                carina_center_zyx=None if carina_center is None else carina_center.tolist(),
                carina_lps_mm=None if carina_center is None else c.geometry.to_lps(carina_center).tolist(),
                carina_root_distance_mm=None if carina is None else carina['root_distance_mm'],
                carina_label=None if carina is None else carina['label'],junctions=infos,
                significant_junction_labels=sorted(significant),significant_junction_count=len(significant),raw_junction_cluster_count=len(infos),
                removed_short_spur_skeleton_voxels=int(removed),analyzed_skeleton_points=int(valid.sum()),
                excluded_skeleton_points=int((~valid).sum()),max_generation_displayed=int(generation[valid].max()),
                skeleton_voxels_by_generation={str(g):int((generation==g).sum()) for g in range(max_display+1)},
                parameters=dict(max_display=max_display,min_spur_mm=min_spur_mm,min_trachea_mm=min_trachea_mm,carina_child_mm=carina_child_mm,min_child_mm=min_child_mm),
                computation=dict(topology='PS_sparse_graph',distance_transform=c.metadata.get('distance_transform'),seconds=time.perf_counter()-start),
                centerline_id=c.metadata.get('centerline_id'),input_sha256=c.metadata.get('input_sha256'),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                original_mask_changed=False,navigation_graph_changed=False,
                warnings=['Heuristic generation counts depend on segmentation and root; no confirmed lobe names.',
                          'Unqualified fallback carina must not be presented as a robust detected carina.'])
    return dict(generation=generation,active=valid,junction_labels=labels,root_distance_mm=distance),result


def save(c,output,**options):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    arrays,report=analyze(c,**options)
    data=output/'anatomical_generations.npz';tmp=output/'anatomical_generations.new.npz'
    np.savez_compressed(tmp,**arrays,indices_zyx=c.indices_zyx);tmp.replace(data)
    report['file']=data.name;report['data_sha256']=hashlib.sha256(data.read_bytes()).hexdigest()
    path=output/'anatomical_generations.json';tmp=path.with_suffix('.json.new')
    tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(path)
    np.savetxt(output/'anatomical_generation_nodes.csv',np.column_stack((np.arange(len(c.points_lps_mm)),c.points_lps_mm,arrays['generation'],arrays['active'].astype(int))),
               delimiter=',',header='point_id,lps_x_mm,lps_y_mm,lps_z_mm,generation,active_after_topology_spur_audit',comments='',fmt=['%d','%.9g','%.9g','%.9g','%d','%d'])
    return report
