 void catalogueTest(){
  QJsonArray checks;auto check=[&](QString name,bool value){checks.append(QJsonObject{{"name",name},{"passed",value}});};
  QJsonArray original=scene["candidates"].toArray();QString originalScene=scenePath,originalSource=source;
  check("ready_complete_own_CT",!failed&&!processing()&&original.size()==9&&lesionList->count()==9);
  QTest::mouseClick(lesionList,Qt::LeftButton);QTest::qWait(60);
  auto*popup=lesionList->view();auto last=lesionList->model()->index(original.size()-1,0);
  popup->scrollTo(last,QAbstractItemView::PositionAtBottom);QTest::qWait(60);
  auto rectangle=popup->visualRect(last);
  check("visible_last_item_popup_clicked",popup->isVisible()&&popup->viewport()->rect().contains(rectangle.center()));
  QTest::mouseClick(popup->viewport(),Qt::LeftButton,Qt::NoModifier,rectangle.center());
  int chosen=lesionList->currentData().toInt();check("selected_original_last_id",chosen==original.last().toObject()["index"].toInt()&&lesion->value()==chosen);
  auto typeThreshold=[&](QString value){minimumCandidateVolume->setFocus();
   QTest::keyClick(minimumCandidateVolume,Qt::Key_A,Qt::ControlModifier);
   QTest::keyClicks(minimumCandidateVolume,value);QTest::keyClick(minimumCandidateVolume,Qt::Key_Return);};
  typeThreshold("0");check("retained_selection_unchanged",lesion->value()==chosen&&lesionList->count()==original.size());
  typeThreshold("1000000000");check("empty_filter_blocks_target_operations",
   lesionList->count()==0&&lesion->value()==-1&&!navButton->isEnabled()&&!focusButton->isEnabled()&&!compareButton->isEnabled());
  check("empty_filter_informs_user",candidateInfo->text().contains(u("体积筛选无候选")));
  typeThreshold("0");bool ids=lesionList->count()==original.size();
  for(int i=0;i<lesionList->count();++i)ids=ids&&lesionList->itemData(i).toInt()==original[i].toObject()["index"].toInt();
  check("restored_original_indices_and_navigation",ids&&navButton->isEnabled()&&focusButton->isEnabled()&&lesion->value()==0);
  typeThreshold("14");check("default_threshold_restored",minimumCandidateVolume->value()==14&&lesionList->count()==9);
  check("cached_scene_and_result_unchanged",scenePath==originalScene&&source==originalSource&&scene["candidates"].toArray()==original);
  bool passed=true;for(auto c:checks)passed=passed&&c.toObject()["passed"].toBool();
  QDir().mkpath(evidence);writeJson(evidence+"/catalogue_UI.json",QJsonObject{
   {"status",passed?"passed_actual_Qt_candidate_filter_identity_and_empty_recovery":"failed"},
   {"checks",checks},{"original_candidates",original},{"input_sha256",scene["input_sha256"]},
   {"source",source},{"UI_peak_RSS_MiB",peakRSS()},{"keyboard_control_events_exercised",true},
   {"physical_mouse_verified",false},{"production_UI_replaced",false},
   {"PL_catalogue_kernel_implemented",false}});
  grab().save(evidence+"/catalogue_complete.png");
  close();if(!passed)QTimer::singleShot(100,[]{QApplication::exit(1);});
 }
