"""Bind the complete accepted UI to tested single-buffer asynchronous paired ID/color draws."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,s):
    p=HERE/n;assert not p.exists();p.write_text(s,encoding='utf-8',newline='\n')
def main():
    candidate=ROOT/'dfx/composite/medical/exact_speed_r22'
    accepted=json.loads((candidate/'acceptance.json').read_text(encoding='utf-8'))
    ram=json.loads((candidate/'RAM_transport.json').read_text(encoding='utf-8'))
    assert accepted['status']=='passed_exact_layers_opacity_recomposition_speedup'
    assert accepted['chosen']['mode']=='single_VBO_paired_ID_color_async'
    assert accepted['build']['extra_geometry_VBO_storage_bytes']==0
    assert accepted['warm_transport']=='actual_UI_tmpfs_after_capture_sync'
    assert sha(candidate/'accept.py')==accepted['source_sha256']
    assert sha(candidate/'test_RAM_transport.py')==ram['source_sha256']
    assert accepted['controls_compared']==17 and accepted['opacity_boundary_cases']==7
    assert accepted['additional_transparent_geometry_cases']==6
    assert accepted['all_complete_layers_and_final_pixels_bit_exact'] and accepted['no_mesh_layer_or_resolution_reduction']
    assert accepted['speedup']['opacity_warm']>.9 and accepted['speedup']['rotate']>1.02
    assert ram['speedup']['opacity']>.9 and ram['speedup']['rotate']>1.02
    for group in ('source_sha256','shared_source_sha256','library_sha256'):
        for n,d in accepted['build'][group].items():assert sha(ROOT/n)==d,n
    for t in accepted['trials']:assert sha(ROOT/t['path'])==t['sha256']
    assert sha(candidate/'worker')==accepted['build']['binary_sha256']
    old=HERE/'src/pl_composite_exact_speed_r5.cpp'
    s=old.read_text(encoding='utf-8');old_receipt=ROOT/'dfx/composite/medical/exact_speed_r14/acceptance.json'
    assert s.count(sha(old_receipt))==1
    s=s.replace('dfx/composite/medical/exact_speed_r14','dfx/composite/medical/exact_speed_r22')
    s=s.replace(sha(old_receipt),sha(candidate/'acceptance.json'))
    a='bool valid=r["projection_threads"].toInt()==4&&'
    assert s.count(a)==1;s=s.replace(a,'bool valid=r["paired_ID_color_without_intermediate_CPU_wait"].toBool()&&r["single_VBO_interleaved_ID_color"].toBool()&&r["projection_threads"].toInt()==4&&')
    save('src/pl_composite_exact_speed_r7.cpp',s)
    s=(HERE/'build_exact_speed_r5.sh').read_text(encoding='utf-8')
    s=s.replace('build_exact_speed_r5','build_exact_speed_r7').replace('source_closure_exact_speed_r5','source_closure_exact_speed_r7').replace('src/pl_composite_exact_speed_r5.cpp','src/pl_composite_exact_speed_r7.cpp')
    save('build_exact_speed_r7.sh',s)
    save('run_exact_speed_r7.sh',(HERE/'run_exact_speed_r5.sh').read_text(encoding='utf-8').replace('build_exact_speed_r5','build_exact_speed_r7'))
    closure=json.loads((HERE/'source_closure_exact_speed_r5.json').read_text(encoding='utf-8'))
    for key in ('source_sha256','shared_source_sha256','old_source_sha256'):
        for n,d in closure[key].items():assert sha(ROOT/n)==d,n
    for n in ['src/pl_composite_exact_speed_r7.cpp','build_exact_speed_r7.sh','run_exact_speed_r7.sh','prepare_exact_speed_UI_r7.py']:
        closure['source_sha256'][(HERE/n).relative_to(ROOT).as_posix()]=sha(HERE/n)
    for n in ('accept.py','test_RAM_transport.py','test_scene_change.py','screen.py','test_with_UI_restore.py'):
        closure['shared_source_sha256'][(candidate/n).relative_to(ROOT).as_posix()]=sha(candidate/n)
    closure.update(status='same_complete_UI_with_interleaved_single_buffer_exact_ID_color_R22',candidate='dfx/composite/medical/exact_speed_r22',
        candidate_acceptance_sha256=sha(candidate/'acceptance.json'),previous_transport_sha256=sha(old),only_worker_binding_changed=True)
    save('source_closure_exact_speed_r7.json',json.dumps(closure,indent=2)+'\n')
if __name__=='__main__':main()
