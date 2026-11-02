"""Derive an isolated tested-R6 extension without editing accepted sources."""
from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,text):
    p=HERE/name
    if p.exists():raise FileExistsError(name)
    p.write_text(text,encoding='utf-8',newline='\n')
def main():
    proof=json.loads((HERE/'build_r6_3/build.json').read_text())
    for group in ('source_sha256','shared_source_sha256'):
        for n,d in proof[group].items():assert sha(ROOT/n)==d,n
    main=(HERE/'src/main_r6_3.cpp').read_text(encoding='utf-8')
    main=main.replace('backend_r6.py','backend_selected_r1.py')
    key='#include "../comparison_dialog_r6.inc"'
    assert main.count(key)==1
    main=main.replace(key,'#include "selected_application_r1.inc"\n#include "../comparison_dialog_selected_r1.inc"')
    key='  QStringList args={root+"/ui/releases/feature_completion_r6/backend_selected_r1.py","prepare","--input",input};'
    assert main.count(key)==1
    main=main.replace(key,'  if(selectedTestStage==0&&qEnvironmentVariableIntValue("KV260_SELECTED_PATH_UI_TEST")==1&&selected.isEmpty())selected=qEnvironmentVariable("KV260_SELECTED_SOURCE_RESULT");\n'+key)
    key='record("scene_loaded");'
    assert main.count(key)==1;main=main.replace(key,key+'selectedPathPrepared();')
    key='if(qEnvironmentVariableIntValue("KV260_WHOLE_COMPARISON_UI_TEST")==1){QTimer::singleShot(400,this,'
    assert main.count(key)==1
    main=main.replace(key,'if(qEnvironmentVariableIntValue("KV260_SELECTED_PATH_UI_TEST")==1){QTimer::singleShot(400,this,[this]{selectedTestAdvance();});}else '+key)
    key='if(rc){failed=true;progress->setRange(0,100);'
    assert main.count(key)==1;main=main.replace(key,'if(rc){selectedTaskPending=false;failed=true;progress->setRange(0,100);')
    # Avoid an unbounded automated wait after a backend failure.
    key='if(qEnvironmentVariableIntValue("KV260_WHOLE_COMPARISON_UI_TEST")==1){QDir().mkpath(evidence);'
    assert main.count(key)==1
    main=main.replace(key,'if(qEnvironmentVariableIntValue("KV260_SELECTED_PATH_UI_TEST")==1){finishTest();}else '+key)
    key='jobProcess.state()!=QProcess::NotRunning);}'
    assert main.count(key)==1
    main=main.replace(key,'jobProcess.state()!=QProcess::NotRunning&&!selectedTaskPending);}')
    save('src/main_selected_r1.cpp',main)
    dialog=(HERE/'comparison_dialog_r6.inc').read_text(encoding='utf-8')
    old='auto*pathNotice=new QLabel(u("备选路径可旋转、缩放和右拖平移；这里只预览，不替换实际导航路径。"));'
    assert dialog.count(old)==1
    dialog=dialog.replace(old,'auto*pathNotice=new QLabel(u("黄色线是原规则的备选路径。点击审核后，实际导航仅使用满足图像净空与弯曲约束的前缀；结果另存，不修改原病例。"));')
    key='  QJsonArray activeCandidates,activeFront;'
    assert dialog.count(key)==1
    dialog=dialog.replace(key,'  auto*apply=new QPushButton(u("审核并用于导航"));apply->setObjectName("applySelectedPath");apply->setEnabled(!groups.isEmpty()&&!processing());pathLayout->addWidget(apply);\n'+key)
    key='  auto*close=new QPushButton(u("关闭"));'
    assert dialog.count(key)==1
    dialog=dialog.replace(key,'  int requestedGroup=-1,requestedCandidate=-1;connect(apply,&QPushButton::clicked,&dialog,[&]{int row=routes->currentRow();if(row<0||row>=activeFront.size())return;requestedGroup=diameters->currentData().toInt();requestedCandidate=activeFront[row].toObject()["candidate_id"].toInt(-1);dialog.accept();});\n'+key)
    key='  dialog.exec();'
    assert dialog.count(key)==1
    dialog=dialog.replace(key,'  if(qEnvironmentVariableIntValue("KV260_SELECTED_PATH_UI_TEST")==1)QTimer::singleShot(500,&dialog,[&]{pages->setCurrentIndex(1);diameters->setCurrentIndex(qEnvironmentVariableIntValue("KV260_SELECTED_TEST_GROUP"));routes->setCurrentCell(0,0);QTest::mouseClick(apply,Qt::LeftButton);});\n'+key+'\n  if(requestedGroup>=0&&requestedCandidate>=0)QTimer::singleShot(0,this,[this,requestedGroup,requestedCandidate]{startSelectedPath(requestedGroup,requestedCandidate);});')
    save('comparison_dialog_selected_r1.inc',dialog)
    build=(HERE/'build_r6_3.sh').read_text(encoding='utf-8')
    build=build.replace('build_r6_3','build_selected_r1').replace('source_closure_r6_3','source_closure_selected_r1').replace('main_r6_3.cpp','main_selected_r1.cpp')
    build=build.replace('whole_profile_comparison_UI_compiled_actual_ARM','selected_path_application_UI_compiled_actual_ARM')
    save('build_selected_r1.sh',build)
    save('run_selected_r1.sh',(HERE/'run_r6_3.sh').read_text(encoding='utf-8').replace('build_r6_3','build_selected_r1'))
    origin=json.loads((HERE/'source_closure_r6_3.json').read_text(encoding='utf-8'))
    new=[p.relative_to(ROOT).as_posix() for p in [HERE/n for n in ('src/main_selected_r1.cpp',
        'src/selected_application_r1.inc','comparison_dialog_selected_r1.inc','backend_selected_r1.py',
        'derive_selected_UI_r1.py','build_selected_r1.sh','run_selected_r1.sh')]]
    new += ['modules/navigation_comparison/'+n for n in ('selected_output_r1.py','selected_pipeline_r1.py','selected_cpu_r1.py')]
    origin['source_sha256'].update({n:sha(ROOT/n) for n in new})
    origin.update(previous_R6_binary_sha256=proof['binary_sha256'],
        selected_path_geometry='complete original path; audited prefix only',new_medical_bitstream=False,
        current_human_accepted_UI_changed=False)
    save('source_closure_selected_r1.json',json.dumps(origin,indent=2)+'\n')
    print('Isolated selected-path UI sources derived:',len(new))
if __name__=='__main__':main()
