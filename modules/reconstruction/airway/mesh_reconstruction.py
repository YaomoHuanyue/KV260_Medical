"""Binary Lewiner MC and physical-coordinate meshes; no firmware switching."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from contextlib import nullcontext

import numpy as np
import SimpleITK as sitk
from .mesh_utils import require_geometry, sha256, write_json

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'binary-lewiner-pl-only-v2'
NAMES = ('lung', 'airway', 'nodule')


def available_backend(root=ROOT):
    firmware = Path('/sys/firmware/devicetree/base/fpga-region/firmware-name')
    return 'pl' if (firmware.is_file() and firmware.read_bytes().rstrip(b'\0') in
                    (b'medical_axis4.bit.bin',b'kv260_mc_smooth.bit.bin') and
                    (Path(root)/'fpga/build/mc_xrt').is_file()) else None


def vertex_normals(points, faces):
    normals = np.zeros_like(points, dtype=np.float32)
    if len(faces):
        tri = points[faces]
        cross = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
        indices = faces.ravel()
        for component in range(3):
            normals[:, component] = np.bincount(indices,
                weights=np.repeat(cross[:, component], 3), minlength=len(points))
        length = np.linalg.norm(normals, axis=1)
        normals /= np.maximum(length[:, None], 1e-20)
    return normals


def sampled_mask(mask, stride):
    """Nearest-grid preview. Keep global grid origin; never silently pad edges."""
    if stride not in (1, 2, 4):
        raise ValueError('Unsupported sampling stride')
    return np.ascontiguousarray(mask[::stride, ::stride, ::stride], dtype=np.uint8)


def build_meshes(result_dir, quality='full', backend='auto', root=ROOT, surface='raw', airway='baseline', smoothing_backend='ps'):
    root = Path(root).resolve()
    result_dir = Path(result_dir).resolve()
    if not result_dir.is_relative_to(root/'outputs'):
        raise ValueError('Select a segmentation result inside this project')
    if quality not in ('full', 'preview') or backend not in ('auto', 'pl'):
        raise ValueError('Invalid mesh configuration')
    if surface not in ('raw','smooth') or airway not in ('baseline','detail'):
        raise ValueError('Invalid detail configuration')
    if smoothing_backend not in ('ps','pl'):raise ValueError('Invalid smoothing backend')
    if surface=='smooth' and smoothing_backend=='pl':
        from fpga.smooth_xrt_backend import available
        if not available(root):raise RuntimeError('PL smoothing is unavailable; load its firmware manually')
    if available_backend(root) != 'pl':
        raise RuntimeError('PS Marching Cubes 已移除；请先手动加载匹配的 PL 重建位流。程序不会切换位流。')
    selected='pl'
    import fcntl
    report = json.loads((result_dir/'report.json').read_text(encoding='utf-8'))
    if report.get('status') != 'completed':
        raise ValueError('Segmentation must be completed')
    ct_path = root/'data/CT-chest.nrrd'
    if report.get('input_sha256') != sha256(ct_path):
        raise ValueError('The segmentation does not belong to the current CT')
    mask_files={n:result_dir/f'{n}_mask.nii.gz' for n in NAMES}
    detail=None
    if airway=='detail':
        from .airway_detail import audit_airway
        with (result_dir/'.detail.lock').open('a') as detail_lock:
            fcntl.flock(detail_lock,fcntl.LOCK_EX)
            if (result_dir/'airway_detail_report.json').is_file():
                detail=json.loads((result_dir/'airway_detail_report.json').read_text(encoding='utf-8'))
            if detail is None or detail.get('implementation_sha256')!=sha256(root/'airway/airway_detail.py') or detail.get('baseline_mask_sha256')!=sha256(mask_files['airway']) or detail.get('raw_mask_sha256')!=sha256(result_dir/'airway_mask_network.nii.gz'):
                if not (result_dir/'airway_logits.json').is_file():
                    raise ValueError('此结果没有保存气道置信度；请重新运行一次 PL 分割后再选择候选分支。')
                detail=audit_airway(result_dir,ct_path)
        mask_files['airway']=result_dir/'airway_mask_detail.nii.gz'
        if detail['input_sha256']!=report['input_sha256'] or detail['model_sha256']!=report['model_sha256'] or detail['mask_sha256']!=sha256(mask_files['airway']):
            raise ValueError('Candidate mask does not match this result')
    inputs = {n: sha256(mask_files[n]) for n in NAMES}
    implementation = sha256(Path(__file__))
    firmware=Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes().rstrip(b'\0')
    metadata='fpga/smooth/package/kv260_mc_smooth.xclbin' if firmware==b'kv260_mc_smooth.bit.bin' else 'fpga/render_axis/package/medical_axis4.xclbin'
    accelerator_files=['fpga/build/mc_xrt','fpga/mc_xrt_backend.py',metadata]
    if surface=='smooth' and smoothing_backend=='pl':accelerator_files+=['fpga/build/smooth_xrt','fpga/smooth_xrt_backend.py','fpga/smooth_host.py']
    accelerator_hashes={p:sha256(root/p) for p in accelerator_files}
    loaded_record=Path('/run/kv260-mc-loaded.sha256')
    loaded_bit_sha256=loaded_record.read_text().strip() if loaded_record.is_file() else 'legacy-unrecorded'
    key = hashlib.sha256(json.dumps(dict(version=VERSION, inputs=inputs,
        quality=quality, backend=selected, surface=surface, airway=airway, implementation=implementation, smoothing_backend=smoothing_backend,
        smoothing_hash=sha256(root/'airway/mesh_smoothing.py'),
        accelerator_hashes=accelerator_hashes, loaded_bit_sha256=loaded_bit_sha256,
        host_hash=sha256(root/'fpga/mc_host.py')),
        sort_keys=True).encode()).hexdigest()
    out = root/'outputs/reconstruction'/key[:24]
    out.mkdir(parents=True, exist_ok=True)
    # A per-result lock makes cache publication safe for CLI and Notebook users.
    with (out/'.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (out/'report.json').is_file():
            saved = json.loads((out/'report.json').read_text(encoding='utf-8'))
            if saved.get('cache_key') == key and all(
                (out/item['mesh_file']).is_file() and
                sha256(out/item['mesh_file']) == item['mesh_sha256']
                for item in saved['layers'].values()):
                return out, saved, True
        from fpga.mc_host import crop_mask, to_mesh
        # Reconstruction only needs the CT affine, not a second complete CT array.
        reference = sitk.ImageFileReader()
        reference.SetFileName(str(ct_path))
        reference.ReadImageInformation()
        from fpga.mc_xrt_backend import XRTAccelerator
        accelerator = XRTAccelerator(root)
        started = time.perf_counter()
        common=None
        if airway=='detail':
            # A candidate airway must not repeat lung/nodule reconstruction.
            common=build_meshes(result_dir,quality,backend,root,surface=surface,airway='baseline',smoothing_backend=smoothing_backend)
        layers = {}
        from fpga.smooth_xrt_backend import SmoothSession
        context=SmoothSession(root) if surface=='smooth' and smoothing_backend=='pl' else nullcontext()
        with context as smoothing_session:
            for name in NAMES:
                if common is not None and name!='airway':
                    import shutil
                    common_folder,common_report,_=common
                    mesh_file=f'{name}.npz'
                    temporary=out/(mesh_file+f'.link.{os.getpid()}')
                    try:os.link(common_folder/mesh_file,temporary)
                    except OSError:shutil.copyfile(common_folder/mesh_file,temporary)
                    temporary.replace(out/mesh_file)
                    layers[name]={**common_report['layers'][name],
                                  'reused_from':str(common_folder.relative_to(root))}
                    continue
                image = sitk.ReadImage(str(mask_files[name]))
                require_geometry(image, reference)
                raw = sitk.GetArrayFromImage(image)
                if not np.all((raw == 0) | (raw == 1)):
                    raise ValueError('Reconstruction expects binary 0/1 masks')
                # Thin airway and lesion candidates always retain native sampling.
                stride = 2 if quality == 'preview' and name == 'lung' else 1
                mask = sampled_mask(raw, stride)
                cropped, offset = crop_mask(mask)
                tick = time.perf_counter()
                words, hardware = accelerator.reconstruct(cropped)
                mc_seconds = time.perf_counter()-tick
                tick = time.perf_counter()
                points, faces = to_mesh(words,
                    np.asarray(image.GetSpacing())*stride, image.GetOrigin(),
                    np.asarray(image.GetDirection()).reshape(3, 3), offset)
                smoothing=None
                if surface=='smooth':
                    from .mesh_smoothing import smooth_mesh
                    limit=min(.10,.10*min(image.GetSpacing())) if name=='airway' else (.35 if name=='lung' else .15)
                    if smoothing_backend=='pl':
                        from fpga.smooth_xrt_backend import smooth
                        points,smoothing=smooth(points,faces,limit,root,session=smoothing_session)
                    else:points,smoothing=smooth_mesh(points,faces,max_displacement_mm=limit)
                normals = vertex_normals(points, faces)
                post_seconds = time.perf_counter()-tick
                mesh_file = f'{name}.npz'
                # Uncompressed NPZ avoids expensive compression on ARM at every build.
                temporary = out/(mesh_file+'.tmp')
                with temporary.open('wb') as stream:
                    np.savez(stream, points=points, faces=faces, normals=normals)
                temporary.replace(out/mesh_file)
                layers[name] = dict(mesh_file=mesh_file, mesh_sha256=sha256(out/mesh_file),
                    triangles=len(faces), vertices=len(points), stride=stride,
                    effective_spacing_xyz_mm=(np.asarray(image.GetSpacing())*stride).tolist(),
                    crop_shape_zyx=list(cropped.shape), crop_offset_zyx=offset.tolist(),
                    mc_seconds=mc_seconds, postprocess_seconds=post_seconds,
                    hardware=hardware, smoothing=smoothing, bounds_mm=[points.min(axis=0).tolist(),
                        points.max(axis=0).tolist()] if len(points) else None)
        saved = dict(status='completed', version=VERSION, cache_key=key,
            backend=selected, quality=quality, surface=surface, airway=airway, smoothing_backend=smoothing_backend, input_sha256=report['input_sha256'],
            airway_candidates=({k:detail[k] for k in ['retained_components','added_voxels','synthetic_bridge_voxels','accuracy_note']} if detail else None),
            source_result=str(result_dir.relative_to(root)), mask_sha256=inputs,
            layers=layers, build_seconds=time.perf_counter()-started,
            firmware_switched=False, loaded_bit_sha256=loaded_bit_sha256,
            display_backend='client_browser_webgl2',
            precision_note='preview only reduces lung grid; airway/nodule retain original sampling')
        write_json(out/'report.json', saved)
        return out, saved, False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--quality', choices=['full', 'preview'], default='full')
    parser.add_argument('--backend', choices=['auto', 'pl'], default='pl')
    parser.add_argument('--surface', choices=['raw','smooth'], default='raw')
    parser.add_argument('--airway', choices=['baseline','detail'], default='baseline')
    parser.add_argument('--smoothing-backend', choices=['ps','pl'], default='ps')
    parser.add_argument('--status', type=Path, required=True)
    args = parser.parse_args()
    if not args.status.resolve().is_relative_to(ROOT/'outputs/reconstruction'):
        raise ValueError('Status must stay inside reconstruction outputs')
    args.status.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.status, dict(status='running', pid=os.getpid()))
    try:
        out, report, cached = build_meshes(args.result, args.quality, args.backend,surface=args.surface,airway=args.airway,smoothing_backend=args.smoothing_backend)
        write_json(args.status, dict(status='completed', output=str(out),
                                    cached=cached, report=report))
    except Exception as error:
        write_json(args.status, dict(status='failed', error=str(error)))
        raise


if __name__ == '__main__':
    main()
