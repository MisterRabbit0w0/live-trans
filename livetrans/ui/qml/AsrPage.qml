import QtQuick
import QtQuick.Layouts
ColumnLayout {
    property bool advanced: false
    id: page
    spacing: 24
    PageHeading { title: "语音识别"; subtitle: "选择本地模型或云端服务，将声音转换为文字。"; Layout.fillWidth: true }
    Panel {
        Layout.fillWidth: true
        ChoiceSetting {
            path: "asr.backend"; label: "识别方式"
            options: [{label: "本地识别", value: "local"}, {label: "云端识别 · OpenAI 兼容", value: "cloud"}]
        }
        ChoiceSetting {
            path: "asr.language"; label: "源语言"
            options: [{label: "自动检测", value: "auto"}, {label: "英语", value: "en"}, {label: "日语", value: "ja"}, {label: "韩语", value: "ko"}, {label: "中文", value: "zh"}, {label: "俄语", value: "ru"}, {label: "西班牙语", value: "es"}, {label: "法语", value: "fr"}, {label: "德语", value: "de"}]
        }
        ChoiceSetting {
            visible: preferences.draft.asr.backend === "local"
            path: "asr.model"; label: "本地模型"; editable: true
            options: [{label: "自动选择", value: "auto"}, {label: "large-v3-turbo", value: "large-v3-turbo"}, {label: "large-v3", value: "large-v3"}, {label: "medium", value: "medium"}, {label: "small", value: "small"}, {label: "base", value: "base"}]
            hint: "自动模式根据可用显存选择模型。首次使用会下载所选模型。"
        }
        TextSetting { visible: preferences.draft.asr.backend === "cloud"; path: "asr.cloud_base_url"; label: "服务地址"; hint: "支持 OpenAI 兼容的语音转写服务。" }
        TextSetting { visible: preferences.draft.asr.backend === "cloud"; path: "asr.cloud_api_key"; label: "API 密钥"; secret: true }
        TextSetting { visible: preferences.draft.asr.backend === "cloud"; path: "asr.cloud_model"; label: "云端模型" }
    }
    ActionButton { text: page.advanced ? "收起高级选项" : "高级选项"; symbol: "settings"; quiet: true; onClicked: page.advanced = !page.advanced }
    Panel {
        visible: page.advanced
        Layout.fillWidth: true
        ChoiceSetting {
            visible: preferences.draft.asr.backend === "local"
            path: "asr.device"; label: "计算设备"
            options: [{label: "自动", value: "auto"}, {label: "NVIDIA GPU · CUDA", value: "cuda"}, {label: "CPU", value: "cpu"}]
        }
        NumberSetting { path: "vad_silence_ms"; label: "切句停顿"; minimum: 250; maximum: 1000; step: 50; suffix: "ms"; hint: "数值越小，字幕出现越快，句子也可能更碎。" }
        NumberSetting { path: "vad_max_segment_s"; label: "最长句子"; minimum: 1; maximum: 30; step: 0.5; suffix: "秒" }
        NumberSetting { path: "vad_min_speech_ms"; label: "最短语音"; minimum: 50; maximum: 1000; step: 50; suffix: "ms"; hint: "短于此长度的语音片段将被忽略。" }
    }
}
