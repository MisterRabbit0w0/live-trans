import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
ColumnLayout {
    id: root
    property string path: ""
    property string label: ""
    property string hint: ""
    property var options: []
    property bool editable: false
    spacing: 8
    Layout.fillWidth: true
    AppText { text: root.label; font.weight: Font.Medium; Layout.fillWidth: true }
    ComboBox {
        id: input
        objectName: root.path
        Layout.fillWidth: true
        implicitHeight: 42
        model: root.options
        textRole: "label"
        valueRole: "value"
        editable: root.editable
        currentIndex: {
            const v = Theme.read(root.path);
            for (let i = 0; i < root.options.length; ++i)
                if (root.options[i].value === v) return i;
            return -1;
        }
        onActivated: preferences.setValue(root.path, currentValue)
        font.family: Theme.font
        font.pixelSize: 14
        Accessible.name: root.label
        contentItem: TextField {
            leftPadding: 12
            rightPadding: 36
            verticalAlignment: Text.AlignVCenter
            text: root.editable ? String(Theme.read(root.path)) : input.displayText
            readOnly: !root.editable
            enabled: root.editable
            selectByMouse: root.editable
            color: Theme.foreground
            selectionColor: Theme.accent
            font: input.font
            background: null
            onTextEdited: preferences.setValue(root.path, text)
            Accessible.name: root.label
        }
        indicator: Icon { x: input.width - 28; y: (input.height - height) / 2; name: "chevron"; width: 16; height: 16 }
        background: Rectangle {
            color: Theme.field
            radius: 10
            border.width: input.activeFocus ? 2 : 1
            border.color: Theme.errorFor(root.path) ? Theme.error : input.activeFocus ? Theme.accent : Theme.line
        }
        delegate: ItemDelegate {
            required property var modelData
            required property int index
            width: input.width
            implicitHeight: 38
            contentItem: AppText { text: modelData.label; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
            background: Rectangle { color: parent.highlighted ? Theme.accentSoft : Theme.surface; radius: 6 }
            highlighted: input.highlightedIndex === index
        }
        popup: Popup {
            y: input.height + 4
            width: input.width
            implicitHeight: Math.min(contentItem.implicitHeight + 12, 270)
            padding: 6
            background: Rectangle { radius: 12; color: Theme.surface; border.color: Theme.line }
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: input.popup.visible ? input.delegateModel : null
                currentIndex: input.highlightedIndex
                ScrollIndicator.vertical: ScrollIndicator {}
            }
        }
    }
    AppText {
        visible: text !== ""
        text: Theme.errorFor(root.path) || root.hint
        color: Theme.errorFor(root.path) ? Theme.error : Theme.secondary
        font.pixelSize: 12
        Layout.fillWidth: true
    }
}
