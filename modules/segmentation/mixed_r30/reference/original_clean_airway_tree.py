from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from skimage.morphology import skeletonize

try:
    import SimpleITK as sitk
except ImportError as e:
    raise SystemExit(
        "SimpleITK is required. Activate your project .venv and run: pip install SimpleITK"
    ) from e

try:
    import pyvista as pv
except ImportError as e:
    raise SystemExit(
        "PyVista is required. Activate your project .venv and run: pip install pyvista vtk"
    ) from e


NEIGHBOR_OFFSETS = [
    (dz, dy, dx)
    for dz in (-1, 0, 1)
    for dy in (-1, 0, 1)
    for dx in (-1, 0, 1)
    if not (dz == 0 and dy == 0 and dx == 0)
]


def read_mask(path: Path):
    image = sitk.ReadImage(str(path))
    arr = sitk.GetArrayFromImage(image) > 0
    if arr.ndim != 3:
        raise ValueError(f"Expected a 3D mask, got shape {arr.shape}")
    return image, arr


def keep_largest_component(mask: np.ndarray):
    structure = np.ones((3, 3, 3), dtype=np.uint8)
    labels, n = ndi.label(mask, structure=structure)
    if n == 0:
        raise ValueError("Mask is empty.")

    counts = np.bincount(labels.ravel())
    counts[0] = 0
    keep = int(np.argmax(counts))
    cleaned = labels == keep
    return cleaned, n, int(counts[keep]), counts


def clean_mask(mask: np.ndarray, closing_iterations: int = 1):
    before_voxels = int(mask.sum())
    main, component_count, largest_voxels, _ = keep_largest_component(mask)

    if closing_iterations > 0:
        # Small 3D closing bridges tiny one-voxel gaps without aggressively expanding the tree.
        structure = ndi.generate_binary_structure(3, 1)
        main = ndi.binary_closing(
            main, structure=structure, iterations=closing_iterations
        )
        main, _, largest_voxels, _ = keep_largest_component(main)

    # Fill tiny enclosed holes inside the lumen mask, then re-keep the main tree.
    main = ndi.binary_fill_holes(main)
    main, _, largest_voxels, _ = keep_largest_component(main)

    info = {
        "input_foreground_voxels": before_voxels,
        "input_connected_components": component_count,
        "largest_component_voxels": largest_voxels,
        "retained_fraction": float(largest_voxels / max(before_voxels, 1)),
        "closing_iterations": int(closing_iterations),
    }
    return main.astype(np.uint8), info


def save_mask_like(mask: np.ndarray, reference: sitk.Image, out_path: Path):
    out = sitk.GetImageFromArray(mask.astype(np.uint8))
    out.CopyInformation(reference)
    sitk.WriteImage(out, str(out_path), useCompression=True)


def make_mesh(mask: np.ndarray, reference: sitk.Image):
    if mask.sum() < 10:
        raise ValueError("Cleaned airway mask is too small for meshing.")

    from airway.render import mask_to_mesh
    phys_xyz, faces = mask_to_mesh(mask, reference.GetSpacing(), reference.GetOrigin(), reference.GetDirection())

    faces_pv = np.hstack(
        [np.full((faces.shape[0], 1), 3, dtype=np.int64), faces.astype(np.int64)]
    ).ravel()
    mesh = pv.PolyData(phys_xyz, faces_pv)
    mesh = mesh.clean()

    # Light smoothing only: enough to remove voxel stair-steps but not erase distal bronchi.
    try:
        mesh = mesh.smooth_taubin(n_iter=20, pass_band=0.12)
    except Exception:
        try:
            mesh = mesh.smooth(n_iter=15, relaxation_factor=0.01)
        except Exception:
            pass
    return mesh


def skeleton_generation(mask: np.ndarray, spacing_zyx: tuple[float, float, float], max_display: int = 7):
    # Lee thinning is the 3D skeletonization method used by scikit-image.
    skel = skeletonize(mask.astype(bool), method="lee")
    if not np.any(skel):
        return None

    coords = np.argwhere(skel)
    shape = skel.shape

    # Voxel degree in 26-neighbour graph.
    kernel = np.ones((3, 3, 3), dtype=np.uint8)
    kernel[1, 1, 1] = 0
    degree = ndi.convolve(skel.astype(np.uint8), kernel, mode="constant", cval=0)

    endpoints = np.argwhere(skel & (degree <= 1))
    if len(endpoints) == 0:
        endpoints = coords

    # Choose the endpoint with the largest local lumen radius; this strongly favors the tracheal root.
    radius = ndi.distance_transform_edt(mask.astype(bool), sampling=spacing_zyx)
    endpoint_r = radius[tuple(endpoints.T)]

    # Mild centrality preference in x-y prevents selecting a large accidental peripheral stump.
    center_yx = np.array([shape[1] / 2.0, shape[2] / 2.0])
    dist_yx = np.linalg.norm(endpoints[:, 1:3] - center_yx[None, :], axis=1)
    norm_dist = dist_yx / max(np.linalg.norm(center_yx), 1.0)
    score = endpoint_r - 1.5 * norm_dist
    root = tuple(endpoints[int(np.argmax(score))])

    branch_mask = skel & (degree >= 3)
    branch_labels, _ = ndi.label(branch_mask, structure=np.ones((3, 3, 3), dtype=np.uint8))

    generation = np.full(shape, -1, dtype=np.int16)
    generation[root] = 0
    q = deque([root])

    while q:
        z, y, x = q.popleft()
        g = int(generation[z, y, x])
        cur_branch = int(branch_labels[z, y, x])

        for dz, dy, dx in NEIGHBOR_OFFSETS:
            nz, ny, nx = z + dz, y + dy, x + dx
            if nz < 0 or ny < 0 or nx < 0 or nz >= shape[0] or ny >= shape[1] or nx >= shape[2]:
                continue
            if not skel[nz, ny, nx] or generation[nz, ny, nx] >= 0:
                continue

            nxt_branch = int(branch_labels[nz, ny, nx])
            ng = g
            # Count one new generation when traversal leaves a branch-point cluster.
            if cur_branch > 0 and nxt_branch == 0:
                ng = g + 1
            generation[nz, ny, nx] = ng
            q.append((nz, ny, nx))

    valid = generation >= 0
    raw_max = int(generation[valid].max()) if np.any(valid) else 0
    display_mask = skel & valid & (generation <= max_display)

    counts = {}
    for g in range(0, min(raw_max, max_display) + 1):
        counts[str(g)] = int(np.count_nonzero(generation == g))

    return {
        "skeleton": skel,
        "generation": generation,
        "display_mask": display_mask,
        "root_zyx": [int(v) for v in root],
        "raw_max_generation_estimate": raw_max,
        "display_max_generation": min(raw_max, max_display),
        "skeleton_voxels_by_generation_0_to_display_max": counts,
    }


def skeleton_points_physical(gen_data, reference: sitk.Image):
    display_mask = gen_data["display_mask"]
    generation = gen_data["generation"]
    zyx = np.argwhere(display_mask)
    if len(zyx) == 0:
        return None, None

    xyz_idx = zyx[:, ::-1].astype(np.float64)
    spacing = np.asarray(reference.GetSpacing(), dtype=np.float64)
    origin = np.asarray(reference.GetOrigin(), dtype=np.float64)
    direction = np.asarray(reference.GetDirection(), dtype=np.float64).reshape(3, 3)
    xyz = origin + (direction @ (xyz_idx * spacing).T).T
    scalars = generation[tuple(zyx.T)].astype(np.int16)
    return xyz, scalars


def render(mesh: pv.PolyData, out_png: Path, gen_data, reference: sitk.Image, interactive: bool):
    plotter = pv.Plotter(off_screen=not interactive, window_size=(1400, 1000))
    plotter.add_mesh(mesh, smooth_shading=True, opacity=1.0)

    if gen_data is not None:
        pts, gens = skeleton_points_physical(gen_data, reference)
        if pts is not None and len(pts) > 0:
            cloud = pv.PolyData(pts)
            cloud["generation"] = gens
            plotter.add_mesh(
                cloud,
                scalars="generation",
                cmap="turbo",
                clim=[0, 7],
                render_points_as_spheres=True,
                point_size=5,
                scalar_bar_args={"title": "Generation 0-7"},
            )

    plotter.add_axes()
    plotter.view_isometric()
    plotter.camera.zoom(1.15)

    if interactive:
        # Screenshot is saved when the interactive window opens.
        plotter.show(screenshot=str(out_png))
    else:
        plotter.show(screenshot=str(out_png), auto_close=True)


def main():
    p = argparse.ArgumentParser(
        description="Clean a deep airway mask into one connected tracheobronchial tree and render a clear 0-7 generation view."
    )
    p.add_argument("--mask", required=True, type=Path, help="Deep airway mask, e.g. airway_mask_deep.nii.gz")
    p.add_argument("--output", required=True, type=Path, help="Output folder")
    p.add_argument("--closing", type=int, default=1, help="Small 3D closing iterations; default 1")
    p.add_argument("--max-generation", type=int, default=7, help="Max generation shown on centerline overlay; default 7")
    p.add_argument("--interactive", action="store_true", help="Open an interactive PyVista window")
    args = p.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    reference, mask = read_mask(args.mask)

    cleaned, clean_info = clean_mask(mask, closing_iterations=args.closing)
    cleaned_path = args.output / "airway_clean_main_tree.nii.gz"
    save_mask_like(cleaned, reference, cleaned_path)

    mesh = make_mesh(cleaned, reference)
    stl_path = args.output / "airway_clean_main_tree.stl"
    mesh.save(str(stl_path))

    spacing_xyz = reference.GetSpacing()
    spacing_zyx = (spacing_xyz[2], spacing_xyz[1], spacing_xyz[0])
    gen_data = skeleton_generation(cleaned, spacing_zyx, max_display=args.max_generation)

    summary = {
        "purpose": "clean connected airway tree; generation overlay intentionally limited for readable 6-7 generation visualization",
        "mask_input": str(args.mask),
        "cleaning": clean_info,
        "requested_max_generation_display": int(args.max_generation),
    }
    if gen_data is not None:
        summary.update({
            "root_zyx": gen_data["root_zyx"],
            "raw_max_generation_estimate": gen_data["raw_max_generation_estimate"],
            "display_max_generation": gen_data["display_max_generation"],
            "skeleton_voxels_by_generation_0_to_display_max": gen_data["skeleton_voxels_by_generation_0_to_display_max"],
            "note": "Generation is a topology estimate, not anatomical bronchial naming. The mesh is the cleaned connected airway tree; the colored centerline is capped for readability.",
        })

    with open(args.output / "clean_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    render_png = args.output / "airway_clean_0_to_7.png"
    render(mesh, render_png, gen_data, reference, interactive=args.interactive)

    print("\n[OK] Clean airway tree created")
    print(f"Clean mask : {cleaned_path}")
    print(f"Clean STL  : {stl_path}")
    print(f"Render PNG : {render_png}")
    print(f"Summary    : {args.output / 'clean_summary.json'}")
    print(f"Kept largest connected tree: {clean_info['retained_fraction']:.1%} of input foreground")
    if gen_data is not None:
        print(f"Raw topology max generation estimate: {gen_data['raw_max_generation_estimate']}")
        print(f"Displayed centerline generations: 0-{gen_data['display_max_generation']}")


if __name__ == "__main__":
    main()
