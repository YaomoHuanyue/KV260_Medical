"""Preserve R1 evidence; synchronize linked target and position readout in R2."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,text):
    p=HERE/name;assert not p.exists();p.write_text(text,encoding='utf-8',newline='\n')
def main():
    proof=json.loads((HERE/'build_selected_r1/build.json').read_text())
    for group in ('source_sha256','shared_source_sha256'):
        for n,d in proof[group].items():assert sha(ROOT/n)==d,n
    s=(HERE/'src/main_selected_r1.cpp').read_text(encoding='utf-8')
    old='if(enabled&&!scenePath.isEmpty())miniOverview->loadScene(scenePath,scene);'
    assert s.count(old)==1
    s=s.replace(old,'if(enabled&&!scenePath.isEmpty()){miniOverview->loadScene(scenePath,scene);miniOverview->selectCandidate(lesion->value());miniOverview->setColorMode(colorMode->currentIndex());miniOverview->setAnalysisParameters(diameter->value(),margin->value());}')
    old='connect(cameraSlider,&QSlider::valueChanged,this,[this]{if(playing){playbackStart=scope->distance();playbackClock.restart();}});'
    assert s.count(old)==1
    new='connect(cameraSlider,&QSlider::valueChanged,this,[this]{navigationPosition->setText(QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,\'f\',1).arg(scope->totalDistance(),0,\'f\',1));if(playing){playbackStart=scope->distance();playbackClock.restart();}});'
    s=s.replace(old,new).replace('"selected_application_r1.inc"','"selected_application_r2.inc"')
    s=s.replace('QFile::remove(stopFile);});','if(!stopFile.isEmpty())QFile::remove(stopFile);});')
    save('src/main_selected_r2.cpp',s)
    s=(HERE/'src/selected_application_r1.inc').read_text(encoding='utf-8')
    old='dualCheck->setChecked(true);QApplication::processEvents();'
    assert s.count(old)==1
    new=old+'''QTest::qWait(150);
   selectedCheck("linked_selected_target_matches_route",miniOverview->featureMetrics()["selected_candidate"].toInt(-1)==scene["navigation"].toObject()["report"].toObject()["target"].toObject()["index"].toInt(-2));
   selectedCheck("position_readout_matches_camera",navigationPosition->text()==QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,'f',1).arg(scope->totalDistance(),0,'f',1));
   auto shown=scope->presentedScopeFrame(),ref=miniOverview->referenceCameraMetrics();
   selectedCheck("linked_reference_tracks_presented_PL_camera",ref["valid"].toBool()&&ref["sequence"]==shown["sequence"]&&std::abs(ref["arc_mm"].toDouble()-shown["arc_mm"].toDouble())<.001);
   selectedCheck("completed_frame_matches_requested_arc",std::abs(plLastFrame["arc_mm"].toDouble()-scope->distance())<.001);
'''
    s=s.replace(old,new)
    save('src/selected_application_r2.inc',s)
    s=(HERE/'build_selected_r1.sh').read_text(encoding='utf-8')
    s=s.replace('build_selected_r1','build_selected_r2').replace('source_closure_selected_r1','source_closure_selected_r2').replace('main_selected_r1.cpp','main_selected_r2.cpp')
    save('build_selected_r2.sh',s)
    save('run_selected_r2.sh',(HERE/'run_selected_r1.sh').read_text(encoding='utf-8').replace('build_selected_r1','build_selected_r2'))
    r=json.loads((HERE/'source_closure_selected_r1.json').read_text())
    names=['src/main_selected_r2.cpp','src/selected_application_r2.inc','derive_selected_UI_r2.py','build_selected_r2.sh','run_selected_r2.sh']
    r['source_sha256'].update({(HERE/n).relative_to(ROOT).as_posix():sha(HERE/n) for n in names})
    r['previous_selected_R1_binary_sha256']=proof['binary_sha256'];r['medical_data_producer_changed']=False
    save('source_closure_selected_r2.json',json.dumps(r,indent=2)+'\n')
    print('New linked target/position UI sources; original tested producer unchanged')
if __name__=='__main__':main()
