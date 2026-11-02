#pragma once
#include <QJsonObject>
#include <QJsonArray>
#include <QString>
#include <QVector3D>
#include <cmath>
#include "../../ui/releases/feature_completion_r6/src/scope_reference.hpp"

// Explicit complete-scene protocol; the legacy worker is never guessed here.
namespace CompleteScopeProtocol {
inline bool ready(const QJsonObject&o,const QString&revision){
 return o["revision"].toString()==revision && o["atomic_scene_activation_required"].toBool()
     && !o["automatic_quality_changes"].toBool(true);
}
inline bool frame(const QJsonObject&o,const QJsonObject&sent,const QString&revision,
                  const QString&scalar,const QString&path){
 if(o["revision"].toString()!=revision || o["renderer_scalar_sha256"].toString()!=scalar
    || o["sequence"].toInt(-1)!=sent["sequence"].toInt(-2)
    || o["width"].toInt()!=sent["width"].toInt() || o["height"].toInt()!=sent["height"].toInt()
    || o["path"].toString()!=path || o["normal_frame_path"].toString()!=path+".normal.rgba"
    || o["normal_computation"].toString()!="PL" || o["normal_backend"].toString()!="PL_C9")return false;
 auto actual=ScopeReference::fromFrame(o);QVector3D eye,f,u;
 if(!actual.valid || !ScopeReference::vector(sent["camera"],eye)
    || !ScopeReference::vector(sent["forward"],f) || !ScopeReference::vector(sent["up"],u)
    || f.lengthSquared()<.5f || u.lengthSquared()<.5f)return false;
 f.normalize();u-=f*QVector3D::dotProduct(f,u);u.normalize();
 return (actual.eye-eye).length()<=1e-4f && (actual.forward-f).length()<=1e-5f
     && (actual.up-u).length()<=1e-5f && sent["arc_mm"].isDouble()
     && std::isfinite(sent["arc_mm"].toDouble())
     && std::abs(o["arc_mm"].toDouble()-sent["arc_mm"].toDouble())<=1e-4;
}
}
