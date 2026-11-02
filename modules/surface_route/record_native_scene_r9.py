"""Record measured native scene integration; keep broader goal and PL gates open."""
from pathlib import Path
import json
import hashlib

ROOT=Path(__file__).resolve().parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))


def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def main():
    folder=ROOT/'modules/surface_route'
    native=read(folder/'results/native_scene_ARM_r9/acceptance.json')
    gui=read(folder/'results/native_GUI_ARM_r9/acceptance.json')
    live=read(ROOT/'results/complete_scene_live_r9.json')
    assert native['status']=='eight_complete_native_Qt_scene_assets_and_actual_camera_protocol_verified'
    assert gui['status']=='actual_HDMI_complete_scene_model_UI_passed_no_PL_access'
    assert len(native['cases'])==8 and native['native_Qt_requests_accepted']==12
    sources=sorted(set([*folder.glob('*r9*.py'),*folder.glob('*r9*.hpp'),*folder.glob('*r9*.cpp'),
        *folder.glob('*derivation_r9*.json'),*folder.glob('*closure_r9*.json'),
        *ROOT.glob('ui/releases/feature_completion_r6/src/*complete*r9*'),
        *ROOT.glob('tools/*complete*scene*r9*.py'),ROOT/'tools/test_complete_worker_guard_r9.py']))
    evidence=sorted(set([*folder.glob('results/native*ARM_r9*.json'),
        *folder.glob('results/native*ARM_r9*.log'),*folder.glob('results/scene_protocol_*_r9.json'),
        *folder.glob('results/worker_*_r9.json'),*folder.glob('results/transfer_cleanup_*_r9.json'),
        *folder.glob('results/native_scene_ARM_r9/**/*.json'),*folder.glob('results/native_GUI_ARM_r9/*'),
        ROOT/'results/complete_scene_live_r9.json',folder/'work_checkpoint_r8.json',
        ROOT/'ui/releases/feature_completion_r6/build_complete_scene_r9b/build.json',
        ROOT/'ui/releases/feature_completion_r6/build_complete_scene_r9/failure.json']))
    checkpoint=dict(status='eight_complete_native_scenes_Qt_protocol_and_HDMI_model_UI_verified_C9_pending',
        goal_turn_classification='progress',whole_goal_completed=False,production_promoted=False,
        source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sources},
        evidence_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in evidence if p.is_file()},
        current_board_state=live,PL_access_this_milestone=False,new_bitstream=False,
        validation=dict(Windows_actual_pose_protocol_checks=13,ARM_actual_pose_protocol_checks=13,
            complete_native_scenes=8,actual_Qt_camera_requests=12,
            actual_HDMI_model_interaction_stages=3,user_physical_review=False,
            Qt_request_validation_ms=native['native_Qt_pose_validation_ms'],
            cold_scene_prepare_seconds_range=[min(c['preparation_seconds'] for c in native['cases']),
                                               max(c['preparation_seconds'] for c in native['cases'])],
            GUI_process_peak_RSS_MiB=gui['UI_peak_RSS_MiB'],
            statistics_are_not_C9_render_time_or_UI_FPS=True),
        computation=dict(PS='scene/asset proof validation, new mesh attributes, cached request and HUD dispatch',
                         GPU='actual HDMI overview geometry and coloring',
                         PL='existing C1 extraction proof retained; C9 transport integrated, not accessed in this milestone'),
        known_failure='First full UI build failed Qt5 ambiguous brace assignment; preserved source/log, explicit QStringList R9b compiled and ran.',
        next_actions=['Add explicit native scene/quality controls with cooperative drain and no automatic delayed model changes',
            'Complete active-new-surface export, profile/Pareto and media dispatch rather than legacy result references',
            'Reduce repeated cold case/asset hashing and verification while retaining exact content binding',
            'Safely initialize medical static without the old ZOCL-unload path, then replay exact original-field requests on C9 against strongest PS',
            'Complete remaining original live image effects, performance and export/physical reviews; broad goal remains intact'])
    write(folder/'work_checkpoint_r9.json',checkpoint)
    previous={}
    for relative in ['docs/FEATURE_COMPLETION_PROGRESS.json','dfx/smooth_speed/work_checkpoint.json']:
        path=ROOT/relative;previous[relative]=sha(path);value=read(path)
        value['previous_goal_turn_classification']='no_progress_revalidated_existing_physical_acceptance'
        value['current_goal_turn_result']=dict(classification='progress',checkpoint='modules/surface_route/work_checkpoint_r9.json',
            status=checkpoint['status'],whole_goal_completed=False,production_promoted=False)
        value['current_surface_route_checkpoint']='modules/surface_route/work_checkpoint_r9.json'
        if relative.startswith('docs/'):
            value['current_board_UI_state']=live
        else:
            value['status']='active_original_feature_completion_complete_native_scene_R9_actual_C9_pending'
            value['last_current_board_state_receipt']='results/complete_scene_live_r9.json'
            value['current_board_boot_id']=live['boot_id']
            value['latest_original_surface_UI_promoted']=False
        with path.open('w',encoding='utf-8',newline='\n') as stream:
            stream.write(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    write(folder/'results/native_scene_progress_plan_r9.json',dict(files={relative:dict(
        previous_sha256=old,new_sha256=sha(ROOT/relative)) for relative,old in previous.items()}))
    print(checkpoint['status'])


if __name__=='__main__':main()
