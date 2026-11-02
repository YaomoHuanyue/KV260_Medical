import QtQuick 2.15
import "."
// 播放条：圆形播放键、带分岔刻度和目标标记的进度条
Rectangle {
    id: root
    color: Theme.panel
    function s(k) { var v = ui.s[k]; return v ? v : ({}) }
    readonly property bool playing: (s("play").text || "").indexOf("暂停") >= 0 || (s("play").text || "").indexOf("停止") >= 0
    readonly property string pos: (s("navPos").text || "").replace("位置 ", "")
    Rectangle { width: parent.width; height: 1; color: Theme.line }
    Row {
        id: left
        x: 12; anchors.verticalCenter: parent.verticalCenter; spacing: 4
        IconButton { icon: "first"; tip: "起点（Home）"; enabledState: root.s("navStart").enabled !== false; onClicked: ui.click("navStart"); anchors.verticalCenter: parent.verticalCenter }
        IconButton { icon: "back"; tip: "后退一步（S / ←）"; enabledState: root.s("navBack").enabled !== false; onClicked: ui.click("navBack"); anchors.verticalCenter: parent.verticalCenter }
        Rectangle {
            width: 40; height: 40; radius: 20; anchors.verticalCenter: parent.verticalCenter
            color: playArea.containsMouse ? Qt.lighter(Theme.accent, 1.08) : Theme.accent
            opacity: root.s("play").enabled === false ? 0.45 : 1
            Icon { anchors.centerIn: parent; anchors.horizontalCenterOffset: root.playing ? 0 : 1; name: root.playing ? "pause" : "play"; size: 18; color: Theme.accentInk }
            MouseArea { id: playArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: ui.click("play") }
            Tip { visible: playArea.containsMouse; text: (root.playing ? "暂停" : "沿路径播放") + "（空格）" }
        }
        IconButton { icon: "forward"; tip: "前进一步（W / →）"; enabledState: root.s("navFwd").enabled !== false; onClicked: ui.click("navFwd"); anchors.verticalCenter: parent.verticalCenter }
        IconButton { icon: "last"; tip: "终点（End）"; enabledState: root.s("navEnd").enabled !== false; onClicked: ui.click("navEnd"); anchors.verticalCenter: parent.verticalCenter }
    }
    Row {
        id: right
        anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; spacing: 8
        Text { text: root.pos; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink; anchors.verticalCenter: parent.verticalCenter; width: 120; horizontalAlignment: Text.AlignRight }
        IconButton { icon: "center"; tip: "回正镜头（也可双击画面）"; onClicked: ui.click("resetScope"); anchors.verticalCenter: parent.verticalCenter }
    }
    Item {
        anchors.left: left.right; anchors.right: right.left; anchors.leftMargin: 14; anchors.rightMargin: 12
        height: parent.height
        Slide {
            id: bar
            width: parent.width; y: 14
            from: root.s("camera").min || 0; to: root.s("camera").max || 1; value: root.s("camera").value || 0
            enabledState: root.s("camera").enabled !== false
            marks: ui.s.navMarks ? ui.s.navMarks : []
            targetMark: (root.s("camera").max || 0) > 0
            onMoved: ui.setValue("camera", value)
        }
        Text { x: 0; y: 38; text: "气管"; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3 }
        Text { anchors.horizontalCenter: parent.horizontalCenter; y: 38; visible: (ui.s.navMarks || []).length > 0; text: "分岔 × " + (ui.s.navMarks || []).length; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3 }
        Text { anchors.right: parent.right; y: 38; text: "目标"; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3 }
    }
}
