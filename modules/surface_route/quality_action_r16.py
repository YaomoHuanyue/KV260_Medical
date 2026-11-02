"""Explicit completed-case surface regeneration; topology is exclusively C1 PL.

The source and tier are fixed for this action. A failure leaves the active
scene untouched. Existing distance and route PS implementations are selected
from the measured PS/PL comparisons, without a production PS MC fallback.
"""
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter
import hashlib,json,os,sys
import numpy as np
import SimpleITK as sitk
from modules.surface_quality.case_io import load_case,save_field,assert_unchanged,same_geometry
from modules.surface_quality.field import Quality
from modules.surface_quality.fast_field_local import build_local
from modules.surface_quality.scalar_mesh_r7 import from_pl_words
from modules.reconstruction.fpga.mc_host import crop_mask
from modules.navigation.navigation.pipeline import load_prepared,choose_target
from modules.surface_route.bundle_r8 import write_json,mesh_digest
from modules.surface_route.verification_session_r15 import sha,verify_bundle
from modules.surface_route.audit import MeshRegion
from modules.surface_route.guidance_r5 import ScalarField,build_guidance
from modules.surface_route.curve_guidance_r5 import GuidanceSurfaceBendPlanner
from modules.surface_route.bend_replan_r3 import checked_replan
from dfx.surface_quality.prepare import pack_scene,unpack_scene

ROOT=Path(__file__).resolve().parents[2]


def configuration(tier):
    if tier=='high':return Quality()
    if tier=='ultra':return replace(Quality(),surface_smoothing_sigma_mm=.5,
        surface_smoothing_strength=.72,axial_smoothing_sigma_mm=1.,quantization_mm=1/64)
    raise ValueError('Unknown surface quality tier')


def renderer_field(q,bits):
    if q.dtype!=np.dtype('<i2') or q.ndim!=3 or bits not in (5,6):
        raise ValueError('Bounded Q5/Q6 INT16 field required')
    positive=q>0
    if not positive.any():raise ValueError('Surface field has no positive lumen')
    floor=-(4<<bits);crossings=0
    for axis in range(3):
        left,right=[slice(None)]*3,[slice(None)]*3
        left[axis],right[axis]=slice(None,-1),slice(1,None)
        a,b=q[tuple(left)],q[tuple(right)]
        crossing=positive[tuple(left)]!=positive[tuple(right)]
        if np.any(a[crossing]<floor) or np.any(b[crossing]<floor):
            raise ValueError('C9 saturation would move a zero-crossing edge')
        crossings+=int(crossing.sum())
    scalar=np.ascontiguousarray(np.maximum(q,floor),dtype='<i2')
    binary,offset=crop_mask(positive)
    if any(n<2 or n>512 for n in binary.shape):raise ValueError('C1 crop axis outside 2..512')
    return scalar,binary,offset,dict(far_negative_floor_q=floor,crossing_edges=crossings,
        far_negative_saturation_preserves_all_crossing_edges=True)


def context(base_path,source,options):
    base_path=Path(base_path).resolve()
    if not base_path.is_relative_to(ROOT):raise ValueError('Project source scene required')
    base=json.loads(base_path.read_text(encoding='utf-8'))
    if base.get('schema')!='kv260.ui.scene.v1':raise ValueError('Native source scene required')
    if base.get('complete_surface'):
        from modules.surface_route.active_actions_r15 import verify_active_scene
        base=verify_active_scene(base_path)
    ct,result=Path(base['input']).resolve(),Path(base['result']).resolve()
    if not all(p.is_relative_to(ROOT) for p in (ct,result)):raise ValueError('Project CT/result required')
    values=np.asarray([options['diameter'],options['margin'],options['minimum_bend']],float)
    if not np.isfinite(values).all() or values[0]<=0 or np.any(values[1:]<0):raise ValueError('Invalid route constraints')
    if type(options['lesion']) is not int or options['lesion']<0:raise ValueError('Explicit target required')
    pipeline=result/'pipeline.json';proof=json.loads(pipeline.read_text(encoding='utf-8'))
    if proof.get('status')!='passed' or proof.get('input_sha256')!=sha(ct) or base['input_sha256']!=sha(ct):
        raise ValueError('Completed result must belong to the selected CT')
    image,identity=load_case(ct,result/'segmentation',source)
    paths=[pipeline,result/'segmentation/nodule_mask.nii.gz',result/'navigation/centerline.json',result/'navigation/centerline.npz']
    for name in ('lung','airway','nodule'):
        path=result/f'segmentation/{name}_mask.nii.gz'
        if path.exists():paths.append(path)
    identity['inputs_sha256'].update({str(p):sha(p) for p in paths})
    c=load_prepared(result/'navigation')
    if c.metadata['input_sha256']!=sha(result/'segmentation/airway_mask.nii.gz'):
        raise ValueError('Centerline belongs to a different airway mask')
    if c.metadata['centerline_id']!=hashlib.sha256(c.points_lps_mm.tobytes()+c.edges.tobytes()+str(c.root).encode()).hexdigest():
        raise ValueError('Changed centerline identity')
    target=choose_target(c,lesion_path=result/'segmentation/nodule_mask.nii.gz',lesion_index=options['lesion'])
    return base,ct,result,image,identity,c,target


def extract_PL(binary,folder):
    if sys.platform!='linux' or os.geteuid()!=0:raise RuntimeError('C1 extraction requires the board root runtime')
    sys.path.insert(0,str(ROOT/'dfx/medical'));sys.path.insert(0,str(ROOT/'dfx/edt_volume'))
    from runtime_extended import Session
    from volume_runtime import VolumeSession
    binary.tofile(folder/'mask.u8')
    (folder/'dimensions.txt').write_text(' '.join(map(str,binary.shape[::-1]))+'\n')
    before=Path.cwd();begin=perf_counter()
    try:
        with VolumeSession(experimental=False) as lifecycle:lifecycle.return_to_scope()
        with Session() as session:
            trial=session.run('mc',folder,folder/'vertices.u64',folder/'mc.json')
            session.echo();session.report(folder/'session.json')
    finally:os.chdir(before)
    if trial['backend']!='dfx_pl' or (folder/'vertices.u64').stat().st_size!=trial['triangles']*24:
        raise RuntimeError('Incomplete actual C1 output')
    return np.fromfile(folder/'vertices.u64','<u8'),dict(trial=trial,
        complete_extraction_seconds=perf_counter()-begin,includes_lifecycle_and_files=True)


def produce(base_path,output,source,tier,options,event=lambda *a,**k:None):
    begin=perf_counter();quality=configuration(tier);bits=5 if tier=='high' else 6
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT) or output.exists():raise ValueError('Fresh project output required')
    base,ct,result,image,identity,c,target=context(base_path,source,options)
    output.mkdir(parents=True,exist_ok=False)
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    event('progress',text='正在从所选分割来源生成物理标量场')
    distance=None
    if source=='network_probability':
        sys.path.insert(0,str(ROOT/'dfx/edt_cache'))
        from ps_runtime import PSReference
        reference=PSReference()
        def distance(mask,spacing):
            values,seconds=reference.distance(mask,spacing,4)
            return values,dict(backend='PS_Q20_4_thread',total_seconds=seconds)
    start=perf_counter();field=build_local(image,quality,distance)
    field_seconds=perf_counter()-start
    save_field(output/'field',field,identity)
    geometry=dict(size_xyz=list(field.sdf_q_zyx.shape[::-1]),spacing_xyz=field.spacing_xyz.tolist(),
        origin_lps_mm=field.origin_xyz.tolist(),direction=field.direction.ravel().tolist())
    scalar,binary,offset,compression=renderer_field(field.sdf_q_zyx,bits)
    del field,image
    blob,capacity=pack_scene(scalar,np.zeros(scalar.shape,bool),16000+bits,geometry,bits=bits)
    got,labels=unpack_scene(blob)
    if not np.array_equal(got,scalar) or labels.any():raise ValueError('C9 field roundtrip changed')
    del blob,got,labels
    event('progress',text='正在用 PL Marching Cubes 重新提取气道')
    extraction=output/'extraction';extraction.mkdir()
    words,PL=extract_PL(binary,extraction)
    points,faces,mesh_proof=from_pl_words(words,scalar,offset,geometry['spacing_xyz'],geometry['origin_lps_mm'],geometry['direction'])
    del words,binary
    field=ScalarField(scalar,geometry,bits);region=MeshRegion(points,faces,geometry)
    mesh_proof.update(renderer_scalar_sha256=field.sha256,points_faces_sha256=mesh_digest(points,faces))
    event('progress',text='正在按新管壁审核路径、相机与分岔通道')
    from modules.surface_quality.mesh_clearance_native import NativeMeshClearance
    from modules.surface_route.own_replan_trial_r1 import AtThreads
    from modules.surface_route.comparison_base_r15 import MemoWall
    oracle=MemoWall(AtThreads(NativeMeshClearance(points,faces),4))
    start=perf_counter()
    report,route,camera=checked_replan(GuidanceSurfaceBendPlanner(c,region,oracle),target,
        scope_diameter_mm=options['diameter'],safety_margin_mm=options['margin'],
        minimum_bend_radius_mm=options['minimum_bend'],forward_window_mm=10.)
    guidance,targets=build_guidance(c,route,field,sitk.ReadImage(str(result/'segmentation/airway_mask.nii.gz')))
    route_seconds=perf_counter()-start
    assert_unchanged(identity)
    bindings={Path(n).relative_to(ROOT).as_posix():h for n,h in identity['inputs_sha256'].items()}
    for path in (output/'field/field.npz',output/'field/report.json',extraction/'vertices.u64',extraction/'mc.json'):
        bindings[path.relative_to(ROOT).as_posix()]=sha(path)
    from modules.surface_route.bundle_r8 import build_bundle
    meta=build_bundle(output/'bundle',scalar=scalar,geometry=geometry,bits=bits,points=points,faces=faces,
        mesh_proof=mesh_proof,route=route,report=report,camera=camera,guidance=guidance,targets=targets,
        provenance=dict(input_case=source+'_'+tier,input_sha256=bindings,
            scalar_source=source,quality=tier,configuration=asdict(quality),generic_completed_case_producer=True,
            topology_backend='PL_C1_binary_Marching_Cubes',PS_Marching_Cubes_used=False))
    quality_receipt=dict(schema='kv260.surface_route.quality_action.v1',status='generated_complete_bundle',
        input_sha256=sha(ct),result=str(result),source=source,tier=tier,configuration=asdict(quality),
        mesh_sha256=sha(output/'bundle/mesh.npz'),renderer_scalar_sha256=meta['renderer_scalar_sha256'],
        initial_bundle_revision=meta['revision'],field=str(output/'field/field.npz'),field_sha256=sha(output/'field/field.npz'),
        case_files_sha256={Path(n).relative_to(ROOT).as_posix():h for n,h in identity['inputs_sha256'].items()},
        source_sha256={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))},options=options,
        compression=compression,C9_capacity=capacity,PL_extraction=PL,field_seconds=field_seconds,
        route_guidance_seconds=route_seconds,total_before_UI_seconds=perf_counter()-begin,
        wall_query_reuse=oracle.metrics(),PS_Marching_Cubes_used=False,new_bitstream=False)
    write_json(output/'quality.json',quality_receipt)
    from modules.surface_route.quality_publish_r16 import prepare
    prepare(base_path,output/'bundle',output/'UI',quality_path=output/'quality.json')
    assert_unchanged(identity)
    return output/'UI/scene.json'
