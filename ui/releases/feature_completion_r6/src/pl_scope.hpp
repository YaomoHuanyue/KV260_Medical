#pragma once
#include <QtWidgets>
#include <functional>

class PlScopeTransport;
class PlScope : public QObject {
 QThread ioThread;PlScopeTransport*io=nullptr;bool running=false,acceptFrames=false;quint64 intent=0;
 QMutex frameMutex;QImage pendingFrame,pendingNormal;QJsonObject pendingInfo;bool frameDeliveryQueued=false;quint64 pendingFrameIntent=0;
public:
 std::function<void(QImage,QImage,QJsonObject)> onFrame;
 std::function<void(QString)> onStatus;
 explicit PlScope(QString root,QObject*parent=nullptr);
 ~PlScope();
 bool active()const{return running;}
 void start(QString result,QJsonObject pose);
 void request(QJsonObject pose);
 void setQuality(int level);
 void stop(std::function<void()> done={});
};
