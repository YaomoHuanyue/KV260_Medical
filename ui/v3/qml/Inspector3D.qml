import QtQuick 2.15
import "."
// 三维页右侧检查器：结构 → 着色 → 透明度 → 剖切 → 高质量透明 → 当前目标
Rectangle {
    id: root
    color: Theme.panel
    function s(k) { var v = ui.s[k]; return v ? v : ({}) }
    Rectangle { width: 1; height: parent.height; color: Theme.line }
    Flickable {
        anchors.fill: parent; anchors.leftMargin: 17; anchors.rightMargin: 16; anchors.topMargin: 14; anchors.bottomMargin: 12
        contentHeight: col.height; clip: true; boundsBehavior: Flickable.StopAtBounds
        Column {
            id: col; width: parent.width; spacing: 18
            Column {
                width: parent.width; spacing: 9
                Section { title: "结构" }
                Repeater {
                    model: [{ k: "layer0", n: "肺", c: Theme.lung, t: "半透明显示肺表面" }, { k: "layer1", n: "气道", c: Theme.airway, t: "" },
                            { k: "layer2", n: "病灶候选", c: Theme.lesion, t: "" }, { k: "route", n: "导航路径", c: Theme.route, t: "" }]
                    Item {
                        width: col.width; height: 22
                        Rectangle { width: 10; height: 10; radius: 3; color: modelData.c; anchors.verticalCenter: parent.verticalCenter }
                        Text { x: 20; text: modelData.n; font.family: Theme.font; font.pixelSize: Theme.fBody; color: Theme.ink; anchors.verticalCenter: parent.verticalCenter }
                        Toggle { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; on: root.s(modelData.k).checked === true
                                 enabledState: root.s(modelData.k).enabled !== false; tip: modelData.t; onToggled: ui.setChecked(modelData.k, value) }
                    }
                }
                Text { width: parent.width; visible: text.indexOf("不可") >= 0 || text.indexOf("缺") >= 0; text: root.s("availability").text || ""
                       wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.warn }
            }
            Column {
                width: parent.width; spacing: 9
                Section { title: "气道着色" }
                Seg { width: parent.width; stretch: true; model: ["结构", "级数", "可达性"]; current: root.s("color").index || 0; onPicked: ui.setIndex("color", index) }
                Text { width: parent.width; visible: text !== ""; text: root.s("legend").text || ""; wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink2 }
            }
            Column {
                width: parent.width; spacing: 6
                Section { title: "肺不透明度"
                    Text { text: Math.round(root.s("opacity").value || 0) + "%"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2 } }
                Slide { width: parent.width; from: 0; to: 100; value: root.s("opacity").value || 0; onMoved: ui.setValue("opacity", value) }
            }
            Column {
                width: parent.width; spacing: 9
                Item {
                    width: parent.width; height: 20
                    Text { text: "剖切"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink3; anchors.verticalCenter: parent.verticalCenter }
                    Toggle { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; on: root.s("clip").checked === true; onToggled: ui.setChecked("clip", value) }
                }
                Seg { visible: root.s("clip").checked === true; width: parent.width; stretch: true; model: ["左右", "前后", "头足"]; current: root.s("clipAxis").index || 0; onPicked: ui.setIndex("clipAxis", index) }
                Slide { visible: root.s("clip").checked === true; width: parent.width; from: -100; to: 100; value: root.s("clipOffset").value || 0; onMoved: ui.setValue("clipOffset", value) }
            }
            Column {
                width: parent.width; spacing: 8
                Item {
                    width: parent.width; height: 20
                    Row { spacing: 8; anchors.verticalCenter: parent.verticalCenter
                        Text { text: "高质量透明"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink3; anchors.verticalCenter: parent.verticalCenter }
                        Tag { text: "PL · C7"; anchors.verticalCenter: parent.verticalCenter } }
                    Toggle { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; on: root.s("precise").checked === true; enabledState: root.s("precise").enabled !== false
                             tip: root.s("precise").tip || ""; onToggled: ui.setChecked("precise", value) }
                }
                Text { width: parent.width; text: root.s("precise").checked === true ? (root.s("compositePerf").text || "") : "停止操作后由 PL 逐层精确合成肺表面"
                       wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink2 }
            }
            Rectangle {
                width: parent.width; height: target.height + 22; radius: Theme.radiusPanel; color: Theme.raised
                Column {
                    id: target; x: 12; y: 11; width: parent.width - 24; spacing: 5
                    Item { width: parent.width; height: 18
                        Text { text: "当前目标"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                        Icon { anchors.right: parent.right; name: "forward"; size: 15; color: Theme.ink3; anchors.verticalCenter: parent.verticalCenter } }
                    Text { width: parent.width; text: root.s("lesion").text || "尚无病灶候选"; elide: Text.ElideRight; font.family: Theme.font; font.pixelSize: Theme.fBody; font.bold: true; color: Theme.ink }
                    Text { width: parent.width; visible: text !== ""; text: root.s("candidateInfo").text || ""; wrapMode: Text.Wrap; maximumLineCount: 4; elide: Text.ElideRight
                           font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink2 }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: ui.action("drawer", "plan") }
            }
        }
    }
}
