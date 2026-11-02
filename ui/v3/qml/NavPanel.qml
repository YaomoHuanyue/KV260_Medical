import QtQuick 2.15
import "."
// 导航页右栏：测量值优先，设置在下方
Rectangle {
    id: root
    color: Theme.panel
    function s(k) { var v = ui.s[k]; return v ? v : ({}) }
    readonly property var hud: ui.s.hud ? ui.s.hud : ({})
    readonly property string state: hud.state || ""
    function num(v, d) { return (v === undefined || v === null || isNaN(v)) ? "—" : Number(v).toFixed(d === undefined ? 2 : d) }
    Rectangle { width: 1; height: parent.height; color: Theme.line }
    Flickable {
        anchors.fill: parent; anchors.leftMargin: 17; anchors.rightMargin: 16; anchors.topMargin: 12; anchors.bottomMargin: 12
        contentHeight: col.height; clip: true; boundsBehavior: Flickable.StopAtBounds
        Column {
            id: col; width: parent.width; spacing: 14
            Item {
                width: parent.width; height: 22
                Text { text: "联动总览"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink3; anchors.verticalCenter: parent.verticalCenter }
                Toggle { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; on: root.s("dual").checked === true; enabledState: root.s("dual").enabled !== false
                         tip: "在上方同步显示三维模型和当前镜头位置"; onToggled: ui.setChecked("dual", value) }
            }
            Column {
                width: parent.width; spacing: 4
                Text { text: "当前管径"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink3 }
                Row { spacing: 4
                    Text { text: root.num(root.hud.current_diameter_mm); font.family: Theme.font; font.pixelSize: Theme.fBig; font.bold: true; color: Theme.ink }
                    Text { text: "mm"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2; anchors.baseline: parent.children[0].baseline } }
            }
            Column {
                width: parent.width; spacing: 6
                Item { width: parent.width; height: 18
                    Text { text: "前方 10 mm 保守管径"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2 }
                    Text { anchors.right: parent.right; text: root.num(root.hud.forward_adjusted_diameter_mm) + " mm"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink } }
                Item { width: parent.width; height: 18
                    Text { text: "器械单侧余量"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2 }
                    Text { anchors.right: parent.right; text: root.num(root.hud.spare_radius_mm) + " mm"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink } }
                Pill {
                    visible: root.state !== ""
                    kind: root.state === "blocked" ? "bad" : root.state === "caution" ? "warn" : "ok"
                    text: root.state === "blocked" ? "受约束" : root.state === "caution" ? "余量较小" : "满足约束"
                }
                Text { width: parent.width; text: "图像几何估算"; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3; visible: root.state !== "" }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.line }
            Column {
                width: parent.width; spacing: 6
                Item { width: parent.width; height: 18
                    Text { text: "沿路径剩余"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2 }
                    Text { anchors.right: parent.right; text: ui.s.remaining !== undefined ? root.num(ui.s.remaining, 1) + " mm" : "—"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink } }
                Item { width: parent.width; height: 18
                    Text { text: "器械 / 每侧余量"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2 }
                    Text { anchors.right: parent.right; text: root.num(root.s("diameter").value, 1) + " / " + root.num(root.s("margin").value, 1) + " mm"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink } }
            }
            Rectangle {
                width: parent.width; height: routeText.height + 20; radius: Theme.radiusPanel; color: Theme.raised
                visible: (root.s("routeInfo").text || "") !== ""
                Text { id: routeText; x: 11; y: 10; width: parent.width - 22; text: root.s("routeInfo").text || ""; wrapMode: Text.Wrap
                       font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink2; lineHeight: 1.15 }
            }
            Column {
                width: parent.width; spacing: 9
                Section { title: "手柄镜头" }
                Item { width: parent.width; height: 22
                    Text { text: "启用手柄"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                    Toggle { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; on: root.s("gamepad").checked === true; enabledState: root.s("gamepad").enabled !== false; onToggled: ui.setChecked("gamepad", value) } }
                Text { width: parent.width; text: root.s("gamepadStatus").text || "手柄未连接"; wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink }
                Item { width: parent.width; height: 30
                    Text { text: "转向速度"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                    Stepper { anchors.right: parent.right; width: 140; value: root.s("gamepadTurn").value || 45; step: 5; from: 5; to: 120; decimals: 0; suffix: " °/s"; onChanged: ui.setValue("gamepadTurn", value) } }
                Text { width: parent.width; text: "左杆上下：前进 / 后退\n右杆：镜头方向\n松杆停止并保持视角，关闭自动矫正"; wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3 }
                Section { title: "播放与画面" }
                Item { width: parent.width; height: 30
                    Text { text: "速度"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                    Stepper { anchors.right: parent.right; width: 140; value: root.s("speed").value || 0; step: root.s("speed").step || 0.5; from: root.s("speed").min || 0; to: root.s("speed").max || 100
                              decimals: root.s("speed").decimals || 1; suffix: " mm/s"; onChanged: ui.setValue("speed", value) } }
                Item { width: parent.width; height: 30
                    Text { text: "步长"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                    Stepper { anchors.right: parent.right; width: 140; value: root.s("step").value || 0; step: root.s("step").step || 0.5; from: root.s("step").min || 0; to: root.s("step").max || 100
                              decimals: root.s("step").decimals || 1; suffix: " mm"; onChanged: ui.setValue("step", value) } }
                Item { width: parent.width; height: 22
                    Text { text: "自动对齐路径"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                    Toggle { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; on: root.s("align").checked === true; enabledState: root.s("align").enabled !== false; onToggled: ui.setChecked("align", value) } }
                Item { width: parent.width; height: 22
                    Text { text: "曝光校正"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                    Toggle { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; on: root.s("exposure").checked === true; enabledState: root.s("exposure").enabled !== false
                             tip: root.s("exposure").tip || ""; onToggled: ui.setChecked("exposure", value) } }
                Text { text: "画质"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2 }
                Seg { width: parent.width; stretch: true; model: ["清晰", "自动", "流畅"]; current: root.s("quality").index || 0; onPicked: ui.setIndex("quality", index) }
                Text { width: parent.width; text: "键盘：W/S 或 ← → 逐步 · 空格播放 · Home/End 起点/终点 · 双击画面回正"
                       wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3 }
            }
        }
    }
}
