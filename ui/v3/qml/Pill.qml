import QtQuick 2.15
import "."
// 状态胶囊：ok / warn / bad / run / idle
Rectangle {
    id: root
    property string text: ""
    property string kind: "ok"
    readonly property color tone: kind === "ok" ? Theme.ok : kind === "warn" ? Theme.warn : kind === "bad" ? Theme.bad : kind === "run" ? Theme.accent : Theme.ink3
    implicitWidth: label.implicitWidth + 16; implicitHeight: 20
    radius: 10
    color: Qt.rgba(tone.r, tone.g, tone.b, 0.15)
    Text { id: label; anchors.centerIn: parent; text: root.text; font.family: Theme.font; font.pixelSize: Theme.fCaption; font.bold: true; color: root.tone }
}
