import QtQuick
import QtQuick.Layouts
ColumnLayout {
    spacing: 24
    PageHeading { title: "声音来源"; subtitle: "捕获系统声音，或指定一个应用。"; Layout.fillWidth: true }
    Panel {
        Layout.fillWidth: true
        ChoiceSetting {
            path: "audio_source_mode"; label: "捕获范围"
            options: [{label: "整个系统", value: "system"}, {label: "指定软件", value: "process"}]
        }
        ChoiceSetting {
            visible: preferences.draft.audio_source_mode === "system"
            path: "audio_device_index"; label: "输出设备"; options: appController.devices
            hint: "捕获此设备正在播放的声音，不需要虚拟声卡。"
        }
        ChoiceSetting {
            visible: preferences.draft.audio_source_mode === "process"
            path: "audio_process_name"; label: "目标软件"; options: appController.processes
            editable: true
            hint: "先让软件播放声音再刷新，也可直接输入 chrome.exe 等进程名。"
        }
        RowLayout {
            Layout.fillWidth: true
            AppText {
                Layout.fillWidth: true
                text: appController.discoveryError || "设备变更后，刷新列表并重新选择。"
                color: appController.discoveryError ? Theme.error : Theme.secondary
                font.pixelSize: 12
            }
            ActionButton {
                objectName: "refreshDevices"
                text: appController.refreshing ? "正在刷新…" : "刷新列表"
                symbol: "refresh"; enabled: !appController.refreshing
                onClicked: appController.refreshDevices()
            }
        }
    }
    AppText { text: "声音来源的修改将在应用设置后生效。"; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
}
