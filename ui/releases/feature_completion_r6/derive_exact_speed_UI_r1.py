"""Bind the existing accepted interaction UI to an independently accepted worker."""
from pathlib import Path
import argparse,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,s):
 p=HERE/n;assert not p.exists();p.write_text(s,encoding='utf-8',newline='\n')
def replace(s,a,b):assert s.count(a)==1,a[:90];return s.replace(a,b)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('candidate');args=parser.parse_args()
 candidate=ROOT/args.candidate;assert candidate.resolve().is_relative_to(ROOT/'dfx/composite/medical')
 acceptance=json.loads((candidate/'acceptance.json').read_text(encoding='utf-8'))
 assert acceptance['status']=='passed_complete_original_CT_controls_layers_final_RGBA_same_input_PS_PL_and_warm_ABBA_speedup'
 assert acceptance['all_complete_layers_and_final_pixels_bit_exact'] and acceptance['controls_compared']==17
 assert acceptance['no_mesh_layer_or_resolution_reduction']
 for key in ('source_sha256','shared_source_sha256','library_sha256'):
  for n,d in acceptance['build'].get(key,{}).items():assert sha(ROOT/n)==d,n
 for t in acceptance['trials']:assert sha(ROOT/t['path'])==t['sha256']
 assert sha(candidate/'worker')==acceptance['build']['binary_sha256']
 old=HERE/'src/pl_composite.cpp';s=old.read_text(encoding='utf-8')
 s=replace(s,'QProcess process;QString root,source,frameFile;','QProcess process;QStringList workerOptions;int expectedSelection=-1,expectedEdge=0;QString root,source,frameFile;')
 start=s.index(' QString current=root+');end=s.index(' return true;',start)
 s=s[:start]+''' QString current=root+"/CANDIDATE/acceptance.json";
 QFile receipt(current);if(!receipt.open(QIODevice::ReadOnly)){error=QString::fromUtf8("加速透明版本尚未通过板测");return false;}
 auto accepted=QJsonDocument::fromJson(receipt.readAll()).object();
 if(accepted["status"]!="passed_complete_original_CT_controls_layers_final_RGBA_same_input_PS_PL_and_warm_ABBA_speedup"||
  !accepted["all_complete_layers_and_final_pixels_bit_exact"].toBool()||accepted["controls_compared"].toInt()!=17){error=QString::fromUtf8("加速透明验收记录无效");return false;}
 QFile metadata(root+"/CANDIDATE/build.json");if(!metadata.open(QIODevice::ReadOnly)){error=QString::fromUtf8("缺少加速透明构建记录");return false;}
 auto build=QJsonDocument::fromJson(metadata.readAll()).object();
 if(build!=accepted["build"].toObject()||compositeFileSHA(root+"/CANDIDATE/worker")!=build["binary_sha256"].toString().toLatin1()){
  error=QString::fromUtf8("加速透明程序与验收版本不一致");return false;}
 for(const char*group:{"source_sha256","shared_source_sha256","library_sha256"}){
  auto hashes=build[group].toObject();if(hashes.isEmpty()){error=QString::fromUtf8("加速透明构建绑定不完整");return false;}
  for(auto i=hashes.begin();i!=hashes.end();++i)if(compositeFileSHA(root+"/"+i.key())!=i.value().toString().toLatin1()){
   error=QString::fromUtf8("加速透明源或库已改变，请重新验证");return false;}
 }
 for(auto value:accepted["trials"].toArray()){auto t=value.toObject();if(compositeFileSHA(root+"/"+t["path"].toString())!=t["sha256"].toString().toLatin1()){
  error=QString::fromUtf8("加速透明板测记录已改变");return false;}}
 auto options=accepted["chosen"].toObject()["options"].toArray();
 if(options.size()!=2||!(options[0]=="baseline"||options[0]=="color")||!(options[1]=="16"||options[1]=="4"||options[1]=="1")){
  error=QString::fromUtf8("加速透明参数无效");return false;}
 workerOptions=QStringList{options[0].toString(),options[1].toString()};expectedSelection=workerOptions[0]=="baseline"?0:1;expectedEdge=workerOptions[1].toInt();
'''.replace('CANDIDATE',args.candidate)+s[end:]
 s=replace(s,' QFile receipt(current);', ' if(compositeFileSHA(current)!=QByteArray(\"'+sha(candidate/'acceptance.json')+'\")){error=QString::fromUtf8(\"加速透明验收记录已改变\");return false;}\n QFile receipt(current);')
 s=replace(s,'process.start(root+"/dfx/composite/build/medical_composite_worker",{scene,frameFile});',
  'process.start(root+"/'+args.candidate+'/worker",QStringList{scene,frameFile}+workerOptions);')
 s=replace(s,'bool valid=expected&&w==','auto r=info["report"].toObject();bool valid=r["exact_selection_mode"].toInt(-1)==expectedSelection&&r["screen_culling_edge"].toInt(-1)==expectedEdge&&!r["thirty_two_layer_overflow"].toBool(true)&&r["live_shared_composition"].toObject()["guards_unchanged"].toBool()&&expected&&w==')
 save('src/pl_composite_exact_speed_r1.cpp',s)
 s=(HERE/'build_interactive_r1.sh').read_text(encoding='utf-8').replace('build_interactive_r1','build_exact_speed_r1').replace('source_closure_interactive_r1','source_closure_exact_speed_r1').replace('src/pl_composite.cpp','src/pl_composite_exact_speed_r1.cpp').replace('transparent_interaction_UI_compiled_actual_ARM','exact_transparency_speed_UI_compiled_actual_ARM')
 save('build_exact_speed_r1.sh',s)
 save('run_exact_speed_r1.sh',(HERE/'run_interactive_r1.sh').read_text(encoding='utf-8').replace('build_interactive_r1','build_exact_speed_r1'))
 s=(HERE/'test_transparent_interaction_with_restore_r1.sh').read_text(encoding='utf-8')
 s=s.replace('build_interactive_r1','build_exact_speed_r1').replace('run_interactive_r1','run_exact_speed_r1').replace('evidence_transparent_r1','evidence_exact_speed_r1').replace('transparent_interaction_trial_summary_r1','exact_speed_UI_trial_summary_r1').replace('state_after_transparent_interaction_r1','state_after_exact_speed_UI_r1').replace('test_transparent_interaction_with_restore_r1','test_exact_speed_UI_with_restore_r1').replace('restored_UI_transparent_interaction_r1','restored_UI_exact_speed_UI_r1')
 s=s.replace('transparent_exact_controls_r1.log','exact_speed_UI_controls_r1.log').replace('transparent_interaction_r1.log','exact_speed_UI_interaction_r1.log')
 save('test_exact_speed_UI_with_restore_r1.sh',s)
 s=(HERE/'show_tested_transparent_UI_with_restore_r1.sh').read_text(encoding='utf-8')
 s=s.replace('build_interactive_r1','build_exact_speed_r1').replace('run_interactive_r1','run_exact_speed_r1').replace('transparent_interaction_trial_summary_r1','exact_speed_UI_trial_summary_r1').replace('state_after_transparent_manual_r1','state_after_exact_speed_manual_r1').replace('state_during_transparent_manual_r1','state_during_exact_speed_manual_r1').replace('show_tested_transparent_UI_with_restore_r1','show_tested_exact_speed_UI_with_restore_r1').replace('manual_transparent_r1.log','manual_exact_speed_r1.log').replace('restored_UI_transparent_manual_r1','restored_UI_exact_speed_manual_r1')
 save('show_tested_exact_speed_UI_with_restore_r1.sh',s)
 closure=json.loads((HERE/'source_closure_interactive_r1.json').read_text(encoding='utf-8'))
 for key in ('source_sha256','shared_source_sha256','old_source_sha256'):
  for n,d in closure[key].items():assert sha(ROOT/n)==d,n
 files=['src/pl_composite_exact_speed_r1.cpp','build_exact_speed_r1.sh','run_exact_speed_r1.sh','test_exact_speed_UI_with_restore_r1.sh','show_tested_exact_speed_UI_with_restore_r1.sh','derive_exact_speed_UI_r1.py']
 closure['source_sha256'].update({(HERE/n).relative_to(ROOT).as_posix():sha(HERE/n) for n in files})
 closure.update(status='source_bound_exact_transparency_speed_UI_derived',candidate=args.candidate,candidate_acceptance_sha256=sha(candidate/'acceptance.json'),old_transport_sha256=sha(old),full_mesh_layers_and_resolution_unchanged=True)
 save('source_closure_exact_speed_r1.json',json.dumps(closure,indent=2)+'\n')
 print('Exact transparency acceleration UI derived from complete accepted worker')
if __name__=='__main__':main()
