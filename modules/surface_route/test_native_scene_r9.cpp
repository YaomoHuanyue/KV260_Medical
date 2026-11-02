#include "../../ui/releases/feature_completion_r6/src/views_batch_r3.hpp"
#include "scope_protocol_r9.hpp"
#include <QApplication>
#include <QFile>
#include <stdexcept>

static void require(bool ok,const char*message){if(!ok)throw std::runtime_error(message);}
static QJsonObject read(const QString&path){QFile f(path);require(f.open(QIODevice::ReadOnly),"JSON open failed");return QJsonDocument::fromJson(f.readAll()).object();}
int main(int argc,char**argv){
 QApplication app(argc,argv);
 try{
  require(argc==4,"Usage: test_native_scene index.json frame_tests.json output.json");
  auto index=read(argv[1]),protocol=read(argv[2]);QJsonArray cases,checks,requests;
  MeshView view;view.resize(640,363);view.setScope(true);
  for(auto value:index["cases"].toArray()){
   auto c=value.toObject();QString path=c["scene"].toString();auto scene=read(path);
   view.loadScene(path,scene);view.setScope(true);
   auto nav=scene["navigation"].toObject();int count=nav["positions"].toArray().size();
   require(view.cameraCount()==count,"Qt camera and new route count mismatch");
   require(view.featureMetrics()["hud_samples"].toInt()==nav["hud"].toObject()["samples"].toArray().size(),"Qt HUD mismatch");
   require(!nav.contains("instrument_profiles")&&!nav.contains("alternative_routes"),"Old route comparisons leaked");
   if(count){for(float distance:{0.f,view.totalDistance()*.5f,view.totalDistance()}){
     view.setDistance(distance);auto pose=view.cameraRequest();pose["revision"]=scene["complete_surface"].toObject()["revision"];
     pose["sequence"]=requests.size()+1;requests.append(QJsonObject{{"bundle",scene["complete_surface"].toObject()["bundle"]},{"request",pose}});
    }
    view.setDistance(view.totalDistance());auto pose=view.cameraRequest();
    require(!pose.isEmpty()&&std::abs(pose["arc_mm"].toDouble()-nav["arc"].toArray().last().toDouble())<1e-4,"Qt endpoint progress mismatch");
   }else require(view.cameraRequest().isEmpty(),"Root-only route acquired camera");
   // Each replacement is explicit; repeat same scene to catch stale route/HUD state.
   view.loadScene(path,scene);require(view.cameraCount()==count,"Repeated scene changed camera count");
   cases.append(QJsonObject{{"scene",path},{"revision",scene["complete_surface"].toObject()["revision"]},
    {"camera_count",count},{"hud_count",view.featureMetrics()["hud_samples"]}});
  }
  auto revision=protocol["revision"].toString();
  require(CompleteScopeProtocol::ready({{"revision",revision},{"atomic_scene_activation_required",true},{"automatic_quality_changes",false}},revision),"Complete ready rejected");
  require(!CompleteScopeProtocol::ready({{"revision","wrong"},{"atomic_scene_activation_required",true}},revision),"Wrong ready accepted");
  for(auto value:protocol["requests"].toArray()){
   auto request=value.toObject()["request"].toObject(),frame=value.toObject()["frame"].toObject();
   QString scalar=frame["renderer_scalar_sha256"].toString(),path=frame["path"].toString();
   require(CompleteScopeProtocol::frame(frame,request,revision,scalar,path),"Completed actual pose rejected");
   for(QString key:{"revision","renderer_scalar_sha256","normal_backend","normal_frame_path","pose_source"}){
    auto bad=frame;bad[key]="wrong";require(!CompleteScopeProtocol::frame(bad,request,revision,scalar,path),"Wrong identity accepted");
    checks.append(key+"_rejected");
   }
   auto bad=frame;bad["sequence"]=999;require(!CompleteScopeProtocol::frame(bad,request,revision,scalar,path),"Wrong sequence accepted");
   bad=frame;bad["camera_lps"]=QJsonArray{0.,0.,0.};require(!CompleteScopeProtocol::frame(bad,request,revision,scalar,path),"Wrong camera accepted");
   bad=frame;bad["width"]=384;require(!CompleteScopeProtocol::frame(bad,request,revision,scalar,path),"Wrong viewport accepted");
  }
  QJsonObject report{{"status","actual_ARM_Qt_complete_scene_load_and_pose_protocol_passed"},
   {"cases",cases},{"protocol_rejections",checks},{"native_requests",requests},
   {"PL_access",false},{"rendered_visual_or_FPS_claim",false}};
  QFile output(argv[3]);require(output.open(QIODevice::WriteOnly|QIODevice::NewOnly),"New output required");
  output.write(QJsonDocument(report).toJson());qInfo()<<"Native Qt cases"<<cases.size();return 0;
 }catch(const std::exception&e){qCritical()<<e.what();return 1;}
}
