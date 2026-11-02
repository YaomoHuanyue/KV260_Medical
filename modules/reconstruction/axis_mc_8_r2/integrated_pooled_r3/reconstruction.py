"""Use actual PL MC output to build CSR, then switch once to PL smoothing."""
from pathlib import Path
import argparse,json,sys,time
import numpy as np
import SimpleITK as sitk
from scipy import sparse
SYSTEM=Path(__file__).resolve().parents[4]
ROOT=SYSTEM/'dfx/medical'
sys.path.insert(0,str(SYSTEM))
sys.path.insert(0,str(SYSTEM/'modules/reconstruction'))
from system.contracts import geometry,validate_masks,sha256
from fpga.mc_host import crop_mask,to_mesh
from fpga.smooth_host import prepare
from airway.mesh_reconstruction import vertex_normals

def audit(points,faces,result,inputs,limit):
    assert np.isfinite(result).all()
    np.testing.assert_array_equal(result[inputs['frozen']!=0],points[inputs['frozen']!=0])
    move=np.linalg.norm(result-points,axis=1);assert float(move.max(initial=0))<=limit+1e-4
    before=points[faces];after=result[faces]
    n0=np.cross(before[:,1]-before[:,0],before[:,2]-before[:,0]);n1=np.cross(after[:,1]-after[:,0],after[:,2]-after[:,0])
    assert np.all(np.einsum('ij,ij->i',n0,n1)[np.linalg.norm(n0,axis=1)>1e-12]>0)
    avg=sparse.csr_matrix((inputs['edges']['weight'],inputs['edges']['index'],inputs['rows']),shape=(len(points),len(points)))
    r0=float(np.mean(np.linalg.norm(avg@points-points,axis=1)));r1=float(np.mean(np.linalg.norm(avg@result-result,axis=1)))
    assert r1<=r0+1e-7
    return dict(max_displacement_mm=float(move.max(initial=0)),roughness_before_mm=r0,roughness_after_mm=r1,orientation_preserved=True,frozen_vertices_unchanged=True)
def write_smooth_inputs(folder,inputs):
    for n in ('original','rows','edges','frozen','faces'):inputs[n].tofile(folder/f'{n}.bin')
    (folder/'config.txt').write_text(f"{len(inputs['original'])} {len(inputs['faces'])} {len(inputs['edges'])} {inputs['limit']:.17g} {inputs['iterations']}\n")
def reconstruct(mask_dir,output,session,selected,input_masks):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if (output/'report.json').exists():raise FileExistsError('Choose a new output directory')
    total=time.perf_counter();layers={};pending={}
    # Batch all three MC jobs, then all three smoothing jobs: two RM selections.
    mask_geometry=None
    for name in selected:
        begin=time.perf_counter();folder=output/name;folder.mkdir(exist_ok=True)
        image=sitk.ReadImage(str(Path(mask_dir)/f'{name}_mask.nii.gz'))
        current=(image.GetSize(),image.GetSpacing(),image.GetOrigin(),image.GetDirection())
        if mask_geometry is None:mask_geometry=current
        if current!=mask_geometry:raise ValueError('Mask geometry mismatch')
        array=sitk.GetArrayFromImage(image)
        if not np.any(array):
            np.savez(output/f'{name}.npz',points=np.empty((0,3),np.float32),faces=np.empty((0,3),np.uint32),normals=np.empty((0,3),np.float32));layers[name]=dict(empty=True);continue
        a,offset=crop_mask(array);a.tofile(folder/'mask.u8');(folder/'dimensions.txt').write_text(' '.join(map(str,a.shape[::-1]))+'\n')
        info=session.run('mc',folder,folder/'vertices.u64',folder/'mc.json')
        words=np.fromfile(folder/'vertices.u64',np.uint64)
        points,faces=to_mesh(words,image.GetSpacing(),image.GetOrigin(),np.asarray(image.GetDirection()).reshape(3,3),offset)
        limit=min(.1,.1*min(image.GetSpacing())) if name=='airway' else (.35 if name=='lung' else .15)
        preparation=time.perf_counter();inputs=prepare(points,faces,limit,8);write_smooth_inputs(folder,inputs)
        layers[name]=dict(triangles=len(faces),vertices=len(points),mc=info,csr_prepare_seconds=time.perf_counter()-preparation,mc_stage_seconds=time.perf_counter()-begin)
        # Re-read topology only while smoothing its layer to avoid retaining all CSR arrays.
        np.savez(folder/'mesh_before.npz',points=points,faces=faces)
        pending[name]=limit
    for name,limit in pending.items():
        begin=time.perf_counter();folder=output/name
        info=session.run('smooth',folder,folder/'points.f32',folder/'smooth.json')
        mesh=np.load(folder/'mesh_before.npz');points=mesh['points'];faces=mesh['faces']
        result=np.fromfile(folder/'points.f32',np.float32).reshape(-1,4)[:,:3].copy()
        inputs={n:np.fromfile(folder/f'{n}.bin',dtype) for n,dtype in [('rows',np.uint32),('frozen',np.uint32),('edges',np.dtype([('index','<u4'),('weight','<f4')]))]}
        checks=audit(points,faces,result,inputs,limit)
        np.savez(output/f'{name}.npz',points=result,faces=faces.astype(np.uint32),normals=vertex_normals(result,faces))
        layers[name].update(smooth=info,audit=checks,smooth_stage_seconds=time.perf_counter()-begin)
    report=dict(status='completed',backend='dfx_pl',mc_backend='pl',smoothing_backend='pl',mc_kernel='AXIS_D7',smoothing_kernel='FMA2',mc_transport='AXIS512',mc_scan_voxels_per_iteration=8,quality='original_voxels',coordinates='LPS',units='mm',layers=layers,total_seconds=time.perf_counter()-total,
        input_masks=input_masks,mesh_sha256={name:sha256(output/f'{name}.npz') for name in layers},
        timing_note='Includes mask validation/read, PL MC, PS topology, partial switching, PL smoothing, geometry audit, normals and result writes. Excludes process imports/session creation and initial static-shell load.')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report
