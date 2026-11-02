from __future__ import annotations
from pathlib import Path
import struct
import numpy as np


def load_pl_accelerator(bitstream):
    """Explicit opt-in: programming the overlay only occurs when requested."""
    from pynq_driver import load_accelerator
    return load_accelerator(bitstream)


def mask_to_mesh(mask: np.ndarray, spacing_xyz, origin_xyz, direction, *, accelerator=None):
    if not np.any(mask): raise RuntimeError("Mask is empty")
    if accelerator is None:
        from .mesh_reconstruction import available_backend
        root = Path(__file__).resolve().parents[1]
        if available_backend(root) != 'pl':
            raise RuntimeError('PS Marching Cubes 已移除；请使用已验证的 PL 重建设计。程序不会切换位流。')
        from fpga.mc_xrt_backend import XRTAccelerator
        accelerator = XRTAccelerator(root)
    from fpga.mc_host import crop_mask, to_mesh
    cropped, offset = crop_mask(mask)
    words, report = accelerator.reconstruct(cropped)
    accelerator.last_report = report
    return to_mesh(words, spacing_xyz, origin_xyz, direction, offset)


def write_binary_stl(points,faces,path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("wb") as f:
        f.write(b"Airway CT project v4".ljust(80,b"\0")); f.write(struct.pack("<I",len(faces)))
        for tri in faces:
            p0,p1,p2=points[tri]
            n=np.cross(p1-p0,p2-p0); norm=np.linalg.norm(n); n=n/norm if norm else np.zeros(3)
            f.write(struct.pack("<12fH",*(n.tolist()+p0.tolist()+p1.tolist()+p2.tolist()),0))
    return path


def save_preview(mask,ct,points,faces,path,max_faces=25000):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    path=Path(path)
    # Four-panel diagnostic image: CT, overlay, coronal MIP, 3D mesh.
    z=int(np.argmax(mask.sum(axis=(1,2)))) if mask.any() else ct.shape[0]//2
    fig=plt.figure(figsize=(12,9))
    ax1=fig.add_subplot(221); ax1.imshow(ct[z],cmap="gray",vmin=-1000,vmax=400); ax1.set_title(f"CT axial z={z}"); ax1.axis("off")
    ax2=fig.add_subplot(222); ax2.imshow(ct[z],cmap="gray",vmin=-1000,vmax=400); ax2.contour(mask[z].astype(float),levels=[0.5]); ax2.set_title("Airway overlay"); ax2.axis("off")
    ax3=fig.add_subplot(223); ax3.imshow(mask.max(axis=1),cmap="gray"); ax3.set_title("Airway coronal projection"); ax3.axis("off")
    ax4=fig.add_subplot(224,projection="3d")
    stride=max(1,int(np.ceil(len(faces)/max_faces))); fs=faces[::stride]
    poly=Poly3DCollection(points[fs],linewidths=0.05,alpha=0.9); ax4.add_collection3d(poly)
    mins=points.min(axis=0); maxs=points.max(axis=0); ctr=(mins+maxs)/2; span=float((maxs-mins).max()/2)
    ax4.set_xlim(ctr[0]-span,ctr[0]+span); ax4.set_ylim(ctr[1]-span,ctr[1]+span); ax4.set_zlim(ctr[2]-span,ctr[2]+span)
    ax4.set_title("3D airway surface"); ax4.set_axis_off(); ax4.view_init(elev=18,azim=-65)
    fig.tight_layout(); fig.savefig(path,dpi=170,bbox_inches="tight"); plt.close(fig)
    return path


def interactive_pyvista(points,faces,screenshot=None):
    try:
        import pyvista as pv
    except Exception:
        return False
    faces_pv=np.column_stack([np.full(len(faces),3,dtype=np.int64),faces.astype(np.int64)]).ravel()
    mesh=pv.PolyData(points,faces_pv).clean()
    plotter=pv.Plotter(off_screen=False)
    plotter.add_mesh(mesh,smooth_shading=True)
    plotter.add_axes(); plotter.view_isometric(); plotter.reset_camera()
    plotter.show(screenshot=str(screenshot) if screenshot else None)
    return True
