import QtQuick 2.15
import "."
// 浮在三维视口左上角：结构预设、适配、复位
Rectangle {
    id: root
    color: Theme.glass; radius: 9; border.color: Theme.glassLine
    readonly property int mode: ui.s.structure !== undefined ? ui.s.structure : 2
    Row {
        anchors.centerIn: parent; spacing: 4
        Seg {
            onGlass: true; anchors.verticalCenter: parent.verticalCenter
            model: ["全部", "肺", "支气管"]
            current: root.mode === 0 ? 1 : root.mode === 1 ? 2 : 0
            onPicked: ui.click(index === 0 ? "preset2" : index === 1 ? "preset0" : "preset1")
        }
        IconButton { onGlass: true; width: 28; height: 28; icon: "fit"; tip: "适配视野：缩放到当前可见结构"; onClicked: ui.click("fit"); anchors.verticalCenter: parent.verticalCenter }
        IconButton { onGlass: true; width: 28; height: 28; icon: "reset"; tip: "复位视角"; onClicked: ui.click("resetView"); anchors.verticalCenter: parent.verticalCenter }
    }
}
