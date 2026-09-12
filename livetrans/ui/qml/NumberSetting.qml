import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
ColumnLayout {
    id: root
    property string path: ""
    property string label: ""
    property string hint: ""
    property string suffix: ""
    property real minimum: 0
    property real maximum: 100
    property real step: 1
    property real factor: 1
    property int decimals: 0
    spacing: 7
    Layout.fillWidth: true
    AppText { text: root.label; font.weight: Font.Medium; Layout.fillWidth: true }
    RowLayout {
        spacing: 16
        Layout.fillWidth: true
        Slider {
            id: slider
            Layout.fillWidth: true
            from: root.minimum
            to: root.maximum
            stepSize: root.step
            value: Number(Theme.read(root.path)) * root.factor
            onMoved: preferences.setValue(root.path, value / root.factor)
            Accessible.name: root.label
            background: Rectangle {
                x: slider.leftPadding; y: (slider.height - height) / 2
                width: slider.availableWidth; height: 4; radius: 2
                color: Theme.line
                Rectangle { height: parent.height; radius: 2; width: slider.visualPosition * parent.width; color: Theme.accent }
            }
            handle: Rectangle {
                x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
                y: (slider.height - height) / 2
                width: 20; height: 20; radius: 10
                color: Theme.surface
                border.color: slider.activeFocus ? Theme.accent : Theme.dark ? "#95a2b4" : "#b4c0d0"
                border.width: slider.activeFocus ? 2 : 1
            }
        }
        TextField {
            id: number
            objectName: root.path
            Layout.preferredWidth: 72
            implicitHeight: 36
            horizontalAlignment: Text.AlignHCenter
            text: String(Math.round(Number(Theme.read(root.path)) * root.factor * 100) / 100)
            color: Theme.foreground
            font.family: Theme.font
            font.pixelSize: 13
            selectByMouse: true
            Accessible.name: root.label
            validator: DoubleValidator {
                bottom: root.minimum; top: root.maximum; locale: "C"
                decimals: root.decimals
                notation: DoubleValidator.StandardNotation
            }
            onTextEdited: {
                if (acceptableInput) preferences.setValue(root.path, Number(text) / root.factor);
            }
            onEditingFinished: {
                if (acceptableInput) preferences.setValue(root.path, Number(text) / root.factor);
                else text = String(Number(Theme.read(root.path)) * root.factor);
            }
            background: Rectangle { color: Theme.field; radius: 8; border.color: number.activeFocus ? Theme.accent : Theme.line }
        }
        AppText { text: root.suffix; color: Theme.secondary; font.pixelSize: 12; Layout.preferredWidth: 24 }
    }
    AppText {
        visible: text !== ""
        text: Theme.errorFor(root.path) || root.hint
        color: Theme.errorFor(root.path) ? Theme.error : Theme.secondary
        font.pixelSize: 12
        Layout.fillWidth: true
    }
}
