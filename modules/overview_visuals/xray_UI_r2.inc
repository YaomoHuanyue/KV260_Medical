 QCheckBox*xrayPreset=nullptr;
 bool xrayTesting=qEnvironmentVariableIntValue("KV260_XRAY_UI_TEST")==1;
 QJsonArray xrayCases;QJsonObject xrayBaseRequest;
 void applyOverviewOpacity(){
  if(xrayPreset)opacity->setEnabled(!xrayPreset->isChecked());
  overview->setLungOpacity(xrayPreset&&xrayPreset->isChecked()?.10f:opacity->value()/100.f);
 }
 void addXrayPreset(QVBoxLayout*layout){
  xrayPreset=new QCheckBox(u("X-Ray 表面预设"));
  xrayPreset->setToolTip(u("肺表面使用 10% 不透明度；关闭后恢复肺不透明度滑条的设置。结构显隐与镜头保持当前设置。"));
  layout->addWidget(xrayPreset);
  connect(xrayPreset,&QCheckBox::toggled,this,[this]{applyOverviewOpacity();});
 }
 void xrayRecord(QString name,bool good){
  auto request=overview->overviewRequest();
  xrayCases.append(QJsonObject{{"case",name},{"passed",good},{"request",request},
    {"preset_checked",xrayPreset->isChecked()},{"slider_value",opacity->value()},
    {"slider_enabled",opacity->isEnabled()}});
  if(!good)throw std::runtime_error(("Xray state failed: "+name).toStdString());
 }
 void xrayTest(){
  if(!xrayTesting)return;
  try{
   if(failed)throw std::runtime_error("Case load failed");
   tabs->setCurrentIndex(1);preciseBlend->setChecked(false);clipCheck->setChecked(false);
   lungQuality->setCurrentIndex(1);
   for(auto*c:meshLayers)c->setChecked(true);
   opacity->setValue(36);overview->resetView();
   auto camera=overview->overviewCamera();auto before=overview->overviewRequest();
   QTest::mouseClick(xrayPreset,Qt::LeftButton,Qt::NoModifier,QPoint(10,xrayPreset->height()/2));
   auto xray=overview->overviewRequest();xrayBaseRequest=xray;
   auto comparable=xray;comparable["lung_opacity"]=before["lung_opacity"];
   xrayRecord("enable_keeps_camera_layers_and_all_other_controls",xrayPreset->isChecked()&&!opacity->isEnabled()&&opacity->value()==36&&std::abs(xray["lung_opacity"].toDouble()-.10)<1e-6&&comparable==before&&overview->overviewCamera()==camera);
   auto presetPixels=overview->grabFramebuffer();
   QTest::mouseClick(xrayPreset,Qt::LeftButton,Qt::NoModifier,QPoint(10,xrayPreset->height()/2));
   xrayRecord("disable_restores_user_opacity",opacity->isEnabled()&&opacity->value()==36&&std::abs(overview->featureMetrics()["lung_opacity"].toDouble()-.36)<1e-6&&overview->overviewCamera()==camera);
   opacity->setValue(10);auto manualPixels=overview->grabFramebuffer();
   xrayRecord("ordinary_pixels_match_manual_ten_percent",presetPixels==manualPixels);
   for(int value:{0,1,20,51,100}){
    opacity->setValue(value);QTest::mouseClick(xrayPreset,Qt::LeftButton,Qt::NoModifier,QPoint(10,xrayPreset->height()/2));
    bool enabled=opacity->value()==value&&std::abs(overview->featureMetrics()["lung_opacity"].toDouble()-.1)<1e-6;
    QTest::mouseClick(xrayPreset,Qt::LeftButton,Qt::NoModifier,QPoint(10,xrayPreset->height()/2));
    xrayRecord(QString("restore_slider_%1").arg(value),enabled&&opacity->value()==value&&std::abs(overview->featureMetrics()["lung_opacity"].toDouble()-value/100.)<1e-6);
   }
   meshLayers[0]->setChecked(false);auto invisible=overview->overviewRequest();QTest::mouseClick(xrayPreset,Qt::LeftButton,Qt::NoModifier,QPoint(10,xrayPreset->height()/2));
   xrayRecord("hidden_lung_stays_hidden",!overview->overviewRequest()["layers"].toObject()["lung"].toBool()&&overview->overviewRequest()["layers"]==invisible["layers"]);
   QTest::mouseClick(xrayPreset,Qt::LeftButton,Qt::NoModifier,QPoint(10,xrayPreset->height()/2));meshLayers[0]->setChecked(true);
   clipCheck->setChecked(true);colorMode->setCurrentIndex(1);auto clipped=overview->overviewRequest();QTest::mouseClick(xrayPreset,Qt::LeftButton,Qt::NoModifier,QPoint(10,xrayPreset->height()/2));
   xrayRecord("clipping_generation_and_camera_preserved",overview->overviewRequest()["clipping"]==clipped["clipping"]&&overview->overviewRequest()["color_mode"]==clipped["color_mode"]&&overview->overviewCamera()==camera);
   QTest::mouseClick(xrayPreset,Qt::LeftButton,Qt::NoModifier,QPoint(10,xrayPreset->height()/2));clipCheck->setChecked(false);colorMode->setCurrentIndex(0);opacity->setValue(36);QTest::mouseClick(xrayPreset,Qt::LeftButton,Qt::NoModifier,QPoint(10,xrayPreset->height()/2));
   QDir().mkpath(evidence);overview->grabFramebuffer().save(evidence+"/xray.png");
   grab().save(evidence+"/xray_UI.png");
   writeJson(evidence+"/xray_UI.json",QJsonObject{{"status","passed_actual_Qt_xray_preset_state_and_manual_pixel_equivalence"},
    {"cases",xrayCases},{"baseline_request",xrayBaseRequest},{"scene",scenePath},{"source",source},
    {"input_sha256",scene["input_sha256"]},{"preview_only",true},{"precise_PL_same_input_test_pending",true},
    {"physical_mouse_verified",false},{"new_bitstream",false}});
   close();
  }catch(const std::exception&e){
   QDir().mkpath(evidence);writeJson(evidence+"/xray_UI.json",QJsonObject{{"status","failed"},{"error",QString::fromUtf8(e.what())},{"cases",xrayCases}});
   close();QTimer::singleShot(100,[]{QApplication::exit(1);});
  }
 }
