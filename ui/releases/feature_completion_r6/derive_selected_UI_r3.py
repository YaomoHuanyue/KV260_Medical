"""Initialize the position label even when a newly loaded camera stays at zero."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,text):
    p=HERE/name;assert not p.exists();p.write_text(text,encoding='utf-8',newline='\n')
def main():
    proof=json.loads((HERE/'build_selected_r2/build.json').read_text(encoding='utf-8'))
    for group in ('source_sha256','shared_source_sha256'):
        for n,d in proof[group].items():assert sha(ROOT/n)==d,n
    failed=json.loads((HERE/'evidence_selected_r3/group_4/selected_application_UI.json').read_text(encoding='utf-8'))
    assert failed['status']=='failed'
    bad=[v['name'] for v in failed['checks'] if not v['passed']]
    assert bad==['position_readout_matches_camera']
    s=(HERE/'src/main_selected_r2.cpp').read_text(encoding='utf-8')
    key='cameraSlider->setRange(0,qMax(0,scope->cameraCount()-1));cameraSlider->setValue(0);'
    assert s.count(key)==1
    s=s.replace(key,key+'navigationPosition->setText(QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,\'f\',1).arg(scope->totalDistance(),0,\'f\',1));')
    save('src/main_selected_r3.cpp',s)
    s=(HERE/'build_selected_r2.sh').read_text(encoding='utf-8')
    s=s.replace('build_selected_r2','build_selected_r3').replace('source_closure_selected_r2','source_closure_selected_r3').replace('main_selected_r2.cpp','main_selected_r3.cpp')
    save('build_selected_r3.sh',s)
    save('run_selected_r3.sh',(HERE/'run_selected_r2.sh').read_text(encoding='utf-8').replace('build_selected_r2','build_selected_r3'))
    r=json.loads((HERE/'source_closure_selected_r2.json').read_text(encoding='utf-8'))
    names=['src/main_selected_r3.cpp','derive_selected_UI_r3.py','build_selected_r3.sh','run_selected_r3.sh']
    r['source_sha256'].update({(HERE/n).relative_to(ROOT).as_posix():sha(HERE/n) for n in names})
    r.update(previous_selected_R2_binary_sha256=proof['binary_sha256'],
        previous_start_position_failure_sha256=sha(HERE/'evidence_selected_r3/group_4/selected_application_UI.json'),
        original_all_selected_UI_checks_unchanged=True,medical_data_producer_changed=False)
    save('source_closure_selected_r3.json',json.dumps(r,indent=2)+'\n')
    print('Start-position initialization fixed; original Qt validation retained')
if __name__=='__main__':main()
