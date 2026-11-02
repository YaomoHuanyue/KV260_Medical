"""Independent physical-coordinate oracle, including rotated/reflected axes."""
import base64,gzip,unittest
import numpy as np
import SimpleITK as sitk
from .target_mapping import map_target


class TargetMapping(unittest.TestCase):
    def source(self,reflected=False):
        mask=np.ones((8,9,10),np.uint8);mask[3:5,3:6,3:7]=0
        image=sitk.GetImageFromArray(mask);image.SetSpacing((.63,1.1,1.7));image.SetOrigin((17,-4,31))
        angle=np.deg2rad(37);direction=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,-1 if reflected else 1]])
        image.SetDirection(tuple(direction.ravel()))
        low=np.array([1,2,1]);coverage=(np.arange(5*5*6).reshape(5,5,6)*13%256).astype(np.uint8)
        lumen=dict(encoding='coverage_u8',shape_xyz=list(coverage.shape[::-1]),
                   origin_lps_mm=list(image.TransformIndexToPhysicalPoint(tuple(map(int,low)))),
                   mask_gzip=base64.b64encode(gzip.compress(coverage.tobytes())).decode())
        return image,mask,low,coverage,lumen
    def test_rotated_reflected_nonuniform_crop_physical_labels(self):
        for reflected in (False,True):
            image,mask,low,coverage,lumen=self.source(reflected)
            direction=np.asarray(image.GetDirection()).reshape(3,3);angle=np.deg2rad(-11)
            dst=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])@direction
            origin=np.array(image.GetOrigin())+direction@np.array([.19,.23,.41])
            geometry=dict(spacing_xyz=[.49,.83,.91],direction=dst.ravel().tolist(),origin_lps_mm=origin.tolist(),size_xyz=[14,15,17])
            positive=np.ones((17,15,14),bool);positive[4:9,4:9,4:9]=False
            actual,report=map_target(lumen,image,geometry,positive)
            z,y,x=np.indices(positive.shape);xyz=np.stack([x,y,z],axis=-1)
            world=np.einsum('ij,...j->...i',dst,xyz*np.array(geometry['spacing_xyz']))+origin
            original_xyz=np.einsum('ij,...j->...i',np.linalg.inv(direction),world-np.array(image.GetOrigin()))/np.array(image.GetSpacing())
            index=np.floor(original_xyz+.5).astype(int);local=index-low
            valid=((local>=0)&(local<np.array(coverage.shape[::-1]))).all(-1)
            reference=np.zeros_like(positive);ix,iy,iz=index[valid].T;lx,ly,lz=local[valid].T
            reference[valid]=(coverage[lz,ly,lx]>165)&(mask[iz,iy,ix]>0);reference&=positive
            np.testing.assert_array_equal(actual,reference);self.assertGreater(report['target_voxels'],0)
            np.testing.assert_array_equal(sitk.GetArrayFromImage(image),mask)
    def test_same_grid_reproduces_original_gate(self):
        image,mask,low,coverage,lumen=self.source()
        geometry=dict(spacing_xyz=list(image.GetSpacing()),direction=list(image.GetDirection()),
                      origin_lps_mm=list(image.GetOrigin()),size_xyz=list(image.GetSize()))
        actual,_=map_target(lumen,image,geometry,mask>0);expected=np.zeros_like(mask,bool)
        expected[1:6,2:7,1:7]=coverage>165;expected&=mask>0
        np.testing.assert_array_equal(actual,expected)
    def test_reject_wrong_lattice_and_bad_geometry(self):
        image,mask,low,coverage,lumen=self.source()
        geometry=dict(spacing_xyz=list(image.GetSpacing()),direction=list(image.GetDirection()),
                      origin_lps_mm=list(image.GetOrigin()),size_xyz=list(image.GetSize()))
        wrong={**lumen,'origin_lps_mm':(np.array(lumen['origin_lps_mm'])+[.1,0,0]).tolist()}
        with self.assertRaises(ValueError):map_target(wrong,image,geometry,mask>0)
        with self.assertRaises(ValueError):map_target(lumen,image,{**geometry,'spacing_xyz':[0,1,1]},mask>0)
        with self.assertRaises(ValueError):map_target(lumen,image,geometry,(mask>0)[:-1])
    def test_no_event(self):
        image,mask,low,coverage,lumen=self.source()
        geometry=dict(spacing_xyz=list(image.GetSpacing()),direction=list(image.GetDirection()),
                      origin_lps_mm=list(image.GetOrigin()),size_xyz=list(image.GetSize()))
        target,_=map_target(None,image,geometry,mask>0);self.assertFalse(target.any())


if __name__=='__main__':unittest.main()
