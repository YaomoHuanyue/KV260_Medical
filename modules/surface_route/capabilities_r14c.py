"""Derive current capability fields from the verified legacy mask cache."""
from pathlib import Path
import copy,json,os,shutil,tempfile
import numpy as np
from modules.surface_route.active_actions_r14 import verify_active_scene
from modules.surface_route.bundle_r8 import sha,write_json
ROOT=Path(__file__).resolve().parents[2]


def capabilities(mask):
    if mask.dtype!=np.uint8 or mask.ndim!=1:raise ValueError('Packed scene mask bytes required')
    counts={name:int(np.count_nonzero(mask&bit)) for name,bit in [('lung',1),('airway',2),('nodule',4)]}
    return [name for name,value in counts.items() if value>0],counts


def prepare(path,output):
    path=Path(path).resolve();output=Path(output).resolve()
    if not output.is_relative_to(ROOT) or output.exists():raise ValueError('Fresh project scene required')
    scene=verify_active_scene(path);receipt=json.loads((path.parent/'prepared.json').read_text())
    mask=Path(scene['masks']).resolve()
    if str(mask) not in receipt['retained_assets_sha256'] or sha(mask)!=receipt['retained_assets_sha256'][str(mask)]:
        raise ValueError('Capability source must be the verified retained scene mask')
    packed=np.fromfile(mask,dtype=np.uint8)
    if packed.size!=int(np.prod(scene['geometry']['size_xyz'])):raise ValueError('Truncated scene mask')
    names,counts=capabilities(packed)
    for key,expected in [('available_structures',names),('structure_foreground_voxels',counts)]:
        if key in scene and scene[key]!=expected:raise ValueError('Existing capabilities disagree with verified mask')
        scene[key]=expected
    attr=Path(scene['meshes']['airway']['attributes']['file'])
    if sha(attr)!=receipt['output_sha256']['airway.attributes']:raise ValueError('Changed C1 attributes')
    output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.'+output.name+'-',dir=output.parent))
    try:
        shutil.copyfile(attr,stage/'airway.attributes')
        scene['meshes']['airway']['attributes']['file']=str(output/'airway.attributes')
        write_json(stage/'scene.json',scene)
        receipt=copy.deepcopy(receipt);receipt.update(base_scene=str(path),base_scene_sha256=sha(path),
            capability_source=dict(file=str(mask),sha256=sha(mask),packed_bits=dict(lung=1,airway=2,nodule=4),counts=counts),
            capability_adapter_sha256=sha(Path(__file__)),output_sha256={n:sha(stage/n) for n in ('scene.json','airway.attributes')})
        write_json(stage/'prepared.json',receipt);os.rename(stage,output)
    finally:
        if stage.exists():
            assert stage.parent==output.parent and stage!=output.parent
            shutil.rmtree(stage)
    verify_active_scene(output/'scene.json')
    return output/'scene.json'
