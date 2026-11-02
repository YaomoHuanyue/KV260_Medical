"""Independent STL/VTP/CSV/report export; never modifies source results."""
from pathlib import Path
import hashlib,json,shutil
import numpy as np
import SimpleITK as sitk

def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def export_result(source,destination,input_sha):
    source=Path(source).resolve();destination=Path(destination).resolve()
    report=json.loads((source/'pipeline.json').read_text(encoding='utf-8'))
    if report.get('status')!='passed' or report.get('input_sha256')!=input_sha:raise ValueError('Export requires a completed result of this CT')
    if destination==source or source in destination.parents:raise ValueError('Export must be outside the source result')
    destination.mkdir(parents=True,exist_ok=False)
    for name in ('lung','airway','nodule'):
        path=source/'reconstruction'/(name+'.npz')
        if not path.exists():continue
        with np.load(path,allow_pickle=False) as mesh:
            points=mesh['points'];faces=mesh['faces']
        if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all() or faces.ndim!=2 or faces.shape[1]!=3 or not np.issubdtype(faces.dtype,np.integer) or (len(faces) and (faces.min()<0 or faces.max()>=len(points))):raise ValueError('Invalid export mesh')
        with (destination/(name+'.stl')).open('wb') as f:
            f.write(b'KV260 LPS coordinates; units millimeters'.ljust(80,b'\0'));f.write(np.asarray(len(faces),'<u4').tobytes())
            dtype=np.dtype([('normal','<f4',(3,)),('vertex','<f4',(3,3)),('attribute','<u2')])
            for start in range(0,len(faces),16384):
                vertices=points[faces[start:start+16384]];normal=np.cross(vertices[:,1]-vertices[:,0],vertices[:,2]-vertices[:,0]);normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-20)
                rows=np.zeros(len(vertices),dtype);rows['normal']=normal;rows['vertex']=vertices;f.write(rows.tobytes())
    nav=source/'navigation'
    if (nav/'route.npz').exists():
        with np.load(nav/'route.npz',allow_pickle=False) as route:p=np.asarray(route['points_lps_mm']);r=np.asarray(route['radius_mm'])
        if p.shape!=(len(r),3) or not np.isfinite(p).all():raise ValueError('Invalid route export')
        coordinates=' '.join(format(float(x),'.9g') for x in p.ravel());radii=' '.join(format(float(x),'.9g') for x in r)
        n=len(p);lines=1 if n>1 else 0;indices=' '.join(map(str,range(n))) if lines else '';offset=str(n) if lines else ''
        xml=f'''<?xml version="1.0"?><VTKFile type="PolyData" version="0.1" byte_order="LittleEndian"><PolyData><Piece NumberOfPoints="{n}" NumberOfLines="{lines}"><PointData Scalars="radius_mm"><DataArray type="Float32" Name="radius_mm" format="ascii">{radii}</DataArray></PointData><Points><DataArray type="Float64" NumberOfComponents="3" format="ascii">{coordinates}</DataArray></Points><Lines><DataArray type="Int32" Name="connectivity" format="ascii">{indices}</DataArray><DataArray type="Int32" Name="offsets" format="ascii">{offset}</DataArray></Lines></Piece></PolyData></VTKFile>'''
        (destination/'route.vtp').write_text(xml,encoding='utf-8')
    for rel in ('navigation/route.csv','navigation/route.json','navigation/branches.json','navigation/instrument_profiles.json','navigation/alternative_routes.json','segmentation/report.json','segmentation/airway_detail_report.json','navigation/anatomical_generations.npz','navigation/anatomical_generation_nodes.csv'):
        path=source/rel
        if path.exists():shutil.copyfile(path,destination/(rel.split('/')[0]+'_'+path.name))
    anatomy_path=nav/'anatomical_generations.json'
    if anatomy_path.exists():
        anatomy=json.loads(anatomy_path.read_text(encoding='utf-8'))
        if (anatomy.get('schema')!='kv260.navigation.anatomical_generations.v1' or
                anatomy.get('file')!='anatomical_generations.npz' or
                file_sha(nav/'anatomical_generations.npz')!=anatomy.get('data_sha256')):
            raise ValueError('Invalid anatomical generation export identity')
        # Flat export names differ from the source project; preserve a usable
        # report->data reference and record the original report checksum.
        anatomy['file']='navigation_anatomical_generations.npz'
        anatomy['source_report_sha256']=file_sha(anatomy_path)
        (destination/'navigation_anatomical_generations.json').write_text(json.dumps(anatomy,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    masks={};geometry=None
    for name in ('lung','airway','nodule'):
        path=source/'segmentation'/(name+'_mask.nii.gz')
        if not path.exists():continue
        image=sitk.ReadImage(str(path));view=sitk.GetArrayViewFromImage(image)
        if image.GetDimension()!=3 or image.GetNumberOfComponentsPerPixel()!=1 or not np.issubdtype(view.dtype,np.integer) or view.min()<0 or view.max()>1:raise ValueError('Invalid binary export mask')
        current=(image.GetSize(),image.GetSpacing(),image.GetOrigin(),image.GetDirection())
        if geometry is None:geometry=current
        elif current[0]!=geometry[0] or any(not np.allclose(a,b,rtol=0,atol=1e-6) for a,b in zip(current[1:],geometry[1:])):raise ValueError('Export mask geometry mismatch')
        nii=destination/(name+'_mask.nii.gz');nrrd=destination/(name+'_mask.nrrd')
        shutil.copyfile(path,nii);sitk.WriteImage(image,str(nrrd),useCompression=True)
        masks[name]=dict(nifti=nii.name,nrrd=nrrd.name,size_xyz=list(current[0]),spacing_xyz_mm=list(current[1]),origin_lps_mm=list(current[2]),direction=list(current[3]),source_sha256=file_sha(path))
    recovery_path=source/'airway_detail/report.json'
    if recovery_path.exists():
        recovery=json.loads(recovery_path.read_text(encoding='utf-8'))
        expected={'high.nii.gz','review.nii.gz','experimental_merged.nii.gz','evidence.nii.gz'}
        if (recovery.get('schema')!='kv260.airway_detail.recovery.v1' or recovery.get('status')!='completed'
                or recovery.get('input_sha256')!=input_sha or set(recovery.get('files',{}))!=expected):
            raise ValueError('Invalid recovery export identity')
        exported={}
        for name,digest in recovery['files'].items():
            path=source/'airway_detail'/name
            if file_sha(path)!=digest:raise ValueError('Changed recovery output')
            export_name='airway_detail_'+name;shutil.copyfile(path,destination/export_name);exported[export_name]=digest
        recovery['files']=exported;recovery['source_report_sha256']=file_sha(recovery_path)
        (destination/'airway_detail_report.json').write_text(json.dumps(recovery,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    files={p.name:file_sha(p) for p in destination.iterdir() if p.is_file()}
    result=dict(schema='kv260.export.v2',source=str(source),input_sha256=input_sha,coordinates='LPS',units='mm',pipeline=report,files=files,masks=masks)
    (destination/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return result
