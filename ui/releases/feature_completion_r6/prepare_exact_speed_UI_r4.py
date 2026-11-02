"""Bind the unchanged complete UI to the independently accepted R8 worker."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,s):
    p=HERE/n;assert not p.exists();p.write_text(s,encoding='utf-8',newline='\n')
def main():
    candidate=ROOT/'dfx/composite/medical/exact_speed_r10'
    accepted=json.loads((candidate/'acceptance.json').read_text(encoding='utf-8'))
    assert accepted['status']=='passed_exact_layers_opacity_recomposition_speedup'
    assert accepted['controls_compared']==17 and accepted['all_complete_layers_and_final_pixels_bit_exact']
    assert accepted['no_mesh_layer_or_resolution_reduction']
    assert accepted['speedup']['opacity_warm']>1 and accepted['speedup']['rotate']>1
    for group in ('source_sha256','shared_source_sha256','library_sha256'):
        for n,d in accepted['build'][group].items():assert sha(ROOT/n)==d,n
    for t in accepted['trials']:assert sha(ROOT/t['path'])==t['sha256']
    assert sha(candidate/'worker')==accepted['build']['binary_sha256']
    old=HERE/'src/pl_composite_exact_speed_r1.cpp'
    s=old.read_text(encoding='utf-8')
    assert 'dfx/composite/medical/exact_speed_r6' in s
    old_receipt=ROOT/'dfx/composite/medical/exact_speed_r6/acceptance.json'
    assert s.count(sha(old_receipt))==1
    s=s.replace('dfx/composite/medical/exact_speed_r6','dfx/composite/medical/exact_speed_r10')
    s=s.replace(sha(old_receipt),sha(candidate/'acceptance.json'))
    s=s.replace('passed_complete_original_CT_controls_layers_final_RGBA_same_input_PS_PL_and_warm_ABBA_speedup','passed_exact_layers_opacity_recomposition_speedup')
    save('src/pl_composite_exact_speed_r4.cpp',s)
    s=(HERE/'build_exact_speed_r1.sh').read_text(encoding='utf-8')
    s=s.replace('build_exact_speed_r1','build_exact_speed_r4').replace('source_closure_exact_speed_r1','source_closure_exact_speed_r4').replace('src/pl_composite_exact_speed_r1.cpp','src/pl_composite_exact_speed_r4.cpp')
    save('build_exact_speed_r4.sh',s)
    save('run_exact_speed_r4.sh',(HERE/'run_exact_speed_r1.sh').read_text(encoding='utf-8').replace('build_exact_speed_r1','build_exact_speed_r4'))
    closure=json.loads((HERE/'source_closure_exact_speed_r1.json').read_text(encoding='utf-8'))
    for key in ('source_sha256','shared_source_sha256','old_source_sha256'):
        for n,d in closure[key].items():assert sha(ROOT/n)==d,n
    for n in ['src/pl_composite_exact_speed_r4.cpp','build_exact_speed_r4.sh','run_exact_speed_r4.sh','prepare_exact_speed_UI_r4.py']:
        closure['source_sha256'][(HERE/n).relative_to(ROOT).as_posix()]=sha(HERE/n)
    closure.update(status='same_complete_UI_with_exact_count_shader_worker_R10',candidate='dfx/composite/medical/exact_speed_r10',
        candidate_acceptance_sha256=sha(candidate/'acceptance.json'),previous_transport_sha256=sha(old),
        only_worker_binding_changed=True)
    save('source_closure_exact_speed_r4.json',json.dumps(closure,indent=2)+'\n')
    print('Unchanged full GUI bound to accepted R10 worker')
if __name__=='__main__':main()
