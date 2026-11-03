#include "include/views_attributes_r52.hpp"
#include "include/composite_scene.hpp"
#include "include/capture.hpp"
#include "include/timeline.hpp"
#include "include/frame_r2.hpp"
#include "include/encoder_UI_r3.hpp"
#include "include/active_binding_r53.hpp"
#include "include/file_hash.hpp"
#include "include/motion.hpp"
#include "include/segmentation_status.hpp"
#include <functional>
#include "include/processing.hpp"
#include "include/pl_scope_complete_r9.hpp"
#include "include/pl_composite.hpp"
#include <QTest>
#include "gamepad_dispatch.hpp"
#include <QStandardItemModel>
#include <QRegularExpression>
#include <QPainter>
#include <QPainterPath>
#include <QButtonGroup>
#include <QStyle>
#include <array>
#include <signal.h>
#include <sys/resource.h>
#include <algorithm>
#include <numeric>
#include <cmath>
#include <atomic>
#include <thread>
#include <fstream>
#include <unistd.h>
#include "include/structures.hpp"
#include <QQuickWidget>
#include <QQmlEngine>
#include <QQmlContext>
#include <QQmlError>
#include <QStackedWidget>
#include "include/ui_bridge.hpp"

static volatile sig_atomic_t exitRequested=0;
static std::atomic<long long> lastTick{0};
static long long monoMs(){return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
static void handleSignal(int){exitRequested=1;}
static QString u(const char*s){return QString::fromUtf8(s);}
static void testDrag(QWidget*view,QPoint from,QPoint to){
 QMouseEvent press(QEvent::MouseButtonPress,from,Qt::LeftButton,Qt::LeftButton,Qt::NoModifier);QApplication::sendEvent(view,&press);
 QMouseEvent move(QEvent::MouseMove,to,Qt::NoButton,Qt::LeftButton,Qt::NoModifier);QApplication::sendEvent(view,&move);
 QMouseEvent release(QEvent::MouseButtonRelease,to,Qt::LeftButton,Qt::NoButton,Qt::NoModifier);QApplication::sendEvent(view,&release);
}
static QJsonObject readJson(QString path){QFile f(path);if(!f.open(QIODevice::ReadOnly))throw std::runtime_error(("Cannot read "+path).toStdString());QJsonParseError e;auto d=QJsonDocument::fromJson(f.readAll(),&e);if(e.error!=QJsonParseError::NoError||!d.isObject())throw std::runtime_error("Invalid JSON");return d.object();}
static void writeJson(QString path,QJsonObject o){QSaveFile f(path);if(!f.open(QIODevice::WriteOnly))throw std::runtime_error("Cannot save report");f.write(QJsonDocument(o).toJson());if(!f.commit())throw std::runtime_error("Cannot commit report");}

static QString routeDescription(const QJsonObject&r){
 QString status=r["status"].toString(),reason=r["reason"].toString();if(status.isEmpty())return u("尚无导航路径");
 QString why=reason=="insufficient_route_clearance"?u("部分管段净空不足"):
  reason=="insufficient_new_surface_route_clearance"?u("新表面部分管段净空不足"):
  reason=="insufficient_root_clearance"?u("起点净空不足"):
  reason=="insufficient_bend_radius"?u("器械最小弯曲半径约束未通过"):
  reason=="continuous_route_clearance_failed"?u("连续路径净空检查未通过"):
  reason=="disconnected_target_component"?u("目标气道与起点不连通"):u("当前模型未提供可达路径");
 QString text=status=="limited_reach"?u("未到目标附近气道：")+why+u("；当前仅显示可达部分"):
  status=="unreachable"?u("路径未建立：")+why:
  status=="airway_approach"?u("路径到达模型内目标附近的气道，未进入病灶组织"):u("路径已建立");
 if(r["final_target_gap_mm"].isDouble())text+=QString(u(" · 末端距%1 %2 mm")).arg(r["target_kind"]=="lesion_candidate"?u("候选区域"):u("目标")).arg(r["final_target_gap_mm"].toDouble(),0,'f',1);
 if(r["scope_diameter_mm"].isDouble())text+=QString(u("\n器械 Ø %1 mm · 每侧余量 %2 mm · 图像保守余量 %3 mm（模型几何估算）")).arg(r["scope_diameter_mm"].toDouble(),0,'f',1).arg(r["safety_margin_mm"].toDouble(),0,'f',1).arg(r["resolution_margin_mm"].toDouble(),0,'f',2);
 return text;
}

class MainWindow:public QWidget{
bool gamepadContextAllowed()const{return drawerKey.isEmpty()&&!demoActive&&!shellDead;}
#include "gamepad_controls_r2.inc"
QPushButton *logToggle=nullptr,*sideToggle=nullptr,*themeToggle=nullptr,*navPanelToggle=nullptr;
#include "include/v3_shell.inc"
QScrollArea *sideScroll=nullptr,*navInspector=nullptr;
bool  sideHidden[3]={false,false,true};
struct FoldSection{QPushButton*head;QWidget*body;bool exclusive;};
QList<FoldSection>  foldSections;
QPixmap glyph(QString kind,QColor color){
  QPixmap pixmap(32,32);pixmap.fill(Qt::transparent);QPainter p(&pixmap);p.setRenderHint(QPainter::Antialiasing);
  QPen pen(color,2.6,Qt::SolidLine,Qt::RoundCap,Qt::RoundJoin);p.setPen(pen);p.setBrush(Qt::NoBrush);
  if(kind=="image"){p.drawRoundedRect(QRectF(4,4,24,24),5,5);p.drawEllipse(QRectF(10,9,12,14));p.drawLine(QPointF(16,9),QPointF(16,23));}
  else if(kind=="cube"){QPolygonF top({QPointF(16,4),QPointF(27,10),QPointF(16,16),QPointF(5,10)});p.drawPolygon(top);
   p.drawLine(QPointF(5,10),QPointF(5,22));p.drawLine(QPointF(27,10),QPointF(27,22));p.drawLine(QPointF(16,16),QPointF(16,28));
   p.drawLine(QPointF(5,22),QPointF(16,28));p.drawLine(QPointF(27,22),QPointF(16,28));}
  else if(kind=="route"){QPainterPath path(QPointF(6,27));path.cubicTo(QPointF(6,16),QPointF(26,18),QPointF(24,7));p.drawPath(path);
   p.setBrush(color);p.drawEllipse(QPointF(24,7),3.2,3.2);p.drawEllipse(QPointF(6,27),2.2,2.2);}
  else if(kind=="right"){p.drawPolyline(QPolygonF({QPointF(12,8),QPointF(20,16),QPointF(12,24)}));}
  else if(kind=="down"){p.drawPolyline(QPolygonF({QPointF(8,12),QPointF(16,20),QPointF(24,12)}));}
  else if(kind=="sidebar"){p.drawRoundedRect(QRectF(4,6,24,20),4,4);p.drawLine(QPointF(12,6),QPointF(12,26));}
  else if(kind=="sun"){p.drawEllipse(QPointF(16,16),5.5,5.5);for(int i=0;i<8;++i){double a=i*M_PI/4;p.drawLine(QPointF(16+10*std::cos(a),16+10*std::sin(a)),QPointF(16+13*std::cos(a),16+13*std::sin(a)));}}
  else if(kind=="moon"){QPainterPath moon;moon.addEllipse(QPointF(15,16),11,11);QPainterPath bite;bite.addEllipse(QPointF(21,11),9,9);p.setBrush(color);p.drawPath(moon.subtracted(bite));}
  else if(kind=="panel"){p.drawRoundedRect(QRectF(4,6,24,20),4,4);p.drawLine(QPointF(20,6),QPointF(20,26));}
  else if(kind=="play"){p.setBrush(color);p.drawPolygon(QPolygonF({QPointF(10,7),QPointF(25,16),QPointF(10,25)}));}
  else if(kind=="stop"){p.setBrush(color);p.drawRoundedRect(QRectF(9,9,14,14),2,2);}
  else if(kind=="brand"){
   QLinearGradient g(0,0,32,32);g.setColorAt(0,QColor("#4f9bff"));g.setColorAt(1,QColor("#2563eb"));p.setPen(Qt::NoPen);p.setBrush(g);p.drawRoundedRect(QRectF(0,0,32,32),8,8);
   p.setPen(QPen(Qt::white,2.8,Qt::SolidLine,Qt::RoundCap,Qt::RoundJoin));p.drawLine(QPointF(16,6),QPointF(16,15));
   QPainterPath branches(QPointF(16,15));branches.cubicTo(QPointF(16,20),QPointF(9,19),QPointF(8,26));p.drawPath(branches);
   QPainterPath other(QPointF(16,15));other.cubicTo(QPointF(16,20),QPointF(23,19),QPointF(24,26));p.drawPath(other);}
  p.end();return pixmap;
 }
QIcon glyphIcon(QString kind,QColor off,QColor on=QColor()){
  QIcon icon;icon.addPixmap(glyph(kind,off),QIcon::Normal,QIcon::Off);icon.addPixmap(glyph(kind,on.isValid()?on:off),QIcon::Normal,QIcon::On);
  icon.addPixmap(glyph(kind,tone("ink3")),QIcon::Disabled,QIcon::Off);return icon;
 }
QVBoxLayout*foldSection(QVBoxLayout*parent,QString title,bool open,bool exclusive){
  auto*head=new QPushButton(title);head->setProperty("role","section");head->setCheckable(true);head->setIcon(glyphIcon("right",tone("ink3"),tone("accent")));head->setIconSize(QSize(14,14));
  auto*body=new QWidget;body->setObjectName("sectionBody");auto*layout=new QVBoxLayout(body);layout->setContentsMargins(10,4,10,12);layout->setSpacing(6);
  parent->addWidget(head);parent->addWidget(body);int index=foldSections.size();foldSections.append({head,body,exclusive});
  connect(head,&QPushButton::toggled,this,[this,index](bool expanded){
   auto section=foldSections[index];section.body->setVisible(expanded);
   section.head->setIcon(glyphIcon(expanded?"down":"right",tone("ink3"),tone("accent")));
   if(expanded&&section.exclusive)for(int i=0;i<foldSections.size();++i)if(i!=index&&foldSections[i].exclusive&&foldSections[i].head->isChecked())foldSections[i].head->setChecked(false);
  });
  body->setVisible(false);head->setChecked(open);return layout;
 }
QScrollArea*inspector(QBoxLayout*parent,int width,QVBoxLayout*&layout){
  auto*panel=new QWidget;panel->setObjectName("inspector");layout=new QVBoxLayout(panel);layout->setContentsMargins(0,4,0,8);layout->setSpacing(0);
  auto*scroll=new QScrollArea;scroll->setObjectName("inspectorScroll");scroll->setWidget(panel);scroll->setWidgetResizable(true);scroll->setFixedWidth(width);
  scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);scroll->setFrameShape(QFrame::NoFrame);parent->addWidget(scroll);return scroll;
 }
QLabel*caption(QString text){auto*l=new QLabel(text);l->setProperty("role","caption");return l;}
QFrame*divider(bool vertical=false){auto*line=new QFrame;line->setObjectName("divider");if(vertical)line->setFixedWidth(1);else line->setFixedHeight(1);return line;}
QList<QWidget*> verticalizeLastRow(QVBoxLayout*layout){
  QList<QWidget*> moved;if(layout->count()==0)return moved;auto*row=qobject_cast<QBoxLayout*>(layout->itemAt(layout->count()-1)->layout());if(!row)return moved;
  while(row->count()){auto*item=row->takeAt(0);if(auto*w=item->widget())moved.append(w);delete item;}
  layout->removeItem(row);delete row;for(auto*w:moved){w->setMaximumWidth(QWIDGETSIZE_MAX);layout->addWidget(w);}return moved;
 }
QString friendlyMessage(QString text){
  static const QList<QPair<QString,QString>> known={
   {"C7 source scene changed",u("合成场景已变化")},{"Source changed during video export",u("导出视频期间病例数据已变化")},
   {"Attribute binding differs from current scene",u("属性数据与当前场景不一致")},{"Attribute binding checksum mismatch",u("属性数据校验失败")},
   {"Missing attribute binding",u("缺少属性数据")},{"Cannot apply selected airway attribute stream",u("无法应用所选气道属性")},
   {"Batch PNG write failed",u("批量图片写入失败")},{"Batch PNG open failed",u("批量图片无法创建")},{"Batch PNG differs after readback",u("批量图片回读校验失败")},
   {"Batch PL camera/frame mismatch",u("批量图片的镜头与画面不一致")},{"Cannot create video destination",u("无法创建视频输出目录")},
   {"Cannot commit video directory",u("视频目录提交失败")},{"Video capture crossed a completed frame",u("视频采集跨越了已完成的画面")},
   {"Cannot save report",u("报告保存失败")},{"Cannot commit report",u("报告提交失败")},{"No candidate to focus",u("没有可聚焦的候选")},
   {"Invalid JSON",u("结果文件格式无效")},{"Missing current surface provenance",u("当前表面缺少来源记录")}};
  for(const auto&k:known)if(text.contains(k.first))text.replace(k.first,k.second);
  static const QRegularExpression english("[A-Za-z][A-Za-z'/-]+(?:[ ,:;]+[A-Za-z][A-Za-z'/-]+){2,}[.!]?");
  auto match=english.match(text);if(match.hasMatch()&&match.capturedStart()>0)text=text.left(match.capturedStart()).trimmed()+u("（技术原因见日志）");
  return text;
 }
QString checkImage(){
  QString path=QDir::temp().filePath("kv260_ui_check_v2.png");if(QFileInfo::exists(path))return path;
  QPixmap pixmap(14,14);pixmap.fill(Qt::transparent);QPainter painter(&pixmap);painter.setRenderHint(QPainter::Antialiasing);
  painter.setPen(QPen(Qt::white,2.0,Qt::SolidLine,Qt::RoundCap,Qt::RoundJoin));painter.drawPolyline(QPolygonF({QPointF(3.2,7.4),QPointF(6,10.2),QPointF(11,4.2)}));painter.end();
  return pixmap.save(path,"PNG")?path:QString();
 }
static QHash<QString,QString> themeTokens(bool light){
  static const QList<std::array<const char*,3>> rows={
   {"win","#0d0f12","#e8ebef"},{"bar","#111418","#f8f9fb"},{"panel","#15181d","#ffffff"},{"inset","#0f1215","#f2f4f7"},
   {"hover","#1c2026","#edf0f4"},{"press","#242930","#e1e6ec"},{"line","#23272e","#dce1e7"},{"line2","#30353e","#c6cdd6"},
   {"ink1","#e9ecef","#151a21"},{"ink2","#a5adb7","#4a5562"},{"ink3","#6f7782","#7b8591"},
   {"accent","#4b8dff","#2563eb"},{"accentHover","#6aa1ff","#3b74f0"},{"accentPress","#3a78e6","#1d4fd0"},{"accentSoft","#18263b","#e4ecfd"},{"accentLine","#2f4c7a","#a3c0f5"},
   {"mode","#262b33","#2563eb"},{"view","#05070a","#0b0e12"},
   {"warnBg","#221d12","#fff7e3"},{"warnLine","#463818","#efd590"},{"warnInk","#e3bf6a","#865800"},
   {"dangerBg","#2a1619","#fdeef0"},{"dangerLine","#58262f","#f1b7bf"},{"dangerInk","#ff9ca6","#b42330"},{"ok","#3ccf7f","#16a34a"}};
  QHash<QString,QString> map;for(const auto&r:rows)map.insert(r[0],light?r[2]:r[1]);return map;
 }
static QColor tone(const char*name,bool light=false){return QColor(themeTokens(light).value(name,"#ff00ff"));}
QString redesignStyleSheet(bool light=false){
  QString check=checkImage();QString checkRule=check.isEmpty()?QString():QString("image:url(%1);").arg(check);
  QString sheet=QString(
   "QWidget{color:@ink1;font-family:'Noto Sans CJK SC';font-size:12px;}"
   "QWidget#v3Black,QStackedWidget#v3Stage{background:#000000;}"
   "QWidget[role=\"window\"],QDialog{background:@win;}"
   "QToolTip{background:@panel;color:@ink1;border:1px solid @line2;padding:6px 8px;}"
   // 顶栏
   "QFrame#headerBar{background:@bar;border-bottom:1px solid @line;}"
   "QLabel#title{font-size:15px;font-weight:700;color:@ink1;}"
   "QFrame#modeBar{background:@inset;border:1px solid @line;border-radius:8px;}"
   "QPushButton[role=\"mode\"]{background:transparent;border:none;border-radius:6px;padding:5px 14px;color:@ink2;font-size:13px;min-height:22px;}"
   "QPushButton[role=\"mode\"]:hover{color:@ink1;background:@hover;}"
   "QPushButton[role=\"mode\"]:checked{background:@mode;color:#ffffff;font-weight:600;}"
   "QLabel#clock{color:@ink3;font-size:12px;padding:0 4px;}"
   "QPushButton[role=\"icon\"]{background:transparent;border:1px solid transparent;border-radius:6px;padding:4px;min-height:22px;}"
   "QPushButton[role=\"icon\"]:hover{background:@hover;border-color:@line;} QPushButton[role=\"icon\"]:checked{background:@accentSoft;border-color:@accentLine;}"
   // 面板与分区
   "QFrame#sidePanel{background:@panel;border:1px solid @line;border-radius:10px;}"
   "QFrame#caseSummary{background:transparent;border:none;}"
   "QLabel#caseName{font-size:14px;font-weight:600;color:@ink1;}"
   "QFrame#divider{background:@line;border:none;}"
   "QPushButton[role=\"section\"]{text-align:left;background:transparent;border:none;border-radius:0;padding:0 10px;min-height:34px;color:@ink2;font-size:13px;font-weight:600;}"
   "QPushButton[role=\"section\"]:hover{background:@hover;color:@ink1;}"
   "QPushButton[role=\"section\"]:checked{color:@ink1;background:@hover;border:none;}"
   "QWidget#inspector,QWidget#sectionBody{background:transparent;}"
   "QScrollArea#inspectorScroll{background:@panel;border:1px solid @line;border-radius:10px;}"
   "QScrollArea{background:transparent;border:none;} QScrollArea>QWidget>QWidget{background:transparent;}"
   "QLabel[role=\"caption\"]{color:@ink3;font-size:11px;}"
   "QLabel#muted,QLabel[role=\"muted\"]{color:@ink3;font-size:11px;}"
   "QLabel#section,QLabel#cardTitle{color:@ink2;font-size:12px;font-weight:600;}"
   "QLabel#status{color:@ink1;}"
   "QLabel#notice{background:@warnBg;border:none;border-left:3px solid @warnInk;color:@warnInk;padding:4px 10px;border-radius:4px;font-size:11px;}"
   "QLabel#structureAvailability{background:@inset;color:@ink2;padding:6px 8px;border:1px solid @line;border-radius:6px;font-size:11px;}"
   // 工具条与视图区
   "QFrame#toolbar,QFrame#viewStrip{background:@panel;border:1px solid @line;border-radius:10px;}"
   "QTabWidget::pane{border:none;background:transparent;} QTabWidget>QWidget{background:transparent;}"
   "QLabel#scopeUnavailable{background:@view;border:1px solid @line;border-radius:10px;color:#8b95a1;font-size:13px;}"
   // 按钮
   "QPushButton{background:@inset;border:1px solid @line2;border-radius:6px;padding:4px 12px;min-height:20px;color:@ink1;}"
   "QPushButton:hover{background:@hover;} QPushButton:pressed{background:@press;}"
   "QPushButton:checked{background:@accentSoft;border-color:@accent;}"
   "QPushButton:disabled{color:@ink3;background:@inset;border-color:@line;}"
   "QPushButton#primary{background:@accent;border:1px solid @accent;color:#ffffff;font-weight:600;padding:4px 16px;}"
   "QPushButton#primary:hover{background:@accentHover;} QPushButton#primary:pressed{background:@accentPress;}"
   "QPushButton#primary:disabled{background:@accentSoft;color:@ink3;border-color:@accentLine;}"
   "QPushButton[role=\"danger\"]:enabled{background:@dangerBg;border-color:@dangerLine;color:@dangerInk;}"
   "QPushButton[role=\"flat\"]{background:transparent;border:1px solid transparent;padding:2px 12px;color:@ink2;}"
   "QPushButton[role=\"flat\"]:hover{background:@hover;color:@ink1;} QPushButton[role=\"flat\"]:checked{background:@accentSoft;color:@ink1;border-color:@accentLine;}"
   "QPushButton[role=\"accent\"]:enabled{background:@accentSoft;border-color:@accentLine;color:@ink1;font-weight:600;}"
   "QPushButton[role=\"accent\"]:enabled:hover{border-color:@accent;}"
   // 输入控件
   "QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit{background:@inset;border:1px solid @line2;border-radius:6px;padding:3px 8px;min-height:20px;}"
   "QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QLineEdit:focus{border-color:@accent;}"
   "QComboBox:disabled,QSpinBox:disabled,QDoubleSpinBox:disabled{color:@ink3;border-color:@line;}"
   "QComboBox::drop-down{border:none;width:20px;}"
   "QComboBox QAbstractItemView{background:@panel;border:1px solid @line2;selection-background-color:@accentSoft;selection-color:@ink1;outline:0;padding:2px;}"
   "QSpinBox::up-button,QDoubleSpinBox::up-button,QSpinBox::down-button,QDoubleSpinBox::down-button{width:14px;border:none;background:transparent;}"
   "QAbstractItemView{background:@inset;alternate-background-color:@panel;} QHeaderView::section{background:@hover;border:none;padding:4px;color:@ink2;}"
   "QGroupBox{border:1px solid @line;border-radius:8px;margin-top:16px;padding:10px 8px 8px 8px;background:@inset;}"
   "QGroupBox::title{subcontrol-origin:margin;left:8px;padding:0 4px;color:@ink2;}"
   "QWidget#inspector QGroupBox{border:none;border-top:1px solid @line;border-radius:0;background:transparent;margin-top:18px;padding:8px 0 0 0;}"
   "QWidget#inspector QGroupBox::title{left:0;padding:0;color:@ink3;font-size:11px;}"
   "QCheckBox{spacing:7px;color:@ink1;min-height:20px;} QCheckBox:disabled{color:@ink3;}"
   "QCheckBox::indicator{width:14px;height:14px;border:1px solid @line2;border-radius:4px;background:@inset;}"
   "QCheckBox::indicator:hover{border-color:@accent;}"
   "QCheckBox::indicator:checked{background:@accent;border-color:@accent;%1}"
   "QCheckBox::indicator:disabled{background:@hover;border-color:@line;} QCheckBox::indicator:checked:disabled{background:@accentLine;border-color:@accentLine;}"
   "QSlider{min-height:18px;}"
   "QSlider::groove:horizontal{height:4px;background:@line2;border-radius:2px;} QSlider::sub-page:horizontal{background:@accent;border-radius:2px;}"
   "QSlider::handle:horizontal{background:#ffffff;border:2px solid @accent;width:10px;height:10px;margin:-5px 0;border-radius:7px;}"
   "QSlider::sub-page:horizontal:disabled{background:@line2;}"
   "QProgressBar{background:@line;border:none;border-radius:3px;} QProgressBar::chunk{background:@accent;border-radius:3px;}"
   "QPlainTextEdit{background:@inset;border:1px solid @line;border-radius:8px;color:@ink2;font-size:11px;padding:4px;}"
   "QScrollBar:vertical{background:transparent;width:8px;margin:2px;} QScrollBar:horizontal{background:transparent;height:8px;margin:2px;}"
   "QScrollBar::handle:vertical{background:@line2;border-radius:3px;min-height:24px;} QScrollBar::handle:horizontal{background:@line2;border-radius:3px;min-width:24px;}"
   "QScrollBar::add-line,QScrollBar::sub-line{width:0;height:0;} QScrollBar::add-page,QScrollBar::sub-page{background:none;}"
   "QMenu{background:@panel;border:1px solid @line2;} QMenu::item:selected{background:@accentSoft;}"
   // 底部状态栏与状态点
   "QFrame#statusBar{background:@bar;border-top:1px solid @line;}"
   "QLabel#stateDot{border-radius:4px;background:@ok;} QLabel#stateDot[busy=\"true\"]{background:@accent;}"
   "QFrame[frameShape=\"4\"]{color:@line;}").arg(checkRule);
  // 先替换较长的名字，避免 @accent 截断 @accentHover 等
  auto tokens=themeTokens(light);QStringList keys=tokens.keys();std::sort(keys.begin(),keys.end(),[](const QString&x,const QString&y){return x.size()>y.size();});
  for(const auto&k:keys)sheet.replace("@"+k,tokens[k]);
  return sheet;
 }
QString  virtualPresetCT;
void applySimplification(){preciseBlend->setText(u("高质量透明（PL）"));scopeQuality->setCurrentIndex(1);scopeQuality->setItemText(1,u("自动 384→640"));exposureToggle->setText(u("曝光校正（可选）"));compareButton->setText(u("比较器械可达性"));}
void showPlanningSummary(){
  auto nav=scene["navigation"].toObject();auto profiles=nav["whole_instrument_profiles"].toObject()["profiles"].toArray();
  auto groups=nav["whole_alternative_routes"].toObject()["groups"].toArray();
  QDialog dialog(this);dialog.setWindowTitle(u("器械与推荐路径摘要"));dialog.resize(720,360);auto*layout=new QVBoxLayout(&dialog);
  auto*hint=new QLabel(u("展示已有比较结果。更换器械后，请重新规划；导航仍执行管径、连续净空和弯曲约束审核。"));hint->setWordWrap(true);layout->addWidget(hint);
  auto*table=new QTableWidget(profiles.size(),4);table->setHorizontalHeaderLabels({u("器械直径 mm"),u("可达总长 mm"),u("推荐路径长 mm"),u("最窄几何直径 mm")});
  table->setEditTriggers(QAbstractItemView::NoEditTriggers);table->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch);layout->addWidget(table,1);
  auto number=[](QJsonValue value){return value.isDouble()?QString::number(value.toDouble(),'f',1):QString::fromUtf8("—");};
  for(int i=0;i<profiles.size();++i){auto profile=profiles[i].toObject();QJsonObject best;
   for(auto value:groups){auto group=value.toObject();if(std::abs(group["scope_diameter_mm"].toDouble()-profile["scope_diameter_mm"].toDouble())>1e-6)continue;
    int selected=group["selected_candidate_id"].toInt(-1);for(auto candidate:group["candidates"].toArray())if(candidate.toObject()["candidate_id"].toInt(-2)==selected)best=candidate.toObject();}
   QStringList values={number(profile["scope_diameter_mm"]),number(profile["reachable_centerline_length_mm"]),number(best.isEmpty()?profile["path_length_to_closest_point_mm"]:best["path_length_mm"]),number(best["minimum_diameter_mm"])};
   for(int k=0;k<values.size();++k)table->setItem(i,k,new QTableWidgetItem(values[k]));
  }
  auto*close=new QPushButton(u("关闭"));layout->addWidget(close);connect(close,&QPushButton::clicked,&dialog,&QDialog::accept);dialog.exec();
 }
void applyVirtualCasePreset(){
  if(input.isEmpty()||virtualPresetCT==input)return;
  QString manifest=QFileInfo(input).dir().absoluteFilePath("synthetic_case.json");
  if(!QFileInfo::exists(manifest))return;
  try{
   auto data=readJson(manifest);
   if((data["schema"]!="kv260.synthetic.wall_lesion.v1"&&data["schema"]!="kv260.synthetic.wall_lesion.v2")||data["ct_sha256"]!=scene["input_sha256"])return;
   virtualPresetCT=input;{QSignalBlocker blocker(minimumCandidateVolume);minimumCandidateVolume->setValue(0);}
   if(data["recommended_scope_diameter_mm"].isDouble()){QSignalBlocker blocker(diameter);diameter->setValue(data["recommended_scope_diameter_mm"].toDouble());}
   if(data["safety_margin_mm"].isDouble()){QSignalBlocker blocker(margin);margin->setValue(data["safety_margin_mm"].toDouble());}
   caseLabel->setToolTip(u("模拟管壁病灶病例：外部真值标签与模型推理结果分别记录。"));
   info->setText(info->text()+u("\n模拟管壁病灶 · 候选体积筛选已设为0"));
  }catch(const std::exception&e){message(u("模拟病例元数据无效：")+QString::fromUtf8(e.what()));}
 }
public:
void finishControlCheck(){
  // Drain transport QObjects while their QWidget parent is still fully alive.
  // Their destructors use an event loop; QWidget teardown must not own it.
  heartbeat.stop();compositeQuiet.stop();compositeCheck.stop();
  scope->onPoseChanged={};scope->onPlPresented={};overview->onOverviewChanged={};
  if(plScope){plScope->onFrame={};plScope->onStatus={};delete plScope;plScope=nullptr;}
  if(plComposite){plComposite->onFrame={};plComposite->onStatus={};delete plComposite;plComposite=nullptr;}
 }
QJsonObject simplificationCheck()const{QStringList retired={"PL_airway_cleanup_open","HU_airway_open","mask_evaluation_open","PL_segmentation_only","overview_outline_glow"};QJsonObject checks;for(auto name:retired)checks[name+"_absent"]=findChild<QWidget*>(name)==nullptr;checks["three_pages"]=tabs->count()==3;checks["external_import"]=importButton&&!importButton->isHidden();checks["PL_transparency"]=preciseBlend!=nullptr;checks["PNG_and_MP4"]=snapshotButton&&videoButton;checks["automatic_preview"]=findChild<QCheckBox*>("fastTransparency")==nullptr;bool passed=true;for(auto value:checks)passed=passed&&value.toBool();return {{"passed",passed},{"checks",checks},{"retired_implementations_compiled",false},{"new_bitstream",false}};}
private:
QString  compositeSourceScene,compositeExpectedAttributeSHA;
int  rejectedCompositeAttributeFrames=0;
QJsonObject  compositeAttributeBinding;
bool compositeAttributeFrameMatches(const QJsonObject&meta)const{
  auto report=meta["report"].toObject();int mode=report["controls"].toObject()["color_mode"].toInt(-1);
  return meta["scene"].toString()==(compositeSourceScene.isEmpty()?scenePath:compositeSourceScene)&&
   mode==(colorMode?colorMode->currentIndex():0)&&(!mode||report["analysis_attributes_sha256"].toString()==compositeExpectedAttributeSHA);
 }
bool bindCompositeSampling(){QString expected,nearest=nearestAttributeFile();if(!nearest.isEmpty())expected=composite_sampling::hash(nearest);bool changed=scenePath!=compositeSourceScene||expected!=compositeExpectedAttributeSHA;compositeSourceScene=scenePath;compositeExpectedAttributeSHA=expected;compositeAttributeBinding={{"policy","nearest"},{"scene",scenePath},{"attribute_file",nearest},{"attribute_SHA256",expected}};if(changed&&overview)overview->invalidateCompositeFrame();return changed;}
QJsonObject attributeMediaBinding()const{auto nearest=nearestAttributeFile();return {{"schema","kv260.media.attribute_sampling.r50"},{"scene",scenePath},{"policy",nearest.isEmpty()?"unavailable":"nearest"},{"nearest_file",nearest},{"display_file",nearest},{"reachability_file",nearest},{"binding",QString()},{"binding_sha256",QString()},{"current_display_file",overview?overview->airwayAttributeFile():QString()},{"current_color_mode",colorMode?colorMode->currentIndex():0}};}
static void appendAttributeMediaPaths(QStringList&paths,QJsonObject sampling){
  for(auto key:{"nearest_file","display_file","binding"}){QString path=sampling[key].toString();if(!path.isEmpty()&&!paths.contains(path))paths<<path;}
 }
QString nearestAttributeFile()const{
  auto a=scene["meshes"].toObject()["airway"].toObject()["attributes"].toObject();
  return a.isEmpty()?QString():QFileInfo(scenePath).dir().absoluteFilePath(a["file"].toString());
 }
void resetAttributeSampling(){applyAttributeSampling();}
void applyAttributeSampling(){if(!overview)return;bool changed=bindCompositeSampling();QString path=nearestAttributeFile();for(auto*v:{overview,miniOverview})if(v){v->setAttributeSamplingSources(path,path,false,"nearest");if(!path.isEmpty()&&!v->setAirwayAttributeFile(path))throw std::runtime_error("Invalid nearest airway attribute stream");}if(changed&&overview->compositeMode())configureScope();}
live_exposure::Overlay *exposureOverlay=nullptr;
std::unique_ptr<endoscope_exposure::Processor> exposureProcessor;
QCheckBox *exposureToggle=nullptr;
QLabel *exposureStatus=nullptr;
bool exposureRequested()const{return exposureToggle&&exposureToggle->isChecked();}
void syncExposure(){
  if(!exposureToggle)return;
  const bool blocked=closing||sceneLoading||graphicsTransition||
   utilityProcess.state()!=QProcess::NotRunning||prepareProcess.state()!=QProcess::NotRunning||jobProcess.state()!=QProcess::NotRunning;
  const bool available=exposureOverlay&&exposureProcessor&&!blocked&&scope->cameraCount()>0;
  exposureToggle->setEnabled(available);
  const bool active=available&&tabs->currentIndex()==2&&exposureRequested()&&!scope->presentedScopeFrame().isEmpty();
  if(exposureOverlay&&exposureOverlay->enabled()!=active)exposureOverlay->setEnabled(active);
  if(!active)exposureStatus->setText(!exposureProcessor?u("曝光未就绪"):!exposureRequested()?u("原始亮度"):u("等待导航完成帧"));
 }
QJsonObject exposureMetrics()const{
  auto value=exposureOverlay?exposureOverlay->stats():QJsonObject{};
  value["requested"]=exposureRequested();value["backend"]="explicit_PS4_original_endoscope_exposure";
  value["same_operation_for_live_and_export"]=true;value["source_masks_geometry_and_route_changed"]=false;
  value["presented_scope_sequence"]=scope->presentedScopeFrame()["sequence"];
  return value;
 }
QImage applyEndoscopeExposure(const QImage& image,QString context={}){
  if(!exposureRequested())return image;
  if(!exposureProcessor)throw std::runtime_error("Qualified endoscope exposure is unavailable");
  auto output=exposureProcessor->apply(image);return output;
 }
void installExposure(QHBoxLayout*layout){
  exposureToggle=new QCheckBox(u("气镜曝光（PS 四核）"));exposureToggle->setObjectName("endoscope_exposure");exposureToggle->setChecked(true);
  exposureToggle->setToolTip(u("原Python的全画面亮度校正和镜头暗角；仅改变显示，截图、视频和批量气镜图片使用同一算法。"));
  exposureStatus=new QLabel(u("等待导航完成帧"));exposureStatus->setObjectName("endoscope_exposure_status");
  exposureStatus->setFixedHeight(exposureStatus->fontMetrics().height()+4);exposureStatus->setSizePolicy(QSizePolicy::Ignored,QSizePolicy::Fixed);
  layout->addWidget(exposureToggle);layout->addWidget(exposureStatus,1);
  try{
   QString directory=root+"/modules/endoscope_exposure/build_ARM";auto proof=readJson(directory+"/compile_receipt.json");
   if(!proof["passed"].toBool()||!proof["actual_test_passed"].toBool())throw std::runtime_error("Unqualified endoscope exposure library");
   auto processor=std::make_unique<endoscope_exposure::Processor>(directory+"/libendoscope_exposure.so",proof["native_SHA256"].toString());
   exposureOverlay=new live_exposure::Overlay(scope,directory+"/libendoscope_exposure.so",proof["native_SHA256"].toString());exposureProcessor=std::move(processor);
   exposureOverlay->onStatus=[this](bool ok,QString text){exposureStatus->setText(ok?u("PS 四核 · ")+text:u("曝光错误：")+text);exposureStatus->setToolTip(text);};
  }catch(const std::exception&e){exposureStatus->setText(u("曝光未就绪"));exposureToggle->setToolTip(QString::fromUtf8(e.what()));}
  connect(exposureToggle,&QCheckBox::toggled,this,[this]{syncExposure();});
  connect(tabs,&QTabWidget::currentChanged,this,[this]{syncExposure();});syncExposure();
  
 }
void exposureFrameArrived(){if(exposureOverlay)exposureOverlay->invalidate();}
void exposureFramePresented(){syncExposure();if(exposureOverlay&&exposureOverlay->enabled())exposureOverlay->invalidate();}
QLabel *segmentationInfo=nullptr;
QTimer  segmentationPoll;
QString  runningMode,runningStage;
int  runningRepeats=1;
void pollSegmentationStatus(){
  if(!segmentationInfo||jobProcess.state()==QProcess::NotRunning||(runningMode!="all"&&runningMode!="segmentation")||runningStage!="segmentation"||runOutput.isEmpty())return;
  auto process=segmentation_status::object(runOutput+"/segmentation_process.json");int pid=0;
  if(!segmentation_status::integer(process["PID"],2,2147483647,pid))return;
  double startTicks=0.;if(!segmentation_status::nonnegative(process["start_ticks"],startTicks)||startTicks<=0.||std::floor(startTicks)!=startTicks)return;
  auto status=segmentation_status::object(runOutput+"/segmentation/status.json");QString text;int done=0,total=0;
  if(segmentation_status::progress(status,pid,runningRepeats,text,done,total,startTicks)){
   segmentationInfo->setText(text);if(total>0){progress->setRange(0,total);progress->setValue(done);}
  }
 }
void showSegmentationSummary(){
  if(!segmentationInfo)return;
  auto report=source.isEmpty()?QJsonObject{}:segmentation_status::object(source+"/segmentation/report.json",1024*1024);
  QString text=segmentation_status::summary(report,scene["input_sha256"].toString());
  segmentationInfo->setText(text.isEmpty()?u("混合分割：PL HU/卷积＋PS层间算子与气道清理；不生成网格或导航。"):text);
 }
QLabel *structureAvailability=nullptr;
bool  sceneLoading=false;
std::thread  sceneLoader;
std::shared_ptr<Volume>  readyVolume;
QJsonObject  readyMeta;
QString  readyPath;
void preparedSceneFinished(int rc){try{if(rc||pendingResult.isEmpty())throw std::runtime_error((errors.isEmpty()?u("病例载入失败，请查看日志"):errors).toStdString());loadScene(pendingResult);}catch(const std::exception&e){failed=true;qCritical()<<"Scene preparation failed"<<e.what();message(QString::fromUtf8(e.what()));progress->setRange(0,100);progress->setValue(0);}busy(false);if(!failed)configureScope();qInfo()<<"R2277 prepare finished"<<rc<<"failed"<<failed;if(compositeTesting){if(failed)finishTest();else compositeCheck.start(150);}else if(smoke){if(failed)finishTest();else QTimer::singleShot(600,this,[this]{smokeAdvance();});}}
void prepareSceneInBackground(int rc){
  if(rc||pendingResult.isEmpty()){preparedSceneFinished(rc);return;}
  if(sceneLoader.joinable())sceneLoader.join();
  sceneLoading=true;busy(true);QString path=pendingResult;
  sceneLoader=std::thread([this,path,rc]{
   std::shared_ptr<Volume> mapped;QJsonObject meta;QString error;
   try{meta=readJson(path);mapped=std::make_shared<Volume>();mapped->load(path,meta);
    auto*gui=QCoreApplication::instance()->thread();mapped->ctFile.moveToThread(gui);mapped->maskFile.moveToThread(gui);
   }catch(const std::exception&e){error=QString::fromUtf8(e.what());mapped.reset();}
   QMetaObject::invokeMethod(this,[this,path,rc,mapped,meta,error]{
    if(sceneLoader.joinable())sceneLoader.join();
    sceneLoading=false;readyVolume=mapped;readyMeta=meta;readyPath=path;
    if(!error.isEmpty()){errors+=error;preparedSceneFinished(1);}else preparedSceneFinished(rc);
   },Qt::QueuedConnection);
  });
 }
bool  freshRawSeen=false,freshRawInitialVerified=false;
QString  root,input,source,scenePath,runOutput,pendingResult,stopFile;
QJsonObject  scene;
QPushButton *importButton=nullptr;
QPushButton *snapshotButton=nullptr;
bool  capturePending=false,captureRunning=false;
QElapsedTimer  captureWait;
std::thread  captureThread;
int capturePollCount=0,captureRetryCount=0;
QJsonArray captureRetries;
QJsonObject  captureLastResult;
QString  captureLastError;
int  captureSerial=0;
void captureRequest(){
  if(processing()||capturePending||input.isEmpty())return;
  capturePending=true;capturePollCount=captureRetryCount=0;captureRetries={};captureWait.start();snapshotButton->setEnabled(false);capturePoll();
 }
void captureReject(QString why){
  capturePending=false;captureLastError=why;++captureSerial;
  
  snapshotButton->setEnabled(!input.isEmpty());message(why);
  
 }
void capturePoll(){
  if(!capturePending)return;++capturePollCount;
  if(closing||failed||captureWait.elapsed()>180000){captureReject(u("显示未就绪，截图未保存"));return;}
  int page=tabs->currentIndex();bool precise=page==1&&overview->compositeMode()&&!overview->compositePreviewMode();
  auto completed=overview->completedComposite();
  if(precise&&(completed.isEmpty()||!compositeAttributeFrameMatches(completed)||overview->completedCompositeImage().isNull())){
   // Only configureScope may ignore this capture wait. All other operations
   // still see processing()==true, including file/scene changes.
   if(!graphicsTransition&&(!plComposite||!plComposite->active()))configureScope();
   if(!graphicsTransition&&(!plComposite||!plComposite->active())){captureReject(u("PL 精确透明未就绪，截图未保存"));return;}
   if(captureWait.elapsed()>1000)message(u("正在等待所选属性的 PL 精确透明帧，完成后保存截图"));
   QTimer::singleShot(50,this,[this]{capturePoll();});return;
  }
  if(page==2&&scope->cameraCount()>0&&scope->presentedScopeFrame().isEmpty()){
   if(!graphicsTransition&&(!plScope||!plScope->active()))configureScope();
   if(!graphicsTransition&&(!plScope||!plScope->active())){captureReject(u("导航显示未就绪，截图未保存"));return;}
   if(captureWait.elapsed()>5000)message(u("正在等待导航首帧，完成后保存截图"));
   QTimer::singleShot(100,this,[this]{capturePoll();});return;
  }
  if(page==2&&exposureRequested()&&exposureOverlay&&exposureOverlay->enabled()&&!exposureOverlay->ready()){
   auto error=exposureOverlay->stats()["error"].toString();
   if(!error.isEmpty()){captureReject(u("曝光未完成，截图未保存：")+error);return;}
   if(captureWait.elapsed()>5000)message(u("正在等待当前镜头曝光校正，完成后保存截图"));
   QTimer::singleShot(50,this,[this]{capturePoll();});return;
  }
  auto scopeBefore=scope->presentedScopeFrame();auto blendBefore=overview->completedComposite();
  auto requestBefore=overview->overviewRequest();auto samplingBefore=attributeMediaBinding();
  bool previewBefore=overview->compositePreviewMode();
  QImage native=precise?overview->completedCompositeImage():QImage();
  QMap<QString,QImage> images{{"window",grab().toImage()},{"active_view",tabs->currentWidget()->grab().toImage()}};
  auto scopeAfter=scope->presentedScopeFrame();auto blendAfter=overview->completedComposite();
  if(tabs->currentIndex()!=page||scopeBefore!=scopeAfter||blendBefore!=blendAfter||
     samplingBefore!=attributeMediaBinding()||requestBefore!=overview->overviewRequest()||previewBefore!=overview->compositePreviewMode()){
   ++captureRetryCount;
   if(captureRetries.size()<3)captureRetries.append(QJsonObject{{"page_changed",tabs->currentIndex()!=page},{"scope_changed",scopeBefore!=scopeAfter},
    {"C7_changed",blendBefore!=blendAfter},{"sampling_changed",samplingBefore!=attributeMediaBinding()},
    {"request_before",requestBefore},{"request_after",overview->overviewRequest()},
    {"preview_changed",previewBefore!=overview->compositePreviewMode()}});
   QTimer::singleShot(50,this,[this]{capturePoll();});return;
  }
  QString backend=page==0?"PS_CT_slice":page==2?"PL_navigation_PS_GPU_shading":
    precise?"PL_C7_precise":previewBefore?"PS_GPU_interactive_preview":"PS_GPU_overview";
  QJsonObject boundary{{"schema","kv260.capture.render_boundary.r52"},{"backend",backend},
   {"selected_attribute_binding",compositeAttributeBinding},{"pending_overview_request",requestBefore},
   {"completed_C7_before",page==1&&precise?blendBefore:QJsonObject()},
   {"completed_C7_after",page==1&&precise?blendAfter:QJsonObject()},
   {"current_binding_matches_completed_C7",precise&&compositeAttributeFrameMatches(blendBefore)},
   {"snapshot_wait_ms",double(captureWait.elapsed())},{"capture_polls",capturePollCount},{"capture_retries",captureRetryCount},{"GPU_preview_is_not_PL",previewBefore},
   {"native_C7_RGBA_pixel_SHA256",native.isNull()?QString():medical_capture::pixelHash(native)},
   {"native_C7_row_order",native.isNull()?QString():QString("GLES_bottom_left")},
   {"source_scene_SHA256",page==1?composite_sampling::hash(compositeSourceScene.isEmpty()?scenePath:compositeSourceScene):QString()}};
  // The test preserves the exact native PL image as a separate oracle. Normal
  // user captures keep only the requested window and active-view PNG files.
  
  QJsonObject meta{{"input",input},{"input_sha256",scene["input_sha256"]},{"source_result",source},
   {"tab_index",page},{"tab_name",tabs->tabText(page)},
   {"slice_indices",QJsonArray{slices[0]->currentSlice(),slices[1]->currentSlice(),slices[2]->currentSlice()}},
   {"overview_camera",overview->overviewCamera()},{"overview_camera_is_pending_controls",true},
   {"render_boundary",boundary},{"presented_scope_before_capture",scopeBefore},{"presented_scope_after_capture",scopeAfter},
   {"scope_pose_metadata_is_capture_boundary",true},{"attribute_sampling",samplingBefore},
   {"endoscope_exposure",exposureMetrics()},{"navigation_available",scope->cameraCount()>0},{"display_only",true},
   {"source_masks_geometry_and_route_changed",false}};
  capturePending=false;captureRunning=true;QString destination=root+"/ui/exports/snapshots";int startTick=ticks;
  captureThread=std::thread([this,images,meta,destination,startTick]{
   QJsonObject result;QString error;
   try{result=medical_capture::save(destination,images,meta);}catch(const std::exception&e){error=QString::fromUtf8(e.what());}
   QMetaObject::invokeMethod(this,[this,result,error,startTick]{
    if(captureThread.joinable())captureThread.join();captureRunning=false;
    captureLastResult=result;captureLastError=error;++captureSerial;snapshotButton->setEnabled(!input.isEmpty());
    if(!error.isEmpty()){message(error);return;}
    message(u("截图已保存至 ")+result["path"].toString());
    // The quiet timer can expire while PNG writing is in flight. Resume the
    // selected precise owner after the write instead of leaving preview stuck.
    configureScope();
    
   },Qt::QueuedConnection);
  });
 }
QString  mediaRestoreAction;
QJsonObject  videoLastReceipt;
int  videoReceiptSerial=0;
std::thread  videoIntegrityThread;
bool  videoIntegrityPreparing=false,videoIntegrityFinalizing=false,videoIntegrityChecked=false;
QString  videoMovieSHA;
QJsonObject  videoIntegrityMetrics;
QPushButton *videoButton=nullptr;
QProgressDialog *videoProgress=nullptr;
bool  videoPending=false,videoRunning=false,videoEnding=false,videoAwaiting=false,videoEncoding=false,videoCancelled=false,videoDrained=false,videoEncoderDone=false;
std::unique_ptr<navigation_media::Timeline>  videoPlan;
std::unique_ptr<navigation_media::Encoder>  videoEncoder;
int  videoIndex=0,videoRendered=0,videoFPS=24,videoSavedTab=2,videoSavedQuality=0;
double  videoSpeed=18;
bool  videoLinked=false;
QSize  videoPaneSize{1280,720};
QJsonObject  videoSavedOverviewCamera;
QSize  videoSize{1280,720};
QString  videoDirectory,videoFinalDirectory,videoError;
QElapsedTimer  videoClock;
QJsonArray  videoTrace;
QJsonObject  videoSources,videoSavedCamera,videoSavedRequest,videoLastMeta;
QJsonObject  videoActiveBinding,videoAttributeSampling;
QImage  videoLastImage;
QByteArray  videoDepth,videoNormal;
bool  videoSavedPlaying=false,videoSavedDual=false,videoCancelledAtPL=false;
int  videoTestPhase=0;
QTimer  videoWatchdog;
QElapsedTimer  videoProgressClock;
int  videoStartTick=0;
QString videoProgressHash(QString path,qint64&processed,QElapsedTimer&notify,bool preparing){
  return navigation_media::streamingFileSHA256(path,[this,&processed,&notify,preparing](qint64 count){
   processed+=count;if(notify.elapsed()<150)return;notify.restart();const qint64 bytes=processed;
   QMetaObject::invokeMethod(this,[this,bytes,preparing]{
    if(videoProgress&&(preparing?videoIntegrityPreparing:videoIntegrityFinalizing))
     videoProgress->setLabelText(QString(preparing?u("正在流式校验输入 · 已读取 %1 MiB"):u("正在流式复核文件 · 已读取 %1 MiB")).arg(bytes/1048576.,0,'f',1));
   },Qt::QueuedConnection);
  });
 }
bool videoAvailable()const{return !processing()&&!source.isEmpty()&&scope->cameraCount()>1&&scope->totalDistance()>0&&QFileInfo::exists((!scene.value("complete_surface").toObject().isEmpty())?scene["complete_surface"].toObject()["bundle"].toString()+"/route.json":source+"/navigation/route.json");}
void videoRequest(){
  if(!videoAvailable())return;
  QDialog setup(this);setup.setWindowTitle(u("导出当前导航路径"));auto*layout=new QVBoxLayout(&setup);auto*form=new QFormLayout;
  QSpinBox fps;fps.setObjectName("exportFPS");fps.setRange(1,60);fps.setValue(24);QDoubleSpinBox speed;speed.setObjectName("exportSpeed");speed.setRange(.25,100);speed.setDecimals(2);speed.setValue(18);speed.setSuffix(" mm/s");
  QComboBox size;size.setObjectName("exportSize");size.addItems({"1280 × 720","640 × 360"});form->addRow(u("视频帧率"),&fps);form->addRow(u("路径速度"),&speed);form->addRow(u("保存尺寸"),&size);layout->addLayout(form);QCheckBox linked(u("同时保存联动总览（左总览 / 右气镜）"));linked.setObjectName("exportLinked");layout->addWidget(&linked);
  auto*note=new QLabel(u("沿当前完整路径逐帧保存，期间可取消。\n每个视图原生计算 640×360；保存尺寸按单个视图设置。\n视频帧率代表回放速度，联动视频总宽度为两倍。"));note->setWordWrap(true);layout->addWidget(note);
  QDialogButtonBox buttons(QDialogButtonBox::Ok|QDialogButtonBox::Cancel);buttons.button(QDialogButtonBox::Ok)->setText(u("开始导出"));buttons.button(QDialogButtonBox::Cancel)->setText(u("返回"));layout->addWidget(&buttons);
  connect(&buttons,&QDialogButtonBox::accepted,&setup,&QDialog::accept);connect(&buttons,&QDialogButtonBox::rejected,&setup,&QDialog::reject);
  
  
  if(setup.exec()!=QDialog::Accepted){return;}
  videoFPS=fps.value();videoSpeed=speed.value();videoLinked=linked.isChecked();videoPaneSize=size.currentIndex()==0?QSize(1280,720):QSize(640,360);videoSize=QSize(videoPaneSize.width()*(videoLinked?2:1),videoPaneSize.height());
  try{
   videoSavedPlaying=playing;videoSavedOverviewCamera=miniOverview->overviewCamera();
   videoSavedCamera=scope->scopeViewState();videoSavedRequest=scope->cameraRequest();videoSavedTab=tabs->currentIndex();videoSavedQuality=scopeQuality->currentIndex();videoSavedDual=dualCheck->isChecked();
   videoPlan=std::make_unique<navigation_media::Timeline>(scope->totalDistance(),videoFPS,videoSpeed);
   videoSources={};videoActiveBinding={};
   QString id=QDateTime::currentDateTimeUtc().toString("yyyyMMdd_HHmmss_zzz")+"_"+QUuid::createUuid().toString(QUuid::Id128).left(8);
   videoFinalDirectory=root+"/ui/exports/navigation_media/"+id;videoDirectory=videoFinalDirectory+".pending";
   if(QFileInfo::exists(videoDirectory)||!QDir().mkpath(videoDirectory))throw std::runtime_error("Cannot create video destination");
   navigationPause();videoPending=true;videoRunning=videoEnding=videoAwaiting=videoEncoding=videoCancelled=videoDrained=videoEncoderDone=false;
   videoCancelledAtPL=false;videoIndex=videoRendered=0;videoTrace={};videoLastMeta={};videoError.clear();videoClock.start();videoProgressClock.start();videoStartTick=ticks;
   videoWatchdog.setInterval(1000);disconnect(&videoWatchdog,nullptr,this,nullptr);connect(&videoWatchdog,&QTimer::timeout,this,[this]{if(!videoEnding&&videoProgressClock.elapsed()>60000)videoEnd(u("当前导出步骤等待超过 60 秒，正在安全恢复"));});videoWatchdog.start();
   videoProgress=new QProgressDialog(u("正在准备导航视频"),u("取消导出"),0,videoPlan->total(),this);videoProgress->setRange(0,0);videoProgress->setWindowTitle(u("保存导航视频"));videoProgress->setWindowModality(Qt::WindowModal);videoProgress->setAutoClose(false);videoProgress->setAutoReset(false);videoProgress->setMinimumDuration(0);videoProgress->show();
   connect(videoProgress,&QProgressDialog::canceled,this,[this]{videoCancel();});
   videoPrepareIntegrity();
  }catch(const std::exception&e){message(QString::fromUtf8(e.what()));}
 }
void videoPrepareIntegrity(){
  videoAttributeSampling=attributeMediaBinding();videoIntegrityPreparing=true;videoIntegrityChecked=false;videoMovieSHA.clear();videoIntegrityMetrics={};
  const auto savedScene=scene;const QString savedRoot=root,savedScenePath=scenePath,savedSource=source;
  const int tickStart=ticks,gapStart=gaps.size();const auto begin=std::chrono::steady_clock::now();
  videoProgress->setLabelText(u("正在后台校验视频输入"));busy(true);
  const auto sampling=videoAttributeSampling;
  videoIntegrityThread=std::thread([this,sampling,savedScene,savedRoot,savedScenePath,savedSource,tickStart,gapStart,begin]{
   QJsonObject sources,binding;QString error;qint64 processed=0;QElapsedTimer notify;notify.start();
   try{
    if(!savedScene.value("complete_surface").toObject().isEmpty())binding=navigation_media::activeVideoBinding(savedRoot,savedScenePath,savedScene,sources,[this,&processed,&notify](QString path){return videoProgressHash(path,processed,notify,true);});
    else for(QString path:{savedScenePath,savedSource+"/navigation/route.json",savedSource+"/segmentation/airway_mask.nii.gz",savedRoot+"/dfx/surface/release/manifest.json"})sources[path]=videoProgressHash(path,processed,notify,true);
    QStringList extra;appendAttributeMediaPaths(extra,sampling);for(auto path:extra)sources[path]=videoProgressHash(path,processed,notify,true);
   }catch(const std::exception&e){error=QString::fromUtf8(e.what());}
   double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
   QMetaObject::invokeMethod(this,[this,sources,binding,error,seconds,tickStart,gapStart,processed]{
    videoIntegrityThread.join();videoIntegrityPreparing=false;
    double gap=0;for(int i=gapStart;i<gaps.size();++i)gap=qMax(gap,double(gaps.at(i)));
    videoIntegrityMetrics["prepare_hashed_bytes"]=double(processed);videoIntegrityMetrics["hash_backend"]="OpenSSL3_EVP_SHA256_streaming";videoIntegrityMetrics["prepare_seconds"]=seconds;videoIntegrityMetrics["prepare_heartbeat_ticks"]=ticks-tickStart;videoIntegrityMetrics["prepare_heartbeat_max_ms"]=gap;
    videoSources=sources;videoActiveBinding=binding;videoProgressClock.restart();
    if(!error.isEmpty()){videoPending=false;videoEnd(error);return;}
    releaseGraphics([this]{videoBegin();});
   },Qt::QueuedConnection);
  });
 }
void videoFinishIntegrity(){
  videoIntegrityFinalizing=true;const auto sources=videoSources;const QString movie=videoDirectory+"/navigation.mp4";
  const int tickStart=ticks,gapStart=gaps.size();const auto begin=std::chrono::steady_clock::now();
  if(videoProgress)videoProgress->setLabelText(u("正在后台复核视频与输入文件"));
  videoIntegrityThread=std::thread([this,sources,movie,tickStart,gapStart,begin]{
   QString error,movieSHA;qint64 processed=0;QElapsedTimer notify;notify.start();
   try{
    for(auto it=sources.begin();it!=sources.end();++it)if(videoProgressHash(it.key(),processed,notify,false)!=it.value().toString())throw std::runtime_error("Source changed during video export");
    if(QFileInfo::exists(movie))movieSHA=videoProgressHash(movie,processed,notify,false);
   }catch(const std::exception&e){error=QString::fromUtf8(e.what());}
   double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
   QMetaObject::invokeMethod(this,[this,error,movieSHA,seconds,tickStart,gapStart,processed]{
    videoIntegrityThread.join();videoIntegrityFinalizing=false;videoIntegrityChecked=true;videoMovieSHA=movieSHA;
    double gap=0;for(int i=gapStart;i<gaps.size();++i)gap=qMax(gap,double(gaps.at(i)));
    videoIntegrityMetrics["finish_hashed_bytes"]=double(processed);videoIntegrityMetrics["finish_seconds"]=seconds;videoIntegrityMetrics["finish_heartbeat_ticks"]=ticks-tickStart;videoIntegrityMetrics["finish_heartbeat_max_ms"]=gap;
    if(!error.isEmpty()&&videoError.isEmpty())videoError=error;videoComplete();
   },Qt::QueuedConnection);
  });
 }
void videoBegin(){
  if(videoCancelled){videoPending=false;videoEncoderDone=true;videoEnd();return;}
  if(videoProgress){videoProgress->setRange(0,0);videoProgress->setLabelText(u("正在初始化导航并计算第一帧"));}
  videoPending=false;videoRunning=true;busy(true);scope->setEnabled(false);tabs->setCurrentIndex(2);scope->setManualNavigation(false);scope->setAutoAlign(false);scope->resetView();scope->setDistance(0);if(videoLinked)dualCheck->setChecked(true);
  videoEncoder=std::make_unique<navigation_media::Encoder>(this,videoDirectory+"/navigation.mp4",videoSize,videoFPS,
   [this](QString error){if(!error.isEmpty()){videoEncoderDone=true;videoEnd(error);return;}if(!videoEnding)videoSend(true);},
   [this](QString){videoProgressClock.restart();videoEncoding=false;++videoIndex;videoProgress->setRange(0,videoPlan->total());videoProgress->setValue(videoIndex);videoProgress->setLabelText(QString(u("已保存 %1 / %2 帧")).arg(videoIndex).arg(videoPlan->total()));
    
    if(!videoEnding)videoSend(false);},
   [this](QString error){videoEncoderDone=true;if(!error.isEmpty())videoEnd(error);videoComplete();},
   (false&&videoTestPhase==4)||(false&&mediaRestoreAction=="video_failure")?"/nonexistent/kv260_codec_failure_test":"/usr/bin/ffmpeg");
 }
void videoSend(bool first){
  try{if(videoEnding)return;if(videoCancelled){videoEnd();return;}if(videoIndex>=videoPlan->total()){videoEnd();return;}
  if(videoIndex>=videoPlan->moving){auto m=videoTrace.last().toObject();m["frame_index"]=videoIndex;m["hold"]=true;videoTrace.append(m);videoEncoding=true;videoEncoder->submit(videoLastImage);return;}
  scope->setDistance(videoPlan->arc(videoIndex));auto request=scope->cameraRequest();request["width"]=640;request["height"]=360;request["interactive"]=false;videoAwaiting=true;
  if(first){if(!videoActiveBinding.isEmpty())plScope->startScene(videoActiveBinding["bundle"].toString(),videoActiveBinding["revision"].toString(),request);
   else plScope->start(source,request);}else plScope->request(request);videoProgressClock.restart();
  }catch(const std::exception&e){videoEnd(QString::fromUtf8(e.what()));}
 }
void videoFrameReceived(const QImage&depth,const QImage&normal,QJsonObject meta){
  if(!videoRunning||videoEnding)return;
  if(!videoAwaiting||depth.size()!=QSize(640,360)||normal.size()!=depth.size()||meta["normal_computation"]!="PL"){videoEnd(u("导航视频收到未配对的 PL 帧"));return;}
  if(!videoActiveBinding.isEmpty()&&!navigation_media::activeVideoFrame(videoActiveBinding,meta)){videoEnd(u("视频收到其他表面或路径的帧"));return;}
  videoProgressClock.restart();videoLastMeta=meta;videoDepth=navigation_media::rgbaBytes(depth);videoNormal=navigation_media::rgbaBytes(normal);
 }
void videoPresented(){
  if(!videoRunning||videoEnding||!videoAwaiting||videoLastMeta.isEmpty())return;
  auto shown=scope->presentedScopeFrame();if(shown["sequence"]!=videoLastMeta["sequence"])return;
  if(shown["pose_source"]!="completed_PL_frame"||std::abs(shown["arc_mm"].toDouble()-videoPlan->arc(videoIndex))>.001){videoEnd(u("视频镜头与完成帧不一致"));return;}
  videoAwaiting=false;QTimer::singleShot(0,this,[this,shown]{
   if(videoEnding)return;
   try{
    auto native=applyEndoscopeExposure(scope->completedScopeColor(),"video");auto after=scope->presentedScopeFrame();if(after["sequence"]!=shown["sequence"])throw std::runtime_error("Video capture crossed a completed frame");
    auto hud=scene["navigation"].toObject()["hud"].toObject()["samples"].toArray();int at=scope->cameraForDistance(scope->distance());
    QJsonObject videoHUD=videoActiveBinding.isEmpty()?(at<hud.size()?hud[at].toObject():QJsonObject{}):shown["hud"].toObject();
    QJsonObject linkedProof;QImage overviewColor;
    if(videoLinked){miniOverview->setUpdatesEnabled(false);overviewColor=miniOverview->linkedOverviewColor(QSize(640,360),shown,linkedProof);}
    videoLastImage=videoLinked?navigation_media::linkedVideoFrame(overviewColor,native,videoPaneSize,shown,videoHUD,videoPlan->length):
      navigation_media::videoFrame(native,videoPaneSize,shown,videoHUD,videoPlan->length);
    QJsonObject meta=shown;meta["endoscope_exposure"]=exposureMetrics();QMap<QString,QByteArray> extra;QString png;
    QString stem=QString("reference_%1").arg(videoIndex,6,10,QChar('0'));
    if(videoIndex==0||videoIndex==videoPlan->moving/2||videoIndex==videoPlan->moving-1){
     meta["depth_reference"]=stem+".depth.rgba";meta["normal_reference"]=stem+".normal.rgba";extra[meta["depth_reference"].toString()]=videoDepth;extra[meta["normal_reference"].toString()]=videoNormal;png=stem+".png";if(videoLinked){meta["overview_reference"]=stem+".overview.rgba";extra[meta["overview_reference"].toString()]=navigation_media::rgbaBytes(overviewColor);}
    }
    auto hash=[](QByteArray b){return QString::fromLatin1(QCryptographicHash::hash(b,QCryptographicHash::Sha256).toHex());};
    QJsonObject row{{"frame_index",videoIndex},{"arc_mm",videoPlan->arc(videoIndex)},{"hold",false},{"completed_frame",meta},
      {"captured_pixel_sha256",medical_capture::pixelHash(videoLastImage)},{"raw_depth_outline_sha256",hash(videoDepth)},{"raw_normal_sha256",hash(videoNormal)},
      {"native_color_sha256",medical_capture::pixelHash(native)},{"source_capture_size",QJsonArray{640,360}},{"fitted_capture_size",QJsonArray{videoSize.width(),videoSize.height()}}};
    if(videoLinked){row["linked_overview"]=linkedProof;row["overview_color_sha256"]=medical_capture::pixelHash(overviewColor);}
    if(!png.isEmpty())row["reference_png"]=png;videoTrace.append(row);++videoRendered;videoEncoding=true;
    videoEncoder->submit(videoLastImage,extra,png);
   }catch(const std::exception&e){videoEnd(QString::fromUtf8(e.what()));}
  });
 }
void videoCancel(){
  if(!videoPending&&!videoRunning)return;videoCancelledAtPL=videoAwaiting;videoCancelled=true;
  if(videoPending){if(videoProgress)videoProgress->setLabelText(u("等待当前显示帧结束后取消"));return;}videoEnd();
 }
void videoEnd(QString error={}){
  if(!error.isEmpty()&&videoError.isEmpty())videoError=error;if(videoIntegrityPreparing){videoCancelled=true;return;}if(videoEnding)return;videoEnding=true;
  if(videoProgress){videoProgress->setRange(0,0);videoProgress->setCancelButton(nullptr);videoProgress->setLabelText(u("正在完成文件并恢复导航"));}
  if(videoEncoder)videoEncoder->finish();else videoEncoderDone=true;
  plScope->stop([this]{videoDrained=true;videoComplete();});videoComplete();
 }
void videoComplete(){
  if(!videoEnding||!videoDrained||!videoEncoderDone||videoIntegrityPreparing||videoIntegrityFinalizing)return;
  if(!videoIntegrityChecked){videoFinishIntegrity();return;}
  videoWatchdog.stop();bool ok=videoError.isEmpty()&&!videoCancelled&&videoIndex==videoPlan->total();
  QJsonObject report{{"schema","kv260.navigation_media.v1"},{"status",ok?"completed":videoCancelled?"cancelled":"failed"},{"error",videoError},
   {"scene",scenePath},{"source_result",source},{"input_sha256",scene["input_sha256"]},{"source_sha256",videoSources},
   {"fps",videoFPS},{"speed_mm_per_s",videoSpeed},{"route_length_mm",videoPlan->length},{"expected_route_frames",videoPlan->moving},
   {"expected_hold_frames",videoPlan->hold},{"expected_total_frames",videoPlan->total()},{"encoded_frames",videoIndex},{"completed_PL_frames",videoRendered},
   {"output_size",QJsonArray{videoSize.width(),videoSize.height()}},{"native_PL_size",QJsonArray{640,360}},{"frame_trace",videoTrace},
   {"attribute_sampling",videoAttributeSampling},{"active_scene_binding",videoActiveBinding},{"linked_overview_enabled",videoLinked},{"pane_output_size",QJsonArray{videoPaneSize.width(),videoPaneSize.height()}},{"overview_native_size",videoLinked?QJsonArray{640,360}:QJsonArray{}},
   {"capture_fit_policy",videoActiveBinding.isEmpty()?(videoLinked?"native_C6_and_linked_overview_FBOs_aspect_preserved":"native_C6_color_FBO_aspect_preserved"):(videoLinked?"native_C9_and_linked_overview_FBOs_aspect_preserved":"native_C9_color_FBO_aspect_preserved")},{"wall_seconds",videoClock.elapsed()/1000.},{"Qt_peak_RSS_MiB",peakRSS()},
   {"native_GUI_button",true},{"integrity_validation",videoIntegrityMetrics},{"all_required_runtime_source_checks_retained",true},{"sealed_historical_provenance_preserved",true},{"integrity_validation_on_worker_thread",true},{"UI_ticks_during_export",ticks-videoStartTick},{"codec", "libx264"},{"encoder_threads",2},{"one_PL_frame_in_flight",true},{"maximum_encoder_owned_images",1},{"real_time_frame_dropping",false},
   {"PL_cooperative_stop",true},{"additional_PL_resources",0},{"new_bitstream",false},{"saved_view_state",videoSavedCamera},
   {"cancel_requested_while_awaiting_PL",videoCancelledAtPL},{"file_writes_on_encoder_thread",true},
   {"PS",QJsonArray{"timeline","camera","GPU shading/HUD","linked overview/frustum/color capture","bounded pipe","H264 encoding"}},
   {"PL",videoActiveBinding.isEmpty()?QJsonArray{"C6 wall intersection","target visibility","outline","depth-aware normals"}:QJsonArray{"C9 scalar wall intersection","current target visibility","outline","scalar-gradient normals"}}};
  try{
   if(!videoMovieSHA.isEmpty())report["movie_sha256"]=videoMovieSHA;
   writeJson(videoDirectory+"/report.json",report);
   if(ok){QDir parent=QFileInfo(videoDirectory).dir();if(!parent.rename(QFileInfo(videoDirectory).fileName(),QFileInfo(videoFinalDirectory).fileName()))throw std::runtime_error("Cannot commit video directory");}
  }catch(const std::exception&e){ok=false;videoError=QString::fromUtf8(e.what());report["status"]="failed";report["error"]=videoError;try{writeJson(videoDirectory+"/report.json",report);}catch(...){}}
  videoEncoder.reset();videoPending=videoRunning=videoAwaiting=videoEncoding=false;videoEnding=false;
  if(videoProgress){videoProgress->hide();videoProgress->deleteLater();videoProgress=nullptr;}
  miniOverview->setUpdatesEnabled(true);bool overviewRestored=miniOverview->restoreOverviewCamera(videoSavedOverviewCamera);
  bool restored=scope->restoreScopeViewState(videoSavedCamera);scope->setEnabled(true);scopeQuality->setCurrentIndex(videoSavedQuality);dualCheck->setChecked(videoSavedDual);tabs->setCurrentIndex(videoSavedTab);
  {QSignalBlocker block(cameraSlider);cameraSlider->setValue(scope->cameraForDistance(scope->distance()));}
  busy(false);configureScope();if(videoSavedPlaying&&videoSavedTab==2)navigationToggle();
  message(ok?u("导航视频已保存：")+videoFinalDirectory:videoCancelled?u("已取消导出，导航视角已恢复"):u("视频导出失败：")+videoError);
  videoLastReceipt=QJsonObject{{"status",report["status"]},{"directory",ok?videoFinalDirectory:videoDirectory},{"error",videoError},
    {"scope_restored",restored},{"linked_camera_restored",overviewRestored},{"attribute_sampling",videoAttributeSampling},
    {"completed_PL_frames",videoRendered},{"cancelled_while_awaiting_PL",videoCancelledAtPL}};++videoReceiptSerial;
   
 }
void applyOverviewOpacity(){overview->setLungOpacity(opacity->value()/100.f);}
QDoubleSpinBox *navigationSpeed=nullptr,*navigationStep=nullptr;
QPushButton *navBackward=nullptr,*navForward=nullptr,*navStart=nullptr,*navEnd=nullptr;
QLabel *navigationPosition=nullptr;
QCheckBox *navigationAlign=nullptr;
double  navigationSpeedCurrent=2.;
void syncNavigationControlsFromCamera(){
  if(!scope||!cameraSlider||!navigationPosition)return;
  {QSignalBlocker blocked(cameraSlider);cameraSlider->setValue(scope->cameraForDistance(scope->distance()));}
  navigationPosition->setText(QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,'f',1).arg(scope->totalDistance(),0,'f',1));
  if(navigationAlign){QSignalBlocker blocked(navigationAlign);navigationAlign->setChecked(scope->scopeViewState()["auto_align"].toBool());}gamepadLabel();
  shellNavChanged();
 }
bool keyboardNavigationAllowed()const{
  auto*f=QApplication::focusWidget();
  return tabs->currentIndex()==2&&!processing()&&scope->cameraCount()>0&&
   !qobject_cast<QLineEdit*>(f)&&!qobject_cast<QAbstractSpinBox*>(f)&&!qobject_cast<QComboBox*>(f);
 }
void navigationPause(){
  if(playing)navigationTick();
  play.stop();playing=false;scope->setPlayback(false);playButton->setText(u("沿路径播放"));
 }
void navigationAt(double at){
  scope->setDistance(float(medical_motion::step(at,0,scope->totalDistance())));
  syncNavigationControlsFromCamera();
 }
void navigationMove(double delta){
  if(processing()||scope->cameraCount()==0)return;
  navigationPause();navigationAt(medical_motion::step(scope->distance(),delta,scope->totalDistance()));
 }
void navigationBoundary(bool end){
  if(processing()||scope->cameraCount()==0)return;
  navigationPause();if(!end)scope->resetView();navigationAt(end?scope->totalDistance():0);
 }
void navigationToggle(){
  if(processing()||scope->cameraCount()==0)return;
  if(playing){navigationPause();return;}
  playbackStart=scope->distance();navigationSpeedCurrent=navigationSpeed->value();
  playbackClock.restart();playing=true;scope->setPlayback(true);
  playButton->setText(u("暂停"));play.start(40);
 }
void navigationTick(){
  double at=medical_motion::position(playbackStart,playbackClock.elapsed(),
   navigationSpeedCurrent,scope->totalDistance());navigationAt(at);
  if(at>=scope->totalDistance()){
   play.stop();playing=false;scope->setPlayback(false);playButton->setText(u("沿路径播放"));
  }
  if(navigationTesting&&navigationBenchmarking){auto sample=scope->cameraRequest();
   sample["elapsed_ms"]=double(playbackClock.elapsed());playbackTestTrace.append(sample);}
 }
void navigationControls(QVBoxLayout*layout){
  auto*row=new QHBoxLayout;
  row->addWidget(new QLabel(u("速度")));navigationSpeed=new QDoubleSpinBox;
  navigationSpeed->setRange(.25,20);navigationSpeed->setDecimals(2);navigationSpeed->setValue(2);
  navigationSpeed->setSuffix(" mm/s");navigationSpeed->setMaximumWidth(110);row->addWidget(navigationSpeed);
  row->addWidget(new QLabel(u("步长")));navigationStep=new QDoubleSpinBox;
  navigationStep->setRange(.25,10);navigationStep->setDecimals(2);navigationStep->setValue(2);
  navigationStep->setSuffix(" mm");navigationStep->setMaximumWidth(100);row->addWidget(navigationStep);
  navBackward=new QPushButton(u("后退"));navForward=new QPushButton(u("前进"));
  navStart=new QPushButton(u("起点"));navEnd=new QPushButton(u("终点"));
  for(auto*b:{navBackward,navForward,navStart,navEnd})row->addWidget(b);
  layout->addLayout(row);navigationPosition=new QLabel(u("位置 0 mm · W/D/→ 前进，S/A/← 后退；1/2 调步长；Home/End"));
  layout->addWidget(navigationPosition);
  connect(navBackward,&QPushButton::clicked,this,[this]{navigationMove(-navigationStep->value());});
  connect(navForward,&QPushButton::clicked,this,[this]{navigationMove(navigationStep->value());});
  connect(navStart,&QPushButton::clicked,this,[this]{navigationBoundary(false);});
  connect(navEnd,&QPushButton::clicked,this,[this]{navigationBoundary(true);});
  connect(navigationSpeed,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this](double v){
   if(playing){navigationTick();playbackStart=scope->distance();playbackClock.restart();}
   navigationSpeedCurrent=v;
  });
  auto shortcut=[this](int key,std::function<void()> action){
   auto*s=new QShortcut(QKeySequence(key),scope);s->setContext(Qt::WidgetWithChildrenShortcut);
   connect(s,&QShortcut::activated,this,[this,action]{if(keyboardNavigationAllowed())action();});
  };
  for(int key:{Qt::Key_W,Qt::Key_D,Qt::Key_Right,Qt::Key_Up})
   shortcut(key,[this]{navigationMove(navigationStep->value());});
  for(int key:{Qt::Key_S,Qt::Key_A,Qt::Key_Left,Qt::Key_Down})
   shortcut(key,[this]{navigationMove(-navigationStep->value());});
  shortcut(Qt::Key_1,[this]{navigationStep->setValue(qMax(.25,navigationStep->value()/2));});
  shortcut(Qt::Key_2,[this]{navigationStep->setValue(qMin(10.,navigationStep->value()*2));});
  for(int key:{Qt::Key_R,Qt::Key_Home})shortcut(key,[this]{navigationBoundary(false);});
  for(int key:{Qt::Key_E,Qt::Key_End})shortcut(key,[this]{navigationBoundary(true);});
  shortcut(Qt::Key_Space,[this]{navigationToggle();});
  scope->setFocusPolicy(Qt::StrongFocus);scope->installEventFilter(this);
 }
bool eventFilter(QObject*object,QEvent*event)override{
  if(object==scope&&tabs->currentIndex()==2&&event->type()==QEvent::Wheel){
   auto*wheel=static_cast<QWheelEvent*>(event);
   if(wheel->angleDelta().y()!=0){navigationMove(navigationStep->value()*wheel->angleDelta().y()/120.);
    wheel->accept();return true;}
  }
  shellEventFilter(object,event);
  return QWidget::eventFilter(object,event);
 }
QLabel *scopeUnavailable=nullptr;
double peakRSS(){struct rusage usage{};getrusage(RUSAGE_SELF,&usage);return usage.ru_maxrss/1024.;}
bool  compositeTesting=qEnvironmentVariableIntValue("KV260_COMPOSITE_UI_TEST")==1;
int  compositeStage=-1,compositeBase=0;
QJsonObject  compositeExpected;
QTimer  compositeCheck;
QElapsedTimer  compositeDeadline;
PlComposite *plComposite=nullptr;
QLabel *compositePerf=nullptr;
QTimer  compositeQuiet;
int  previewQuietRequests=0,previewStaleFrames=0;
QCheckBox *preciseBlend=nullptr;
QCheckBox *meshLayers[3]={};
int  compositeFrames=0;
QJsonArray  compositeTrace;
QCheckBox *routeCheck=nullptr;
QPushButton *structureButtons[3]={};
int  structureMode=2;
bool  settingStructure=false;
bool  combinedLayers[3]={false,true,true},combinedRoute=true;
QJsonObject  structureCameras[3];
PlScope * plScope=nullptr;
bool  graphicsTransition=false,finishingTest=false,closing=false;
int  plFrames=0,scopeWait=0,returnFrameBase=-1;
bool  verifiedScopeReturn=false;
QJsonObject  plLastFrame;
QLabel *scopePerf=nullptr;
QJsonArray  navigationTrace;
std::shared_ptr<Volume>  volume;
QProcess  prepareProcess,jobProcess,utilityProcess;
QByteArray  utilityBytes;
QString  utilityAction,utilityError;
QByteArray  prepPending,jobPending;
QString  errors;
QTabWidget *tabs;
QComboBox *results,*windowPreset,*scopeQuality;
QLabel *caseLabel,*info,*task,*coordinate,*routeInfo,*clock,*gpuLabel,*elapsed;
QProgressBar *progress;
QPushButton *openButton,*refreshButton,*runButton,*rebuildButton,*navButton,*stopButton,*playButton;
QSpinBox *lesion;
QDoubleSpinBox *minimumCandidateVolume=nullptr;
QDoubleSpinBox *diameter,*margin;
QComboBox *lesionList,*colorMode,*clipAxis;
QLabel *candidateInfo,*legend;
QPushButton *focusButton,*compareButton,*comparisonResults,*exportButton,*dicomButton;
QCheckBox *clipCheck,*dualCheck;
QSlider *clipOffset,*opacity;
MeshView *miniOverview;
QSlider *cameraSlider,*axialSlider;
QPlainTextEdit *log;
SliceView *slices[3];
MeshView *overview,*scope;
QTimer  heartbeat,play,navigationMotion;
QElapsedTimer  beatClock,taskClock,playbackClock,navigationMotionClock;
float  playbackStart=0;
QJsonArray  playbackTestTrace;
QVector<double>  gaps,jobGaps,swapIntervals,lungIntervals;
bool  lungBenchmark=false;
QTimer  rotation;
QElapsedTimer  swapClock;
bool  benchmarking=false;
int  ticks=0;
bool  playing=false,failed=false;
QString  evidence;
bool  featureTesting=false;
bool  smoke=false,acceptance=false,smokeStarted=false,navigationTesting=false,navigationBenchmarking=false,navigationBenchStarted=false;
int  navigationBase=0;
QVector<double>  navigationPresented;
QJsonObject  navigationTestReport;
int  smokeStep=0;
QJsonArray  actions;
QPushButton*button(QString text,QBoxLayout*layout){auto*b=new QPushButton(text);b->setMinimumHeight(30);layout->addWidget(b);return b;}
void record(QString action){actions.append(QJsonObject{{"action",action},{"elapsed_ms",double(beatClock.elapsed())}});}
void showStructure(int mode){
  if(mode<0||mode>2||scenePath.isEmpty())return;
  structureCameras[structureMode]=overview->overviewCamera();
  if(structureMode==2){for(int i=0;i<3;++i)combinedLayers[i]=meshLayers[i]->isChecked();combinedRoute=routeCheck->isChecked();}
  settingStructure=true;structureMode=mode;
  for(int i=0;i<3;++i)meshLayers[i]->setChecked(mode==2?combinedLayers[i]:i==mode);
  routeCheck->setChecked(mode==2&&combinedRoute);settingStructure=false;
  if(!overview->restoreOverviewCamera(structureCameras[mode]))overview->resetView();
  record(QString("structure_preset_%1").arg(mode));
 }
void syncLinkedOverview(){if(dualCheck->isChecked()){if(!miniOverview->setReferenceCamera(scope->presentedScopeFrame())){qWarning()<<"Invalid completed PL camera for linked overview";if(smoke)failed=true;}}}
void message(QString text){log->appendPlainText(text);text=friendlyMessage(text);task->setText(text.left(180));task->setToolTip(text);if(logToggle&&(text.contains(u("失败"))||text.contains(u("错误"))))logToggle->setChecked(true);}
bool hasStructure(QString name)const{return scene["available_structures"].toArray().contains(name);}
bool canNavigate()const{return hasStructure("airway")&&hasStructure("nodule")&&lesionList&&lesionList->count()>0&&scene["structure_foreground_voxels"].toObject()["airway"].toDouble()>0;}
void busy(bool value){if(value)gamepadSuspend();syncExposure();value=value||videoPending||videoRunning;if(videoButton)videoButton->setEnabled(!value&&!replanUnavailable&&scope->cameraCount()>1&&!source.isEmpty());if(snapshotButton)snapshotButton->setEnabled(!value&&!capturePending&&!captureRunning&&!input.isEmpty());for(auto*b:{dicomButton,exportButton,compareButton,focusButton})if(b)b->setEnabled(!value&&!(replanUnavailable&&b==exportButton)&&(!source.isEmpty()||b==dicomButton));if(lesionList)lesionList->setEnabled(!value&&lesionList->count()>0);if(minimumCandidateVolume)minimumCandidateVolume->setEnabled(!value);if(focusButton)focusButton->setEnabled(!value&&!source.isEmpty()&&lesionList->count()>0);if(comparisonResults)comparisonResults->setEnabled(!value&&!scene["navigation"].toObject().isEmpty());if(importButton)importButton->setEnabled(!value&&!input.isEmpty());openButton->setEnabled(!value);refreshButton->setEnabled(!value);results->setEnabled(!value);runButton->setEnabled(!value&&!input.isEmpty());rebuildButton->setEnabled(!value&&!source.isEmpty()&&!scene["available_structures"].toArray().isEmpty());navButton->setEnabled(!value&&!source.isEmpty()&&canNavigate());if(compareButton)compareButton->setEnabled(!value&&!source.isEmpty()&&canNavigate());stopButton->setEnabled(jobProcess.state()!=QProcess::NotRunning);}
bool processing(bool includeCapture=true)const{return sceneLoading||videoPending||videoRunning||(includeCapture&&capturePending)||captureRunning||utilityProcess.state()!=QProcess::NotRunning||graphicsTransition||prepareProcess.state()!=QProcess::NotRunning||jobProcess.state()!=QProcess::NotRunning;}
void releaseGraphics(std::function<void()> done){
  graphicsTransition=true;busy(true);
  auto finish=[this,done]{graphicsTransition=false;scope->clearPlFrame();miniOverview->setReferenceCamera({});overview->setCompositeStatus(u("上一张完成画面"));busy(false);if(done)done();};
  auto composite=[this,finish]{if(plComposite&&plComposite->active())plComposite->stop(finish);else finish();};
  if(plScope&&plScope->active())plScope->stop(composite);else composite();
 }
void configureScope(){
  if(layoutReviewMode||!plScope||!plComposite||processing(false)||finishingTest||closing||source.isEmpty())return;
  int page=tabs->currentIndex();bool needsBlend=page==1&&overview->compositeMode()&&!scene["meshes"].toObject().isEmpty();bool needsScope=page==2&&!replanUnavailable&&scope->cameraCount()>0&&QFileInfo::exists(source+"/navigation/route.json");
  if((!needsScope&&plScope->active())||(!needsBlend&&plComposite->active())){releaseGraphics([this]{configureScope();});return;}
  if(needsScope){auto complete=scene["complete_surface"].toObject();
   if(!complete.isEmpty())plScope->startScene(complete["bundle"].toString(),complete["revision"].toString(),scope->cameraRequest());
   else plScope->start(source,scope->cameraRequest());
  }else if(page==2)scopePerf->setText(u("尚无导航路径，请先重新规划导航。"));
  if(needsBlend)plComposite->start(compositeSourceScene.isEmpty()?scenePath:compositeSourceScene,overview->overviewRequest());else if(page==1)compositePerf->setText(u("快速总览 · 拖动旋转 / 滚轮缩放"));
 }
void firstBranchPose(){auto events=scene["navigation"].toObject()["report"].toObject()["branch_guidance"].toObject()["events"].toArray();auto arcs=scene["navigation"].toObject()["arc"].toArray();int index=qMin(180,cameraSlider->maximum());if(!events.isEmpty()){auto e=events.first().toObject();double at=(e["show_from_mm"].toDouble()+e["hide_after_mm"].toDouble())*.5;for(int i=0;i<arcs.size();++i)if(arcs[i].toDouble()>=at){index=i;break;}}cameraSlider->setValue(index);}
void processLines(QByteArray&pending,QByteArray bytes){
  pending+=bytes;while(pending.contains('\n')){int end=pending.indexOf('\n');auto line=pending.left(end);pending.remove(0,end+1);auto d=QJsonDocument::fromJson(line);if(!d.isObject()){if(!line.trimmed().isEmpty())log->appendPlainText(QString::fromUtf8(line));continue;}auto o=d.object();QString event=o["event"].toString();pipelineEvent(o);
   if(event=="progress")message(o["text"].toString());
   if(event=="stage"){runningStage=o["stage"].toString();if(runningStage=="airway-cleanup")segmentationInfo->setText(u("气道清理（PS 四核）：连通域 / 闭运算 / 填洞"));}
   if(event=="stage_done"&&o["stage"].toString()==runningStage)runningStage.clear();
   if(event=="navigation_unavailable"){if(activeSurfaceAction!="replan"||o["parent_scene"].toString()!=scenePath){failed=true;message(u("导航结果与当前病例不符"));}else replanBlockedEvent=o;}
   if(event=="prepared")pendingResult=o["scene"].toString();
   if(event=="started"){runOutput=o["output"].toString();message(u("DFX 任务已启动"));}
   if(event=="stage"){QString stage=o["stage"].toString();QString name=stage=="airway-cleanup"?u("气道清理（PS）"):stage=="segmentation"?u("CT 分割"):stage=="reconstruction"?u("重建与平滑"):stage=="airway-detail"?u("细支气管候选审核"):u("路径导航");progress->setRange(0,0);message(u("正在执行：")+name+u("，界面可继续操作"));record("stage_"+stage);}
   if(event=="stage_done")message(o["stage"].toString()+QString(" · %1 s").arg(o["seconds"].toDouble(),0,'f',2));
   if(event=="completed"){progress->setRange(0,100);progress->setValue(o["status"]=="passed"?100:0);message(o["status"]=="passed"?u("任务已完成，正在更新视图"):u("已停止后续步骤，当前阶段正常结束"));if(o["status"]!="passed")runOutput.clear();}
   if(event=="error"){failed=true;message(o["text"].toString());}
  }
 }
void prepare(QString selected=QString()){
  if(processing())return;if((plScope&&plScope->active())||(plComposite&&plComposite->active())){releaseGraphics([this,selected]{prepare(selected);});return;}busy(true);pendingResult.clear();failed=false;prepPending.clear();errors.clear();progress->setRange(0,0);message(u("正在准备病例视图"));
  
  if(scene.isEmpty()&&selected.isEmpty()){selected=qEnvironmentVariable("KV260_INITIAL_RESULT");qunsetenv("KV260_INITIAL_RESULT");}
  QStringList args={root+"/modules/image_import/positive_labels_r1/backend.py","prepare","--input",input};if(!selected.isEmpty())args<<"--result"<<selected;
  QString complete=qEnvironmentVariable("KV260_COMPLETE_SCENE");
  if(scene.isEmpty()&&selected.isEmpty()&&!complete.isEmpty())args=QStringList{root+"/modules/navigation_replan/backend_r2265.py","prepare","--active-scene",complete,"--input",input};
  prepareProcess.start(root+"/.venv/bin/python",args);
 }
void loadScene(QString path){
  gamepadSuspend();
  bool previouslyUnavailable=replanUnavailable;replanUnavailable=false;cameraSlider->setEnabled(true);
  auto nextScene=readyVolume&&readyPath==path?readyMeta:readJson(path);auto next=readyVolume&&readyPath==path?readyVolume:std::make_shared<Volume>();if(next!=readyVolume)next->load(path,nextScene);readyVolume.reset();readyMeta={};readyPath.clear();volume=next;scene=nextScene;scenePath=path;source=scene["result"].toString();
  if(qEnvironmentVariableIntValue("KV260_FORCE_RAW_CT_TEST")==1&&!freshRawSeen){freshRawSeen=true;
   freshRawInitialVerified=source.isEmpty()&&scene["meshes"].toObject().isEmpty()&&scene["candidates"].toArray().isEmpty();
   if(!freshRawInitialVerified)failed=true;
  }
  for(auto*s:slices)s->setVolume(volume);axialSlider->setRange(0,volume->dims[2]-1);axialSlider->setValue(volume->dims[2]/2);
  for(auto*slice:slices)slice->setAirwayMask(2);
  overview->loadScene(path,scene);scope->loadScene(path,scene);if(dualCheck->isChecked())miniOverview->loadScene(path,scene);scope->setScope(true);bool ready=scope->cameraCount()>0&&QFileInfo::exists(source+"/navigation/route.json");scope->setVisible(ready);scopeUnavailable->setVisible(!ready);playButton->setEnabled(ready);bool haveMeshes=!scene["meshes"].toObject().isEmpty();preciseBlend->setEnabled(haveMeshes);if(!haveMeshes)preciseBlend->setChecked(false);cameraSlider->setRange(0,qMax(0,scope->cameraCount()-1));cameraSlider->setValue(0);navigationPosition->setText(QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,'f',1).arg(scope->totalDistance(),0,'f',1));
  structure_availability::apply(scene,meshLayers,structureButtons,structureAvailability);shellSceneLoaded();
  const auto lungState=structure_availability::describe(scene,"lung");
  opacity->setEnabled(lungState.ready);
  for(auto&camera:structureCameras)camera={};overview->setLungDetail(false);for(int i=0;i<3;++i)overview->setLayer(i,meshLayers[i]->isChecked());overview->resetView();
  results->blockSignals(true);results->clear();for(auto v:scene["results"].toArray()){auto o=v.toObject();results->addItem(o["name"].toString(),o["path"].toString());}int selected=results->findData(source);if(selected>=0)results->setCurrentIndex(selected);results->blockSignals(false);
  caseLabel->setText(QFileInfo(input).fileName());info->setText(QString("%1 × %2 × %3\n%4 × %5 × %6 mm\n%7").arg(volume->dims[0]).arg(volume->dims[1]).arg(volume->dims[2]).arg(volume->spacing[0],0,'f',3).arg(volume->spacing[1],0,'f',3).arg(volume->spacing[2],0,'f',3).arg(source.isEmpty()?u("尚无分割结果"):u("分割 / 模型结果已加载")));
  auto nr=scene["navigation"].toObject()["report"].toObject();QString routeStatus=nr["status"].toString();
  routeInfo->setText(routeDescription(nr));routeInfo->setToolTip(u("净空检查：估计管腔半径减去图像分辨率保守余量，须不小于器械半径加每侧余量。此检查基于分割模型，不包含真实器械的弯曲及接触模型。"));
  if(!nr.isEmpty()){lesion->setValue(nr["target"].toObject()["index"].toInt());diameter->setValue(nr["scope_diameter_mm"].toDouble(1.));margin->setValue(nr["safety_margin_mm"].toDouble(.2));}
  refreshCandidates();
  auto attributes=scene["meshes"].toObject()["airway"].toObject()["attributes"].toObject();auto*model=qobject_cast<QStandardItemModel*>(colorMode->model());if(model){model->item(1)->setEnabled(!attributes.isEmpty());model->item(2)->setEnabled(!attributes.isEmpty());}if(attributes.isEmpty())colorMode->setCurrentIndex(0);
  if(previouslyUnavailable)routeCheck->setChecked(replanRouteWasVisible);
  updateColorLegend();progress->setRange(0,100);progress->setValue(100);message(u("病例已就绪 · 鼠标滚轮切片，拖动模型旋转"));if(!source.isEmpty()&&scene["source"]=="external_partial"){QStringList names;for(auto n:scene["available_structures"].toArray())names<<structure_availability::name(n.toString());info->setText(info->text()+u("\n已提供：")+names.join(" / "));message(u("仅重建已提供的结构；导航需气道和病灶候选。"));}else if(!source.isEmpty()&&QFile::exists(source+"/external_import.json")){info->setText(info->text()+u("\n外部掩膜已校验 · 概率图已保留"));message(u("外部掩膜已加载；点击重新重建使用PL生成模型。概率图表面需另行选择。"));}if(!source.isEmpty()){QFile p(source+"/pipeline.json");if(p.open(QIODevice::ReadOnly)&&QJsonDocument::fromJson(p.readAll()).object()["mode"]=="airway-cleanup")message(u("PL气道清理已完成；请重新重建模型，再规划导航。"));}
  if(!source.isEmpty()&&QFileInfo::exists(source+"/segmentation/report.json")){auto policy=readJson(source+"/segmentation/report.json")["images"].toObject()["airway"].toObject()["postprocessing"].toObject();if(policy["policy"]=="probability_threshold_then_largest_26_connected_airway"){auto note=QString(u("概率图气道筛选：保留主气道 %1 体素，排除孤立区域 %2 体素；原始概率图已保留。" )).arg(policy["kept_voxels"].toInt()).arg(policy["removed_voxels"].toInt());info->setText(info->text()+"\n"+note);message(note);}}
  resetAttributeSampling();showSegmentationSummary();record("scene_loaded");
 }
int navigationTargetForJob(QString mode)const{return mode=="all"?0:lesion->value();}
void startJob(QString mode){
  
  if((!scene.value("complete_surface").toObject().isEmpty())&&mode=="reconstruction"){startSurfaceAction("quality");return;}
  if((!scene.value("complete_surface").toObject().isEmpty())&&mode=="comparison"){startSurfaceAction(mode);return;}
  if((!scene.value("complete_surface").toObject().isEmpty())&&mode=="navigation"){startSurfaceAction("replan");return;}
  if((!scene.value("complete_surface").toObject().isEmpty())&&mode!="all"){message(u("当前新表面场景的单项重规划尚未接入；请保留当前场景，或选择原结果。"));return;}
  if(segmentation_status::needsExistingTarget(mode)&&(!hasStructure("nodule")||lesionList->count()==0)){message(u("当前筛选没有目标候选，请降低最小候选体积后再处理。"));return;}
  if(processing())return;if((plScope&&plScope->active())||(plComposite&&plComposite->active())){message(u("等待显示帧结束，准备切换医疗模块"));releaseGraphics([this,mode]{startJob(mode);});return;}runOutput.clear();failed=false;errors.clear();jobPending.clear();runningMode=mode;runningStage.clear();runningRepeats=1;if(mode=="all"||mode=="segmentation")segmentationInfo->setText(u("正在读取 CT、执行 PL HU 预处理并预热模型"));
  stopFile=root+"/ui/cache/stop_"+QUuid::createUuid().toString(QUuid::Id128);QFile::remove(stopFile);taskClock.restart();
  QStringList args={root+"/modules/image_import/positive_labels_r1/backend.py","run","--input",input,"--mode",mode,"--lesion",QString::number(navigationTargetForJob(mode)),"--diameter",QString::number(diameter->value()),"--margin",QString::number(margin->value()),"--minimum-bend",QString::number(0.),"--stop-file",stopFile};if(mode!="all")args<<"--result"<<source;if(mode=="all"){args[0]=root+"/modules/segmentation/reader_burst/backend.py";if(qEnvironmentVariable("KV260_SPEEDUP")!="0"&&QFileInfo::exists(root+"/modules/segmentation/speedup_r1/backend.py"))args[0]=root+"/modules/segmentation/speedup_r1/backend.py";args<<"--admission"<<(root+"/modules/segmentation/reader_burst/candidate_ui_selection.json")<<"--admission-sha256"<<"76b614933504abb4ae946b978fc44ce15fa5dd44e727e99a5e5fc5bcd81a2a06";auto parent=qEnvironmentVariable("KV260_B7_RUN_PARENT");if(parent.isEmpty())parent=root+"/ui/runs";args<<"--run-parent"<<parent;}
  jobProcess.start(root+"/.venv/bin/python",args);busy(true);stopButton->setEnabled(true);progress->setRange(0,0);message(u("正在启动后台医疗计算"));record("job_"+mode);
 }
void stopAfterStage(){if(jobProcess.state()==QProcess::NotRunning)return;QFile f(stopFile);f.open(QIODevice::WriteOnly);f.write("stop after current stage\n");stopButton->setEnabled(false);message(u("将在当前阶段正常完成后停止，不中断 DMA"));}
void updateAnalysis(){if(replanUnavailable){routeInfo->setText(blockedNavigationNotice());return;}for(auto*v:{overview,miniOverview})v->setAnalysisParameters(diameter->value(),margin->value());auto r=scene["navigation"].toObject()["report"].toObject();if(r.isEmpty())return;bool changed=r["target"].toObject()["index"].toInt()!=lesion->value()||std::abs(r["scope_diameter_mm"].toDouble()-diameter->value())>.001||std::abs(r["safety_margin_mm"].toDouble()-margin->value())>.001||std::abs(r["minimum_bend_radius_mm"].toDouble()-0.)>.001;routeInfo->setText(routeDescription(r)+(changed?u("\n目标或器械参数已改变；当前路径尚未重算，请重新规划。"):QString()));}
void updateColorLegend(){
  int mode=colorMode->currentIndex();auto attributes=scene["meshes"].toObject()["airway"].toObject()["attributes"].toObject();
  auto anatomy=attributes["anatomical_generation"].toObject();bool anchored=attributes["generation_kind"]=="carina_anchored_heuristic_topology_not_confirmed_anatomical_names";
  legend->setText(mode==1?(anchored?u("隆突锚定 · 0—7+ 代 · 灰色=不连通"):u("气管=0 · 图分支深度 · 灰色=不连通")):mode==2?u("红=受限 · 黄=余量小 · 绿=满足几何约束"):mode==3?u("红<0.45 · 黄<0.70 · 青<0.90 · 蓝≥0.90"):u("右击候选标记可选中"));
  legend->setToolTip(anchored?u("按骨架和显著分岔估计代数；短毛刺仅在着色分析中排除。未确认肺叶名称，不修改导航图或掩膜。")+(anatomy["carina_selection"]=="earliest_junction_unqualified_fallback"?u("\n当前采用未满足主分支条件的回退隆突，请审核。"):QString()):u("按当前导航图的分支深度着色。"));
 }
void refreshCandidates(){
  applyVirtualCasePreset();
  int previous=lesion->value();lesionList->blockSignals(true);lesionList->clear();
  for(auto value:scene["candidates"].toArray()){auto c=value.toObject();
   if(c["volume_mm3"].toDouble()<minimumCandidateVolume->value())continue;
   int id=c["index"].toInt();lesionList->addItem(QString(u("候选 #%1 · %2 mm³")).arg(id).arg(c["volume_mm3"].toDouble(),0,'f',1),id);
  }
  int selected=lesionList->findData(previous);lesionList->setCurrentIndex(selected>=0?selected:0);
  lesionList->blockSignals(false);updateCandidate();
 }
void updateCandidate(){int index=lesionList->currentData().toInt();if(lesionList->count()==0){lesion->setValue(-1);for(auto*v:{overview,miniOverview})v->selectCandidate(-1);candidateInfo->setText(scene["candidates"].toArray().isEmpty()?u("当前结果没有病灶候选"):u("当前体积筛选无候选；降低阈值可恢复"));updateAnalysis();busy(processing());return;}lesion->setValue(index);for(auto*v:{overview,miniOverview})v->selectCandidate(index);for(auto value:scene["candidates"].toArray()){auto c=value.toObject();if(c["index"].toInt()==index){auto p=c["centroid_lps_mm"].toArray();candidateInfo->setText(QString(u("%1 mm³ · %2 体素\nLPS (%3, %4, %5) mm")).arg(c["volume_mm3"].toDouble(),0,'f',1).arg(c["voxel_count"].toInt()).arg(p[0].toDouble(),0,'f',1).arg(p[1].toDouble(),0,'f',1).arg(p[2].toDouble(),0,'f',1));break;}}updateAnalysis();busy(processing());}
bool  activeSurfaceJob=false;
QString  activeSurfaceAction;
bool  replanUnavailable=false,replanRouteWasVisible=false;
QJsonObject  replanBlockedEvent;
QString blockedNavigationNotice()const{return u("当前入口不满足通行约束，未生成任何导航路径。\n模型和上次成功结果已保留；检查器械参数及分割模型后，可重新规划。");}
QJsonObject  replanSavedOverview,replanSavedStructures[3];
void saveReplanOverview(){replanSavedOverview=overview->overviewCamera();for(int i=0;i<3;++i)replanSavedStructures[i]=structureCameras[i];}
void restoreReplanOverview(){if(!overview->restoreOverviewCamera(replanSavedOverview))throw std::runtime_error("Replanning could not restore overview camera");for(int i=0;i<3;++i)structureCameras[i]=replanSavedStructures[i];}
void startSurfaceAction(QString action,int group=-1,int candidate=-1){
  qInfo()<<"R14b start surface action"<<action<<"processing"<<processing()<<"graphics"<<graphicsTransition;
  if(processing()||(action!="quality"&&!(!scene.value("complete_surface").toObject().isEmpty())))return;
  if((plScope&&plScope->active())||(plComposite&&plComposite->active())){
   releaseGraphics([this,action,group,candidate]{startSurfaceAction(action,group,candidate);});return;
  }
  
  if(action=="replan")saveReplanOverview();
  play.stop();playing=false;playButton->setText(u("沿路径播放"));scope->setPlayback(false);
  
  activeSurfaceJob=true;activeSurfaceAction=action;replanBlockedEvent={};runOutput.clear();pendingResult.clear();failed=false;
  errors.clear();jobPending.clear();stopFile.clear();taskClock.restart();
  QStringList args={root+"/modules/surface_route/pl_default_r1/backend.py",action,"--active-scene",scenePath,
   "--input",input,"--result",source,"--lesion",QString::number(lesion->value()),"--diameter",QString::number(diameter->value()),
   "--margin",QString::number(margin->value()),"--minimum-bend",QString::number(0.)};
  if(action=="quality")args<<"--source"<<(0<2?"accepted_binary":"network_probability")<<"--quality"<<(0%2?"ultra":"high");
  
  jobProcess.start(root+"/.venv/bin/python",args);busy(true);stopButton->setEnabled(false);progress->setRange(0,0);
  message(action=="replan"?u("正在按当前管壁和器械约束重新规划导航"):action=="airway-detail"?u("正在审核当前目标的细支气管；模型和导航保持原样"):action=="quality"?u("正在重新生成 PL 气道表面并同步导航"):action=="comparison"?u("正在比较当前表面的器械与接近路径"):u("正在审核所选曲线并同步相机和分岔标记"));
  record("active_surface_"+action+"_started");
 }
void surfaceJobFinished(int rc){
  activeSurfaceJob=false;stopButton->setEnabled(false);
  if(!rc&&!failed&&activeSurfaceAction=="replan"&&!replanBlockedEvent.isEmpty()){
   if(!replanUnavailable)replanRouteWasVisible=routeCheck->isChecked();replanUnavailable=true;
   play.stop();playing=false;scope->setPlayback(false);scope->clearPlFrame();miniOverview->setReferenceCamera({});
   routeCheck->setChecked(false);scope->hide();scopeUnavailable->setText(blockedNavigationNotice());scopeUnavailable->show();
   playButton->setEnabled(false);cameraSlider->setEnabled(false);progress->setRange(0,100);progress->setValue(100);
   routeInfo->setText(blockedNavigationNotice());message(blockedNavigationNotice());record("active_surface_replan_unreachable");busy(false);
   return;
  }
  try{
   if(rc||failed||pendingResult.isEmpty())throw std::runtime_error((errors.isEmpty()?u("当前表面任务未完成"):errors).toStdString());
   loadScene(pendingResult);if(activeSurfaceAction=="replan")restoreReplanOverview();record("active_surface_"+activeSurfaceAction+"_loaded");
  }catch(const std::exception&e){failed=true;message(QString::fromUtf8(e.what()));progress->setRange(0,100);progress->setValue(0);}
  busy(false);if(!failed)configureScope();
  
 }
void showComparisons(){showPlanningSummary();}
void focusCandidate(){if(lesionList->count()==0)return;int index=lesion->value();tabs->setCurrentIndex(1);structureCameras[structureMode]=overview->overviewCamera();settingStructure=true;meshLayers[2]->setChecked(true);overview->focusCandidate(index);settingStructure=false;structureMode=2;if(overview->onOverviewChanged)overview->onOverviewChanged();for(auto v:scene["candidates"].toArray()){auto c=v.toObject();if(c["index"].toInt()!=index)continue;auto a=c["centroid_lps_mm"].toArray();QVector3D point(float(a[0].toDouble()),float(a[1].toDouble()),float(a[2].toDouble()));QMatrix4x4 matrix;for(int r=0;r<3;++r)for(int col=0;col<3;++col)matrix(r,col)=volume->direction(r,col);auto xyz=matrix.inverted().mapVector(point-volume->origin);for(int k=0;k<3;++k)xyz[k]/=volume->spacing[k];axialSlider->setValue(qRound(xyz.z()));slices[1]->setSlice(qRound(xyz.y()));slices[2]->setSlice(qRound(xyz.x()));}message(u("已聚焦选中候选；更换目标后需点击重新规划导航"));}
void startUtility(QString action,QStringList args){
  bool activeExport=action=="export"&&(!scene.value("complete_surface").toObject().isEmpty());if(processing())return;if((plScope&&plScope->active())||(plComposite&&plComposite->active())){releaseGraphics([this,action,args]{startUtility(action,args);});return;}utilityBytes.clear();utilityError.clear();utilityAction=action;busy(true);QString adapter=action=="import-external"?root+"/modules/image_import/positive_labels_r1/entry.py":activeExport?root+"/modules/surface_route/export_backend_r21.py":root+"/modules/report_export/backend.py";if(activeExport&&!(false))args<<"--active-scene"<<scenePath;utilityProcess.start(root+"/.venv/bin/python",QStringList{root+"/modules/image_import/positive_labels_r1/utility.py","--adapter",adapter,action}+args);message(action=="import-external"?u("正在校验外部掩膜与概率图"):action=="export"?u("正在导出模型与报告"):u("正在读取 DICOM 序列"));}
void chooseDicomSeries(const QJsonObject&result){
  auto series=result["series"].toArray();
  if(series.isEmpty()){
   message(u("所选目录及子目录内没有可读取的 DICOM 序列"));configureScope();
   return;
  }
  int index=0;
  if(series.size()>1){
   QDialog dialog(this);dialog.setWindowTitle(u("选择 DICOM 序列（包含子目录）"));dialog.resize(860,430);
   auto*layout=new QVBoxLayout(&dialog);auto*hint=new QLabel(QString(u("共 %1 个序列。重复 UID 按所在目录分别列出，请选择要导入的一行。\n%2")).arg(series.size()).arg(result["directory"].toString()));hint->setWordWrap(true);layout->addWidget(hint);
   auto*table=new QTableWidget(series.size(),3);table->setHorizontalHeaderLabels({u("所在子目录"),u("切片数量"),u("序列 UID")});
   for(int i=0;i<series.size();++i){auto r=series[i].toObject();QStringList text={r["relative_directory"].toString(),QString::number(r["file_count"].toInt()),r["series_uid"].toString()};for(int k=0;k<3;++k){auto*item=new QTableWidgetItem(text[k]);item->setToolTip(text[k]);table->setItem(i,k,item);}}
   table->setSelectionBehavior(QAbstractItemView::SelectRows);table->setSelectionMode(QAbstractItemView::SingleSelection);table->setEditTriggers(QAbstractItemView::NoEditTriggers);table->horizontalHeader()->setSectionResizeMode(0,QHeaderView::Stretch);table->horizontalHeader()->setSectionResizeMode(1,QHeaderView::ResizeToContents);table->horizontalHeader()->setSectionResizeMode(2,QHeaderView::Stretch);table->selectRow(0);layout->addWidget(table);
   auto*row=new QHBoxLayout;auto*cancel=new QPushButton(u("取消"));auto*load=new QPushButton(u("导入所选序列"));row->addStretch();row->addWidget(cancel);row->addWidget(load);layout->addLayout(row);
   connect(cancel,&QPushButton::clicked,&dialog,&QDialog::reject);connect(load,&QPushButton::clicked,&dialog,&QDialog::accept);connect(table,&QTableWidget::cellDoubleClicked,&dialog,[&dialog](int,int){dialog.accept();});
   
   if(dialog.exec()!=QDialog::Accepted){configureScope();return;}index=table->currentRow();
  }
  if(index<0||index>=series.size()){message(u("请先选择一个序列"));configureScope();return;}
  auto selected=series[index].toObject();QString token=selected["selection_id"].toString();
  if(token.isEmpty()){message(u("序列选择标识无效，请重新扫描目录"));configureScope();return;}
  QStringList args={"--input",result["directory"].toString(),"--series-uid",token};
  
  startUtility("import-dicom",args);
 }
void finishUtility(int code,QProcess::ExitStatus status){utilityBytes+=utilityProcess.readAllStandardOutput();utilityError+=QString::fromUtf8(utilityProcess.readAllStandardError());QJsonObject result;for(auto line:utilityBytes.split('\n')){auto doc=QJsonDocument::fromJson(line);if(doc.isObject())result=doc.object();}busy(false);if(code||status!=QProcess::NormalExit||result["event"]=="error"){QString why=result["text"].toString(utilityError);message(why);configureScope();return;}if(result["event"]=="external_imported"){prepare(result["result"].toString());}else if(result["event"]=="dicom_series"){chooseDicomSeries(result);}else if(result["event"]=="imported"){input=result["input"].toString();source.clear();prepare();}else if(result["event"]=="exported"){message(u("已导出至 ")+result["path"].toString());
configureScope();}}
void capture(QString name){QDir().mkpath(evidence);grab().save(evidence+"/"+name+".png");if(overview->isVisible())overview->grabFramebuffer().save(evidence+"/"+name+"_viewport.png");if(scope->isVisible())scope->grabFramebuffer().save(evidence+"/"+name+"_viewport.png");}
bool compositeControlsMatch()const{
 auto meta=overview->completedComposite(),c=meta["report"].toObject()["controls"].toObject();
 if(compositeFrames<=compositeBase||meta["width"]!=compositeExpected["width"]||meta["height"]!=compositeExpected["height"])return false;
 for(const char*k:{"full_lung","layers","clipping"})if(c[k]!=compositeExpected[k])return false;
 for(const char*k:{"yaw_degrees","pitch_degrees","zoom","radius_mm","color_mode","required_radius_mm","resolution_margin_mm"})if(std::abs(c[k].toDouble()-compositeExpected[k].toDouble())>1e-4)return false;
 if(c["center_lps_mm"]!=compositeExpected["center_lps_mm"])return false;
 return c["lung_opacity_byte"].toInt()==int(std::floor(compositeExpected["lung_opacity"].toDouble()*255+.5));
}
void compositeAdvance(){
 if(compositeStage>=0){
  bool ready=compositeStage==5?plFrames>compositeBase&&!graphicsTransition&&!plComposite->active():
   compositeStage>=7?!processing()&&!plScope->active()&&!plComposite->active():compositeControlsMatch();
  if(!ready){if(compositeDeadline.elapsed()>60000){compositeCheck.stop();failed=true;record("composite_UI_timeout_stage_"+QString::number(compositeStage));finishTest();}return;}
  if(compositeStage==3){auto p=overview->candidateScreenPoint(lesion->value());
   qInfo()<<"C7 focus projection"<<p<<"widget center"<<overview->rect().center()<<"candidate"<<lesion->value();
   if(p.x()<0||QLineF(p,overview->rect().center()).length()>3){failed=true;record("C7_focus_projection_failed");}
   int before=lesion->value();QMouseEvent click(QEvent::MouseButtonPress,p,Qt::RightButton,Qt::RightButton,Qt::NoModifier);QApplication::sendEvent(overview,&click);
   if(lesion->value()!=before){failed=true;record("C7_candidate_pick_failed");}record("completed_frame_candidate_pick");
  }
  capture("composite_"+QString::number(compositeStage));record("composite_UI_stage_"+QString::number(compositeStage)+"_completed");
  if(compositeStage==8){if(overview->compositeMode()||!overview->metrics()["error"].toString().isEmpty())failed=true;record("fast_GPU_overview_restored_after_C7_stop");compositeCheck.stop();finishTest();return;}
 }
 ++compositeStage;compositeBase=compositeStage==5?plFrames:compositeFrames;compositeDeadline.restart();
 switch(compositeStage){
  case 0:preciseBlend->setChecked(true);tabs->setCurrentIndex(1);overview->resetView();break;
  case 1:structureButtons[0]->click();overview->setLungDetail(false);opacity->setValue(40);colorMode->setCurrentIndex(1);break;
  case 2:structureButtons[2]->click();meshLayers[0]->setChecked(true);overview->setLungDetail(true);colorMode->setCurrentIndex(0);break;
  case 3:QTest::mouseClick(meshLayers[0],Qt::LeftButton);focusButton->click();colorMode->setCurrentIndex(2);break;
  case 4:{overview->resetView();for(int i=0;i<64;++i)overview->turn(1.2f);
   if(!overview->compositePreviewMode()||std::abs(overview->overviewRequest()["yaw_degrees"].toDouble()-76.8)>0.01){failed=true;record("C7_immediate_preview_failed");}
   record("immediate_preview_during_64_pose_burst");resize(940,720);break;}
  case 5:tabs->setCurrentIndex(2);firstBranchPose();break;
  case 6:tabs->setCurrentIndex(1);overview->resetView();colorMode->setCurrentIndex(2);clipAxis->setCurrentIndex(0);clipCheck->setChecked(true);break;
  case 7:tabs->setCurrentIndex(0);return;
  case 8:preciseBlend->setChecked(false);tabs->setCurrentIndex(1);overview->turn(10);return;
 }
 QCoreApplication::processEvents();compositeExpected=overview->overviewRequest();
 if(compositeStage!=5&&plComposite->active()&&!processing())plComposite->request(compositeExpected);
}
bool transparentFrameMatches(const QJsonObject&meta,const QJsonObject&state)const{
 auto c=meta["report"].toObject()["controls"].toObject();
 if(c["breathing"]!=state["breathing"])return false;
 if(meta["width"]!=state["width"]||meta["height"]!=state["height"])return false;
 for(const char*k:{"full_lung","layers","clipping","center_lps_mm"})if(c[k]!=state[k])return false;
 for(const char*k:{"yaw_degrees","pitch_degrees","zoom","radius_mm","color_mode","required_radius_mm","resolution_margin_mm"}){
  if(!c[k].isDouble()||!state[k].isDouble()||std::abs(c[k].toDouble()-state[k].toDouble())>1e-4)return false;
 }
 return c["lung_opacity_byte"].toInt(-1)==int(std::floor(state["lung_opacity"].toDouble()*255+.5));
}
QJsonObject  linkedReport;
QJsonArray  linkedTrace;
void finishTest(){
  finishingTest=true;if((plScope&&plScope->active())||(plComposite&&plComposite->active())){releaseGraphics([this]{finishTest();});return;}
  capture("final");for(auto*v:{overview,scope}){auto m=v->metrics();if(!m["valid"].toBool()||!m["shader_linked"].toBool()||!m["error"].toString().isEmpty())failed=true;}QVector<double> sorted=gaps;std::sort(sorted.begin(),sorted.end());QVector<double> jg=jobGaps;std::sort(jg.begin(),jg.end());struct rusage usage{};getrusage(RUSAGE_SELF,&usage);
  QJsonObject o{{"status",failed?"failed":"passed"},{"kind","actual_kv260_native_ui"},{"platform",QApplication::platformName()},{"root",root},{"scene",scenePath},{"input",input},{"actions",actions},{"ui_heartbeat_count",ticks},{"ui_heartbeat_interval_ms",50},{"heartbeat_gap_p95_ms",sorted.isEmpty()?0:sorted[int((sorted.size()-1)*.95)]},{"heartbeat_gap_max_ms",sorted.isEmpty()?0:sorted.last()},{"ct_pages_locked",volume&&volume->ctLocked},{"mask_pages_locked",volume&&volume->maskLocked},{"peak_rss_mib",usage.ru_maxrss/1024.},{"overview",overview->metrics()},{"scope",scope->metrics()},{"dfx_run_output",runOutput},{"dfx_heartbeat_samples",jg.size()},{"dfx_heartbeat_p95_ms",jg.isEmpty()?0:jg[int((jg.size()-1)*.95)]},{"dfx_heartbeat_max_ms",jg.isEmpty()?0:jg.last()},{"lung_rotation_swapped_frames",lungIntervals.size()},{"lung_rotation_fps",lungIntervals.isEmpty()?0:1000.*lungIntervals.size()/std::accumulate(lungIntervals.begin(),lungIntervals.end(),0.)},{"rotation_swapped_frames",swapIntervals.size()},{"rotation_fps",swapIntervals.isEmpty()?0:1000.*swapIntervals.size()/std::accumulate(swapIntervals.begin(),swapIntervals.end(),0.)},{"physical_mouse_verified",false},{"pl_scope_frames",plFrames},{"pl_scope_last_frame",plLastFrame}};
  o["fresh_raw_initial_scene_verified"]=freshRawInitialVerified;o["composite_frame_trace"]=compositeTrace;o["composite_frames"]=compositeFrames;o["composite_last_frame"]=overview->completedComposite();o["features"]=overview->featureMetrics();o["scope_features"]=scope->featureMetrics();o["navigation_interaction"]=navigationTestReport;o["navigation_frame_trace"]=navigationTrace;o["linked_camera_test"]=linkedReport;o["linked_camera_trace"]=linkedTrace;o["linked_overview"]=miniOverview->metrics();writeJson(evidence+"/ui_acceptance.json",o);QApplication::exit(failed?1:0);
 }
void navigationBenchmarkFinish(){
  navigationMotion.stop();play.stop();playing=false;playButton->setText(u("沿路径播放"));scope->setPlayback(false);navigationBenchmarking=false;navigationTestReport["continuous_playback_samples"]=playbackTestTrace;
  double fps=navigationPresented.size()>1?1000.*(navigationPresented.size()-1)/(navigationPresented.last()-navigationPresented.first()):0;
  QVector<double> intervals;for(int i=1;i<navigationPresented.size();++i)intervals.append(navigationPresented[i]-navigationPresented[i-1]);std::sort(intervals.begin(),intervals.end());
  navigationTestReport["quality_level"]=scopeQuality->currentIndex();navigationTestReport["presented_frames"]=navigationPresented.size();navigationTestReport["actual_update_fps"]=fps;
  navigationTestReport["gap_p95_ms"]=intervals.isEmpty()?0:intervals[int((intervals.size()-1)*.95)];navigationTestReport["gap_max_ms"]=intervals.isEmpty()?0:intervals.last();navigationTestReport["pose_after_release"]=scope->cameraRequest();
  scopeWait=0;navigationRefineWait();
 }
void navigationRefineWait(){
  if((plLastFrame["interactive"].toBool()||plLastFrame["width"].toInt()<640)&&scopeWait++<50){QTimer::singleShot(100,this,[this]{navigationRefineWait();});return;}
  auto pose=scope->cameraRequest();navigationTestReport["refined_frame"]=plLastFrame;
  if(plLastFrame["interactive"].toBool()||plLastFrame["width"].toInt()<640||std::abs(pose["manual_yaw_degrees"].toDouble())+std::abs(pose["manual_pitch_degrees"].toDouble())>1||navigationPresented.size()<20)failed=true;
  capture("06_navigation_refined");
  if(scope->property("synthetic_wall_active").toBool()){
   scope->setDistance(scope->totalDistance());scope->resetView();
   QTimer::singleShot(1200,this,[this]{syntheticWallTestWait(0);});return;
  }
  finishTest();
 }
void syntheticWallTestWait(int attempt){
  auto frame=plLastFrame;auto request=frame["requested_camera"].toObject();
  bool ready=frame["width"].toInt()>=640&&!frame["interactive"].toBool()&&std::abs(request["arc_mm"].toDouble()-scope->totalDistance())<.01;
  if(!ready&&attempt<80){QTimer::singleShot(100,this,[this,attempt]{syntheticWallTestWait(attempt+1);});return;}
  navigationTestReport["synthetic_wall_endpoint_frame"]=frame;
  navigationTestReport["synthetic_wall_endpoint_ready"]=ready;
  if(!ready)failed=true;capture("07_synthetic_wall_target");finishTest();
 }
void smokeAdvance(){
  if(!smoke||scenePath.isEmpty())return;if(processing()){QTimer::singleShot(100,this,[this]{smokeAdvance();});return;}
  if(!smokeStarted){smokeStarted=true;
   if(qEnvironmentVariableIntValue("KV260_FORCE_RAW_CT_TEST")==1){
    if(!freshRawInitialVerified||!runButton->isEnabled()||navigationTargetForJob("all")!=0){failed=true;finishTest();return;}
    smokeStep=5;runButton->click();return;
   }
   QTimer::singleShot(500,this,[this]{smokeAdvance();});return;}
  switch(smokeStep++){
   case 0:tabs->setCurrentIndex(0);axialSlider->setValue(qMin(70,axialSlider->maximum()));record("slice_changed");capture("01_slices");break;
   case 1:if(acceptance)preciseBlend->setChecked(true);tabs->setCurrentIndex(1);overview->resetView();record("overview_opened");break;
   case 2:if(featureTesting){if(lesionList->count()==0||scene["meshes"].toObject()["airway"].toObject()["attributes"].toObject().isEmpty())failed=true;focusCandidate();capture("feature_focus");overview->resetView();for(int mode:{1,2}){colorMode->setCurrentIndex(mode);capture(mode==1?"feature_generation":"feature_reachability");}clipCheck->setChecked(true);capture("feature_clip");clipCheck->setChecked(false);colorMode->setCurrentIndex(0);record("features_checked");}testDrag(overview,QPoint(180,160),QPoint(260,200));record("mouse_drag_overview");capture("02_model");break;
   case 3:tabs->setCurrentIndex(2);firstBranchPose();record("navigation_camera_changed");if(featureTesting){capture("navigation_preparing");if(!scope->featureMetrics()["last_paint_awaiting_pl"].toBool())failed=true;}break;
   case 4:if((plFrames==0||(!scene["navigation"].toObject()["report"].toObject()["branch_guidance"].toObject()["events"].toArray().isEmpty()&&plLastFrame["branch_event"].toInt(-1)<0))&&scopeWait++<100){--smokeStep;QTimer::singleShot(700,this,[this]{smokeAdvance();});return;}if(plFrames==0||(!scene["navigation"].toObject()["report"].toObject()["branch_guidance"].toObject()["events"].toArray().isEmpty()&&plLastFrame["branch_event"].toInt(-1)<0))failed=true;if(featureTesting){dualCheck->setChecked(true);QApplication::processEvents();capture("feature_linked_overview");dualCheck->setChecked(false);QApplication::processEvents();if(scope->featureMetrics()["overlay_paints"].toInt()==0)failed=true;}capture("03_navigation");if(navigationTesting&&!navigationBenchStarted){navigationBenchStarted=true;navigationBase=cameraSlider->value();navigationMotionClock.restart();navigationBenchmarking=true;scope->setPlayback(true);testDrag(scope,QPoint(200,170),QPoint(280,200));navigationTestReport["pose_after_drag"]=scope->cameraRequest();if(std::abs(scope->cameraRequest()["manual_yaw_degrees"].toDouble())<10)failed=true;if(qEnvironmentVariableIntValue("KV260_NAV_TEST_PLAYBACK")==1)playButton->click();else navigationMotion.start(16);QTimer::singleShot(8500,this,[this]{navigationBenchmarkFinish();});return;}if(acceptance){runButton->click();return;}break;
   case 5:if(acceptance&&!verifiedScopeReturn){if(returnFrameBase<0){returnFrameBase=plFrames;scopeWait=0;tabs->setCurrentIndex(2);configureScope();firstBranchPose();}if((plFrames<=returnFrameBase||(!scene["navigation"].toObject()["report"].toObject()["branch_guidance"].toObject()["events"].toArray().isEmpty()&&plLastFrame["branch_event"].toInt(-1)<0))&&scopeWait++<100){--smokeStep;QTimer::singleShot(700,this,[this]{smokeAdvance();});return;}if(plFrames<=returnFrameBase||(!scene["navigation"].toObject()["report"].toObject()["branch_guidance"].toObject()["events"].toArray().isEmpty()&&plLastFrame["branch_event"].toInt(-1)<0))failed=true;verifiedScopeReturn=true;record("pl_scope_resumed_after_medical_dfx");capture("05_scope_after_dfx");}tabs->setCurrentIndex(1);record("rotation_benchmark_started");QTimer::singleShot(250,this,[this]{benchmarking=true;swapClock.restart();rotation.start(16);});QTimer::singleShot(5500,this,[this]{benchmarking=false;rotation.stop();record("rotation_benchmark_finished");smokeAdvance();});return;
   case 6:overview->setLayer(0,true);lungBenchmark=true;record("full_lung_benchmark_started");QTimer::singleShot(800,this,[this]{benchmarking=true;swapClock.restart();rotation.start(16);});QTimer::singleShot(5800,this,[this]{benchmarking=false;rotation.stop();capture("04_all_structures");overview->setLayer(0,false);record("full_lung_benchmark_finished");smokeAdvance();});return;
   default:finishTest();return;
  }
  QTimer::singleShot(700,this,[this]{smokeAdvance();});
 }
public:
MainWindow(QString project,QString initial,bool testing,bool realRun,bool navTesting,QString output,int navQuality,bool featuresTest):root(project),input(initial),evidence(output),smoke(testing),acceptance(realRun),navigationTesting(navTesting){featureTesting=featuresTest;
  setWindowTitle(u("KV260 医疗影像工作站"));setProperty("role","window");setAttribute(Qt::WA_StyledBackground,true);resize(1024,768);setMinimumSize(780,580);
  // 界面 v2 构建段（替换原构建段）：创建的控件、objectName 和信号连接与原段逐条对应，只改变摆放和可见文字。
  // V3：原界面构建段整体放进隐藏的 legacyHost，作为 QML 外框的状态模型
  legacyHost=new QWidget(this);legacyHost->hide();
  auto*outer=new QVBoxLayout(legacyHost);outer->setContentsMargins(0,0,0,0);outer->setSpacing(0);

  // ── 顶栏：品牌 · 模式切换 · 主操作 · 状态 ──
  auto*headerBar=new QFrame;headerBar->setObjectName("headerBar");headerBar->setFixedHeight(52);outer->addWidget(headerBar);
  auto*header=new QHBoxLayout(headerBar);header->setContentsMargins(12,0,12,0);header->setSpacing(8);
  sideToggle=new QPushButton;sideToggle->setProperty("role","icon");sideToggle->setCheckable(true);sideToggle->setIcon(glyphIcon("sidebar",tone("ink2"),tone("accent")));
  sideToggle->setIconSize(QSize(18,18));sideToggle->setToolTip(u("收起 / 展开左侧面板，给图像留出更大空间"));header->addWidget(sideToggle);
  auto*brand=new QLabel;brand->setPixmap(glyph("brand",QColor()).scaled(26,26,Qt::KeepAspectRatio,Qt::SmoothTransformation));header->addWidget(brand);
  auto*title=new QLabel(u("支气管导航工作站"));title->setObjectName("title");header->addWidget(title);header->addSpacing(14);
  auto*modeBar=new QFrame;modeBar->setObjectName("modeBar");auto*modeLayout=new QHBoxLayout(modeBar);modeLayout->setContentsMargins(3,3,3,3);modeLayout->setSpacing(2);
  auto*modeGroup=new QButtonGroup(this);modeGroup->setExclusive(true);
  {QStringList modeNames={u("影像"),u("三维"),u("导航")},modeIcons={"image","cube","route"};
   QStringList modeTips={u("CT 切片与气道分割"),u("三维模型：肺、气道、病灶和路径"),u("沿路径的虚拟支气管镜")};
   for(int i=0;i<3;++i){auto*b=new QPushButton(modeNames[i]);b->setProperty("role","mode");b->setCheckable(true);b->setChecked(i==0);b->setToolTip(modeTips[i]);
    b->setIcon(glyphIcon(modeIcons[i],tone("ink2"),QColor(Qt::white)));b->setIconSize(QSize(16,16));modeGroup->addButton(b,i);modeLayout->addWidget(b);
    b->setToolTip(modeTips[i]+QString(u("（Ctrl+%1）")).arg(i+1));
    auto*key=new QShortcut(QKeySequence(Qt::CTRL+Qt::Key_1+i),this);connect(key,&QShortcut::activated,this,[this,i]{tabs->setCurrentIndex(i);});}}
  modeBar->setFixedHeight(38);header->addWidget(modeBar);header->addStretch();
  runButton=new QPushButton(u("开始完整处理"));runButton->setObjectName("primary");runButton->setIcon(glyphIcon("play",QColor(Qt::white)));runButton->setIconSize(QSize(12,12));
  runButton->setToolTip(u("依次完成气道分割、三维重建和导航规划"));runButton->setFixedHeight(32);header->addWidget(runButton);
  stopButton=new QPushButton(u("停止后续步骤"));stopButton->setProperty("role","danger");stopButton->setIcon(glyphIcon("stop",QColor("#ff9aa5")));stopButton->setIconSize(QSize(11,11));
  stopButton->setToolTip(u("当前步骤完成后停止，不中断正在进行的计算"));stopButton->setFixedHeight(32);stopButton->setEnabled(false);header->addWidget(stopButton);
  header->addSpacing(6);{auto*line=divider(true);line->setFixedHeight(22);header->addWidget(line);}header->addSpacing(2);
  gpuLabel=new QLabel(u("图形初始化"),this);gpuLabel->hide();
  themeToggle=new QPushButton;themeToggle->setProperty("role","icon");themeToggle->setCheckable(true);themeToggle->setIconSize(QSize(18,18));
  themeToggle->setIcon(glyphIcon("moon",tone("ink2")));themeToggle->setToolTip(u("切换浅色 / 深色主题；图像区始终保持深色"));header->addWidget(themeToggle);
  connect(themeToggle,&QPushButton::toggled,this,[this](bool light){setStyleSheet(redesignStyleSheet(light));themeToggle->setIcon(glyphIcon(light?"sun":"moon",tone("ink2",light)));});
  clock=new QLabel;clock->setObjectName("clock");header->addWidget(clock);
  auto*close=new QPushButton(u("退出"));close->setProperty("role","flat");header->addWidget(close);connect(close,&QPushButton::clicked,this,&QWidget::close);

  auto*body=new QHBoxLayout;body->setContentsMargins(12,12,12,10);body->setSpacing(12);outer->addLayout(body,1);

  // ── 左侧面板：病例摘要常显，其余按工作流分区，同时只展开一个 ──
  auto*sidebar=new QFrame;sidebar->setObjectName("sidePanel");auto*left=new QVBoxLayout(sidebar);left->setContentsMargins(0,0,0,0);left->setSpacing(0);
  auto*sideRoot=left;
  auto*caseSummary=new QFrame;caseSummary->setObjectName("caseSummary");auto*caseLayout=new QVBoxLayout(caseSummary);caseLayout->setContentsMargins(14,12,14,12);caseLayout->setSpacing(3);
  caseLayout->addWidget(caption(u("当前病例")));
  caseLabel=new QLabel(u("未选择 CT"));caseLabel->setObjectName("caseName");caseLabel->setWordWrap(true);caseLayout->addWidget(caseLabel);
  info=new QLabel;info->setWordWrap(true);info->setObjectName("muted");caseLayout->addWidget(info);
  sideRoot->addWidget(caseSummary);sideRoot->addWidget(divider());
  auto*caseCard=foldSection(sideRoot,u("病例与数据"),true,true);sideRoot->addWidget(divider());
  auto*processCard=foldSection(sideRoot,u("处理流程"),false,true);sideRoot->addWidget(divider());
  auto*targetCard=foldSection(sideRoot,u("目标与器械"),false,true);sideRoot->addWidget(divider());
  auto*exportCard=foldSection(sideRoot,u("导出与记录"),false,true);sideRoot->addWidget(divider());
  left=caseCard;
  openButton=button(u("打开 CT 文件"),left);openButton->setProperty("role","accent");
  dicomButton=button(u("导入 DICOM 目录"),left);dicomButton->setToolTip(u("选择 DICOM 根目录，包含子目录中的所有序列"));
  importButton=button(u("导入外部分割"),left);importButton->setToolTip(u("导入掩膜或概率图：选择属于当前CT的外部影像清单；校验文件及物理坐标，不自动重采样。"));
  results=new QComboBox;results->setMinimumWidth(0);results->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
  left->addSpacing(4);left->addWidget(caption(u("历史结果")));left->addWidget(results);refreshButton=button(u("重新载入"),left);
  left=processCard;
  rebuildButton=button(u("重新生成三维模型"),left);rebuildButton->setToolTip(u("用当前分割重新重建并平滑三维表面"));
  navButton=button(u("重新规划导航"),left);navButton->setToolTip(u("按当前目标和器械参数重新计算路径"));
  segmentationInfo=new QLabel(u("PL HU/卷积＋PS层间算子、气道清理和调度"));segmentationInfo->setObjectName("segmentation_statistics");segmentationInfo->setProperty("role","muted");segmentationInfo->setWordWrap(true);left->addWidget(segmentationInfo);
  left=targetCard;
  lesion=new QSpinBox;lesion->setRange(-1,1000000000);lesion->hide();
  left->addWidget(caption(u("目标候选")));
  lesionList=new QComboBox;lesionList->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);left->addWidget(lesionList);
  candidateInfo=new QLabel;candidateInfo->setWordWrap(true);candidateInfo->setObjectName("muted");left->addWidget(candidateInfo);
  focusButton=button(u("在模型中定位该候选"),left);
  auto*form=new QFormLayout;form->setContentsMargins(0,4,0,2);form->setHorizontalSpacing(10);form->setVerticalSpacing(6);form->setLabelAlignment(Qt::AlignLeft|Qt::AlignVCenter);
  minimumCandidateVolume=new QDoubleSpinBox;minimumCandidateVolume->setRange(0,1.e9);minimumCandidateVolume->setDecimals(1);minimumCandidateVolume->setValue(14);minimumCandidateVolume->setSuffix(u(" mm³"));minimumCandidateVolume->setToolTip(u("按原始体素的物理体积筛选候选，0 显示全部；不修改分割或重建模型。"));form->addRow(caption(u("最小候选体积")),minimumCandidateVolume);
  diameter=new QDoubleSpinBox;diameter->setRange(.1,10);diameter->setDecimals(1);diameter->setValue(1);diameter->setSuffix(" mm");form->addRow(caption(u("器械直径")),diameter);
  margin=new QDoubleSpinBox;margin->setRange(0,5);margin->setDecimals(1);margin->setSingleStep(.1);margin->setValue(.2);margin->setSuffix(" mm");margin->setToolTip(u("器械每侧与气道壁之间至少保留的距离"));form->addRow(caption(u("安全余量")),margin);
  left->addLayout(form);
  compareButton=button(u("比较器械与路径"),left);compareButton->setToolTip(u("比较不同器械直径在全气道中的可达范围和备选接近路径"));
  comparisonResults=button(u("查看比较结果"),left);comparisonResults->setEnabled(false);
  left=exportCard;
  exportButton=button(u("导出模型与报告"),left);exportButton->setToolTip(u("导出三维模型、颜色、导航路径和报告"));
  snapshotButton=button(u("保存截图"),left);snapshotButton->setToolTip(u("保存当前画面为 PNG（Ctrl+S）"));
  videoButton=button(u("导出导航视频"),left);videoButton->setToolTip(u("沿当前路径录制 MP4 视频"));connect(videoButton,&QPushButton::clicked,this,[this]{videoRequest();});
  connect(snapshotButton,&QPushButton::clicked,this,[this]{captureRequest();});
  auto*snapshotShortcut=new QShortcut(QKeySequence("Ctrl+S"),this);connect(snapshotShortcut,&QShortcut::activated,this,[this]{captureRequest();});
  sideRoot->addStretch();
  sideScroll=new QScrollArea;sideScroll->setWidget(sidebar);sideScroll->setWidgetResizable(true);sideScroll->setFixedWidth(250);sideScroll->setFrameShape(QFrame::NoFrame);sideScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);body->addWidget(sideScroll);
  connect(sideToggle,&QPushButton::toggled,sideScroll,[this](bool hidden){sideScroll->setVisible(!hidden);if(tabs)sideHidden[tabs->currentIndex()]=hidden;});

  tabs=new QTabWidget;connect(tabs,&QTabWidget::currentChanged,this,[this](int i){if(stage&&!shellDead)stage->setCurrentIndex(i);});tabs->setDocumentMode(true);tabs->tabBar()->hide();body->addWidget(tabs,1);
  connect(modeGroup,&QButtonGroup::idClicked,tabs,&QTabWidget::setCurrentIndex);
  connect(tabs,&QTabWidget::currentChanged,modeGroup,[modeGroup](int i){if(auto*b=modeGroup->button(i))b->setChecked(true);});
  connect(tabs,&QTabWidget::currentChanged,this,[this](int i){if(i>=0&&i<3)sideToggle->setChecked(sideHidden[i]);});

  // ── 影像页：工具条 · 三视图 · 层面滑条 ──
  auto*ctPage=new QWidget;auto*ctLayout=new QVBoxLayout(ctPage);ctLayout->setContentsMargins(0,0,0,0);ctLayout->setSpacing(10);
  auto*toolbar=new QFrame;toolbar->setObjectName("toolbar");auto*tools=new QHBoxLayout(toolbar);tools->setContentsMargins(12,7,10,7);tools->setSpacing(8);
  tools->addWidget(caption(u("窗位")));windowPreset=new QComboBox;windowPreset->addItems({u("肺窗"),u("纵隔窗"),u("骨窗")});tools->addWidget(windowPreset);
  tools->addSpacing(4);tools->addWidget(divider(true));tools->addSpacing(4);
  auto*mask=new QCheckBox(u("显示分割"));mask->setChecked(true);tools->addWidget(mask);
  tools->addStretch();
  ctLayout->addWidget(toolbar);
  
  auto*grid=new QGridLayout;grid->setSpacing(8);slices[0]=new SliceView(2,u("轴位"));slices[1]=new SliceView(1,u("冠状位"));slices[2]=new SliceView(0,u("矢状位"));
  grid->addWidget(slices[0],0,0,2,1);grid->addWidget(slices[1],0,1);grid->addWidget(slices[2],1,1);grid->setColumnStretch(0,3);grid->setColumnStretch(1,2);grid->setRowStretch(0,1);grid->setRowStretch(1,1);ctLayout->addLayout(grid,1);
  auto*sliceStrip=new QFrame;sliceStrip->setObjectName("viewStrip");auto*sliceLayout=new QGridLayout(sliceStrip);sliceLayout->setContentsMargins(12,6,12,6);sliceLayout->setHorizontalSpacing(10);sliceLayout->setVerticalSpacing(2);
  axialSlider=new QSlider(Qt::Horizontal);axialSlider->setToolTip(u("拖动切换轴位层面"));sliceLayout->addWidget(caption(u("层面")),0,0);sliceLayout->addWidget(axialSlider,0,1);
  coordinate=new QLabel(u("滚轮翻页 · 单击图像查看该点 CT 值与坐标"));coordinate->setObjectName("muted");sliceLayout->addWidget(coordinate,1,1);ctLayout->addWidget(sliceStrip);
  tabs->addTab(ctPage,u("影像 / 分割"));

  // ── 三维页：大视口 + 右侧检查器 ──
  auto*meshPage=new QWidget;auto*meshOuter=new QHBoxLayout(meshPage);meshOuter->setContentsMargins(0,0,0,0);meshOuter->setSpacing(12);auto*meshLayout=new QVBoxLayout;meshLayout->setSpacing(10);meshOuter->addLayout(meshLayout,1);
  QVBoxLayout*displayPanel=nullptr;inspector(meshOuter,248,displayPanel);
  auto*structureSection=foldSection(displayPanel,u("结构与视角"),true,false);displayPanel->addWidget(divider());
  auto*colorSection=foldSection(displayPanel,u("气道着色"),true,false);displayPanel->addWidget(divider());
  auto*displaySection=foldSection(displayPanel,u("显示效果"),true,false);displayPanel->addWidget(divider());
  auto*clipSection=foldSection(displayPanel,u("剖切"),false,false);displayPanel->addWidget(divider());
  QStringList names={u("肺"),u("气道"),u("病灶候选")};overview=new MeshView;scope=new MeshView;
  auto*layers=new QGridLayout;layers->setHorizontalSpacing(10);layers->setVerticalSpacing(4);
  for(int i=0;i<3;++i){auto*c=new QCheckBox(names[i]);meshLayers[i]=c;c->setChecked(i!=0);layers->addWidget(c,i/2,i%2);connect(c,&QCheckBox::toggled,this,[this,i](bool enabled){overview->setLayer(i,enabled);if(!settingStructure)structureMode=2;});}
  meshLayers[0]->setToolTip(u("半透明显示肺表面"));
  routeCheck=new QCheckBox(u("导航路径"));routeCheck->setChecked(true);layers->addWidget(routeCheck,1,1);connect(routeCheck,&QCheckBox::toggled,overview,&MeshView::setRoute);structureSection->addLayout(layers);
  auto*structureTools=new QGridLayout;structureTools->setSpacing(6);QStringList presetNames={u("只看肺"),u("只看支气管"),u("恢复组合")};
  for(int i=0;i<3;++i){auto*b=new QPushButton(presetNames[i]);structureButtons[i]=b;structureTools->addWidget(b,i/2,i%2);connect(b,&QPushButton::clicked,this,[this,i]{showStructure(i);});}
  structureButtons[2]->setToolTip(u("回到自己勾选的结构组合"));
  auto*fit=new QPushButton(u("适配视野"));fit->setToolTip(u("缩放到当前可见结构"));structureTools->addWidget(fit,1,1);connect(fit,&QPushButton::clicked,overview,&MeshView::fitVisible);
  auto*reset=new QPushButton(u("复位视角"));structureTools->addWidget(reset,2,0,1,2);connect(reset,&QPushButton::clicked,overview,&MeshView::resetView);
  structureSection->addSpacing(4);structureSection->addLayout(structureTools);
  structureAvailability=new QLabel;structureAvailability->setObjectName("structureAvailability");structureAvailability->setWordWrap(true);structureSection->addWidget(structureAvailability);
  auto*analysisTools=colorSection;colorMode=new QComboBox;colorMode->addItems({u("按结构"),u("按分支级数"),u("按器械可达性")});analysisTools->addWidget(colorMode);
  legend=new QLabel;legend->setObjectName("muted");legend->setWordWrap(true);analysisTools->addWidget(legend);
  auto*clipRow=new QHBoxLayout;clipCheck=new QCheckBox(u("启用剖切"));clipRow->addWidget(clipCheck);clipAxis=new QComboBox;clipAxis->addItems({u("左右 (X)"),u("前后 (Y)"),u("头足 (Z)")});clipAxis->setCurrentIndex(2);clipRow->addWidget(clipAxis,1);clipSection->addLayout(clipRow);
  clipOffset=new QSlider(Qt::Horizontal);clipOffset->setRange(-100,100);clipOffset->setToolTip(u("移动剖切面位置"));clipSection->addWidget(caption(u("剖切位置")));clipSection->addWidget(clipOffset);
  opacity=new QSlider(Qt::Horizontal);opacity->setRange(0,100);opacity->setToolTip(u("左端完全透明，右端完全不透明。快速模式显示最近一层肺表面；精确透明显示多层表面。"));opacity->setValue(20);
  displaySection->addWidget(caption(u("肺不透明度")));displaySection->addWidget(opacity);
  meshLayout->addWidget(overview,1);
  auto*blendStrip=new QFrame;blendStrip->setObjectName("viewStrip");auto*blendTools=new QHBoxLayout(blendStrip);blendTools->setContentsMargins(12,6,12,6);blendTools->setSpacing(14);
  preciseBlend=new QCheckBox(u("高质量透明（PL）"));preciseBlend->setToolTip(u("停止操作后逐层排序肺表面并用 PL 精确合成；交互预览保留所选网格，使用近似透明。"));blendTools->addWidget(preciseBlend);
  compositePerf=new QLabel(u("快速总览 · 拖动旋转 / 滚轮缩放"));compositePerf->setObjectName("muted");compositePerf->setAlignment(Qt::AlignRight|Qt::AlignVCenter);compositePerf->setSizePolicy(QSizePolicy::Ignored,QSizePolicy::Preferred);blendTools->addWidget(compositePerf,1);
  meshLayout->addWidget(blendStrip);
  connect(preciseBlend,&QCheckBox::toggled,this,[this](bool enabled){overview->setCompositeEnabled(enabled);compositeQuiet.stop();if(enabled){overview->setCompositePreview(true);compositeQuiet.start(450);}else configureScope();});
  displayPanel->addStretch();tabs->addTab(meshPage,u("三维模型"));

  // ── 导航页：路径提示 · 虚拟镜视图 · 播放条 + 右侧检查器 ──
  auto*navPage=new QWidget;auto*navOuter=new QHBoxLayout(navPage);navOuter->setContentsMargins(0,0,0,0);navOuter->setSpacing(12);
  auto*navLayout=new QVBoxLayout;navLayout->setSpacing(10);navOuter->addLayout(navLayout,1);
  QVBoxLayout*navPanel=nullptr;navInspector=inspector(navOuter,216,navPanel);
  routeInfo=new QLabel(u("尚无导航结果"));routeInfo->setObjectName("notice");routeInfo->setWordWrap(true);navLayout->addWidget(routeInfo);
  auto*dualLayout=new QHBoxLayout;dualLayout->setSpacing(8);scopeUnavailable=new QLabel(u("尚无导航路径，请先重新规划导航。"));scopeUnavailable->setObjectName("scopeUnavailable");scopeUnavailable->setAlignment(Qt::AlignCenter);scopeUnavailable->setWordWrap(true);scopeUnavailable->hide();dualLayout->addWidget(scopeUnavailable,2);
  dualLayout->addWidget(scope,2);miniOverview=new MeshView;miniOverview->setMinimumWidth(180);miniOverview->setLayer(1,true);miniOverview->setLayer(2,true);miniOverview->hide();dualLayout->addWidget(miniOverview,1);navLayout->addLayout(dualLayout,1);
  auto*transport=new QFrame;transport->setObjectName("viewStrip");auto*transportRow=new QHBoxLayout(transport);transportRow->setContentsMargins(10,6,8,6);transportRow->setSpacing(6);
  cameraSlider=new QSlider(Qt::Horizontal);cameraSlider->setToolTip(u("拖动到路径上的任意位置"));navLayout->addWidget(transport);
  playButton=new QPushButton(u("沿路径播放"));playButton->setProperty("role","accent");playButton->setMinimumWidth(96);
  auto*resetScope=new QPushButton(u("回正镜头"));resetScope->setToolTip(u("镜头回到路径方向（也可双击画面）"));
  navigationAlign=new QCheckBox(u("自动对齐路径"));navigationAlign->setChecked(true);
  dualCheck=new QCheckBox(u("联动总览"));dualCheck->setToolTip(u("在右侧同步显示三维总览和当前镜头位置"));
  connect(navigationAlign,&QCheckBox::toggled,scope,&MeshView::setAutoAlign);
  auto*cameraSection=foldSection(navPanel,u("镜头"),true,false);navPanel->addWidget(divider());
  auto*motionSection=foldSection(navPanel,u("播放"),true,false);navPanel->addWidget(divider());
  auto*pictureSection=foldSection(navPanel,u("画面"),true,false);navPanel->addWidget(divider());
  auto*helpSection=foldSection(navPanel,u("操作提示"),false,false);
  cameraSection->addWidget(resetScope);cameraSection->addWidget(navigationAlign);cameraSection->addWidget(dualCheck);
  installGamepadControls(cameraSection);
  auto*qualityTools=new QHBoxLayout;qualityTools->setSpacing(8);scopeQuality=new QComboBox;scopeQuality->addItems({u("清晰 · 640"),u("自动 384→640"),u("流畅 · 256")});scopeQuality->setCurrentIndex(navQuality);scopeQuality->setToolTip(u("清晰：始终宽 640；均衡/流畅：移动时宽 384/256，停止后恢复宽 640。只调整显示像素数。"));
  qualityTools->addWidget(caption(u("画质")));qualityTools->addWidget(scopeQuality,1);pictureSection->addLayout(qualityTools);
  connect(scopeQuality,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this](int level){plScope->setQuality(level);if(plScope->active())plScope->request(scope->cameraRequest());});
  scopePerf=new QLabel(u("默认清晰画面 · 可选择均衡或流畅"));scopePerf->setObjectName("muted");scopePerf->setWordWrap(true);pictureSection->addWidget(scopePerf);
  auto*exposureRow=new QHBoxLayout;installExposure(exposureRow);exposureToggle->setText(u("画面曝光校正"));exposureToggle->setToolTip(exposureToggle->toolTip()+u("\n后台 PS 四核处理。"));
  pictureSection->addLayout(exposureRow);verticalizeLastRow(pictureSection);exposureStatus->setProperty("role","muted");
  navigationControls(motionSection);
  {// 导航控件模块按 [速度][值][步长][值][后退][前进][起点][终点] 横排安装，并在其后追加位置标签；拆开后分别放入播放条和检查器。
   auto*row=qobject_cast<QBoxLayout*>(motionSection->itemAt(motionSection->count()-2)->layout());QList<QWidget*> parts;
   while(row&&row->count()){auto*item=row->takeAt(0);if(auto*w=item->widget())parts.append(w);delete item;}
   if(row){motionSection->removeItem(row);delete row;}motionSection->removeWidget(navigationPosition);
   auto*motionForm=new QFormLayout;motionForm->setHorizontalSpacing(10);motionForm->setVerticalSpacing(6);
   for(auto*w:parts)if(auto*l=qobject_cast<QLabel*>(w)){l->setProperty("role","caption");}
   navigationSpeed->setMaximumWidth(QWIDGETSIZE_MAX);navigationStep->setMaximumWidth(QWIDGETSIZE_MAX);
   if(parts.size()==8){motionForm->addRow(parts[0],navigationSpeed);motionForm->addRow(parts[2],navigationStep);}else{motionForm->addRow(caption(u("速度")),navigationSpeed);motionForm->addRow(caption(u("步长")),navigationStep);}
   motionSection->addLayout(motionForm);
   navStart->setToolTip(u("回到起点（Home）"));navBackward->setToolTip(u("后退一步（S / ←）"));navForward->setToolTip(u("前进一步（W / →）"));navEnd->setToolTip(u("到达终点（End）"));
   transportRow->addWidget(navStart);transportRow->addWidget(navBackward);transportRow->addWidget(playButton);transportRow->addWidget(navForward);transportRow->addWidget(navEnd);
   transportRow->addSpacing(6);transportRow->addWidget(cameraSlider,1);transportRow->addSpacing(4);
   navigationPosition->setObjectName("muted");navigationPosition->setSizePolicy(QSizePolicy::Fixed,QSizePolicy::Preferred);navigationPosition->setFixedWidth(136);
   navigationPosition->setAlignment(Qt::AlignRight|Qt::AlignVCenter);transportRow->addWidget(navigationPosition);
   navPanelToggle=new QPushButton;navPanelToggle->setProperty("role","icon");navPanelToggle->setCheckable(true);navPanelToggle->setChecked(true);navPanelToggle->setIcon(glyphIcon("panel",tone("ink2"),tone("accent")));
   navPanelToggle->setIconSize(QSize(18,18));navPanelToggle->setToolTip(u("显示 / 隐藏右侧设置面板"));transportRow->addWidget(navPanelToggle);
   connect(navPanelToggle,&QPushButton::toggled,navInspector,&QWidget::setVisible);
  }
  auto*keys=new QLabel(u("滚轮：前进 / 后退\n双击画面：回正镜头\nW / S 或方向键：逐步移动\n1 / 2：减小 / 增大步长\nHome / End：起点 / 终点\n空格：播放 / 暂停"));keys->setObjectName("muted");helpSection->addWidget(keys);
  navPanel->addStretch();tabs->addTab(navPage,u("导航"));

  // ── 底部状态栏：状态文字 · 后台计时 · 进度 · 日志 ──
  auto*statusBar=new QFrame;statusBar->setObjectName("statusBar");statusBar->setFixedHeight(34);auto*statusRow=new QHBoxLayout(statusBar);statusRow->setContentsMargins(14,0,10,0);statusRow->setSpacing(12);
  auto*stateDot=new QLabel;stateDot->setObjectName("stateDot");stateDot->setFixedSize(8,8);stateDot->setToolTip(u("绿色：就绪；蓝色：后台处理中"));statusRow->addWidget(stateDot);
  auto*stateTimer=new QTimer(this);connect(stateTimer,&QTimer::timeout,this,[this,stateDot]{bool now=processing();if(stateDot->property("busy").toBool()!=now){stateDot->setProperty("busy",now);stateDot->style()->unpolish(stateDot);stateDot->style()->polish(stateDot);}});stateTimer->start(300);
  task=new QLabel(u("准备启动"));task->setObjectName("status");task->setSizePolicy(QSizePolicy::Ignored,QSizePolicy::Preferred);statusRow->addWidget(task,1);
  elapsed=new QLabel;elapsed->setObjectName("muted");statusRow->addWidget(elapsed);
  auto*note=new QLabel(u("实验系统 · 病灶为模型候选，仅供参考"));note->setObjectName("muted");note->setToolTip(u("显示与医疗计算独立运行"));statusRow->addWidget(note);
  progress=new QProgressBar;progress->setFixedSize(180,6);progress->setTextVisible(false);statusRow->addWidget(progress);
  logToggle=new QPushButton(u("日志"));logToggle->setProperty("role","flat");logToggle->setCheckable(true);statusRow->addWidget(logToggle);
  log=new QPlainTextEdit;log->setReadOnly(true);log->setMaximumHeight(120);log->setMaximumBlockCount(100);log->hide();
  auto*logHost=new QVBoxLayout;logHost->setContentsMargins(12,0,12,8);logHost->addWidget(log);outer->addLayout(logHost);outer->addWidget(statusBar);
  connect(logToggle,&QPushButton::toggled,log,&QWidget::setVisible);
  sideToggle->setChecked(sideHidden[0]);

  connect(axialSlider,&QSlider::valueChanged,slices[0],&SliceView::setSlice);slices[0]->onSlice=[this](int value){axialSlider->setValue(value);};for(auto*s:slices)s->onPosition=[this](QString text){coordinate->setText(text);};
  connect(windowPreset,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this](int i){float c[]={-600,40,400},w[]={1500,400,1800};for(auto*s:slices)s->windowLevel(c[i],w[i]);});connect(mask,&QCheckBox::toggled,this,[this](bool enabled){for(auto*s:slices)s->setMask(enabled);});
  
  connect(dualCheck,&QCheckBox::toggled,this,[this](bool enabled){if(enabled&&!scenePath.isEmpty()){miniOverview->loadScene(scenePath,scene);applyAttributeSampling();miniOverview->selectCandidate(lesion->value());miniOverview->setColorMode(colorMode->currentIndex());miniOverview->setAnalysisParameters(diameter->value(),margin->value());}miniOverview->setVisible(enabled);if(enabled)syncLinkedOverview();});
  connect(lesionList,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this]{updateCandidate();});overview->onCandidatePicked=[this](int index){int i=lesionList->findData(index);if(i>=0)lesionList->setCurrentIndex(i);};
  connect(minimumCandidateVolume,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this]{refreshCandidates();});connect(focusButton,&QPushButton::clicked,this,[this]{focusCandidate();});connect(diameter,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this]{updateAnalysis();});connect(margin,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this]{updateAnalysis();});
  connect(colorMode,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this](int i){overview->setColorMode(i);miniOverview->setColorMode(i);updateColorLegend();applyAttributeSampling();});
  auto clipping=[this]{overview->setClipping(clipCheck->isChecked(),clipAxis->currentIndex(),clipOffset->value()/100.f);};connect(clipCheck,&QCheckBox::toggled,this,[clipping]{clipping();});connect(clipAxis,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[clipping]{clipping();});connect(clipOffset,&QSlider::valueChanged,this,[clipping]{clipping();});connect(opacity,&QSlider::valueChanged,this,[this](int value){applyOverviewOpacity();});
  miniOverview->setReferenceCamera({});connect(cameraSlider,&QSlider::valueChanged,scope,&MeshView::setCamera);scope->onCamera=[this](int){syncNavigationControlsFromCamera();if(playing){playbackStart=scope->distance();playbackClock.restart();}};connect(resetScope,&QPushButton::clicked,scope,&MeshView::resetView);
  connect(playButton,&QPushButton::clicked,this,[this]{navigationToggle();});
  play.setTimerType(Qt::PreciseTimer);
  connect(&play,&QTimer::timeout,this,[this]{navigationTick();});
  connect(cameraSlider,&QSlider::valueChanged,this,[this]{navigationPosition->setText(QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,'f',1).arg(scope->totalDistance(),0,'f',1));if(playing){playbackStart=scope->distance();playbackClock.restart();}});
  connect(&navigationMotion,&QTimer::timeout,this,[this]{int phase=(navigationMotionClock.elapsed()/16)%48;cameraSlider->setValue(navigationBase+(phase<24?phase-12:36-phase));});
  connect(&rotation,&QTimer::timeout,this,[this]{overview->turn(.8f);});connect(overview,&QOpenGLWidget::frameSwapped,this,[this]{if(benchmarking){if(lungBenchmark)lungIntervals.append(swapClock.nsecsElapsed()/1.e6);else swapIntervals.append(swapClock.nsecsElapsed()/1.e6);swapClock.restart();}});
  overview->onBackend=scope->onBackend=[this](QString name){gpuLabel->setText(name.contains("Mali",Qt::CaseInsensitive)?u("Mali GPU"):u("软件渲染"));gpuLabel->setToolTip(name);};
  connect(openButton,&QPushButton::clicked,this,[this]{QString p=QFileDialog::getOpenFileName(this,u("选择 CT"),QFileInfo(input).absolutePath(),"CT (*.nrrd *.nii *.nii.gz *.mha *.mhd)");if(!p.isEmpty()){input=p;source.clear();prepare();}});
  connect(importButton,&QPushButton::clicked,this,[this]{QString path=QFileDialog::getOpenFileName(this,u("选择外部掩膜 / 概率图清单"),QFileInfo(input).absolutePath(),"Image manifest (*.json)");if(!path.isEmpty())startUtility("import-external",{"--input",input,"--manifest",path});});
  connect(dicomButton,&QPushButton::clicked,this,[this]{QString path=QFileDialog::getExistingDirectory(this,u("选择 DICOM 根目录（包含子目录）"),QFileInfo(input).absolutePath());if(!path.isEmpty())startUtility("dicom-series",{"--input",path});});
  connect(exportButton,&QPushButton::clicked,this,[this]{QString path=root+"/ui/exports/"+QDateTime::currentDateTime().toString("yyyyMMdd_HHmmss")+"_"+QUuid::createUuid().toString(QUuid::Id128).left(6);startUtility("export",{"--input",input,"--result",source,"--destination",path,"--minimum-candidate-volume",QString::number(minimumCandidateVolume->value(),'g',15)});});
  connect(compareButton,&QPushButton::clicked,this,[this]{startJob("comparison");});connect(comparisonResults,&QPushButton::clicked,this,[this]{showComparisons();});
  connect(&utilityProcess,&QProcess::readyReadStandardOutput,this,[this]{utilityBytes+=utilityProcess.readAllStandardOutput();});connect(&utilityProcess,&QProcess::readyReadStandardError,this,[this]{utilityError+=QString::fromUtf8(utilityProcess.readAllStandardError());});connect(&utilityProcess,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),this,[this](int code,QProcess::ExitStatus status){finishUtility(code,status);});
  connect(refreshButton,&QPushButton::clicked,this,[this]{prepare(results->currentData().toString());});connect(results,QOverload<int>::of(&QComboBox::activated),this,[this](int){prepare(results->currentData().toString());});
  connect(runButton,&QPushButton::clicked,this,[this]{startJob("all");});connect(rebuildButton,&QPushButton::clicked,this,[this]{startJob("reconstruction");});connect(navButton,&QPushButton::clicked,this,[this]{startJob("navigation");});connect(stopButton,&QPushButton::clicked,this,[this]{stopAfterStage();});
  for(auto*p:{&prepareProcess,&jobProcess,&utilityProcess}){p->setWorkingDirectory(root);auto env=QProcessEnvironment::systemEnvironment();env.remove("LD_PRELOAD");env.remove("QT_QPA_PLATFORM");env.insert("PYTHONUNBUFFERED","1");env.insert("PYTHONIOENCODING","utf-8");p->setProcessEnvironment(env);connect(p,&QProcess::readyReadStandardError,this,[this,p]{errors+=QString::fromUtf8(p->readAllStandardError());});connect(p,&QProcess::errorOccurred,this,[this,p](QProcess::ProcessError e){if(e==QProcess::FailedToStart){failed=true;message(p->errorString());busy(false);if(smoke)finishTest();}});}
  connect(&prepareProcess,&QProcess::readyReadStandardOutput,this,[this]{processLines(prepPending,prepareProcess.readAllStandardOutput());});connect(&jobProcess,&QProcess::readyReadStandardOutput,this,[this]{processLines(jobPending,jobProcess.readAllStandardOutput());});
  connect(&prepareProcess,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),this,[this](int rc,QProcess::ExitStatus){prepareSceneInBackground(rc);});
  connect(&jobProcess,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),this,[this](int rc,QProcess::ExitStatus){if(activeSurfaceJob){surfaceJobFinished(rc);return;}stopButton->setEnabled(false);if(rc){failed=true;progress->setRange(0,100);progress->setValue(0);message(u("任务失败，保留日志：")+runOutput+"\n"+errors.right(1000));busy(false);if(smoke)finishTest();}else if(!runOutput.isEmpty()){record("job_finished");prepare(runOutput);}else busy(false);if(!stopFile.isEmpty())QFile::remove(stopFile);});
  connect(&segmentationPoll,&QTimer::timeout,this,[this]{pollSegmentationStatus();});segmentationPoll.start(500);
  beatClock.start();taskClock.start();qint64 last=0;connect(&heartbeat,&QTimer::timeout,this,[this,last]()mutable{lastTick=monoMs();shellTick();qint64 now=beatClock.elapsed();gaps.append(now-last);if(now-last>200)actions.append(QJsonObject{{"action","heartbeat_stall"},{"gap_ms",double(now-last)},{"elapsed_ms",double(now)},{"dfx_active",jobProcess.state()!=QProcess::NotRunning}});last=now;++ticks;clock->setText(QTime::currentTime().toString("HH:mm:ss"));if(jobProcess.state()!=QProcess::NotRunning){jobGaps.append(gaps.last());elapsed->setText(u("后台运行：")+QString::number(taskClock.elapsed()/1000)+u(" 秒"));if(smoke&&ticks%8==0){tabs->setCurrentIndex((ticks/8)%3);axialSlider->setValue((axialSlider->value()+1)%(axialSlider->maximum()+1));overview->turn(2);record("interaction_during_dfx");}}if(exitRequested&&(videoPending||videoRunning))videoCancel();if(exitRequested&&!processing())this->close();});heartbeat.start(50);
  setStyleSheet(redesignStyleSheet());
  plScope=new PlScope(root,this);plScope->setQuality(navQuality);plScope->onFrame=[this](QImage frame,QImage normals,QJsonObject meta){videoFrameReceived(frame,normals,meta);++plFrames;plLastFrame=meta;exposureFrameArrived();scope->setPlFrame(frame,normals,meta);shellPlFrame(meta["round_trip_ms"].toDouble());scopePerf->setText(QString("%1 · %2 × %3 · %4 ms").arg(meta["interactive"].toBool()?u("交互画面"):u("精细画面")).arg(meta["width"].toInt()).arg(meta["height"].toInt()).arg(meta["round_trip_ms"].toDouble(),0,'f',0));if(navigationTrace.size()>=400)navigationTrace.removeFirst();auto trace=meta;trace["ui_received_ms"]=double(beatClock.elapsed());navigationTrace.append(trace);};plScope->onStatus=[this](QString text){scope->setScopeStatus(text);};scope->onPoseChanged=[this]{syncNavigationControlsFromCamera();if(plScope->active()&&!processing())plScope->request(scope->cameraRequest());};
  scope->onPlPresented=[this](int){++plPresentedCount;exposureFramePresented();syncLinkedOverview();videoPresented();if(navigationBenchmarking&&navigationMotionClock.elapsed()>1000)navigationPresented.append(navigationMotionClock.elapsed());};
  connect(&compositeCheck,&QTimer::timeout,this,[this]{compositeAdvance();});
  plComposite=new PlComposite(root,this);
  plComposite->onFrame=[this](QImage frame,QJsonObject meta){
   
   if(!overview->compositeMode())return;
   if(!compositeAttributeFrameMatches(meta)){++rejectedCompositeAttributeFrames;return;}
   if(!transparentFrameMatches(meta,overview->overviewRequest())){++previewStaleFrames;return;}
   
   
   overview->setCompositePreview(false);if(!overview->setCompositeFrame(frame,meta)){failed=true;message(u("完成帧的相机矩阵无效，保留上一张画面"));return;}
   ++compositeFrames;if(compositeTesting){QDir().mkpath(evidence);QSaveFile raw(evidence+"/frame_"+QString::number(compositeFrames)+".rgba");if(!raw.open(QIODevice::WriteOnly)||raw.write(reinterpret_cast<const char*>(frame.constBits()),frame.sizeInBytes())!=frame.sizeInBytes()||!raw.commit())failed=true;}auto report=meta["report"].toObject();compositePerf->setText(QString(u("PL 合成 · %1 × %2 · 本帧 %3 秒")).arg(frame.width()).arg(frame.height()).arg(meta["round_trip_seconds"].toDouble(),0,'f',2));
   auto trace=meta;trace["ui_received_ms"]=double(beatClock.elapsed());trace["UI_frame_index"]=compositeFrames;if(compositeTrace.size()>=100)compositeTrace.removeFirst();compositeTrace.append(trace);
  };
  plComposite->onStatus=[this](QString text){if(overview->compositeMode()){overview->setCompositeStatus(text);compositePerf->setText(text);}};
  compositeQuiet.setSingleShot(true);compositeQuiet.setTimerType(Qt::PreciseTimer);
  connect(&compositeQuiet,&QTimer::timeout,this,[this]{if(closing||finishingTest||processing()||tabs->currentIndex()!=1||!overview->compositeMode())return;++previewQuietRequests;configureScope();});
  overview->onOverviewChanged=[this]{if(settingStructure||!overview->compositeMode()||processing()||tabs->currentIndex()!=1)return;overview->setCompositePreview(true);compositePerf->setText(u("交互预览 · 停止操作后生成精确透明画面"));compositeQuiet.start(450);};
  
  connect(overview,&QOpenGLWidget::frameSwapped,this,[this]{});
  connect(tabs,&QTabWidget::currentChanged,this,[this](int i){gamepadSuspend();if(i!=2){play.stop();playing=false;playButton->setText(u("沿路径播放"));scope->setPlayback(false);}configureScope();QTimer::singleShot(0,this,[this]{gamepadRefresh();});});
  buildShell(resetScope,fit,reset,mask);
  layoutReviewStart();demoCaptureStart();
  applySimplification();setupGamepad();
  busy(true);if(qEnvironmentVariableIntValue("KV260_UI_CONTROL_CHECK")!=1)QTimer::singleShot(150,this,[this]{prepare();});
 }
public:
~MainWindow(){shellShutdown();if(sceneLoader.joinable())sceneLoader.join();if(videoIntegrityThread.joinable())videoIntegrityThread.join();}
protected:
void changeEvent(QEvent*e)override{QWidget::changeEvent(e);if(e->type()==QEvent::ActivationChange){gamepadSuspend();QTimer::singleShot(0,this,[this]{gamepadRefresh();});}}
void closeEvent(QCloseEvent*e)override{gamepadSuspend();if(videoPending||videoRunning){videoCancel();e->ignore();return;}if(processing()){message(u("任务仍在运行。可停止后续步骤，当前阶段完成后再退出。"));e->ignore();return;}play.stop();if((plScope&&plScope->active())||(plComposite&&plComposite->active())){e->ignore();if(!closing){closing=true;releaseGraphics([this]{close();});}return;}e->accept();}
};

int main(int argc,char**argv){
 QSurfaceFormat f;f.setRenderableType(QSurfaceFormat::OpenGLES);f.setVersion(2,0);f.setDepthBufferSize(24);f.setStencilBufferSize(8);f.setSwapInterval(1);QSurfaceFormat::setDefaultFormat(f);
 QApplication::setAttribute(Qt::AA_ShareOpenGLContexts);QApplication app(argc,argv);app.setFont(QFont("Noto Sans CJK SC",10));
 QCommandLineParser p;p.addHelpOption();p.addOptions({{"simplification-check","Check production controls without starting PL"},{"root","Integrated project root","path"},{"input","Raw CT file","path"},{"result","Completed result to open initially","path"},{"smoke","Run actual UI smoke test"},{"acceptance-run","Run a real DFX case while interacting with the UI"},{"navigation-test","Measure navigation updates, auto alignment and quiet-frame refinement"},{"feature-test","Validate catalogue, focus, surface modes and clipping"},{"evidence","Test output directory","path"},{"navigation-quality","Navigation viewport: 0 clear, 1 balanced, 2 fast","level","1"}});p.process(app);if(p.isSet("simplification-check"))qputenv("KV260_UI_CONTROL_CHECK","1");
 QString root=p.value("root");if(root.isEmpty())root=QDir(QCoreApplication::applicationDirPath()+"/../..").absolutePath();QString input=p.value("input");if(input.isEmpty())input=root+"/fixtures/own_ct/CT-chest.nrrd";QString evidence=p.value("evidence");if(evidence.isEmpty())evidence=root+"/ui/docs/smoke";
 if(p.isSet("result"))qputenv("KV260_INITIAL_RESULT",p.value("result").toUtf8());
 signal(SIGTERM,handleSignal);signal(SIGINT,handleSignal);
 bool qualityOk=false;int navQuality=p.value("navigation-quality").toInt(&qualityOk);if(!qualityOk||navQuality<0||navQuality>2){qCritical()<<"Invalid navigation quality";return 2;}
 try{MainWindow window(root,input,p.isSet("smoke")||p.isSet("acceptance-run")||p.isSet("navigation-test")||p.isSet("feature-test"),p.isSet("acceptance-run"),p.isSet("navigation-test"),evidence,navQuality,p.isSet("feature-test"));if(p.isSet("simplification-check")){auto report=window.simplificationCheck();QDir().mkpath(evidence);writeJson(evidence+"/simplification.json",report);window.finishControlCheck();return report["passed"].toBool()?0:1;}window.show();return app.exec();}catch(const std::exception&e){qCritical()<<e.what();return 1;}
}
