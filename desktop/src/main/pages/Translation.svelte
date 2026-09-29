<script lang="ts">
  import GlassPanel from "../../lib/components/GlassPanel.svelte";
  import PageHeading from "../../lib/components/PageHeading.svelte";
  import Select from "../../lib/components/Select.svelte";
  import TextField from "../../lib/components/TextField.svelte";
  import ToggleField from "../../lib/components/ToggleField.svelte";
  import { readString, setValue } from "../../lib/settings";
  import { core } from "../../lib/store.svelte";

  const targetLanguages = $derived(
    core.state?.settings.targetLanguages ?? [],
  );
</script>

<div class="page-col">
  <PageHeading title="翻译" subtitle="选择译文语言，配置翻译服务。" />

  <GlassPanel>
    <ToggleField
      path="translate.enabled"
      label="启用实时翻译"
      fallback={true}
      hint="开启后将识别语音自动翻译为目标语言；关闭后仅显示原文字幕并可保存原文记录，不调用大模型。"
    />
  </GlassPanel>

  <GlassPanel>
    <Select
      label="目标语言"
      path="translate.target_language"
      value={readString("translate.target_language")}
      options={targetLanguages}
      onchange={(v) => setValue("translate.target_language", v)}
    />
  </GlassPanel>

  <GlassPanel>
    <h2 class="section">翻译服务</h2>
    <TextField
      label="服务地址"
      path="translate.base_url"
      value={readString("translate.base_url")}
      hint="本地 Ollama 或任意 OpenAI 兼容服务，例如 http://localhost:11434/v1。"
      onchange={(v) => setValue("translate.base_url", v)}
    />
    <TextField
      label="API 密钥"
      path="translate.api_key"
      secret
      value={readString("translate.api_key")}
      hint="本地 Ollama 可保留默认值 ollama。"
      onchange={(v) => setValue("translate.api_key", v)}
    />
    <TextField
      label="模型"
      path="translate.model"
      value={readString("translate.model")}
      hint="填写服务提供的模型名称。"
      onchange={(v) => setValue("translate.model", v)}
    />
  </GlassPanel>
</div>

<style>
  .page-col {
    display: flex;
    flex-direction: column;
    gap: 24px;
  }
  .section {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }
</style>
