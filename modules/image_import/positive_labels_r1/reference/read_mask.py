from pathlib import Path
import SimpleITK as sitk

def read_mask(path: Path):
    image = sitk.ReadImage(str(path))
    arr = sitk.GetArrayFromImage(image) > 0
    if arr.ndim != 3:
        raise ValueError(f"Expected a 3D mask, got shape {arr.shape}")
    return image, arr
