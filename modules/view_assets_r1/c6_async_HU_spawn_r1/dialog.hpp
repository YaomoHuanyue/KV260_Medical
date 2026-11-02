#pragma once
#include <QtWidgets>
#include <functional>

class AdaptiveAirwayDialog:public QDialog {
    QString root, ct, source, requestedOutput, completed;
    QThread workerThread;QObject* workerContext=nullptr;QProcess* worker=nullptr;
    QByteArray pending;
    QString errors;
    QJsonObject request;
    bool active=false;
    std::function<bool()> canStart;
    std::function<void(bool)> changed;
    std::function<void(QString)> accepted;
    QComboBox *seedMode, *backend;
    QSpinBox *seedX, *seedY, *seedZ, *lower, *upperStart, *upperStop, *upperStep, *workers;
    QCheckBox *preserve;
    QPushButton *start;
    QLabel *status;
    QTableWidget *steps;
    QList<QWidget*> controls;
    static QString t(const char* s) {return QString::fromUtf8(s);}
    QSpinBox* integer(QString name,int low,int high,int value) {
        auto* s=new QSpinBox;
        s->setObjectName(name);s->setRange(low,high);s->setValue(value);controls.append(s);return s;
    }
    void availability() {
        for(auto* c:controls)c->setEnabled(!active);
        preserve->setEnabled(!active&&!source.isEmpty());
        for(auto* s:{seedX,seedY,seedZ})s->setEnabled(!active&&seedMode->currentIndex()==1);
        start->setEnabled(!active);
    }
    void setActive(bool value) {
        if(active==value)return;
        active=value;availability();if(changed)changed(value);
    }
    void lines(QByteArray data) {
        pending+=data;
        while(pending.contains('\n')) {
            int n=pending.indexOf('\n');auto line=pending.left(n);pending.remove(0,n+1);
            QJsonParseError error;auto object=QJsonDocument::fromJson(line,&error).object();
            if(error.error!=QJsonParseError::NoError){errors+=QString::fromUtf8(line);continue;}
            QString event=object["event"].toString();
            if(event=="stage")status->setText(object["text"].toString());
            else if(event=="growth_step") {
                int row=steps->rowCount();steps->insertRow(row);
                QStringList values={QString::number(object["upper_hu"].toInt()),
                    QString::number(object["voxels"].toInt()),QString::number(object["volume_ml"].toDouble(),'f',2),
                    object["leaked"].toBool()?t("泄漏，回退"):t("通过")};
                for(int i=0;i<values.size();++i)steps->setItem(row,i,new QTableWidgetItem(values[i]));
            } else if(event=="completed")completed=object["result"].toString();
            else if(event=="error")errors+=object["text"].toString();
        }
    }
    void finish(int code,QProcess::ExitStatus exitStatus) {
        if(!pending.trimmed().isEmpty())lines("\n");
        bool good=code==0&&exitStatus==QProcess::NormalExit&&completed==requestedOutput&&
            QFileInfo::exists(completed+"/hu_handoff.json");
        if(good) {
            QFile file(completed+"/hu_handoff.json");good=file.open(QIODevice::ReadOnly);
            auto report=QJsonDocument::fromJson(file.readAll()).object();
            good=good&&report["status"]=="completed"&&report["independently_validated_self_contained_bundle"].toBool();
            if(good)status->setText(QString(t("完成 · 采用 %1 HU · %2 个气道体素\n结果：%3"))
                .arg(report["selected_upper_hu"].toInt()).arg(report["cleaned_mask_voxels"].toInt()).arg(completed));
        }
        if(good&&accepted)accepted(completed);
        if(!good){completed.clear();status->setText(t("处理失败，原病例保持不变：\n")+errors.right(1800));}
        setActive(false);
    }
protected:
    void closeEvent(QCloseEvent* event) override {
        if(active){status->setText(t("当前增长正在后台执行，完成后即可关闭。"));event->ignore();}
        else event->accept();
    }
public:
    AdaptiveAirwayDialog(QString project,QString input,QString current,
        std::function<bool()> mayStart,std::function<void(bool)> onChanged,
        std::function<void(QString)> onCompleted,QWidget* parent=nullptr):
        QDialog(parent),root(project),ct(input),source(current),canStart(mayStart),changed(onChanged),accepted(onCompleted) {
        setAttribute(Qt::WA_DeleteOnClose);setObjectName("HU_airway_dialog");
        setWindowTitle(t("HU 自适应气道分割"));resize(690,650);
        auto* layout=new QVBoxLayout(this);
        auto* context=new QLabel(t("当前 CT：")+QFileInfo(ct).fileName()+t("\n生成新的结果；保留原有深度学习结果。"));
        context->setWordWrap(true);layout->addWidget(context);
        auto* form=new QFormLayout;
        backend=new QComboBox;backend->setObjectName("HU_backend");backend->addItem(t("优化实现（PS）"),"native");
        backend->addItem(t("原 Python（PS，对照）"),"original");controls.append(backend);form->addRow(t("执行方式"),backend);
        seedMode=new QComboBox;seedMode->setObjectName("HU_seed_mode");seedMode->addItems({t("自动定位气管"),t("手动体素坐标")});
        controls.append(seedMode);form->addRow(t("种子选择"),seedMode);
        auto* xyz=new QHBoxLayout;
        seedX=integer("HU_seed_x",0,1000000000,0);seedY=integer("HU_seed_y",0,1000000000,0);seedZ=integer("HU_seed_z",0,1000000000,0);
        for(auto pair:{qMakePair(QString("X"),seedX),qMakePair(QString("Y"),seedY),qMakePair(QString("Z"),seedZ)}) {
            xyz->addWidget(new QLabel(pair.first));xyz->addWidget(pair.second);
        }
        form->addRow(t("种子（体素）"),xyz);
        lower=integer("HU_lower",-32768,32767,-1050);upperStart=integer("HU_upper_start",-32768,32767,-950);
        upperStop=integer("HU_upper_stop",-32768,32767,-625);upperStep=integer("HU_upper_step",1,10000,25);
        form->addRow(t("HU 下限"),lower);form->addRow(t("上限起点"),upperStart);form->addRow(t("上限终点"),upperStop);
        form->addRow(t("递增步长"),upperStep);workers=integer("HU_workers",1,4,4);form->addRow(t("选种线程"),workers);
        layout->addLayout(form);
        preserve=new QCheckBox(t("保留当前同一 CT 的肺和病灶候选"));preserve->setObjectName("HU_preserve");
        preserve->setChecked(!source.isEmpty());controls.append(preserve);layout->addWidget(preserve);
        start=new QPushButton(t("开始 HU 气道分割"));start->setObjectName("HU_start");layout->addWidget(start);
        status=new QLabel(t("发现体积突增或边界泄漏时，回退到前一次结果。"));status->setObjectName("HU_status");
        status->setWordWrap(true);status->setTextInteractionFlags(Qt::TextSelectableByMouse);layout->addWidget(status);
        steps=new QTableWidget(0,4);steps->setObjectName("HU_steps");steps->setHorizontalHeaderLabels({t("上限 HU"),t("体素数"),t("体积 ml"),t("结果")});
        steps->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch);steps->setEditTriggers(QAbstractItemView::NoEditTriggers);
        layout->addWidget(steps,1);auto* close=new QPushButton(t("关闭"));layout->addWidget(close);
        connect(close,&QPushButton::clicked,this,&QDialog::close);connect(start,&QPushButton::clicked,this,[this]{begin();});
        connect(seedMode,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this]{availability();});
        workerContext=new QObject;worker=new QProcess(workerContext);worker->setWorkingDirectory(root);auto env=QProcessEnvironment::systemEnvironment();
        env.remove("LD_PRELOAD");env.remove("QT_QPA_PLATFORM");
        for(auto key:{"OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"})env.insert(key,"1");
        env.insert("PYTHONDONTWRITEBYTECODE","1");env.insert("PYTHONUNBUFFERED","1");worker->setProcessEnvironment(env);
        workerContext->moveToThread(&workerThread);
        connect(&workerThread,&QThread::finished,workerContext,&QObject::deleteLater);
        connect(worker,&QProcess::started,workerContext,[this]{worker->write(worker->property("HU_request_bytes").toByteArray());worker->closeWriteChannel();});
        connect(worker,&QProcess::readyReadStandardOutput,workerContext,[this]{auto bytes=worker->readAllStandardOutput();QMetaObject::invokeMethod(this,[this,bytes]{lines(bytes);},Qt::QueuedConnection);});
        connect(worker,&QProcess::readyReadStandardError,workerContext,[this]{auto bytes=worker->readAllStandardError();QMetaObject::invokeMethod(this,[this,bytes]{errors+=QString::fromUtf8(bytes);},Qt::QueuedConnection);});
        connect(worker,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),workerContext,[this](int code,QProcess::ExitStatus exitStatus){
            auto output=worker->readAllStandardOutput(),error=worker->readAllStandardError();
            QMetaObject::invokeMethod(this,[this,output,error,code,exitStatus]{lines(output);errors+=QString::fromUtf8(error);finish(code,exitStatus);},Qt::QueuedConnection);
        });
        connect(worker,&QProcess::errorOccurred,workerContext,[this](QProcess::ProcessError error){if(error==QProcess::FailedToStart){auto text=worker->errorString();QMetaObject::invokeMethod(this,[this,text]{status->setText(text);setActive(false);},Qt::QueuedConnection);}});
        workerThread.setObjectName("HU worker transport");workerThread.start();
        availability();
    }
    ~AdaptiveAirwayDialog()override {workerThread.quit();workerThread.wait();}
    bool running() const {return active;}
    QString completedResult() const {return completed;}
    QJsonObject submittedRequest() const {return request;}
    void begin() {
        if(active)return;
        if(canStart&&!canStart()){status->setText(t("病例或任务已变化，请关闭后重新打开此入口。"));return;}
        if(lower->value()>upperStart->value()||upperStart->value()>upperStop->value()) {
            status->setText(t("请使用 下限 ≤ 上限起点 ≤ 上限终点。"));return;
        }
        requestedOutput=root+"/ui/runs/hu_"+QUuid::createUuid().toString(QUuid::Id128);
        request=QJsonObject{{"schema","kv260.HU_airway.UI.request.v1"},{"input",QFileInfo(ct).absoluteFilePath()},
            {"output",requestedOutput},{"backend",backend->currentData().toString()},{"workers",workers->value()},
            {"lower_hu",lower->value()},{"upper_start",upperStart->value()},{"upper_stop",upperStop->value()},
            {"upper_step",upperStep->value()}};
        if(seedMode->currentIndex()==1)request["seed_xyz"]=QJsonArray{seedX->value(),seedY->value(),seedZ->value()};
        if(preserve->isChecked()&&!source.isEmpty())request["preserve_result"]=QFileInfo(source).absoluteFilePath();
        pending.clear();errors.clear();completed.clear();steps->setRowCount(0);status->setText(t("正在启动后台增长"));
        setActive(true);auto bytes=QJsonDocument(request).toJson(QJsonDocument::Compact);
        QMetaObject::invokeMethod(workerContext,[this,bytes]{worker->setProperty("HU_request_bytes",bytes);worker->start(root+"/.venv/bin/python",{"-B","-m","modules.adaptive_airway_growth.ui_r1.worker","--root",root});},Qt::QueuedConnection);
    }
};
