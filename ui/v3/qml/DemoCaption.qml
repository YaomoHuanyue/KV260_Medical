import QtQuick 2.15
import "."
// 演示字幕：底部字幕条；有 title 时显示为居中的片头 / 结尾卡片
Rectangle {
    id: root
    readonly property var d: ui.s.demo ? ui.s.demo : ({ active: false, step: 0, total: 6, text: "", title: "", subtitle: "", process: false })
    readonly property bool card: (d.title || "") !== ""
    color: card ? "#F00B0D10" : "#E60B0D10"; radius: card ? 16 : 12; border.color: card ? "#4D4FB6FF" : "#33FFFFFF"

    // 片头 / 结尾卡片
    Column {
        visible: root.card; anchors.centerIn: parent; spacing: 14; width: parent.width - 64
        Rectangle { width: 56; height: 4; radius: 2; color: Theme.accent; anchors.horizontalCenter: parent.horizontalCenter }
        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: root.d.title || ""; wrapMode: Text.WordWrap
               font.family: Theme.font; font.pixelSize: 30; font.bold: true; color: "#FFFFFF" }
        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: root.d.subtitle || ""; wrapMode: Text.WordWrap
               font.family: Theme.font; font.pixelSize: 16; color: "#C9D1DA" }
    }

    // 底部字幕条
    Row {
        visible: !root.card
        anchors.verticalCenter: parent.verticalCenter; x: 14; spacing: 12
        Rectangle { width: stepText.implicitWidth + 16; height: 24; radius: 12; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter
            Text { id: stepText; anchors.centerIn: parent; text: (root.d.process ? "处理 " : "演示 ") + root.d.step + " / " + root.d.total
                   font.family: Theme.font; font.pixelSize: Theme.fSmall; font.bold: true; color: Theme.accentInk } }
        Text { width: root.width - stepText.implicitWidth - 150; text: root.d.text || ""; elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter
               font.family: Theme.font; font.pixelSize: 15; color: "#FFFFFF" }
    }
    Text { visible: !root.card; anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
           text: "任意键退出"; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: "#9BA3AD" }
    onDChanged: if(d.active) { pulse.restart() }
    SequentialAnimation { id: pulse; NumberAnimation { target: root; property: "opacity"; from: 0.3; to: 1; duration: 260 } }
}
