"""Prepare bounded-smoothing CSR input, independent of XRT/native execution."""
import numpy as np
from scipy import sparse
from airway.mesh_smoothing import _unique_edges

def prepare(points,faces,limit,iterations=8):
    p=np.asarray(points,np.float32);f=np.asarray(faces)
    if p.ndim!=2 or p.shape[1]!=3 or not len(p) or len(p)>1000000 or not np.isfinite(p).all():
        raise ValueError('Invalid smoothing points')
    if f.ndim!=2 or f.shape[1]!=3 or f.dtype.kind not in 'iu' or len(f)>2000000 or (f.size and (f.min()<0 or f.max()>=len(p))):
        raise ValueError('Invalid smoothing faces')
    if not np.isfinite(limit) or limit<=0 or not 1<=iterations<=16:raise ValueError('Invalid smoothing parameters')
    edges,counts=_unique_edges(f)
    frozen=np.zeros(len(p),np.uint32);frozen[edges[counts!=2].ravel()]=1
    adjacency=sparse.csr_matrix((np.ones(len(edges)*2,np.float32),
        (np.concatenate([edges[:,0],edges[:,1]]),np.concatenate([edges[:,1],edges[:,0]]))),shape=(len(p),len(p)))
    degrees=np.asarray(adjacency.sum(axis=1)).ravel();frozen[degrees==0]=1
    if adjacency.nnz>12000000:raise ValueError('Smoothing graph exceeds hardware bound')
    # Diagonal @ CSR emits each sorted row in reverse order in our validated
    # SciPy reference. Build those identical records directly, including the
    # doubled self-edge weights of degenerate faces, without sparse matmul.
    sizes=np.diff(adjacency.indptr)
    reverse=np.repeat(adjacency.indptr[:-1]+adjacency.indptr[1:]-1,sizes)-np.arange(adjacency.nnz,dtype=adjacency.indptr.dtype)
    neighbors=np.empty(adjacency.nnz,dtype=[('index','<u4'),('weight','<f4')])
    neighbors['index']=adjacency.indices[reverse]
    neighbors['weight']=np.repeat(1/np.maximum(degrees,1),sizes)*adjacency.data[reverse]
    rows=adjacency.indptr.astype(np.uint32)
    del adjacency,reverse,sizes,edges,counts
    padded_points=np.zeros((len(p),4),np.float32);padded_points[:,:3]=p
    padded_faces=np.zeros((len(f),4),np.uint32);padded_faces[:,:3]=f
    return dict(original=padded_points,rows=rows,edges=neighbors,
        frozen=frozen,faces=padded_faces,limit=float(limit),iterations=int(iterations))
