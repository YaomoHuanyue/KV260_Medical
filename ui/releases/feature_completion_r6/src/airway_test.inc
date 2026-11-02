void airwayComparisonTest(){
 tabs->setCurrentIndex(0);QJsonArray checks;bool passed=true;
 auto check=[&](QString name,bool ok){checks.append(QJsonObject{{"name",name},{"passed",ok}});passed=passed&&ok;};
 auto options=scene["airway_masks"].toObject();check("raw_and_candidate_available",options.contains("network")&&options.contains("detail"));
 qint64 samples[3]={-1,-1,-1};qint64 n=qint64(volume->dims[0])*volume->dims[1]*volume->dims[2];
 for(qint64 k=0;volume->masks&&k<n;++k){uchar b=volume->masks[k];if(b&4)continue;if((b&2)&&samples[0]<0)samples[0]=k;if((b&8)&&!(b&2)&&!(b&16)&&samples[1]<0)samples[1]=k;if((b&16)&&!(b&2)&&samples[2]<0)samples[2]=k;if(samples[0]>=0&&samples[1]>=0&&samples[2]>=0)break;}
 for(int t=0;t<3;++t){check(QString("real_CT_sample_%1_found").arg(t),samples[t]>=0);if(samples[t]<0)continue;auto k=samples[t];int x=k%volume->dims[0],y=(k/volume->dims[0])%volume->dims[1],z=k/(qint64(volume->dims[0])*volume->dims[1]);axialSlider->setValue(z);
  for(int i=0;i<3;++i){airwayOverlay->setCurrentIndex(i);auto c=slices[0]->sliceImage().pixelColor(x,y);bool green=c.green()>c.red()+15&&c.green()>c.blue();bool expected=volume->masks[k]&airwayOverlay->itemData(i).toInt();check(QString("sample_%1_choice_%2_matches_selected_mask").arg(t).arg(i),green==expected&&slices[0]->airwayMaskBit()==airwayOverlay->itemData(i).toInt());}
 }
 if(samples[2]>=0){int z=samples[2]/(qint64(volume->dims[0])*volume->dims[1]);axialSlider->setValue(z);for(int i=0;i<3;++i){airwayOverlay->setCurrentIndex(i);QApplication::processEvents();capture(QString("airway_mask_%1").arg(i));}}
 airwayOverlay->setCurrentIndex(0);check("clean_restored_as_default",slices[0]->airwayMaskBit()==2);check("invalid_selection_rejected",!slices[0]->setAirwayMask(256)&&slices[0]->airwayMaskBit()==2);
 check("formal_navigation_unchanged",scene["navigation"].toObject()["report"].toObject()["centerline_input_sha256"].toString()==readJson(QDir(source).filePath("navigation/centerline.json"))["input_sha256"].toString());
 QJsonObject report{{"status",passed?"passed":"failed"},{"kind","actual_KV260_Qt_slice_mask_comparison"},{"checks",checks},{"scene",scenePath},{"audit",scene["airway_detail"]},{"physical_mouse_verified",false}};writeJson(evidence+"/airway_ui_acceptance.json",report);QApplication::exit(passed?0:1);
}
