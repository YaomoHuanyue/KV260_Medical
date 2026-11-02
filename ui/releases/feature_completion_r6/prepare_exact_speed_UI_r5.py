"""Bind the accepted full UI to exact parallel bounds R14."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,s):
    p=HERE/n;assert not p.exists();p.write_text(s,encoding='utf-8',newline='\n')
def main():
    candidate=ROOT/'dfx/composite/medical/exact_speed_r14'
    accepted=json.loads((candidate/'acceptance.json').read_text(encoding='utf-8'))
    assert accepted['status']=='passed_exact_layers_opacity_recomposition_speedup'
    assert accepted['controls_compared']==17 and accepted['opacity_boundary_cases']==7
    assert accepted['all_complete_layers_and_final_pixels_bit_exact'] and accepted['no_mesh_layer_or_resolution_reduction']
    assert accepted['additional_transparent_geometry_cases']==6
    assert accepted['speedup']['opacity_warm']>.9 and accepted['speedup']['rotate']>1.02
    for group in ('source_sha256','shared_source_sha256','library_sha256'):
        for n,d in accepted['build'][group].items():assert sha(ROOT/n)==d,n
    for t in accepted['trials']:assert sha(ROOT/t['path'])==t['sha256']
    assert sha(candidate/'worker')==accepted['build']['binary_sha256']
    old=HERE/'src/pl_composite_exact_speed_r4.cpp'
    s=old.read_text(encoding='utf-8');old_receipt=ROOT/'dfx/composite/medical/exact_speed_r10/acceptance.json'
    assert s.count(sha(old_receipt))==1
    s=s.replace('dfx/composite/medical/exact_speed_r10','dfx/composite/medical/exact_speed_r14')
    s=s.replace(sha(old_receipt),sha(candidate/'acceptance.json'))
    a='expectedSelection=workerOptions[0]=="baseline"?0:1;'
    assert s.count(a)==1;s=s.replace(a,'expectedSelection=0;')
    a='bool valid=r["exact_selection_mode"].toInt(-1)==expectedSelection&&'
    assert s.count(a)==1;s=s.replace(a,'bool valid=r["projection_threads"].toInt()==4&&r["hidden_mesh_reprojection_skipped"].toBool()&&r["exact_selection_mode"].toInt(-1)==expectedSelection&&')
    save('src/pl_composite_exact_speed_r5.cpp',s)
    s=(HERE/'build_exact_speed_r4.sh').read_text(encoding='utf-8')
    s=s.replace('build_exact_speed_r4','build_exact_speed_r5').replace('source_closure_exact_speed_r4','source_closure_exact_speed_r5').replace('src/pl_composite_exact_speed_r4.cpp','src/pl_composite_exact_speed_r5.cpp')
    save('build_exact_speed_r5.sh',s)
    save('run_exact_speed_r5.sh',(HERE/'run_exact_speed_r4.sh').read_text(encoding='utf-8').replace('build_exact_speed_r4','build_exact_speed_r5'))
    closure=json.loads((HERE/'source_closure_exact_speed_r4.json').read_text(encoding='utf-8'))
    for key in ('source_sha256','shared_source_sha256','old_source_sha256'):
        for n,d in closure[key].items():assert sha(ROOT/n)==d,n
    for n in ['src/pl_composite_exact_speed_r5.cpp','build_exact_speed_r5.sh','run_exact_speed_r5.sh','prepare_exact_speed_UI_r5.py']:
        closure['source_sha256'][(HERE/n).relative_to(ROOT).as_posix()]=sha(HERE/n)
    closure.update(status='same_complete_UI_with_parallel_exact_bounds_R14',candidate='dfx/composite/medical/exact_speed_r14',
        candidate_acceptance_sha256=sha(candidate/'acceptance.json'),previous_transport_sha256=sha(old),only_worker_binding_changed=True)
    save('source_closure_exact_speed_r5.json',json.dumps(closure,indent=2)+'\n')
    print('Unchanged full GUI bound to accepted R14 worker')
if __name__=='__main__':main()
