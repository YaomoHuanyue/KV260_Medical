"""Save inference evidence and audit discarded components without inventing links."""
from pathlib import Path
import json
import os
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from .ct_segmentation import require_geometry, sha256, write_json, write_like


class LogitRecorder:
    """One airway head, disk-backed; no additional inference or float volume."""
    def __init__(self, folder, image):
        self.folder = Path(folder)
        self.image = image
        self.data = None
        self.parameters = None
        self.seen = np.zeros(image.GetSize()[2], bool)

    def record(self, z, prediction):
        from ct_pl.quantized_runtime import Quantized
        if isinstance(prediction, Quantized):
            if prediction.scale.size != 1 or prediction.zero.size != 1:
                raise ValueError('Airway recording requires scalar output quantization')
            parameters = dict(dtype='int8', scale=float(prediction.scale.item()),
                              zero=int(prediction.zero.item()))
            value = prediction.data[0, 1]
        else:
            parameters = dict(dtype='float32', scale=1., zero=0)
            value = prediction[0, 1]
        if self.parameters is not None and parameters != self.parameters:
            raise ValueError('Output quantization changed across slices')
        if self.data is None:
            self.parameters = parameters
            self.data = np.lib.format.open_memmap(self.folder/'airway_logits.npy.tmp',
                mode='w+', dtype=parameters['dtype'], shape=tuple(reversed(self.image.GetSize())))
        h, w = self.data.shape[1:]
        self.data[z] = value[:h, :w]
        self.seen[z] = True

    def finish(self, input_sha256, model_sha256):
        if self.data is None or not self.seen.all():
            raise ValueError('Incomplete airway logit volume')
        self.data.flush()
        del self.data
        self.data = None
        target = self.folder/'airway_logits.npy'
        (self.folder/'airway_logits.npy.tmp').replace(target)
        metadata = dict(status='completed', file=target.name,
            sha256=sha256(target), **self.parameters,
            formula='logit = (stored - zero) * scale; probability = sigmoid(logit)',
            size_xyz=list(self.image.GetSize()), spacing_xyz_mm=list(self.image.GetSpacing()),
            origin_xyz_mm=list(self.image.GetOrigin()), direction=list(self.image.GetDirection()),
            input_sha256=input_sha256, model_sha256=model_sha256,
            bytes=target.stat().st_size, metric_kind='model_confidence_not_ground_truth')
        write_json(self.folder/'airway_logits.json', metadata)
        return metadata


def audit_airway(folder, ct_path):
    """Retain only high-confidence nearby fragments; no dilation or gap filling.

    The output is explicitly a candidate, not a new default or validated branch.
    Distances use CT physical spacing. Strict limits reject broad leakage.
    """
    folder = Path(folder)
    metadata = json.loads((folder/'airway_logits.json').read_text(encoding='utf-8'))
    report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    if metadata['input_sha256'] != sha256(ct_path) or metadata['model_sha256'] != report['model_sha256']:
        raise ValueError('Logits do not belong to this CT/model')
    if metadata['sha256'] != sha256(folder/metadata['file']):
        raise ValueError('Logit checksum mismatch')
    raw_image = sitk.ReadImage(str(folder/'airway_mask_network.nii.gz'))
    clean_image = sitk.ReadImage(str(folder/'airway_mask.nii.gz'))
    require_geometry(raw_image, clean_image)
    if any(not np.allclose(getattr(raw_image, method)(), metadata[key], rtol=0, atol=1e-6)
           for method, key in [('GetSize','size_xyz'),('GetSpacing','spacing_xyz_mm'),
                               ('GetOrigin','origin_xyz_mm'),('GetDirection','direction')]):
        raise ValueError('Logit/mask geometry differs; explicit resampling is required')
    ct_image = sitk.ReadImage(str(ct_path)); require_geometry(raw_image, ct_image)
    raw = sitk.GetArrayFromImage(raw_image).astype(bool)
    clean = sitk.GetArrayFromImage(clean_image).astype(bool)
    ct = sitk.GetArrayFromImage(ct_image)
    logits = np.load(folder/metadata['file'], mmap_mode='r', allow_pickle=False)
    if logits.shape != raw.shape or logits.dtype != np.dtype(metadata['dtype']):
        raise ValueError('Invalid stored logits')
    if not np.array_equal(logits >= metadata['zero'], raw):
        raise ValueError('Raw network mask differs from stored zero-logit threshold')
    removed = raw & ~clean
    # Crop labels and use exact nearest-neighbour queries on the sparse main
    # airway. A whole-volume float64 distance field wastes RAM and seconds.
    bounds=[]
    support=raw | clean
    if support.any():
        for axis in range(3):
            indices=np.flatnonzero(np.any(support,axis=tuple(i for i in range(3) if i!=axis)))
            bounds.append(slice(int(indices[0]),int(indices[-1])+1))
    region=tuple(bounds)
    labels,count=ndi.label(removed[region],np.ones((3,3,3),np.uint8)) if bounds else (np.zeros((0,0,0),np.uint8),0)
    objects=ndi.find_objects(labels)
    spacing=np.asarray(raw_image.GetSpacing())
    direction=np.asarray(raw_image.GetDirection()).reshape(3,3)
    physical=lambda zyx:(np.asarray(zyx)[:,::-1]*spacing)@direction.T
    main_positions=np.argwhere(clean)
    tree=cKDTree(physical(main_positions)) if len(main_positions) else None
    candidate=clean.copy(); rows=[]
    threshold=np.log(.70/.30)
    for number, local_box in enumerate(objects, 1):
        if local_box is None: continue
        component=labels[local_box]==number
        box=tuple(slice(s.start+b.start,s.stop+b.start) for s,b in zip(local_box,bounds))
        values=(np.asarray(logits[box][component],np.float32)-metadata['zero'])*metadata['scale']
        hu=ct[box][component]
        positions=np.argwhere(component)+np.array([s.start for s in box])
        gap=float(tree.query(physical(positions),workers=1)[0].min()) if tree is not None else None
        voxels=int(component.sum())
        confident=float(np.mean(values>=threshold)); air_fraction=float(np.mean(hu<=-600))
        # A candidate stays disconnected. A thin bridge needs stronger evidence
        # and separate validation; morphology must not manufacture that evidence.
        keep=bool(gap is not None and gap<=3.0 and 8<=voxels<=512 and confident>=.80 and air_fraction>=.90)
        if keep: candidate[box] |= component
        rows.append(dict(component=number, voxels=voxels, distance_to_main_mm=gap,
            bounds_zyx=[[s.start,s.stop] for s in box],
            confidence_ge_070_fraction=confident, hu_le_minus600_fraction=air_fraction,
            median_probability=float(1/(1+np.exp(-np.clip(np.median(values),-80,80)))),
            retained_candidate=keep))
    temporary=folder/f'airway_mask_detail.{os.getpid()}.tmp.nii.gz'
    write_like(candidate.astype(np.uint8), clean_image, temporary)
    temporary.replace(folder/'airway_mask_detail.nii.gz')
    result=dict(status='completed', policy='retain_nearby_confident_fragments_without_bridging_v1',
        raw_voxels=int(raw.sum()), baseline_voxels=int(clean.sum()),
        discarded_voxels=int(removed.sum()), discarded_components=int(count),
        retained_components=sum(r['retained_candidate'] for r in rows),
        candidate_voxels=int(candidate.sum()), added_voxels=int((candidate & ~clean).sum()),
        synthetic_bridge_voxels=0, original_mask_unchanged=True,
        thresholds=dict(max_distance_mm=3., min_voxels=8,max_voxels=512,
                        probability=.70, confidence_fraction=.80, max_hu=-600,air_fraction=.90),
        components=rows, mask_file='airway_mask_detail.nii.gz',
        mask_sha256=sha256(folder/'airway_mask_detail.nii.gz'),
        logits_sha256=metadata['sha256'], input_sha256=metadata['input_sha256'],
        model_sha256=metadata['model_sha256'],
        implementation_sha256=sha256(Path(__file__)),
        raw_mask_sha256=sha256(folder/'airway_mask_network.nii.gz'),
        baseline_mask_sha256=sha256(folder/'airway_mask.nii.gz'),
        accuracy_note='Candidates are not manually verified branches; confidence is not accuracy.')
    write_json(folder/'airway_detail_report.json',result)
    return result
