import QtQuick 2.15
import "."
// 分段按钮
Rectangle {
    id: root
    property var model: []
    property int current: 0
    property bool onGlass: false
    property bool stretch: false
    property bool enabledState: true
    signal picked(int index)
    implicitHeight: 28
    implicitWidth: row.implicitWidth + 4
    radius: Theme.radius
    color: onGlass ? "transparent" : Theme.sunken
    opacity: enabledState ? 1 : 0.45
    Row {
        id: row
        anchors.fill: parent; anchors.margins: 2
        spacing: 2
        Repeater {
            model: root.model
            Rectangle {
                width: root.stretch ? (row.width - (root.model.length - 1) * 2) / root.model.length : label.implicitWidth + 22
                height: row.height
                radius: Theme.radius - 1
                color: index === root.current ? Theme.accentSoft : (cell.containsMouse ? (root.onGlass ? "#14FFFFFF" : Theme.hover) : "transparent")
                Behavior on color { ColorAnimation { duration: Theme.quick } }
                Text { id: label; anchors.centerIn: parent; text: modelData; font.family: Theme.font; font.pixelSize: Theme.fSmall
                       font.bold: index === root.current
                       color: index === root.current ? (root.onGlass ? "#FFFFFF" : Theme.ink) : (root.onGlass ? Theme.glassInk2 : Theme.ink2) }
                MouseArea { id: cell; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: if(root.enabledState) root.picked(index) }
            }
        }
    }
}
