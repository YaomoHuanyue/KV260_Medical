#pragma once
#include <QtWidgets>
#include <cmath>

class ReachabilityChart : public QWidget {
 QJsonArray profiles;
public:
 ReachabilityChart(QJsonArray rows,QWidget*parent=nullptr):QWidget(parent),profiles(rows){setMinimumSize(500,210);setToolTip(QString::fromUtf8("蓝柱：气道末端距候选区域；橙线：从起点可达的气道中心线总长。左右轴单位均为 mm。"));}
protected:
 void paintEvent(QPaintEvent*) override {
  QPainter p(this);p.setRenderHint(QPainter::Antialiasing);p.fillRect(rect(),QColor("#101f2f"));
  p.setPen(QColor("#e3edf7"));p.drawText(QRect(12,4,width()-24,24),Qt::AlignCenter,QString::fromUtf8("器械直径与全气道可达性"));
  QRectF area(78,38,qMax(1,width()-162),qMax(1,height()-93));
  double maxGap=1,maxLength=1;for(auto v:profiles){auto r=v.toObject();maxGap=qMax(maxGap,r["closest_lesion_gap_mm"].toDouble());maxLength=qMax(maxLength,r["reachable_centerline_length_mm"].toDouble());}
  maxGap*=1.15;maxLength*=1.15;
  for(int i=0;i<=4;++i){double y=area.bottom()-area.height()*i/4.;p.setPen(QColor("#294055"));p.drawLine(QPointF(area.left(),y),QPointF(area.right(),y));p.setPen(QColor("#63b7ff"));p.drawText(QRectF(0,y-9,area.left()-8,18),Qt::AlignRight|Qt::AlignVCenter,QString::number(maxGap*i/4.,'f',0));p.setPen(QColor("#ffc06f"));p.drawText(QRectF(area.right()+8,y-9,70,18),Qt::AlignLeft|Qt::AlignVCenter,QString::number(maxLength*i/4.,'f',0));}
  QVector<QPointF> line;double step=area.width()/qMax(1,profiles.size());
  for(int i=0;i<profiles.size();++i){auto r=profiles[i].toObject();double x=area.left()+step*(i+.5),gap=r["closest_lesion_gap_mm"].toDouble(),length=r["reachable_centerline_length_mm"].toDouble();
   if(r["closest_lesion_gap_mm"].isDouble()){p.setPen(Qt::NoPen);p.setBrush(QColor("#4aa8ef"));p.drawRoundedRect(QRectF(x-step*.21,area.bottom()-area.height()*gap/maxGap,step*.42,area.height()*gap/maxGap),2,2);p.setPen(QColor("#b8dcff"));p.drawText(QRectF(x-step*.5,area.bottom()-area.height()*gap/maxGap-23,step,20),Qt::AlignCenter,QString::number(gap,'f',1));}
   line.append(QPointF(x,area.bottom()-area.height()*length/maxLength));p.setPen(QColor("#dce8f5"));p.drawText(QRectF(x-step*.5,area.bottom()+4,step,20),Qt::AlignCenter,QString::number(r["scope_diameter_mm"].toDouble(),'f',1));
  }
  p.setPen(QPen(QColor("#ffb454"),3));for(int i=1;i<line.size();++i)p.drawLine(line[i-1],line[i]);p.setBrush(QColor("#ffb454"));for(auto q:line)p.drawEllipse(q,4,4);
  p.setPen(QColor("#dce8f5"));p.drawText(QRectF(area.left(),area.bottom()+25,area.width(),22),Qt::AlignCenter,QString::fromUtf8("器械直径（mm） · 蓝柱：距候选区域（左轴） · 橙线：可达总长（右轴）"));
 }
};
