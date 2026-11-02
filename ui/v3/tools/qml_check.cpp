// 逐个创建 QML 页面（不依赖医疗后端），用于定位 QML 创建期错误。
#include "../src/include/ui_bridge.hpp"
#include <QQmlEngine>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQuickItem>
#include <cstdio>
int main(int argc,char**argv){
  QApplication app(argc,argv);QQmlEngine engine;UiBridge bridge;
  bridge.set("page",0);bridge.set("drawer",QString());bridge.set("busy",false);bridge.set("theme","dark");bridge.set("hud",QVariantMap{});
  bridge.set("navMarks",QVariantList{0.2,0.5});bridge.set("remaining",12.5);bridge.set("structure",2);bridge.set("pipeline",QVariantMap{{"stages",QVariantList{}},{"running",false},{"label","x"}});
  engine.rootContext()->setContextProperty("ui",&bridge);
  int bad=0;
  for(int i=1;i<argc;++i){
    std::printf("== %s\n",argv[i]);std::fflush(stdout);
    QQmlComponent c(&engine,QUrl(QString("qrc:/qml/")+argv[i]));
    QObject*o=c.create();
    if(!o){++bad;for(auto&e:c.errors())std::printf("  %s\n",qPrintable(e.toString()));}
    else std::printf("  ok\n");
    std::fflush(stdout);delete o;
  }
  return bad;
}
