import QtQuick 2.15
import "."
// 左侧图标栏：点开覆盖式抽屉，再点一次收起
Rectangle {
    id: root
    color: Theme.panel
    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.line }
    Column {
        y: 10; width: parent.width; spacing: 6
        RailItem { key: "case"; icon: "folder"; label: "病例"; tip: "打开 CT、导入数据、历史结果" }
        RailItem { key: "plan"; icon: "target"; label: "规划"; tip: "选择目标、器械参数、重新规划" }
        RailItem { key: "export"; icon: "download"; label: "导出"; tip: "截图、导航视频、模型与报告" }
    }
    Column {
        anchors.bottom: parent.bottom; anchors.bottomMargin: 10; width: parent.width; spacing: 6
        RailItem { key: "system"; icon: "cpu"; label: "系统"; tip: "PL 模块、运行信息、日志与外观" }
    }
}
