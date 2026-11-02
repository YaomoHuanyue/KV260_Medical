import QtQuick 2.15
import "."
// 浮在轴位图右上角：窗位 + 分割叠加
Rectangle {
    id: root
    function s(k) { var v = ui.s[k]; return v ? v : ({}) }
    color: Theme.glass; radius: 9; border.color: Theme.glassLine
    Row {
        anchors.centerIn: parent; spacing: 8
        Seg { onGlass: true; model: ["肺窗", "纵隔", "骨窗"]; current: root.s("window").index || 0; onPicked: ui.setIndex("window", index); anchors.verticalCenter: parent.verticalCenter }
        Rectangle { width: 1; height: 16; color: "#33FFFFFF"; anchors.verticalCenter: parent.verticalCenter }
        Toggle { on: root.s("mask").checked === true; onToggled: ui.setChecked("mask", value); anchors.verticalCenter: parent.verticalCenter; tip: "在三个切面上叠加肺与气道分割" }
        Text { text: "分割叠加"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.glassInk; anchors.verticalCenter: parent.verticalCenter
               MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: ui.setChecked("mask", !(root.s("mask").checked === true)) } }
    }
}
