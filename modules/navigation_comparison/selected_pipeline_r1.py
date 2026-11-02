"""Independent result bundle for a displayed original Pareto path.

No source result is edited. Each completed bundle has regular copies of its
segmentation, reconstruction and centerline inputs, so it survives source cleanup.
"""
from pathlib import Path
import hashlib,json,shutil,sys,time
from selected_output_r1 import produce
from selected_path_r2 import load_selection
from navigation.pipeline import load_prepared,choose_target

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,data):Path(path).write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')

def run(input_path,source,output,group,candidate,*,provider='verified_PL_C4',emit=lambda *a,**k:None):
    input_path=Path(input_path).resolve();source=Path(source).resolve();output=Path(output).resolve()
    if not source.is_relative_to(ROOT) or not output.is_relative_to(ROOT/'ui'):
        raise ValueError('Selected-path results must remain inside this integrated project')
    if output.exists() or output==source or output.is_relative_to(source):
        raise ValueError('A fresh independent result folder is required')
    if provider not in ('verified_PL_C4','optimized_PS4'):raise ValueError('Unknown audit provider')
    digest=sha(input_path);original=read(source/'pipeline.json')
    if original.get('status')!='passed' or original.get('input_sha256')!=digest:
        raise ValueError('Source result is incomplete or belongs to a different CT')
    nav=source/'navigation'
    bound_inputs={p:sha(p) for p in [nav/'centerline.json',nav/'centerline.npz',
        nav/'whole_instrument_profiles.json',nav/'whole_alternative_routes.json',
        nav/'whole_comparison_arrays.npz',source/'segmentation/airway_mask.nii.gz',
        source/'segmentation/nodule_mask.nii.gz']}
    whole=read(nav/'whole_instrument_profiles.json')
    context=load_prepared(nav)
    if sha(source/'segmentation/airway_mask.nii.gz')!=context.metadata['input_sha256']:
        raise ValueError('Centerline and source airway mask differ')
    if whole['target_kind']!='lesion_candidate':raise ValueError('This UI action requires a lesion candidate target')
    target=choose_target(context,lesion_path=source/'segmentation/nodule_mask.nii.gz',
        lesion_index=int(whole['target_metadata']['index']))
    selection=load_selection(context,target,nav,int(group),int(candidate))
    # Preflight all owned files before copying any. Symlinked old-result inputs
    # are rejected instead of turning the new bundle into a hidden dependency.
    owned=[]
    for name in ('segmentation','reconstruction','airway_detail','navigation'):
        folder=source/name
        if not folder.exists():continue
        if not folder.is_dir() or folder.is_symlink():raise ValueError('Result stage is not a regular directory')
        for p in folder.iterdir():
            if p.is_symlink() or not p.is_file():raise ValueError('Result stages must contain regular files only')
            if name=='navigation' and p.name in ('route.npz','route.json','route.csv','camera.npz','session.json','dfx_report.json','selected_output.json'):
                continue
            owned.append((p,p.relative_to(source),sha(p)))
    for p,d in bound_inputs.items():
        if sha(p)!=d:raise ValueError('Anatomy or comparison changed during input loading')
    if any(sha(nav/n)!=d for n,d in selection.binding['comparison_files_sha256'].items()):
        raise ValueError('Selected path binding differs from source snapshot')
    start=time.perf_counter();output.mkdir(parents=True)
    pipeline=dict(schema='kv260.ui.pipeline.v1',status='running',backend=provider,
        input_sha256=digest,input=str(input_path),mode='selected-path',source_result=str(source),
        selected_group=int(group),selected_candidate_id=int(candidate),stages=[])
    write(output/'pipeline.json',pipeline);emit('started',output=str(output),text='审核所选备选路径')
    try:
        # produce requires a new navigation directory, then verified original
        # non-route inputs are copied beside its fresh outputs.
        if provider=='verified_PL_C4':
            from audit_runtime import AuditSession
            with AuditSession() as session:
                try:
                    receipt=produce(context,target,selection,session,output/'navigation')
                finally:session.select('scope');session.report(output/'selected_session.json')
        else:
            from selected_cpu_r1 import NativeSession
            receipt=produce(context,target,selection,NativeSession(4),output/'navigation')
        emit('stage',stage='navigation',index=0,count=1,text='所选路径已审核，保存独立结果')
        copied={}
        for p,rel,d in owned:
            if sha(p)!=d:raise ValueError('Source changed during selected-path execution')
            dest=output/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
            if dest.is_symlink() or sha(dest)!=d:raise ValueError('Result copy differs')
            copied[rel.as_posix()]=d
        if sha(input_path)!=digest:raise ValueError('CT changed during selected-path execution')
        # Every numerical input used by the producer must still match the
        # bound source. Hashing only the copied files would miss overwritten
        # source route/context files or a different selected path.
        for p,_,d in owned:
            if sha(p)!=d:raise ValueError('Source changed while publishing the result')
        write(output/'selected_pipeline.json',dict(status='self_contained_selected_navigation_bundle_passed',
            copied_files_sha256=copied,selection_output=receipt,provider=provider,
            source_sha256=sha(Path(__file__)),actual_UI_application_verified=False))
        pipeline['status']='passed';pipeline['stages']=[dict(stage='navigation',wall_seconds=time.perf_counter()-start)]
    except BaseException as e:
        pipeline.update(status='failed',error=str(e));raise
    finally:
        pipeline['total_wall_seconds']=time.perf_counter()-start;write(output/'pipeline.json',pipeline)
    emit('completed',output=str(output),status='passed',seconds=pipeline['total_wall_seconds'])
    return pipeline
