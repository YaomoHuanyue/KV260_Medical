import QtQuick 2.15
import "."
// 虚拟支气管镜画面左上角浮层：所在级数、下一分岔距离与转向、到病灶距离
Rectangle {
    id: root
    readonly property var n: ui.s.navInfo ? ui.s.navInfo : ({})
    readonly property int passed: n.junctions_passed !== undefined ? n.junctions_passed : -1
    readonly property bool hasNext: n.next_junction_mm !== undefined
    function num(v, d) { return (v === undefined || v === null || isNaN(v)) ? "—" : Number(v).toFixed(d) }
    function arrow(d) { return d === "向左" ? "←" : d === "向右" ? "→" : d === "向上" ? "↑" : d === "向下" ? "↓" : "↑" }
    color: "#D90B0D10"; radius: 10; border.color: "#33FFFFFF"
    visible: passed >= 0
    Column {
        x: 12; y: 10; width: parent.width - 24; spacing: 6
        Row {
            spacing: 8
            Text { text: root.passed <= 0 ? "气管" : "第 " + root.passed + " 级支气管"; font.family: Theme.font; font.pixelSize: 15; font.bold: true; color: "#FFFFFF" }
            Text { anchors.baseline: parent.children[0].baseline; text: "已过分岔 " + Math.max(root.passed, 0) + " / " + (root.n.junctions_total || 0)
                   font.family: Theme.font; font.pixelSize: Theme.fCaption; color: "#9BA3AD" }
        }
        Row {
            spacing: 10; height: 34
            Rectangle { width: 34; height: 34; radius: 17; color: root.hasNext ? "#4D7A4DB8" : "#33FFFFFF"
                Text { anchors.centerIn: parent; text: root.hasNext ? root.arrow(root.n.next_direction) : "●"; font.pixelSize: 18; font.bold: true; color: "#FFFFFF" } }
            Column {
                anchors.verticalCenter: parent.verticalCenter; spacing: 1
                Text { text: root.hasNext ? root.num(root.n.next_junction_mm, 0) + " mm 后分岔 · " + root.n.next_direction : "前方无分岔，接近路径终点"
                       font.family: Theme.font; font.pixelSize: 13; font.bold: true; color: "#FFFFFF" }
                Text { visible: root.hasNext; text: "转角约 " + root.num(root.n.next_angle_deg, 0) + "°"; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: "#9BA3AD" }
            }
        }
        Text { visible: root.n.target_distance_mm !== undefined; text: "距目标病灶 " + root.num(root.n.target_distance_mm, 1) + " mm（直线）"
               font.family: Theme.font; font.pixelSize: Theme.fSmall; color: "#E58FB5" }
    }
}
