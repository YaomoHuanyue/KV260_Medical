"""Seal revised-route cues only after actual same-input C9/PS and UI restore."""
from pathlib import Path
import hashlib, json, sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
READ=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))


def main():
    out=HERE/'work_checkpoint_r5.json'
    live=ROOT/'results/surface_guidance_R17_live_r5.json'
    assert not out.exists() and not live.exists()
    sys.path.insert(0,str(ROOT/'dfx/navigation_profile'))
    from test_with_UI_restore_r4_2 import ui_binding,BOOT
    sys.path.insert(0,str(ROOT/'dfx/surface_quality'))
    from quality_runtime import verify
    verify()
    _,pid=ui_binding()
    restore=READ(HERE/'results/state_after_board_guidance_r5.json')
    assert restore['status']=='accepted_default_UI_and_C6_restored_after_independent_C9_guidance_trial'
    assert restore['PID']==pid and restore['trial_exit_code']==0 and restore['boot_id']==BOOT
    assert restore['accepted_volume_lifecycle_and_C6_restore_passed'] and restore['PL_lock_free_before_UI_launch']
    assert not any(restore[k] for k in ('static_shell_reloaded','ZOCL_unloaded','forced_kill_or_reset'))
    for name,digest in restore['source_sha256'].items():assert SHA(HERE/name)==digest,name
    board=READ(HERE/'results/own_board_guidance_r5.json')
    assert board['status']=='six_revised_route_selected_branch_frames_exact_PS1_PS4_C9_compared_C6_restored'
    assert board['full_static_one_MiB_echo_and_C6_restore_passed'] and board['boot_id']==BOOT
    assert len(board['cases'])==6
    for name,digest in board['source_sha256'].items():assert SHA(ROOT/name)==digest,name
    for case in board['cases']:
        assert case['width']==640 and case['height']==363 and case['maximum_ray_steps']==1023
        assert case['full_232320_depth_normal_target_and_outline_pixels_exact']
        assert case['full_four_4096_byte_DMA_guards_passed']
        assert case['selected_pixels']>0 and case['outline_pixels']>0
        assert case['performance_gate_passed']==(case['PL_median_full_API_seconds']<=min(case['PS_median_full_API_seconds'].values()))
    assert board['all_six_cases_faster_than_strongest_PS']==all(c['performance_gate_passed'] for c in board['cases'])
    cross=READ(HERE/'results/guidance_cross_platform_r5.json')
    assert cross['status']=='eight_Windows_ARM_curves_cameras_selected_exits_and_targets_match_six_C9_packets_byte_exact'
    assert cross['source_sha256']==SHA(HERE/'compare_guidance_receipts_r5.py')
    evidence={}
    for platform in ('Windows','ARM'):
        folder=HERE/f'results/guidance_own_CT_{platform}_r5'
        own=READ(folder/'acceptance.json')
        assert len(own['scenarios'])==8 and len(own['render_cases'])==6
        assert cross['evidence_sha256'][platform]==SHA(folder/'acceptance.json')
        for name,digest in {**own['source_sha256'],**own['input_sha256']}.items():assert SHA(ROOT/name)==digest,name
        for scenario in own['scenarios']:
            for name,digest in scenario['files_sha256'].items():assert SHA(folder/name)==digest,name
        for case in own['render_cases']:
            for name,digest in case['files_sha256'].items():assert SHA(folder/'render_cases'/name)==digest,name
        for p in folder.rglob('*'):
            if p.is_file():evidence[p.relative_to(ROOT).as_posix()]=SHA(p)
        # The old R4 receipts close over the native geometric/audit baseline,
        # which was used unchanged by the new preparation implementation.
        old=READ(HERE/f'results/curve_own_CT_{platform}_r4/acceptance.json')
        for name,digest in old['source_sha256'].items():assert SHA(ROOT/name)==digest,name
    for name in ('guidance_unit_Windows_r5.json','guidance_unit_ARM_r5.json'):
        proof=READ(HERE/'results'/name)
        assert proof['status']=='all_displaced_guidance_geometry_ownership_and_negative_cases_passed' and len(proof['tests'])==7
    source_names=['curve_guidance_r5.py','curve_guidance_derivation_r5.json','guidance_r5.py','test_guidance_r5.py',
        'own_guidance_trial_r5.py','compare_guidance_receipts_r5.py','compare_guidance_board_r5.py',
        'with_guidance_UI_restore_r5.py','guidance_board_derivation_r5.json','record_guidance_r5.py','README_GUIDANCE_r5.md']
    for name in ('guidance_unit_Windows_r5.json','guidance_unit_ARM_r5.json','guidance_cross_platform_r5.json',
                 'own_board_guidance_r5.json','state_after_board_guidance_r5.json','board_guidance_trial_started_r5.json'):
        path=HERE/'results'/name;evidence[path.relative_to(ROOT).as_posix()]=SHA(path)
    accepted=READ(ROOT/'dfx/surface_quality/docs/board_acceptance_r7.json')
    record=dict(status='R5_retained_source_arc_restores_displaced_junction_guidance_Windows_ARM_actual_C9_exact_PS_PL_compared',
        goal_turn_classification='progress',whole_goal_completed=False,
        board_UI=dict(PID=pid,boot_id=BOOT,release='complete_feature_UI_with_interactive_xray_surface_preset_r1',
            restore_receipt='modules/surface_route/results/state_after_board_guidance_r5.json',
            original_default_UI_and_C6_restored=True,new_geometry_or_guidance_default_promoted=False),
        source_sha256={('modules/surface_route/'+name):SHA(HERE/name) for name in source_names},
        evidence_sha256=evidence,
        own_CT=dict(scenarios=8,Windows_and_ARM_geometry_camera_audit_unchanged_from_R4=True,
            displaced_one_mm_bend_curve_old_guidance_events=0,displaced_one_mm_bend_curve_new_guidance_events=3,
            selected_branches=[80,51,52],scalar_geometry_used_for_apertures_visibility_and_target_clipping=True,
            root_only_route_never_generates_forward_exit_cue=True,
            one_mm_curve_length_mm=166.76242827012666,one_mm_curve_candidate_gap_mm=81.35641843023643,
            reach_status='limited_reach_remains_not_candidate_reached'),
        same_input_C9_PS_PL=dict(cases=board['cases'],all_six_cases_faster_than_strongest_PS=board['all_six_cases_faster_than_strongest_PS'],
            timing_scope=board['timing_scope'],peak_process_RSS_MiB=board['peak_process_RSS_MiB'],
            new_bitstream=False,resource_usage_changed=False,existing_C9_resources=accepted['routed_resources'],
            existing_C9_remaining_RP=accepted['remaining_RP']),
        computation_split=dict(PS='Retained graph decisions, physical source-arc mapping, once-per-route labels and camera input',
            PL='Accepted C9 exact scalar ray traversal, depth, normals, selected target and outline per frame'),
        remaining=['Original probability/isotropic SDF surface extraction and geometry-filtered replan',
            'Complete new scalar/mesh/route/camera/guidance UI bundle and physical review',
            'Original remaining visual/export features and profile/smoothing full-API acceleration'],
        production_promoted=False,PS_Marching_Cubes_used=False,clinical_safety_certified=False)
    out.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    state=dict(status='R17_identity_and_default_C6_UI_verified_after_R5_C9_guidance_comparison',
        PID=pid,boot_id=BOOT,UI_binary_sha256=restore['UI_binary_sha256'],
        default_descriptor_sha256=restore['default_descriptor_sha256'],manual_entry_sha256=restore['manual_entry_sha256'],
        restoration_receipt='modules/surface_route/results/state_after_board_guidance_r5.json',
        restoration_receipt_sha256=SHA(HERE/'results/state_after_board_guidance_r5.json'),
        new_geometry_or_guidance_default_promoted=False,static_shell_reloaded=False,ZOCL_unloaded=False)
    live.write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(record['status'],'restored_UI',pid,flush=True)


if __name__=='__main__':main()
