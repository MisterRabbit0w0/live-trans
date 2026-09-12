import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Layouts

Window {
    id: root
    objectName: "controlCenter"
    title: "LiveTrans"
    visible: false
    color: "transparent"
    flags: Qt.Window | Qt.WindowSystemMenuHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint
           | (windowControls.nativeFrame ? Qt.CustomizeWindowHint : Qt.FramelessWindowHint)
    width: 1040
    height: 720
    minimumWidth: Math.min(800, Screen.desktopAvailableWidth)
    minimumHeight: Math.min(540, Screen.desktopAvailableHeight)
    property int currentPage: 0
    property string validationPath: ""
    property var pages: ["概览", "声音来源", "语音识别", "翻译", "字幕外观", "通用"]
    property var symbols: ["overview", "audio", "mic", "translate", "subtitles", "settings"]
    onClosing: function(close) { close.accepted = false; root.hide(); }
    onCurrentPageChanged: {
        if (currentPage === 1) appController.refreshDevices();
        if (visible && Theme.motion) transition.restart();
    }
    Rectangle {
        anchors.fill: parent
        radius: windowControls.nativeFrame || root.visibility === Window.Maximized ? 0 : 16
        color: appearance.mainGlass ? (Theme.dark ? "#681b2029" : "#48f1f4f9") : Theme.canvas
        border.color: Theme.highContrast ? Theme.foreground : Theme.dark ? "#606c7d" : "#faffffff"
        border.width: windowControls.nativeFrame ? 0 : 1
    }
    // A single native move region preserves Windows drag and snap gestures.
    MouseArea {
        height: 52
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: windowButtons.left
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onPressed: function(mouse) {
            if (mouse.button === Qt.RightButton) windowControls.showSystemMenu();
            else root.startSystemMove();
        }
        onDoubleClicked: root.visibility === Window.Maximized ? root.showNormal() : root.showMaximized()
    }
    RowLayout {
        x: 22; y: 14
        spacing: 9
        Image { source: "../../assets/livetrans.svg"; sourceSize: Qt.size(28, 28); Layout.preferredWidth: 28; Layout.preferredHeight: 28 }
        AppText { text: "LiveTrans"; font.pixelSize: 15; font.weight: Font.DemiBold }
    }
    AppText { x: 248; y: 18; text: root.pages[root.currentPage]; color: Theme.secondary; font.pixelSize: 12 }
    Row {
        id: windowButtons
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 8
        spacing: 2
        Repeater {
            model: [
                {symbol: "minus", label: "最小化"},
                {symbol: "maximize", label: "最大化或还原"},
                {symbol: "close", label: "隐藏到托盘"}
            ]
            delegate: ToolButton {
                required property var modelData
                required property int index
                width: 38; height: 34
                Accessible.name: modelData.label
                contentItem: Icon { name: modelData.symbol; color: Theme.secondary; sourceSize: Qt.size(16, 16) }
                background: Rectangle { radius: 9; color: parent.hovered ? Theme.field : "transparent" }
                onClicked: {
                    if (index === 0) root.showMinimized();
                    else if (index === 1) root.visibility === Window.Maximized ? root.showNormal() : root.showMaximized();
                    else root.hide();
                }
                ToolTip.text: modelData.label
                ToolTip.visible: hovered
                ToolTip.delay: 700
            }
        }
    }
    Rectangle {
        id: sidebar
        x: 12; y: 64; width: 204
        height: parent.height - y - 12
        radius: 16
        color: Theme.dark ? "#382c3544" : "#55ffffff"
        border.color: Theme.dark ? "#34404f" : "#80ffffff"
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 6
            Repeater {
                model: root.pages
                delegate: Button {
                    id: nav
                    required property string modelData
                    required property int index
                    objectName: "nav" + index
                    Layout.fillWidth: true
                    implicitHeight: 43
                    padding: 12
                    Accessible.name: modelData
                    onClicked: root.currentPage = index
                    contentItem: RowLayout {
                        spacing: 12
                        Icon { name: root.symbols[nav.index]; color: root.currentPage === nav.index ? Theme.accent : Theme.secondary; Layout.preferredWidth: 18; Layout.preferredHeight: 18 }
                        AppText {
                            text: nav.modelData
                            color: root.currentPage === nav.index ? Theme.accent : Theme.foreground
                            font.pixelSize: 13; font.weight: root.currentPage === nav.index ? Font.DemiBold : Font.Normal
                            Layout.fillWidth: true
                        }
                    }
                    background: Item {
                        Rectangle {
                            anchors.fill: parent
                            radius: 11
                            // Hover changes only opacity; color animation is
                            // reserved for transitions between opaque palette colors.
                            color: root.currentPage === nav.index ? Theme.accentSoft : Theme.field
                            opacity: root.currentPage === nav.index || nav.hovered ? 1 : 0
                            Behavior on color { ColorAnimation { duration: root.visible ? Theme.fast : 0 } }
                            Behavior on opacity { NumberAnimation { duration: root.visible ? Theme.fast : 0 } }
                        }
                        Rectangle {
                            anchors.fill: parent
                            radius: 11
                            color: "transparent"
                            border.width: nav.activeFocus ? 2 : 0
                            border.color: Theme.accent
                        }
                    }
                }
            }
            Item { Layout.fillHeight: true }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.line; Layout.leftMargin: 10; Layout.rightMargin: 10 }
            RowLayout {
                Layout.margins: 10
                spacing: 8
                Rectangle { width: 6; height: 6; radius: 3; color: appController.state === "running" ? Theme.success : Theme.muted }
                AppText {
                    text: ({"running": "正在翻译", "paused": "已暂停", "starting": "准备中", "stopping": "停止中", "idle": "尚未开始", "error": "需要检查"})[appController.state]
                    color: Theme.secondary; font.pixelSize: 11; Layout.fillWidth: true
                }
            }
        }
    }
    ColumnLayout {
        anchors.top: parent.top; anchors.topMargin: 65
        anchors.left: sidebar.right; anchors.leftMargin: 28
        anchors.right: parent.right; anchors.rightMargin: 28
        anchors.bottom: footer.top; anchors.bottomMargin: 12
        spacing: 12
        Rectangle {
            visible: appController.notice !== ""
            Layout.fillWidth: true
            implicitHeight: noticeRow.implicitHeight + 20
            radius: 12
            color: appController.noticeIsError ? (Theme.dark ? "#482d33" : "#fbeaec") : Theme.accentSoft
            RowLayout {
                id: noticeRow
                anchors.fill: parent; anchors.margins: 10
                AppText { text: appController.notice; font.pixelSize: 12; color: appController.noticeIsError ? Theme.error : Theme.foreground; Layout.fillWidth: true }
                ActionButton { text: "关闭"; quiet: true; implicitHeight: 28; onClicked: appController.dismissNotice() }
            }
        }
        ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            contentHeight: pageLoader.height
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded
            Loader {
                id: pageLoader
                width: scroll.availableWidth
                height: item ? item.implicitHeight + 8 : 0
                source: ["OverviewPage.qml", "AudioPage.qml", "AsrPage.qml", "TranslationPage.qml", "SubtitlePage.qml", "GeneralPage.qml"][root.currentPage]
                onLoaded: {
                    scroll.contentItem.contentY = 0;
                    if (root.currentPage === 2 && (root.validationPath.indexOf("vad_") === 0 || root.validationPath === "asr.device")) item.advanced = true;
                    root.validationPath = "";
                }
            }
        }
    }
    NumberAnimation { id: transition; target: pageLoader; property: "opacity"; from: 0.35; to: 1; duration: Theme.duration; easing.type: Easing.OutCubic }
    Connections { target: pageLoader.item; ignoreUnknownSignals: true; function onNavigate(index) { root.currentPage = index; } }
    Rectangle {
        id: footer
        anchors.left: sidebar.right; anchors.leftMargin: 28
        anchors.right: parent.right; anchors.rightMargin: 28
        anchors.bottom: parent.bottom; anchors.bottomMargin: 12
        height: 58
        radius: 14
        color: Theme.dark ? "#cc222a36" : "#e8ffffff"
        border.color: Theme.line
        RowLayout {
            anchors.fill: parent; anchors.margins: 10
            spacing: 10
            Icon { name: preferences.dirty ? "settings" : "check"; color: preferences.dirty ? Theme.accent : Theme.muted; Layout.leftMargin: 4; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
            AppText { text: preferences.dirty ? "有未应用的修改" : "设置已同步"; color: Theme.secondary; font.pixelSize: 12; Layout.fillWidth: true }
            ActionButton { text: "还原修改"; enabled: preferences.dirty && !appController.busy; quiet: true; onClicked: appController.discardSettings() }
            ActionButton { objectName: "applySettings"; text: "应用设置"; primary: true; enabled: preferences.dirty && !appController.busy; onClicked: appController.applySettings() }
        }
    }
    Repeater {
        model: [Qt.LeftEdge, Qt.RightEdge, Qt.TopEdge, Qt.BottomEdge, Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge, Qt.RightEdge | Qt.BottomEdge]
        delegate: MouseArea {
            required property int modelData
            property bool horizontal: Boolean(modelData & (Qt.LeftEdge | Qt.RightEdge))
            property bool vertical: Boolean(modelData & (Qt.TopEdge | Qt.BottomEdge))
            enabled: root.visibility !== Window.Maximized
            width: horizontal ? 7 : root.width - 14
            height: vertical ? 7 : root.height - 14
            x: modelData & Qt.RightEdge ? root.width - width : horizontal ? 0 : 7
            y: modelData & Qt.BottomEdge ? root.height - height : vertical ? 0 : 7
            cursorShape: horizontal && vertical ? ((modelData === (Qt.LeftEdge | Qt.TopEdge) || modelData === (Qt.RightEdge | Qt.BottomEdge)) ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor) : horizontal ? Qt.SizeHorCursor : Qt.SizeVerCursor
            onPressed: root.startSystemResize(modelData)
        }
    }
    Dialog {
        id: quitDialog
        title: "还有未应用的修改"
        modal: true
        anchors.centerIn: parent
        width: 360
        padding: 24
        background: Rectangle { color: Theme.surface; radius: 18; border.color: Theme.line }
        header: AppText { text: quitDialog.title; padding: 24; font.pixelSize: 18; font.weight: Font.DemiBold }
        contentItem: ColumnLayout {
            spacing: 24
            AppText { text: "退出将丢弃设置草稿。已应用的配置会保留。"; Layout.fillWidth: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                spacing: 8
                ActionButton { text: "返回设置"; onClicked: quitDialog.close() }
                ActionButton { text: "丢弃并退出"; primary: true; onClicked: { quitDialog.close(); appController.confirmQuit(); } }
            }
        }
    }
    Connections { target: appController; function onQuitConfirmationRequested() { quitDialog.open(); } }
    Connections {
        target: appController
        function onValidationFailed(path) {
            root.validationPath = path;
            const index = path.indexOf("audio_") === 0 ? 1 : path.indexOf("asr.") === 0 || path.indexOf("vad_") === 0 ? 2 : path.indexOf("translate.") === 0 ? 3 : path.indexOf("subtitle.") === 0 ? 4 : 5;
            root.currentPage = index;
            if (index === 2 && (path.indexOf("vad_") === 0 || path === "asr.device") && pageLoader.item) pageLoader.item.advanced = true;
        }
    }
    Shortcut { sequence: "Ctrl+,"; onActivated: root.currentPage = 5 }
    Shortcut { sequence: "Ctrl+Return"; onActivated: appController.applySettings() }
    Shortcut { sequence: "Ctrl+Q"; onActivated: appController.requestQuit() }
    Shortcut { sequence: "Alt+Space"; onActivated: windowControls.showSystemMenu() }
}
