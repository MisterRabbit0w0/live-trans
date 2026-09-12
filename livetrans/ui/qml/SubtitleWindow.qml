import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Layouts
Window {
    id: root
    objectName: "subtitleWindow"
    title: "LiveTrans 字幕"
    flags: Qt.Tool | Qt.WindowStaysOnTopHint
           | (subtitleControls.nativeFrame ? Qt.CustomizeWindowHint : Qt.FramelessWindowHint)
    color: "transparent"
    visible: appController.subtitleVisible
    width: Math.min(appController.committed.subtitle.width, Screen.desktopAvailableWidth - 32)
    height: Math.min(lines.implicitHeight + 32, Screen.desktopAvailableHeight * 0.6)
    Rectangle {
        anchors.fill: parent
        radius: subtitleControls.nativeFrame ? 0 : 16
        color: appearance.highContrast ? "#000000" : appController.committed.subtitle.opacity === 0 && appearance.mainGlass ? "transparent" : appearance.subtitleGlass
            ? Qt.rgba(0.025, 0.035, 0.055, appController.committed.subtitle.opacity * 0.85)
            : "#141923"
        border.width: !subtitleControls.nativeFrame && appController.committed.subtitle.opacity > 0 ? 1 : 0
        border.color: appearance.highContrast ? "#ffffff" : "#707d8d"
    }
    Flickable {
        id: viewport
        anchors.fill: parent
        anchors.margins: 16
        contentWidth: width
        contentHeight: lines.implicitHeight
        clip: true
        onContentHeightChanged: contentY = Math.max(0, contentHeight - height)
        ColumnLayout {
            id: lines
            width: viewport.width
            spacing: 14
            Repeater {
                id: entries
                model: subtitleModel
                delegate: SubtitleEntry {
                    Layout.fillWidth: true
                    textSize: appController.committed.subtitle.font_size
                    showOriginal: appController.committed.subtitle.show_original
                    onDark: true
                }
            }
            AppText {
                visible: entries.count === 0 || ["paused", "starting", "stopping", "error"].indexOf(appController.state) >= 0
                text: entries.count === 0 ? (appController.state === "running" ? "等待声音…" : appController.statusTitle) : appController.statusTitle
                font.pixelSize: Math.max(12, appController.committed.subtitle.font_size * 0.7)
                color: "#c4d1e4"
                Layout.fillWidth: true
            }
        }
    }
    MouseArea {
        id: drag
        anchors.fill: parent
        hoverEnabled: true
        onPressed: root.startSystemMove()
        onWheel: function(event) {
            if (event.modifiers & Qt.ControlModifier) {
                appController.adjustFont(event.angleDelta.y > 0 ? 1 : -1);
                event.accepted = true;
            } else {
                viewport.contentY = Math.max(0, Math.min(viewport.contentHeight - viewport.height, viewport.contentY - event.angleDelta.y / 2));
                event.accepted = true;
            }
        }
    }
    Row {
        anchors.right: parent.right; anchors.rightMargin: 8
        anchors.top: parent.top; anchors.topMargin: 4
        visible: drag.containsMouse || toolbarHover.hovered
        spacing: 4
        HoverHandler { id: toolbarHover }
        ActionButton { text: "控制中心"; implicitHeight: 30; onClicked: appController.showControlCenter() }
        ActionButton { text: "隐藏"; implicitHeight: 30; onClicked: appController.toggleSubtitles() }
    }
}
