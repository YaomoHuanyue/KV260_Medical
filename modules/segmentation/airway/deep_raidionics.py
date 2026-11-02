from __future__ import annotations

import configparser
import fnmatch
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile
import numpy as np

from airway.volume import load_volume

AIRWAY_MODEL_URL = "https://github.com/raidionics/Raidionics-models/releases/download/v1.3.0-rc/Raidionics-CT_Airways-v13.zip"
MODEL_DIRNAME = "CT_Airways"


def _download(url: str, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading: {url}")
    print(f"Destination: {dst}")

    def hook(blocks, block_size, total):
        if total <= 0:
            return
        done = min(blocks * block_size, total)
        pct = 100.0 * done / total
        print(f"\r  {pct:5.1f}%  {done/1024/1024:7.1f}/{total/1024/1024:.1f} MB", end="")

    urllib.request.urlretrieve(url, dst, reporthook=hook)
    print()


def ensure_airway_model(model_root: str | Path = "resources/models", force: bool = False) -> Path:
    """Ensure the official CT_Airways model is present.

    Important: current Raidionics/AeroPath builds the execution pipeline at runtime.
    The model archive itself is what is required here; a standalone release pipeline
    JSON must not be used as CT_Airways/pipeline.json with recent raidionicsrads.
    """
    root = Path(model_root).resolve()
    model_dir = root / MODEL_DIRNAME

    if model_dir.exists() and any(p.is_file() for p in model_dir.rglob("*")) and not force:
        return model_dir

    root.mkdir(parents=True, exist_ok=True)
    archive = root / "Raidionics-CT_Airways-v13.zip"
    if force or not archive.exists():
        _download(AIRWAY_MODEL_URL, archive)

    with zipfile.ZipFile(archive, "r") as zf:
        zf.extractall(root)

    # Some archives/tools may introduce an extra top-level folder. Normalize it.
    if not model_dir.exists():
        matches = [x for x in root.rglob(MODEL_DIRNAME) if x.is_dir()]
        if matches:
            src = matches[0]
            if src != model_dir:
                shutil.copytree(src, model_dir, dirs_exist_ok=True)

    if not model_dir.exists() or not any(p.is_file() for p in model_dir.rglob("*")):
        raise RuntimeError(f"Model archive extracted, but the CT_Airways model was not found under {model_dir}")
    return model_dir


def _make_nifti(input_path: str | Path, destination: Path) -> Path:
    p = Path(input_path)
    name = p.name.lower()
    if p.is_file() and (name.endswith(".nii") or name.endswith(".nii.gz")):
        shutil.copy2(p, destination)
        return destination
    vol = load_volume(p)
    try:
        import SimpleITK as sitk
    except Exception as exc:
        raise RuntimeError("SimpleITK is required to convert DICOM/NRRD to NIfTI") from exc
    img = sitk.GetImageFromArray(vol.array)
    img.SetSpacing(vol.spacing_xyz)
    img.SetOrigin(vol.origin_xyz)
    img.SetDirection(vol.direction)
    sitk.WriteImage(img, str(destination))
    return destination


def _write_current_aeropath_pipeline(path: Path) -> Path:
    """Write the pipeline schema used by the current AeroPath demo.

    Recent raidionicsrads expects a mapping of numbered steps. The separate
    Mediastinum_Segmentation_Airways.json release asset is not the same schema
    expected by PipelineStructure in current raidionicsrads, which is why using
    it directly can raise: TypeError: string indices must be integers, not 'str'.
    """
    pipeline = {
        "1": {
            "task": "Classification",
            "inputs": {},
            "target": ["MRSequence"],
            "model": "MRI_SequenceClassifier",
            "description": "Classification of the input scan type.",
        },
        "2": {
            "task": "Model selection",
            "model": MODEL_DIRNAME,
            "timestamp": 0,
            "format": "thresholding",
            "description": "Select the CT_Airways segmentation model for the existing input.",
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pipeline, indent=4), encoding="utf-8")
    return path


def run_raidionics_airway(
    input_path: str | Path,
    output_mask: str | Path,
    model_root: str | Path = "resources/models",
    gpu_id: int = -1,
    keep_work: bool = False,
    output_probability: str | Path | None = None,
) -> Path:
    """Run the pretrained CT_Airways model used by the AeroPath demo.

    This mirrors the current AeroPath inference path: prepare a patient/T0 NIfTI,
    generate a two-step Raidionics pipeline at runtime, run raidionicsrads, then
    collect the Airways NIfTI prediction.
    """
    try:
        from raidionicsrads.compute import run_rads
    except Exception as exc:
        raise RuntimeError(
            "Deep mode requires Raidionics. Install it with: pip install -r requirements_deep.txt"
        ) from exc

    model_dir = ensure_airway_model(model_root)
    model_root_abs = model_dir.parent
    output_mask = Path(output_mask).resolve()
    output_mask.parent.mkdir(parents=True, exist_ok=True)

    work_parent = output_mask.parent / "_raidionics_work"
    if work_parent.exists():
        shutil.rmtree(work_parent)
    work_parent.mkdir(parents=True, exist_ok=True)

    patient_dir = work_parent / "patient"
    t0_dir = patient_dir / "T0"
    result_dir = work_parent / "result"
    t0_dir.mkdir(parents=True)
    result_dir.mkdir(parents=True)

    case_name = "airwaycase"
    case_input = t0_dir / f"{case_name}-t1gd.nii.gz"
    _make_nifti(input_path, case_input)

    runtime_pipeline = _write_current_aeropath_pipeline(result_dir / "test_pipeline.json")

    cfg = configparser.ConfigParser()
    cfg.add_section("Default")
    cfg.set("Default", "task", "mediastinum_diagnosis")
    cfg.set("Default", "caller", "")
    cfg.add_section("System")
    cfg.set("System", "gpu_id", str(int(gpu_id)))
    cfg.set("System", "input_folder", str(patient_dir))
    cfg.set("System", "output_folder", str(result_dir))
    cfg.set("System", "model_folder", str(model_root_abs))
    cfg.set("System", "pipeline_filename", str(runtime_pipeline))
    cfg.add_section("Runtime")
    # Probability mode preserves model confidence.  The binary mask is then
    # reconstructed with the model's published Airways threshold (0.4).
    cfg.set("Runtime", "reconstruction_method", "probabilities" if output_probability else "thresholding")
    cfg.set("Runtime", "reconstruction_order", "resample_first")
    cfg.set("Runtime", "use_preprocessed_data", "False")
    cfg_path = work_parent / "rads_config.ini"
    with cfg_path.open("w", encoding="utf-8") as f:
        cfg.write(f)

    print("Running pretrained deep airway model (this can take several minutes on CPU)...")
    run_rads(config_filename=str(cfg_path))

    candidates: list[tuple[int, Path]] = []
    for p in result_dir.rglob("*.nii.gz"):
        low = p.name.lower()
        score = 0
        if "airway" in low:
            score += 20
        if "annotation" in low:
            score += 5
        if fnmatch.fnmatch(low, "*-airways.*"):
            score += 20
        if "lung" in low:
            score -= 10
        candidates.append((score, p))
    if not candidates:
        raise RuntimeError(f"Raidionics finished but no NIfTI prediction was found under {result_dir}")
    candidates.sort(key=lambda x: (x[0], x[1].stat().st_size), reverse=True)
    pred = candidates[0][1]
    if output_probability:
        import SimpleITK as sitk
        probability_path = Path(output_probability).resolve()
        probability_path.parent.mkdir(parents=True, exist_ok=True)
        probability_img = sitk.ReadImage(str(pred), sitk.sitkFloat32)
        probability = sitk.GetArrayFromImage(probability_img).astype("float32", copy=False)
        # Be defensive if an upstream build emits logits rather than activated probabilities.
        if float(probability.min()) < 0.0 or float(probability.max()) > 1.0:
            probability = 1.0 / (1.0 + np.exp(-np.clip(probability, -30.0, 30.0)))
        probability = np.clip(probability, 0.0, 1.0)
        prob_out = sitk.GetImageFromArray(probability)
        prob_out.CopyInformation(probability_img)
        sitk.WriteImage(prob_out, str(probability_path), True)
        binary_out = sitk.GetImageFromArray((probability >= 0.4).astype("uint8"))
        binary_out.CopyInformation(probability_img)
        sitk.WriteImage(binary_out, str(output_mask), True)
    else:
        shutil.copy2(pred, output_mask)

    if not keep_work:
        shutil.rmtree(work_parent, ignore_errors=True)
    return output_mask
