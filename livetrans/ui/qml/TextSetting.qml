import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
ColumnLayout {
    id: root
    property string path: ""
    property string label: ""
    property string hint: ""
    property bool secret: false
    spacing: 8
    Layout.fillWidth: true
    AppText { text: root.label; font.weight: Font.Medium; Layout.fillWidth: true }
    TextField {
        id: input
        objectName: root.path
        Layout.fillWidth: true
        implicitHeight: 42
        text: String(Theme.read(root.path))
        onTextEdited: preferences.setValue(root.path, text)
        echoMode: root.secret ? TextInput.Password : TextInput.Normal
        selectByMouse: true
        color: Theme.foreground
        selectionColor: Theme.accent
        selectedTextColor: "#ffffff"
        font.family: Theme.font
        font.pixelSize: 14
        leftPadding: 12
        rightPadding: 12
        Accessible.name: root.label
        background: Rectangle {
            radius: 10
            color: Theme.field
            border.width: input.activeFocus ? 2 : 1
            border.color: Theme.errorFor(root.path) ? Theme.error : input.activeFocus ? Theme.accent : Theme.line
        }
    }
    SettingHint { path: root.path; hint: root.hint }
}
