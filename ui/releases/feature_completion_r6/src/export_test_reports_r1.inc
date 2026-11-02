 void exportFinish(bool passed,const QJsonObject&result,QString detail){
  if(!exportTesting)return;
  QDir().mkpath(evidence);
  writeJson(evidence+"/export_UI.json",QJsonObject{
    {"status",passed?"passed_actual_Qt_export_control_and_async_colored_bundle":"failed"},
    {"detail",detail},{"event",result},{"source",source},{"input",input},
    {"heartbeat_ticks_during_export",ticks-exportStartTick},{"UI_peak_RSS_MiB",peakRSS()},
    {"physical_mouse_verified",false},{"production_UI_replaced",false},
    {"new_medical_PL_core_loaded",false}});
  grab().save(evidence+"/export_complete.png");
  this->close();if(!passed)QTimer::singleShot(100,[]{QApplication::exit(1);});
 }
 void exportAdvance(){
  if(!exportTesting||exportStarted)return;
  QString requested=qEnvironmentVariable("KV260_COMPLETE_REPORTS_SOURCE");
  if(!requested.isEmpty()&&source!=requested){prepare(requested);return;}
  if(failed||source.isEmpty()||!exportButton->isEnabled()){
    exportFinish(false,{},u("完成结果未正常载入"));return;
  }
  exportStarted=true;exportStartTick=ticks;
  QTest::mouseClick(exportButton,Qt::LeftButton);
 }
