#pragma once
#include <QtCore>
#include <functional>
#include <stdexcept>

namespace navigation_media {
inline QJsonObject mediaObject(QString path){
 QFile file(path);if(!file.open(QIODevice::ReadOnly))throw std::runtime_error("Cannot read active video binding");
 auto document=QJsonDocument::fromJson(file.readAll());if(!document.isObject())throw std::runtime_error("Invalid active video JSON");
 return document.object();
}
inline bool sameSavedVideoScene(const QJsonObject&saved,const QJsonObject&displayed,QStringList*extraNulls=nullptr){
 // QJsonObject non-const operator[] inserts null for a missing read. Only
 // these additional top-level nulls are ignored; all saved values stay exact.
 for(auto it=saved.begin();it!=saved.end();++it)
  if(!displayed.contains(it.key())||displayed.value(it.key())!=it.value())return false;
 for(auto it=displayed.begin();it!=displayed.end();++it)if(!saved.contains(it.key())){
  if(!it.value().isNull())return false;
  if(extraNulls)extraNulls->append(it.key());
 }
 return true;
}
// The UI scene has already passed the full prepared/bundle geometry verifier.
// Pin its complete dependency set again before export, then recheck at commit.
inline QJsonObject activeVideoBinding(QString root,QString scenePath,QJsonObject scene,
      QJsonObject&hashes,std::function<QString(QString)> hash){
 QString canonicalRoot=QFileInfo(root).canonicalFilePath();
 auto pin=[&](QString path,QString expected=QString()){
  if(!QFileInfo(path).isAbsolute())path=QDir(root).absoluteFilePath(path);
  const QString requested=path;path=QFileInfo(path).canonicalFilePath();
  if(canonicalRoot.isEmpty()||!path.startsWith(canonicalRoot+"/")||!QFileInfo(path).isFile())
   throw std::runtime_error(("Required video source unavailable or outside active project: "+requested).toStdString());
  QString value=hash(path);
  if(value.size()!=64||(!expected.isEmpty()&&(expected.size()!=64||value!=expected)))
   throw std::runtime_error("Changed active video source");
  if(hashes.contains(path)&&hashes[path]!=value)throw std::runtime_error("Mixed active video source");
  hashes[path]=value;return path;
 };
 auto complete=scene["complete_surface"].toObject();
 if(complete.isEmpty())throw std::runtime_error("Complete video scene required");
 QStringList extraNulls;if(!sameSavedVideoScene(mediaObject(scenePath),scene,&extraNulls))throw std::runtime_error("Displayed and saved video scene differ");
 QString folder=QFileInfo(scenePath).absolutePath(),bundle=complete["bundle"].toString();
 auto prepared=mediaObject(folder+"/prepared.json"),meta=mediaObject(bundle+"/scene.json");
 if(prepared["schema"]!="kv260.ui.complete_surface.prepared.v1"||
    prepared["revision"]!=complete["revision"]||prepared["input_sha256"]!=scene["input_sha256"]||
    prepared["bundle"]!=complete["bundle"]||complete["source_result"]!=scene["result"]||
    meta["schema"]!="kv260.surface_route.complete_scene.v1"||!meta["complete"].toBool()||
    meta["revision"]!=complete["revision"]||meta["route_id"]!=complete["route_id"]||
    meta["renderer_scalar_sha256"]!=complete["scalar_sha256"])
  throw std::runtime_error("Mixed current video surface, path or CT");
 pin(folder+"/prepared.json");
 auto outputs=prepared["output_sha256"].toObject();
 if(!outputs.contains("scene.json")||!outputs.contains("airway.attributes"))throw std::runtime_error("Missing prepared video outputs");
 for(auto it=outputs.begin();it!=outputs.end();++it){
  if(it.key()!="scene.json"&&it.key()!="airway.attributes")throw std::runtime_error("Unknown prepared video output");
  pin(folder+"/"+it.key(),it.value().toString());
 }
 pin(scene["input"].toString(),scene["input_sha256"].toString());
 pin(bundle+"/scene.json",prepared["bundle_sha256"].toString());
 pin(bundle+"/airway.vertices",prepared["airway_vertices_sha256"].toString());
 auto identity=meta["identity"].toObject(),files=identity["files_sha256"].toObject();
 for(auto it=files.begin();it!=files.end();++it)pin(bundle+"/"+it.key(),it.value().toString());
 for(auto key:{"case_files_sha256","retained_assets_sha256"}){
  auto map=prepared[key].toObject();if(map.isEmpty())throw std::runtime_error("Missing active video input bindings");
  for(auto it=map.begin();it!=map.end();++it)pin(it.key(),it.value().toString());
 }
 auto provenance=identity["provenance"].toObject()["input_sha256"].toObject();
 if(provenance.isEmpty())throw std::runtime_error("Missing current surface provenance");
 QJsonArray provenanceAudit;int unavailableHistory=0;
 // The sealed bundle manifest already pins every runtime bundle file. Older
 // builders also placed entire experiment sweeps in provenance. Those are
 // reproducibility records, not files read by a video or image export.
 for(auto it=provenance.begin();it!=provenance.end();++it){
  QString expected=it.value().toString();
  if(!QRegularExpression("^[0-9a-f]{64}$").match(expected).hasMatch())throw std::runtime_error("Invalid sealed historical source hash");
  QString absolute=QFileInfo(it.key()).isAbsolute()?it.key():QDir(root).absoluteFilePath(it.key());
  QString canonical=QFileInfo(absolute).canonicalFilePath();
  bool available=!canonical.isEmpty()&&canonical.startsWith(canonicalRoot+"/")&&QFileInfo(canonical).isFile();
  if(available)pin(absolute,expected);else ++unavailableHistory;
  provenanceAudit.append(QJsonObject{{"declared_source",it.key()},{"declared_SHA256",expected},
    {"role",available&&hashes.contains(canonical)?"runtime_or_available_history":"sealed_build_history"},
    {"live_file_hash_verified",available},{"unavailable_history_is_not_runtime_fallback",!available}});
 }
 auto quality=complete["quality"].toObject();
 if(!quality.isEmpty()){
  if(quality!=prepared["active_quality"].toObject())throw std::runtime_error("Mixed active video quality");
  pin(quality["receipt"].toString(),quality["receipt_sha256"].toString());
  auto proof=mediaObject(quality["receipt"].toString());
  if(proof["input_sha256"]!=scene["input_sha256"]||proof["source"]!=quality["source"]||proof["tier"]!=quality["tier"])
   throw std::runtime_error("Video quality belongs to another case");
  pin(proof["field"].toString(),proof["field_sha256"].toString());
 }
 auto recovery=scene["distal_recovery_binding"].toObject();
 if(!recovery.isEmpty()){
  pin(recovery["report"].toString(),recovery["report_sha256"].toString());
  auto outputs=recovery["outputs_sha256"].toObject();if(outputs.size()!=4)throw std::runtime_error("Invalid recovery review outputs");
  for(auto it=outputs.begin();it!=outputs.end();++it)pin(it.key(),it.value().toString());
  auto review=scene["distal_recovery"].toObject();auto inputs=review["inputs_sha256"].toObject();
  for(auto it=inputs.begin();it!=inputs.end();++it)pin(it.key(),it.value().toString());
 }
 pin(root+"/dfx/surface_quality/release/manifest.json");
 return {{"bundle",bundle},{"revision",complete["revision"]},{"route_id",complete["route_id"]},
   {"scalar_sha256",complete["scalar_sha256"]},{"input_sha256",scene["input_sha256"]},
   {"source_result",scene["result"]},{"topology_backend","PL_C1_binary_Marching_Cubes"},
   {"render_backend","PL_C9"},{"extra_UI_null_keys",QJsonArray::fromStringList(extraNulls)},{"quality",quality},{"full_dependencies_pinned",true},
   {"dependency_pin_scope","required_runtime_and_available_history"},{"runtime_dependencies_fully_pinned",true},
   {"sealed_bundle_metadata_pinned",true},{"historical_sources",provenanceAudit},{"unavailable_historical_sources",unavailableHistory}};
}
inline bool activeVideoFrame(const QJsonObject&binding,const QJsonObject&frame){
 return frame["revision"]==binding["revision"]&&frame["renderer_scalar_sha256"]==binding["scalar_sha256"]&&
  frame["pl_module"]=="surface_quality"&&frame["normal_backend"]=="PL_C9"&&
  frame["pose_source"]=="completed_PL_frame"&&frame["normal_computation"]=="PL";
}
}
