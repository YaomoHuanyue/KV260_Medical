 void dicomFinish(bool passed,QString detail){
  if(!dicomTesting)return;QDir().mkpath(evidence);
  writeJson(evidence+"/dicom_UI.json",QJsonObject{{"status",passed?"passed_recursive_DICOM_actual_UI_selection_import_and_empty_rejection":"failed"},{"detail",detail},{"trace",dicomTrace},{"selection",dicomImported},{"input",input},{"scene",scenePath},{"input_sha256",scene["input_sha256"]},{"geometry",scene["geometry"]},{"UI_peak_RSS_MiB",peakRSS()},{"physical_mouse_verified",false},{"new_medical_PL_core_loaded",false},{"accepted_UI_replaced",false}});
  grab().save(evidence+"/final.png");this->close();if(!passed)QTimer::singleShot(100,[]{QApplication::exit(1);});
 }
 void dicomAdvance(){
  if(!dicomTesting)return;
  if(failed){dicomFinish(false,u("CT 视图载入失败"));return;}
  if(dicomStep==0){dicomStep=1;dicomTrace.append("clicked_recursive_directory_import");QTest::mouseClick(dicomButton,Qt::LeftButton);return;}
  if(dicomStep==1){
   bool good=dicomImported["relative_directory"]=="nested/deep"&&dicomImported["file_count"].toInt()==5&&volume&&volume->dims[0]==32&&volume->dims[1]==40&&volume->dims[2]==5&&scene["meshes"].toObject().isEmpty()&&scene["masks"].isNull()&&scene["source"]=="raw_ct";
   if(!good){dicomFinish(false,u("所选子目录或导入 CT 几何不正确"));return;}
   dicomTrace.append("selected_nested_duplicate_UID_and_loaded_CT_slices");grab().save(evidence+"/imported.png");
   dicomExpectedInput=input;dicomExpectedScene=scenePath;dicomStep=2;
   startUtility("dicom-series",{"--input",qEnvironmentVariable("KV260_DICOM_EMPTY_ROOT")});
  }
 }
 void chooseDicomSeries(const QJsonObject&result){
  auto series=result["series"].toArray();
  if(series.isEmpty()){
   message(u("所选目录及子目录内没有可读取的 DICOM 序列"));configureScope();
   if(dicomTesting){bool good=dicomStep==2&&input==dicomExpectedInput&&scenePath==dicomExpectedScene;dicomTrace.append("empty_directory_preserved_completed_CT_view");dicomFinish(good,u("空目录未替换当前病例"));}return;
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
   if(dicomTesting){QTimer::singleShot(250,&dialog,[this,table,load,&dialog,series]{int found=-1;for(int i=0;i<series.size();++i)if(series[i].toObject()["relative_directory"]=="nested/deep")found=i;if(found<0){dialog.reject();return;}table->selectRow(found);QDir().mkpath(evidence);dialog.grab().save(evidence+"/series_selection.png");dicomTrace.append("clicked_directory_qualified_sequence_choice");QTest::mouseClick(load,Qt::LeftButton);});}
   if(dialog.exec()!=QDialog::Accepted){configureScope();if(dicomTesting)dicomFinish(false,u("测试目标序列未选中"));return;}index=table->currentRow();
  }
  if(index<0||index>=series.size()){message(u("请先选择一个序列"));configureScope();return;}
  auto selected=series[index].toObject();QString token=selected["selection_id"].toString();
  if(token.isEmpty()){message(u("序列选择标识无效，请重新扫描目录"));configureScope();return;}
  QStringList args={"--input",result["directory"].toString(),"--series-uid",token};
  if(dicomTesting)args<<"--case-root"<<qEnvironmentVariable("KV260_DICOM_CASE_ROOT");
  startUtility("import-dicom",args);
 }
