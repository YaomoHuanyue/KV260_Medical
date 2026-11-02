import QtQuick 2.15
import "."
// 开关（替代复选框）
Item {
    id: root
    property bool on: false
    property bool enabledState: true
    property string tip: ""
    signal toggled(bool value)
    width: 30; height: 18
    opacity: enabledState ? 1 : 0.4
    Rectangle {
        anchors.fill: parent; radius: height / 2
        color: root.on ? Theme.accent : Theme.line
        Behavior on color { ColorAnimation { duration: Theme.quick } }
        Rectangle {
            width: 14; height: 14; radius: 7; y: 2
            x: root.on ? parent.width - width - 2 : 2
            color: root.on ? "#FFFFFF" : Theme.ink3
            Behavior on x { NumberAnimation { duration: Theme.quick; easing.type: Easing.OutCubic } }
        }
    }
    MouseArea { id: area; anchors.fill: parent; anchors.margins: -6; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: if(root.enabledState) root.toggled(!root.on) }
    Tip { visible: area.containsMouse && root.tip !== ""; text: root.tip }
}
