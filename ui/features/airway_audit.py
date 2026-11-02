"""Audit discarded airway fragments; never connect or replace the main mask.

The sparse PS KD-tree and existing C3 PL EDT implement the same physical
nearest-foreground distance. PL is an explicit benchmark option: sparse data
must not be forced through a slower dense transform in the production path.
"""
from pathlib import Path
import hashlib
import json
import sys
import time
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

SYSTEM = Path(__file__).resolve().parents[2]
POLICY = dict(max_distance_mm=3., min_voxels=8, max_voxels=512,
              probability=.70, confidence_fraction=.80, max_hu=-600,
              air_fraction=.90)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name+'.new')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    tmp.replace(path)


def validate_geometry(image, other):
    if image.GetDimension()!=3 or other.GetDimension()!=3 or image.GetNumberOfComponentsPerPixel()!=1 or other.GetNumberOfComponentsPerPixel()!=1:
        raise ValueError('Require scalar 3D CT/masks')
    if image.GetSize()!=other.GetSize() or any(not np.allclose(getattr(image,k)(),getattr(other,k)(),atol=1e-6,rtol=0)
            for k in ('GetSpacing','GetOrigin','GetDirection')):
        raise ValueError('Airway audit geometry mismatch; explicit resampling required')


def audit_arrays(raw, clean, ct, logits, metadata, image, *, backend='ps', session=None):
    """Return a separate candidate and report, with PS/PL distance provenance."""
    if backend not in ('ps','pl'): raise ValueError('Choose ps or pl distance backend')
    shape = tuple(reversed(image.GetSize()))
    if any(a.shape!=shape for a in (raw,clean,ct,logits)) or len(shape)!=3 or min(shape)<1:
        raise ValueError('Array/geometry shape mismatch')
    if raw.dtype!=bool or clean.dtype!=bool: raise ValueError('Binary boolean masks required')
    spacing=np.asarray(image.GetSpacing(),float); direction=np.asarray(image.GetDirection()).reshape(3,3)
    if not np.isfinite(spacing).all() or min(spacing)<=0 or not np.allclose(direction.T@direction,np.eye(3),atol=1e-6,rtol=0):
        raise ValueError('Positive spacing and orthonormal direction required')
    if logits.dtype!=np.dtype(metadata['dtype']) or logits.dtype not in (np.dtype('int8'),np.dtype('float32')):
        raise ValueError('Unsupported stored logit dtype')
    scale=float(metadata['scale']); zero=float(metadata['zero'])
    if not np.isfinite([scale,zero]).all() or scale<=0: raise ValueError('Invalid logit quantization')
    # Bound temporary arrays to one slice; preserve the zero-logit equality.
    for z in range(shape[0]):
        if not np.isfinite(logits[z]).all() or not np.isfinite(ct[z]).all(): raise ValueError('Non-finite CT/logits')
        if not np.array_equal(logits[z]>=zero,raw[z]): raise ValueError('Raw mask differs from recorded threshold')
    start=time.perf_counter()
    bounds=[]
    if raw.any() or clean.any():
        for axis in range(3):
            axes=tuple(j for j in range(3) if j!=axis)
            ids=np.flatnonzero(np.any(raw,axis=axes)|np.any(clean,axis=axes))
            bounds.append(slice(int(ids[0]),int(ids[-1])+1))
    region=tuple(bounds)
    labels,count=ndi.label(raw[region]&~clean[region],np.ones((3,3,3),np.uint8)) if bounds else (np.zeros((0,0,0),np.int32),0)
    local=np.argwhere(labels>0); ids=labels[tuple(local.T)] if len(local) else np.empty(0,np.int32)
    offset=np.array([s.start for s in bounds],int) if bounds else np.zeros(3,int)
    positions=local+offset
    label_seconds=time.perf_counter()-start
    physical=lambda p:(np.asarray(p)[:,::-1]*spacing)@direction.T
    gap=None; distance_stats=dict(backend=backend,computed=False,total_seconds=0.)
    begin=time.perf_counter()
    if len(positions) and clean.any():
        if backend=='ps':
            tree=cKDTree(physical(np.argwhere(clean[region])+offset))
            gap=tree.query(physical(positions),workers=1)[0]
            distance_stats=dict(backend='ps_sparse_kdtree',computed=True,total_seconds=time.perf_counter()-begin)
        else:
            if session is None: raise ValueError('Explicit checked DFX session required for PL')
            sys.path.insert(0,str(SYSTEM/'modules/navigation'))
            from pl.runtime import distance_transform, Q
            # Only main-airway voxels are zero. Padding with zero background
            # would invent a near airway at the image/crop boundary.
            field,stats=distance_transform(~clean[region],spacing[::-1],session)
            gap=np.asarray(field[tuple(local.T)],float); del field
            error2=.5/Q*sum((n-1)**2 for n in labels.shape)
            ambiguous=np.abs(gap*gap-POLICY['max_distance_mm']**2)<=error2+1e-3
            if ambiguous.any():
                tree=cKDTree(physical(np.argwhere(clean[region])+offset))
                gap[ambiguous]=tree.query(physical(positions[ambiguous]),workers=1)[0]
            distance_stats=dict(backend='dfx_pl_edt_q20',computed=True,total_seconds=time.perf_counter()-begin,
                                decision_boundary_exact_PS_queries=int(ambiguous.sum()),
                                squared_distance_error_bound_mm2=float(error2),edt=stats)
    rows=[]; candidate=clean.copy()
    values=(np.asarray(logits[tuple(positions.T)],np.float32)-zero)*scale if len(positions) else np.empty(0,np.float32)
    if not np.isfinite(values).all(): raise ValueError('Dequantized candidate logits are non-finite')
    hu=ct[tuple(positions.T)] if len(positions) else np.empty(0)
    high=values>=np.log(.70/.30)
    sizes=np.bincount(ids,minlength=count+1)
    confidence=np.bincount(ids,weights=high,minlength=count+1)
    air=np.bincount(ids,weights=hu<=-600,minlength=count+1)
    minima=np.full(count+1,np.inf)
    if gap is not None: np.minimum.at(minima,ids,gap)
    for number in range(1,count+1):
        take=ids==number; points=positions[take]; voxels=int(sizes[number])
        confident=float(confidence[number]/voxels); air_fraction=float(air[number]/voxels)
        distance=float(minima[number]) if np.isfinite(minima[number]) else None
        keep=bool(distance is not None and distance<=3. and 8<=voxels<=512 and confident>=.80 and air_fraction>=.90)
        if keep: candidate[tuple(points.T)]=True
        rows.append(dict(component=number,voxels=voxels,distance_to_main_mm=distance,
                         bounds_zyx=np.column_stack((points.min(0),points.max(0)+1)).tolist(),
                         confidence_ge_070_fraction=confident,hu_le_minus600_fraction=air_fraction,
                         median_probability=float(1/(1+np.exp(-np.clip(np.median(values[take]),-80,80)))),
                         retained_candidate=keep))
    result=dict(status='completed',policy='retain_nearby_confident_fragments_without_bridging_v1',
                raw_voxels=int(raw.sum()),baseline_voxels=int(clean.sum()),discarded_voxels=int(len(positions)),
                discarded_components=int(count),retained_components=sum(r['retained_candidate'] for r in rows),
                candidate_voxels=int(candidate.sum()),added_voxels=int((candidate&~clean).sum()),
                synthetic_bridge_voxels=0,original_mask_unchanged=True,thresholds=POLICY.copy(),components=rows,
                computation=dict(distance=distance_stats,components='PS scipy 26-connectivity',
                                 confidence_HU_statistics='PS sparse vectorized',label_seconds=label_seconds,
                                 arrays_total_seconds=time.perf_counter()-start),
                accuracy_note='Candidates are not manually verified branches; probability is not accuracy.')
    return candidate,result


def publish_audit(candidate, result, image, folder, output, metadata):
    """Save a verified in-memory candidate; input validation is the caller's job."""
    import SimpleITK as sitk
    folder=Path(folder).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    dest=output/'airway_mask_detail.nii.gz';temp=output/'airway_mask_detail.new.nii.gz'
    out=sitk.GetImageFromArray(candidate.astype(np.uint8));out.CopyInformation(image)
    sitk.WriteImage(out,str(temp),True);temp.replace(dest)
    result.update(mask_file=dest.name,mask_sha256=sha(dest),logits_sha256=metadata['sha256'],
                  input_sha256=metadata['input_sha256'],model_sha256=metadata['model_sha256'],
                  implementation_sha256=sha(Path(__file__)),raw_mask_sha256=sha(folder/'airway_mask_network.nii.gz'),
                  baseline_mask_sha256=sha(folder/'airway_mask.nii.gz'),default_mask_replaced=False)
    write_json(output/'airway_detail_report.json',result)
    return result


def audit_result(folder, ct_path, output=None, *, backend='ps', session=None):
    """Load and validate immutable inference inputs, then save separate evidence."""
    import SimpleITK as sitk
    folder=Path(folder).resolve(); ct_path=Path(ct_path).resolve()
    output=folder if output is None else Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    begin=time.perf_counter()
    metadata=json.loads((folder/'airway_logits.json').read_text(encoding='utf-8'))
    inference=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    logit_path=(folder/metadata['file']).resolve()
    if logit_path.parent!=folder or logit_path.name!=metadata['file']: raise ValueError('Invalid logit path')
    if metadata['input_sha256']!=sha(ct_path) or metadata['input_sha256']!=inference['input_sha256'] or metadata['model_sha256']!=inference['model_sha256']:
        raise ValueError('Logits do not belong to CT/model')
    if metadata['sha256']!=sha(logit_path): raise ValueError('Logit checksum mismatch')
    raw_path=folder/'airway_mask_network.nii.gz'; clean_path=folder/'airway_mask.nii.gz'
    raw_image=sitk.ReadImage(str(raw_path)); clean_image=sitk.ReadImage(str(clean_path)); image=sitk.ReadImage(str(ct_path))
    validate_geometry(image,raw_image); validate_geometry(image,clean_image)
    for method,key in [('GetSize','size_xyz'),('GetSpacing','spacing_xyz_mm'),('GetOrigin','origin_xyz_mm'),('GetDirection','direction')]:
        if not np.allclose(getattr(image,method)(),metadata[key],atol=1e-6,rtol=0): raise ValueError('Logit geometry mismatch')
    a=sitk.GetArrayFromImage(raw_image); b=sitk.GetArrayFromImage(clean_image)
    for z in range(len(a)):
        if np.any((a[z]!=0)&(a[z]!=1)) or np.any((b[z]!=0)&(b[z]!=1)): raise ValueError('Non-binary airway labels')
    raw=a>0; clean=b>0; del a,b
    logits=np.load(logit_path,mmap_mode='r',allow_pickle=False)
    candidate,result=audit_arrays(raw,clean,sitk.GetArrayFromImage(image),logits,metadata,image,backend=backend,session=session)
    if np.any(clean&~candidate) or np.any((candidate&~clean)&~raw): raise RuntimeError('Candidate invented/lost voxels')
    publish_audit(candidate,result,clean_image,folder,output,metadata)
    result['task_seconds']=time.perf_counter()-begin
    write_json(output/'airway_detail_report.json',result)
    return result


def append_display_masks(folder, image, packed, meta, input_sha):
    """Add optional comparison bits. Formal clean mask and geometry stay intact."""
    import SimpleITK as sitk
    folder=Path(folder);meta['airway_masks']={'clean':2};meta['airway_mask_notes']={}
    network=folder/'airway_mask_network.nii.gz';detail=folder/'airway_mask_detail.nii.gz'
    if network.exists():
        img=sitk.ReadImage(str(network))
        try:validate_geometry(image,img)
        except ValueError:
            meta['airway_mask_notes']['network']='Network grid differs; explicit resampling required.'
        else:
            values=sitk.GetArrayFromImage(img)
            for z in range(len(values)):
                if np.any((values[z]!=0)&(values[z]!=1)):raise ValueError('Non-binary network mask')
                packed[z]|=values[z].astype(np.uint8)*8
            meta['airway_masks']['network']=8
    report_path=folder/'airway_detail_report.json'
    if detail.exists() or report_path.exists():
        report=json.loads(report_path.read_text(encoding='utf-8'))
        if (report.get('status')!='completed' or report['input_sha256']!=input_sha or
                report['baseline_mask_sha256']!=sha(folder/'airway_mask.nii.gz') or
                report['raw_mask_sha256']!=sha(network) or report['mask_sha256']!=sha(detail) or
                report.get('synthetic_bridge_voxels')!=0 or report.get('default_mask_replaced') is not False):
            raise ValueError('Candidate airway evidence identity/policy mismatch')
        infer=json.loads((folder/'report.json').read_text(encoding='utf-8'))
        lm=json.loads((folder/'airway_logits.json').read_text(encoding='utf-8'))
        log_path=(folder/lm['file']).resolve()
        if (infer['input_sha256']!=input_sha or lm['input_sha256']!=input_sha or
                report['model_sha256']!=infer['model_sha256'] or report['model_sha256']!=lm['model_sha256'] or
                report['logits_sha256']!=lm['sha256'] or log_path.parent!=folder.resolve() or
                log_path.name!=lm['file'] or sha(log_path)!=lm['sha256']):
            raise ValueError('Candidate airway belongs to another model/logit volume')
        img=sitk.ReadImage(str(detail));validate_geometry(image,img);values=sitk.GetArrayFromImage(img)
        if 'network' not in meta['airway_masks']:raise ValueError('Candidate lacks matching network grid')
        added=0
        for z in range(len(values)):
            if np.any((values[z]!=0)&(values[z]!=1)):raise ValueError('Non-binary candidate mask')
            clean=(packed[z]&2)>0;raw=(packed[z]&8)>0;candidate=values[z]>0
            if np.any(clean&~candidate) or np.any((candidate&~clean)&~raw):raise ValueError('Candidate invented or lost airway voxels')
            added+=int(np.count_nonzero(candidate&~clean));packed[z]|=values[z].astype(np.uint8)*16
        if added!=report['added_voxels']:raise ValueError('Candidate voxel count disagrees with report')
        meta['airway_masks']['detail']=16
        meta['airway_detail']={k:report[k] for k in ('policy','retained_components','added_voxels','synthetic_bridge_voxels','default_mask_replaced')}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--input',type=Path,required=True);p.add_argument('--segmentation',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--backend',choices=['ps','pl'],default='ps');a=p.parse_args()
    if a.backend=='pl':
        sys.path.insert(0,str(SYSTEM/'dfx/medical'))
        from run_navigation import NavigationSession
        with NavigationSession() as s: report=audit_result(a.segmentation,a.input,a.output,backend='pl',session=s)
    else: report=audit_result(a.segmentation,a.input,a.output)
    print(json.dumps({k:report[k] for k in ('status','discarded_components','retained_components','added_voxels','task_seconds')}))
