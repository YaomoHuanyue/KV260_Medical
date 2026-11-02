"""Geometry/checksum helpers for standalone mask-to-mesh reconstruction."""
from pathlib import Path
import hashlib,json
import numpy as np
import SimpleITK as sitk

def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def write_json(path,data):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)

def require_geometry(image,reference):
    if image.GetSize()!=reference.GetSize() or any(not np.allclose(a,b,rtol=0,atol=1e-4)
        for a,b in ((image.GetSpacing(),reference.GetSpacing()),(image.GetOrigin(),reference.GetOrigin()),(image.GetDirection(),reference.GetDirection()))):
        raise ValueError('Mask geometry differs from input image')

def write_like(array,reference,path):
    if tuple(array.shape)!=tuple(reversed(reference.GetSize())):raise ValueError('Mask size differs')
    image=sitk.GetImageFromArray(array);image.CopyInformation(reference)
    sitk.WriteImage(image,str(path),True)
