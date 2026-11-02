"""Bind the accepted native UI to the exact two-slot geometry submission worker."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,s):
 p=HERE/n;assert not p.exists();p.write_text(s,encoding='utf-8',newline='\n')
def main():
 candidate=ROOT/'dfx/composite/medical/exact_speed_r26'
 accepted=json.loads((candidate/'acceptance.json').read_text(encoding='utf-8'))
 ram=json.loads((candidate/'RAM_transport.json').read_text(encoding='utf-8'))
 assert accepted['status']=='passed_exact_layers_opacity_recomposition_speedup'
 assert accepted['chosen']['mode']=='two_slot_ID_color_GPU_opacity_cache'
 assert accepted['build']['normal_UI_color_layers_remain_on_GPU'] and accepted['build']['GPU_cached_opacity_updates']
 assert accepted['build']['two_slot_grouped_ID_color'] and accepted['build']['draws_between_CPU_completion_waits']==4
 assert accepted['warm_transport']=='actual_UI_tmpfs_after_capture_sync'
 assert sha(candidate/'accept.py')==accepted['source_sha256']
 assert sha(candidate/'test_RAM_transport.py')==ram['source_sha256']
 assert accepted['controls_compared']==17 and accepted['opacity_boundary_cases']==7 and accepted['additional_transparent_geometry_cases']==6
 assert accepted['all_complete_layers_and_final_pixels_bit_exact'] and accepted['no_mesh_layer_or_resolution_reduction']
 assert accepted['speedup']['opacity_warm']>.9 and accepted['speedup']['rotate']>1.05
 assert ram['speedup']['opacity']>.9 and ram['speedup']['rotate']>1.02
 for group in ('source_sha256','shared_source_sha256','library_sha256'):
  for n,d in accepted['build'][group].items():assert sha(ROOT/n)==d,n
 for t in accepted['trials']:assert sha(ROOT/t['path'])==t['sha256']
 assert sha(candidate/'worker')==accepted['build']['binary_sha256']
 old=HERE/'src/pl_composite_exact_speed_r7.cpp';s=old.read_text(encoding='utf-8')
 old_receipt=ROOT/'dfx/composite/medical/exact_speed_r22/acceptance.json';assert s.count(sha(old_receipt))==1
 s=s.replace('dfx/composite/medical/exact_speed_r22','dfx/composite/medical/exact_speed_r26').replace(sha(old_receipt),sha(candidate/'acceptance.json'))
 a='r["paired_ID_color_without_intermediate_CPU_wait"].toBool()&&r["single_VBO_interleaved_ID_color"].toBool()&&'
 assert s.count(a)==1;s=s.replace(a,'r["two_slot_grouped_ID_color"].toBool()&&r["paired_ID_color_without_intermediate_CPU_wait"].toBool()&&')
 save('src/pl_composite_exact_speed_r8.cpp',s)
 s=(HERE/'build_exact_speed_r7.sh').read_text(encoding='utf-8').replace('exact_speed_r7','exact_speed_r8')
 save('build_exact_speed_r8.sh',s)
 save('run_exact_speed_r8.sh',(HERE/'run_exact_speed_r7.sh').read_text(encoding='utf-8').replace('build_exact_speed_r7','build_exact_speed_r8'))
 closure=json.loads((HERE/'source_closure_exact_speed_r7.json').read_text(encoding='utf-8'))
 for key in ('source_sha256','shared_source_sha256','old_source_sha256'):
  for n,d in closure[key].items():assert sha(ROOT/n)==d,n
 for n in ('src/pl_composite_exact_speed_r8.cpp','build_exact_speed_r8.sh','run_exact_speed_r8.sh','prepare_exact_speed_UI_r8.py'):
  closure['source_sha256'][(HERE/n).relative_to(ROOT).as_posix()]=sha(HERE/n)
 for n in ('accept.py','test_RAM_transport.py','test_scene_change.py','screen.py','test_with_UI_restore.py'):
  closure['shared_source_sha256'][(candidate/n).relative_to(ROOT).as_posix()]=sha(candidate/n)
 closure.update(status='same_complete_UI_with_two_slot_exact_ID_color_R26',candidate='dfx/composite/medical/exact_speed_r26',candidate_acceptance_sha256=sha(candidate/'acceptance.json'),previous_transport_sha256=sha(old),only_worker_binding_changed=True)
 save('source_closure_exact_speed_r8.json',json.dumps(closure,indent=2)+'\n')
if __name__=='__main__':main()
