import QtQuick 2.15
import "."
Text {
    property string name: ""
    property int size: 18
    text: Theme.glyph(name)
    font.family: Theme.iconFamily
    font.pixelSize: size
    color: Theme.ink2
    verticalAlignment: Text.AlignVCenter
    horizontalAlignment: Text.AlignHCenter
}
