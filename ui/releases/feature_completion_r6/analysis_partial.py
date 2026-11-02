"""Optional structures in the UI; accepted complete-result analysis is shared."""
from pathlib import Path
import numpy as np
import json
from modules.lesion_catalogue.catalogue import catalogue
from features.analysis import surface_attributes, navigation_hud


def enrich_scene(result, image, meta, cache, input_sha):
    result, cache = Path(result), Path(cache)
    if (result / 'segmentation/nodule_mask.nii.gz').is_file():
        return enrich_complete(result, image, meta, cache, input_sha)
    meta['candidates'] = []
    if 'airway' in meta['meshes']:
        item = meta['meshes']['airway']
        attributes = surface_attributes(result, image, cache/item['file'], cache/'airway.attributes', input_sha)
        if attributes:
            item['attributes'] = attributes
    if meta.get('navigation'):
        raise ValueError('Navigation cannot be attached to a result without a target mask')


def enrich_complete(result, image, meta, cache, input_sha):
    import SimpleITK as sitk
    result=Path(result);cache=Path(cache)
    mi=sitk.ReadImage(str(result/'segmentation/nodule_mask.nii.gz'))
    if mi.GetSize()!=image.GetSize() or any(not np.allclose(a,b,atol=1e-6,rtol=0) for a,b in [(mi.GetSpacing(),image.GetSpacing()),(mi.GetOrigin(),image.GetOrigin()),(mi.GetDirection(),image.GetDirection())]):raise ValueError('Candidate/CT geometry mismatch')
    report,_=catalogue(sitk.GetArrayViewFromImage(mi),image,0.,False)
    meta['candidates']=report['rows']
    meta['candidate_catalogue']=report
    if 'airway' in meta['meshes']:
        item=meta['meshes']['airway'];attributes=surface_attributes(result,image,cache/item['file'],cache/'airway.attributes',input_sha)
        if attributes:item['attributes']=attributes
    nav=meta.get('navigation')
    if nav:
        nav['hud']=navigation_hud(result/'navigation/route.npz',nav['report'])
        for name in ('instrument_profiles','alternative_routes','whole_instrument_profiles','whole_alternative_routes'):
            path=result/'navigation'/(name+'.json')
            if path.exists():nav[name]=json.loads(path.read_text(encoding='utf-8'))
