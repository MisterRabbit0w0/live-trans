"""验证翻译：把示例文本翻译成中文（需要 Ollama 运行中，或改用云端配置）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from livetrans.config import AppConfig
from livetrans.pipeline import build_translator

cfg = AppConfig.load()
print(f"翻译端点: {cfg.translate.base_url}  模型: {cfg.translate.model}")
tr = build_translator(cfg)
for text, lang in [
    ("Alright chat, we're gonna try this boss one more time, wish me luck.", "en"),
    ("えっとね、今日はみんなとゲームやろうかなって思ってます！", "ja"),
]:
    print(f"\n原文[{lang}]: {text}")
    print(f"译文: {tr.translate(text, source_language=lang)}")
