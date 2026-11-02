"""Export accepted PL-produced meshes and the exact current UI scalar semantics."""
from pathlib import Path
import hashlib,json,sys,tempfile,time,uuid
import numpy as np
import SimpleITK as sitk

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ui'))
from features.analysis import surface_attributes
from .vtp import write_vtp

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def generation_rgb(generation,connected):
    """Unlit UI hue palette, including its gray disconnected-point convention."""
    h=np.mod(np.maximum(generation,0),12).astype(np.float64)/12
    hue=np.clip(np.abs(np.mod(h[:,None]+np.array([0.,2/3,1/3]),1)*6-3)-1,0,1)
    hue[np.asarray(connected)<.5]=[.48,.48,.5]
    return np.rint(hue*255).astype(np.uint8)

def load_mesh(path):
    with np.load(path,allow_pickle=False) as mesh:
        points=mesh['points'];faces=mesh['faces'];normals=mesh['normals']
    if points.ndim!=2 or points.shape[1]!=3 or points.dtype not in (np.float32,np.float64):
        raise ValueError('Invalid source points')
    if normals.shape!=points.shape or normals.dtype not in (np.float32,np.float64):
        raise ValueError('Invalid source normals')
    if not np.isfinite(points).all() or not np.isfinite(normals).all():
        raise ValueError('Non-finite source geometry')
    if faces.ndim!=2 or faces.shape[1]!=3 or faces.dtype.kind not in 'iu':
        raise ValueError('Invalid source triangles')
    if faces.size and (faces.min()<0 or faces.max()>=len(points)):
        raise ValueError('Source triangle index out of range')
    return points,faces,normals

def export_surfaces(source,destination,input_sha):
    start=time.monotonic();source=Path(source).resolve();destination=Path(destination).resolve()
    pipeline_path=source/'pipeline.json'
    pipeline=json.loads(pipeline_path.read_text(encoding='utf-8'))
    if pipeline.get('status')!='passed' or pipeline.get('input_sha256')!=input_sha:
        raise ValueError('Requires a completed result for the selected CT')
    if destination==source or source in destination.parents or destination in source.parents:
        raise ValueError('Export directory must be separate from the source result')
    if destination.exists():raise FileExistsError(destination)
    inputs={'pipeline.json':sha(pipeline_path)};names=[]
    for name in ('lung','airway','nodule'):
        path=source/'reconstruction'/(name+'.npz')
        if path.exists():
            p,f,n=load_mesh(path);del p,f,n
            inputs[str(path.relative_to(source))]=sha(path);names.append(name)
    if not names:raise ValueError('No completed surface exists')
    for rel in ('segmentation/airway_mask.nii.gz','segmentation/airway_logits.json',
                'segmentation/airway_logits.npy','navigation/centerline.json',
                'navigation/centerline.npz','navigation/branches.json',
                'navigation/anatomical_generations.json','navigation/anatomical_generations.npz'):
        if (source/rel).is_file():inputs[rel]=sha(source/rel)
    if 'airway' in names and not all(n in inputs for n in (
            'segmentation/airway_mask.nii.gz','navigation/centerline.json',
            'navigation/centerline.npz','navigation/branches.json')):
        raise ValueError('Airway color export requires identified centerline attributes')
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=destination.parent/(destination.name+'.pending_'+uuid.uuid4().hex)
    staging.mkdir(exist_ok=False);structures={}
    try:
        for name in names:
            path=source/'reconstruction'/(name+'.npz');points,faces,normals=load_mesh(path)
            attrs={'Normals':normals};attribute_meta=None
            if name=='airway':
                image=sitk.ReadImage(str(source/'segmentation/airway_mask.nii.gz'))
                with tempfile.TemporaryDirectory(prefix='attribute_work_',dir=staging) as temp:
                    assert Path(temp).resolve().is_relative_to(staging.resolve())
                    stream=Path(temp)/'points.f32';attribute_path=Path(temp)/'attributes.f32'
                    with stream.open('wb') as target:
                        for a in range(0,len(points),16384):
                            np.column_stack((points[a:a+16384],normals[a:a+16384])).astype('<f4').tofile(target)
                    attribute_meta=surface_attributes(source,image,stream,attribute_path,input_sha)
                    if attribute_meta is None:raise ValueError('Missing source airway attributes')
                    values=np.fromfile(attribute_path,'<f4').reshape(-1,4)
                if len(values)!=len(points):raise ValueError('Attribute cardinality changed')
                attrs.update(generation=values[:,0].astype(np.int16),radius_mm=values[:,1],
                    network_probability=values[:,2],probability_available=(values[:,2]>=0).astype(np.uint8),
                    connected_to_root=values[:,3].astype(np.uint8),
                    RGB=generation_rgb(values[:,0],values[:,3]))
            else:
                color=[148,209,250] if name=='lung' else [255,138,59]
                attrs['RGB']=np.broadcast_to(np.asarray(color,np.uint8),(len(points),3))
            file=staging/(name+'.vtp');write_vtp(file,points,faces,attrs)
            structures[name]=dict(file=file.name,points=len(points),triangles=len(faces),
                source_mesh_sha256=inputs[str(path.relative_to(source))],
                point_arrays=list(attrs),attribute_semantics=attribute_meta,
                geometry_recomputed=False,preview_decimation_used=False,
                airway_palette='current_UI_unlit_hue' if name=='airway' else None)
            del points,faces,normals,attrs
        for n,d in inputs.items():
            if sha(source/n)!=d:raise ValueError('Source result changed during export')
        sources={str(p.relative_to(ROOT)):sha(p) for p in (
            Path(__file__).resolve(),Path(__file__).with_name('vtp.py'),ROOT/'ui/features/analysis.py')}
        result=dict(schema='kv260.surface_export.v1',status='completed',input_sha256=input_sha,
            source_result=str(source),source_files_sha256=inputs,source_sha256=sources,
            structures=structures,files={p.name:sha(p) for p in staging.iterdir()},
            coordinates='LPS',units='mm',additional_PL_resources=0,
            geometry_producer=pipeline.get('backend','see_source_pipeline'),
            attribute_backend='existing_PS_sparse_nearest_centerline',
            file_serialization_backend='PS_bounded_binary_chunks',
            active_color='RGB',probability_is_not_accuracy=True,
            elapsed_seconds=time.monotonic()-start)
        (staging/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,
            allow_nan=False)+'\n',encoding='utf-8')
        staging.rename(destination)
        return result
    except BaseException:
        # Preserve a failed candidate directory; never present it as a finished
        # export and never remove or modify the original accepted result.
        (staging/'FAILED.txt').write_text('Export did not complete. Original result retained.\n')
        raise

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--input-sha',required=True)
    a=parser.parse_args();print(json.dumps(export_surfaces(a.result,a.destination,a.input_sha)))

if __name__=='__main__':main()
