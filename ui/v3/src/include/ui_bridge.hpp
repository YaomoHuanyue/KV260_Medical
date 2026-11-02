#pragma once
// 界面桥：原有 Qt 控件继续作为"状态模型"（保留对象名、信号连接与自动测试），
// QML 外框通过本对象读取它们的状态，并把用户操作转回原控件。
// 本文件含 Q_OBJECT，需要 moc；全部成员内联定义，可被多个编译单元包含。
#include <QtWidgets>
#include <QQmlPropertyMap>
#include <cmath>
#include <functional>

class UiBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(QObject* s READ stateObject CONSTANT)
public:
    explicit UiBridge(QObject* parent=nullptr) : QObject(parent), map(new QQmlPropertyMap(this)) {
        poll.setInterval(120);
        connect(&poll, &QTimer::timeout, this, [this]{ pollLabels(); });
        poll.start();
    }
    QQmlPropertyMap* state() const { return map; }
    QObject* stateObject() const { return map; }

    // ── 注册原控件 ──
    void addButton(const QString& key, QAbstractButton* b) {
        if(!b) return; buttons[key]=b; QPointer<QAbstractButton> w(b);
        auto sync=[this,key,w]{ if(!dead && w) publishButton(key,w); }; syncers[key]=sync;
        connect(b, &QAbstractButton::toggled, this, sync);
        watch(b, sync); sync();
    }
    void addCombo(const QString& key, QComboBox* c, bool emitActivated=false) {
        if(!c) return; combos[key]=c; if(emitActivated) activatedCombos.insert(key); QPointer<QComboBox> w(c);
        auto sync=[this,key,w]{ if(!dead && w) publishCombo(key,w); }; syncers[key]=sync;
        connect(c, QOverload<int>::of(&QComboBox::currentIndexChanged), this, sync);
        if(auto* m=c->model()){
            connect(m, &QAbstractItemModel::rowsInserted, this, sync);
            connect(m, &QAbstractItemModel::rowsRemoved, this, sync);
            connect(m, &QAbstractItemModel::modelReset, this, sync);
            connect(m, &QAbstractItemModel::dataChanged, this, sync);
        }
        watch(c, sync); sync();
    }
    void addSlider(const QString& key, QAbstractSlider* s) {
        if(!s) return; sliders[key]=s; QPointer<QAbstractSlider> w(s);
        auto sync=[this,key,w]{ if(dead || !w) return; auto* s=w.data(); map->insert(key, QVariantMap{{"value",s->value()},{"min",s->minimum()},{"max",s->maximum()},{"enabled",s->isEnabled()},{"tip",s->toolTip()}}); }; syncers[key]=sync;
        connect(s, &QAbstractSlider::valueChanged, this, sync);
        connect(s, &QAbstractSlider::rangeChanged, this, sync);
        watch(s, sync); sync();
    }
    void addSpin(const QString& key, QDoubleSpinBox* s) {
        if(!s) return; doubles[key]=s; QPointer<QDoubleSpinBox> w(s);
        auto sync=[this,key,w]{ if(dead || !w) return; auto* s=w.data(); map->insert(key, QVariantMap{{"value",s->value()},{"min",s->minimum()},{"max",s->maximum()},{"step",s->singleStep()},{"decimals",s->decimals()},{"suffix",s->suffix()},{"enabled",s->isEnabled()},{"tip",s->toolTip()}}); }; syncers[key]=sync;
        connect(s, QOverload<double>::of(&QDoubleSpinBox::valueChanged), this, sync);
        watch(s, sync); sync();
    }
    void addLabel(const QString& key, QLabel* l) { if(l){ labels[key]=l; publishLabel(key,l); } }
    void addProgress(const QString& key, QProgressBar* p) {
        if(!p) return; bars[key]=p; QPointer<QProgressBar> w(p);
        auto sync=[this,key,w]{ if(dead || !w) return; auto* p=w.data(); map->insert(key, QVariantMap{{"value",p->value()},{"min",p->minimum()},{"max",p->maximum()},{"busy",p->minimum()==p->maximum()}}); }; syncers[key]=sync;
        connect(p, &QProgressBar::valueChanged, this, sync);
        watch(p, sync); sync();
    }
    void addText(const QString& key, QPlainTextEdit* t) {
        if(!t) return; QPointer<QPlainTextEdit> w(t);
        auto sync=[this,key,w]{ if(!dead && w) map->insert(key, w->toPlainText().right(12000)); }; syncers[key]=sync;
        connect(t, &QPlainTextEdit::textChanged, this, sync); sync();
    }
    // 由 C++ 直接发布的值（页码、遥测、流程状态等）
    void set(const QString& key, const QVariant& value) { if(!dead && map->value(key)!=value) map->insert(key, value); }
    // 窗口析构前调用：停止轮询、拆除事件过滤器，之后不再访问任何控件
    void shutdown() { dead=true; poll.stop(); for(auto* f:filters) delete f; filters.clear(); }
    QVariant get(const QString& key) const { return map->value(key); }
    void republish(const QString& key) { if(!dead && syncers.contains(key)) syncers[key](); }

    // ── QML 调用 ──
    Q_INVOKABLE void click(const QString& key) {
        if(dead) return;
        if(auto* b=buttons.value(key).data()) if(b->isEnabled()) b->click();
    }
    Q_INVOKABLE void setChecked(const QString& key, bool on) {
        if(dead) return;
        if(auto* b=buttons.value(key).data()) if(b->isEnabled() && b->isChecked()!=on) b->setChecked(on);
    }
    Q_INVOKABLE void setIndex(const QString& key, int index) {
        if(dead) return;
        auto* c=combos.value(key).data(); if(!c || !c->isEnabled() || index<0 || index>=c->count()) return;
        c->setCurrentIndex(index);
        if(activatedCombos.contains(key)) emit c->activated(index);
    }
    Q_INVOKABLE void setValue(const QString& key, double value) {
        if(dead) return;
        if(auto* s=sliders.value(key).data()) { if(s->isEnabled()) s->setValue(int(std::lround(value))); return; }
        if(auto* d=doubles.value(key).data()) { if(d->isEnabled()) d->setValue(value); return; }
    }
    Q_INVOKABLE void action(const QString& name, const QVariant& argument=QVariant()) { if(!dead) emit actionRequested(name, argument); }
signals:
    void actionRequested(const QString& name, const QVariant& argument);
private:
    // 控件的启用 / 文字 / 提示变化没有专门信号，用事件过滤器捕获
    struct Watch : public QObject {
        std::function<void()> fn; bool queued=false;
        bool eventFilter(QObject*, QEvent* e) override {
            auto t=e->type();
            if(!queued && (t==QEvent::EnabledChange || t==QEvent::ToolTipChange || t==QEvent::ShowToParent || t==QEvent::HideToParent || t==QEvent::DynamicPropertyChange)){
                queued=true; QTimer::singleShot(0, this, [this]{ queued=false; fn(); });
            }
            return false;
        }
    };
    void watch(QWidget* w, std::function<void()> fn) { auto* f=new Watch; f->setParent(this); f->fn=fn; w->installEventFilter(f); filters.append(f); }
    void publishButton(const QString& key, QAbstractButton* b) {
        map->insert(key, QVariantMap{{"text",b->text()},{"enabled",b->isEnabled()},{"checked",b->isChecked()},{"checkable",b->isCheckable()},{"hidden",b->isHidden()},{"tip",b->toolTip()}});
        buttonText[key]=b->text();
    }
    void publishCombo(const QString& key, QComboBox* c) {
        QStringList items; for(int i=0;i<c->count();++i) items<<c->itemText(i);
        map->insert(key, QVariantMap{{"index",c->currentIndex()},{"items",items},{"text",c->currentText()},{"enabled",c->isEnabled()},{"tip",c->toolTip()}});
    }
    void publishLabel(const QString& key, QLabel* l) {
        labelText[key]=l->text();
        map->insert(key, QVariantMap{{"text",l->text()},{"tip",l->toolTip()},{"hidden",l->isHidden()}});
    }
    void pollLabels() {
        if(dead) return;
        for(auto it=labels.cbegin(); it!=labels.cend(); ++it) if(it.value() && labelText.value(it.key())!=it.value()->text()) publishLabel(it.key(), it.value());
        for(auto it=buttons.cbegin(); it!=buttons.cend(); ++it) if(it.value() && buttonText.value(it.key())!=it.value()->text()) publishButton(it.key(), it.value());
    }
    QQmlPropertyMap* map;
    QTimer poll;
    QHash<QString,QPointer<QAbstractButton>> buttons;
    QHash<QString,QPointer<QComboBox>> combos;
    QHash<QString,QPointer<QAbstractSlider>> sliders;
    QHash<QString,QPointer<QDoubleSpinBox>> doubles;
    QHash<QString,QPointer<QLabel>> labels;
    QHash<QString,QPointer<QProgressBar>> bars;
    QHash<QString,QString> labelText, buttonText;
    QSet<QString> activatedCombos;
    QHash<QString,std::function<void()>> syncers;
    QList<QObject*> filters;
    bool dead=false;
};
