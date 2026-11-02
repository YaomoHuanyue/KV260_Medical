"""Wait for the actual CT-page button after the supported PL display drain."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    edits=[]
    def change(parent,child,changes):
        source=(ROOT/parent).read_text(encoding='utf-8')
        for before,after,count in changes:
            assert source.count(before)==count,(parent,before,source.count(before));source=source.replace(before,after)
        with (ROOT/child).open('x',encoding='utf-8',newline='\n') as f:f.write(source)
        if child.endswith('.py'):compile(source,child,'exec')
        edits.append(dict(parent=parent,parent_sha256=sha(ROOT/parent),child=child,child_sha256=sha(ROOT/child),changes=changes))
    change('ui/releases/feature_completion_r6/src/active_recovery_UI_r21.inc','ui/releases/feature_completion_r6/src/active_recovery_UI_r21a.inc',[
        (' void recoveryAdvance(){',''' void recoveryClickVisibleButton(int attempts=0){
  if(processing()||!recoveryButton->isEnabled()){
   if(attempts>=480){recoveryCheck("CT_page_recovery_button_ready_after_supported_drain",false);finishActiveRecovery();return;}
   QTimer::singleShot(100,this,[this,attempts]{recoveryClickVisibleButton(attempts+1);});return;
  }
  recoveryCheck("actual_visible_CT_page_recovery_button",tabs->currentIndex()==0&&recoveryButton->isVisible());
  if(failed){finishActiveRecovery();return;}QTest::mouseClick(recoveryButton,Qt::LeftButton);
 }
 void recoveryAdvance(){''',1),
        ('     activeRecoveryStage=2;QTest::mouseClick(recoveryButton,Qt::LeftButton);return;}',
         '     activeRecoveryStage=2;QTimer::singleShot(100,this,[this]{recoveryClickVisibleButton();});return;}',1)])
    change('ui/releases/feature_completion_r6/src/main_complete_scene_r21.cpp','ui/releases/feature_completion_r6/src/main_complete_scene_r21a.cpp',[
        ('active_recovery_UI_r21.inc','active_recovery_UI_r21a.inc',1)])
    change('modules/surface_route/board_native_build_r21.py','modules/surface_route/board_native_build_r21a.py',[
        ("out=folder/'build_complete_scene_r21'","out=folder/'build_complete_scene_r21a'",1),
        ('native_UI_source_closure_r21','native_UI_source_closure_r21a',1),
        ('main_complete_scene_r21','main_complete_scene_r21a',3),('R21 native adapter','R21a native adapter',1)])
    parent=ROOT/'modules/surface_route/native_UI_source_closure_r21.json';files=json.loads(parent.read_text())['files_sha256']
    for n,h in files.items():assert sha(ROOT/n)==h,n
    names=[e['child'] for e in edits]+['tools/derive_navigation_trial_wait_r21a.py'];files.update({n:sha(ROOT/n) for n in names})
    with (ROOT/'modules/surface_route/native_UI_source_closure_r21a.json').open('x',encoding='utf-8') as f:
        json.dump(dict(files_sha256=files,parent_sha256=sha(parent),change='actual visible CT button regression waits for normal PL graphics drain; synchronization code unchanged',production_promoted=False),f,indent=2);f.write('\n')
    with (ROOT/'modules/navigation_controls/active_derivation_r21a.json').open('x',encoding='utf-8') as f:json.dump(dict(edits=edits,new_bitstream=False),f,indent=2);f.write('\n')
    print('R21a visible-button trial wait derived')
if __name__=='__main__':main()
