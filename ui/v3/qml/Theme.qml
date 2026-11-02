pragma Singleton
import QtQuick 2.15

// 视觉规范：见 kv260_system/docs/界面重构规划_V3.md 第五节。每种颜色只有一种含义。
QtObject {
    id: t
    readonly property bool light: ui && ui.s.theme === "light"
    // 界面色
    readonly property color room:   light ? "#EEF0F3" : "#0B0D10"
    readonly property color panel:  light ? "#FFFFFF" : "#13161B"
    readonly property color raised: light ? "#F5F6F8" : "#1B1F25"
    readonly property color sunken: light ? "#E6E9ED" : "#0F1216"
    readonly property color line:   light ? "#DADDE2" : "#252A31"
    readonly property color hover:  light ? "#0F000000" : "#0FFFFFFF"
    readonly property color ink:    light ? "#15181D" : "#E6E9ED"
    readonly property color ink2:   light ? "#535B66" : "#9BA3AD"
    readonly property color ink3:   light ? "#8A929C" : "#67707B"
    readonly property color accent: light ? "#1F7AE0" : "#4DA3FF"
    readonly property color accentInk: light ? "#FFFFFF" : "#06121F"
    readonly property color accentSoft: light ? "#1F1F7AE0" : "#2E4DA3FF"
    readonly property color pl:     light ? "#6E4FE0" : "#A98BFF"
    readonly property color plSoft: light ? "#1A6E4FE0" : "#22A98BFF"
    // 解剖色（只用于图像和图例）
    readonly property color lung:   "#6F8FB8"
    readonly property color airway: "#3CC8B0"
    readonly property color lesion: "#FF5D5D"
    readonly property color route:  "#FFD15C"
    // 状态色
    readonly property color ok:   light ? "#1E9E6E" : "#34C38F"
    readonly property color warn: light ? "#B7821D" : "#F2B84B"
    readonly property color bad:  light ? "#D2434F" : "#F0616D"
    readonly property color scrim: "#80000000"
    // 浮在图像上的半透明底（图像区始终是深色）
    readonly property color glass: "#D913161B"
    readonly property color glassLine: "#14FFFFFF"
    readonly property color glassInk: "#E6E9ED"
    readonly property color glassInk2: "#9BA3AD"

    readonly property string font: "Noto Sans CJK SC"
    readonly property int fTitle: 15
    readonly property int fBody: 13
    readonly property int fSmall: 12
    readonly property int fCaption: 11
    readonly property int fBig: 22
    readonly property int radius: 6
    readonly property int radiusPanel: 10
    readonly property int quick: 120
    readonly property int slide: 180

    property FontLoader iconFont: FontLoader { source: "qrc:/assets/tabler-icons.ttf" }
    readonly property string iconFamily: iconFont.name
    readonly property var glyphs: ({
        "folder": "", "folder-open": "﫷", "target": "", "download": "", "cpu": "",
        "play": "", "pause": "", "first": "", "last": "", "back": "", "forward": "",
        "center": "", "tune": "", "more": "", "fit": "", "reset": "", "check": "",
        "stop": "", "image": "", "cube": "流", "route": "", "eye": "", "eye-off": "",
        "sun": "", "moon": "", "x": "", "video": "", "camera": "", "report": "",
        "history": "", "refresh": "", "lungs": "", "scan": "", "info": "",
        "alert": "", "done": "", "loader": "", "settings": "", "bolt": "", "layers": "",
        "cut": "", "palette": "", "pin": "", "crosshair": "", "ruler": "", "power": "",
        "terminal": "", "presentation": "", "import": "", "database": "", "chart": ""
    })
    function glyph(name) { return glyphs[name] !== undefined ? glyphs[name] : "" }
}
