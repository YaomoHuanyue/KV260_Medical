"""Validate new quality identity and retained CT assets before publication."""
from pathlib import Path
import json
import numpy as np
import SimpleITK as sitk
from modules.surface_route.verification_session_r15 import sha,verify_bundle
from modules.surface_route.active_actions_r15 import verify_active_scene as verify_parent
from modules.surface_route.ui_bridge_r9 import asset_path,ROOT
from modules.surface_quality.case_io import same_geometry


def verify_active_scene(path):
    scene=verify_parent(path);entry=scene['complete_surface'].get('quality')
    if entry is None:return scene
    prepared=json.loads((Path(path).parent/'prepared.json').read_text(encoding='utf-8'))
    if entry!=prepared.get('active_quality'):raise ValueError('Mixed quality action identity')
    proof_path=asset_path(Path(path).parent,entry['receipt'])
    if sha(proof_path)!=entry['receipt_sha256']:raise ValueError('Changed quality receipt')
    proof=json.loads(proof_path.read_text(encoding='utf-8'))
    meta=verify_bundle(scene['complete_surface']['bundle'])
    if (proof['schema']!='kv260.surface_route.quality_action.v1' or proof['source']!=entry['source']
            or proof['tier']!=entry['tier'] or proof['input_sha256']!=scene['input_sha256']
            or Path(proof['result']).resolve()!=Path(scene['result']).resolve()
            or proof['renderer_scalar_sha256']!=meta['renderer_scalar_sha256']
            or proof['mesh_sha256']!=sha(Path(scene['complete_surface']['bundle'])/'mesh.npz')
            or proof['PS_Marching_Cubes_used'] is not False):raise ValueError('Quality belongs to a different surface or case')
    if sha(asset_path(proof_path.parent,proof['field']))!=proof['field_sha256']:raise ValueError('Changed generated field')
    for name,digest in proof['case_files_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Changed quality input: '+name)
    return scene


def validate_base_assets(path,base,ct,result,root=ROOT):
    """Ordinary cached views also prove their CT/mask contents, not just size."""
    path=Path(path)
    if base.get('complete_surface'):
        verify_active_scene(path)
        return
    image=sitk.ReadImage(str(ct))
    shape=tuple(reversed(image.GetSize()))
    volume=np.memmap(asset_path(path.parent,base['volume'],root),'<f4','r',shape=shape)
    pixels=sitk.GetArrayFromImage(image)
    for z in range(shape[0]):
        if not np.array_equal(volume[z],pixels[z].astype('<f4')):raise ValueError('Cached CT contents differ')
    del pixels,volume
    packed=np.memmap(asset_path(path.parent,base['masks'],root),np.uint8,'r',shape=shape)
    for bit,name in ((1,'lung'),(2,'airway'),(4,'nodule')):
        file=result/f'segmentation/{name}_mask.nii.gz'
        if file.exists():
            mask=sitk.ReadImage(str(file))
            if not same_geometry(image,mask):raise ValueError('Mask geometry differs from CT')
            expected=sitk.GetArrayFromImage(mask)
            if np.any((expected!=0)&(expected!=1)):raise ValueError('Nonbinary source mask')
            for z in range(shape[0]):
                if not np.array_equal((packed[z]&bit)>0,expected[z]>0):raise ValueError('Cached source mask differs: '+name)
        elif np.any(packed&bit):raise ValueError('Cached nonexistent source mask')
