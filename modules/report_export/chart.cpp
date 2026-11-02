#include "../../ui/releases/feature_completion_r6/reachability_chart.hpp"
#include <stdexcept>
#include <iostream>

int main(int argc,char**argv) {
 try {
  qputenv("QT_QPA_PLATFORM","offscreen");
  QApplication app(argc,argv);
  if(argc!=3)throw std::runtime_error("Require profile JSON and a new PNG path");
  QFile input(QString::fromLocal8Bit(argv[1]));
  if(!input.open(QIODevice::ReadOnly))throw std::runtime_error("Cannot read profiles");
  QByteArray bytes=input.readAll();QJsonParseError error;
  auto doc=QJsonDocument::fromJson(bytes,&error);
  if(error.error!=QJsonParseError::NoError||!doc.isObject())throw std::runtime_error("Invalid profiles");
  auto whole=doc.object();auto profiles=whole["profiles"].toArray();QJsonArray rows;
  if(whole["schema"]!="kv260.navigation.raw_comparison.v1"||profiles.isEmpty()||profiles.size()>64)
   throw std::runtime_error("Unsupported complete profile");
  // The original Python chart filters to reachable rows before plotting.
  for(auto value:profiles)if(value.toObject()["reachable"].toBool())rows.append(value);
  QString path=QString::fromLocal8Bit(argv[2]);
  if(QFileInfo::exists(path))throw std::runtime_error("Chart destination exists");
  ReachabilityChart chart(rows);chart.setFont(QFont("Noto Sans CJK SC",14));
  chart.resize(qMax(1900,rows.size()*100+162),1140);
  QImage image(chart.size(),QImage::Format_ARGB32);image.fill(Qt::transparent);
  chart.render(&image);
  QSaveFile output(path);
  if(!output.open(QIODevice::WriteOnly)||!image.save(&output,"PNG")||!output.commit())
   throw std::runtime_error("Cannot publish chart");
  QJsonObject proof{{"status","complete_original_profile_data_rendered_with_native_Qt_chart"},
   {"input_sha256",QString(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex())},
   {"width",image.width()},{"height",image.height()},{"reachable_rows",rows},
   {"all_query_count",profiles.size()},{"original_reachable_row_filter",true}};
  std::cout<<QJsonDocument(proof).toJson(QJsonDocument::Compact).constData()<<std::endl;
  return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}
}
