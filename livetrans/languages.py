"""Shared translation choices and exact ASR language-code lookup."""

TARGET_LANGUAGES = (
    ("中文（简体）", "中文", "zh"), ("中文（繁体）", "繁体中文", "zh"),
    ("英语", "英语", "en"), ("日语", "日语", "ja"), ("韩语", "韩语", "ko"),
    ("法语", "法语", "fr"), ("德语", "德语", "de"), ("西班牙语", "西班牙语", "es"),
    ("葡萄牙语", "葡萄牙语", "pt"), ("俄语", "俄语", "ru"), ("意大利语", "意大利语", "it"),
    ("阿拉伯语", "阿拉伯语", "ar"), ("印地语", "印地语", "hi"), ("泰语", "泰语", "th"),
    ("越南语", "越南语", "vi"), ("印度尼西亚语", "印度尼西亚语", "id"),
    ("土耳其语", "土耳其语", "tr"), ("荷兰语", "荷兰语", "nl"), ("波兰语", "波兰语", "pl"),
)

_LANGUAGE_CODES = {name.casefold(): code for label, value, code in TARGET_LANGUAGES
                   for name in (label, value, code)}
# Preserve the English names accepted by older JSON configurations. Custom
# targets must go through translation instead of being guessed by first letter.
_LANGUAGE_CODES.update({"english": "en", "chinese": "zh", "简体中文": "zh"})


def target_lang_code(target_language: str) -> str:
    return _LANGUAGE_CODES.get(target_language.strip().casefold(), "")
