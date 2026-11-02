#include "../../../modules/view_assets_r1/c6_async_HU_spawn_r1/dialog.hpp"
#include "../feature_completion_r6/src/views_breathing_r1.hpp"
#include "../../../modules/mask_evaluation/ui/dialog.hpp"
#include "../feature_completion_r6/reachability_chart.hpp"
#include "../../../modules/user_capture/capture.hpp"
#include "../../../modules/navigation_media/timeline.hpp"
#include "../../../modules/navigation_media/frame_r2.hpp"
#include "../../../modules/navigation_media/encoder_UI_r3.hpp"
#include "../../../modules/navigation_media/active_binding_r20.hpp"
#include "../../../modules/navigation_media/stream_integrity_r2/file_hash.hpp"
#include "../../../modules/navigation_controls/motion.hpp"
#include <functional>
#include "../feature_completion_r6/src/pl_scope_complete_r9.hpp"
#include "../feature_completion_r6/src/pl_composite.hpp"
#include <QTest>
#include <QStandardItemModel>
#include <signal.h>
#include <sys/resource.h>
#include <algorithm>
#include <numeric>
#include <cmath>
#include <atomic>
#include <thread>
#include <fstream>
#include <unistd.h>
#include "../../../modules/image_import/availability_r1/structures.hpp"

static volatile sig_atomic_t exitRequested=0;
static std::atomic<long long> lastTick{0};
static long long monoMs(){return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
static void handleSignal(int){exitRequested=1;}
static QString u(const char*s){return QString::fromUtf8(s);}
static void testDrag(QWidget*view,QPoint from,QPoint to){
 QMouseEvent press(QEvent::MouseButtonPress,from,Qt::LeftButton,Qt::LeftButton,Qt::NoModifier);QApplication::sendEvent(view,&press);
 QMouseEvent move(QEvent::MouseMove,to,Qt::NoButton,Qt::LeftButton,Qt::NoModifier);QApplication::sendEvent(view,&move);
 QMouseEvent release(QEvent::MouseButtonRelease,to,Qt::LeftButton,Qt::NoButton,Qt::NoModifier);QApplication::sendEvent(view,&release);
}
static QJsonObject readJson(QString path){QFile f(path);if(!f.open(QIODevice::ReadOnly))throw std::runtime_error(("Cannot read "+path).toStdString());QJsonParseError e;auto d=QJsonDocument::fromJson(f.readAll(),&e);if(e.error!=QJsonParseError::NoError||!d.isObject())throw std::runtime_error("Invalid JSON");return d.object();}
static void writeJson(QString path,QJsonObject o){QSaveFile f(path);if(!f.open(QIODevice::WriteOnly))throw std::runtime_error("Cannot save report");f.write(QJsonDocument(o).toJson());if(!f.commit())throw std::runtime_error("Cannot commit report");}

static QString routeDescription(const QJsonObject&r){
 QString status=r["status"].toString(),reason=r["reason"].toString();if(status.isEmpty())return u("尚无导航路径");
 QString why=reason=="insufficient_route_clearance"?u("部分管段净空不足"):
  reason=="insufficient_new_surface_route_clearance"?u("新表面部分管段净空不足"):
  reason=="insufficient_root_clearance"?u("起点净空不足"):
  reason=="insufficient_bend_radius"?u("器械最小弯曲半径约束未通过"):
  reason=="continuous_route_clearance_failed"?u("连续路径净空检查未通过"):
  reason=="disconnected_target_component"?u("目标气道与起点不连通"):u("当前模型未提供可达路径");
 QString text=status=="limited_reach"?u("未到目标附近气道：")+why+u("；当前仅显示可达部分"):
  status=="unreachable"?u("路径未建立：")+why:
  status=="airway_approach"?u("路径到达模型内目标附近的气道，未进入病灶组织"):u("路径已建立");
 if(r["final_target_gap_mm"].isDouble())text+=QString(u(" · 末端距%1 %2 mm")).arg(r["target_kind"]=="lesion_candidate"?u("候选区域"):u("目标")).arg(r["final_target_gap_mm"].toDouble(),0,'f',1);
 if(r["scope_diameter_mm"].isDouble())text+=QString(u("\n器械 Ø %1 mm · 每侧余量 %2 mm · 图像保守余量 %3 mm（模型几何估算）")).arg(r["scope_diameter_mm"].toDouble(),0,'f',1).arg(r["safety_margin_mm"].toDouble(),0,'f',1).arg(r["resolution_margin_mm"].toDouble(),0,'f',2);
 return text;
}

class MainWindow:public QWidget{
 QLabel*structureAvailability=nullptr;

 bool sceneLoading=false;std::thread sceneLoader;
 std::shared_ptr<Volume> readyVolume;QJsonObject readyMeta;QString readyPath;
 void preparedSceneFinished(int rc){try{if(rc||pendingResult.isEmpty())throw std::runtime_error((errors.isEmpty()?u("病例载入失败，请查看任务日志"):errors).toStdString());loadScene(pendingResult);}catch(const std::exception&e){failed=true;if(!scene.isEmpty()){input=scene["input"].toString();source=scene["result"].toString();}message(QString::fromUtf8(e.what()));progress->setRange(0,100);progress->setValue(0);}busy(false);if(!failed)configureScope();qInfo()<<"R2277 prepare finished"<<rc<<"failed"<<failed<<"replan flag/environment"<<replanTesting<<qEnvironmentVariableIntValue("KV260_REPLAN_UI_TEST")<<"active/quality/complete flags"<<activeSurfaceTesting<<qualityTesting<<completeSceneGuiTesting;
  if(replanTesting){QTimer::singleShot(400,this,[this]{qInfo()<<"R2277 initial replan advance";replanAdvance();});}
  else if(activeRecoveryTesting){QTimer::singleShot(300,this,[this]{recoveryAdvance();});}else if(qualityTesting){QTimer::singleShot(300,this,[this]{qualityTestAdvance();});}else if(activeSurfaceTesting){QTimer::singleShot(300,this,[this]{surfaceTestAdvance();});}else if(completeSceneGuiTesting){QTimer::singleShot(400,this,[this]{completeSceneGuiTest();});}else if(batchTesting){QTimer::singleShot(400,this,[this]{batchTestAdvance();});}else if(videoTesting){QTimer::singleShot(400,this,[this]{videoTestAdvance();});}else if(breathingTesting||breathingFpsTesting){QTimer::singleShot(400,this,[this]{breathingTest();breathingFpsTest();});}else if(xrayTesting){QTimer::singleShot(400,this,[this]{xrayTest();});}else if(qEnvironmentVariableIntValue("KV260_FAST_OPACITY_TEST")==1){QTimer::singleShot(400,this,[this]{
      if(failed){QApplication::exit(1);return;}
      tabs->setCurrentIndex(1);preciseBlend->setChecked(false);clipCheck->setChecked(false);opacity->setValue(100);
      QApplication::processEvents();QDir().mkpath(evidence);
      auto proof=overview->fastOpacityRegression(evidence);proof["slider_right_endpoint_opacity"]=overview->featureMetrics()["lung_opacity"];
      proof["precise_checkbox_unchecked"]=!preciseBlend->isChecked();proof["scene"]=scenePath;
      writeJson(evidence+"/fast_opacity_UI.json",proof);
      bool good=proof["status"]=="passed"&&proof["slider_right_endpoint_opacity"].toDouble()==1&&proof["precise_checkbox_unchecked"].toBool();
      releaseGraphics([good]{QApplication::exit(good?0:1);});
    });}else if(replanTesting){QTimer::singleShot(400,this,[this]{replanAdvance();});}else if(transparentInteractionTesting){QTimer::singleShot(400,this,[this]{if(failed)transparentTestFinish(false,u("病例准备失败"));else transparentTestCheck.start(100);});}else if(qEnvironmentVariableIntValue("KV260_SELECTED_PATH_UI_TEST")==1){QTimer::singleShot(400,this,[this]{selectedTestAdvance();});}else if(qEnvironmentVariableIntValue("KV260_WHOLE_COMPARISON_UI_TEST")==1){QTimer::singleShot(400,this,[this]{if(failed){this->close();QApplication::exit(1);}else if(!wholeComparisonTestStarted){wholeComparisonTestStarted=true;QTest::mouseClick(compareButton,Qt::LeftButton);}else{showComparisons();this->close();if(failed)QApplication::exit(1);}});}else if(qEnvironmentVariableIntValue("KV260_CATALOGUE_UI_TEST")==1){QTimer::singleShot(400,this,[this]{catalogueTest();});}else if(missingDataTesting){QTimer::singleShot(400,this,[this]{missingDataAdvance();});}else if(controlsTesting){QTimer::singleShot(400,this,[this]{controlsAdvance();});}else if(captureTesting){QTimer::singleShot(400,this,[this]{captureTestAdvance();});}else if(exportTesting){QTimer::singleShot(400,this,[this]{exportAdvance();});}else if(dicomTesting){QTimer::singleShot(400,this,[this]{dicomAdvance();});}else if(externalTesting){QTimer::singleShot(400,this,[this]{externalAdvance();});}else if(recoveryTesting){if(failed)QApplication::exit(1);else QTimer::singleShot(500,this,[this]{recoveryReviewTest();});}else if(airwayTesting){if(failed)QApplication::exit(1);else QTimer::singleShot(500,this,[this]{airwayComparisonTest();});}else if(interactionTesting){if(failed)QApplication::exit(1);else QTimer::singleShot(500,this,[this]{structureInteractionTest();});}else if(compositeTesting){if(failed)finishTest();else compositeCheck.start(150);}else if(smoke){if(failed)finishTest();else QTimer::singleShot(600,this,[this]{smokeAdvance();});}}
 void prepareSceneInBackground(int rc){
  if(rc||pendingResult.isEmpty()){preparedSceneFinished(rc);return;}
  if(sceneLoader.joinable())sceneLoader.join();
  sceneLoading=true;busy(true);QString path=pendingResult;
  sceneLoader=std::thread([this,path,rc]{
   std::shared_ptr<Volume> mapped;QJsonObject meta;QString error;
   try{meta=readJson(path);mapped=std::make_shared<Volume>();mapped->load(path,meta);
    auto*gui=QCoreApplication::instance()->thread();mapped->ctFile.moveToThread(gui);mapped->maskFile.moveToThread(gui);
   }catch(const std::exception&e){error=QString::fromUtf8(e.what());mapped.reset();}
   QMetaObject::invokeMethod(this,[this,path,rc,mapped,meta,error]{
    if(sceneLoader.joinable())sceneLoader.join();
    sceneLoading=false;readyVolume=mapped;readyMeta=meta;readyPath=path;
    if(!error.isEmpty()){errors+=error;preparedSceneFinished(1);}else preparedSceneFinished(rc);
   },Qt::QueuedConnection);
  });
 }

 QPointer<AdaptiveAirwayDialog> huDialog;QPushButton*huButton=nullptr;bool huBusy=false;
 QPointer<MaskEvaluationDialog> maskEvaluation;bool maskEvaluationBusy=false;QPushButton*maskEvaluationButton=nullptr;
 bool wholeComparisonTestStarted=false;
 bool freshRawSeen=false,freshRawInitialVerified=false;
 QString root,input,source,scenePath,runOutput,pendingResult,stopFile;QJsonObject scene;QPushButton*importButton=nullptr;
#include "../feature_completion_r6/src/capture_wait_r86.inc"
#include "../../../modules/navigation_media/stream_integrity_r2/UI_feature.inc"
#include "../../../modules/batch_images/UI_feature_current_r20_presence_r96.inc"
#include "../../../modules/overview_visuals/xray_UI_r2.inc"
#include "../feature_completion_r6/src/controls_sync_r21.inc"
#include "../../../modules/overview_breathing/UI_feature_fps_r327.inc"
#include "../../../modules/overview_breathing/fps_UI_r327.inc"
#include "../feature_completion_r6/src/missing_data_guard_r4.inc"
QLabel*scopeUnavailable=nullptr;
 bool exportTesting=qEnvironmentVariableIntValue("KV260_SURFACE_EXPORT_UI_TEST")==1;bool exportStarted=false;int exportStartTick=0;
 bool dicomTesting=qEnvironmentVariableIntValue("KV260_DICOM_UI_TEST")==1;int dicomStep=0;QJsonArray dicomTrace;QJsonObject dicomImported;QString dicomExpectedInput,dicomExpectedScene;
 bool externalTesting=qEnvironmentVariableIntValue("KV260_EXTERNAL_IMPORT_UI_TEST")==1;int externalStep=0;QString externalImported,externalRebuilt,externalExpectedScene,externalExpectedSource;QJsonArray externalTrace;
 void externalFinish(bool passed,QString detail){
  if(!externalTesting)return;QDir().mkpath(evidence);
  writeJson(evidence+"/import_UI.json",QJsonObject{{"status",passed?"passed_external_import_UI_then_actual_PL_reconstruction_and_wrong_CT_rejection":"failed"},{"detail",detail},{"trace",externalTrace},{"imported_result",externalImported},{"reconstructed_result",externalRebuilt},{"source_after_rejected_import",source},{"scene_after_rejected_import",scenePath},{"input_sha256",scene["input_sha256"]},{"UI_peak_RSS_MiB",peakRSS()},{"accepted_UI_replaced",false},{"physical_mouse_verified",false}});
  this->close();if(!passed)QTimer::singleShot(100,[]{QApplication::exit(1);});
 }
 double peakRSS(){struct rusage usage{};getrusage(RUSAGE_SELF,&usage);return usage.ru_maxrss/1024.;}
 void externalAdvance(){
  if(!externalTesting)return;
  if(failed){externalFinish(false,u("病例准备失败"));return;}
  if(externalStep==0){externalStep=1;externalTrace.append("clicked_import_control");QTest::mouseClick(importButton,Qt::LeftButton);return;}
  if(externalStep==1){
   externalImported=source;auto r=readJson(source+"/segmentation/report.json");
   auto selected=qEnvironmentVariable("KV260_PARTIAL_IMPORT_NAMES").split(",",Qt::SkipEmptyParts);bool partial=!selected.isEmpty();bool good=r["schema"]==(partial?"kv260.external.segmentation.v2":"kv260.external.segmentation.v1")&&r["input_sha256"]==scene["input_sha256"]&&!scene["masks"].toString().isEmpty()&&scene["meshes"].toObject().isEmpty()&&scene["navigation"].isNull()&&rebuildButton->isEnabled();
   if(partial){QJsonArray expected;for(auto n:selected)expected.append(n);good=good&&scene["available_structures"].toArray()==expected&&navButton->isEnabled()==canNavigate();for(auto n:{"lung","airway","nodule"})good=good&&(QFileInfo::exists(source+"/segmentation/"+n+"_mask.nii.gz")==selected.contains(n));externalTrace.append(QJsonObject{{"partial_import",true},{"provided",expected},{"navigation_button_enabled",navButton->isEnabled()}});}if(!good){externalFinish(false,u("导入后状态不完整"));return;}
   externalTrace.append("validated_external_masks_loaded_without_inference_or_mesh");tabs->setCurrentIndex(0);QApplication::processEvents();QDir().mkpath(evidence);grab().save(evidence+"/imported.png");
   externalStep=2;QTimer::singleShot(300,this,[this]{QTest::mouseClick(rebuildButton,Qt::LeftButton);});return;
  }
  if(externalStep==2){
   externalRebuilt=source;auto r=readJson(source+"/reconstruction/report.json");auto meshes=scene["meshes"].toObject();
   auto selected=qEnvironmentVariable("KV260_PARTIAL_IMPORT_NAMES").split(",",Qt::SkipEmptyParts);if(selected.isEmpty())selected=QStringList{"lung","airway","nodule"};bool good=r["status"]=="completed"&&r["mc_backend"]=="pl"&&r["smoothing_backend"]=="pl";for(auto n:{"lung","airway","nodule"})good=good&&(meshes.contains(n)==selected.contains(n));good=good&&navButton->isEnabled()==canNavigate();
   const char* layerNames[]={"lung","airway","nodule"};QJsonArray visible;
   for(int i=0;i<3;++i){good=good&&(meshLayers[i]->isEnabled()==selected.contains(layerNames[i]));if(meshLayers[i]->isChecked())visible.append(layerNames[i]);}
   good=good&&!visible.isEmpty();externalTrace.append(QJsonObject{{"visible_structures",visible}});
   if(!good){externalFinish(false,u("导入掩膜的PL重建未完成"));return;}
   externalTrace.append("clicked_reconstruction_control_actual_PL_MC_and_smoothing_completed");tabs->setCurrentIndex(1);QApplication::processEvents();grab().save(evidence+"/reconstructed.png");
   externalExpectedScene=scenePath;externalExpectedSource=source;externalStep=3;
   startUtility("import-external",{"--input",input,"--manifest",qEnvironmentVariable("KV260_EXTERNAL_BAD_MANIFEST")});return;
  }
 }
 void externalRejected(QString reason){
  if(!externalTesting||externalStep!=3)return;
  bool good=source==externalExpectedSource&&scenePath==externalExpectedScene&&reason.contains("different CT SHA256");
  externalTrace.append("wrong_CT_manifest_rejected_without_replacing_scene");QApplication::processEvents();grab().save(evidence+"/rejected.png");externalFinish(good,reason);
 }

 bool compositeTesting=qEnvironmentVariableIntValue("KV260_COMPOSITE_UI_TEST")==1;int compositeStage=-1,compositeBase=0;QJsonObject compositeExpected;QTimer compositeCheck;QElapsedTimer compositeDeadline;
 PlComposite*plComposite=nullptr;QLabel*compositePerf=nullptr;QCheckBox*fastTransparency=nullptr;QTimer compositeQuiet;int previewQuietRequests=0,previewStaleFrames=0;
 bool transparentInteractionTesting=qEnvironmentVariableIntValue("KV260_TRANSPARENT_INTERACTION_TEST")==1;
 QTimer transparentTestCheck,transparentTestMotion;QElapsedTimer transparentTestDeadline,transparentMotionClock;
 int transparentTestStage=-1,transparentTestBase=0,transparentMoves=0,transparentSwapBase=0,transparentRequestBase=0;
 QJsonObject transparentBaselineRequest,transparentBaselineMeta,transparentTestReport;QByteArray transparentBaselinePixels,transparentLastPixels;
 QVector<double>transparentSwapTimes;bool transparentMoving=false;
 QCheckBox*preciseBlend=nullptr;QCheckBox*meshLayers[3]={};QComboBox*lungQuality=nullptr;int compositeFrames=0;QJsonArray compositeTrace;
 QCheckBox*routeCheck=nullptr;QPushButton*structureButtons[3]={};int structureMode=2;bool settingStructure=false;bool combinedLayers[3]={false,true,true},combinedRoute=true;QJsonObject structureCameras[3];
 bool interactionTesting=qEnvironmentVariableIntValue("KV260_STRUCTURE_UI_TEST")==1;
 bool airwayTesting=qEnvironmentVariableIntValue("KV260_AIRWAY_UI_TEST")==1;
 bool recoveryTesting=qEnvironmentVariableIntValue("KV260_RECOVERY_UI_TEST")==1;QPushButton*recoveryButton=nullptr,*recoveryReviewButton=nullptr;
 PlScope* plScope=nullptr;bool graphicsTransition=false,finishingTest=false,closing=false;int plFrames=0,scopeWait=0,returnFrameBase=-1;bool verifiedScopeReturn=false;QJsonObject plLastFrame;QLabel*scopePerf=nullptr;QJsonArray navigationTrace;
 std::shared_ptr<Volume> volume;
 QProcess prepareProcess,jobProcess,utilityProcess;QByteArray utilityBytes;QString utilityAction,utilityError;QByteArray prepPending,jobPending;QString errors;
 QTabWidget*tabs;QComboBox*results,*windowPreset,*scopeQuality,*airwayOverlay;QLabel*caseLabel,*info,*task,*coordinate,*routeInfo,*clock,*gpuLabel,*elapsed,*airwayAuditInfo;
 QProgressBar*progress;QPushButton*openButton,*refreshButton,*runButton,*rebuildButton,*navButton,*stopButton,*playButton;
 QSpinBox*lesion;QDoubleSpinBox*minimumCandidateVolume=nullptr;QDoubleSpinBox*diameter,*margin,*minimumBend;QComboBox*lesionList,*colorMode,*clipAxis;QLabel*candidateInfo,*legend;QPushButton*focusButton,*compareButton,*comparisonResults,*exportButton,*dicomButton;QCheckBox*clipCheck,*dualCheck;QSlider*clipOffset,*opacity;MeshView*miniOverview;QSlider*cameraSlider,*axialSlider;QPlainTextEdit*log;
 SliceView*slices[3];MeshView*overview,*scope;QTimer heartbeat,play,navigationMotion;QElapsedTimer beatClock,taskClock,playbackClock,navigationMotionClock;float playbackStart=0;QJsonArray playbackTestTrace;
 QVector<double> gaps,jobGaps,swapIntervals,lungIntervals;bool lungBenchmark=false;QTimer rotation;QElapsedTimer swapClock;bool benchmarking=false;int ticks=0;bool playing=false,failed=false;
 QString evidence;bool featureTesting=false;bool smoke=false,acceptance=false,smokeStarted=false,navigationTesting=false,navigationBenchmarking=false,navigationBenchStarted=false;int navigationBase=0;QVector<double> navigationPresented;QJsonObject navigationTestReport;int smokeStep=0;QJsonArray actions;
 QPushButton*button(QString text,QBoxLayout*layout){auto*b=new QPushButton(text);b->setMinimumHeight(35);layout->addWidget(b);return b;}
 bool completeSceneGuiTesting=qEnvironmentVariableIntValue("KV260_COMPLETE_SCENE_GUI_TEST")==1;
 int completeSceneGuiStage=0;QJsonArray completeSceneGuiTrace;
 void completeSceneGuiTest(){
  if(failed||!(!scene.value("complete_surface").toObject().isEmpty())){writeJson(evidence+"/complete_scene_UI.json",{{"status","failed_complete_scene_load"},{"PL_access",false}});QApplication::exit(1);return;}
  if(completeSceneGuiStage==0){tabs->setCurrentIndex(1);preciseBlend->setChecked(false);showStructure(0);}
  else if(completeSceneGuiStage==1){showStructure(1);colorMode->setCurrentIndex(1);testDrag(overview,QPoint(180,160),QPoint(260,200));}
  else if(completeSceneGuiStage==2){showStructure(2);colorMode->setCurrentIndex(0);overview->turn(12);}
  else{
   bool good=plFrames==0&&compositeFrames==0&&scope->cameraCount()==scene["navigation"].toObject()["positions"].toArray().size();
   writeJson(evidence+"/complete_scene_UI.json",{{"status",good?"passed_complete_native_scene_model_interactions_no_PL":"failed"},
    {"scene",scenePath},{"revision",scene["complete_surface"].toObject()["revision"]},{"trace",completeSceneGuiTrace},
    {"scope_features",scope->featureMetrics()},{"camera_count",scope->cameraCount()},{"UI_peak_RSS_MiB",peakRSS()},
    {"PL_access",false},{"new_bitstream",false},{"physical_review",false}});QApplication::exit(good?0:1);return;
  }
  QString file=evidence+QString("/model_%1.png").arg(completeSceneGuiStage);
  QTimer::singleShot(700,this,[this,file]{bool saved=grab().save(file);completeSceneGuiTrace.append(QJsonObject{{"stage",completeSceneGuiStage},{"PNG",file},{"saved",saved},{"features",overview->featureMetrics()},{"camera",overview->overviewCamera()}});if(!saved)failed=true;++completeSceneGuiStage;completeSceneGuiTest();});
 }
 void record(QString action){actions.append(QJsonObject{{"action",action},{"elapsed_ms",double(beatClock.elapsed())}});}
 void showStructure(int mode){
  if(mode<0||mode>2||scenePath.isEmpty())return;
  structureCameras[structureMode]=overview->overviewCamera();
  if(structureMode==2){for(int i=0;i<3;++i)combinedLayers[i]=meshLayers[i]->isChecked();combinedRoute=routeCheck->isChecked();}
  settingStructure=true;structureMode=mode;
  for(int i=0;i<3;++i)meshLayers[i]->setChecked(mode==2?combinedLayers[i]:i==mode);
  routeCheck->setChecked(mode==2&&combinedRoute);settingStructure=false;
  if(!overview->restoreOverviewCamera(structureCameras[mode]))overview->resetView();
  record(QString("structure_preset_%1").arg(mode));
 }
 void syncLinkedOverview(){if(dualCheck->isChecked()){if(!miniOverview->setReferenceCamera(scope->presentedScopeFrame())){qWarning()<<"Invalid completed PL camera for linked overview";if(smoke)failed=true;}}}
 void message(QString text){log->appendPlainText(text);task->setText(text.left(180));}
 bool hasStructure(QString name)const{return scene["available_structures"].toArray().contains(name);}bool canNavigate()const{return hasStructure("airway")&&hasStructure("nodule")&&lesionList&&lesionList->count()>0&&scene["structure_foreground_voxels"].toObject()["airway"].toDouble()>0;}void busy(bool value){value=value||maskEvaluationBusy||huBusy;if(huButton)huButton->setEnabled(!value&&!input.isEmpty());if(maskEvaluationButton)maskEvaluationButton->setEnabled(!value&&!source.isEmpty());value=value||videoPending||videoRunning||batchRunning;qualityBusy(value);if(batchButton)batchButton->setEnabled(!value&&!replanUnavailable&&!source.isEmpty()&&!scene["meshes"].toObject().isEmpty());if(videoButton)videoButton->setEnabled(!value&&!replanUnavailable&&scope->cameraCount()>1&&!source.isEmpty());if(snapshotButton)snapshotButton->setEnabled(!value&&!capturePending&&!captureRunning&&!input.isEmpty());for(auto*b:{dicomButton,exportButton,compareButton,focusButton})if(b)b->setEnabled(!value&&!(replanUnavailable&&b==exportButton)&&(!source.isEmpty()||b==dicomButton));if(recoveryButton)recoveryButton->setEnabled(!value&&!source.isEmpty()&&scene["airway_masks"].toObject().contains("network")&&lesionList->count()>0);if(recoveryReviewButton)recoveryReviewButton->setEnabled(!value&&scene.contains("distal_recovery"));if(lesionList)lesionList->setEnabled(!value&&lesionList->count()>0);if(minimumBend)minimumBend->setEnabled(!value);if(minimumCandidateVolume)minimumCandidateVolume->setEnabled(!value);if(focusButton)focusButton->setEnabled(!value&&!source.isEmpty()&&lesionList->count()>0);if(comparisonResults)comparisonResults->setEnabled(!value&&scene["navigation"].toObject().contains((!scene.value("complete_surface").toObject().isEmpty())?"whole_instrument_profiles":"instrument_profiles"));if(importButton)importButton->setEnabled(!value&&!input.isEmpty());openButton->setEnabled(!value);refreshButton->setEnabled(!value);results->setEnabled(!value);runButton->setEnabled(!value&&!input.isEmpty()&&(!hasStructure("nodule")||lesionList->count()>0));rebuildButton->setEnabled(!value&&!source.isEmpty()&&!scene["available_structures"].toArray().isEmpty());navButton->setEnabled(!value&&!source.isEmpty()&&canNavigate());if(compareButton)compareButton->setEnabled(!value&&!source.isEmpty()&&canNavigate());navButton->setToolTip(canNavigate()?u("按当前目标规划导航"):u("导航需要非空气道和病灶候选掩膜"));stopButton->setEnabled(jobProcess.state()!=QProcess::NotRunning&&!selectedTaskPending);
 }
 bool processing()const{return sceneLoading||huBusy||maskEvaluationBusy||batchRunning||videoPending||videoRunning||capturePending||captureRunning||utilityProcess.state()!=QProcess::NotRunning||graphicsTransition||prepareProcess.state()!=QProcess::NotRunning||jobProcess.state()!=QProcess::NotRunning;}
 void releaseGraphics(std::function<void()> done){
  graphicsTransition=true;busy(true);
  auto finish=[this,done]{graphicsTransition=false;scope->clearPlFrame();miniOverview->setReferenceCamera({});overview->setCompositeStatus(u("上一张完成画面"));busy(false);if(done)done();};
  auto composite=[this,finish]{if(plComposite&&plComposite->active())plComposite->stop(finish);else finish();};
  if(plScope&&plScope->active())plScope->stop(composite);else composite();
 }
 void configureScope(){
  if(!plScope||!plComposite||processing()||finishingTest||closing||source.isEmpty())return;
  int page=tabs->currentIndex();bool needsBlend=page==1&&overview->compositeMode()&&!scene["meshes"].toObject().isEmpty();bool needsScope=page==2&&!replanUnavailable&&scope->cameraCount()>0&&QFileInfo::exists(source+"/navigation/route.json");
  if((!needsScope&&plScope->active())||(!needsBlend&&plComposite->active())){releaseGraphics([this]{configureScope();});return;}
  if(needsScope){auto complete=scene["complete_surface"].toObject();
   if(!complete.isEmpty())plScope->startScene(complete["bundle"].toString(),complete["revision"].toString(),scope->cameraRequest());
   else plScope->start(source,scope->cameraRequest());
  }else if(page==2)scopePerf->setText(u("尚无导航路径，请先重新规划导航。"));
  if(needsBlend)plComposite->start(scenePath,overview->overviewRequest());else if(page==1)compositePerf->setText(u("快速总览 · 拖动旋转 / 滚轮缩放"));
 }
 void firstBranchPose(){auto events=scene["navigation"].toObject()["report"].toObject()["branch_guidance"].toObject()["events"].toArray();auto arcs=scene["navigation"].toObject()["arc"].toArray();int index=qMin(180,cameraSlider->maximum());if(!events.isEmpty()){auto e=events.first().toObject();double at=(e["show_from_mm"].toDouble()+e["hide_after_mm"].toDouble())*.5;for(int i=0;i<arcs.size();++i)if(arcs[i].toDouble()>=at){index=i;break;}}cameraSlider->setValue(index);}
 void processLines(QByteArray&pending,QByteArray bytes){
  pending+=bytes;while(pending.contains('\n')){int end=pending.indexOf('\n');auto line=pending.left(end);pending.remove(0,end+1);auto d=QJsonDocument::fromJson(line);if(!d.isObject()){if(!line.trimmed().isEmpty())log->appendPlainText(QString::fromUtf8(line));continue;}auto o=d.object();QString event=o["event"].toString();
   if(event=="progress")message(o["text"].toString());
   if(event=="navigation_unavailable"){if(activeSurfaceAction!="replan"||o["parent_scene"].toString()!=scenePath){failed=true;message(u("导航结果与当前病例不符"));}else replanBlockedEvent=o;}
   if(event=="prepared")pendingResult=o["scene"].toString();
   if(event=="started"){runOutput=o["output"].toString();message(u("DFX 任务已启动"));}
   if(event=="stage"){QString stage=o["stage"].toString();QString name=stage=="segmentation"?u("CT 分割"):stage=="reconstruction"?u("重建与平滑"):stage=="airway-detail"?u("细支气管候选审核"):u("路径导航");progress->setRange(0,0);message(u("正在执行：")+name+u("，界面可继续操作"));record("stage_"+stage);}
   if(event=="stage_done")message(o["stage"].toString()+QString(" · %1 s").arg(o["seconds"].toDouble(),0,'f',2));
   if(event=="completed"){progress->setRange(0,100);progress->setValue(o["status"]=="passed"?100:0);message(o["status"]=="passed"?u("任务已完成，正在更新视图"):u("已停止后续步骤，当前阶段正常结束"));if(o["status"]!="passed")runOutput.clear();}
   if(event=="error"){failed=true;message(o["text"].toString());}
  }
 }
 void prepare(QString selected=QString()){
  if(processing())return;if((plScope&&plScope->active())||(plComposite&&plComposite->active())){releaseGraphics([this,selected]{prepare(selected);});return;}busy(true);pendingResult.clear();failed=false;prepPending.clear();errors.clear();progress->setRange(0,0);message(u("正在准备病例视图"));
  if(selectedTestStage==0&&qEnvironmentVariableIntValue("KV260_SELECTED_PATH_UI_TEST")==1&&selected.isEmpty())selected=qEnvironmentVariable("KV260_SELECTED_SOURCE_RESULT");
  QStringList args={root+"/ui/releases/ct_bounded_outputs_r1/backend.py","prepare","--input",input};if(!selected.isEmpty())args<<"--result"<<selected;
  QString complete=qEnvironmentVariable("KV260_COMPLETE_SCENE");
  if(scene.isEmpty()&&selected.isEmpty()&&!complete.isEmpty())args=QStringList{root+"/modules/navigation_replan/backend_r2265.py","prepare","--active-scene",complete,"--input",input};
  prepareProcess.start(root+"/.venv/bin/python",args);
 }
 void loadScene(QString path){
  bool previouslyUnavailable=replanUnavailable;replanUnavailable=false;cameraSlider->setEnabled(true);
  auto nextScene=readyVolume&&readyPath==path?readyMeta:readJson(path);auto next=readyVolume&&readyPath==path?readyVolume:std::make_shared<Volume>();if(next!=readyVolume)next->load(path,nextScene);readyVolume.reset();readyMeta={};readyPath.clear();volume=next;scene=nextScene;scenePath=path;source=scene["result"].toString();
  if(qEnvironmentVariableIntValue("KV260_FORCE_RAW_CT_TEST")==1&&!freshRawSeen){freshRawSeen=true;
   freshRawInitialVerified=source.isEmpty()&&scene["meshes"].toObject().isEmpty()&&scene["candidates"].toArray().isEmpty();
   if(!freshRawInitialVerified)failed=true;
  }
  for(auto*s:slices)s->setVolume(volume);axialSlider->setRange(0,volume->dims[2]-1);axialSlider->setValue(volume->dims[2]/2);
  {QSignalBlocker block(airwayOverlay);airwayOverlay->setCurrentIndex(0);auto options=scene["airway_masks"].toObject();auto*model=qobject_cast<QStandardItemModel*>(airwayOverlay->model());if(model){model->item(1)->setEnabled(options.contains("network"));model->item(2)->setEnabled(options.contains("detail"));for(int i=3;i<6;++i)model->item(i)->setEnabled(scene.contains("distal_recovery"));}for(auto*s:slices)s->setAirwayMask(2);auto audit=scene["airway_detail"].toObject();QString text=audit.isEmpty()?u("默认清理掩膜；候选碎片审核尚无结果。"):QString(u("独立候选：%1 个碎片 / %2 体素 · 未生成连接桥 · 不替换默认重建与导航掩膜")).arg(audit["retained_components"].toInt()).arg(audit["added_voxels"].toInt());auto recovery=scene["distal_recovery"].toObject();if(!recovery.isEmpty()){auto s=recovery["summary"].toObject();text+=QString(u("\n恢复审核：高置信 %1 / 待复核 %2 / 排除 %3；连接桥仅供审核，默认模型与导航保持原样。目标候选 #%4")).arg(s["high_confidence_candidates"].toInt()).arg(s["review_candidates"].toInt()).arg(s["rejected_candidates"].toInt()).arg(recovery["candidate_index_zero_based"].toInt());}airwayAuditInfo->setText(text);}
  overview->loadScene(path,scene);scope->loadScene(path,scene);if(dualCheck->isChecked())miniOverview->loadScene(path,scene);scope->setScope(true);bool ready=scope->cameraCount()>0&&QFileInfo::exists(source+"/navigation/route.json");scope->setVisible(ready);scopeUnavailable->setVisible(!ready);playButton->setEnabled(ready);bool haveMeshes=!scene["meshes"].toObject().isEmpty();preciseBlend->setEnabled(haveMeshes);if(!haveMeshes)preciseBlend->setChecked(false);cameraSlider->setRange(0,qMax(0,scope->cameraCount()-1));cameraSlider->setValue(0);navigationPosition->setText(QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,'f',1).arg(scope->totalDistance(),0,'f',1));
  structure_availability::apply(scene,meshLayers,structureButtons,structureAvailability);
  const auto lungState=structure_availability::describe(scene,"lung");
  xrayPreset->setEnabled(lungState.ready);opacity->setEnabled(lungState.ready);lungQuality->setEnabled(lungState.ready);
  if(!lungState.ready){opacity->setToolTip(lungState.reason);lungQuality->setToolTip(lungState.reason);}
  else{opacity->setToolTip(u("左端完全透明，右端完全不透明。快速模式显示最近一层肺表面；精确透明显示多层表面。"));lungQuality->setToolTip(u("切换肺的显示精度，计算结果保持完整。"));}
  airwayOverlay->setEnabled(hasStructure("airway"));airwayOverlay->setToolTip(hasStructure("airway")?u("选择已提供的气道叠加结果"):u("本次结果未提供气道掩膜。"));
  for(auto&camera:structureCameras)camera={};overview->setLungDetail(lungQuality->currentIndex()==1);for(int i=0;i<3;++i)overview->setLayer(i,meshLayers[i]->isChecked());overview->resetView();
  results->blockSignals(true);results->clear();for(auto v:scene["results"].toArray()){auto o=v.toObject();results->addItem(o["name"].toString(),o["path"].toString());}int selected=results->findData(source);if(selected>=0)results->setCurrentIndex(selected);results->blockSignals(false);
  caseLabel->setText(QFileInfo(input).fileName());info->setText(QString("%1 × %2 × %3\n%4 × %5 × %6 mm\n%7").arg(volume->dims[0]).arg(volume->dims[1]).arg(volume->dims[2]).arg(volume->spacing[0],0,'f',3).arg(volume->spacing[1],0,'f',3).arg(volume->spacing[2],0,'f',3).arg(source.isEmpty()?u("尚无分割结果"):u("分割 / 模型结果已加载")));
  auto nr=scene["navigation"].toObject()["report"].toObject();QString routeStatus=nr["status"].toString();
  routeInfo->setText(routeDescription(nr));routeInfo->setToolTip(u("净空检查：估计管腔半径减去图像分辨率保守余量，须不小于器械半径加每侧余量。此检查基于分割模型，不包含真实器械的弯曲及接触模型。"));
  if(!nr.isEmpty()){lesion->setValue(nr["target"].toObject()["index"].toInt());diameter->setValue(nr["scope_diameter_mm"].toDouble(1.));margin->setValue(nr["safety_margin_mm"].toDouble(.2));}
  refreshCandidates();
  auto attributes=scene["meshes"].toObject()["airway"].toObject()["attributes"].toObject();auto*model=qobject_cast<QStandardItemModel*>(colorMode->model());if(model){model->item(1)->setEnabled(!attributes.isEmpty());model->item(2)->setEnabled(!attributes.isEmpty());model->item(3)->setEnabled(attributes["confidence_available"].toBool());}if(attributes.isEmpty()||(colorMode->currentIndex()==3&&!attributes["confidence_available"].toBool()))colorMode->setCurrentIndex(0);minimumBend->setValue(nr["minimum_bend_radius_mm"].toDouble());
  if(previouslyUnavailable)routeCheck->setChecked(replanRouteWasVisible);
  updateColorLegend();progress->setRange(0,100);progress->setValue(100);message(u("病例已就绪 · 鼠标滚轮切片，拖动模型旋转"));if(!source.isEmpty()&&scene["source"]=="external_partial"){QStringList names;for(auto n:scene["available_structures"].toArray())names<<structure_availability::name(n.toString());info->setText(info->text()+u("\n已提供：")+names.join(" / "));message(u("仅重建已提供的结构；导航需气道和病灶候选。"));}else if(!source.isEmpty()&&QFile::exists(source+"/external_import.json")){info->setText(info->text()+u("\n外部掩膜已校验 · 概率图已保留"));message(u("外部掩膜已加载；点击重新重建使用PL生成模型。概率图表面需另行选择。"));}restoreSurfaceComparisonControls();restoreQualityControls();
  if(!source.isEmpty()&&QFileInfo::exists(source+"/segmentation/report.json")){auto policy=readJson(source+"/segmentation/report.json")["images"].toObject()["airway"].toObject()["postprocessing"].toObject();if(policy["policy"]=="probability_threshold_then_largest_26_connected_airway"){auto note=QString(u("概率图气道筛选：保留主气道 %1 体素，排除孤立区域 %2 体素；原始概率图已保留。" )).arg(policy["kept_voxels"].toInt()).arg(policy["removed_voxels"].toInt());info->setText(info->text()+"\n"+note);message(note);}}
  record("scene_loaded");selectedPathPrepared();
 }
 int navigationTargetForJob(QString mode)const{return mode=="all"&&!hasStructure("nodule")?0:lesion->value();}
 void startJob(QString mode){
  if((!scene.value("complete_surface").toObject().isEmpty())&&mode=="airway-detail"){startSurfaceAction(mode);return;}
  if((!scene.value("complete_surface").toObject().isEmpty())&&mode=="reconstruction"){startSurfaceAction("quality");return;}
  if((!scene.value("complete_surface").toObject().isEmpty())&&mode=="comparison"){startSurfaceAction(mode);return;}
  if((!scene.value("complete_surface").toObject().isEmpty())&&mode=="navigation"){startSurfaceAction("replan");return;}
  if((!scene.value("complete_surface").toObject().isEmpty())&&mode!="all"){message(u("当前新表面场景的单项重规划尚未接入；请保留当前场景，或选择原结果。"));return;}
  if((mode=="all"||mode=="navigation"||mode=="comparison"||mode=="airway-detail")&&hasStructure("nodule")&&lesionList->count()==0){message(u("当前筛选没有目标候选，请降低最小候选体积后再处理。"));return;}
  if(processing())return;if((plScope&&plScope->active())||(plComposite&&plComposite->active())){message(u("等待显示帧结束，准备切换医疗模块"));releaseGraphics([this,mode]{startJob(mode);});return;}runOutput.clear();failed=false;errors.clear();jobPending.clear();
  stopFile=root+"/ui/cache/stop_"+QUuid::createUuid().toString(QUuid::Id128);QFile::remove(stopFile);taskClock.restart();
  QStringList args={root+"/ui/releases/ct_bounded_outputs_r1/backend.py","run","--input",input,"--mode",mode,"--lesion",QString::number(navigationTargetForJob(mode)),"--diameter",QString::number(diameter->value()),"--margin",QString::number(margin->value()),"--minimum-bend",QString::number(minimumBend->value()),"--stop-file",stopFile};if(mode!="all")args<<"--result"<<source;
  jobProcess.start(root+"/.venv/bin/python",args);busy(true);stopButton->setEnabled(true);progress->setRange(0,0);message(u("正在启动后台医疗计算"));record("job_"+mode);
 }
 void stopAfterStage(){if(jobProcess.state()==QProcess::NotRunning)return;QFile f(stopFile);f.open(QIODevice::WriteOnly);f.write("stop after current stage\n");stopButton->setEnabled(false);message(u("将在当前阶段正常完成后停止，不中断 DMA"));}

 void updateAnalysis(){if(replanUnavailable){routeInfo->setText(blockedNavigationNotice());return;}for(auto*v:{overview,miniOverview})v->setAnalysisParameters(diameter->value(),margin->value());auto r=scene["navigation"].toObject()["report"].toObject();if(r.isEmpty())return;bool changed=r["target"].toObject()["index"].toInt()!=lesion->value()||std::abs(r["scope_diameter_mm"].toDouble()-diameter->value())>.001||std::abs(r["safety_margin_mm"].toDouble()-margin->value())>.001||std::abs(r["minimum_bend_radius_mm"].toDouble()-minimumBend->value())>.001;routeInfo->setText(routeDescription(r)+(changed?u("\n目标或器械参数已改变；当前路径尚未重算，请重新规划。"):QString()));}
 void updateColorLegend(){
  int mode=colorMode->currentIndex();auto attributes=scene["meshes"].toObject()["airway"].toObject()["attributes"].toObject();
  auto anatomy=attributes["anatomical_generation"].toObject();bool anchored=attributes["generation_kind"]=="carina_anchored_heuristic_topology_not_confirmed_anatomical_names";
  legend->setText(mode==1?(anchored?u("隆突锚定 · 0—7+ 代 · 灰色=不连通"):u("气管=0 · 图分支深度 · 灰色=不连通")):mode==2?u("红=受限 · 黄=余量小 · 绿=满足几何约束"):mode==3?u("红<0.45 · 黄<0.70 · 青<0.90 · 蓝≥0.90"):u("右击候选标记可选中"));
  legend->setToolTip(anchored?u("按骨架和显著分岔估计代数；短毛刺仅在着色分析中排除。未确认肺叶名称，不修改导航图或掩膜。")+(anatomy["carina_selection"]=="earliest_junction_unqualified_fallback"?u("\n当前采用未满足主分支条件的回退隆突，请审核。"):QString()):u("按当前导航图的分支深度着色。"));
 }
 void refreshCandidates(){
  int previous=lesion->value();lesionList->blockSignals(true);lesionList->clear();
  for(auto value:scene["candidates"].toArray()){auto c=value.toObject();
   if(c["volume_mm3"].toDouble()<minimumCandidateVolume->value())continue;
   int id=c["index"].toInt();lesionList->addItem(QString(u("候选 #%1 · %2 mm³")).arg(id).arg(c["volume_mm3"].toDouble(),0,'f',1),id);
  }
  int selected=lesionList->findData(previous);lesionList->setCurrentIndex(selected>=0?selected:0);
  lesionList->blockSignals(false);updateCandidate();
 }
#include "../feature_completion_r6/src/catalogue_test_guard_r4.inc"
 void updateCandidate(){int index=lesionList->currentData().toInt();if(lesionList->count()==0){lesion->setValue(-1);for(auto*v:{overview,miniOverview})v->selectCandidate(-1);candidateInfo->setText(scene["candidates"].toArray().isEmpty()?u("当前结果没有病灶候选"):u("当前体积筛选无候选；降低阈值可恢复"));updateAnalysis();busy(processing());return;}lesion->setValue(index);for(auto*v:{overview,miniOverview})v->selectCandidate(index);for(auto value:scene["candidates"].toArray()){auto c=value.toObject();if(c["index"].toInt()==index){auto p=c["centroid_lps_mm"].toArray();candidateInfo->setText(QString(u("%1 mm³ · %2 体素\nLPS (%3, %4, %5) mm")).arg(c["volume_mm3"].toDouble(),0,'f',1).arg(c["voxel_count"].toInt()).arg(p[0].toDouble(),0,'f',1).arg(p[1].toDouble(),0,'f',1).arg(p[2].toDouble(),0,'f',1));break;}}updateAnalysis();busy(processing());}

#include "../feature_completion_r6/src/selected_application_r14_presence_r96.inc"
#include "../feature_completion_r6/src/active_recovery_UI_r21a.inc"
#include "../feature_completion_r6/src/active_surface_UI_replan_r2266.inc"
#include "../../../modules/navigation_replan/UI_test_r2280.inc"
#include "../feature_completion_r6/src/surface_quality_UI_r16.inc"
#include "../feature_completion_r6/src/active_surface_test_r14b_presence_r96.inc"
#include "../feature_completion_r6/src/surface_comparison_dialog_r14d.inc"
#include "../feature_completion_r6/comparison_dispatch_r14_presence_r96.inc"
 void focusCandidate(){if(lesionList->count()==0)return;int index=lesion->value();tabs->setCurrentIndex(1);structureCameras[structureMode]=overview->overviewCamera();settingStructure=true;meshLayers[2]->setChecked(true);overview->focusCandidate(index);settingStructure=false;structureMode=2;if(overview->onOverviewChanged)overview->onOverviewChanged();for(auto v:scene["candidates"].toArray()){auto c=v.toObject();if(c["index"].toInt()!=index)continue;auto a=c["centroid_lps_mm"].toArray();QVector3D point(float(a[0].toDouble()),float(a[1].toDouble()),float(a[2].toDouble()));QMatrix4x4 matrix;for(int r=0;r<3;++r)for(int col=0;col<3;++col)matrix(r,col)=volume->direction(r,col);auto xyz=matrix.inverted().mapVector(point-volume->origin);for(int k=0;k<3;++k)xyz[k]/=volume->spacing[k];axialSlider->setValue(qRound(xyz.z()));slices[1]->setSlice(qRound(xyz.y()));slices[2]->setSlice(qRound(xyz.x()));}message(u("已聚焦选中候选；更换目标后需点击重新规划导航"));}
 void showRecoveryReview(){
  auto report=scene["distal_recovery"].toObject();if(report.isEmpty())return;auto rows=report["candidates"].toArray();
  QDialog dialog(this);dialog.setWindowTitle(u("细支气管恢复证据"));dialog.resize(850,470);auto*layout=new QVBoxLayout(&dialog);
  auto*hint=new QLabel(QString(u("目标候选 #%1 · 点击一行定位到 CT。黄色=待复核区域，连接桥为推测；默认模型与导航未改变。")).arg(report["candidate_index_zero_based"].toInt()));hint->setWordWrap(true);layout->addWidget(hint);
  auto*table=new QTableWidget(rows.size(),7);table->setHorizontalHeaderLabels({u("分量"),u("判断"),u("分数"),u("间隔 mm"),u("接近增益 mm"),u("CT 空气比例"),u("网络支持")});
  for(int i=0;i<rows.size();++i){auto r=rows[i].toObject();QStringList values={QString::number(r["component_label"].toInt()),r["classification"]=="high"?u("高置信"):r["classification"]=="review"?u("待复核"):u("排除"),QString::number(r["confidence"].toDouble(),'f',3),QString::number(r["gap_mm"].toDouble(),'f',2),QString::number(r["lesion_distance_gain_mm"].toDouble(),'f',2),QString::number(r["bridge_air_fraction"].toDouble(),'f',2),r["bridge_network_probability"].isDouble()?QString::number(r["bridge_network_probability"].toDouble(),'f',2):"—"};for(int k=0;k<values.size();++k)table->setItem(i,k,new QTableWidgetItem(values[k]));}
  table->setEditTriggers(QAbstractItemView::NoEditTriggers);table->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch);layout->addWidget(table);
  connect(table,&QTableWidget::cellClicked,this,[this,rows,&dialog](int row,int){auto r=rows[row].toObject();auto q=r["component_point_zyx"].toArray();tabs->setCurrentIndex(0);airwayOverlay->setCurrentIndex(r["classification"]=="review"?4:r["classification"]=="high"?3:1);axialSlider->setValue(q[0].toInt());slices[1]->setSlice(q[1].toInt());slices[2]->setSlice(q[2].toInt());dialog.accept();});
  auto*close=new QPushButton(u("关闭"));layout->addWidget(close);connect(close,&QPushButton::clicked,&dialog,&QDialog::accept);dialog.exec();
 }
 void startUtility(QString action,QStringList args){
  bool activeExport=action=="export"&&(!scene.value("complete_surface").toObject().isEmpty());if(processing())return;if((plScope&&plScope->active())||(plComposite&&plComposite->active())){releaseGraphics([this,action,args]{startUtility(action,args);});return;}utilityBytes.clear();utilityError.clear();utilityAction=action;busy(true);QString adapter=action=="import-external"?root+"/ui/releases/probability_cleanup_r1/import_backend.py":activeExport?root+"/modules/surface_route/export_backend_r21.py":root+"/modules/report_export/backend.py";if(activeExport)args<<"--active-scene"<<scenePath;utilityProcess.start(root+"/.venv/bin/python",QStringList{adapter,action}+args);message(action=="import-external"?u("正在校验外部掩膜与概率图"):action=="export"?u("正在导出模型与报告"):u("正在读取 DICOM 序列"));}
#include "../feature_completion_r6/src/dicom_test.inc"
#include "../feature_completion_r6/src/export_test_reports_r1.inc"
 void finishUtility(int code,QProcess::ExitStatus status){utilityBytes+=utilityProcess.readAllStandardOutput();utilityError+=QString::fromUtf8(utilityProcess.readAllStandardError());QJsonObject result;for(auto line:utilityBytes.split('\n')){auto doc=QJsonDocument::fromJson(line);if(doc.isObject())result=doc.object();}busy(false);if(code||status!=QProcess::NormalExit||result["event"]=="error"){QString why=result["text"].toString(utilityError);message(why);if(exportTesting){exportFinish(false,result,why);return;}if(dicomTesting){dicomFinish(false,why);return;}configureScope();externalRejected(why);return;}if(result["event"]=="external_imported"){prepare(result["result"].toString());}else if(result["event"]=="dicom_series"){chooseDicomSeries(result);}else if(result["event"]=="imported"){if(dicomTesting)dicomImported=result;input=result["input"].toString();source.clear();prepare();}else if(result["event"]=="exported"){message(u("已导出至 ")+result["path"].toString());if(activeRecoveryTesting){recoveryExported(result);return;}
if(exportTesting){
 QString folder=result["path"].toString();
 auto report=readJson(folder+"/surfaces/report.json");
 auto structures=report["structures"].toObject();
 bool activeExport=(!scene.value("complete_surface").toObject().isEmpty());auto complete=readJson(folder+(activeExport?"/original_analysis/index.json":"/reports/index.json"));
 bool bound=!activeExport||(result["active_revision"]==scene["complete_surface"].toObject()["revision"]&&result["active_route_id"]==scene["complete_surface"].toObject()["route_id"]&&report["active_revision"]==scene["complete_surface"].toObject()["revision"]&&QFileInfo::exists(folder+"/active_scene/bundle/scene.json"));bool good=bound&&result["schema"]==(activeExport?"kv260.export.v6":"kv260.export.v5")&&complete["schema"]=="kv260.export.complete_reports.v1"&&complete["status"]=="completed"&&report["status"]=="completed"&&
   structures.contains("lung")&&structures.contains("airway")&&structures.contains("nodule")&&
   ticks-exportStartTick>=2&&result["lesion_catalogue_state"]=="retained_candidates"&&QFileInfo::exists(folder+"/lesions/lesion_labels.nrrd");
 exportFinish(good,result,u("完整模型、属性和原有导出包已生成"));return;
}configureScope();}}
 void capture(QString name){QDir().mkpath(evidence);grab().save(evidence+"/"+name+".png");if(overview->isVisible())overview->grabFramebuffer().save(evidence+"/"+name+"_viewport.png");if(scope->isVisible())scope->grabFramebuffer().save(evidence+"/"+name+"_viewport.png");}
#include "../feature_completion_r6/src/composite_test.inc"
#include "../feature_completion_r6/src/transparent_breathing_r1.inc"
#include "../feature_completion_r6/src/linked_camera_test.inc"
 void finishTest(){
  finishingTest=true;if((plScope&&plScope->active())||(plComposite&&plComposite->active())){releaseGraphics([this]{finishTest();});return;}
  capture("final");for(auto*v:{overview,scope}){auto m=v->metrics();if(!m["valid"].toBool()||!m["shader_linked"].toBool()||!m["error"].toString().isEmpty())failed=true;}QVector<double> sorted=gaps;std::sort(sorted.begin(),sorted.end());QVector<double> jg=jobGaps;std::sort(jg.begin(),jg.end());struct rusage usage{};getrusage(RUSAGE_SELF,&usage);
  QJsonObject o{{"status",failed?"failed":"passed"},{"kind","actual_kv260_native_ui"},{"platform",QApplication::platformName()},{"root",root},{"scene",scenePath},{"input",input},{"actions",actions},{"ui_heartbeat_count",ticks},{"ui_heartbeat_interval_ms",50},{"heartbeat_gap_p95_ms",sorted.isEmpty()?0:sorted[int((sorted.size()-1)*.95)]},{"heartbeat_gap_max_ms",sorted.isEmpty()?0:sorted.last()},{"ct_pages_locked",volume&&volume->ctLocked},{"mask_pages_locked",volume&&volume->maskLocked},{"peak_rss_mib",usage.ru_maxrss/1024.},{"overview",overview->metrics()},{"scope",scope->metrics()},{"dfx_run_output",runOutput},{"dfx_heartbeat_samples",jg.size()},{"dfx_heartbeat_p95_ms",jg.isEmpty()?0:jg[int((jg.size()-1)*.95)]},{"dfx_heartbeat_max_ms",jg.isEmpty()?0:jg.last()},{"lung_rotation_swapped_frames",lungIntervals.size()},{"lung_rotation_fps",lungIntervals.isEmpty()?0:1000.*lungIntervals.size()/std::accumulate(lungIntervals.begin(),lungIntervals.end(),0.)},{"rotation_swapped_frames",swapIntervals.size()},{"rotation_fps",swapIntervals.isEmpty()?0:1000.*swapIntervals.size()/std::accumulate(swapIntervals.begin(),swapIntervals.end(),0.)},{"physical_mouse_verified",false},{"pl_scope_frames",plFrames},{"pl_scope_last_frame",plLastFrame}};
  o["fresh_raw_initial_scene_verified"]=freshRawInitialVerified;o["composite_frame_trace"]=compositeTrace;o["composite_frames"]=compositeFrames;o["composite_last_frame"]=overview->completedComposite();o["features"]=overview->featureMetrics();o["scope_features"]=scope->featureMetrics();o["navigation_interaction"]=navigationTestReport;o["navigation_frame_trace"]=navigationTrace;o["linked_camera_test"]=linkedReport;o["linked_camera_trace"]=linkedTrace;writeJson(evidence+"/ui_acceptance.json",o);QApplication::exit(failed?1:0);
 }
 void navigationBenchmarkFinish(){
  navigationMotion.stop();play.stop();playing=false;playButton->setText(u("沿路径播放"));scope->setPlayback(false);navigationBenchmarking=false;navigationTestReport["continuous_playback_samples"]=playbackTestTrace;
  double fps=navigationPresented.size()>1?1000.*(navigationPresented.size()-1)/(navigationPresented.last()-navigationPresented.first()):0;
  QVector<double> intervals;for(int i=1;i<navigationPresented.size();++i)intervals.append(navigationPresented[i]-navigationPresented[i-1]);std::sort(intervals.begin(),intervals.end());
  navigationTestReport["quality_level"]=scopeQuality->currentIndex();navigationTestReport["presented_frames"]=navigationPresented.size();navigationTestReport["actual_update_fps"]=fps;
  navigationTestReport["gap_p95_ms"]=intervals.isEmpty()?0:intervals[int((intervals.size()-1)*.95)];navigationTestReport["gap_max_ms"]=intervals.isEmpty()?0:intervals.last();navigationTestReport["pose_after_release"]=scope->cameraRequest();
  scopeWait=0;navigationRefineWait();
 }
 void navigationRefineWait(){
  if((plLastFrame["interactive"].toBool()||plLastFrame["width"].toInt()<640)&&scopeWait++<50){QTimer::singleShot(100,this,[this]{navigationRefineWait();});return;}
  auto pose=scope->cameraRequest();navigationTestReport["refined_frame"]=plLastFrame;
  if(plLastFrame["interactive"].toBool()||plLastFrame["width"].toInt()<640||std::abs(pose["manual_yaw_degrees"].toDouble())+std::abs(pose["manual_pitch_degrees"].toDouble())>1||navigationPresented.size()<20)failed=true;
  capture("06_navigation_refined");finishTest();
 }
 #include "../../../ui/releases/feature_completion_r6/src/structure_test.inc"
 #include "../../../ui/releases/feature_completion_r6/src/airway_test.inc"
 #include "../../../ui/releases/feature_completion_r6/src/recovery_test.inc"
 void smokeAdvance(){
  if(!smoke||scenePath.isEmpty())return;if(processing()){QTimer::singleShot(100,this,[this]{smokeAdvance();});return;}
  if(!smokeStarted){smokeStarted=true;
   if(qEnvironmentVariableIntValue("KV260_FORCE_RAW_CT_TEST")==1){
    if(!freshRawInitialVerified||!runButton->isEnabled()||navigationTargetForJob("all")!=0){failed=true;finishTest();return;}
    smokeStep=5;runButton->click();return;
   }
   QTimer::singleShot(500,this,[this]{smokeAdvance();});return;}
  switch(smokeStep++){
   case 0:tabs->setCurrentIndex(0);axialSlider->setValue(qMin(70,axialSlider->maximum()));record("slice_changed");capture("01_slices");break;
   case 1:if(acceptance)preciseBlend->setChecked(true);tabs->setCurrentIndex(1);overview->resetView();record("overview_opened");break;
   case 2:if(featureTesting){if(lesionList->count()==0||scene["meshes"].toObject()["airway"].toObject()["attributes"].toObject().isEmpty())failed=true;focusCandidate();capture("feature_focus");overview->resetView();for(int mode:{1,2}){colorMode->setCurrentIndex(mode);capture(mode==1?"feature_generation":"feature_reachability");}if(scene["meshes"].toObject()["airway"].toObject()["attributes"].toObject()["confidence_available"].toBool()){colorMode->setCurrentIndex(3);capture("feature_confidence");}clipCheck->setChecked(true);capture("feature_clip");clipCheck->setChecked(false);colorMode->setCurrentIndex(0);record("features_checked");}testDrag(overview,QPoint(180,160),QPoint(260,200));record("mouse_drag_overview");capture("02_model");break;
   case 3:tabs->setCurrentIndex(2);firstBranchPose();record("navigation_camera_changed");if(featureTesting){capture("navigation_preparing");if(!scope->featureMetrics()["last_paint_awaiting_pl"].toBool())failed=true;}break;
   case 4:if((plFrames==0||plLastFrame["branch_event"].toInt(-1)<0)&&scopeWait++<100){--smokeStep;QTimer::singleShot(700,this,[this]{smokeAdvance();});return;}if(plFrames==0||plLastFrame["branch_event"].toInt(-1)<0)failed=true;if(featureTesting){dualCheck->setChecked(true);QApplication::processEvents();capture("feature_linked_overview");dualCheck->setChecked(false);QApplication::processEvents();if(scope->featureMetrics()["overlay_paints"].toInt()==0)failed=true;}capture("03_navigation");if(linkedTesting){linkedStart();return;}if(navigationTesting&&!navigationBenchStarted){navigationBenchStarted=true;navigationBase=cameraSlider->value();navigationMotionClock.restart();navigationBenchmarking=true;scope->setPlayback(true);testDrag(scope,QPoint(200,170),QPoint(280,200));navigationTestReport["pose_after_drag"]=scope->cameraRequest();if(std::abs(scope->cameraRequest()["manual_yaw_degrees"].toDouble())<10)failed=true;if(qEnvironmentVariableIntValue("KV260_NAV_TEST_PLAYBACK")==1)playButton->click();else navigationMotion.start(16);QTimer::singleShot(8500,this,[this]{navigationBenchmarkFinish();});return;}if(acceptance){runButton->click();return;}break;
   case 5:if(acceptance&&!verifiedScopeReturn){if(returnFrameBase<0){returnFrameBase=plFrames;scopeWait=0;tabs->setCurrentIndex(2);configureScope();firstBranchPose();}if((plFrames<=returnFrameBase||plLastFrame["branch_event"].toInt(-1)<0)&&scopeWait++<100){--smokeStep;QTimer::singleShot(700,this,[this]{smokeAdvance();});return;}if(plFrames<=returnFrameBase||plLastFrame["branch_event"].toInt(-1)<0)failed=true;verifiedScopeReturn=true;record("pl_scope_resumed_after_medical_dfx");capture("05_scope_after_dfx");}tabs->setCurrentIndex(1);record("rotation_benchmark_started");QTimer::singleShot(250,this,[this]{benchmarking=true;swapClock.restart();rotation.start(16);});QTimer::singleShot(5500,this,[this]{benchmarking=false;rotation.stop();record("rotation_benchmark_finished");smokeAdvance();});return;
   case 6:overview->setLayer(0,true);lungBenchmark=true;record("full_lung_benchmark_started");QTimer::singleShot(800,this,[this]{benchmarking=true;swapClock.restart();rotation.start(16);});QTimer::singleShot(5800,this,[this]{benchmarking=false;rotation.stop();capture("04_all_structures");overview->setLayer(0,false);record("full_lung_benchmark_finished");smokeAdvance();});return;
   default:finishTest();return;
  }
  QTimer::singleShot(700,this,[this]{smokeAdvance();});
 }
public:
 MainWindow(QString project,QString initial,bool testing,bool realRun,bool navTesting,QString output,int navQuality,bool featuresTest):root(project),input(initial),evidence(output),smoke(testing),acceptance(realRun),navigationTesting(navTesting){featureTesting=featuresTest;
  setWindowTitle(u("KV260 医疗影像工作站"));resize(1024,768);setMinimumSize(780,580);
  auto*outer=new QVBoxLayout(this);outer->setContentsMargins(16,12,16,10);outer->setSpacing(10);
  auto*header=new QHBoxLayout;auto*title=new QLabel(u("AIRWAY  /  医疗影像工作站"));title->setObjectName("title");header->addWidget(title);header->addStretch();gpuLabel=new QLabel(u("图形初始化"));header->addWidget(gpuLabel);clock=new QLabel;header->addWidget(clock);auto*close=new QPushButton(u("退出"));header->addWidget(close);connect(close,&QPushButton::clicked,this,&QWidget::close);outer->addLayout(header);
  auto*body=new QHBoxLayout;outer->addLayout(body,1);auto*sidebar=new QWidget;sidebar->setFixedWidth(230);sidebar->setObjectName("sidebar");auto*left=new QVBoxLayout(sidebar);left->setSpacing(8);
  auto*section=new QLabel(u("当前病例"));section->setObjectName("section");left->addWidget(section);caseLabel=new QLabel(u("未选择 CT"));caseLabel->setWordWrap(true);left->addWidget(caseLabel);info=new QLabel;info->setWordWrap(true);info->setObjectName("muted");left->addWidget(info);
  openButton=button(u("打开 CT 文件"),left);dicomButton=button(u("导入 DICOM 序列目录"),left);importButton=button(u("导入掩膜 / 概率图"),left);importButton->setToolTip(u("选择属于当前CT的外部影像清单；校验文件及物理坐标，不自动重采样。"));results=new QComboBox;results->setMinimumWidth(0);results->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);left->addWidget(new QLabel(u("已完成结果")));left->addWidget(results);refreshButton=button(u("刷新 / 重新载入"),left);
  maskEvaluationButton=button(u("参考标注评估"),left);maskEvaluationButton->setObjectName("mask_evaluation_open");
  connect(maskEvaluationButton,&QPushButton::clicked,this,[this]{if(processing()||source.isEmpty())return;if(maskEvaluation){maskEvaluation->close();maskEvaluation=nullptr;}maskEvaluation=new MaskEvaluationDialog(root,input,source,[this](bool running){maskEvaluationBusy=running;busy(false);if(!running)QTimer::singleShot(0,this,[this]{if(!maskEvaluationBusy)configureScope();});},this);maskEvaluation->show();});
  huButton=button(u("HU 气道分割…"),left);huButton->setObjectName("HU_airway_open");
  connect(huButton,&QPushButton::clicked,this,[this]{
   if(processing()||input.isEmpty())return;
   if(huDialog){huDialog->close();huDialog=nullptr;}
   QString selectedCT=input;
   huDialog=new AdaptiveAirwayDialog(root,input,source,
    [this,selectedCT]{return input==selectedCT&&!processing();},
    [this](bool running){huBusy=running;busy(false);if(!running)QTimer::singleShot(0,this,[this]{if(!processing())configureScope();});},
    [this,selectedCT](QString result){QTimer::singleShot(0,this,[this,selectedCT,result]{
     if(input==selectedCT&&!processing()){record("HU_result_accepted");prepare(result);}
     else message(u("HU 结果已保存；当前病例已变化，请从原病例载入结果。"));
    });},this);huDialog->show();
  });
  auto*line=new QFrame;line->setFrameShape(QFrame::HLine);left->addWidget(line);runButton=button(u("开始完整处理"),left);runButton->setObjectName("primary");rebuildButton=button(u("重新重建 / 平滑"),left);navButton=button(u("重新规划导航"),left);
  auto*form=new QFormLayout;lesion=new QSpinBox;lesion->setRange(-1,1000000000);lesion->hide();lesionList=new QComboBox;lesionList->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);form->addRow(u("目标候选"),lesionList);minimumCandidateVolume=new QDoubleSpinBox;minimumCandidateVolume->setRange(0,1.e9);minimumCandidateVolume->setDecimals(1);minimumCandidateVolume->setValue(14);minimumCandidateVolume->setSuffix(u(" mm³"));minimumCandidateVolume->setToolTip(u("按原始体素的物理体积筛选候选，0 显示全部；不修改分割或重建模型。"));form->addRow(u("最小候选体积"),minimumCandidateVolume);candidateInfo=new QLabel;candidateInfo->setWordWrap(true);candidateInfo->setObjectName("muted");left->addWidget(candidateInfo);focusButton=button(u("聚焦选中候选"),left);diameter=new QDoubleSpinBox;diameter->setRange(.1,10);diameter->setDecimals(1);diameter->setValue(1);diameter->setSuffix(" mm");form->addRow(u("器械直径"),diameter);margin=new QDoubleSpinBox;margin->setRange(0,5);margin->setDecimals(1);margin->setSingleStep(.1);margin->setValue(.2);margin->setSuffix(" mm");form->addRow(u("安全余量"),margin);minimumBend=new QDoubleSpinBox;minimumBend->setRange(0,100);minimumBend->setDecimals(1);minimumBend->setSuffix(" mm");minimumBend->setToolTip(u("0 为关闭；非零值审核路径的离散弯曲半径，超限时仅保留复核后的可达前段。"));form->addRow(u("最小弯曲半径"),minimumBend);left->addLayout(form);compareButton=button(u("比较器械与接近路径"),left);comparisonResults=button(u("查看比较结果"),left);comparisonResults->setEnabled(false);exportButton=button(u("导出模型 / 颜色 / 路径 / 报告"),left);snapshotButton=button(u("保存截图 · PNG"),left);batchButton=button(u("批量导出功能图片"),left);connect(batchButton,&QPushButton::clicked,this,[this]{batchRequest();});videoButton=button(u("导出导航视频 · MP4"),left);connect(videoButton,&QPushButton::clicked,this,[this]{videoRequest();});
  connect(snapshotButton,&QPushButton::clicked,this,[this]{captureRequest();});
  auto*snapshotShortcut=new QShortcut(QKeySequence("Ctrl+S"),this);connect(snapshotShortcut,&QShortcut::activated,this,[this]{captureRequest();});
  left->addStretch();elapsed=new QLabel;left->addWidget(elapsed);stopButton=button(u("停止后续步骤"),left);stopButton->setEnabled(false);auto*note=new QLabel(u("实验系统 · 病灶为模型候选\n显示与医疗计算独立运行"));note->setObjectName("muted");note->setWordWrap(true);left->addWidget(note);auto*sideScroll=new QScrollArea;sideScroll->setWidget(sidebar);sideScroll->setWidgetResizable(true);sideScroll->setFixedWidth(250);sideScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);body->addWidget(sideScroll);
  tabs=new QTabWidget;body->addWidget(tabs,1);
  auto*ctPage=new QWidget;auto*ctLayout=new QVBoxLayout(ctPage);auto*tools=new QHBoxLayout;tools->addWidget(new QLabel(u("窗位预设")));windowPreset=new QComboBox;windowPreset->addItems({u("肺窗"),u("纵隔窗"),u("骨窗")});tools->addWidget(windowPreset);auto*mask=new QCheckBox(u("分割叠加"));mask->setChecked(true);tools->addWidget(mask);tools->addWidget(new QLabel(u("气道掩膜")));airwayOverlay=new QComboBox;airwayOverlay->addItem(u("清理后（默认）"),2);airwayOverlay->addItem(u("网络原始"),8);airwayOverlay->addItem(u("候选碎片（未验证）"),16);airwayOverlay->addItem(u("高置信恢复（实验）"),32);airwayOverlay->addItem(u("待复核（黄色）"),64);airwayOverlay->addItem(u("实验合并（不用于导航）"),128);tools->addWidget(airwayOverlay);tools->addStretch();ctLayout->addLayout(tools);airwayAuditInfo=new QLabel;airwayAuditInfo->setWordWrap(true);airwayAuditInfo->setObjectName("muted");ctLayout->addWidget(airwayAuditInfo);auto*recoveryTools=new QHBoxLayout;recoveryButton=new QPushButton(u("审核朝向目标的细支气管"));recoveryReviewButton=new QPushButton(u("查看恢复证据 / 定位 CT"));recoveryTools->addWidget(recoveryButton);recoveryTools->addWidget(recoveryReviewButton);recoveryTools->addStretch();ctLayout->addLayout(recoveryTools);connect(recoveryButton,&QPushButton::clicked,this,[this]{startJob("airway-detail");});connect(recoveryReviewButton,&QPushButton::clicked,this,[this]{showRecoveryReview();});
  auto*grid=new QGridLayout;slices[0]=new SliceView(2,u("Z 切面 · 轴向采样"));slices[1]=new SliceView(1,u("Y 切面 · 冠状采样"));slices[2]=new SliceView(0,u("X 切面 · 矢状采样"));grid->addWidget(slices[0],0,0,1,2);grid->addWidget(slices[1],1,0);grid->addWidget(slices[2],1,1);grid->setRowStretch(0,1);grid->setRowStretch(1,1);ctLayout->addLayout(grid,1);axialSlider=new QSlider(Qt::Horizontal);ctLayout->addWidget(axialSlider);coordinate=new QLabel(u("滚轮浏览切片 · 点击读取 HU 和 LPS 坐标"));coordinate->setObjectName("muted");ctLayout->addWidget(coordinate);tabs->addTab(ctPage,u("影像 / 分割"));
  auto*meshPage=new QWidget;auto*meshLayout=new QVBoxLayout(meshPage);auto*layers=new QHBoxLayout;QStringList names={u("肺（半透明）"),u("气道"),u("病灶候选")};overview=new MeshView;scope=new MeshView;
  for(int i=0;i<3;++i){auto*c=new QCheckBox(names[i]);meshLayers[i]=c;c->setChecked(i!=0);layers->addWidget(c);connect(c,&QCheckBox::toggled,this,[this,i](bool enabled){overview->setLayer(i,enabled);if(!settingStructure)structureMode=2;});}
  routeCheck=new QCheckBox(u("路径"));routeCheck->setChecked(true);layers->addWidget(routeCheck);connect(routeCheck,&QCheckBox::toggled,overview,&MeshView::setRoute);layers->addStretch();auto*reset=new QPushButton(u("复位视角"));layers->addWidget(reset);connect(reset,&QPushButton::clicked,overview,&MeshView::resetView);meshLayout->addLayout(layers);structureAvailability=new QLabel;structureAvailability->setObjectName("structureAvailability");structureAvailability->setWordWrap(true);meshLayout->addWidget(structureAvailability);
  auto*structureTools=new QHBoxLayout;QStringList presetNames={u("只看肺"),u("只看支气管"),u("恢复组合")};for(int i=0;i<3;++i){auto*b=new QPushButton(presetNames[i]);structureButtons[i]=b;structureTools->addWidget(b);connect(b,&QPushButton::clicked,this,[this,i]{showStructure(i);});}auto*fit=new QPushButton(u("适配当前结构"));structureTools->addWidget(fit);connect(fit,&QPushButton::clicked,overview,&MeshView::fitVisible);structureTools->addStretch();meshLayout->addLayout(structureTools);addXrayPreset(meshLayout);addBreathingControl(meshLayout);
  auto*quality=new QComboBox;lungQuality=quality;quality->addItems({u("肺：交互预览（计算结果保持完整）"),u("肺：完整网格（较慢）")});connect(quality,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this](int i){overview->setLungDetail(i==1);});qualityControls(meshLayout);meshLayout->addWidget(quality);auto*analysisTools=new QHBoxLayout;analysisTools->addWidget(new QLabel(u("气道着色")));colorMode=new QComboBox;colorMode->addItems({u("结构颜色"),u("分支代数"),u("器械可达性"),u("网络置信度")});analysisTools->addWidget(colorMode);legend=new QLabel;legend->setObjectName("muted");analysisTools->addWidget(legend,1);meshLayout->addLayout(analysisTools);
  auto*surfaceTools=new QHBoxLayout;clipCheck=new QCheckBox(u("剖切"));surfaceTools->addWidget(clipCheck);clipAxis=new QComboBox;clipAxis->addItems({"LPS X","LPS Y","LPS Z"});clipAxis->setCurrentIndex(2);surfaceTools->addWidget(clipAxis);clipOffset=new QSlider(Qt::Horizontal);clipOffset->setRange(-100,100);surfaceTools->addWidget(clipOffset,1);surfaceTools->addWidget(new QLabel(u("肺不透明度")));opacity=new QSlider(Qt::Horizontal);opacity->setRange(0,100);opacity->setToolTip(u("左端完全透明，右端完全不透明。快速模式显示最近一层肺表面；精确透明显示多层表面。"));opacity->setValue(20);opacity->setMaximumWidth(110);surfaceTools->addWidget(opacity);meshLayout->addLayout(surfaceTools);meshLayout->addWidget(overview,1);auto*modelNote=new QLabel(u("气道 / 病灶保持完整网格 · 肺显示精度可切换"));modelNote->setObjectName("muted");meshLayout->addWidget(modelNote);auto*blendTools=new QHBoxLayout;preciseBlend=new QCheckBox(u("精确透明（多层）"));preciseBlend->setToolTip(u("停止操作后逐层排序肺表面并用 PL 精确合成；交互预览保留所选网格，使用近似透明。"));blendTools->addWidget(preciseBlend);fastTransparency=new QCheckBox(u("交互时快速预览"));fastTransparency->setChecked(!compositeTesting);fastTransparency->setToolTip(u("旋转、缩放和平移时立即显示当前镜头；停止 450 ms 后生成完整精确透明画面。关闭后始终等待精确帧。"));blendTools->addWidget(fastTransparency);compositePerf=new QLabel(u("快速总览 · 拖动旋转 / 滚轮缩放"));compositePerf->setObjectName("muted");blendTools->addWidget(compositePerf,1);meshLayout->addLayout(blendTools);connect(preciseBlend,&QCheckBox::toggled,this,[this](bool enabled){overview->setCompositeEnabled(enabled);compositeQuiet.stop();if(enabled&&fastTransparency->isChecked()){overview->setCompositePreview(true);compositeQuiet.start(450);}else configureScope();});
  connect(fastTransparency,&QCheckBox::toggled,this,[this](bool enabled){if(!overview->compositeMode())return;compositeQuiet.stop();overview->setCompositePreview(enabled);if(enabled)compositeQuiet.start(450);else{configureScope();if(plComposite->active()&&!processing())plComposite->request(overview->overviewRequest());}});tabs->addTab(meshPage,u("三维模型"));
  auto*navPage=new QWidget;auto*navLayout=new QVBoxLayout(navPage);routeInfo=new QLabel(u("尚无导航结果"));routeInfo->setObjectName("notice");routeInfo->setWordWrap(true);navLayout->addWidget(routeInfo);auto*dualLayout=new QHBoxLayout;scopeUnavailable=new QLabel(u("尚无导航路径，请先重新规划导航。"));scopeUnavailable->setAlignment(Qt::AlignCenter);scopeUnavailable->setWordWrap(true);scopeUnavailable->hide();dualLayout->addWidget(scopeUnavailable,2);dualLayout->addWidget(scope,2);miniOverview=new MeshView;miniOverview->setMinimumWidth(180);miniOverview->setLayer(1,true);miniOverview->setLayer(2,true);miniOverview->hide();dualLayout->addWidget(miniOverview,1);navLayout->addLayout(dualLayout,1);cameraSlider=new QSlider(Qt::Horizontal);navLayout->addWidget(cameraSlider);auto*navTools=new QHBoxLayout;playButton=new QPushButton(u("沿路径播放"));navTools->addWidget(playButton);auto*resetScope=new QPushButton(u("回正镜头"));navTools->addWidget(resetScope);navigationAlign=new QCheckBox(u("自动对齐路径"));navigationAlign->setChecked(true);navTools->addWidget(navigationAlign);dualCheck=new QCheckBox(u("联动总览"));navTools->addWidget(dualCheck);connect(navigationAlign,&QCheckBox::toggled,scope,&MeshView::setAutoAlign);navTools->addStretch();navTools->addWidget(new QLabel(u("滚轮前进 / 后退，双击回正")));navLayout->addLayout(navTools);auto*qualityTools=new QHBoxLayout;qualityTools->addWidget(new QLabel(u("画质")));scopeQuality=new QComboBox;scopeQuality->addItems({u("清晰 · 640"),u("均衡 · 384"),u("流畅 · 256")});scopeQuality->setCurrentIndex(navQuality);scopeQuality->setToolTip(u("清晰：始终宽 640；均衡/流畅：移动时宽 384/256，停止后恢复宽 640。只调整显示像素数。"));qualityTools->addWidget(scopeQuality);connect(scopeQuality,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this](int level){plScope->setQuality(level);if(plScope->active())plScope->request(scope->cameraRequest());});scopePerf=new QLabel(u("默认清晰画面 · 可选择均衡或流畅"));scopePerf->setObjectName("muted");qualityTools->addWidget(scopePerf,1);navLayout->addLayout(qualityTools);navigationControls(navLayout);tabs->addTab(navPage,u("导航"));
  task=new QLabel(u("准备启动"));task->setWordWrap(true);outer->addWidget(task);progress=new QProgressBar;progress->setFixedHeight(5);progress->setTextVisible(false);outer->addWidget(progress);log=new QPlainTextEdit;log->setReadOnly(true);log->setMaximumHeight(64);log->setMaximumBlockCount(100);outer->addWidget(log);
  connect(axialSlider,&QSlider::valueChanged,slices[0],&SliceView::setSlice);slices[0]->onSlice=[this](int value){axialSlider->setValue(value);};for(auto*s:slices)s->onPosition=[this](QString text){coordinate->setText(text);};
  connect(windowPreset,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this](int i){float c[]={-600,40,400},w[]={1500,400,1800};for(auto*s:slices)s->windowLevel(c[i],w[i]);});connect(mask,&QCheckBox::toggled,this,[this](bool enabled){for(auto*s:slices)s->setMask(enabled);});
  connect(airwayOverlay,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this](int i){int bit=airwayOverlay->itemData(i).toInt();for(auto*s:slices)s->setAirwayMask(bit);});
  connect(dualCheck,&QCheckBox::toggled,this,[this](bool enabled){if(enabled&&!scenePath.isEmpty()){miniOverview->loadScene(scenePath,scene);miniOverview->selectCandidate(lesion->value());miniOverview->setColorMode(colorMode->currentIndex());miniOverview->setAnalysisParameters(diameter->value(),margin->value());}miniOverview->setVisible(enabled);if(enabled)syncLinkedOverview();});
  connect(lesionList,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this]{updateCandidate();});overview->onCandidatePicked=[this](int index){int i=lesionList->findData(index);if(i>=0)lesionList->setCurrentIndex(i);};
  connect(minimumCandidateVolume,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this]{refreshCandidates();});connect(focusButton,&QPushButton::clicked,this,[this]{focusCandidate();});connect(diameter,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this]{updateAnalysis();});connect(margin,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this]{updateAnalysis();});connect(minimumBend,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this]{updateAnalysis();});
  connect(colorMode,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this](int i){overview->setColorMode(i);miniOverview->setColorMode(i);updateColorLegend();});
  auto clipping=[this]{overview->setClipping(clipCheck->isChecked(),clipAxis->currentIndex(),clipOffset->value()/100.f);};connect(clipCheck,&QCheckBox::toggled,this,[clipping]{clipping();});connect(clipAxis,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[clipping]{clipping();});connect(clipOffset,&QSlider::valueChanged,this,[clipping]{clipping();});connect(opacity,&QSlider::valueChanged,this,[this](int value){applyOverviewOpacity();});
  miniOverview->setReferenceCamera({});connect(cameraSlider,&QSlider::valueChanged,scope,&MeshView::setCamera);scope->onCamera=[this](int){syncNavigationControlsFromCamera();if(playing){playbackStart=scope->distance();playbackClock.restart();}};connect(resetScope,&QPushButton::clicked,scope,&MeshView::resetView);
  connect(playButton,&QPushButton::clicked,this,[this]{navigationToggle();});
  play.setTimerType(Qt::PreciseTimer);
  connect(&play,&QTimer::timeout,this,[this]{navigationTick();});
  connect(cameraSlider,&QSlider::valueChanged,this,[this]{navigationPosition->setText(QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,'f',1).arg(scope->totalDistance(),0,'f',1));if(playing){playbackStart=scope->distance();playbackClock.restart();}});
  connect(&navigationMotion,&QTimer::timeout,this,[this]{int phase=(navigationMotionClock.elapsed()/16)%48;cameraSlider->setValue(navigationBase+(phase<24?phase-12:36-phase));});
  connect(&rotation,&QTimer::timeout,this,[this]{overview->turn(.8f);});connect(overview,&QOpenGLWidget::frameSwapped,this,[this]{if(benchmarking){if(lungBenchmark)lungIntervals.append(swapClock.nsecsElapsed()/1.e6);else swapIntervals.append(swapClock.nsecsElapsed()/1.e6);swapClock.restart();}});
  overview->onBackend=scope->onBackend=[this](QString name){gpuLabel->setText(name.contains("Mali",Qt::CaseInsensitive)?u("Mali GPU"):name);};
  connect(openButton,&QPushButton::clicked,this,[this]{QString p=QFileDialog::getOpenFileName(this,u("选择 CT"),QFileInfo(input).absolutePath(),"CT (*.nrrd *.nii *.nii.gz *.mha *.mhd)");if(!p.isEmpty()){input=p;source.clear();prepare();}});
  connect(importButton,&QPushButton::clicked,this,[this]{QString path=externalTesting?qEnvironmentVariable("KV260_EXTERNAL_MANIFEST"):QFileDialog::getOpenFileName(this,u("选择外部掩膜 / 概率图清单"),QFileInfo(input).absolutePath(),"Image manifest (*.json)");if(!path.isEmpty())startUtility("import-external",{"--input",input,"--manifest",path});});
  connect(dicomButton,&QPushButton::clicked,this,[this]{QString path=dicomTesting?qEnvironmentVariable("KV260_DICOM_TEST_ROOT"):QFileDialog::getExistingDirectory(this,u("选择 DICOM 根目录（包含子目录）"),QFileInfo(input).absolutePath());if(!path.isEmpty())startUtility("dicom-series",{"--input",path});});
  connect(exportButton,&QPushButton::clicked,this,[this]{QString path=root+"/ui/exports/"+QDateTime::currentDateTime().toString("yyyyMMdd_HHmmss")+"_"+QUuid::createUuid().toString(QUuid::Id128).left(6);startUtility("export",{"--input",input,"--result",source,"--destination",path,"--minimum-candidate-volume",QString::number(minimumCandidateVolume->value(),'g',15)});});
  connect(compareButton,&QPushButton::clicked,this,[this]{startJob("comparison");});connect(comparisonResults,&QPushButton::clicked,this,[this]{showComparisons();});
  connect(&utilityProcess,&QProcess::readyReadStandardOutput,this,[this]{utilityBytes+=utilityProcess.readAllStandardOutput();});connect(&utilityProcess,&QProcess::readyReadStandardError,this,[this]{utilityError+=QString::fromUtf8(utilityProcess.readAllStandardError());});connect(&utilityProcess,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),this,[this](int code,QProcess::ExitStatus status){finishUtility(code,status);});
  connect(refreshButton,&QPushButton::clicked,this,[this]{prepare(results->currentData().toString());});connect(results,QOverload<int>::of(&QComboBox::activated),this,[this](int){prepare(results->currentData().toString());});
  connect(runButton,&QPushButton::clicked,this,[this]{startJob("all");});connect(rebuildButton,&QPushButton::clicked,this,[this]{startJob("reconstruction");});connect(navButton,&QPushButton::clicked,this,[this]{startJob("navigation");});connect(stopButton,&QPushButton::clicked,this,[this]{stopAfterStage();});
  for(auto*p:{&prepareProcess,&jobProcess,&utilityProcess}){p->setWorkingDirectory(root);auto env=QProcessEnvironment::systemEnvironment();env.remove("LD_PRELOAD");env.remove("QT_QPA_PLATFORM");env.insert("PYTHONUNBUFFERED","1");env.insert("PYTHONIOENCODING","utf-8");p->setProcessEnvironment(env);connect(p,&QProcess::readyReadStandardError,this,[this,p]{errors+=QString::fromUtf8(p->readAllStandardError());});connect(p,&QProcess::errorOccurred,this,[this,p](QProcess::ProcessError e){if(e==QProcess::FailedToStart){failed=true;message(p->errorString());busy(false);if(smoke)finishTest();}});}
  connect(&prepareProcess,&QProcess::readyReadStandardOutput,this,[this]{processLines(prepPending,prepareProcess.readAllStandardOutput());});connect(&jobProcess,&QProcess::readyReadStandardOutput,this,[this]{processLines(jobPending,jobProcess.readAllStandardOutput());});
  connect(&prepareProcess,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),this,[this](int rc,QProcess::ExitStatus){prepareSceneInBackground(rc);});
  connect(&jobProcess,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),this,[this](int rc,QProcess::ExitStatus){if(activeSurfaceJob){surfaceJobFinished(rc);return;}stopButton->setEnabled(false);if(rc){selectedTaskPending=false;failed=true;progress->setRange(0,100);progress->setValue(0);message(u("任务失败，保留日志：")+runOutput+"\n"+errors.right(1000));busy(false);if(qEnvironmentVariableIntValue("KV260_SELECTED_PATH_UI_TEST")==1){finishTest();}else if(qEnvironmentVariableIntValue("KV260_WHOLE_COMPARISON_UI_TEST")==1){QDir().mkpath(evidence);writeJson(evidence+"/whole_comparison_UI_failure.json",QJsonObject{{"error",errors},{"output",runOutput}});this->close();QApplication::exit(1);}else if(externalTesting)externalFinish(false,errors);else if(smoke)finishTest();}else if(!runOutput.isEmpty()){record("job_finished");prepare(runOutput);}else busy(false);if(!stopFile.isEmpty())QFile::remove(stopFile);});
  beatClock.start();taskClock.start();qint64 last=0;connect(&heartbeat,&QTimer::timeout,this,[this,last]()mutable{lastTick=monoMs();qint64 now=beatClock.elapsed();gaps.append(now-last);if(now-last>200)actions.append(QJsonObject{{"action","heartbeat_stall"},{"gap_ms",double(now-last)},{"elapsed_ms",double(now)},{"dfx_active",jobProcess.state()!=QProcess::NotRunning}});last=now;++ticks;clock->setText(QTime::currentTime().toString("HH:mm:ss"));if(jobProcess.state()!=QProcess::NotRunning){jobGaps.append(gaps.last());elapsed->setText(u("后台运行：")+QString::number(taskClock.elapsed()/1000)+u(" 秒"));if(smoke&&ticks%8==0){tabs->setCurrentIndex((ticks/8)%3);axialSlider->setValue((axialSlider->value()+1)%(axialSlider->maximum()+1));overview->turn(2);record("interaction_during_dfx");}}if(exitRequested&&(videoPending||videoRunning))videoCancel();if(exitRequested&&!processing())this->close();});heartbeat.start(50);
  setStyleSheet("QWidget{background:#0b1623;color:#dce8f5;font-family:'Noto Sans CJK SC';font-size:12px;} QLabel#title{font-size:19px;font-weight:700;color:#f0f7ff;} QLabel#section{color:#51d6c1;font-size:14px;font-weight:600;} QLabel#muted{color:#8296ae;font-size:11px;} QWidget#sidebar{background:#112131;border-radius:9px;} QPushButton{background:#20364b;border:1px solid #2b455e;border-radius:5px;padding:5px 9px;} QPushButton:hover{background:#2b4e68;} QPushButton:pressed{background:#396b83;} QPushButton:disabled{color:#536778;background:#142331;} QPushButton#primary{background:#0b897c;color:white;border:1px solid #20b9a5;font-weight:600;} QTabWidget::pane{border:1px solid #233b51;} QTabBar::tab{padding:10px 20px;background:#112131;color:#91a6bb;} QTabBar::tab:selected{background:#20394e;color:#65ead4;border-bottom:2px solid #3dd8be;} QComboBox,QSpinBox,QDoubleSpinBox{background:#0a1723;border:1px solid #2d455b;border-radius:4px;padding:5px;} QComboBox QAbstractItemView{selection-background-color:#1e6d69;} QProgressBar{background:#20354a;border:none;} QProgressBar::chunk{background:#35cbb1;} QPlainTextEdit{background:#07121c;border:1px solid #21354a;color:#93abc0;font-size:11px;} QLabel#notice{background:#3a3020;color:#ffdc89;padding:8px;border-radius:4px;} QSlider::groove:horizontal{height:5px;background:#294158;} QSlider::handle:horizontal{background:#4dddc1;width:13px;margin:-5px 0;border-radius:6px;} QCheckBox{spacing:5px;} QCheckBox::indicator{width:15px;height:15px;} QCheckBox:disabled{color:#8da0b4;} QCheckBox::indicator:disabled{background:#182736;border:1px solid #506074;border-radius:3px;} QLabel#structureAvailability{background:#14283b;color:#b7d6eb;padding:8px;border:1px solid #2c4a60;border-radius:4px;}");
  plScope=new PlScope(root,this);plScope->setQuality(navQuality);plScope->onFrame=[this](QImage frame,QImage normals,QJsonObject meta){batchFrameReceived(frame,normals,meta);videoFrameReceived(frame,normals,meta);++plFrames;plLastFrame=meta;scope->setPlFrame(frame,normals,meta);scopePerf->setText(QString("%1 · %2 × %3 · %4 ms").arg(meta["interactive"].toBool()?u("交互画面"):u("精细画面")).arg(meta["width"].toInt()).arg(meta["height"].toInt()).arg(meta["round_trip_ms"].toDouble(),0,'f',0));if(navigationTrace.size()>=400)navigationTrace.removeFirst();auto trace=meta;trace["ui_received_ms"]=double(beatClock.elapsed());navigationTrace.append(trace);};plScope->onStatus=[this](QString text){scope->setScopeStatus(text);};scope->onPoseChanged=[this]{syncNavigationControlsFromCamera();if(plScope->active()&&!processing())plScope->request(scope->cameraRequest());};
  scope->onPlPresented=[this](int){syncLinkedOverview();batchPresented();videoPresented();if(linkedTesting&&dualCheck->isChecked())linkedRecordFrame();if(navigationBenchmarking&&navigationMotionClock.elapsed()>1000)navigationPresented.append(navigationMotionClock.elapsed());};
  connect(&compositeCheck,&QTimer::timeout,this,[this]{compositeAdvance();});
  plComposite=new PlComposite(root,this);
  plComposite->onFrame=[this](QImage frame,QJsonObject meta){
   breathingWaiting=false;
   if(!overview->compositeMode())return;
   if(fastTransparency->isChecked()&&!transparentFrameMatches(meta,overview->overviewRequest())){++previewStaleFrames;return;}
   if(transparentInteractionTesting)transparentLastPixels=QByteArray(reinterpret_cast<const char*>(frame.constBits()),frame.sizeInBytes());
   overview->setCompositePreview(false);if(!overview->setCompositeFrame(frame,meta)){failed=true;message(u("完成帧的相机矩阵无效，保留上一张画面"));return;}
   ++compositeFrames;if(compositeTesting){QDir().mkpath(evidence);QSaveFile raw(evidence+"/frame_"+QString::number(compositeFrames)+".rgba");if(!raw.open(QIODevice::WriteOnly)||raw.write(reinterpret_cast<const char*>(frame.constBits()),frame.sizeInBytes())!=frame.sizeInBytes()||!raw.commit())failed=true;}auto report=meta["report"].toObject();compositePerf->setText(QString(u("PL 合成 · %1 × %2 · 本帧 %3 秒")).arg(frame.width()).arg(frame.height()).arg(meta["round_trip_seconds"].toDouble(),0,'f',2));
   auto trace=meta;trace["ui_received_ms"]=double(beatClock.elapsed());trace["UI_frame_index"]=compositeFrames;if(compositeTrace.size()>=100)compositeTrace.removeFirst();compositeTrace.append(trace);
  };
  plComposite->onStatus=[this](QString text){if(overview->compositeMode()){overview->setCompositeStatus(text);compositePerf->setText(text);}};
  compositeQuiet.setSingleShot(true);compositeQuiet.setTimerType(Qt::PreciseTimer);
  connect(&compositeQuiet,&QTimer::timeout,this,[this]{if(closing||finishingTest||processing()||tabs->currentIndex()!=1||!overview->compositeMode()||!fastTransparency->isChecked())return;++previewQuietRequests;configureScope();});
  overview->onOverviewChanged=[this]{if(settingStructure||!overview->compositeMode()||processing()||tabs->currentIndex()!=1)return;if(fastTransparency->isChecked()){overview->setCompositePreview(true);compositePerf->setText(u("交互预览 · 停止操作后生成精确透明画面"));compositeQuiet.start(450);}else if(plComposite->active()){overview->setCompositeStatus(u("正在计算新视角，显示上一张完成画面"));plComposite->request(overview->overviewRequest());}};
  connect(&transparentTestCheck,&QTimer::timeout,this,[this]{transparentTestAdvance();});
  connect(&transparentTestMotion,&QTimer::timeout,this,[this]{transparentMotionAdvance();});
  connect(overview,&QOpenGLWidget::frameSwapped,this,[this]{if(transparentMoving&&overview->compositePreviewMode())transparentSwapTimes.append(transparentMotionClock.nsecsElapsed()/1.e6);});
  connect(tabs,&QTabWidget::currentChanged,this,[this](int i){breathingWaiting=false;syncBreathing();if(i!=2){play.stop();playing=false;playButton->setText(u("沿路径播放"));scope->setPlayback(false);}configureScope();});
  busy(true);QTimer::singleShot(150,this,[this]{prepare();});
 }
public:
 ~MainWindow(){if(sceneLoader.joinable())sceneLoader.join();if(videoIntegrityThread.joinable())videoIntegrityThread.join();}
protected:
 void closeEvent(QCloseEvent*e)override{if(batchRunning){batchCancelled=true;writeJson(batchDirectory+"/cancel",{});e->ignore();return;}if(videoPending||videoRunning){videoCancel();e->ignore();return;}if(processing()){message(u("任务仍在运行。可停止后续步骤，当前阶段完成后再退出。"));e->ignore();return;}play.stop();if((plScope&&plScope->active())||(plComposite&&plComposite->active())){e->ignore();if(!closing){closing=true;releaseGraphics([this]{close();});}return;}e->accept();}
};

int main(int argc,char**argv){
 QSurfaceFormat f;f.setRenderableType(QSurfaceFormat::OpenGLES);f.setVersion(2,0);f.setDepthBufferSize(24);f.setStencilBufferSize(8);f.setSwapInterval(1);QSurfaceFormat::setDefaultFormat(f);
 QApplication::setAttribute(Qt::AA_ShareOpenGLContexts);QApplication app(argc,argv);app.setFont(QFont("Noto Sans CJK SC",10));
 QCommandLineParser p;p.addHelpOption();p.addOptions({{"root","Integrated project root","path"},{"input","Raw CT file","path"},{"smoke","Run actual UI smoke test"},{"acceptance-run","Run a real DFX case while interacting with the UI"},{"navigation-test","Measure navigation updates, auto alignment and quiet-frame refinement"},{"feature-test","Validate catalogue, focus, surface modes and clipping"},{"evidence","Test output directory","path"},{"navigation-quality","Navigation viewport: 0 clear, 1 balanced, 2 fast","level","0"}});p.process(app);
 QString root=p.value("root");if(root.isEmpty())root=QDir(QCoreApplication::applicationDirPath()+"/../..").absolutePath();QString input=p.value("input");if(input.isEmpty())input=root+"/fixtures/own_ct/CT-chest.nrrd";QString evidence=p.value("evidence");if(evidence.isEmpty())evidence=root+"/ui/docs/smoke";
 signal(SIGTERM,handleSignal);signal(SIGINT,handleSignal);
 bool qualityOk=false;int navQuality=p.value("navigation-quality").toInt(&qualityOk);if(!qualityOk||navQuality<0||navQuality>2){qCritical()<<"Invalid navigation quality";return 2;}
 try{MainWindow window(root,input,p.isSet("smoke")||p.isSet("acceptance-run")||p.isSet("navigation-test")||p.isSet("feature-test"),p.isSet("acceptance-run"),p.isSet("navigation-test"),evidence,navQuality,p.isSet("feature-test"));window.show();return app.exec();}catch(const std::exception&e){qCritical()<<e.what();return 1;}
}
