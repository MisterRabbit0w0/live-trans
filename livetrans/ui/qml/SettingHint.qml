import QtQuick
import QtQuick.Layouts

AppText {
    property string path: ""
    property string hint: ""
    readonly property string errorText: Theme.errorFor(path)
    visible: text !== ""
    text: errorText || hint
    color: errorText ? Theme.error : Theme.secondary
    font.pixelSize: 12
    Layout.fillWidth: true
}
