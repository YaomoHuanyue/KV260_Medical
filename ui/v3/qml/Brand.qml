import QtQuick 2.15
import "."
// 标识：圆角方块里画一棵分叉的支气管树
Rectangle {
    width: 24; height: 24; radius: 6; color: Theme.accent
    Canvas {
        id: art
        anchors.fill: parent
        onPaint: {
            var c = getContext("2d"); c.reset();
            c.strokeStyle = Theme.accentInk; c.lineWidth = 1.9; c.lineCap = "round";
            c.beginPath(); c.moveTo(12, 4.5); c.lineTo(12, 11.5);
            c.moveTo(12, 11.5); c.lineTo(7.5, 15.7); c.lineTo(7.5, 19.3);
            c.moveTo(12, 11.5); c.lineTo(16.5, 15.7); c.lineTo(16.5, 19.3);
            c.moveTo(7.5, 15.7); c.lineTo(5.2, 17.3); c.moveTo(16.5, 15.7); c.lineTo(18.8, 17.3);
            c.stroke();
        }
        Connections { target: Theme; function onLightChanged() { art.requestPaint() } }
    }
}
