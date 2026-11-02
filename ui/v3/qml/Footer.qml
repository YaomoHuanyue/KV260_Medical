import QtQuick 2.15
import "."
Rectangle {
    id: root
    color: Theme.panel
    function s(k) { var v = ui.s[k]; return v ? v : ({}) }
    readonly property bool busy: ui.s.busy === true
    Rectangle { width: parent.width; height: 1; color: Theme.line }
    Row {
        x: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 8
        width: parent.width - right.width - 40
        Rectangle { width: 7; height: 7; radius: 4; anchors.verticalCenter: parent.verticalCenter; color: root.busy ? Theme.accent : Theme.ok
            SequentialAnimation on opacity { running: root.busy; loops: Animation.Infinite; alwaysRunToEnd: true; NumberAnimation { to: 0.3; duration: 600 } NumberAnimation { to: 1; duration: 600 } } }
        Text {
            readonly property string msg: root.s("task").text || ""
            readonly property bool bad: msg.indexOf("失败") >= 0 || msg.indexOf("错误") >= 0
            text: msg; elide: Text.ElideRight; width: parent.width - 20; font.family: Theme.font; font.pixelSize: Theme.fCaption
            color: bad ? Theme.bad : Theme.ink2; anchors.verticalCenter: parent.verticalCenter
            MouseArea { anchors.fill: parent; enabled: parent.bad; cursorShape: Qt.PointingHandCursor; onClicked: ui.action("drawer", "system") }
        }
    }
    Row {
        id: right
        anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 12
        Text { visible: root.busy && (root.s("elapsed").text || "") !== ""; text: root.s("elapsed").text || ""; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3; anchors.verticalCenter: parent.verticalCenter }
        Rectangle {
            id: track
            visible: root.busy; width: 120; height: 3; radius: 2; color: Theme.line; anchors.verticalCenter: parent.verticalCenter; clip: true
            readonly property var p: root.s("progress")
            readonly property bool indeterminate: p.busy === true
            Rectangle {
                height: parent.height; radius: 2; color: Theme.accent
                width: track.indeterminate ? track.width * 0.3 : track.width * Math.max(0, Math.min(1, ((track.p.value || 0) - (track.p.min || 0)) / Math.max(1, (track.p.max || 100) - (track.p.min || 0))))
                x: 0
                SequentialAnimation on x { running: track.indeterminate && root.busy; loops: Animation.Infinite
                    NumberAnimation { from: -40; to: 120; duration: 1100; easing.type: Easing.InOutQuad } }
            }
        }
        Text { text: ui.s.disclaimer || "研究原型 · 非临床诊断"; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3; anchors.verticalCenter: parent.verticalCenter }
    }
}
