#pragma once
#include <QCheckBox>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QPushButton>
#include <QStringList>

namespace structure_availability {
inline QString text(const char* value){return QString::fromUtf8(value);}
inline QString name(const QString& key){
 return key=="lung"?text("肺"):key=="airway"?text("气道"):text("病灶候选");
}
struct State {QString label,status,reason;bool ready=false;};
inline State describe(const QJsonObject& scene,const QString& key){
 const auto meshes=scene["meshes"].toObject();const auto mesh=meshes[key].toObject();
 const bool provided=scene["available_structures"].toArray().contains(key)||
  (!scene.contains("available_structures")&&meshes.contains(key));
 State state;const auto title=name(key);state.label=key=="lung"?text("肺（半透明）"):title;
 if(!provided){
  const bool raw=scene["result"].toString().isEmpty()&&scene["source"]=="raw_ct";
  state.status=raw?text("尚未分割"):text("未提供");
  state.reason=raw?text("当前仅载入 CT；请先运行分割或导入掩膜。"):
   text("本次结果未提供")+title+text("掩膜；导入对应掩膜后才能重建和显示。");
 }else if(!mesh["file"].toString().isEmpty()&&mesh["vertices"].toInt()>0&&mesh["triangles"].toInt()>0){
  state.ready=true;state.status=text("可显示");state.reason=title+text("三维模型已生成，可勾选显示或隐藏。");
 }else{
  const auto counts=scene["structure_foreground_voxels"].toObject();
  if(counts.contains(key)&&counts[key].toDouble()==0){
   state.status=text("掩膜为空");state.reason=title+text("掩膜已提供，但没有前景体素，无法生成三维表面。");
  }else if(meshes.contains(key)){
   state.status=text("无可显示表面");state.reason=title+text("掩膜已提供，但当前重建没有可显示的三角形。");
  }else{
   state.status=text("尚未重建");state.reason=title+text("掩膜已提供；请点击左侧“重新重建 / 平滑”生成三维模型。");
  }
 }
 if(!state.ready)state.label+=text(" · ")+state.status;
 return state;
}
inline void apply(const QJsonObject& scene,QCheckBox* const* layers,QPushButton* const* presets,QLabel* note){
 const char* keys[]={"lung","airway","nodule"};QStringList descriptions;bool visible=false,any=false;
 State states[3];
 for(int i=0;i<3;++i){
  states[i]=describe(scene,keys[i]);auto* box=layers[i];
  box->setText(states[i].label);box->setEnabled(states[i].ready);
  box->setToolTip(states[i].reason);box->setAccessibleDescription(states[i].reason);
  box->setProperty("structureStatus",states[i].status);
  if(!states[i].ready)box->setChecked(false);
  visible|=states[i].ready&&box->isChecked();any|=states[i].ready;
  descriptions<<name(keys[i])+text("：")+states[i].status;
 }
 if(!visible)for(int i=0;i<3;++i)if(states[i].ready){layers[i]->setChecked(true);break;}
 const QString base[]={text("只看肺"),text("只看支气管")};
 for(int i=0;i<2;++i){
  presets[i]->setEnabled(states[i].ready);
  presets[i]->setText(base[i]+(states[i].ready?QString():text(" · ")+states[i].status));
  presets[i]->setToolTip(states[i].reason);presets[i]->setAccessibleDescription(states[i].reason);
 }
 presets[2]->setEnabled(any);presets[2]->setText(any?text("恢复组合"):text("恢复组合 · 无可显示模型"));
 presets[2]->setToolTip(any?text("恢复已生成结构的组合显示。"):text("请先重建已提供的结构。"));
 note->setText(descriptions.join(text("　｜　")));note->setWordWrap(true);
 note->setAccessibleDescription(note->text());
}
}
