from pathlib import Path
import hashlib,json,math,os,re,shutil,uuid
import numpy as np
import SimpleITK as sitk

SCHEMA='kv260.system.case.v1'
CLASSES=('lung','airway','nodule')

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    os.replace(tmp,path)

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def inside(root,relative):
    root=Path(root).resolve();rel=Path(relative)
    if rel.is_absolute() or '..' in rel.parts or ':' in str(relative):raise ValueError('Expected a relative artifact path')
    p=(root/rel).resolve()
    if not p.is_relative_to(root):raise ValueError('Artifact escapes its case folder')
    return p

def geometry(image):
    if image.GetDimension()!=3 or image.GetNumberOfComponentsPerPixel()!=1:raise ValueError('Expected scalar 3-D image')
    size=list(image.GetSize());spacing=list(image.GetSpacing());origin=list(image.GetOrigin());direction=list(image.GetDirection())
    if not all(math.isfinite(v) for v in spacing+origin+direction) or min(spacing)<=0 or min(size)<=0:raise ValueError('Invalid image geometry')
    d=np.array(direction).reshape(3,3)
    if not np.allclose(d.T@d,np.eye(3),atol=1e-5):raise ValueError('Image direction must be orthonormal')
    return dict(coordinates='LPS',units='mm',array_order='zyx',size_xyz=size,spacing_xyz_mm=spacing,origin_lps_mm=origin,direction_row_major=direction)

def matching(a,b):
    return a['size_xyz']==b['size_xyz'] and all(np.allclose(a[k],b[k],atol=1e-5,rtol=0) for k in ('spacing_xyz_mm','origin_lps_mm','direction_row_major'))

def read_volume(path):
    image=sitk.ReadImage(str(path));g=geometry(image)
    if not np.isfinite(sitk.GetArrayViewFromImage(image)).all():raise ValueError('Nonfinite voxel values')
    return image,g

def validate_masks(folder,expected):
    result={}
    for name in CLASSES:
        p=Path(folder)/f'{name}_mask.nii.gz';im,g=read_volume(p)
        if not matching(expected,g):raise ValueError(f'{name} mask geometry does not match CT; no implicit resampling')
        a=sitk.GetArrayViewFromImage(im)
        if not np.all((a==0)|(a==1)):raise ValueError(f'{name} must be binary 0/1')
        result[name]={'filename':p.name,'sha256':sha256(p),'foreground_voxels':int(np.count_nonzero(a))}
    return result

def create_case(system_root,case_id,ct,series_uid=None):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',case_id):raise ValueError('Use a simple case ID of at most 64 characters')
    folder=Path(system_root)/'cases'/case_id
    if folder.exists():raise FileExistsError(f'Case already exists: {case_id}')
    ct=Path(ct).resolve();source_hashes={}
    if ct.is_dir():
        ids=list(sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(ct)) or [])
        if series_uid is None and len(ids)!=1:raise ValueError('Choose exactly one DICOM series with --series-uid')
        uid=series_uid or ids[0]
        if uid not in ids:raise ValueError('DICOM series not found')
        files=list(sitk.ImageSeriesReader.GetGDCMSeriesFileNames(str(ct),uid));reader=sitk.ImageSeriesReader();reader.SetFileNames(files);im=reader.Execute()
        source_hashes={Path(p).name:sha256(p) for p in files}
    else:
        im,_=read_volume(ct);source_hashes={ct.name:sha256(ct)}
    g=geometry(im)
    if not np.isfinite(sitk.GetArrayViewFromImage(im)).all():raise ValueError('Nonfinite CT')
    temporary=folder.with_name('.'+case_id+'.'+uuid.uuid4().hex)
    (temporary/'input').mkdir(parents=True)
    try:
        if ct.is_file() and ct.suffix.lower()=='.nrrd':shutil.copyfile(ct,temporary/'input/ct.nrrd')
        else:sitk.WriteImage(im,str(temporary/'input/ct.nrrd'),True)
        record={'schema':SCHEMA,'case_id':case_id,'ct':{'path':'input/ct.nrrd','sha256':sha256(temporary/'input/ct.nrrd'),'geometry':g},'source_sha256':source_hashes}
        write_json(temporary/'case.json',record);temporary.rename(folder)
    except Exception:
        shutil.rmtree(temporary);raise
    return folder

def load_case(folder):
    folder=Path(folder);c=read_json(folder/'case.json')
    if c.get('schema')!=SCHEMA:raise ValueError('Unsupported case schema')
    ct=inside(folder,c['ct']['path'])
    if sha256(ct)!=c['ct']['sha256']:raise ValueError('CT changed after case import')
    _,g=read_volume(ct)
    if not matching(g,c['ct']['geometry']):raise ValueError('Case geometry record does not match CT')
    return c

def artifact(folder,case,kind,dependencies,parameters,provenance):
    files={p.relative_to(folder).as_posix():sha256(p) for p in Path(folder).rglob('*') if p.is_file() and p.name!='artifact.json'}
    result={'schema':'kv260.system.artifact.v1','case_id':case['case_id'],'ct_sha256':case['ct']['sha256'],'kind':kind,'dependencies':dependencies,'parameters':parameters,'provenance':provenance,'files':files}
    write_json(Path(folder)/'artifact.json',result)
    return result

def validate_artifact(folder,case,kind=None):
    a=read_json(Path(folder)/'artifact.json')
    if a.get('schema')!='kv260.system.artifact.v1' or a['case_id']!=case['case_id'] or a['ct_sha256']!=case['ct']['sha256']:raise ValueError('Artifact belongs to a different CT/case')
    if kind and a['kind']!=kind:raise ValueError('Unexpected artifact kind')
    if not a['files']:raise ValueError('Empty artifact')
    for p,h in a['files'].items():
        if sha256(inside(folder,p))!=h:raise ValueError(f'Artifact file changed: {p}')
    return a
