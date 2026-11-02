#pragma once
#include <QtWidgets>
#include <functional>
class PlCompositeTransport;
// Dedicated C7 owner. One frame in flight, one latest unsent complete state,
// one completed GUI delivery. Stop waits for the worker to restore C6.
class PlComposite : public QObject {
 QThread ioThread;PlCompositeTransport*io=nullptr;quint64 intent=0;bool running=false,acceptFrames=false;
 QMutex frameMutex;QImage pendingFrame;QJsonObject pendingInfo;quint64 pendingIntent=0;bool queued=false;
public:
 std::function<void(QImage,QJsonObject)> onFrame;
 std::function<void(QString)> onStatus;
 explicit PlComposite(QString root,QObject*parent=nullptr);
 ~PlComposite();
 bool active()const{return running;}
 void start(QString scene,QJsonObject state);
 void request(QJsonObject state);
 void stop(std::function<void()> done={});
};
