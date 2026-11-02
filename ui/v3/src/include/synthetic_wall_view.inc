// The first-hit depth and normals come from PL. GPU material uses reference
// labels; camera-relative coordinates preserve mediump precision and cropping.
static QJsonObject wallRead(const QString&name){QFile f(name);if(!f.open(QIODevice::ReadOnly))return {};return QJsonDocument::fromJson(f.readAll()).object();}
static void loadSyntheticWall(QObject*view,const QJsonObject&scene){
 view->setProperty("synthetic_wall_active",false);view->setProperty("wall_count",0);
 auto truth=wallRead(QFileInfo(scene["input"].toString()).dir().filePath("synthetic_case.json"));
 auto seg=wallRead(scene["result"].toString()+"/segmentation/report.json");auto provenance=seg["provenance"].toObject();
 if((truth["schema"]!="kv260.synthetic.wall_lesion.v1"&&truth["schema"]!="kv260.synthetic.wall_lesion.v2")||truth["ct_sha256"]!=scene["input_sha256"]||!provenance["synthetic"].toBool()||!provenance["reference_ground_truth"].toBool()||provenance["model_inference"].toBool())return;
 auto geometry=scene["geometry"].toObject();auto spacing=geometry["spacing_xyz"].toArray(),direction=geometry["direction"].toArray();if(spacing.size()!=3||direction.size()!=9)return;
 auto origin=vec(geometry["origin_lps_mm"]);QMatrix4x4 transform;for(int i=0;i<3;++i){transform(i,3)=origin[i];for(int k=0;k<3;++k)transform(i,k)=direction[i*3+k].toDouble()*spacing[k].toDouble();}
 bool valid=false;auto inverse=transform.inverted(&valid);if(!valid)return;
 QJsonArray lesions=truth["lesions"].toArray();if(lesions.isEmpty())lesions.append(truth);if(lesions.size()>6)return;
 auto nav=scene["navigation"].toObject(),report=nav["report"].toObject();int target=report["target"].toObject()["index"].toInt(0);QVariantList centers,metrics[3];QVector3D selected;bool haveSelected=false;
 for(auto value:lesions){auto lesion=value.toObject();auto center=lesion["center_lps_mm"].toArray(),radii=lesion["ellipsoid_radii_mm"].toArray(),axes=lesion["ellipsoid_axes_lps"].toArray();if(center.size()!=3||radii.size()!=3||axes.size()!=3)return;
  for(auto a:axes)if(a.toArray().size()!=3)return;
  QVector3D physical=vec(center);centers.append(QVariant::fromValue(inverse.map(physical)));
  for(int j=0;j<3;++j){double radius=radii[j].toDouble()+.4;if(radius<=.4)return;QVector3D coefficient;for(int k=0;k<3;++k){double v=0;for(int i=0;i<3;++i)v+=axes[i].toArray()[j].toDouble()*direction[i*3+k].toDouble()*spacing[k].toDouble()/radius;coefficient[k]=v;}metrics[j].append(QVariant::fromValue(coefficient));}
  if(lesion["candidate_index"].toInt(0)==target){selected=physical;haveSelected=true;}
 }
 view->setProperty("wall_inverse",QVariant::fromValue(inverse));view->setProperty("wall_centers",centers);for(int j=0;j<3;++j)view->setProperty(qPrintable(QString("wall_metrics%1").arg(j)),metrics[j]);view->setProperty("wall_count",lesions.size());
 auto arcs=nav["arc"].toArray();if(haveSelected&&!arcs.isEmpty()&&report["status"]=="airway_approach"){
  view->setProperty("synthetic_wall_center",QVariant::fromValue(selected));view->setProperty("synthetic_wall_total",arcs.last().toDouble());view->setProperty("synthetic_wall_active",true);
 }
}
static void applyWallUniforms(const QObject*view,QOpenGLShaderProgram&shader,const QJsonObject&frame){
 int count=view->property("wall_count").toInt();QVector3D centers[6],m0[6],m1[6],m2[6];
 auto camera=view->property("wall_inverse").value<QMatrix4x4>().map(vec(frame["camera_lps"]));auto stored=view->property("wall_centers").toList();auto a=view->property("wall_metrics0").toList(),b=view->property("wall_metrics1").toList(),c=view->property("wall_metrics2").toList();
 if(count>stored.size()||count>a.size()||count>b.size()||count>c.size())count=0;
 for(int i=0;i<count;++i){centers[i]=stored[i].value<QVector3D>()-camera;m0[i]=a[i].value<QVector3D>();m1[i]=b[i].value<QVector3D>();m2[i]=c[i].value<QVector3D>();}
 shader.setUniformValue("wallCount",float(count));shader.setUniformValueArray("wallCenter[0]",centers,6);shader.setUniformValueArray("wallMetric0[0]",m0,6);shader.setUniformValueArray("wallMetric1[0]",m1,6);shader.setUniformValueArray("wallMetric2[0]",m2,6);
}
static void syntheticWallDirection(const QObject*view,QVector3D eye,float arc,float total,QVector3D&forward,QVector3D&up){
 if(!view->property("synthetic_wall_active").toBool())return;
 auto toward=view->property("synthetic_wall_center").value<QVector3D>()-eye;if(toward.lengthSquared()<.01f)return;
 float t=qBound(0.f,1.f-(total-arc)/12.f,1.f);t=t*t*(3.f-2.f*t);
 auto next=forward*(1.f-t)+toward.normalized()*t;if(next.lengthSquared()<.01f)return;forward=next.normalized();
 auto right=QVector3D::crossProduct(forward,up);if(right.lengthSquared()<.001f)right=QVector3D::crossProduct(forward,QVector3D(1,0,0));
 if(right.lengthSquared()<.001f)right=QVector3D::crossProduct(forward,QVector3D(0,1,0));up=QVector3D::crossProduct(right.normalized(),forward).normalized();
}
static void drawSyntheticWall(const QObject*view,QPainter&p,QSize size,const QJsonObject&frame){
 if(!view->property("synthetic_wall_active").toBool()||frame.isEmpty())return;
 auto request=frame["requested_camera"].toObject();if(view->property("synthetic_wall_total").toDouble()-request["arc_mm"].toDouble()>1.)return;
 auto v=view->property("synthetic_wall_center").value<QVector3D>()-vec(frame["camera_lps"]);
 double z=QVector3D::dotProduct(v,vec(frame["forward_lps"])),field=frame["field"].toDouble();int w=frame["width"].toInt(),h=frame["height"].toInt();
 if(z<=0||field<=0||w<=0||h<=0)return;
 double x=QVector3D::dotProduct(v,vec(frame["right_lps"]))/z/field*h/w,y=QVector3D::dotProduct(v,vec(frame["up_lps"]))/z/field;
 // Mark only a target within the completed frame; never clamp an off-screen target.
 if(std::abs(x)>.88||std::abs(y)>.78)return;
 QSize fit(w,h);fit.scale(size,Qt::KeepAspectRatio);QPointF q((size.width()-fit.width())/2.+(x+1)*fit.width()/2.,(size.height()-fit.height())/2.+(1-y)*fit.height()/2.);
 {p.save();QFont f=p.font();f.setPixelSize(11);p.setFont(f);QString t=QString::fromUtf8("红色区域 · 模拟病灶管壁");QRectF chip(12,size.height()-34,p.fontMetrics().horizontalAdvance(t)+18,20);p.setRenderHint(QPainter::Antialiasing);p.setPen(Qt::NoPen);p.setBrush(QColor(11,13,16,190));p.drawRoundedRect(chip,10,10);p.setPen(QColor("#ff8c83"));p.drawText(chip,Qt::AlignCenter,t);p.restore();}
 p.save();p.setRenderHint(QPainter::Antialiasing);p.setBrush(Qt::NoBrush);p.setPen(QPen(QColor("#07121c"),7));p.drawEllipse(q,19,19);p.setPen(QPen(QColor("#ffdf55"),3));p.drawEllipse(q,19,19);
 {QFont f=p.font();f.setPixelSize(11);p.setFont(f);QString t=QString::fromUtf8("模拟管壁病灶 · 位置提示");QRectF label(q.x()-(p.fontMetrics().horizontalAdvance(t)+20)/2.,q.y()+30,p.fontMetrics().horizontalAdvance(t)+20,22);p.setPen(Qt::NoPen);p.setBrush(QColor(11,13,16,215));p.drawRoundedRect(label,11,11);p.setPen(QColor("#ffdf55"));p.drawText(label,Qt::AlignCenter,t);}p.restore();
}
