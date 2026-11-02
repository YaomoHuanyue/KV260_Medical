from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import gzip
import re
import numpy as np


@dataclass
class Volume:
    array: np.ndarray  # z,y,x
    spacing_xyz: tuple[float, float, float]
    origin_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)
    direction: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    sitk_image: object | None = None
    source_kind: str = "unknown"

    @property
    def shape_zyx(self) -> tuple[int, int, int]:
        return tuple(int(v) for v in self.array.shape)


def _parse_vec(text: str) -> tuple[float, float, float]:
    nums = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)]
    if len(nums) != 3:
        raise ValueError(f"Cannot parse vector: {text}")
    return tuple(nums)  # type: ignore[return-value]


def _read_nrrd(path: Path) -> Volume:
    raw = path.read_bytes()
    sep = raw.find(b"\n\n")
    sep_len = 2
    if sep < 0:
        sep = raw.find(b"\r\n\r\n")
        sep_len = 4
    if sep < 0:
        raise ValueError("Invalid NRRD: header terminator not found")
    header = raw[:sep].decode("ascii", errors="replace")
    payload = raw[sep + sep_len:]
    fields: dict[str, str] = {}
    for line in header.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("NRRD") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        fields[k.strip().lower()] = v.strip()

    if int(fields.get("dimension", "0")) != 3:
        raise ValueError("Lite NRRD reader supports 3D volumes only")
    sizes = tuple(int(x) for x in fields["sizes"].split())
    if len(sizes) != 3:
        raise ValueError("Expected 3 NRRD sizes")
    type_map = {
        "char": np.int8, "int8": np.int8, "signed char": np.int8,
        "uchar": np.uint8, "uint8": np.uint8, "unsigned char": np.uint8,
        "short": np.int16, "short int": np.int16, "int16": np.int16,
        "ushort": np.uint16, "unsigned short": np.uint16, "uint16": np.uint16,
        "int": np.int32, "int32": np.int32, "uint": np.uint32, "uint32": np.uint32,
        "float": np.float32, "double": np.float64,
    }
    ntype = fields.get("type", "short").lower()
    if ntype not in type_map:
        raise ValueError(f"Unsupported NRRD type: {ntype}")
    dtype = np.dtype(type_map[ntype])
    endian = fields.get("endian", "little").lower()
    if dtype.itemsize > 1:
        dtype = dtype.newbyteorder("<" if endian == "little" else ">")

    encoding = fields.get("encoding", "raw").lower()
    if encoding in {"gzip", "gz"}:
        payload = gzip.decompress(payload)
    elif encoding not in {"raw"}:
        raise ValueError(f"Lite NRRD reader supports raw/gzip only, got {encoding}")

    expected = int(np.prod(sizes))
    arr = np.frombuffer(payload, dtype=dtype, count=expected)
    if arr.size != expected:
        raise ValueError(f"NRRD data size mismatch: expected {expected}, got {arr.size}")
    # NRRD axis 0 is fastest; sizes are x,y,z for scalar Slicer volumes.
    arr = arr.reshape((sizes[2], sizes[1], sizes[0]), order="C").astype(np.int16, copy=False)

    spacing = [1.0, 1.0, 1.0]
    direction = np.eye(3, dtype=float)
    if "space directions" in fields:
        vec_texts = re.findall(r"\([^)]*\)|none", fields["space directions"], flags=re.I)
        if len(vec_texts) == 3:
            cols = []
            for i, t in enumerate(vec_texts):
                if t.lower() == "none":
                    vec = np.zeros(3)
                    vec[i] = 1.0
                else:
                    vec = np.asarray(_parse_vec(t), dtype=float)
                norm = float(np.linalg.norm(vec))
                spacing[i] = norm if norm > 0 else 1.0
                cols.append(vec / spacing[i])
            direction = np.column_stack(cols)
    elif "spacings" in fields:
        spacing = [float(x) for x in fields["spacings"].split()[:3]]

    origin = (0.0, 0.0, 0.0)
    if "space origin" in fields:
        origin = _parse_vec(fields["space origin"])

    return Volume(
        array=arr,
        spacing_xyz=tuple(float(x) for x in spacing),
        origin_xyz=tuple(float(x) for x in origin),
        direction=tuple(float(x) for x in direction.ravel()),
        source_kind="nrrd-lite",
    )


def load_volume(path: str | Path, series_uid: str | None = None) -> Volume:
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".nrrd":
        try:
            return _read_nrrd(path)
        except Exception as lite_error:
            try:
                import SimpleITK as sitk
            except Exception:
                raise RuntimeError(f"Failed to read NRRD with built-in reader: {lite_error}") from lite_error
            image = sitk.ReadImage(str(path))
            return _from_sitk(image, "nrrd-sitk")

    try:
        import SimpleITK as sitk
    except Exception as exc:
        raise RuntimeError(
            "This input requires SimpleITK. Install dependencies with: pip install -r requirements.txt"
        ) from exc

    if path.is_dir():
        ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(path)) or []
        if not ids:
            # Search nested directories.
            dirs = sorted({p.parent for p in path.rglob("*") if p.is_file()})
            candidates = []
            for d in dirs:
                for uid in sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(d)) or []:
                    files = sitk.ImageSeriesReader.GetGDCMSeriesFileNames(str(d), uid)
                    candidates.append((len(files), d, uid, files))
            if not candidates:
                raise RuntimeError("No readable DICOM series found")
            candidates.sort(reverse=True, key=lambda t: t[0])
            _, d, uid, files = candidates[0]
        else:
            uid = series_uid or max(ids, key=lambda u: len(sitk.ImageSeriesReader.GetGDCMSeriesFileNames(str(path), u)))
            files = sitk.ImageSeriesReader.GetGDCMSeriesFileNames(str(path), uid)
        reader = sitk.ImageSeriesReader()
        reader.SetFileNames(files)
        image = reader.Execute()
        return _from_sitk(image, "dicom")

    image = sitk.ReadImage(str(path))
    return _from_sitk(image, "sitk")


def _from_sitk(image, kind: str) -> Volume:
    import SimpleITK as sitk
    if image.GetDimension() != 3:
        raise RuntimeError(f"Expected 3D image, got {image.GetDimension()}D")
    arr = sitk.GetArrayFromImage(image).astype(np.int16, copy=False)
    return Volume(
        array=arr,
        spacing_xyz=tuple(float(x) for x in image.GetSpacing()),
        origin_xyz=tuple(float(x) for x in image.GetOrigin()),
        direction=tuple(float(x) for x in image.GetDirection()),
        sitk_image=image,
        source_kind=kind,
    )


def write_mask_nrrd(mask_zyx: np.ndarray, volume: Volume, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mask = (mask_zyx > 0).astype(np.uint8)
    nz, ny, nx = mask.shape
    sx, sy, sz = volume.spacing_xyz
    d = np.asarray(volume.direction, dtype=float).reshape(3, 3)
    cols = [d[:, i] * volume.spacing_xyz[i] for i in range(3)]
    dirs = " ".join(f"({v[0]:.9g},{v[1]:.9g},{v[2]:.9g})" for v in cols)
    o = volume.origin_xyz
    header = (
        "NRRD0005\n"
        "type: uchar\n"
        "dimension: 3\n"
        f"sizes: {nx} {ny} {nz}\n"
        "encoding: gzip\n"
        f"space directions: {dirs}\n"
        f"space origin: ({o[0]:.9g},{o[1]:.9g},{o[2]:.9g})\n\n"
    ).encode("ascii")
    payload = gzip.compress(mask.tobytes(order="C"))
    path.write_bytes(header + payload)
    return path


def write_mask_nifti_if_possible(mask_zyx: np.ndarray, volume: Volume, path: str | Path) -> Path | None:
    try:
        import SimpleITK as sitk
    except Exception:
        return None
    img = sitk.GetImageFromArray((mask_zyx > 0).astype(np.uint8))
    img.SetSpacing(volume.spacing_xyz)
    img.SetOrigin(volume.origin_xyz)
    img.SetDirection(volume.direction)
    path = Path(path)
    sitk.WriteImage(img, str(path))
    return path
