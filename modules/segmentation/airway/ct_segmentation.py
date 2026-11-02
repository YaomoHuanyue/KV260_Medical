"""Raw CT segmentation baseline, independent of mesh reconstruction and AMD DPU."""
from __future__ import annotations

import configparser
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import SimpleITK as sitk

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ("lung", "airway", "nodule")
REFERENCE_PATHS = {
    "lung": "outputs/ctchest_lesions/_totalseg_work/seg/lung.nii.gz",
    "airway": "outputs/deep_ctchest_probability/airway_mask_deep.nii.gz",
    "nodule": "outputs/ctchest_lesions/lesion_mask_all.nii.gz",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_ct(path: Path, series_uid: str | None = None) -> sitk.Image:
    if path.is_dir():
        ids = list(sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(path)) or [])
        if not ids:
            raise ValueError("No DICOM series in this directory; select the series directory explicitly")
        if series_uid is None and len(ids) != 1:
            raise ValueError(f"Multiple DICOM series; specify --series-uid from {ids}")
        uid = series_uid or ids[0]
        if uid not in ids:
            raise ValueError("Requested DICOM series is not present")
        reader = sitk.ImageSeriesReader()
        reader.SetFileNames(sitk.ImageSeriesReader.GetGDCMSeriesFileNames(str(path), uid))
        image = reader.Execute()
    else:
        image = sitk.ReadImage(str(path))
    if image.GetDimension() != 3 or image.GetNumberOfComponentsPerPixel() != 1:
        raise ValueError("A scalar 3-D CT volume is required")
    values = sitk.GetArrayViewFromImage(image)
    if not np.isfinite(values).all() or min(image.GetSpacing()) <= 0:
        raise ValueError("Invalid CT values or spacing")
    return image


def geometry(image: sitk.Image) -> dict:
    return {"size_xyz": list(image.GetSize()), "spacing_xyz_mm": list(image.GetSpacing()),
            "origin_xyz_mm": list(image.GetOrigin()), "direction": list(image.GetDirection())}


def require_geometry(image: sitk.Image, reference: sitk.Image) -> None:
    if image.GetSize() != reference.GetSize() or any(
        not np.allclose(a, b, rtol=0, atol=1e-4) for a, b in (
            (image.GetSpacing(), reference.GetSpacing()),
            (image.GetOrigin(), reference.GetOrigin()),
            (image.GetDirection(), reference.GetDirection()))
    ):
        raise ValueError("Prediction geometry differs from the original CT; refusing silent alignment")


def write_like(array: np.ndarray, reference: sitk.Image, path: Path) -> None:
    if tuple(array.shape) != tuple(reversed(reference.GetSize())):
        raise ValueError("Array shape differs from CT")
    image = sitk.GetImageFromArray(array)
    image.CopyInformation(reference)
    sitk.WriteImage(image, str(path), True)


def agreement(a: np.ndarray, b: np.ndarray) -> dict:
    if a.shape != b.shape:
        raise ValueError("Different mask shapes")
    a, b = a > 0, b > 0
    na, nb = int(np.count_nonzero(a)), int(np.count_nonzero(b))
    intersection = int(np.count_nonzero(a & b))
    return {"metric_kind": "agreement_with_model_prediction_not_ground_truth",
            "dice": 2 * intersection / (na + nb) if na + nb else None,
            "prediction_voxels": na, "reference_voxels": nb}


def refine_airway(reference: sitk.Image, raw_mask: np.ndarray, include_proximal=True) -> tuple[np.ndarray, dict]:
    """Retain the proximal-connected tree; keep the unfiltered network mask separately."""
    from airway.ct_postprocess import find_trachea_seed, keep_seed_connected
    from airway.segment import segment_airway_adaptive
    raw_image = sitk.GetImageFromArray(raw_mask.astype(np.uint8)); raw_image.CopyInformation(reference)
    canonical = sitk.DICOMOrient(reference, "LPS")
    canonical_mask = sitk.DICOMOrient(raw_image, "LPS")
    ct = sitk.GetArrayFromImage(canonical)
    seed_candidate = find_trachea_seed(ct, canonical.GetSpacing())
    seed = (seed_candidate.x, seed_candidate.y, seed_candidate.z)
    union = sitk.GetArrayViewFromImage(canonical_mask)>0
    proximal = None
    if include_proximal:
        proximal = segment_airway_adaptive(ct, canonical.GetSpacing(), seed, lower_hu=-1050,
            upper_candidates=range(-950,-749,25),growth_ratio_limit=2.,absolute_volume_limit_ml=120.)
        union = union | proximal.mask
    cleaned, details = keep_seed_connected(union, seed, canonical.GetSpacing())
    details.pop("component_sizes_voxels", None)
    details.update(proximal_upper_hu=proximal.selected_upper_hu if proximal is not None else None,
                   seed_physical_xyz_mm=list(canonical.TransformIndexToPhysicalPoint(tuple(map(int,seed)))))
    output = sitk.GetImageFromArray(cleaned.astype(np.uint8)); output.CopyInformation(canonical)
    output = sitk.Resample(output, reference, sitk.Transform(), sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8)
    return sitk.GetArrayFromImage(output), details


def audit(ct: Path, output: Path, series_uid: str | None = None) -> dict:
    image = read_ct(ct, series_uid)
    arr = sitk.GetArrayViewFromImage(image)
    report = {"input": str(ct.resolve()), "geometry": geometry(image),
              "sha256": sha256(ct) if ct.is_file() else None,
              "hu_range": [float(arr.min()), float(arr.max())],
              "real_ct_cases_in_project": 1, "clinical_ground_truth_found": False,
              "references": {}, "models": {}, "amd_dpu_used": False}
    for name, relative in REFERENCE_PATHS.items():
        p = ROOT / relative
        if p.exists():
            pred = sitk.ReadImage(str(p)); require_geometry(pred, image)
            report["references"][name] = {"path": relative, "sha256": sha256(p),
                "label_type": "model_prediction", "voxels": int(np.count_nonzero(sitk.GetArrayViewFromImage(pred)))}
    import onnx
    from collections import Counter
    for p in (ROOT / "resources/models").glob("*/hr/0/model.onnx"):
        model = onnx.load(p)
        report["models"][p.parents[2].name] = {
            "path": str(p.relative_to(ROOT)), "sha256": sha256(p),
            "parameters": sum(int(np.prod(t.dims)) for t in model.graph.initializer),
            "operators": dict(Counter(n.op_type for n in model.graph.node)),
            "inputs": [{"name": t.name, "shape": [d.dim_value or d.dim_param for d in t.type.tensor_type.shape.dim]}
                       for t in model.graph.input]}
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, report)
    return report


def raid_config(input_dir: Path, output: Path, model: str, device: str,
                lung: Path | None = None) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    c = configparser.ConfigParser()
    c["System"] = {"gpu_id": "0" if device == "gpu" else "-1",
        "inputs_folder": str(input_dir), "output_folder": str(output),
        "model_folder": str(ROOT / "resources/models" / model / "hr"), "acceleration": "cpu"}
    c["Runtime"] = {"batch_size": "1", "reconstruction_method": "probabilities",
        "reconstruction_order": "resample_first", "use_preprocessed_data": "false",
        "folds_ensembling": "false", "overlapping_ratio": "0.5"}
    if lung:
        c["Mediastinum"] = {"lungs_segmentation_filename": str(lung)}
    path = output / "inference.ini"
    with path.open("w", encoding="utf-8") as f:
        c.write(f)
    return path


def run_raid(config: Path, output: Path, target: str, reference: sitk.Image,
             probability_path: Path, mask_path: Path, threshold: float, device: str) -> dict:
    subprocess.run([sys.executable, str(ROOT / "ct_segment.py"), "_raid",
                    "--config", str(config), "--device", device], check=True)
    candidates = [p for p in output.glob("*.nii.gz") if p.name.lower().endswith(f"_{target.lower()}.nii.gz")]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one {target} probability file, got {list(output.glob('*.nii.gz'))}")
    im = sitk.ReadImage(str(candidates[0]), sitk.sitkFloat32)
    require_geometry(im, reference)
    a = sitk.GetArrayFromImage(im)
    if not np.isfinite(a).all() or a.min() < -1e-5 or a.max() > 1.00001:
        raise ValueError("Invalid model probabilities; logits must not be silently reinterpreted")
    write_like(a, reference, probability_path)
    write_like((a >= threshold).astype(np.uint8), reference, mask_path)
    return {"threshold": threshold, "probability_min": float(a.min()), "probability_max": float(a.max())}


def preview(ct: sitk.Image, masks: dict[str, np.ndarray], destination: Path, *, compress_level: int = 6) -> None:
    from PIL import Image, ImageDraw
    a = sitk.GetArrayViewFromImage(ct)
    # Include the largest nodule and airway cross-sections, plus evenly spaced lung views.
    slices = set(np.linspace(0.15 * (a.shape[0]-1), .85 * (a.shape[0]-1), 4).astype(int).tolist())
    for name in ("nodule", "airway"):
        slices.add(int(np.argmax(masks[name].sum(axis=(1, 2)))))
    colors = {"lung": (70, 180, 255), "airway": (255, 200, 20), "nodule": (255, 60, 70)}
    canvas = Image.new("RGB", (3 * 512, 2 * 550), "#111111")
    for i, z in enumerate(sorted(slices)):
        gray = np.clip((a[z].astype(np.float32) + 1000) / 1400 * 255, 0, 255)
        rgb = np.repeat(gray[..., None], 3, axis=-1)
        for name, color in colors.items():
            selected = masks[name][z] > 0
            rgb[selected] = .55 * rgb[selected] + .45 * np.array(color)
        tile = Image.fromarray(rgb.astype(np.uint8)).resize((512, 512))
        x, y = (i % 3) * 512, (i // 3) * 550
        canvas.paste(tile, (x, y)); ImageDraw.Draw(canvas).text((x + 8, y + 515),
            f"z={z}  blue:lung yellow:airway red:nodule", fill="white")
    canvas.save(destination, compress_level=compress_level)


def run_pipeline(ct: Path, output: Path, device: str, series_uid: str | None = None) -> dict:
    output = output.resolve(); output.mkdir(parents=True, exist_ok=True)
    if (output / "report.json").exists() or (output / "work").exists():
        raise FileExistsError("Output already contains a run; choose a new output folder")
    # An exclusive lock also prevents two Notebook launches sharing model output files.
    lock = output / "run.lock"
    with lock.open("x", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    started = time.perf_counter()
    report = {"status": "running", "pid": os.getpid(), "device_requested": device,
              "amd_dpu_used": False, "pl_inference_implemented": False, "stages": {},
              "execution_note": "CUDA enabled when requested; CPU preprocessing/postprocessing and unsupported ONNX operators are permitted and reported. Not an all-GPU benchmark.",
              "execution_platform": platform.platform(),
              "label_semantics": {"lung": "lung region", "airway": "airway", "nodule": "lung nodule candidates"}}
    def status(stage: str):
        report["stage"] = stage; report["elapsed_seconds"] = time.perf_counter() - started
        write_json(output / "status.json", report)
        print(f"[{stage}] {report['elapsed_seconds']:.1f}s", flush=True)
    try:
        status("input")
        image = read_ct(ct, series_uid)
        report["package_versions"] = {name: importlib.metadata.version(name) for name in
            ("torch", "raidionicsseg", "TotalSegmentator", "nnunetv2")}
        report["geometry"] = geometry(image)
        report["input_sha256"] = sha256(ct) if ct.is_file() else None
        inputs = output / "work/input"; inputs.mkdir(parents=True)
        sitk.WriteImage(image, str(inputs / "input0.nii.gz"), True)
        for model, target, key, threshold in (("CT_Lungs", "Lungs", "lung", .5),
                                                ("CT_Airways", "Airways", "airway", .4)):
            status(key); t = time.perf_counter()
            stage_dir = output / "work" / key
            config = raid_config(inputs, stage_dir, model, device,
                                 output / "lung_mask.nii.gz" if key == "airway" else None)
            info = run_raid(config, stage_dir, target, image, output / f"{key}_probability.nii.gz",
                            output / f"{key}_mask.nii.gz", threshold, device)
            if key == "airway":
                raw_path = output / "airway_mask_network.nii.gz"
                (output / "airway_mask.nii.gz").replace(raw_path)
                refined, details = refine_airway(image, sitk.GetArrayFromImage(sitk.ReadImage(str(raw_path))))
                write_like(refined, image, output / "airway_mask.nii.gz")
                info["refinement"] = details
            info.update(seconds=time.perf_counter()-t,
                        model_sha256=sha256(ROOT / "resources/models" / model / "hr/0/model.onnx"))
            report["stages"][key] = info
        status("nodule"); t = time.perf_counter()
        subprocess.run([sys.executable, str(ROOT / "ct_segment.py"), "_nodules",
            "--input", str(inputs / "input0.nii.gz"), "--output", str(output / "work/nodule"),
            "--device", device], check=True)
        nodule_image = sitk.ReadImage(str(output / "work/nodule/lung_nodules.nii.gz"))
        require_geometry(nodule_image, image)
        from lesion_detection_totalseg import component_report
        labels, components = component_report(sitk.GetArrayFromImage(nodule_image) > 0, image, 14.)
        write_like((labels > 0).astype(np.uint8), image, output / "nodule_mask.nii.gz")
        write_like(labels, image, output / "nodule_labels.nii.gz")
        report["stages"]["nodule"] = {"seconds": time.perf_counter()-t, "candidates": components,
                                              "minimum_volume_mm3": 14.0}
        weights = ROOT / "resources/totalsegmentator/nnunet/results"
        report["stages"]["nodule"]["checkpoints"] = {
            str(p.relative_to(weights)): sha256(p) for p in weights.rglob("*.pth")}
        status("quality_control")
        masks = {name: sitk.GetArrayFromImage(sitk.ReadImage(str(output / f"{name}_mask.nii.gz")))
                 for name in CLASSES}
        report["mask_voxels"] = {k: int(np.count_nonzero(v)) for k, v in masks.items()}
        if any(count == 0 for count in (report["mask_voxels"]["lung"], report["mask_voxels"]["airway"])):
            raise RuntimeError("Empty lung/airway result: review inference before accepting")
        report["reference_agreement"] = {}
        if report["input_sha256"] == "4507b664690840abb6cb9af2d919377ffc4ef75b167cb6fd0f747befdb12e38e":
            for name, relative in REFERENCE_PATHS.items():
                reference_path = ROOT / relative
                if reference_path.exists():
                    ref = sitk.ReadImage(str(reference_path)); require_geometry(ref, image)
                    report["reference_agreement"][name] = agreement(masks[name], sitk.GetArrayViewFromImage(ref))
        preview(image, masks, output / "ct_overlay.png")
        report["clinical_accuracy"] = None
        report["clinical_accuracy_reason"] = "No independent manual ground truth for this CT"
        report["status"] = "completed"; status("completed")
        write_json(output / "report.json", report)
        return report
    except BaseException as exc:
        report["status"] = "failed"; report["error"] = f"{type(exc).__name__}: {exc}"
        status("failed")
        raise
    finally:
        lock.unlink(missing_ok=True)
