import QtQuick 2.15
import "."
// 滑条：拖动时连续发出 moved；marks 为 0..1 的刻度位置（如分岔点），target 为终点标记
Item {
    id: root
    property real value: 0
    property real from: 0
    property real to: 100
    property bool enabledState: true
    property var marks: []
    property bool targetMark: false
    property bool onGlass: false
    signal moved(real value)
    implicitHeight: 22
    opacity: enabledState ? 1 : 0.4
    readonly property real frac: to > from ? Math.max(0, Math.min(1, (value - from) / (to - from))) : 0
    Rectangle {
        id: track
        anchors.verticalCenter: parent.verticalCenter
        x: 7; width: parent.width - 14; height: 4; radius: 2
        color: root.onGlass ? "#40FFFFFF" : Theme.line
        Rectangle { width: parent.width * root.frac; height: parent.height; radius: 2; color: Theme.accent }
        Repeater {
            model: root.marks
            Rectangle { x: track.width * modelData - 1; y: -5; width: 2; height: 14; radius: 1; color: root.onGlass ? "#99FFFFFF" : Theme.ink3 }
        }
        Rectangle { visible: root.targetMark; x: track.width - 6; y: -4; width: 12; height: 12; radius: 6; color: "transparent"; border.color: Theme.lesion; border.width: 2 }
    }
    Rectangle {
        x: track.x + track.width * root.frac - width / 2
        anchors.verticalCenter: parent.verticalCenter
        width: drag.pressed ? 15 : 13; height: width; radius: width / 2
        color: "#FFFFFF"
        border.width: 3; border.color: "#594DA3FF"
    }
    MouseArea {
        id: drag
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        function emitAt(mx) { if(!root.enabledState) return; var f = Math.max(0, Math.min(1, (mx - track.x) / track.width)); root.moved(root.from + f * (root.to - root.from)) }
        onPressed: emitAt(mouse.x)
        onPositionChanged: if(pressed) emitAt(mouse.x)
    }
}
