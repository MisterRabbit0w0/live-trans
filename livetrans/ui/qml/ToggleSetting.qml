import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
RowLayout {
    id: root
    property string path: ""
    property string label: ""
    property string hint: ""
    spacing: 20
    Layout.fillWidth: true
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 5
        AppText { text: root.label; font.weight: Font.Medium; Layout.fillWidth: true }
        AppText { visible: text !== ""; text: root.hint; color: Theme.secondary; font.pixelSize: 12; Layout.fillWidth: true }
    }
    Switch {
        id: input
        objectName: root.path
        checked: Boolean(Theme.read(root.path))
        onToggled: preferences.setValue(root.path, checked)
        Accessible.name: root.label
        implicitWidth: 48
        implicitHeight: 32
        padding: 0
        indicator: Rectangle {
            y: 3
            width: 46
            height: 26
            radius: 13
            color: input.checked ? Theme.accent : Theme.dark ? "#566171" : "#c2cbd7"
            border.width: input.activeFocus ? 2 : 0
            border.color: Theme.foreground
            Rectangle {
                width: 22; height: 22; radius: 11; y: 2
                x: input.checked ? 22 : 2
                color: "#ffffff"
                Behavior on x { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
            }
        }
    }
}
