import QtQuick 2.15
import "."
// 轴位底部：层面滑条 + 单击读数
Rectangle {
    id: root
    function s(k) { var v = ui.s[k]; return v ? v : ({}) }
    readonly property var axial: s("axial")
    readonly property string reading: s("coordinate").text || ""
    readonly property bool hint: reading.indexOf("滚轮") >= 0 || reading === ""
    color: Theme.glass; radius: 8; border.color: Theme.glassLine
    Row {
        anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 10
        Text { text: "层面"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.glassInk2; anchors.verticalCenter: parent.verticalCenter }
        Slide {
            id: bar
            width: Math.max(140, parent.width * (root.hint ? 0.55 : 0.36))
            anchors.verticalCenter: parent.verticalCenter
            onGlass: true
            from: root.axial.min || 0; to: root.axial.max || 1; value: root.axial.value || 0
            onMoved: ui.setValue("axial", value)
            Behavior on width { NumberAnimation { duration: Theme.slide } }
        }
        Text { text: ((root.axial.value || 0) + 1) + " / " + ((root.axial.max || 0) + 1); font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.glassInk; anchors.verticalCenter: parent.verticalCenter }
        Rectangle { width: 1; height: 16; color: "#33FFFFFF"; anchors.verticalCenter: parent.verticalCenter }
        Text {
            id: readout
            width: parent.width - x; elide: Text.ElideRight
            text: root.hint ? "单击图像读取 CT 值" : root.reading
            font.family: Theme.font; font.pixelSize: Theme.fSmall
            color: root.hint ? Theme.glassInk2 : "#FFFFFF"
            anchors.verticalCenter: parent.verticalCenter
            onTextChanged: if(!root.hint) { opacity = 1; fade.restart() }
            SequentialAnimation { id: fade; PauseAnimation { duration: 5000 } NumberAnimation { target: readout; property: "opacity"; to: 0.55; duration: 400 } }
        }
    }
}
