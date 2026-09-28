import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
// Explicit model management. Models live in the runtime environment below;
// recognition never downloads on its own.
Panel {
    id: root
    readonly property string runtime: String(preferences.draft.asr.runtime).trim()
    readonly property string selected: String(preferences.draft.asr.model).trim()
    // "auto" resolves to the best installed model, so offer the recommended one.
    readonly property string wanted: selected === "auto" ? models.recommended : selected
    readonly property bool ready: selected === "auto" ? models.autoModel !== "" : models.isInstalled(selected)
    Layout.fillWidth: true
    gap: 14
    Component.onCompleted: models.refresh(runtime)
    onRuntimeChanged: refreshTimer.restart()
    Timer { id: refreshTimer; interval: 600; onTriggered: models.refresh(root.runtime) }

    RowLayout {
        Layout.fillWidth: true
        spacing: 12
        ColumnLayout {
            spacing: 4
            Layout.fillWidth: true
            AppText { text: "已下载的模型"; font.weight: Font.Medium; Layout.fillWidth: true }
            AppText {
                objectName: "modelDirectory"
                text: models.directory ? "保存在 " + models.directory : "正在读取运行环境…"
                color: Theme.secondary; font.pixelSize: 12
                elide: Text.ElideMiddle; Layout.fillWidth: true
            }
        }
        ActionButton {
            text: "打开文件夹"; symbol: "folder"; quiet: true
            enabled: models.directory !== ""
            onClicked: models.openDirectory()
        }
        ActionButton {
            objectName: "refreshModels"
            text: "刷新"; symbol: "refresh"; quiet: true
            enabled: !models.busy
            onClicked: models.refresh(root.runtime)
        }
    }

    Repeater {
        model: models.installed
        delegate: RowLayout {
            required property var modelData
            Layout.fillWidth: true
            spacing: 12
            Icon { name: "check"; color: Theme.success; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
            AppText { text: modelData.name; Layout.fillWidth: true; elide: Text.ElideRight }
            AppText { text: modelData.size; color: Theme.secondary; font.pixelSize: 12 }
            ActionButton {
                text: "删除"; symbol: "close"; quiet: true
                enabled: !models.busy
                Accessible.name: "删除模型 " + modelData.name
                onClicked: models.remove(root.runtime, modelData.name)
            }
        }
    }
    AppText {
        visible: models.directory !== "" && models.installed.length === 0
        text: "此运行环境中还没有模型。"
        color: Theme.secondary; font.pixelSize: 12; Layout.fillWidth: true
    }

    ColumnLayout {
        visible: models.state === "downloading"
        Layout.fillWidth: true
        spacing: 6
        AppText { text: "正在下载 " + models.target + "  " + models.progressText; font.pixelSize: 12; Layout.fillWidth: true }
        ProgressBar {
            objectName: "modelProgress"
            Layout.fillWidth: true
            from: 0; to: 1
            value: Math.max(0, models.progress)
            indeterminate: models.progress < 0
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 12
        AppText {
            objectName: "modelStatus"
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            font.pixelSize: 12
            color: models.error || (!root.ready && models.directory && !models.busy) ? Theme.error : Theme.secondary
            text: models.error ? models.error
                : !models.writable ? "该目录不可写，请改用可写的运行环境。"
                : root.ready ? (root.selected === "auto" ? "自动模式将使用 " + models.autoModel + "。" : "所选模型已就绪。")
                : root.wanted ? "所选模型 " + root.wanted + " 尚未下载，开始翻译前需要先下载。"
                : ""
        }
        ActionButton {
            objectName: "downloadModel"
            visible: models.state !== "downloading"
            primary: !root.ready
            text: "下载 " + root.wanted
            symbol: "arrow"
            enabled: !models.busy && root.wanted !== "" && models.writable && !models.isInstalled(root.wanted)
            onClicked: models.download(root.runtime, root.wanted)
        }
        ActionButton {
            visible: models.state === "downloading"
            text: "取消下载"; symbol: "stop"
            onClicked: models.cancel()
        }
    }
}
