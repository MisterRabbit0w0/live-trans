import QtQuick
import QtQuick.Layouts
ColumnLayout {
    id: page
    signal navigate(int index)
    spacing: 18
    PageHeading { title: "实时翻译"; subtitle: "管理翻译状态，查看最近的字幕。"; Layout.fillWidth: true }
    Panel {
        Layout.fillWidth: true
        padding: 22
        RowLayout {
            Layout.fillWidth: true
            spacing: 24
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 10
                AppText { text: appController.statusTitle; font.pixelSize: 22; font.weight: Font.DemiBold; Layout.fillWidth: true }
                AppText { text: appController.statusDetail; color: Theme.secondary; Layout.fillWidth: true }
                RowLayout {
                    Layout.topMargin: 2
                    spacing: 10
                    ActionButton {
                        objectName: "primaryAction"
                        primary: true
                        symbol: appController.state === "running" ? "pause" : "play"
                        text: appController.state === "running" ? "暂停翻译" : appController.state === "paused" ? "继续翻译" : appController.state === "error" ? "重试" : "开始翻译"
                        enabled: !appController.busy
                        onClicked: appController.togglePause()
                    }
                    ActionButton {
                        text: "停止"; symbol: "stop"; quiet: true
                        visible: ["starting", "running", "paused", "stopping"].indexOf(appController.state) >= 0
                        enabled: appController.state !== "stopping"
                        onClicked: appController.stop()
                    }
                }
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 16
        Panel {
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            Layout.fillHeight: true
            padding: 18
            gap: 8
            RowLayout {
                Layout.fillWidth: true
                Icon { name: "audio" }
                AppText { text: "声音来源"; color: Theme.secondary; Layout.fillWidth: true }
            }
            AppText { text: appController.sourceLabel; font.weight: Font.DemiBold; maximumLineCount: 2; elide: Text.ElideRight; Layout.fillWidth: true }
            ActionButton { text: "更改来源"; symbol: "arrow"; quiet: true; implicitHeight: 30; onClicked: page.navigate(1) }
        }
        Panel {
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            Layout.fillHeight: true
            padding: 18
            gap: 8
            RowLayout {
                Layout.fillWidth: true
                Icon { name: "translate" }
                AppText { text: "语言与识别"; color: Theme.secondary; Layout.fillWidth: true }
            }
            AppText { text: appController.modelLabel + "  →  " + appController.committed.translate.target_language; font.weight: Font.DemiBold; maximumLineCount: 2; elide: Text.ElideRight; Layout.fillWidth: true }
            ActionButton { text: "调整识别"; symbol: "arrow"; quiet: true; implicitHeight: 30; onClicked: page.navigate(2) }
        }
    }
    Panel {
        Layout.fillWidth: true
        padding: 20
        gap: 12
        RowLayout {
            Layout.fillWidth: true
            AppText { text: "最近字幕"; font.pixelSize: 16; font.weight: Font.DemiBold; Layout.fillWidth: true }
            ActionButton {
                text: appController.subtitleVisible ? "隐藏悬浮字幕" : "显示悬浮字幕"
                symbol: "subtitles"; quiet: true
                implicitHeight: 30
                onClicked: appController.toggleSubtitles()
            }
        }
        ColumnLayout {
            visible: entries.count === 0
            Layout.fillWidth: true
            Layout.bottomMargin: 4
            spacing: 6
            AppText { text: "暂无字幕"; color: Theme.secondary; Layout.fillWidth: true }
            AppText { text: "开始翻译后，原文和译文会出现在这里。"; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
        }
        Repeater {
            id: entries
            model: subtitleModel
            delegate: SubtitleEntry {
                Layout.fillWidth: true
                textSize: 17
                showOriginal: appController.committed.subtitle.show_original
            }
        }
    }
}
