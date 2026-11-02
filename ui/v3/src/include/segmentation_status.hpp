#pragma once
#include <QtCore>
#include <cmath>

// Scalar-only UI helpers. No image decoding, inference or hardware access.
namespace segmentation_status {
inline QJsonObject object(const QString& path, qint64 limit=65536) {
    QFile file(path);
    if(!file.open(QIODevice::ReadOnly)||file.size()<2||file.size()>limit)return {};
    QJsonParseError error;
    auto doc=QJsonDocument::fromJson(file.readAll(),&error);
    return error.error==QJsonParseError::NoError&&doc.isObject()?doc.object():QJsonObject{};
}
inline bool integer(QJsonValue value,int low,int high,int& result) {
    if(!value.isDouble())return false;
    double n=value.toDouble();
    if(!std::isfinite(n)||n<low||n>high||std::floor(n)!=n)return false;
    result=int(n);return true;
}
inline bool nonnegative(QJsonValue value,double& result) {
    if(!value.isDouble())return false;
    result=value.toDouble();return std::isfinite(result)&&result>=0.;
}
inline bool sameProcess(int pid,double startTicks) {
    if(!std::isfinite(startTicks)||startTicks<=0||startTicks>9007199254740991.||std::floor(startTicks)!=startTicks)return false;
    QFile stat(QString("/proc/%1/stat").arg(pid));if(!stat.open(QIODevice::ReadOnly))return false;
    auto raw=stat.read(65536);int closing=raw.lastIndexOf(')');if(closing<0)return false;
    auto fields=raw.mid(closing+1).simplified().split(' ');if(fields.size()<20)return false;
    bool ok=false;auto ticks=fields[19].toULongLong(&ok);return ok&&double(ticks)==startTicks;
}
inline qint64 sampledPeakRSS(int pid,double startTicks) {
    if(!sameProcess(pid,startTicks))return -1;
    QFile file(QString("/proc/%1/status").arg(pid));
    if(!file.open(QIODevice::ReadOnly))return -1;
    auto lines=file.read(65536).split('\n');
    for(const auto& line:lines)if(line.startsWith("VmHWM:")) {
        auto fields=line.simplified().split(' ');bool ok=false;
        if(fields.size()!=3||fields[2]!="kB")return -1;
        qint64 kb=fields[1].toLongLong(&ok);
        return ok&&kb>=0&&kb<=((qint64(1)<<53)/1024)&&sameProcess(pid,startTicks)?kb*1024:-1;
    }
    return -1;
}
inline bool progress(const QJsonObject& status,int childPID,int expectedRepeats,
                     QString& text,int& done,int& total,double startTicks=0.) {
    int pid=0;if(!integer(status["pid"],2,2147483647,pid)||pid!=childPID)return false;
    if(status["status"]=="hardware_blocked") {
        text=QString::fromUtf8("PL 等待异常：后端保留缓冲区和锁；请勿结束进程，等待检查。 ");
        done=total=0;return true;
    }
    if(status["status"]!="running")return false;
    int repeat=0,repeats=0,slice=0,slices=0;
    if(!integer(status["repeats"],1,5,repeats)||repeats!=expectedRepeats||
       !integer(status["repeat"],1,repeats,repeat)||
       !integer(status["slices"],1,268435456,slices)||
       !integer(status["slice"],0,slices,slice))return false;
    total=repeats*slices;done=(repeat-1)*slices+slice;
    text=QString::fromUtf8("第 %1/%2 遍 · 切片 %3/%4").arg(repeat).arg(repeats).arg(slice).arg(slices);
    double elapsed=0.;if(nonnegative(status["elapsed_seconds"],elapsed))
        text+=QString::fromUtf8(" · 已用 %1 秒").arg(elapsed,0,'f',0);
    if(status["stage"]=="postprocess"||done>=total)
        text+=QString::fromUtf8("\n推理已完成；正在后处理、保存和核对");
    else {
        double inference=0.;
        if(status["stage"]=="inference"&&done>=8&&nonnegative(status["inference_elapsed_seconds"],inference))
            text+=QString::fromUtf8("\n预计剩余推理 %1 秒（不含后处理与保存）").arg(inference*(total-done)/done,0,'f',0);
    }
    qint64 peak=sampledPeakRSS(pid,startTicks);
    if(peak>=0)text+=QString::fromUtf8("\n分割进程采样峰值 RSS %1 MiB").arg(peak/double(1<<20),0,'f',1);
    return true;
}
inline QString summary(const QJsonObject& report,const QString& inputSHA) {
    if(report["status"]!="completed"||!report["input_sha256"].isString()||
       inputSHA.size()!=64||report["input_sha256"].toString()!=inputSHA)return {};
    int repeats=0;double inference=0.,post=0.,peak=0.,total=0.;
    if(!integer(report["repeats"],1,5,repeats)||
       !nonnegative(report["median_inference_seconds"],inference)||
       !nonnegative(report["postprocess_seconds"],post)||
       !nonnegative(report["process_peak_rss_bytes"],peak))return {};
    QString text=QString::fromUtf8("网络与调度中位数 %1 秒\n后处理 %2 秒 · 峰值 RSS %3 MiB")
        .arg(inference,0,'f',2).arg(post,0,'f',2).arg(peak/double(1<<20),0,'f',1);
    if(nonnegative(report["segmentation_with_cleanup_stage_wall_seconds"],total))
        text+=QString::fromUtf8(report["airway_cleanup"].toObject()["backend"]=="PS_original_clean_mask"?"\n共 %1 遍混合推理＋PS气道清理总计 %2 秒（含准备、保存和核对）":"\n共 %1 遍推理＋B7 PL清理总计 %2 秒（含准备、保存和核对）").arg(repeats).arg(total,0,'f',2);
    text+=QString::fromUtf8("\n网络/调度计时含准备和同步；不是纯 PL MAC 时间。");
    return text;
}
inline bool needsExistingTarget(const QString& mode) {
    return mode=="navigation"||mode=="comparison"||mode=="airway-detail";
}
} // namespace segmentation_status
