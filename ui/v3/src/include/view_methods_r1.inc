QMatrix4x4 MeshView::displayModel(unsigned)const{return {};}
QVector3D MeshView::displayPoint(QVector3D point,unsigned slot)const{return displayModel(slot)*point;}
