import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
Button {
    id: root
    property bool primary: false
    property bool quiet: false
    property string symbol: ""
    implicitHeight: 40
    implicitWidth: contents.implicitWidth + 28
    padding: 0
    leftPadding: 14
    rightPadding: 14
    hoverEnabled: true
    font.family: Theme.font
    font.pixelSize: 13
    Accessible.name: text
    opacity: enabled ? 1 : 0.45
    contentItem: RowLayout {
        id: contents
        spacing: 8
        Icon {
            visible: root.symbol !== ""
            name: root.symbol
            color: root.primary ? (Theme.dark ? "#10223b" : "#ffffff") : Theme.foreground
            Layout.preferredWidth: 16
            Layout.preferredHeight: 16
        }
        AppText {
            text: root.text
            font.pixelSize: 13
            font.weight: Font.DemiBold
            color: root.primary ? (Theme.dark ? "#10223b" : "#ffffff") : Theme.foreground
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
            Layout.fillWidth: true
        }
    }
    background: Item {
        Rectangle {
            anchors.fill: parent
            radius: 11
            // Keep RGB opaque even when hidden; fading transparent black to
            // a light fill creates a dark intermediate frame.
            color: root.primary ? Theme.accent : root.down ? Theme.line : root.hovered || root.quiet ? Theme.field : Theme.surface
            opacity: root.primary || !root.quiet || root.hovered || root.down ? 1 : 0
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            Behavior on opacity { NumberAnimation { duration: Theme.fast } }
        }
        Rectangle {
            anchors.fill: parent
            radius: 11
            color: "transparent"
            // Keyboard focus must remain visible when the hover fill fades out.
            border.width: root.activeFocus ? 2 : root.quiet ? 0 : 1
            border.color: root.activeFocus ? Theme.accent : root.primary ? Theme.accent : Theme.line
        }
    }
}
