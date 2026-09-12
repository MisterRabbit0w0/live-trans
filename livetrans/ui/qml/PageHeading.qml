import QtQuick
import QtQuick.Layouts
ColumnLayout {
    property string title: ""
    property string subtitle: ""
    spacing: 8
    AppText { text: parent.title; font.pixelSize: 28; font.weight: Font.DemiBold; Layout.fillWidth: true }
    AppText { text: parent.subtitle; color: Theme.secondary; Layout.fillWidth: true }
}
