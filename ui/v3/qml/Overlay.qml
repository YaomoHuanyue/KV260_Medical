import QtQuick 2.15
import "."
// 覆盖在工作区上的抽屉：左侧 病例 / 规划 / 导出 / 系统，右侧 处理流程。点空白处或 Esc 关闭。
Item {
    id: root
    function s(k) { var v = ui.s[k]; return v ? v : ({}) }
    readonly property string key: ui.s.drawer || ""
    property string shown: ""
    readonly property bool openLeft: key !== "" && key !== "process"
    readonly property bool openRight: key === "process"
    onKeyChanged: if(key !== "") shown = key
    readonly property var pipe: ui.s.pipeline ? ui.s.pipeline : ({ stages: [], running: false, sequence: [] })

    Rectangle {
        anchors.fill: parent; color: "#000000"
        opacity: root.key !== "" ? 0.35 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.slide } }
        MouseArea { anchors.fill: parent; onClicked: ui.action("drawer", "") }
    }

    // ───── 左侧抽屉 ─────
    Rectangle {
        id: left
        width: 300; height: parent.height
        x: root.openLeft ? 0 : -width - 24
        Behavior on x { NumberAnimation { duration: Theme.slide; easing.type: Easing.OutCubic } }
        color: Theme.raised
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.line }
        Rectangle { anchors.left: parent.right; width: 18; height: parent.height
            gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "#59000000" } GradientStop { position: 1; color: "#00000000" } } }
        MouseArea { anchors.fill: parent }  // 吞掉点击，避免穿透到遮罩
        Item {
            anchors.fill: parent; anchors.margins: 18
            Item {
                id: head; width: parent.width; height: 26
                Text { text: root.shown === "case" ? "病例" : root.shown === "plan" ? "规划" : root.shown === "export" ? "导出" : "系统"
                       font.family: Theme.font; font.pixelSize: 16; font.bold: true; color: Theme.ink; anchors.verticalCenter: parent.verticalCenter }
                IconButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; icon: "x"; width: 28; height: 28; tip: "关闭（Esc）"; onClicked: ui.action("drawer", "") }
            }
            Loader {
                anchors.top: head.bottom; anchors.topMargin: 14; width: parent.width; anchors.bottom: parent.bottom
                sourceComponent: root.shown === "case" ? caseView : root.shown === "plan" ? planView : root.shown === "export" ? exportView : systemView
            }
        }
    }

    Component {
        id: caseView
        Flickable {
            contentHeight: c1.height; clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: c1; width: parent.width; spacing: 14
                Rectangle {
                    width: parent.width; height: info.height + 24; radius: Theme.radiusPanel; color: Theme.panel
                    Column { id: info; x: 12; y: 12; width: parent.width - 24; spacing: 4
                        Row { spacing: 8
                            Text { text: root.s("case").text || "未选择 CT"; font.family: Theme.font; font.pixelSize: Theme.fBody + 1; font.bold: true; color: Theme.ink }
                            Pill { visible: (root.s("info").text || "").indexOf("模拟") >= 0; kind: "warn"; text: "模拟病例" } }
                        Text { width: parent.width; text: root.s("info").text || ""; wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink2; lineHeight: 1.2 }
                    }
                }
                Column { width: parent.width; spacing: 2
                    Btn { wide: true; kind: "plain"; icon: "folder-open"; text: "打开 CT 文件"; enabledState: root.s("open").enabled !== false; tip: root.s("open").tip || ""; onClicked: ui.click("open") }
                    Btn { wide: true; kind: "plain"; icon: "folder"; text: "导入 DICOM 目录"; enabledState: root.s("dicom").enabled !== false; tip: root.s("dicom").tip || ""; onClicked: ui.click("dicom") }
                    Btn { wide: true; kind: "plain"; icon: "import"; text: "导入外部分割"; enabledState: root.s("import").enabled !== false; tip: root.s("import").tip || ""; onClicked: ui.click("import") }
                }
                Section { title: "历史结果"
                    IconButton { width: 24; height: 24; iconSize: 15; icon: "refresh"; tip: "重新载入所选结果"; enabledState: root.s("refresh").enabled !== false; onClicked: ui.click("refresh") } }
                Column {
                    width: parent.width; spacing: 2
                    Repeater {
                        model: root.s("results").items || []
                        Rectangle {
                            width: c1.width; height: 30; radius: Theme.radius
                            readonly property bool cur: index === (root.s("results").index || 0)
                            color: cur ? Theme.accentSoft : (ra.containsMouse ? Theme.hover : "transparent")
                            Text { x: 10; width: parent.width - 20; anchors.verticalCenter: parent.verticalCenter; text: modelData; elide: Text.ElideMiddle
                                   font.family: Theme.font; font.pixelSize: Theme.fSmall; color: parent.cur ? Theme.ink : Theme.ink2; font.bold: parent.cur }
                            MouseArea { id: ra; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: ui.setIndex("results", index) }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: planView
        Flickable {
            contentHeight: c2.height; clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: c2; width: parent.width; spacing: 12
                Section { title: "目标候选" }
                Column {
                    width: parent.width; spacing: 2
                    Repeater {
                        model: root.s("lesion").items || []
                        Rectangle {
                            width: c2.width; height: 30; radius: Theme.radius
                            readonly property bool cur: index === (root.s("lesion").index || 0)
                            color: cur ? Theme.accentSoft : (la.containsMouse ? Theme.hover : "transparent")
                            Row { x: 10; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                                Rectangle { width: 8; height: 8; radius: 4; color: Theme.lesion; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: modelData; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: parent.parent.cur ? Theme.ink : Theme.ink2; font.bold: parent.parent.cur } }
                            MouseArea { id: la; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: ui.setIndex("lesion", index) }
                        }
                    }
                }
                Text { width: parent.width; visible: text !== ""; text: root.s("candidateInfo").text || ""; wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink2 }
                Btn { wide: true; icon: "crosshair"; text: "在模型中定位"; enabledState: root.s("focus").enabled !== false; onClicked: { ui.click("focus"); ui.action("drawer", "") } }
                Section { title: "器械与约束" }
                Repeater {
                    model: [{ k: "diameter", n: "器械直径", u: " mm" }, { k: "margin", n: "每侧安全余量", u: " mm" }, { k: "minVolume", n: "最小候选体积", u: " mm³" }]
                    Item { width: c2.width; height: 30
                        Text { text: modelData.n; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                        Stepper { anchors.right: parent.right; width: 140; value: root.s(modelData.k).value || 0; step: root.s(modelData.k).step || 0.1
                                  from: root.s(modelData.k).min || 0; to: root.s(modelData.k).max || 10; decimals: root.s(modelData.k).decimals || 1; suffix: modelData.u
                                  enabledState: root.s(modelData.k).enabled !== false; onChanged: ui.setValue(modelData.k, value) } }
                }
                Btn { wide: true; kind: "primary"; icon: "route"; text: "重新规划导航"; enabledState: root.s("nav").enabled !== false; tip: root.s("nav").tip || ""; onClicked: ui.click("nav") }
                Btn { wide: true; icon: "cube"; text: "重新生成三维模型"; enabledState: root.s("rebuild").enabled !== false; tip: root.s("rebuild").tip || ""; onClicked: ui.click("rebuild") }
                Row { width: parent.width; spacing: 8
                    Btn { width: (parent.width - 8) / 2; text: "比较器械可达性"; enabledState: root.s("compare").enabled !== false; tip: root.s("compare").tip || ""; onClicked: ui.click("compare") }
                    Btn { width: (parent.width - 8) / 2; text: "查看比较结果"; enabledState: root.s("comparisonResults").enabled !== false; onClicked: ui.click("comparisonResults") } }
            }
        }
    }

    Component {
        id: exportView
        Column {
            spacing: 10
            Repeater {
                model: [{ k: "snapshot", i: "camera", t: "保存截图", d: "当前画面保存为 PNG（Ctrl+S）" },
                        { k: "video", i: "video", t: "导出导航视频", d: "沿当前路径录制 MP4" },
                        { k: "export", i: "report", t: "导出模型与报告", d: "三维模型、颜色、导航路径和报告" }]
                Rectangle {
                    width: 264; height: 66; radius: Theme.radiusPanel
                    readonly property bool can: root.s(modelData.k).enabled !== false
                    color: ea.containsMouse && can ? Qt.lighter(Theme.panel, Theme.light ? 0.98 : 1.18) : Theme.panel
                    opacity: can ? 1 : 0.5
                    Rectangle { x: 12; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; radius: 9; color: Theme.accentSoft
                        Icon { anchors.centerIn: parent; name: modelData.i; size: 20; color: Theme.accent } }
                    Column { x: 64; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                        Text { text: modelData.t; font.family: Theme.font; font.pixelSize: Theme.fBody; font.bold: true; color: Theme.ink }
                        Text { text: modelData.d; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink2 } }
                    MouseArea { id: ea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: if(parent.can) { ui.click(modelData.k); ui.action("drawer", "") } }
                }
            }
            Text { width: 264; text: "导出文件保存在板上 ui/exports 目录。导出期间可继续查看，但不能开始新的处理。"; wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3 }
        }
    }

    Component {
        id: systemView
        Flickable {
            contentHeight: c4.height; clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: c4; width: parent.width; spacing: 12
                Section { title: "外观" }
                Seg { width: parent.width; stretch: true; model: ["深色", "浅色"]; current: Theme.light ? 1 : 0; onPicked: ui.setChecked("theme", index === 1) }
                Section { title: "PL 加速模块（动态区轮流装载）" }
                Rectangle {
                    width: parent.width; height: table.height + 16; radius: Theme.radiusPanel; color: Theme.panel
                    Column {
                        id: table; x: 10; y: 8; width: parent.width - 20; spacing: 4
                        Repeater {
                            model: [["D6", "HU 预处理", "4.8k", "0"], ["C5", "卷积引擎", "78.9k", "906"], ["D7", "移动立方体", "11.5k", "18"], ["D9", "网格平滑", "78.1k", "168"],
                                    ["C8", "体距离场", "43.7k", "297"], ["C4", "路径与镜头", "77.9k", "192"], ["C6", "导航画面", "22.3k", "248"], ["C7", "透明合成", "7.3k", "96"]]
                            Item { width: table.width; height: 20
                                Tag { text: modelData[0]; anchors.verticalCenter: parent.verticalCenter }
                                Text { x: 40; text: modelData[1]; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink; anchors.verticalCenter: parent.verticalCenter }
                                Text { anchors.right: parent.right; text: modelData[2] + " LUT · " + modelData[3] + " DSP"; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink2; anchors.verticalCenter: parent.verticalCenter } }
                        }
                        Text { width: table.width; text: "动态区容量 88.3k LUT · 960 DSP；单个模块布线后结果，各行不能相加；切换约 155 ms。"
                               wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3 }
                    }
                }
                Section { title: "运行信息" }
                Repeater {
                    model: [{ k: "scopePerf", n: "导航画面" }, { k: "compositePerf", n: "三维合成" }, { k: "segmentationInfo", n: "分割" }, { k: "exposureStatus", n: "曝光校正" }]
                    Column { width: c4.width; spacing: 2; visible: (root.s(modelData.k).text || "") !== ""
                        Text { text: modelData.n; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3 }
                        Text { width: parent.width; text: root.s(modelData.k).text || ""; wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink2 } }
                }
                Section { title: "日志" }
                Rectangle {
                    width: parent.width; height: 170; radius: Theme.radius; color: Theme.sunken; clip: true
                    Flickable {
                        id: logView; anchors.fill: parent; anchors.margins: 8; contentHeight: logText.height; clip: true
                        onContentHeightChanged: contentY = Math.max(0, contentHeight - height)
                        Text { id: logText; width: parent.width; text: ui.s.log || ""; wrapMode: Text.WrapAnywhere; font.family: Theme.font; font.pixelSize: 11; color: Theme.ink2 }
                    }
                }
                Btn { wide: true; kind: "primary"; icon: "presentation"; text: "一键演示（F5）"; tip: "约 3 分钟：处理记录、影像分割、三维与透明合成、重新规划、实时导航；任意键退出"; onClicked: ui.action("demo") }
                Btn { wide: true; icon: "play"; text: "处理演示（F6）"; tip: "对当前原始 CT 现场执行完整处理（约 2 分钟），字幕随阶段更新；任意键只关闭字幕，不中止处理"; onClicked: ui.action("demoProcess") }
                Btn { wide: true; icon: "power"; text: "退出程序"; onClicked: ui.action("quit") }
            }
        }
    }

    // ───── 右侧：处理流程 ─────
    Rectangle {
        id: right
        width: 340; height: parent.height
        x: root.openRight ? parent.width - width : parent.width + 24
        Behavior on x { NumberAnimation { duration: Theme.slide; easing.type: Easing.OutCubic } }
        color: Theme.raised
        Rectangle { width: 1; height: parent.height; color: Theme.line }
        Rectangle { anchors.right: parent.left; width: 18; height: parent.height
            gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "#00000000" } GradientStop { position: 1; color: "#59000000" } } }
        MouseArea { anchors.fill: parent }
        Column {
            x: 18; y: 16; width: parent.width - 36; spacing: 12
            Item { width: parent.width; height: 26
                Text { text: "完整处理"; font.family: Theme.font; font.pixelSize: 16; font.bold: true; color: Theme.ink; anchors.verticalCenter: parent.verticalCenter }
                Row { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                    Text { text: root.pipe.elapsed || ""; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                    IconButton { width: 28; height: 28; icon: "x"; tip: "关闭（Esc）"; onClicked: ui.action("drawer", ""); anchors.verticalCenter: parent.verticalCenter } } }
            Column {
                width: parent.width; spacing: 0
                Repeater {
                    model: root.pipe.stages
                    Item {
                        width: parent.width; height: stageCol.height + 20
                        Rectangle { width: parent.width; height: 1; color: Theme.line }
                        Rectangle {
                            x: 0; y: 13; width: 16; height: 16; radius: 8
                            color: modelData.state === "done" ? Theme.ok : modelData.state === "fail" ? Theme.bad : "transparent"
                            border.width: modelData.state === "run" ? 2 : modelData.state === "done" || modelData.state === "fail" ? 0 : 1.5
                            border.color: modelData.state === "run" ? Theme.accent : Theme.ink3
                            Icon { anchors.centerIn: parent; visible: modelData.state === "done"; name: "check"; size: 11; color: Theme.accentInk }
                            RotationAnimation on rotation { running: modelData.state === "run"; from: 0; to: 360; duration: 1600; loops: Animation.Infinite }
                            Rectangle { visible: modelData.state === "run"; width: 4; height: 4; radius: 2; color: Theme.accent; x: 6; y: -1 }
                        }
                        Column {
                            id: stageCol; x: 28; y: 10; width: parent.width - 28; spacing: 6
                            Item { width: parent.width; height: 20
                                Text { text: modelData.name; font.family: Theme.font; font.pixelSize: Theme.fBody; font.bold: modelData.state === "run"
                                       color: modelData.state === "wait" ? Theme.ink2 : Theme.ink; anchors.verticalCenter: parent.verticalCenter }
                                Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; font.family: Theme.font; font.pixelSize: Theme.fSmall
                                       text: modelData.state === "run" ? "进行中" : modelData.seconds > 0 ? modelData.seconds.toFixed(1) + " s" : modelData.state === "skip" ? "未执行" : "—"
                                       color: modelData.state === "run" ? Theme.accent : Theme.ink2 } }
                            Flow { width: parent.width; spacing: 6
                                Repeater { model: modelData.pl
                                    Row { spacing: 6
                                        Text { visible: index > 0; text: "→"; font.pixelSize: Theme.fCaption; color: Theme.ink3; anchors.verticalCenter: parent.verticalCenter }
                                        Tag { text: modelData } } }
                                Text { visible: modelData.note !== ""; text: modelData.note; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3 } }
                            Text { visible: modelData.detail !== undefined && modelData.detail !== ""; width: parent.width; text: modelData.detail || ""; wrapMode: Text.Wrap
                                   font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink2 }
                        }
                    }
                }
                Rectangle { width: parent.width; height: 1; color: Theme.line }
            }
            Rectangle {
                width: parent.width; height: rp.height + 24; radius: Theme.radiusPanel
                color: Qt.rgba(Theme.pl.r, Theme.pl.g, Theme.pl.b, 0.06)
                border.color: Qt.rgba(Theme.pl.r, Theme.pl.g, Theme.pl.b, 0.4)
                Column {
                    id: rp; x: 12; y: 12; width: parent.width - 24; spacing: 10
                    Item { width: parent.width; height: 16
                        Text { text: "PL 动态区"; font.family: Theme.font; font.pixelSize: Theme.fSmall; color: Theme.pl; anchors.verticalCenter: parent.verticalCenter }
                        Text { anchors.right: parent.right; text: "每次切换约 155 ms"; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3; anchors.verticalCenter: parent.verticalCenter } }
                    Row { spacing: 10
                        Rectangle {
                            height: 30; radius: 6; width: cur.implicitWidth + 24; color: (root.pipe.module || "") !== "" ? Theme.pl : Theme.sunken
                            Text { id: cur; anchors.centerIn: parent; text: root.pipe.module || "空闲"; font.family: Theme.font; font.pixelSize: Theme.fBody; font.bold: true
                                   color: (root.pipe.module || "") !== "" ? "#FFFFFF" : Theme.ink2 }
                            Behavior on width { NumberAnimation { duration: Theme.slide } }
                        }
                        Text { text: (root.pipe.module || "") !== "" ? "按阶段推断" : ""; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink2; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Flow { width: parent.width; spacing: 6; visible: (root.pipe.sequence || []).length > 0
                        Text { text: "本次顺序"; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3 }
                        Repeater { model: root.pipe.sequence || []
                            Rectangle { height: 18; radius: 4; width: seqText.implicitWidth + 12; color: index === (root.pipe.sequence.length - 1) && root.pipe.running ? Theme.pl : "transparent"; border.color: Theme.line
                                Text { id: seqText; anchors.centerIn: parent; text: modelData; font.family: Theme.font; font.pixelSize: Theme.fCaption
                                       color: index === (root.pipe.sequence.length - 1) && root.pipe.running ? "#FFFFFF" : Theme.ink2 } } } }
                }
            }
            Text { width: parent.width; wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.ink3
                   text: root.pipe.running ? "处理在后台进行，可以继续翻层、旋转模型。“停止后续步骤”会在当前阶段结束后停止。" : "点击顶栏“开始处理”，依次完成分割、清理、重建和规划。" }
            Btn { visible: root.pipe.running; kind: "danger"; icon: "stop"; text: "停止后续步骤"; enabledState: root.s("stop").enabled === true; onClicked: ui.click("stop") }
        }
    }
}
