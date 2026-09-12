import QtQuick
import QtQuick.Layouts
ColumnLayout {
    spacing: 24
    PageHeading { title: "通用"; subtitle: "设置启动方式、主题和辅助显示选项。"; Layout.fillWidth: true }
    Panel {
        Layout.fillWidth: true
        AppText { text: "启动与后台"; font.pixelSize: 16; font.weight: Font.DemiBold }
        ToggleSetting { path: "ui.silent_start"; label: "静默启动"; hint: "启动时隐藏控制中心，保留系统托盘。翻译时仍显示字幕。" }
        ToggleSetting { path: "ui.auto_translate"; label: "启动后自动开始翻译"; hint: "使用已保存的声音来源和模型配置。" }
        AppText { text: "关闭控制中心后仍在后台运行。可从系统托盘重新打开或退出。"; font.pixelSize: 12; color: Theme.secondary; Layout.fillWidth: true }
    }
    Panel {
        Layout.fillWidth: true
        AppText { text: "外观与辅助显示"; font.pixelSize: 16; font.weight: Font.DemiBold }
        ChoiceSetting {
            path: "ui.theme"; label: "主题"
            options: [{label: "跟随系统", value: "system"}, {label: "浅色", value: "light"}, {label: "深色", value: "dark"}]
        }
        ToggleSetting { path: "ui.reduce_motion"; label: "减少动态效果"; hint: "关闭页面切换和控件过渡动画。" }
        ToggleSetting { path: "ui.reduce_transparency"; label: "减少透明效果"; hint: "使用实色面板，提高内容对比度。" }
        AppText { text: "同时遵循 Windows 的动画、透明度和高对比设置。"; font.pixelSize: 12; color: Theme.secondary; Layout.fillWidth: true }
    }
    Panel {
        Layout.fillWidth: true
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                AppText { text: "LiveTrans"; font.pixelSize: 16; font.weight: Font.DemiBold }
                AppText { text: "实时语音识别与翻译"; color: Theme.secondary; font.pixelSize: 12 }
            }
            ActionButton { text: "打开日志目录"; symbol: "folder"; onClicked: appController.openLogDirectory() }
        }
    }
}
