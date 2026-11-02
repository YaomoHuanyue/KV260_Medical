"""Bounded PS preparation of the original clipped 3x3x3 radius-winner attributes.

The current system's nearest-centreline sampler is a different policy. This
candidate is explicit compatibility preparation, with no automatic UI switch
and no claim of PL execution. Inputs stay on their original CT voxel grid.
"""
import numpy as np
from scipy.spatial import cKDTree

class NeighbourhoodSampler:
    def __init__(self,mask,spacing_xyz,origin_xyz,direction,centerline_points,radii,
                 generation_points=None,generation_values=None,*,logits=None,
                 logit_scale=1.,logit_zero=0.,confidence_volume=None):
        self.mask=np.asarray(mask);self.spacing=np.asarray(spacing_xyz,np.float64)
        self.origin=np.asarray(origin_xyz,np.float64);self.direction=np.asarray(direction,np.float64).reshape(3,3)
        if (self.mask.ndim!=3 or min(self.mask.shape)<1 or max(self.mask.shape)>1024 or self.mask.size>256*1024*1024
            or self.mask.dtype not in (np.dtype(bool),np.dtype('uint8'))):raise ValueError('Bounded binary CT-grid mask required')
        if self.mask.dtype==np.uint8 and self.mask.max()>1:raise ValueError('Binary mask required')
        if (self.spacing.shape!=(3,) or self.origin.shape!=(3,) or not np.isfinite(np.r_[self.spacing,self.origin,self.direction.ravel()]).all()
            or np.any(self.spacing<=0) or not np.allclose(self.direction.T@self.direction,np.eye(3),rtol=0,atol=1e-6)):
            raise ValueError('Finite orthonormal CT geometry required')
        points=np.asarray(centerline_points,np.float64);self.radii=np.asarray(radii,np.float32)
        if (points.ndim!=2 or points.shape[1]!=3 or not len(points) or self.radii.shape!=(len(points),)
            or not np.isfinite(points).all() or not np.isfinite(self.radii).all() or np.any(self.radii<0)):
            raise ValueError('Finite centreline and nonnegative radii required')
        self.radius_tree=cKDTree(points)
        if generation_points is None and generation_values is None:
            generation_points=points;generation_values=np.zeros(len(points),np.uint8)
        gp=np.asarray(generation_points,np.float64);gv=np.asarray(generation_values)
        if (gp.ndim!=2 or gp.shape[1]!=3 or not len(gp) or gv.shape!=(len(gp),)
            or gv.dtype.kind not in 'iu' or np.any(gv<0) or np.any(gv>255) or not np.isfinite(gp).all()):
            raise ValueError('Finite generation points and uint8 labels required')
        self.generation_tree=cKDTree(gp);self.generation_values=gv.astype(np.uint8,copy=False)
        if logits is not None and confidence_volume is not None:raise ValueError('Select one confidence source')
        self.logits=None if logits is None else np.asarray(logits)
        self.confidence=None if confidence_volume is None else np.asarray(confidence_volume)
        self.scale=float(logit_scale);self.zero=float(logit_zero)
        if not np.isfinite([self.scale,self.zero]).all() or self.scale<=0:raise ValueError('Finite positive logit scale required')
        if self.logits is not None:
            if self.logits.shape!=self.mask.shape or self.logits.dtype not in (np.dtype('int8'),np.dtype('float32')):raise ValueError('CT-grid INT8/float32 logits required')
            if self.logits.dtype.kind=='f':
                for plane in self.logits:
                    if not np.isfinite(plane).all():raise ValueError('Nonfinite logits')
        self.int8_confidence=None
        if self.logits is not None and self.logits.dtype==np.int8:
            value=(np.arange(-128,128,dtype=np.float32)-self.zero)*self.scale
            self.int8_confidence=1/(1+np.exp(-np.clip(value,-80,80)))
        if self.confidence is not None:
            if self.confidence.shape!=self.mask.shape or self.confidence.dtype not in (np.dtype('float16'),np.dtype('float32')):raise ValueError('CT-grid confidence volume required')
            for plane in self.confidence:
                if not np.isfinite(plane).all() or np.any(plane<0) or np.any(plane>1):raise ValueError('Confidence must be in [0,1]')
        self.world_to_index=np.diag(1./self.spacing)@self.direction.T
        self.offsets=np.asarray([(dx,dy,dz) for dz in (-1,0,1) for dy in (-1,0,1) for dx in (-1,0,1)],np.int64)
        self.shape_xyz=np.asarray(self.mask.shape[::-1],np.int64);self.last_stats={}

    def iter_samples(self,points_xyz,*,batch_size=4096):
        p=np.asarray(points_xyz)
        if p.ndim!=2 or p.shape[1]!=3 or p.dtype.kind not in 'fiu':raise ValueError('Nx3 numeric physical positions required')
        if type(batch_size) is not int or not 1<=batch_size<=8192:raise ValueError('Batch size must be 1..8192')
        nx,ny,nz=map(int,self.shape_xyz);scratch_peak=0;batches=0;max_unique=0
        self.last_stats=dict(backend='PS_sparse_original_27_neighbour_candidate',PL_accessed=False,
            input_mask_voxels=int(self.mask.size),full_radius_generation_confidence_volumes_allocated=0,
            legacy_default_confidence_when_unavailable=1.,confidence_available=self.logits is not None or self.confidence is not None,
            confidence_availability_must_be_preserved_by_UI=True,
            batch_size=batch_size,points=len(p),batches=0,explicit_array_scratch_peak_bytes=0,
            scratch_excludes_input_arrays_output_buffers_and_scipy_tree_internals=True,
            field_geometry_resampled=False,neighbour_order='dz,dy,dx ascending; strict-greater radius; first tie wins')
        for start in range(0,len(p),batch_size):
            block=np.asarray(p[start:start+batch_size],np.float64)
            if not np.isfinite(block).all():raise ValueError('Nonfinite query point')
            floating=(block-self.origin)@self.world_to_index.T
            if np.any(np.abs(floating)>2**52):raise ValueError('Query index exceeds exact integer conversion range')
            center=np.rint(floating).astype(np.int64)
            xyz=np.clip(center[:,None,:]+self.offsets[None,:,:],0,self.shape_xyz-1)
            linear=(xyz[:,:,2]*ny+xyz[:,:,1])*nx+xyz[:,:,0]
            unique,inverse=np.unique(linear,return_inverse=True);inverse=inverse.reshape(len(block),27)
            z=unique//(nx*ny);rem=unique%(nx*ny);y=rem//nx;x=rem%nx
            foreground=self.mask[z,y,x]!=0
            radii=np.zeros(len(unique),np.float32);generation=np.zeros(len(unique),np.uint8)
            voxel_xyz=np.column_stack((x[foreground],y[foreground],z[foreground]))
            physical=self.origin+(voxel_xyz*self.spacing)@self.direction.T
            if len(physical):
                _,ids=self.radius_tree.query(physical,workers=1);radii[foreground]=self.radii[ids]
                _,ids=self.generation_tree.query(physical,workers=1);generation[foreground]=self.generation_values[ids]
            neighbour_radius=radii[inverse]
            # argmax's first winner is equivalent to the original 27 strict >
            # updates, including equal radii and clipping at image boundaries.
            winner=inverse[np.arange(len(block)),np.argmax(neighbour_radius,axis=1)]
            out_generation=generation[winner];out_radius=radii[winner]
            if self.confidence is not None:out_confidence=self.confidence[z[winner],y[winner],x[winner]].astype(np.float32)
            elif self.int8_confidence is not None:
                ids=self.logits[z[winner],y[winner],x[winner]].astype(np.int16)+128
                out_confidence=self.int8_confidence[ids]
            elif self.logits is not None:
                value=(self.logits[z[winner],y[winner],x[winner]].astype(np.float32)-self.zero)*self.scale
                out_confidence=1/(1+np.exp(-np.clip(value,-80,80)))
            else:out_confidence=np.ones(len(block),np.float32)
            scratch=sum(a.nbytes for a in [block,floating,center,xyz,linear,unique,inverse,z,rem,y,x,foreground,radii,generation,
                voxel_xyz,physical,neighbour_radius,winner,out_generation,out_radius,out_confidence])
            scratch_peak=max(scratch_peak,int(scratch));batches+=1;max_unique=max(max_unique,len(unique))
            self.last_stats.update(batches=batches,max_unique_voxels_per_batch=max_unique,explicit_array_scratch_peak_bytes=scratch_peak)
            yield start,out_generation,out_radius,out_confidence

    def sample(self,points_xyz,*,batch_size=4096):
        points=np.asarray(points_xyz);n=len(points)
        generation=np.empty(n,np.uint8);radius=np.empty(n,np.float32);confidence=np.empty(n,np.float32)
        for start,g,r,c in self.iter_samples(points,batch_size=batch_size):
            end=start+len(g);generation[start:end]=g;radius[start:end]=r;confidence[start:end]=c
        self.last_stats['output_buffers_bytes']=generation.nbytes+radius.nbytes+confidence.nbytes
        return generation,radius,confidence
