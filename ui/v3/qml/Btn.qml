import QtQuick 2.15
import "."
// 文字按钮：primary（主操作）/ ghost（次要）/ danger（停止）/ plain（列表式）
Rectangle {
    id: root
    property string text: ""
    property string icon: ""
    property string kind: "ghost"
    property string tip: ""
    property bool enabledState: true
    property bool wide: false
    signal clicked()
    implicitWidth: row.implicitWidth + 28
    implicitHeight: 32
    width: wide && parent ? parent.width : implicitWidth
    height: implicitHeight
    radius: Theme.radius
    opacity: enabledState ? 1 : 0.45
    color: kind === "primary" ? (area.containsMouse && enabledState ? Qt.lighter(Theme.accent, 1.08) : Theme.accent)
         : kind === "plain" ? (area.containsMouse && enabledState ? Theme.hover : "transparent")
         : (area.containsMouse && enabledState ? Theme.hover : "transparent")
    border.width: kind === "ghost" || kind === "danger" ? 1 : 0
    border.color: kind === "danger" ? "#73F0616D" : Theme.line
    Behavior on color { ColorAnimation { duration: Theme.quick } }
    Row {
        id: row
        anchors.verticalCenter: parent.verticalCenter
        x: root.kind === "plain" ? 10 : (root.width - width) / 2
        spacing: 7
        Icon { visible: root.icon !== ""; name: root.icon; size: 16; anchors.verticalCenter: parent.verticalCenter
               color: root.kind === "primary" ? Theme.accentInk : root.kind === "danger" ? "#FFB3B9" : Theme.ink2 }
        Text { text: root.text; anchors.verticalCenter: parent.verticalCenter; font.family: Theme.font; font.pixelSize: Theme.fBody
               font.bold: root.kind === "primary"
               color: root.kind === "primary" ? Theme.accentInk : root.kind === "danger" ? "#FFB3B9" : Theme.ink }
    }
    MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: if(root.enabledState) root.clicked() }
    Tip { visible: area.containsMouse && root.tip !== ""; text: root.tip }
}
