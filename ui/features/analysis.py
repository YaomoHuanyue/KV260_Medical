"""Physical-space candidate catalogue, surface attributes and route HUD."""
from pathlib import Path
import json
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

def physical(zyx, image):
    q=np.asarray(zyx,dtype=float)[...,::-1]*np.asarray(image.GetSpacing())
    return q @ np.asarray(image.GetDirection()).reshape(3,3).T + np.asarray(image.GetOrigin())

def candidates(mask, image):
    """Use exactly the planner's 26-connectivity and volume/id ordering."""
    if not np.any(mask):return []
    extent=[np.flatnonzero(np.any(mask,axis=tuple(j for j in range(3) if j!=i))) for i in range(3)]
    offset=np.array([a[0] for a in extent]);end=np.array([a[-1]+1 for a in extent])
    crop=mask[tuple(slice(a,b) for a,b in zip(offset,end))]
    labels,count=ndi.label(crop,np.ones((3,3,3),np.uint8))
    sizes=np.bincount(labels.ravel());boxes=ndi.find_objects(labels);rows=[]
    for rank,label in enumerate(sorted(range(1,count+1),key=lambda i:(-sizes[i],i))):
        box=boxes[label-1];component=labels[box]==label
        lower=offset+np.array([s.start for s in box]);upper=offset+np.array([s.stop-1 for s in box])
        center=physical(np.asarray(ndi.center_of_mass(component))+lower,image)
        bounds=np.array([physical([z,y,x],image) for z in (lower[0],upper[0]) for y in (lower[1],upper[1]) for x in (lower[2],upper[2])])
        rows.append(dict(index=rank,voxel_count=int(sizes[label]),volume_mm3=float(sizes[label]*np.prod(image.GetSpacing())),
            centroid_lps_mm=center.tolist(),bounds_min=bounds.min(axis=0).tolist(),bounds_max=bounds.max(axis=0).tolist(),
            label_status='model_candidate_not_confirmed_lesion'))
    return rows

def bend_radii(points):
    """Discrete turn radius on the sampled curve; not a contact/elastic model."""
    p=np.asarray(points,dtype=float)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all():raise ValueError('Invalid route coordinates')
    result=np.full(len(p),np.inf)
    if len(p)>2:
        d=np.diff(p,axis=0);length=np.linalg.norm(d,axis=1)
        good=(length[:-1]>1e-8)&(length[1:]>1e-8)
        angle=np.arccos(np.clip(np.sum(d[:-1]*d[1:],axis=1)/np.maximum(length[:-1]*length[1:],1e-20),-1,1))
        curved=good&(angle>1e-6)
        radius=np.full(len(angle),np.inf)
        radius[curved]=.5*(length[:-1][curved]+length[1:][curved])/angle[curved]
        result[1:-1]=radius
    return result

def route_hud(points, arc, radii, report, lookahead_mm=10.):
    p=np.asarray(points);a=np.asarray(arc,float);r=np.asarray(radii,float)
    if p.shape!=(len(a),3) or r.shape!=a.shape or not np.isfinite(np.r_[a,r]).all() or np.any(r<0) or np.any(np.diff(a)<0):
        raise ValueError('Route HUD requires ordered finite physical samples')
    resolution=float(report.get('resolution_margin_mm',0.));required=float(report.get('required_radius_mm',0.))
    adjusted=np.maximum(0,r-resolution);br=bend_radii(p);rows=[]
    threshold=float(report.get('minimum_bend_radius_mm',0.))
    for i in range(len(a)):
        end=max(i+1,int(np.searchsorted(a,a[i]+lookahead_mm,side='right')))
        minimum=float(adjusted[i:end].min());spare=minimum-required
        finite=br[i:end][np.isfinite(br[i:end])];bend=float(finite.min()) if len(finite) else None
        state='blocked' if spare < -1e-5 or (threshold>0 and bend is not None and bend+1e-5<threshold) else ('caution' if spare<.4 else 'clear')
        rows.append(dict(current_diameter_mm=float(2*r[i]),forward_adjusted_diameter_mm=2*minimum,
            spare_radius_mm=spare,forward_minimum_bend_radius_mm=bend,state=state))
    return dict(lookahead_mm=float(lookahead_mm),samples=rows,kind='segmentation_geometry_estimate')

def navigation_hud(route_path,report):
    with np.load(route_path,allow_pickle=False) as data:
        if 'route_audit' in report:
            import sys
            sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'dfx/route_audit_speed'))
            from protocol import hud_from_pl
            return hud_from_pl(data,report)
        # Previously successful legacy results keep their explicitly labelled
        # PS HUD. A malformed protocol-3 result never falls back to PS.
        hud=route_hud(data['points_lps_mm'],data['arc_mm'],data['radius_mm'],report)
        hud['computation']='ps_legacy_result'
        return hud

def surface_attributes(result, image, mesh, destination, input_sha):
    """Sparse nearest-centerline assignment, with unconnected points flagged."""
    result=Path(result);nav=result/'navigation';destination=Path(destination)
    if not (nav/'centerline.npz').exists() or not (nav/'branches.json').exists():return None
    meta=json.loads((nav/'centerline.json').read_text(encoding='utf-8'))
    import hashlib
    if meta.get('input_sha256')!=hashlib.sha256((result/'segmentation/airway_mask.nii.gz').read_bytes()).hexdigest():
        raise ValueError('Surface attributes belong to another airway mask')
    with np.load(nav/'centerline.npz',allow_pickle=False) as c:
        points=np.asarray(c['points_lps_mm']);radius=np.asarray(c['radii_mm']);components=np.asarray(c['components']);root=int(c['root'])
    if points.ndim!=2 or points.shape[1]!=3 or len(radius)!=len(points) or len(components)!=len(points) or not len(points) or not np.isfinite(points).all() or not np.isfinite(radius).all() or np.any(radius<0) or root<0 or root>=len(points):
        raise ValueError('Invalid centerline attributes')
    tree=cKDTree(points);generation=np.full(len(points),-1.,np.float32)
    generation_tree=None;anatomical_values=None;anatomical_report=None
    anatomy_path=nav/'anatomical_generations.json'
    if anatomy_path.exists():
        anatomical_report=json.loads(anatomy_path.read_text(encoding='utf-8'))
        path=(nav/anatomical_report['file']).resolve()
        if (anatomical_report.get('schema')!='kv260.navigation.anatomical_generations.v1' or anatomical_report.get('status')!='completed' or
                anatomical_report['input_sha256']!=meta['input_sha256'] or anatomical_report['centerline_id']!=meta['centerline_id'] or
                path.parent!=nav.resolve() or path.name!=anatomical_report['file'] or
                hashlib.sha256(path.read_bytes()).hexdigest()!=anatomical_report['data_sha256']):raise ValueError('Anatomical generation identity mismatch')
        with np.load(path,allow_pickle=False) as data:
            active=data['active'];g=data['generation'];indices=data['indices_zyx']
        with np.load(nav/'centerline.npz',allow_pickle=False) as data:expected_indices=data['indices_zyx']
        with np.load(nav/'centerline.npz',allow_pickle=False) as data:
            identity=hashlib.sha256(points.tobytes()+data['edges'].tobytes()+str(root).encode()).hexdigest()
        if identity!=meta['centerline_id']:raise ValueError('Anatomical centerline data identity mismatch')
        maximum=anatomical_report['parameters']['max_display']
        if (not isinstance(maximum,int) or isinstance(maximum,bool) or maximum<0 or maximum>32767 or
                active.shape!=(len(points),) or active.dtype!=bool or g.shape!=active.shape or g.dtype!=np.int16 or
                not np.array_equal(indices,expected_indices) or not active[root] or g[root]!=0 or
                np.any(g[active]<0) or np.any(g[active]>maximum) or np.any(g[~active]!=-1) or
                int(active.sum())!=anatomical_report['analyzed_skeleton_points']):raise ValueError('Invalid anatomical generation arrays')
        generation_tree=cKDTree(points[active]);anatomical_values=g[active]
    branches=json.loads((nav/'branches.json').read_text(encoding='utf-8'))['branches']
    for branch in sorted(branches,key=lambda b:b.get('generation') if b.get('generation') is not None else 1e9,reverse=True):
        ids=np.asarray(branch['point_ids'],np.int64)
        if np.any(ids<0) or np.any(ids>=len(points)):raise ValueError('Branch references an invalid point')
        if branch.get('generation') is not None:generation[ids]=branch['generation']
    logits=None;log_meta=None;confidence_note='unavailable'
    lm=result/'segmentation/airway_logits.json'
    if lm.exists():
        log_meta=json.loads(lm.read_text(encoding='utf-8'))
        path=result/'segmentation'/log_meta['file']
        if path.parent.resolve()!=lm.parent.resolve() or log_meta.get('input_sha256')!=input_sha:raise ValueError('Confidence belongs to another CT')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=log_meta['sha256']:raise ValueError('Confidence checksum mismatch')
        logits=np.load(path,mmap_mode='r',allow_pickle=False)
        if tuple(logits.shape[::-1])!=tuple(image.GetSize()) or any(not np.allclose(a,b,atol=1e-6,rtol=0) for a,b in [(log_meta['origin_xyz_mm'],image.GetOrigin()),(log_meta['spacing_xyz_mm'],image.GetSpacing()),(log_meta['direction'],image.GetDirection())]):raise ValueError('Confidence/CT geometry mismatch')
        if not np.isfinite(log_meta['scale']) or log_meta['scale']<=0 or not np.isfinite(log_meta['zero']):raise ValueError('Invalid confidence quantization')
        confidence_note='network_probability_not_accuracy'
    size=Path(mesh).stat().st_size
    if size%24:raise ValueError('Truncated surface mesh stream')
    stream=np.memmap(mesh,dtype='<f4',mode='r').reshape(-1,6) if size else np.empty((0,6),np.float32)
    with destination.open('wb') as output:
        for start in range(0,len(stream),16384):
            positions=np.asarray(stream[start:start+16384,:3]);_,ids=tree.query(positions,workers=1)
            displayed_generation=generation[ids]
            if generation_tree is not None:
                _,anatomical_ids=generation_tree.query(positions,workers=1)
                displayed_generation=anatomical_values[anatomical_ids]
            confidence=np.full(len(ids),-1.,np.float32)
            if logits is not None:
                direction=np.asarray(log_meta['direction']).reshape(3,3)
                xyz=(positions-np.asarray(log_meta['origin_xyz_mm'])) @ np.linalg.inv(direction).T / np.asarray(log_meta['spacing_xyz_mm'])
                ijk=np.rint(xyz[:,::-1]).astype(int);valid=np.all((ijk>=0)&(ijk<np.asarray(logits.shape)),axis=1)
                value=(logits[tuple(ijk[valid].T)].astype(np.float32)-log_meta['zero'])*log_meta['scale']
                confidence[valid]=1/(1+np.exp(-np.clip(value,-80,80)))
            np.column_stack((displayed_generation,radius[ids],confidence,(components[ids]==components[root]).astype(float))).astype('<f4').tofile(output)
    return dict(file=destination.name,vertices=len(stream),confidence_available=logits is not None,
        confidence_note=confidence_note,generation_kind='rooted_branch_depth_not_anatomical_label' if anatomical_report is None else anatomical_report['kind'],
        anatomical_generation=anatomical_report,
        branches=branches,total_length_mm=float(sum(b['length_mm'] for b in branches)))

def enrich_scene(result, image, meta, cache, input_sha):
    import SimpleITK as sitk
    result=Path(result);cache=Path(cache)
    mi=sitk.ReadImage(str(result/'segmentation/nodule_mask.nii.gz'))
    if mi.GetSize()!=image.GetSize() or any(not np.allclose(a,b,atol=1e-6,rtol=0) for a,b in [(mi.GetSpacing(),image.GetSpacing()),(mi.GetOrigin(),image.GetOrigin()),(mi.GetDirection(),image.GetDirection())]):raise ValueError('Candidate/CT geometry mismatch')
    meta['candidates']=candidates(sitk.GetArrayFromImage(mi)>0,image)
    if 'airway' in meta['meshes']:
        item=meta['meshes']['airway'];attributes=surface_attributes(result,image,cache/item['file'],cache/'airway.attributes',input_sha)
        if attributes:item['attributes']=attributes
    nav=meta.get('navigation')
    if nav:
        nav['hud']=navigation_hud(result/'navigation/route.npz',nav['report'])
        for name in ('instrument_profiles','alternative_routes'):
            path=result/'navigation'/(name+'.json')
            if path.exists():nav[name]=json.loads(path.read_text(encoding='utf-8'))
