"""Check the immutable application and tested worker before a manual launch."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def checked(name):
 r=PurePosixPath(name)
 assert not r.is_absolute() and '..' not in r.parts and ':' not in name and '\\' not in name
 p=(ROOT/name).resolve();assert p.is_relative_to(ROOT) and p.is_file(),name
 return p
def verify(descriptor):
 p=checked(descriptor);r=json.loads(p.read_text(encoding='utf-8'))
 assert r['schema']=='kv260.manual_UI_release.v1' and r['auto_start']==False
 for group in ('launch_source_sha256','proof_sha256'):
  assert r[group]
  for n,d in r[group].items():assert sha(checked(n))==d,n
 for record in (r['UI_build'],r['composite_build']):
  for key in ('source_sha256','shared_source_sha256','library_sha256'):
   for n,d in record.get(key,{}).items():assert sha(checked(n))==d,n
 assert sha(checked(r['binary']))==r['UI_build']['binary_sha256']
 assert sha(checked(r['composite_binary']))==r['composite_build']['binary_sha256']
 ui=json.loads(checked(r['UI_build_file']).read_text(encoding='utf-8'))
 comp=json.loads(checked(r['composite_build_file']).read_text(encoding='utf-8'))
 assert ui==r['UI_build'] and comp==r['composite_build']
 accepted=json.loads(checked(r['composite_acceptance']).read_text(encoding='utf-8'))
 assert accepted['build']==comp and accepted['controls_compared']==17 and accepted['all_complete_layers_and_final_pixels_bit_exact']
 assert accepted['chosen']['options']==['baseline','1']
 assert accepted['status'] in ('passed_complete_original_CT_controls_layers_final_RGBA_same_input_PS_PL_and_warm_ABBA_speedup','passed_exact_layers_opacity_recomposition_speedup')
 if accepted['status']=='passed_exact_layers_opacity_recomposition_speedup':
  assert accepted['opacity_boundary_cases']==7 and accepted['rotation_timing_always_recomputes_geometry']
  if accepted['chosen']['mode']=='two_slot_ID_color_GPU_opacity_cache':
   assert accepted['additional_transparent_geometry_cases']==6
   assert accepted['build']['normal_UI_color_layers_remain_on_GPU']
   assert accepted['build']['GPU_cached_opacity_updates']
   assert accepted['build']['two_slot_grouped_ID_color']
   assert accepted['build']['source_buffer_reuse_only_after_completed_color']
   assert accepted['build']['draws_between_CPU_completion_waits']==4
   assert accepted['build']['extra_geometry_VBO_storage_bytes_limit']==8064000
   assert accepted['warm_transport']=='actual_UI_tmpfs_after_capture_sync'
   assert accepted['speedup']['opacity_warm']>.9 and accepted['speedup']['rotate']>1.05
  elif accepted['chosen']['mode']=='single_VBO_paired_ID_color_async':
   assert accepted['additional_transparent_geometry_cases']==6
   assert accepted['build']['extra_geometry_VBO_storage_bytes']==0
   assert accepted['build']['source_buffer_reuse_only_after_completed_color']
   assert accepted['build']['draws_between_CPU_completion_waits']==2
   assert accepted['warm_transport']=='actual_UI_tmpfs_after_capture_sync'
   assert accepted['speedup']['opacity_warm']>.9 and accepted['speedup']['rotate']>1.02
  elif accepted['chosen']['mode']=='parallel_bounds_and_visible_mesh_preparation':
   assert accepted['additional_transparent_geometry_cases']==6
   assert accepted['speedup']['opacity_warm']>.9 and accepted['speedup']['rotate']>1.02
  else:
   assert accepted['speedup']['opacity_warm']>1 and accepted['speedup']['rotate']>1
 fixed=json.loads(checked(r['fast_opacity_acceptance']).read_text())
 assert fixed['status']=='passed' and fixed['failed_cases']==0 and len(fixed['cases'])==48
 assert fixed['precise_checkbox_unchecked'] and fixed['slider_right_endpoint_opacity']==1
 assert fixed['widget_stencil_bits']>=8 and fixed['real_CT_meshes_used']
 assert not fixed['disk_geometry_changed'] and not fixed['precise_PL_worker_used']
 assert all(c['framebuffer_alpha_preserved'] for c in fixed['cases'])
 assert fixed['opacity_cache_passed'] and fixed['camera_invalidates_cache']
 native=json.loads(checked(r['native_media_acceptance']).read_text())
 assert native['status']=='passed_actual_GUI_full_route_video_setup_cancel_PL_cancel_codec_failure_camera_restore'
 assert [x['status'] for x in native['exports']]==['setup_cancelled','completed','cancelled','failed']
 assert native['exports'][0]['camera_unchanged']
 assert all(x['restored'] and x['restored_camera']==native['before']['camera'] for x in native['exports'][1:])
 video=json.loads(checked(r['native_media_video_acceptance']).read_text())
 assert video['status']=='passed_complete_route_MP4_decode_timeline_and_same_input_PS1_PS4_PL_full_pixels'
 assert not video['GUI_export_button_pending'] and len(video['frame_checks'])==6
 assert all(x['raw_depth_outline_and_normals_bit_exact'] for x in video['frame_checks'])
 assert sha(Path('/usr/bin/ffmpeg'))==r['UI_build']['ffmpeg_sha256']
 native=json.loads(checked(r['linked_media_acceptance']).read_text())
 assert native['status']=='passed_actual_GUI_single_and_linked_full_route_video_cancel_failure_view_restore'
 assert [x['status'] for x in native['exports']]==['setup_cancelled','completed','completed','cancelled','failed']
 assert native['exports'][0]['camera_unchanged']
 assert all(x['restored'] and x['overview_restored'] and x['restored_camera']==native['before']['camera'] and x['restored_overview_camera']==native['before']['overview_camera'] for x in native['exports'][1:])
 assert native['exports'][3]['cancel_requested_while_awaiting_PL']
 assert len(r['linked_media_movie_acceptances'])==2
 for path,linked in zip(r['linked_media_movie_acceptances'],(False,True)):
  video=json.loads(checked(path).read_text())
  assert video['status']=='passed_complete_route_MP4_decode_timeline_and_same_input_PS1_PS4_PL_full_pixels'
  assert video['linked_overview_enabled']==linked and not video['GUI_export_button_pending']
  assert len(video['frame_checks'])==6 and all(x['raw_depth_outline_and_normals_bit_exact'] for x in video['frame_checks'])
  if linked:assert video['all_route_frames_reference_pose_synced'] and len(video['linked_reference_checks'])==3 and any(x['cyan_camera_marker_found'] for x in video['linked_reference_checks'])
 geometry=json.loads(checked(r['linked_media_geometry_acceptance']).read_text())
 assert geometry['status']=='passed_same_CT_meshes_unchanged_through_single_and_linked_GUI_trials'
 for path,digest in geometry['input_mesh_scene_sha256'].items():assert sha(ROOT/path)==digest,path
 batch=json.loads(checked(r['batch_UI_summary']).read_text())
 assert batch['status']=='passed_native_C8_sixteen_and_routeless_fourteen_images_three_cancels_failure_and_48_depth_cases'
 assert batch['binary_sha256']==r['previous_UI_binary_sha256'] and batch['original_inputs_unchanged']
 prior=json.loads(checked(r['previous_UI_build_file']).read_text());assert prior['binary_sha256']==batch['binary_sha256']
 trials={t['kind']:t for t in batch['trials']}
 assert set(trials)=={'complete','no_route','cancel_wait_frame','cancel_view','cancel_C8','fail_helper','depth'}
 for kind,t in trials.items():
  assert sha(checked(t['receipt']))==t['sha256'];u=json.loads(checked(t['receipt']).read_text())
  if kind=='depth':assert u['status']=='passed' and u['failed_cases']==0;continue
  assert u['restored'] and u['exact_mode_restored'] and u['scope_before']==u['scope_after'] and u['overview_before']==u['overview_after']
  if kind in ('complete','no_route'):assert u['status']=='completed'
  elif kind.startswith('cancel_'):assert u['status']=='cancelled' and u['cancel_button_clicked']
  else:assert u['status']=='failed' and u['error']
  if kind=='cancel_wait_frame':assert u['cancel_requested_while_awaiting_PL']
  if kind=='cancel_C8':assert u['cancel_requested_during_C8_API']
 assert len(r['batch_export_acceptances'])==2
 for name,navigation in zip(r['batch_export_acceptances'],(True,False)):
  a=json.loads(checked(name).read_text());assert a['status']=='passed_native_batch_C8_original_quantized_fields_heatmap_and_conditional_navigation'
  assert a['navigation_available']==navigation and len(a['sizes'])==(16 if navigation else 14)
  assert a['original_glow_exposure_and_multivolume_heatmap_all_RGB_exact']
  if navigation:assert a['raw_C6_depth_outline_normal_all_pixels_exact_PS1_and_PS4']
 c8=json.loads(checked(r['batch_C8_same_input_acceptance']).read_text())
 assert c8['status']=='passed_original_fields_steps_RGB_and_strongest_PS_speed_gate' and c8['all_three_layers_PL_faster_strongest_PS']
 eligibility=json.loads(checked(r['batch_C8_eligibility']).read_text())
 assert eligibility['acceptance']==r['batch_C8_same_input_acceptance'] and eligibility['acceptance_sha256']==sha(checked(eligibility['acceptance']))
 reports=json.loads(checked(r['complete_reports_UI_summary']).read_text())
 assert reports['status']=='actual_Qt_complete_report_bundle_export_and_48_opacity_cases_passed'
 assert reports['binary_sha256']==r['xray_parent_UI_binary_sha256'] and reports['source_result_files_unchanged']
 assert not reports['new_bitstream']
 trials={t['kind']:t for t in reports['trials']};assert set(trials)=={'export','depth'}
 for t in trials.values():assert sha(checked(t['receipt']))==t['sha256']
 event=json.loads(checked(trials['export']['receipt']).read_text())
 assert event['status']=='passed_actual_Qt_export_control_and_async_colored_bundle' and event['heartbeat_ticks_during_export']>=2
 folder=checked(r['complete_reports_export']+'/report.json').parent
 assert folder==Path(event['event']['path']) and folder.is_relative_to(ROOT/'ui/exports')
 bundle=json.loads((folder/'report.json').read_text());index=json.loads((folder/'reports/index.json').read_text())
 assert bundle['schema']=='kv260.export.v5' and bundle['complete_reports_sha256']==sha(folder/'reports/index.json')
 assert index['schema']=='kv260.export.complete_reports.v1' and index['status']=='completed'
 assert index['full_profile_state']=='exported' and index['selected_route_state']=='exported_with_original_audit'
 assert index['profile_query_count']==5 and index['candidate_count']==48
 assert not index['medical_results_recomputed'] and not index['PL_bitstream_changed']
 assert index['chart']['original_reachable_row_filter'] and index['chart']['chart_sha256']==sha(folder/'reports/reachability_chart.png')
 for name,digest in index['files'].items():
  target=(folder/'reports'/name).resolve();assert target.is_relative_to(folder/'reports') and sha(target)==digest,name
 chart=json.loads(checked(r['complete_reports_chart_build']).read_text())
 assert chart['status']=='compiled_headless_native_Qt_chart' and sha(checked('modules/report_export/build/report_chart'))==chart['binary_sha256']
 for name,digest in chart['source_sha256'].items():assert sha(checked(name))==digest,name
 assert index['chart']['binary_sha256']==chart['binary_sha256']
 derivation=json.loads(checked(r['complete_reports_derivation']).read_text())
 before=checked(derivation['baseline']);after=checked(derivation['candidate'])
 assert sha(before)==derivation['baseline_sha256'] and sha(after)==derivation['candidate_sha256']
 assert r['UI_build']['source_sha256'][derivation['candidate']]==sha(after)
 assert prior['source_sha256'][derivation['baseline']]==sha(before)
 text=after.read_bytes().decode()
 assert len(derivation['replacements'])==3
 for change in derivation['replacements']:
  assert text.count(change['after'])==1;text=text.replace(change['after'],change['before'])
 assert text.encode()==before.read_bytes()
 report_depth=json.loads(checked(trials['depth']['receipt']).read_text())
 assert report_depth['status']=='passed' and report_depth['failed_cases']==0 and len(report_depth['cases'])==48
 xray=json.loads(checked(r['xray_UI_summary']).read_text())
 assert xray['status']=='actual_Qt_xray_controls_48_opacity_cases_and_complete_C7_PS_comparison_passed'
 assert xray['binary_sha256']==r['UI_build']['binary_sha256'] and not xray['new_bitstream']
 trials={t['kind']:t for t in xray['trials']};assert set(trials)=={'xray','depth'}
 for t in trials.values():assert sha(checked(t['receipt']))==t['sha256']
 controls=json.loads(checked(trials['xray']['receipt']).read_text())
 assert controls['status']=='passed_actual_Qt_xray_preset_state_and_manual_pixel_equivalence'
 assert len(controls['cases'])==10 and all(c['passed'] for c in controls['cases'])
 assert controls['baseline_request']['full_lung'] and abs(controls['baseline_request']['lung_opacity']-.1)<1e-6
 assert fixed==json.loads(checked(trials['depth']['receipt']).read_text())
 worker=json.loads(checked(r['xray_worker_acceptance']).read_text())
 assert sha(checked(r['xray_worker_acceptance']))==xray['worker_acceptance_sha256']
 assert worker['worker_sha256']==r['composite_build']['binary_sha256'] and worker['C6_restored']
 assert worker['status']=='complete_actual_Qt_xray_request_C7_and_all_strong_PS_pixels_exact'
 assert worker['UI_proof']==trials['xray']['receipt'] and worker['UI_proof_sha256']==trials['xray']['sha256']
 assert worker['GPU_input_PL_faster_strongest_PS'] and worker['benchmark']['GPU_input_PS_over_PL']>1
 assert worker['benchmark']['frames']==60 and all(t['all_pixels_exact'] for t in worker['benchmark']['trials'])
 assert worker['complete_original_meshes_and_layers'] and not worker['new_bitstream']
 cases=worker['cases'];assert len(cases)==2 and cases[0]['capture_sha256']==cases[1]['capture_sha256']
 assert cases[0]['final_sha256']==cases[1]['final_sha256']
 previous=json.loads(checked(r['xray_parent_UI_build_file']).read_text());assert previous['binary_sha256']==r['xray_parent_UI_binary_sha256']
 derivation=json.loads(checked(r['xray_UI_derivation']).read_text());before=checked(derivation['baseline']);after=checked(derivation['candidate'])
 assert sha(before)==derivation['baseline_sha256'] and sha(after)==derivation['candidate_sha256']
 assert previous['source_sha256'][derivation['baseline']]==sha(before) and r['UI_build']['source_sha256'][derivation['candidate']]==sha(after)
 text=after.read_bytes().decode();assert len(derivation['replacements'])==5
 for change in reversed(derivation['replacements']):
  assert text.count(change['after'])==1;text=text.replace(change['after'],change['before'])
 assert text.encode()==before.read_bytes()
 return r
def main():
 p=argparse.ArgumentParser();p.add_argument('--descriptor',required=True);a=p.parse_args()
 r=verify(a.descriptor);print(r['binary'])
if __name__=='__main__':main()
