import QtQuick 2.15
import "."
Rectangle {
    id: root
    color: Theme.panel
    function s(k) { var v = ui.s[k]; return v ? v : ({}) }
    readonly property int page: ui.s.page !== undefined ? ui.s.page : 0
    readonly property var pipe: ui.s.pipeline ? ui.s.pipeline : ({ stages: [], running: false, label: "" })
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line }

    Row {
        id: brand
        x: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 9
        Brand { anchors.verticalCenter: parent.verticalCenter }
        Text { text: "支气管导航工作站"; font.family: Theme.font; font.pixelSize: Theme.fTitle; font.bold: true; color: Theme.ink; anchors.verticalCenter: parent.verticalCenter }
    }

    // 模式切换：下划线式
    Row {
        id: modes
        anchors.left: brand.right; anchors.leftMargin: 26; height: parent.height
        Repeater {
            id: modeRepeater
            model: [{ t: "影像", i: "image", k: "Ctrl+1" }, { t: "三维", i: "cube", k: "Ctrl+2" }, { t: "导航", i: "route", k: "Ctrl+3" }]
            Item {
                width: modeRow.implicitWidth + 28; height: modes.height
                Row {
                    id: modeRow; anchors.centerIn: parent; spacing: 7
                    Icon { name: modelData.i; size: 16; color: index === root.page ? Theme.ink : Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: modelData.t; font.family: Theme.font; font.pixelSize: Theme.fBody; font.bold: index === root.page; color: index === root.page ? Theme.ink : Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                }
                MouseArea { id: modeArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: ui.action("page", index) }
                Tip { visible: modeArea.containsMouse; text: modelData.t + "（" + modelData.k + "）" }
            }
        }
    }
    Rectangle {
        // 当前模式下划线，切换时滑动
        height: 2; radius: 1; color: Theme.accent; y: parent.height - 2
        property Item cur: modeRepeater.count > root.page ? modeRepeater.itemAt(root.page) : null
        x: cur ? modes.x + cur.x + 12 : 0
        width: cur ? cur.width - 24 : 0
        Behavior on x { NumberAnimation { duration: Theme.slide; easing.type: Easing.OutCubic } }
        Behavior on width { NumberAnimation { duration: Theme.slide; easing.type: Easing.OutCubic } }
    }

    Row {
        anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
        spacing: 10
        // 流程胶囊：四个阶段，点开处理面板
        Rectangle {
            id: pill
            anchors.verticalCenter: parent.verticalCenter
            height: 30; radius: 15; width: pipeRow.implicitWidth + 24
            color: pillArea.containsMouse ? Qt.lighter(Theme.raised, Theme.light ? 0.97 : 1.15) : Theme.raised
            border.width: root.pipe.running ? 1 : 0; border.color: "#804DA3FF"
            Row {
                id: pipeRow; anchors.centerIn: parent; spacing: 10
                Repeater {
                    model: root.pipe.stages
                    Row {
                        spacing: 5; anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            id: dot; width: 7; height: 7; radius: 4; anchors.verticalCenter: parent.verticalCenter
                            color: modelData.state === "done" ? Theme.ok : modelData.state === "run" ? Theme.accent : modelData.state === "fail" ? Theme.bad : Theme.ink3
                            SequentialAnimation on opacity { running: modelData.state === "run"; loops: Animation.Infinite; alwaysRunToEnd: true
                                NumberAnimation { to: 0.35; duration: 600 } NumberAnimation { to: 1; duration: 600 } }
                        }
                        Text { text: modelData.short; font.family: Theme.font; font.pixelSize: Theme.fSmall; anchors.verticalCenter: parent.verticalCenter
                               color: modelData.state === "run" ? Theme.ink : Theme.ink2; font.bold: modelData.state === "run" }
                    }
                }
                Rectangle { width: 1; height: 14; color: Theme.line; anchors.verticalCenter: parent.verticalCenter }
                Text { text: root.pipe.label; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3; anchors.verticalCenter: parent.verticalCenter }
            }
            MouseArea { id: pillArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: ui.action("drawer", "process") }
            Tip { visible: pillArea.containsMouse; text: "查看处理流程与 PL 动态区" }
        }
        Btn {
            anchors.verticalCenter: parent.verticalCenter
            visible: !root.pipe.running
            kind: "primary"; icon: "play"; text: "开始处理"
            enabledState: root.s("run").enabled === true
            tip: root.s("run").tip || ""
            onClicked: ui.click("run")
        }
        Btn {
            anchors.verticalCenter: parent.verticalCenter
            visible: root.pipe.running
            kind: "danger"; icon: "stop"; text: "停止后续步骤"
            enabledState: root.s("stop").enabled === true
            tip: root.s("stop").tip || ""
            onClicked: ui.click("stop")
        }
        IconButton { anchors.verticalCenter: parent.verticalCenter; icon: "more"; tip: "系统、外观与退出"; active: ui.s.drawer === "system"; onClicked: ui.action("drawer", "system") }
    }
}
