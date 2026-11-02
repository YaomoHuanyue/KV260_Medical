"""UI data adapter and asynchronous stage runner. Medical kernels remain unchanged."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, sys, time, uuid

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / 'ui'
# Isolate trial results while preserving the accepted feature and stage paths.
RUNS = UI / 'runs'
trial_runs = os.environ.get('KV260_IMPORT_TEST_RUNS')
if trial_runs:
    RUNS = Path(trial_runs).resolve()
    if not RUNS.is_relative_to(ROOT / 'ui/candidates/external_import_r1'):
        raise ValueError('Import test runs must stay in the independent candidate folder')
MEDICAL = ROOT / 'dfx/medical'
NAMES = ('lung', 'airway', 'nodule')


def emit(kind, **data):
    print(json.dumps(dict(event=kind, **data), ensure_ascii=False), flush=True)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.new')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def validate_result(folder, input_sha):
    folder = Path(folder).resolve()
    report = read(folder / 'pipeline.json')
    if report.get('status') != 'passed' or report.get('input_sha256') != input_sha:
        raise ValueError('结果未成功完成，或结果不属于当前 CT')
    return report


def catalogue(input_path):
    digest = sha(input_path)
    folders = list((MEDICAL / 'results').glob('*/whole_case/pipeline.json'))
    folders += list(RUNS.glob('*/pipeline.json'))
    results = []
    for p in sorted(folders, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            report = validate_result(p.parent, digest)
            results.append(dict(path=str(p.parent), name=p.parent.parent.name if p.parent.name == 'whole_case' else p.parent.name,
                                seconds=report.get('total_wall_seconds')))
        except (ValueError, OSError, KeyError):
            continue
    return digest, results


def geometry(image):
    return dict(size_xyz=list(image.GetSize()), spacing_xyz=list(image.GetSpacing()),
                origin_lps_mm=list(image.GetOrigin()), direction=list(image.GetDirection()))


def require_geometry(a, b):
    import numpy as np
    if a.GetSize() != b.GetSize() or any(not np.allclose(x, y, atol=1e-6, rtol=0) for x, y in
        [(a.GetSpacing(), b.GetSpacing()), (a.GetOrigin(), b.GetOrigin()), (a.GetDirection(), b.GetDirection())]):
        raise ValueError('CT 和分割结果的尺寸或物理坐标不一致')


def mesh_vertices(source, destination, preview=False):
    import numpy as np
    with np.load(source, allow_pickle=False) as f:
        points = np.asarray(f['points'], dtype=np.float32)
        faces = np.asarray(f['faces'])
        normals = np.asarray(f['normals'], dtype=np.float32)
    if points.ndim != 2 or points.shape[1] != 3 or normals.shape != points.shape:
        raise ValueError('网格坐标/法线形状错误')
    if faces.ndim != 2 or faces.shape[1] != 3 or not np.issubdtype(faces.dtype, np.integer):
        raise ValueError('网格索引错误')
    if len(faces) and (faces.min() < 0 or faces.max() >= len(points)):
        raise ValueError('网格索引越界')
    if not np.isfinite(points).all() or not np.isfinite(normals).all():
        raise ValueError('网格包含无效数值')
    original_triangles=len(faces)
    clustering_mm=0.
    if preview and len(faces)>80000:
        # Display-only vertex clustering for the large context lung surface.
        # Airway, lesion, saved reconstruction, and navigation never use this.
        for cell in (1.5,2.,2.5,3.,4.):
            _,inv=np.unique(np.floor(points/cell).astype(np.int32),axis=0,return_inverse=True)
            remapped=inv[faces]
            valid=(remapped[:,0]!=remapped[:,1])&(remapped[:,1]!=remapped[:,2])&(remapped[:,0]!=remapped[:,2])
            new_faces=remapped[valid]
            if len(new_faces)<=80000 or cell==4.:
                counts=np.bincount(inv)
                new_points=np.column_stack([np.bincount(inv,weights=points[:,i])/counts for i in range(3)]).astype(np.float32)
                new_normals=np.column_stack([np.bincount(inv,weights=normals[:,i])/counts for i in range(3)])
                length=np.linalg.norm(new_normals,axis=1);new_normals/=np.maximum(length[:,None],1e-12)
                points,faces,normals=new_points,new_faces,new_normals.astype(np.float32)
                clustering_mm=cell;break
    # Non-indexed GLES2 stream avoids relying on OES_element_index_uint.
    # This preserves every accepted triangle and smooth vertex normal.
    with destination.open('wb') as output:
        for start in range(0, len(faces), 16384):
            idx = faces[start:start+16384].reshape(-1)
            np.column_stack((points[idx], normals[idx])).astype('<f4').tofile(output)
    return dict(file=destination.name, triangles=len(faces), vertices=len(faces)*3,
                original_triangles=original_triangles,display_only=preview,clustering_mm=clustering_mm,
                source_sha256=sha(source), bounds_min=points.min(axis=0).tolist() if len(points) else [0,0,0],
                bounds_max=points.max(axis=0).tolist() if len(points) else [0,0,0])


def prepare(input_path, result=None):
    import numpy as np
    import SimpleITK as sitk
    start = time.monotonic()
    input_path = Path(input_path).resolve()
    digest, results = catalogue(input_path)
    result = Path(result).resolve() if result else (Path(results[0]['path']) if results else None)
    if result:
        validate_result(result, digest)
    sources = {'ct': digest, 'adapter': sha(Path(__file__)), 'features':sha(UI/'features/analysis.py'), 'result': str(result)}
    if result:
        for name in NAMES:
            for path in [result/'segmentation'/(name+'_mask.nii.gz'), result/'reconstruction'/(name+'.npz')]:
                if path.exists(): sources[str(path.relative_to(result))] = sha(path)
        for path in (result/'pipeline.json',result/'navigation/route.npz',result/'navigation/camera.npz',result/'navigation/route.json',result/'navigation/centerline.npz',result/'navigation/centerline.json',result/'navigation/branches.json',result/'navigation/instrument_profiles.json',result/'navigation/alternative_routes.json',result/'segmentation/airway_logits.json',result/'segmentation/airway_logits.npy',result/'segmentation/airway_mask_network.nii.gz',result/'segmentation/airway_mask_detail.nii.gz',result/'segmentation/airway_detail_report.json',result/'navigation/anatomical_generations.json',result/'navigation/anatomical_generations.npz'):
            if path.exists(): sources[str(path.relative_to(result))] = sha(path)
        for name in ('report.json', 'high.nii.gz', 'review.nii.gz', 'experimental_merged.nii.gz', 'evidence.nii.gz'):
            path = result/'airway_detail'/name
            if path.exists(): sources[str(path.relative_to(result))] = sha(path)
        sources['distal_recovery_adapter'] = sha(UI/'features/distal_recovery.py')
    key = hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()[:24]
    target = UI/'cache'/key
    cache_report = target/'cache.json'
    if cache_report.exists():
        cached = read(cache_report)
        if all((target/name).is_file() and (target/name).stat().st_size==size for name,size in cached['sizes'].items()):
            # The sources are content-addressed; cached binaries are disposable.
            meta=read(target/'scene.json'); meta['results']=results
            write(target/'scene.json',meta)
            emit('prepared',scene=str(target/'scene.json'),seconds=time.monotonic()-start,reused=True)
            return target/'scene.json'
    emit('progress', text='读取 CT 和物理坐标')
    image = sitk.ReadImage(str(input_path))
    if image.GetDimension() != 3 or image.GetNumberOfComponentsPerPixel() != 1:
        raise ValueError('当前查看器需要三维单通道 CT')
    array = sitk.GetArrayFromImage(image)
    if not np.isfinite(array).all():
        raise ValueError('CT 包含无效数值')
    if array.size > 256*1024*1024:
        raise ValueError('当前查看器单病例超过 256M 体素上限')
    target.mkdir(parents=True, exist_ok=True)
    np.asarray(array, dtype='<f4').tofile(target / 'ct.f32')
    del array
    meta = dict(schema='kv260.ui.scene.v1', input=str(input_path), input_sha256=digest,
                geometry=geometry(image), volume='ct.f32', masks=None, meshes={}, navigation=None,
                result=str(result) if result else None, results=results, source='raw_ct',candidates=[])
    if result:
        emit('progress', text='读取分割结果和三维网格')
        mask = np.zeros(tuple(reversed(image.GetSize())), dtype=np.uint8)
        for bit, name in enumerate(NAMES):
            path = result / 'segmentation' / (name + '_mask.nii.gz')
            if path.exists():
                mi = sitk.ReadImage(str(path)); require_geometry(image, mi)
                values = sitk.GetArrayFromImage(mi)
                if not np.isin(values, [0, 1]).all():
                    raise ValueError('分割掩膜必须为二值')
                mask |= (values.astype(np.uint8) << bit)
            mesh = result / 'reconstruction' / (name + '.npz')
            if mesh.exists():
                meta['meshes'][name] = mesh_vertices(mesh, target / (name + '.mesh'))
                if name=='lung':meta['meshes']['lung_preview']=mesh_vertices(mesh,target/'lung_preview.mesh',preview=True)
        from features.airway_audit import append_display_masks
        append_display_masks(result/'segmentation',image,mask,meta,digest)
        from features.distal_recovery import append_recovery_masks
        append_recovery_masks(result,image,mask,meta,digest)
        mask.tofile(target / 'masks.u8'); meta['masks'] = 'masks.u8'
        route_path = result / 'navigation/route.npz'
        camera_path = result / 'navigation/camera.npz'
        if route_path.exists() and camera_path.exists():
            with np.load(route_path, allow_pickle=False) as route, np.load(camera_path, allow_pickle=False) as camera:
                meta['navigation'] = dict(points=route['points_lps_mm'].tolist(), arc=route['arc_mm'].tolist(),
                    radius=route['radius_mm'].tolist(), positions=camera['position_lps_mm'].tolist(),
                    forward=camera['forward_lps'].tolist(), up=camera['up_lps'].tolist(), report=read(result/'navigation/route.json'))
        from features.analysis import enrich_scene
        enrich_scene(result,image,meta,target,digest)
    write(target / 'scene.json', meta)
    write(cache_report,dict(sources=sources,sizes={p.name:p.stat().st_size for p in target.iterdir() if p.is_file() and p.name not in ('cache.json','scene.json')}))
    emit('prepared', scene=str(target/'scene.json'), seconds=time.monotonic()-start)
    return target / 'scene.json'


def run(input_path, mode, source=None, lesion=0, diameter=1., margin=.2, stop_file=None, minimum_bend=0.):
    import fcntl
    # This lock serializes UI requests. The existing XRT runtime also owns the
    # global hardware lock, including requests from other programs.
    (RUNS).mkdir(parents=True, exist_ok=True)
    with (RUNS/'.runner.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _run_locked(input_path,mode,source,lesion,diameter,margin,stop_file,minimum_bend)


def _run_locked(input_path, mode, source, lesion, diameter, margin, stop_file, minimum_bend):
    input_path=Path(input_path).resolve(); digest=sha(input_path)
    source = Path(source).resolve() if source else None
    if mode != 'all':
        if source is None: raise ValueError('请先选择属于该 CT 的已完成结果')
        validate_result(source, digest)
    output = RUNS/(time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
    output.mkdir()
    emit('started', output=str(output), text='准备 DFX 任务')
    if source:
        # Each result is self-contained, so deleting an older run cannot break it.
        for name in ('segmentation', 'reconstruction', 'airway_detail'):
            if name == 'airway_detail' and mode == 'airway-detail': continue
            if (source/name).exists() and not (mode=='reconstruction' and name=='reconstruction'):
                (output/name).mkdir()
                for file in (source/name).iterdir():
                    if file.is_file(): shutil.copy2(file, output/name/file.name)
    stages = ['segmentation', 'reconstruction', 'navigation'] if mode=='all' else ['navigation' if mode=='comparison' else mode]
    command = {
        'segmentation': ['run_segmentation.py','--input',str(input_path),'--output',str(output/'segmentation')],
        'reconstruction': ['run_reconstruction_extended.py','--mask-dir',str(output/'segmentation'),'--output',str(output/'reconstruction')],
        'navigation': [str(UI/'features/navigation_task.py'),'--airway',str(output/'segmentation/airway_mask.nii.gz'),
            '--lesion',str(output/'segmentation/nodule_mask.nii.gz'),'--lesion-index',str(lesion),
            '--scope-diameter-mm',str(diameter),'--safety-margin-mm',str(margin),'--minimum-bend-radius-mm',str(minimum_bend),'--output',str(output/'navigation')]+(['--compare'] if mode=='comparison' else []),
        'airway-detail': [str(ROOT/'modules/airway_detail/run_recovery.py'),'--input',str(input_path),
            '--segmentation',str(output/'segmentation'),'--lesion-index',str(lesion),'--output',str(output/'airway_detail')]
    }
    if mode in ('reconstruction', 'airway-detail') and source and (source/'navigation').exists():
        (output/'navigation').mkdir()
        for file in (source/'navigation').iterdir():
            if file.is_file(): shutil.copy2(file, output/'navigation'/file.name)
    phases=[]; start=time.monotonic()
    report=dict(schema='kv260.ui.pipeline.v1',status='running',backend='PS_ROI_sparse' if mode=='airway-detail' else 'dfx_pl',input_sha256=digest,
                input=str(input_path),mode=mode,source_result=str(source) if source else None,stages=phases)
    write(output/'pipeline.json', report)
    try:
        for i, stage in enumerate(stages):
            if stop_file and Path(stop_file).exists():
                report['status']='stopped'; break
            emit('stage', stage=stage, index=i, count=len(stages), text='执行 '+stage)
            t=time.monotonic()
            with (output/(stage+'.log')).open('w') as log:
                rc=subprocess.call([sys.executable,str(MEDICAL/command[stage][0]),*command[stage][1:]],
                                   cwd=MEDICAL,stdout=log,stderr=subprocess.STDOUT)
            if rc:
                tail=(output/(stage+'.log')).read_text(errors='replace')[-5000:]
                raise RuntimeError(stage+' 失败：\n'+tail)
            phases.append(dict(stage=stage,wall_seconds=time.monotonic()-t))
            emit('stage_done',stage=stage,seconds=phases[-1]['wall_seconds'])
        else:
            report['status']='passed'
    except BaseException as e:
        report.update(status='failed',error=str(e)); raise
    finally:
        report['total_wall_seconds']=time.monotonic()-start
        write(output/'pipeline.json',report)
    emit('completed',output=str(output),status=report['status'],seconds=report['total_wall_seconds'])


def main():
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['prepare','run','export','dicom-series','import-dicom'])
    p.add_argument('--input',type=Path,required=True); p.add_argument('--result',type=Path)
    p.add_argument('--mode',choices=['all','reconstruction','navigation','comparison','airway-detail'],default='all')
    p.add_argument('--lesion',type=int,default=0); p.add_argument('--diameter',type=float,default=1.)
    p.add_argument('--margin',type=float,default=.2); p.add_argument('--stop-file',type=Path)
    p.add_argument('--minimum-bend',type=float,default=0.);p.add_argument('--destination',type=Path);p.add_argument('--series-uid')
    a=p.parse_args()
    # Let the display/input process preempt CPU-heavy preparation and reports.
    if hasattr(os,'nice'): os.nice(10)
    os.environ.setdefault('ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS','2')
    os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
    if a.action=='prepare': prepare(a.input,a.result)
    elif a.action=='run': run(a.input,a.mode,a.result,a.lesion,a.diameter,a.margin,a.stop_file,a.minimum_bend)
    elif a.action=='export':
        from features.export import export_result
        if a.result is None or a.destination is None:raise ValueError('Export requires source result and destination')
        r=export_result(a.result,a.destination,sha(a.input));emit('exported',path=str(a.destination.resolve()),files=len(r['files']))
    elif a.action=='dicom-series':
        import SimpleITK as sitk
        emit('dicom_series',directory=str(a.input.resolve()),series=list(sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(a.input)) or []))
    elif a.action=='import-dicom':
        sys.path.insert(0,str(ROOT))
        from system.contracts import create_case
        token=hashlib.sha256((str(a.input.resolve())+'|'+str(a.series_uid)).encode()).hexdigest()[:16]
        # Every import gets a new independent case; changed files cannot reuse it.
        folder=create_case(ROOT,'dicom_'+token+'_'+uuid.uuid4().hex[:6],a.input,a.series_uid)
        emit('imported',input=str(folder/'input/ct.nrrd'))


if __name__=='__main__':
    try: main()
    except Exception as e:
        emit('error',text=str(e)); sys.exit(1)
