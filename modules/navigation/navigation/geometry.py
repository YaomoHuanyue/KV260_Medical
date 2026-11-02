from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import numpy as np
import SimpleITK as sitk


@dataclass(frozen=True)
class Geometry:
    size_xyz: tuple
    spacing_xyz: tuple
    origin_lps_mm: tuple
    direction: tuple

    def __post_init__(self):
        d = np.asarray(self.direction).reshape(3, 3)
        if (len(self.size_xyz) != 3 or min(self.size_xyz) < 1
                or not np.all(np.isfinite(self.spacing_xyz)) or min(self.spacing_xyz) <= 0
                or not np.all(np.isfinite(self.origin_lps_mm))
                or not np.allclose(d.T @ d, np.eye(3), atol=1e-5)):
            raise ValueError("Invalid 3D geometry; require positive spacing and orthonormal direction")

    @classmethod
    def from_image(cls, image):
        if image.GetDimension() != 3:
            raise ValueError("Require a 3D scalar mask")
        return cls(image.GetSize(), image.GetSpacing(), image.GetOrigin(), image.GetDirection())

    @classmethod
    def from_dict(cls, value):
        return cls(**{k: tuple(v) for k, v in value.items()})

    def to_dict(self):
        return asdict(self)

    def to_lps(self, zyx):
        a = np.asarray(zyx, dtype=np.float64)
        return (a[..., ::-1] * self.spacing_xyz) @ np.asarray(self.direction).reshape(3, 3).T + self.origin_lps_mm

    def to_zyx(self, lps):
        a = np.asarray(lps, dtype=np.float64)
        return (((a - self.origin_lps_mm) @ np.asarray(self.direction).reshape(3, 3)) / self.spacing_xyz)[..., ::-1]

    def matches(self, other):
        return self.size_xyz == other.size_xyz and all(np.allclose(a, b, rtol=0, atol=1e-5) for a, b in (
            (self.spacing_xyz, other.spacing_xyz), (self.origin_lps_mm, other.origin_lps_mm), (self.direction, other.direction)))


def read_mask(path):
    image = sitk.ReadImage(str(path))
    geometry = Geometry.from_image(image)
    a = sitk.GetArrayFromImage(image)
    if a.ndim != 3 or not np.all(np.isfinite(a)):
        raise ValueError("Require a finite scalar 3D mask")
    if not np.all((a == 0) | (a == 1) | (a == 255)):
        raise ValueError("Require a binary mask, not logits or a multi-class label map")
    return a > 0, geometry


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
