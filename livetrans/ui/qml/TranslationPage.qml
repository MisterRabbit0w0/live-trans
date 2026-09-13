import QtQuick
import QtQuick.Layouts
ColumnLayout {
    spacing: 24
    PageHeading { title: "翻译"; subtitle: "选择译文语言，配置翻译服务。"; Layout.fillWidth: true }
    Panel {
        Layout.fillWidth: true
        ChoiceSetting { path: "translate.target_language"; label: "目标语言"; options: preferences.targetLanguages }
    }
    Panel {
        Layout.fillWidth: true
        AppText { text: "翻译服务"; font.pixelSize: 16; font.weight: Font.DemiBold; Layout.fillWidth: true }
        TextSetting { path: "translate.base_url"; label: "服务地址"; hint: "本地 Ollama 或任意 OpenAI 兼容服务，例如 http://localhost:11434/v1。" }
        TextSetting { path: "translate.api_key"; label: "API 密钥"; secret: true; hint: "本地 Ollama 可保留默认值 ollama。" }
        TextSetting { path: "translate.model"; label: "模型"; hint: "填写服务提供的模型名称。" }
    }
}
