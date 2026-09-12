import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
Pane {
    id: root
    default property alias contents: body.data
    property int gap: 20
    padding: 24
    implicitHeight: body.implicitHeight + topPadding + bottomPadding
    background: Rectangle {
        radius: 18
        color: Theme.surface
        border.width: 1
        border.color: Theme.highContrast ? Theme.foreground : Theme.dark ? "#343d4c" : "#e7ebf2"
    }
    contentItem: ColumnLayout { id: body; spacing: root.gap }
}
