"""Explicit comparison and selected-path preparation on one immutable C1 surface.

CPU control/preparation surrounds the accepted C9 renderer. R12 measured the
existing R4 profile accelerator slower than native PS, so profile solve uses PS4.
No bitstream load, PS Marching Cubes, source-scene mutation or UI promotion.
"""
from pathlib import Path
import copy,json,os,tempfile
from time import perf_counter
import numpy as np
import SimpleITK as sitk
from modules.surface_route.comparison_r15 import Comparison
from modules.surface_route.comparison_r11 import solve_all
from modules.surface_route.bundle_r8 import arrays,write_json,build_bundle
from modules.surface_route.verification_session_r15 import sha,verify_bundle
from modules.surface_route.selected_surface_r13 import audit_selected
from modules.surface_route.guidance_r13 import build_guidance
from profile_session_r2 import ProfilePS

ROOT=Path(__file__).resolve().parents[2]
COMPARISON_FILES=('whole_instrument_profiles.json','whole_alternative_routes.json','whole_comparison_arrays.npz')


def verify_sources():
    path=ROOT/'modules/surface_route/selected_source_closure_r13.json'
    closure=json.loads(path.read_text(encoding='utf-8'))
    for name,expected in closure['files_sha256'].items():
        p=(ROOT/name).resolve()
        if not p.is_relative_to(ROOT) or sha(p)!=expected:raise ValueError('Changed R13 source: '+name)
    for name,expected in closure['sealed_parent_closures_sha256'].items():
        p=(ROOT/name).resolve()
        if not p.is_relative_to(ROOT) or sha(p)!=expected:raise ValueError('Changed sealed parent closure: '+name)
        for source,digest in json.loads(p.read_text(encoding='utf-8'))['files_sha256'].items():
            if sha(ROOT/source)!=digest:raise ValueError('Changed sealed parent source: '+source)
    platform='Windows' if os.name=='nt' else 'ARM'
    build=ROOT/f'modules/navigation_comparison/results/profile_{platform}_r1.json'
    proof=json.loads(build.read_text(encoding='utf-8'))
    library=ROOT/'modules/navigation_comparison/build'/('profile_ps_r1.dll' if os.name=='nt' else 'libprofile_ps_r1.so')
    if sha(library)!=proof['library_sha256']:raise ValueError('Changed native profile library')
    for name,expected in proof['source_sha256'].items():
        if sha(ROOT/'modules/navigation_comparison'/name)!=expected:raise ValueError('Changed profile native source')
    return sha(path)


def prepare_comparison(comp,output,*,diameters=(1.,1.2,1.8,2.8,4.),margin=.3,bend=0.):
    closure=verify_sources();output=Path(output).resolve()
    if not output.is_relative_to(ROOT) or output.exists():raise ValueError('Fresh project comparison output required')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.'+output.name+'-',dir=output.parent))
    start=perf_counter();q=comp.queries(diameters,margin);prep=perf_counter()-start
    cpu=ProfilePS();start=perf_counter();values=solve_all(q,lambda g,d,m,w:cpu.solve(g,d,m,w,4)[1:]);solve=perf_counter()-start
    start=perf_counter();whole,alternative,data=comp.produce(q,*values,minimum_bend_radius_mm=bend);reports=perf_counter()-start
    write_json(stage/COMPARISON_FILES[0],whole);write_json(stage/COMPARISON_FILES[1],alternative)
    np.savez_compressed(stage/COMPARISON_FILES[2],**data)
    proof=dict(schema='kv260.surface_route.comparison_action.v1',complete=True,binding=comp.binding,
        files_sha256={name:sha(stage/name) for name in COMPARISON_FILES},source_closure_sha256=closure,
        backend='optimized_PS4_native',selection_reason='R12 same-input actual R4 slower than strongest PS',
        query_preparation_seconds=prep,solve_API_seconds=solve,full_report_API_seconds=reports,
        total_preparation_seconds=perf_counter()-start+prep+solve,
        PL_access=False,new_bitstream=False,production_promoted=False)
    write_json(stage/'comparison.json',proof);os.rename(stage,output)
    return proof


def verify_comparison(folder,comp):
    folder=Path(folder).resolve()
    if not folder.is_relative_to(ROOT):raise ValueError('Project comparison required')
    proof=json.loads((folder/'comparison.json').read_text(encoding='utf-8'))
    if (proof.get('schema')!='kv260.surface_route.comparison_action.v1' or proof.get('complete') is not True
            or proof['source_closure_sha256']!=verify_sources() or set(proof['files_sha256'])!=set(COMPARISON_FILES)):
        raise ValueError('Complete source-bound comparison required')
    for name,expected in proof['files_sha256'].items():
        p=folder/name
        if p.is_symlink() or sha(p)!=expected:raise ValueError('Changed comparison payload: '+name)
    for key in ('scalar_sha256','mesh_sha256','CT_input_sha256','centerline_id','source_files_sha256','target'):
        if proof['binding'][key]!=comp.binding[key]:raise ValueError('Comparison belongs to another surface or target: '+key)
    for name in COMPARISON_FILES[:2]:
        if json.loads((folder/name).read_text(encoding='utf-8'))['binding']!=proof['binding']:
            raise ValueError('Report and comparison receipt differ')
    return proof


def prepare_selected(comp,parent_bundle,comparison,group,candidate,output,*,auditor=None):
    parent_bundle=Path(parent_bundle).resolve();comparison=Path(comparison).resolve()
    meta=verify_bundle(parent_bundle);proof=verify_comparison(comparison,comp)
    if (sha(parent_bundle/'mesh.npz')!=comp.binding['mesh_sha256']
            or meta['renderer_scalar_sha256']!=comp.field.sha256):
        raise ValueError('Selected output and active mesh/scalar differ')
    start=perf_counter()
    report,route,camera,context=audit_selected(comp,comparison,group,candidate,auditor=auditor)
    audit_seconds=perf_counter()-start
    source=Path(comp.binding['source_result'])/'segmentation/airway_mask.nii.gz'
    image=sitk.ReadImage(str(source));start=perf_counter()
    guidance,targets=build_guidance(context,route,comp.field,image)
    guidance['source_forest_or_mask_changed']=bool(report['guidance_forest']['changed'])
    guidance['selected_guidance_forest']=report['guidance_forest']
    report.update(branch_guidance_application_pending=False,
        branch_guidance_and_current_complete_UI_integration_pending=True,
        complete_bundle_prepared=True,native_UI_selection_integration_pending=True)
    guidance_seconds=perf_counter()-start
    provenance=copy.deepcopy(meta['identity']['provenance'])
    bindings={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [parent_bundle/'scene.json',comparison/'comparison.json',
        *[comparison/name for name in COMPARISON_FILES],ROOT/'modules/surface_route/selected_source_closure_r13.json']}
    provenance['input_sha256'].update(bindings)
    provenance.update(selected_complete_polyline=report['selection'],parent_revision=meta['revision'],
        parent_route_id=meta['route_id'],selected_preparation_backend='PS_actual_wall_checked_prefix',
        current_turn_PL_access=False,original_probability_or_binary_field_unchanged=True)
    mesh=arrays(parent_bundle/'mesh.npz');start=perf_counter()
    result=build_bundle(output,scalar=comp.field.values,geometry=comp.field.geometry,bits=comp.field.bits,
        points=mesh['points'],faces=mesh['faces'],mesh_proof=meta['identity']['mesh_proof'],
        route=route,report=report,camera=camera,guidance=guidance,targets=targets,provenance=provenance)
    return dict(revision=result['revision'],route_id=result['route_id'],point_count=len(route['arc_mm']),
        available_branch_events=sum(e['available'] for e in guidance['events']),
        audit_seconds=audit_seconds,guidance_seconds=guidance_seconds,bundle_seconds=perf_counter()-start,
        requested_original_endpoint=int(report['requested_endpoint_id']),length_mm=report['length_mm'],
        bend_prefix_queries=report['bend_prefix_queries'],native_UI_selection_integration_pending=True,
        new_bitstream=False,PL_access=auditor is not None and str(auditor.backend).startswith('PL'))
