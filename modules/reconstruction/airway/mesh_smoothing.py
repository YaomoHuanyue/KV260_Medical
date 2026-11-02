"""Bounded Taubin smoothing in physical millimetres, preserving mesh topology."""
import numpy as np
from scipy import sparse


def _unique_edges(faces):
    # Numeric uint64 sorting preserves the old lexicographic pair order exactly.
    # Geometry indices fit in uint32; two columns otherwise trigger slow
    # structured-array sorting inside np.unique(axis=0).
    keys=np.empty(3*len(faces),np.uint64)
    for index,(first,second) in enumerate(((0,1),(1,2),(2,0))):
        left=np.minimum(faces[:,first],faces[:,second]).astype(np.uint64)
        right=np.maximum(faces[:,first],faces[:,second]).astype(np.uint64)
        keys[index*len(faces):(index+1)*len(faces)]=(left<<np.uint64(32))|right
    unique,counts=np.unique(keys,return_counts=True)
    edges=np.empty((len(unique),2),faces.dtype)
    edges[:,0]=unique>>np.uint64(32)
    edges[:,1]=unique&np.uint64(0xffffffff)
    return edges,counts


def smooth_mesh(points, faces, max_displacement_mm=.15, iterations=8):
    original=np.asarray(points,np.float32)
    faces=np.asarray(faces)
    if not np.isfinite(original).all() or max_displacement_mm<=0 or iterations<1:
        raise ValueError('Invalid smoothing input')
    if not len(faces):
        return original.copy(),dict(max_displacement_mm=0., frozen_vertices=0, iterations=0)
    if (original.ndim!=2 or original.shape[1]!=3 or faces.ndim!=2 or faces.shape[1]!=3
        or faces.dtype.kind not in 'iu' or faces.min()<0
        or faces.max()>=len(original) or faces.max()>np.iinfo(np.uint32).max):
        raise ValueError('Invalid mesh indices or geometry')
    edges,counts=_unique_edges(faces)
    frozen=np.zeros(len(original),bool)
    # Protect open ends and nonmanifold junctions; never change their positions.
    frozen[edges[counts!=2].ravel()]=True
    adjacency=sparse.csr_matrix((np.ones(len(edges)*2,np.float32),
        (np.concatenate([edges[:,0],edges[:,1]]),np.concatenate([edges[:,1],edges[:,0]]))),
        shape=(len(original),len(original)))
    degrees=np.asarray(adjacency.sum(axis=1)).ravel()
    frozen |= degrees==0
    average=sparse.diags(1/np.maximum(degrees,1)) @ adjacency
    result=original.copy()
    roughness=lambda laplacian:float(np.mean(np.linalg.norm(laplacian,axis=1)))
    laplacian=average@result-result
    current_roughness=roughness(laplacian)
    original_roughness=current_roughness
    original_tri=original[faces]
    normal0=np.cross(original_tri[:,1]-original_tri[:,0],original_tri[:,2]-original_tri[:,0])
    nondegenerate=np.linalg.norm(normal0,axis=1)>1e-12
    del original_tri
    accepted=0
    for _ in range(iterations):
        advanced=False
        for step_scale in (1.,.5,.25,.125):
            # Apply the shrink/expand pair before imposing displacement limits.
            # Clipping the two half-steps separately can turn a thin-tube
            # smoother into an expansion and increase surface roughness.
            trial=result+.5*step_scale*laplacian
            trial[frozen]=original[frozen]
            trial=trial-.53*step_scale*(average@trial-trial)
            delta=trial-original
            lengths=np.linalg.norm(delta,axis=1)
            trial=original+delta*np.minimum(1,max_displacement_mm/np.maximum(lengths,1e-20))[:,None]
            trial[frozen]=original[frozen]
            after=trial[faces]
            normal1=np.cross(after[:,1]-after[:,0],after[:,2]-after[:,0])
            del after
            valid=np.einsum('ij,ij->i',normal0,normal1)>0
            valid_orientation=np.all(valid[nondegenerate])
            del normal1,valid
            if valid_orientation:
                next_laplacian=average@trial-trial
                next_roughness=roughness(next_laplacian)
                if next_roughness<current_roughness:
                    result=trial.astype(np.float32)
                    if trial.dtype==np.float32:
                        laplacian=next_laplacian;current_roughness=next_roughness
                    else:
                        laplacian=average@result-result;current_roughness=roughness(laplacian)
                    accepted+=1;advanced=True;break
        # All four candidates failed. Repeating with identical coordinates,
        # graph and limits cannot make a later iteration succeed.
        if not advanced:break
    movement=np.linalg.norm(result-original,axis=1)
    # Translation improves the numerical stability of signed volume on CTs
    # whose patient-coordinate origin is hundreds of millimetres away.
    centre=original.mean(axis=0,dtype=np.float64)
    original_tri=(original.astype(np.float64)-centre)[faces]
    volume=lambda tri:float(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum(dtype=np.float64)/6)
    original_volume=volume(original_tri)
    del original_tri
    final_tri=(result.astype(np.float64)-centre)[faces]
    final_volume=volume(final_tri)
    return result,dict(method='bounded_taubin', iterations=iterations,
        accepted_iterations=accepted,
        coefficients=[.5,-.53], displacement_limit_mm=float(max_displacement_mm),
        max_displacement_mm=float(movement.max()), mean_displacement_mm=float(movement.mean()),
        frozen_vertices=int(frozen.sum()), open_or_nonmanifold_edges=int(np.sum(counts!=2)),
        roughness_before_mm=original_roughness,roughness_after_mm=current_roughness,
        signed_volume_before_mm3=original_volume, signed_volume_after_mm3=final_volume,
        faces_unchanged=True, topology_unchanged=True,
        note='Bounded surface adjustment cannot recover absent anatomical branches.')
