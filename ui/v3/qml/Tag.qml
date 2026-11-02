import QtQuick 2.15
import "."
// “PL · 模块”标签：全界面固定表示“这里用了 FPGA”
Rectangle {
    property string text: ""
    property bool dim: false
    property bool onGlass: false
    implicitWidth: label.implicitWidth + 14; implicitHeight: 18
    radius: 9
    color: onGlass ? "#B30B0D10" : Theme.plSoft
    border.color: Qt.rgba(Theme.pl.r, Theme.pl.g, Theme.pl.b, 0.45)
    opacity: dim ? 0.55 : 1
    Text { id: label; anchors.centerIn: parent; text: parent.text; font.family: Theme.font; font.pixelSize: Theme.fCaption; color: Theme.pl }
}
