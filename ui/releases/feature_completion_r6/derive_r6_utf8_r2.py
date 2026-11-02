"""Derive a self-contained comparison UI from the physically accepted R5."""
from pathlib import Path
import hashlib
import json
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=HERE.parent/'feature_completion_r4'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def write(name,text):
    path=HERE/name;assert not path.exists(),path
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(text.replace('\r\n','\n').encode('utf-8'))


def main():
    proof=json.loads((OLD/'source_closure_r5.json').read_text(encoding='utf-8'))
    for key in ('source_sha256','shared_source_sha256','old_source_sha256'):
        for name,digest in proof[key].items():assert sha(ROOT/name)==digest,name
    acceptance=json.loads((OLD/'acceptance_physical_catalogue_r2.json').read_text(encoding='utf-8'))
    assert sha(OLD/'build_r5/medical_ui')=='ea6efee66371071c2d220b5303f706659365f2cbe6808c4972c84e9daf462332'
    copied={}
    for path in sorted((OLD/'src').iterdir()):
        if path.suffix not in ('.cpp','.hpp','.inc') or path.name.startswith('main_'):continue
        copied[path.relative_to(ROOT).as_posix()]=sha(path)
        write('src/'+path.name,path.read_text(encoding='utf-8'))
    main=(OLD/'src/main_catalogue_r5.cpp').read_text(encoding='utf-8')
    main=main.replace('#include "views.hpp"','#include "views.hpp"\n#include "../reachability_chart.hpp"')
    main=main.replace('/ui/releases/feature_completion_r4/backend_r5.py','/ui/releases/feature_completion_r6/backend_r6.py')
    start=main.index(' void showComparisons(){');end=main.index('\n',start)
    assert main[start:end].endswith('dialog.exec();}')
    main=main[:start]+'#include "../comparison_dialog_r6.inc"'+main[end:]
    marker='if(qEnvironmentVariableIntValue("KV260_CATALOGUE_UI_TEST")==1)'
    assert main.count(marker)==1
    main=main.replace(marker,'if(qEnvironmentVariableIntValue("KV260_WHOLE_COMPARISON_UI_TEST")==1){QTimer::singleShot(400,this,[this]{if(!failed)showComparisons();close();if(failed)QApplication::exit(1);});}else '+marker)
    write('src/main_r6.cpp',main)
    # Only the preview widget gains setters; normal navigation remains intact.
    header=(HERE/'src/views.hpp').read_text(encoding='utf-8')
    header=header.replace(' void setScope(bool enabled);', ' void setPreviewRoute(const QJsonArray&); QJsonObject previewRouteMetrics()const;\n void setScope(bool enabled);')
    (HERE/'src/views.hpp').write_text(header,encoding='utf-8',newline='\n')
    source=(HERE/'src/views.cpp').read_text(encoding='utf-8')
    source+='''
void MeshView::setPreviewRoute(const QJsonArray&points){
 QVector<QVector3D> next;for(auto v:points){auto a=v.toArray();if(a.size()!=3)throw std::runtime_error("Invalid preview route coordinate");double x=a[0].toDouble(),y=a[1].toDouble(),z=a[2].toDouble();if(!std::isfinite(x)||!std::isfinite(y)||!std::isfinite(z))throw std::runtime_error("Nonfinite preview route coordinate");next.append(QVector3D(x,y,z));}if(next.isEmpty())throw std::runtime_error("Empty preview route");route=next;refresh();
}
QJsonObject MeshView::previewRouteMetrics()const{
 auto array=[](QVector3D v){return QJsonArray{v.x(),v.y(),v.z()};};return {{"point_count",route.size()},{"start_lps_mm",route.isEmpty()?QJsonArray():array(route.first())},{"end_lps_mm",route.isEmpty()?QJsonArray():array(route.last())}};
}
'''
    (HERE/'src/views.cpp').write_text(source,encoding='utf-8',newline='\n')
    for name in ('backend_core_r5.py','backend_r5.py','complete_import_r5.py','complete_features_r5.py',
                 'analysis_partial.py','reconstruction_partial.py'):
        text=(OLD/name).read_text(encoding='utf-8');new=name.replace('_r5','_r6')
        for before,after in [('backend_core_r5','backend_core_r6'),('complete_import_r5','complete_import_r6'),
                             ('complete_features_r5','complete_features_r6'),('feature_completion_r4','feature_completion_r6')]:text=text.replace(before,after)
        if name=='backend_core_r5.py':
            text=text.replace("str(UI/'features/navigation_task.py')", "str(Path(__file__).parent/'navigation_task_r6.py')")
            text=text.replace("result/'navigation/alternative_routes.json',", "result/'navigation/alternative_routes.json',result/'navigation/whole_instrument_profiles.json',result/'navigation/whole_alternative_routes.json',result/'navigation/whole_comparison_arrays.npz',")
        elif name=='analysis_partial.py':
            text=text.replace("('instrument_profiles','alternative_routes')", "('instrument_profiles','alternative_routes','whole_instrument_profiles','whole_alternative_routes')")
        write(new,text);copied[(OLD/name).relative_to(ROOT).as_posix()]=sha(OLD/name)
    task=(ROOT/'ui/features/navigation_task.py').read_text(encoding='utf-8')
    task=task.replace("SYSTEM=Path(__file__).resolve().parents[2]", "SYSTEM=Path(__file__).resolve().parents[3]")
    task=task.replace("str(Path(__file__).resolve().parents[1])", "str(SYSTEM/'ui')")
    task=task.replace("p.add_argument('--edt-core'", "p.add_argument('--comparison-profile-provider',choices=['PS4','verified-R1PL'],default='PS4');p.add_argument('--edt-core'")
    point="    result=dict(status='completed',backend='dfx_pl'"
    assert point in task
    addition='''    comparison_backend=None
    if a.compare:
        # VolumeNavigationSession has released its PL lock before opening any
        # distinct profile session. Do not nest reconfigurable module owners.
        sys.path.insert(0,str(SYSTEM/'modules/navigation_comparison'))
        from produce_r1 import produce,save
        if a.comparison_profile_provider=='verified-R1PL':
            sys.path.insert(0,str(SYSTEM/'dfx/navigation_profile'))
            from protocol_fast_r2 import R1AdapterSession
            from runtime_r1 import Session as VerifiedProfileSession
            class ProfileSession(R1AdapterSession,VerifiedProfileSession):pass
            with ProfileSession() as profile:
                whole,other,arrays=produce(c,target,profile.solve,provider_kind='verified_PL_R1',
                    scope_diameter_mm=a.scope_diameter_mm,safety_margin_mm=a.safety_margin_mm,
                    minimum_bend_radius_mm=a.minimum_bend_radius_mm)
        else:
            from profile_session_r2 import ProfilePS
            profile=ProfilePS()
            provider=lambda g,d,m,w:profile.solve(g,d,m,w,threads=4)[1:]
            whole,other,arrays=produce(c,target,provider,provider_kind='optimized_PS4',
                scope_diameter_mm=a.scope_diameter_mm,safety_margin_mm=a.safety_margin_mm,
                minimum_bend_radius_mm=a.minimum_bend_radius_mm)
        save(output,whole,other,arrays);comparison_backend=whole['profile_backend']
'''
    task=task.replace(point,addition+point)
    task=task.replace("result['edt_core']=", "result['whole_comparison_backend']=comparison_backend\n    result['actual_navigation_route_replaced_by_comparison']=False\n    result['edt_core']=")
    write('navigation_task_r6.py',task)
    run=(OLD/'run_r5.sh').read_text(encoding='utf-8').replace('feature_completion_r4/build_r5','feature_completion_r6/build_r6')
    write('run_r6.sh',run)
    build=(OLD/'build_r5.sh').read_text(encoding='utf-8')
    build=build.replace('build_r5','build_r6').replace('source_closure_r5','source_closure_r6').replace('main_catalogue_r5.cpp','main_r6.cpp')
    build=build.replace('independent_catalogue_UI_compiled_actual_ARM','whole_profile_comparison_UI_compiled_actual_ARM')
    write('build_r6.sh',build)
    # Numeric test certificates bind the new report producer to the full oracle.
    for host in ('Windows','ARM'):
        previous=json.loads((ROOT/f'modules/navigation_comparison/results/full_candidates_{host}_r2.json').read_text(encoding='utf-8'))
        assert previous['full_profile_fixture_sha256'] and len(previous['cases'])==10
    comparison_names=('produce_r1.py','profile_r1.py','profile_session_r2.py','candidates_r2.py','path_rules_r1.py','pareto_r1.py')
    shared=dict(proof['shared_source_sha256'])
    for name in comparison_names:shared['modules/navigation_comparison/'+name]=sha(ROOT/'modules/navigation_comparison'/name)
    for name in ('ui/features/navigation_task.py','modules/navigation/navigation/pipeline.py',
                 'dfx/route_audit_speed/protocol.py','dfx/route_audit_speed/checked_plan.py'):
        shared[name]=sha(ROOT/name)
    record=dict(status='derived_self_contained_R6_UI_for_original_full_raw_comparisons',
        original_R5_binary_sha256=sha(OLD/'build_r5/medical_ui'),
        original_R5_closure_sha256=sha(OLD/'source_closure_r5.json'),
        original_human_catalogue_acceptance_sha256=sha(OLD/'acceptance_physical_catalogue_r2.json'),
        accepted_UI_binary_sha256=proof['accepted_UI_binary_sha256'],C9_release_sha256=proof['C9_release_sha256'],
        shared_source_sha256=shared,old_source_sha256=copied,
        original_task_sha256=sha(ROOT/'ui/features/navigation_task.py'),
        PL_algorithms_changed=False,runtime_old_candidate_imports=False,
        comparison_default_provider='optimized_PS4',
        reason_PS4='Verified R1 complete raw profile API is slower than optimized PS4; no new unverified core exposed.',
        actual_navigation_keeps_PL_EDT_route_bend_clearance_camera=True,
        whole_alternative_paths_preview_only=True,source_sha256={})
    record['source_sha256']={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and p.suffix in ('.py','.cpp','.hpp','.inc','.sh')}
    path=HERE/'source_closure_r6.json';assert not path.exists()
    path.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(record['status'],len(record['source_sha256']),flush=True)


if __name__=='__main__':main()
