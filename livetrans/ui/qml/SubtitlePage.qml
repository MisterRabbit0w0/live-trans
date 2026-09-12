import QtQuick
import QtQuick.Layouts
ColumnLayout {
    spacing: 24
    PageHeading { title: "字幕外观"; subtitle: "预览字幕样式，应用后更新悬浮窗。"; Layout.fillWidth: true }
    Panel {
        Layout.fillWidth: true
        gap: 14
        RowLayout {
            Layout.fillWidth: true
            AppText { text: "即时预览"; font.weight: Font.DemiBold; Layout.fillWidth: true }
            AppText { text: "应用后更新悬浮窗"; font.pixelSize: 11; color: Theme.secondary }
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: sample.implicitHeight + 48
            radius: 14
            color: Theme.dark ? "#404a60" : "#d8e3f1"
            Rectangle {
                anchors.fill: parent
                anchors.margins: 10
                radius: 12
                color: Qt.rgba(0.035, 0.045, 0.065, preferences.draft.subtitle.opacity)
                border.color: "#647184"
            }
            SubtitleEntry {
                id: sample
                anchors.left: parent.left; anchors.right: parent.right
                anchors.margins: 26; anchors.verticalCenter: parent.verticalCenter
                original: "The next session starts in five minutes."
                translation: "下一场将在五分钟后开始。"
                showOriginal: preferences.draft.subtitle.show_original
                textSize: preferences.draft.subtitle.font_size
                onDark: true
            }
        }
    }
    Panel {
        Layout.fillWidth: true
        ToggleSetting { path: "subtitle.show_original"; label: "显示原文"; hint: "同时显示原文和译文。" }
        NumberSetting { path: "subtitle.font_size"; label: "字幕字号"; minimum: 10; maximum: 48; suffix: "px" }
        NumberSetting { path: "subtitle.max_lines"; label: "同屏条数"; minimum: 1; maximum: 10; suffix: "条" }
        NumberSetting { path: "subtitle.opacity"; label: "背景不透明度"; minimum: 0; maximum: 100; step: 5; factor: 100; suffix: "%" }
        NumberSetting { path: "subtitle.width"; label: "悬浮窗宽度"; minimum: 300; maximum: 2400; step: 10; suffix: "px" }
    }
    AppText { text: "拖动悬浮窗可调整位置，Ctrl + 滚轮可直接调整字号。"; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
}
