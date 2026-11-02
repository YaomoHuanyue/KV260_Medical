import QtQuick 2.15
import "."
// 分区标题：小号次文字，右侧可放附加内容
Item {
    id: root
    property string title: ""
    default property alias extra: right.data
    width: parent ? parent.width : 200
    height: 18
    Text { text: root.title; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink3; font.letterSpacing: 0.5; anchors.verticalCenter: parent.verticalCenter }
    Row { id: right; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 6 }
}
