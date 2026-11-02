import QtQuick 2.15
import "."
// 图标栏条目：点开对应抽屉，再点收起
Rectangle {
    id: item
    property string key: ""
    property string icon: ""
    property string label: ""
    property string tip: ""
    readonly property bool on: ui.s.drawer === key
    width: 46; height: 50; radius: 8
    anchors.horizontalCenter: parent ? parent.horizontalCenter : undefined
    color: on ? Theme.raised : (area.containsMouse ? Theme.hover : "transparent")
    Behavior on color { ColorAnimation { duration: Theme.quick } }
    Column {
        anchors.centerIn: parent; spacing: 3
        Icon { name: item.icon; size: 19; color: item.on ? Theme.ink : Theme.ink2; anchors.horizontalCenter: parent.horizontalCenter }
        Text { text: item.label; font.family: Theme.font; font.pixelSize: 11; color: item.on ? Theme.ink : Theme.ink2; anchors.horizontalCenter: parent.horizontalCenter }
    }
    MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: ui.action("drawer", item.on ? "" : item.key) }
    Tip { visible: area.containsMouse; text: item.tip }
}
