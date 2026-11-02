"""Cache addressing, rejection boundaries and independent analytic geometry."""
from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare import pack_scene,unpack_scene,reference,boundary_fixtures,normal_matrix,smooth_normals,ROOT,MAX_BLOCKS,MAP_WORDS,SW,SCENE_WORDS,OUTSIDE_Q5

def unpack(blob):
    header=np.frombuffer(blob[:64],'<i4');nx,ny,nz=map(int,header[:3])
    words=np.frombuffer(blob[64:],'<u8').reshape(-1,8)
    maps=words[:MAP_WORDS];field=words[MAP_WORDS:MAP_WORDS+SW];labels=words[MAP_WORDS+SW:]
    q=np.full((nz,ny,nx),OUTSIDE_Q5,np.int16);target=np.zeros_like(q,bool)
    mx,my,mz=(nx+3)//4,(ny+3)//4,(nz+3)//4;sy=(mx+1)//2;sz=sy*((my+1)//2)
    for bz in range(mz):
        for by in range(my):
            for bx in range(mx):
                bank=(bx&1)+2*(by&1)+4*(bz&1);index=(bz//2)*sz+(by//2)*sy+bx//2
                bid=(int(maps[index//4,bank])>>((index&3)*16))&65535
                if not bid:continue
                bid-=1
                for z in range(bz*4,min(nz,bz*4+4)):
                    for y in range(by*4,min(ny,by*4+4)):
                        for x in range(bx*4,min(nx,bx*4+4)):
                            bank=(x&1)+2*(y&1)+4*(z&1);local=((z&3)//2)*4+((y&3)//2)*2+(x&3)//2
                            i=bid*8+local;v=(int(field[i//4,bank])>>((i&3)*16))&65535
                            q[z,y,x]=v if v<32768 else v-65536
                            target[z,y,x]=bool((int(labels[bid//8,bank])>>((bid&7)*8+local))&1)
    return q,target

class SparseFieldTests(unittest.TestCase):
    def test_previous_depth_and_visibility_bits_preserved(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('old_surface',ROOT/'archive/board_20261004_r2/prepare.py')
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        for name in ('tube','blocked','filled','empty'):
            q,s=unpack_scene((ROOT/f'fixtures/{name}.scene.bin').read_bytes())
            p=np.fromfile(ROOT/f'fixtures/{name}.request.bin','<i4')
            np.testing.assert_array_equal((reference(q,s,p)&0xffffffff).astype(np.uint32),old.reference(q,s,p))

    def test_normals_rotate_in_physical_space_on_anisotropic_grid(self):
        spacing=np.array([.6,1.3,2.2]);angle=np.deg2rad(37)
        direction=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
        geometry=dict(direction=direction.ravel(),spacing_xyz=spacing)
        z,y,x=np.indices((24,24,32));center=np.array([15.3,11.8,12.1]);radius=5.5
        signed=radius-np.linalg.norm((np.stack((x,y,z),axis=-1)-center)*spacing,axis=-1)
        q=np.rint(signed*32).clip(OUTSIDE_Q5,32767).astype(np.int16);target=np.zeros_like(q,bool)
        p=np.fromfile(ROOT/'fixtures/anisotropic.request.bin','<i4')
        out=reference(q,target,p,normal_matrix(geometry));depth=out&65535
        rgb=np.stack([((out>>(32+8*i))&255).astype(float)-128 for i in range(3)],axis=-1)
        py,px=np.indices(depth.shape);rays=p[7:10]+px[:,:,None]*p[10:13]+py[:,:,None]*p[13:16]
        hit=p[4:7]/65536+rays/65536*depth[:,:,None]/64
        truth=-((hit-center)*spacing)@direction.T;truth/=np.linalg.norm(truth,axis=-1,keepdims=True)
        rgb/=np.maximum(np.linalg.norm(rgb,axis=-1,keepdims=True),1e-10)
        degrees=np.rad2deg(np.arccos(np.clip(np.sum(rgb*truth,axis=-1),-1,1)))
        self.assertLess(float(np.median(degrees)),6)
        self.assertLess(float(np.quantile(degrees,.95)),12)
        print('anisotropic sphere normal angular median %.3f deg, p95 %.3f deg'%(np.median(degrees),np.quantile(degrees,.95)))

    def test_filter_never_bleeds_through_depth_discontinuities_or_misses(self):
        depth=np.array([[100,100,500,65535]]*4,np.uint32)
        n=np.zeros((4,4,4),np.uint8);n[:,:2]=[190,128,128,255];n[:,2]=[128,190,128,255]
        got=smooth_normals(depth,n)
        np.testing.assert_array_equal(got,n)
        n[:,:3]=[128,128,128,255];np.testing.assert_array_equal(smooth_normals(depth,n),n)
        with self.assertRaises(ValueError):normal_matrix(dict(direction=np.eye(3).ravel(),spacing_xyz=[0,1,1]))
        with self.assertRaises(ValueError):normal_matrix(dict(direction=np.eye(3).ravel(),spacing_xyz=[1e-8,1,1]))

    def test_last_cache_addresses_and_zero_bricks(self):
        boundary_fixtures()
        blob=(ROOT/'fixtures/lastbrick.scene.bin').read_bytes();q,target=unpack_scene(blob)
        self.assertEqual(np.frombuffer(blob,'<i4',count=16)[5],MAX_BLOCKS)
        self.assertEqual(int(q[-1,-1,-1]),32);self.assertTrue(target[-1,-1,-1])
        self.assertEqual(np.count_nonzero(q>0),64)
        blob=(ROOT/'fixtures/outside.scene.bin').read_bytes();q,target=unpack_scene(blob)
        self.assertFalse(target.any());self.assertTrue(np.all(q==OUTSIDE_Q5))

    def test_odd_dimensions_parities_signed_values_and_targets(self):
        rng=np.random.default_rng(734);q=rng.integers(-128,600,size=(13,19,27),dtype=np.int16);s=(q>0)&(rng.random(q.shape)>.65)
        blob,meta=pack_scene(q,s,7);self.assertEqual(len(blob),SCENE_WORDS*64)
        got,target=unpack(blob);np.testing.assert_array_equal(got,q);np.testing.assert_array_equal(target,s)
        self.assertLessEqual(meta['bricks'],MAX_BLOCKS)

    def test_empty_sparse_field(self):
        q=np.full((5,9,17),OUTSIDE_Q5,np.int16);s=np.zeros(q.shape,bool)
        blob,m=pack_scene(q,s,0);self.assertEqual(m['bricks'],0)
        got,target=unpack(blob);np.testing.assert_array_equal(got,q);np.testing.assert_array_equal(target,s)

    def test_capacity_and_invalid_target_rejected(self):
        with self.assertRaises(ValueError):pack_scene(np.ones((128,192,256),np.int16),np.zeros((128,192,256),bool),1)
        q=np.full((4,4,4),OUTSIDE_Q5,np.int16)
        with self.assertRaises(ValueError):pack_scene(q,np.ones_like(q,bool),1)
        with self.assertRaises(ValueError):pack_scene(q.astype(np.float32),np.zeros_like(q,bool),1)

    def test_analytic_sphere_surface_accuracy_improves_over_binary(self):
        z,y,x=np.indices((24,24,32));center=np.array([15.3,11.8,12.1]);radius=5.5
        signed=radius-np.sqrt((x-center[0])**2+(y-center[1])**2+(z-center[2])**2)
        sdf=np.rint(signed*32).clip(OUTSIDE_Q5,32767).astype(np.int16)
        binary=np.where(signed>0,32,-32).astype(np.int16);target=np.zeros(sdf.shape,bool)
        p=np.zeros(16,np.int32);p[:4]=[32,16,160,1];p[4:7]=np.rint(center*65536)
        p[7:10]=[8192,-3100,1600];p[10:13]=[0,200,0];p[13:16]=[0,0,-210]
        a=reference(sdf,target,p)&65535;b=reference(binary,target,p)&65535
        py,px=np.indices(a.shape);ray=p[7:10]+px[:,:,None]*p[10:13]+py[:,:,None]*p[13:16]
        norm=np.linalg.norm(ray/65536,axis=-1)
        origin=p[4:7]/65536-center;unit=ray/65536/norm[:,:,None]
        dot=np.sum(unit*origin,axis=-1);truth=-dot+np.sqrt(dot*dot+radius*radius-np.dot(origin,origin))
        err_a=a/64*norm-truth;err_b=b/64*norm-truth
        rms_a=float(np.sqrt(np.mean(err_a**2)));rms_b=float(np.sqrt(np.mean(err_b**2)))
        self.assertLess(rms_a,.08);self.assertLess(float(np.abs(err_a).max()),.12);self.assertLess(rms_a,rms_b*.5)
        print('analytic sphere: SDF RMSE %.6f mm, binary RMSE %.6f mm'%(rms_a,rms_b))

if __name__=='__main__':unittest.main()
