import QtQuick 2.15
import "."
// 图标按钮：可选激活态；onGlass 用于浮在图像上的工具条
Rectangle {
    id: root
    property string icon: ""
    property string tip: ""
    property bool active: false
    property bool onGlass: false
    property int iconSize: 18
    property bool enabledState: true
    signal clicked()
    width: 32; height: 32; radius: Theme.radius
    color: active ? Theme.accentSoft : (area.containsMouse && enabledState ? (onGlass ? "#1AFFFFFF" : Theme.hover) : "transparent")
    opacity: enabledState ? 1 : 0.4
    Behavior on color { ColorAnimation { duration: Theme.quick } }
    Icon { anchors.centerIn: parent; name: root.icon; size: root.iconSize; color: root.active ? Theme.accent : (root.onGlass ? Theme.glassInk : Theme.ink2) }
    MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: if(root.enabledState) root.clicked() }
    Tip { visible: area.containsMouse && root.tip !== ""; text: root.tip }
}
