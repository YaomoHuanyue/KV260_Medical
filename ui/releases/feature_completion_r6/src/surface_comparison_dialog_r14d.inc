 void showSurfaceComparisons(){
  auto nav=scene["navigation"].toObject();auto whole=nav["whole_instrument_profiles"].toObject();auto alternatives=nav["whole_alternative_routes"].toObject();
  QDialog dialog(this);dialog.setWindowTitle(u("器械可达性与备选路径"));dialog.resize(qMin(1080,width()-24),qMin(660,height()-24));auto*layout=new QVBoxLayout(&dialog);
  auto*hint=new QLabel(whole.isEmpty()?u("该结果尚无全气道比较，请点击“比较器械与接近路径”生成。"):u("当前 C1 表面的完整原始骨架比较；净空包含连续管壁、裁剪与图像保守余量。采用时再次审核完整曲线。"));hint->setWordWrap(true);layout->addWidget(hint);
  auto*pages=new QTabWidget;layout->addWidget(pages,1);
  auto number=[](QJsonValue value,int decimals=1){return value.isDouble()?QString::number(value.toDouble(),'f',decimals):QString::fromUtf8("—");};
  auto makeTable=[](QJsonArray rows,QStringList headers,QWidget*parent){auto*t=new QTableWidget(rows.size(),headers.size(),parent);t->setHorizontalHeaderLabels(headers);t->setEditTriggers(QAbstractItemView::NoEditTriggers);t->setSelectionBehavior(QAbstractItemView::SelectRows);t->setSelectionMode(QAbstractItemView::SingleSelection);t->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch);t->verticalHeader()->hide();return t;};
  auto*chartPage=new QWidget;auto*chartLayout=new QVBoxLayout(chartPage);auto profiles=whole["profiles"].toArray();
  auto*chart=new ReachabilityChart(profiles);chartLayout->addWidget(chart,1);
  auto*fullTable=makeTable(profiles,{u("直径 mm"),u("可达点数"),u("可达总长 mm"),u("距候选 mm"),u("最近点路径 mm")},chartPage);
  for(int i=0;i<profiles.size();++i){auto r=profiles[i].toObject();QStringList values={number(r["scope_diameter_mm"]),QString::number(r["reachable_skeleton_voxels"].toInt()),number(r["reachable_centerline_length_mm"]),number(r["closest_lesion_gap_mm"]),number(r["path_length_to_closest_point_mm"])};for(int k=0;k<values.size();++k)fullTable->setItem(i,k,new QTableWidgetItem(values[k]));}
  chartLayout->addWidget(fullTable);pages->addTab(chartPage,u("全气道统计"));
  auto*pathPage=new QWidget;auto*pathLayout=new QVBoxLayout(pathPage);auto*diameters=new QComboBox;auto groups=alternatives["groups"].toArray();int initial=0;
  for(int i=0;i<groups.size();++i){double d=groups[i].toObject()["scope_diameter_mm"].toDouble();diameters->addItem(QString(u("器械 Ø %1 mm")).arg(d,0,'f',1),i);if(std::abs(d-diameter->value())<1e-9)initial=i;}
  pathLayout->addWidget(diameters);auto*choiceInfo=new QLabel;choiceInfo->setWordWrap(true);pathLayout->addWidget(choiceInfo);
  auto*split=new QSplitter;auto*routes=makeTable({}, {u("候选"),u("路径 mm"),u("间隙 mm"),u("转角 rad"),u("最窄直径 mm")},pathPage);split->addWidget(routes);
  auto*preview=new MeshView;preview->loadScene(scenePath,scene);preview->selectCandidate(lesion->value());preview->setLayer(1,true);preview->setLayer(2,true);preview->setRoute(true);preview->setMinimumSize(320,200);split->addWidget(preview);split->setSizes({540,450});pathLayout->addWidget(split,1);
  auto*pathNotice=new QLabel(u("黄色线是原规则的备选路径。点击审核后，实际导航仅使用满足图像净空与弯曲约束的前缀；结果另存，不修改原病例。"));pathNotice->setWordWrap(true);pathLayout->addWidget(pathNotice);pages->addTab(pathPage,u("Pareto 备选路径"));
  auto*apply=new QPushButton(u("审核并用于导航"));apply->setObjectName("applySelectedPath");apply->setEnabled(!groups.isEmpty()&&!processing());pathLayout->addWidget(apply);
  QJsonArray activeCandidates,activeFront;
  auto selected=[&]{int row=routes->currentRow();if(row<0||row>=activeFront.size())return;int id=activeFront[row].toObject()["candidate_id"].toInt(-1);QJsonObject candidate;for(auto v:activeCandidates)if(v.toObject()["candidate_id"].toInt(-2)==id){candidate=v.toObject();break;}if(candidate.isEmpty())return;
   preview->setPreviewRoute(candidate["points_lps_mm"].toArray());apply->setEnabled(candidate["points_lps_mm"].toArray().size()>1&&!processing());dialog.setProperty("preview_candidate_id",id);dialog.setProperty("preview_endpoint",candidate["endpoint_xyz_mm"].toArray());
   bool originalEligible=candidate["original_diameter_bend_eligible"].toBool();QString text=QString(u("候选 #%1 · 路径 %2 mm · 距候选区域 %3 mm · 最窄直径 %4 mm\n%5；已包含当前表面的净空审核，采用时继续复核所选曲线及弯曲约束。")).arg(id).arg(candidate["path_length_mm"].toDouble(),0,'f',1).arg(candidate["gap_mm"].toDouble(),0,'f',1).arg(candidate["minimum_diameter_mm"].toDouble(),0,'f',2).arg(originalEligible?u("通过原规则的管径/弯曲筛选"):u("未通过原规则的管径/弯曲筛选"));choiceInfo->setText(text);
  };
  connect(routes,&QTableWidget::currentCellChanged,&dialog,[&](int,int,int,int){selected();});
  auto populate=[&]{int group=diameters->currentData().toInt();if(group<0||group>=groups.size())return;auto value=groups[group].toObject();activeCandidates=value["candidates"].toArray();activeFront=value["pareto"].toArray();QSignalBlocker block(routes);routes->clearContents();routes->setRowCount(activeFront.size());
   for(int i=0;i<activeFront.size();++i){auto r=activeFront[i].toObject();int id=r["candidate_id"].toInt();QString suffix=id==value["selected_candidate_id"].toInt()?u(" · 推荐"):QString();QStringList values={QString::number(id)+suffix,number(r["route_length_mm"]),number(r["airway_to_lesion_gap_mm"]),number(r["route_turn_cost_radians"],2),number(r["minimum_route_diameter_mm"],2)};for(int k=0;k<values.size();++k)routes->setItem(i,k,new QTableWidgetItem(values[k]));}
   if(!activeFront.isEmpty())routes->setCurrentCell(0,0);selected();
  };
  connect(diameters,QOverload<int>::of(&QComboBox::currentIndexChanged),&dialog,[&](int){populate();});diameters->setCurrentIndex(initial);populate();
  int requestedGroup=-1,requestedCandidate=-1;connect(apply,&QPushButton::clicked,&dialog,[&]{int row=routes->currentRow();if(row<0||row>=activeFront.size())return;requestedGroup=diameters->currentData().toInt();requestedCandidate=activeFront[row].toObject()["candidate_id"].toInt(-1);dialog.accept();});
  auto*close=new QPushButton(u("关闭"));layout->addWidget(close);connect(close,&QPushButton::clicked,&dialog,&QDialog::accept);
  if(activeSurfaceTesting&&surfaceTestStage==2)QTimer::singleShot(500,&dialog,[&]{
   surfaceCheck("preview_highlights_current_target",preview->featureMetrics()["selected_candidate"].toInt(-1)==surfaceTarget);
   surfaceCheck("five_current_surface_profiles",profiles.size()==5&&fullTable->rowCount()==5);
   surfaceCheck("complete_raw_cycles_preserved",whole["raw_nodes"].toInt()==863&&whole["raw_undirected_edges"].toInt()==871&&whole["cycles_preserved_before_explicit_geometry_filter"].toBool());
   surfaceCheck("no_old_PL_audit_tab",pages->count()==2);QDir().mkpath(evidence);dialog.grab().save(evidence+"/active_profile_chart.png");pages->setCurrentIndex(1);
   int visited=0;
   for(int i=0;i<groups.size();++i){diameters->setCurrentIndex(i);QTest::qWait(40);
    surfaceCheck(QString("current_Pareto_rows_%1").arg(i),routes->rowCount()==groups[i].toObject()["pareto"].toArray().size());
    for(int j=0;j<routes->rowCount();++j){routes->setCurrentCell(j,0);QTest::qWait(25);int id=activeFront[j].toObject()["candidate_id"].toInt();QJsonObject expected;
     for(auto v:activeCandidates)if(v.toObject()["candidate_id"].toInt()==id)expected=v.toObject();
     auto actual=preview->previewRouteMetrics();surfaceCheck(QString("complete_preview_%1_%2").arg(i).arg(j),actual["point_count"].toInt()==expected["points_lps_mm"].toArray().size());++visited;
    }
   }
   surfaceCheck("all_Pareto_paths_previewed",visited>8);diameters->setCurrentIndex(2);int choice=0;double length=-1;
   for(int j=0;j<activeFront.size();++j){double value=activeFront[j].toObject()["route_length_mm"].toDouble();if(value>length){length=value;choice=j;}}
   routes->setCurrentCell(choice,0);QTest::qWait(100);dialog.grab().save(evidence+"/active_Pareto_preview.png");surfaceTickBase=ticks;
   surfaceCheck("actual_apply_button_enabled",apply->isEnabled());if(failed)dialog.reject();else apply->click();
  });
  dialog.exec();
  if(requestedGroup>=0&&requestedCandidate>=0)QTimer::singleShot(0,this,[this,requestedGroup,requestedCandidate]{startSelectedPath(requestedGroup,requestedCandidate);});
 }
