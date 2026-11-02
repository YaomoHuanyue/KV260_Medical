import QtQuick 2.15
import "."
// 数值步进：− 值 +
Rectangle {
    id: root
    property real value: 0
    property real step: 0.1
    property real from: 0
    property real to: 10
    property int decimals: 1
    property string suffix: ""
    property bool enabledState: true
    signal changed(real value)
    implicitWidth: 132; implicitHeight: 30
    radius: Theme.radius
    color: Theme.sunken
    opacity: enabledState ? 1 : 0.45
    function bump(d) { if(!enabledState) return; var v = Math.max(from, Math.min(to, Math.round((value + d) / step) * step)); changed(Number(v.toFixed(decimals))) }
    IconButton { id: minus; x: 1; y: 1; width: 28; height: 28; icon: "back"; iconSize: 15; enabledState: root.enabledState && root.value > root.from; onClicked: root.bump(-root.step) }
    Text { anchors.centerIn: parent; text: root.value.toFixed(root.decimals) + root.suffix; font.family: Theme.font; font.pixelSize: Theme.fBody; color: Theme.ink }
    IconButton { x: parent.width - 29; y: 1; width: 28; height: 28; icon: "forward"; iconSize: 15; enabledState: root.enabledState && root.value < root.to; onClicked: root.bump(root.step) }
}
