import QtQuick
import QtQuick.Layouts
ColumnLayout {
    id: root
    required property string original
    required property string translation
    property bool showOriginal: true
    property real textSize: 22
    property bool onDark: false
    spacing: 5
    AppText {
        visible: root.showOriginal && root.original !== "" && root.translation !== root.original
        text: root.original
        font.pixelSize: Math.max(11, root.textSize * 0.72)
        color: root.onDark ? "#c5cedb" : Theme.secondary
        Layout.fillWidth: true
    }
    AppText {
        text: root.translation || "…"
        font.pixelSize: root.textSize
        font.weight: Font.DemiBold
        color: root.onDark ? "#ffffff" : Theme.foreground
        Layout.fillWidth: true
    }
}
