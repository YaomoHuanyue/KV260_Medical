import QtQuick 2.15
import QtQuick.Controls 2.15
import "."
ToolTip {
    id: tip
    delay: 500
    timeout: 6000
    contentItem: Text { text: tip.text; color: "#E6E9ED"; font.family: Theme.font; font.pixelSize: Theme.fSmall; wrapMode: Text.Wrap }
    background: Rectangle { color: "#F0181C22"; radius: 6; border.color: "#22FFFFFF" }
}
