<script lang="ts">
  import { onMount } from "svelte";
  import Button from "../../lib/components/Button.svelte";
  import Dialog from "../../lib/components/Dialog.svelte";
  import GlassPanel from "../../lib/components/GlassPanel.svelte";
  import Icon from "../../lib/components/Icon.svelte";
  import IconButton from "../../lib/components/IconButton.svelte";
  import PageHeading from "../../lib/components/PageHeading.svelte";
  import SubtitleEntry from "../../lib/components/SubtitleEntry.svelte";
  import Toggle from "../../lib/components/Toggle.svelte";
  import { call } from "../../lib/core";
  import { readBool, setValue } from "../../lib/settings";
  import { core } from "../../lib/store.svelte";

  interface RecordItem {
    name: string;
    stem: string;
    size: number;
    size_label: string;
    modified: number;
    date_str: string;
    utterances: number;
    has_summary: boolean;
    is_current: boolean;
  }

  interface RecordDetail {
    name: string;
    stem: string;
    meta: Record<string, unknown>;
    entries: Array<{
      seq: number;
      start: number;
      end: number;
      language?: string;
      text: string;
      translation?: string;
    }>;
    summary: {
      content: string;
      mode: string;
      model: string;
      created_at: number;
      utterance_count: number;
    } | null;
    size_label: string;
    date_str: string;
  }

  let records = $state<RecordItem[]>([]);
  let loadingList = $state(false);
  let selectedName = $state<string | null>(null);
  let selectedDetail = $state<RecordDetail | null>(null);
  let loadingDetail = $state(false);

  // Summary generation state
  let summarizing = $state(false);
  let summaryMode = $state<"minutes" | "concise">("minutes");
  let summaryError = $state("");

  // Feedback states
  let copyFeedback = $state(false);
  let deleteDialogOpen = $state(false);
  let activeTab = $state<"summary" | "transcript">("summary");

  const appState = $derived(core.state?.app.state ?? "idle");

  async function refreshRecords() {
    loadingList = true;
    try {
      const res = (await call("records.list")) as RecordItem[];
      records = res || [];
      if (selectedName && !records.some((r) => r.name === selectedName)) {
        selectedName = null;
        selectedDetail = null;
      } else if (!selectedName && records.length > 0) {
        selectRecord(records[0].name);
      }
    } catch (err) {
      console.error("加载记录列表失败:", err);
    } finally {
      loadingList = false;
    }
  }

  async function selectRecord(name: string) {
    selectedName = name;
    loadingDetail = true;
    summaryError = "";
    try {
      const detail = (await call("records.get", { name })) as RecordDetail;
      selectedDetail = detail;
      if (detail.summary) {
        summaryMode = (detail.summary.mode as "minutes" | "concise") || "minutes";
        activeTab = "summary";
      } else {
        activeTab = detail.entries.length > 0 ? "transcript" : "summary";
      }
    } catch (err) {
      console.error("获取记录详情失败:", err);
      selectedDetail = null;
    } finally {
      loadingDetail = false;
    }
  }

  async function handleSummarize(force = false) {
    if (!selectedName || summarizing) return;
    summarizing = true;
    summaryError = "";
    try {
      const summary = (await call("records.summarize", {
        name: selectedName,
        mode: summaryMode,
        force,
      })) as RecordDetail["summary"];
      if (selectedDetail && summary) {
        selectedDetail.summary = summary;
      }
      activeTab = "summary";
      // Update has_summary tag in list
      const item = records.find((r) => r.name === selectedName);
      if (item) item.has_summary = true;
    } catch (err) {
      console.error("生成纪要失败:", err);
      summaryError = err instanceof Error ? err.message : String(err);
    } finally {
      summarizing = false;
    }
  }

  async function handleCopy() {
    if (!selectedDetail) return;
    let textToCopy = "";
    if (activeTab === "summary" && selectedDetail.summary?.content) {
      textToCopy = selectedDetail.summary.content;
    } else {
      textToCopy = selectedDetail.entries
        .map((e) => {
          const t = `[${Math.floor(e.start / 60)}:${Math.floor(e.start % 60).toString().padStart(2, "0")}]`;
          return `${t} ${e.text}${e.translation ? "\n      " + e.translation : ""}`;
        })
        .join("\n\n");
    }

    try {
      await navigator.clipboard.writeText(textToCopy);
      copyFeedback = true;
      setTimeout(() => (copyFeedback = false), 2000);
    } catch (err) {
      console.error("复制失败:", err);
    }
  }

  async function handleExport() {
    if (!selectedName) return;
    try {
      const res = (await call("records.export", { name: selectedName, format: "md" })) as {
        filename: string;
        content: string;
      };
      // Trigger download
      const blob = new Blob([res.content], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = res.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("导出记录失败:", err);
    }
  }

  async function confirmDelete() {
    if (!selectedName) return;
    try {
      await call("records.delete", { name: selectedName });
      deleteDialogOpen = false;
      await refreshRecords();
    } catch (err) {
      console.error("删除记录失败:", err);
    }
  }

  onMount(() => {
    refreshRecords();
  });
</script>

<div class="page-col">
  <PageHeading
    title="记录与纪要"
    subtitle="查看历史翻译会话，使用大模型一键生成智能会议纪要与行动项。"
  />

  <div class="layout">
    <!-- Left Column: Master List -->
    <div class="master lt-panel">
      <div class="master-head">
        <span class="master-title">历史记录 ({records.length})</span>
        <div class="master-actions">
          <IconButton
            icon="folder"
            label="打开记录文件夹"
            size={28}
            iconSize={15}
            onclick={() => void call("app.openRecordDirectory")}
          />
          <IconButton
            icon="refresh"
            label="刷新记录"
            size={28}
            iconSize={15}
            disabled={loadingList}
            onclick={refreshRecords}
          />
        </div>
      </div>

      <div class="master-record-toggle">
        <span class="toggle-label">启用会话保存</span>
        <Toggle
          checked={readBool("record.enabled", false)}
          label="启用会话保存"
          onchange={(v) => setValue("record.enabled", v)}
        />
      </div>
      <div class="record-list">
        {#if records.length === 0}
          <div class="empty-list">
            <Icon name="document" size={28} />
            <p class="empty-title">暂无保存的记录</p>
            <p class="empty-desc">
              在「通用」中开启保存翻译记录后，翻译结束时将在此自动生成记录文件。
            </p>
          </div>
        {:else}
          {#each records as record (record.name)}
            <div
              role="button"
              tabindex="0"
              class="record-card"
              class:selected={selectedName === record.name}
              class:current={record.is_current}
              onclick={() => selectRecord(record.name)}
              onkeydown={(e) => {
                if (e.key === "Enter" || e.key === " ") selectRecord(record.name);
              }}
            >
              <div class="card-top">
                <span class="card-date">{record.date_str}</span>
                {#if record.is_current}
                  <span class="badge live">正在录制</span>
                {:else if record.has_summary}
                  <span class="badge ai">
                    <Icon name="sparkles" size={11} /> 纪要已生成
                  </span>
                {/if}
              </div>
              <div class="card-meta">
                <span>{record.utterances} 句对话</span>
                <span>·</span>
                <span>{record.size_label}</span>
              </div>
            </div>
          {/each}
        {/if}
      </div>
    </div>

    <!-- Right Column: Detail View -->
    <div class="detail lt-panel">
      {#if !selectedDetail}
        <div class="detail-empty">
          <Icon name="document" size={40} />
          <p class="empty-prompt">请在左侧选择一条记录以查看详情</p>
        </div>
      {:else}
        <!-- Detail Header -->
        <div class="detail-head">
          <div class="detail-info">
            <h2 class="detail-title">{selectedDetail.date_str}</h2>
            <div class="detail-sub">
              <span>共 {selectedDetail.entries.length} 句对话</span>
              <span>·</span>
              <span>大小 {selectedDetail.size_label}</span>
            </div>
          </div>

          <div class="detail-tools">
            <Button
              variant="primary"
              icon="sparkles"
              disabled={summarizing || selectedDetail.entries.length === 0}
              onclick={() => handleSummarize(!!selectedDetail?.summary)}
            >
              {summarizing ? "正在生成…" : selectedDetail.summary ? "重新生成纪要" : "生成智能纪要"}
            </Button>

            <Button
              variant="raised"
              icon="copy"
              disabled={selectedDetail.entries.length === 0}
              onclick={handleCopy}
            >
              {copyFeedback ? "已复制！" : "复制"}
            </Button>

            <Button
              variant="quiet"
              icon="download"
              title="导出 Markdown 文件"
              onclick={handleExport}
            >
              导出
            </Button>

            <Button
              variant="quiet"
              icon="trash"
              title="删除记录"
              onclick={() => (deleteDialogOpen = true)}
            >
              删除
            </Button>
          </div>
        </div>

        <!-- Detail Tabs Navigation -->
        <div class="tab-bar">
          <button
            class="tab-btn"
            class:active={activeTab === "summary"}
            onclick={() => (activeTab = "summary")}
          >
            <Icon name="sparkles" size={14} />
            <span>智能会议纪要</span>
            {#if selectedDetail.summary}
              <span class="tab-dot"></span>
            {/if}
          </button>
          <button
            class="tab-btn"
            class:active={activeTab === "transcript"}
            onclick={() => (activeTab = "transcript")}
          >
            <Icon name="document" size={14} />
            <span>逐句对话记录 ({selectedDetail.entries.length})</span>
          </button>
        </div>

        <!-- Tab Content -->
        <div class="tab-content">
          {#if activeTab === "summary"}
            <!-- Mode switcher and summary content -->
            <div class="summary-wrapper">
              <div class="mode-bar">
                <span class="mode-label">纪要类型：</span>
                <div class="mode-toggles">
                  <button
                    class="mode-btn"
                    class:active={summaryMode === "minutes"}
                    disabled={summarizing}
                    onclick={() => {
                      summaryMode = "minutes";
                      if (selectedDetail?.summary && selectedDetail.summary.mode !== "minutes") {
                        handleSummarize(true);
                      }
                    }}
                  >
                    完整会议纪要
                  </button>
                  <button
                    class="mode-btn"
                    class:active={summaryMode === "concise"}
                    disabled={summarizing}
                    onclick={() => {
                      summaryMode = "concise";
                      if (selectedDetail?.summary && selectedDetail.summary.mode !== "concise") {
                        handleSummarize(true);
                      }
                    }}
                  >
                    极简速览
                  </button>
                </div>
                {#if selectedDetail.summary}
                  <span class="model-tag">
                    由 {selectedDetail.summary.model} 生成
                  </span>
                {/if}
              </div>

              {#if summarizing}
                <div class="generating-box">
                  <Icon name="sparkles" size={28} />
                  <p class="generating-text">正在调用大模型生成结构化会议纪要，请稍候…</p>
                  <p class="generating-hint">模型会提炼核心主题、讨论议题、重要结论及待办事项。</p>
                </div>
              {:else if summaryError}
                <div class="error-box">
                  <Icon name="close" size={20} />
                  <div class="error-text">
                    <p class="error-title">生成纪要失败</p>
                    <p class="error-desc">{summaryError}</p>
                  </div>
                  <Button variant="raised" onclick={() => handleSummarize(true)}>重试</Button>
                </div>
              {:else if selectedDetail.summary}
                <div class="markdown-body">
                  <pre class="content-text">{selectedDetail.summary.content}</pre>
                </div>
              {:else}
                <div class="no-summary-card lt-panel">
                  <Icon name="sparkles" size={32} />
                  <h3>尚未生成会议纪要</h3>
                  <p>
                    点击上方「生成智能纪要」按钮，利用配置的翻译大模型将本次对话整理为结构清晰的会议纪要与行动项。
                  </p>
                  <Button
                    variant="primary"
                    icon="sparkles"
                    disabled={selectedDetail.entries.length === 0}
                    onclick={() => handleSummarize(false)}
                  >
                    立即生成会议纪要
                  </Button>
                </div>
              {/if}
            </div>
          {:else}
            <!-- Transcript timeline -->
            <div class="timeline-wrapper">
              {#if selectedDetail.entries.length === 0}
                <p class="empty-timeline">此记录中没有捕获到有效语音。</p>
              {:else}
                {#each selectedDetail.entries as entry (entry.seq)}
                  <div class="utterance-row">
                    <span class="time-badge">
                      {Math.floor(entry.start / 60)}:{Math.floor(entry.start % 60).toString().padStart(2, "0")}
                    </span>
                    <div class="utterance-text">
                      <SubtitleEntry
                        original={entry.text}
                        translation={entry.translation || ""}
                        showOriginal={true}
                        textSize={15}
                      />
                    </div>
                  </div>
                {/each}
              {/if}
            </div>
          {/if}
        </div>
      {/if}
    </div>
  </div>
</div>

<!-- Delete Confirmation Dialog -->
<Dialog
  open={deleteDialogOpen}
  title="确认删除该条记录？"
  onclose={() => (deleteDialogOpen = false)}
>
  <p>删除后记录文件及已生成的会议纪要将从磁盘彻底移除，无法恢复。</p>
  {#snippet actions()}
    <Button variant="raised" onclick={() => (deleteDialogOpen = false)}>取消</Button>
    <Button variant="primary" onclick={confirmDelete}>确认删除</Button>
  {/snippet}
</Dialog>

<style>
  .page-col {
    display: flex;
    flex-direction: column;
    gap: 16px;
    height: 100%;
  }

  .layout {
    display: flex;
    gap: 14px;
    min-height: 480px;
    height: calc(100vh - 165px);
  }

  /* Master list styles */
  .master {
    width: 260px;
    flex: none;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .master-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    border-bottom: 1px solid var(--md-sys-color-outline-variant);
  }

  .master-title {
    font-size: 13px;
    font-weight: 600;
  }

  .master-actions {
    display: flex;
    gap: 4px;
  }

  .master-record-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 14px;
    background: var(--md-sys-color-surface-container);
    border-bottom: 1px solid var(--md-sys-color-outline-variant);
    font-size: 12px;
  }

  .toggle-label {
    color: var(--md-sys-color-on-surface-variant);
    font-weight: 500;
  }

  .record-list {
    overflow-y: auto;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .empty-list {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 32px 16px;
    text-align: center;
    color: var(--md-sys-color-on-surface-variant);
  }

  .empty-title {
    margin: 10px 0 4px;
    font-size: 13px;
    font-weight: 500;
  }

  .empty-desc {
    margin: 0;
    font-size: 11px;
    line-height: 1.4;
    color: var(--md-sys-color-outline);
  }

  .record-card {
    padding: 10px 12px;
    border-radius: var(--lt-radius-control);
    background: transparent;
    border: 1px solid transparent;
    cursor: pointer;
    transition:
      background-color var(--lt-fast) var(--lt-ease),
      border-color var(--lt-fast) var(--lt-ease);
  }

  .record-card:hover {
    background: var(--md-sys-color-surface-container-high);
  }

  .record-card.selected {
    background: var(--md-sys-color-surface-container-highest);
    border-color: var(--md-sys-color-outline-variant);
  }

  .card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
  }

  .card-date {
    font-size: 12px;
    font-weight: 500;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 10px;
    padding: 2px 6px;
    border-radius: var(--lt-radius-full);
  }

  .badge.live {
    background: color-mix(in oklab, var(--lt-success) 20%, transparent);
    color: var(--lt-success);
    font-weight: 600;
  }

  .badge.ai {
    background: color-mix(in oklab, var(--md-sys-color-primary) 18%, transparent);
    color: var(--md-sys-color-primary);
  }

  .card-meta {
    display: flex;
    gap: 6px;
    margin-top: 4px;
    font-size: 11px;
    color: var(--md-sys-color-on-surface-variant);
  }

  /* Detail view styles */
  .detail {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .detail-empty {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: var(--md-sys-color-on-surface-variant);
  }

  .empty-prompt {
    margin-top: 12px;
    font-size: 14px;
  }

  .detail-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 18px;
    border-bottom: 1px solid var(--md-sys-color-outline-variant);
    gap: 16px;
  }
  .detail-info {
    min-width: 0;
    flex: none;
    white-space: nowrap;
  }
  .detail-title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    white-space: nowrap;
  }
  .detail-sub {
    display: flex;
    gap: 6px;
    margin-top: 4px;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
    white-space: nowrap;
  }
  .detail-tools {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  /* Tab bar */
  .tab-bar {
    display: flex;
    padding: 0 16px;
    border-bottom: 1px solid var(--md-sys-color-outline-variant);
    gap: 8px;
  }

  .tab-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 10px 14px;
    border: none;
    background: transparent;
    font: inherit;
    font-size: 13px;
    color: var(--md-sys-color-on-surface-variant);
    cursor: pointer;
    position: relative;
    border-bottom: 2px solid transparent;
    transition: color var(--lt-fast) var(--lt-ease);
  }

  .tab-btn:hover {
    color: var(--md-sys-color-on-surface);
  }

  .tab-btn.active {
    color: var(--md-sys-color-primary);
    border-bottom-color: var(--md-sys-color-primary);
    font-weight: 600;
  }

  .tab-dot {
    width: 6px;
    height: 6px;
    border-radius: var(--lt-radius-full);
    background: var(--md-sys-color-primary);
  }

  /* Tab content */
  .tab-content {
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px;
    min-height: 0;
  }

  .summary-wrapper {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .mode-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 12px;
  }

  .mode-label {
    color: var(--md-sys-color-on-surface-variant);
  }

  .mode-toggles {
    display: flex;
    border-radius: var(--lt-radius-control);
    background: var(--md-sys-color-surface-container);
    border: 1px solid var(--md-sys-color-outline-variant);
    padding: 2px;
  }

  .mode-btn {
    border: none;
    background: transparent;
    padding: 4px 10px;
    border-radius: var(--lt-radius-sm);
    font: inherit;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
    cursor: pointer;
  }

  .mode-btn.active {
    background: var(--md-sys-color-surface-container-highest);
    color: var(--md-sys-color-on-surface);
    font-weight: 500;
  }

  .model-tag {
    margin-left: auto;
    color: var(--md-sys-color-outline);
  }

  .generating-box {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 24px;
    border-radius: var(--lt-radius-card);
    background: var(--md-sys-color-surface-container);
    color: var(--md-sys-color-primary);
    gap: 10px;
    text-align: center;
  }

  .generating-text {
    margin: 0;
    font-weight: 500;
    font-size: 14px;
  }

  .generating-hint {
    margin: 0;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
  }

  .error-box {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-radius: var(--lt-radius-control);
    background: var(--md-sys-color-error-container);
    color: var(--md-sys-color-on-error-container);
  }

  .error-text {
    flex: 1;
  }

  .error-title {
    margin: 0 0 2px;
    font-weight: 600;
    font-size: 13px;
  }

  .error-desc {
    margin: 0;
    font-size: 12px;
  }

  .markdown-body {
    border-radius: var(--lt-radius-card);
    background: var(--md-sys-color-surface-container);
    border: 1px solid var(--md-sys-color-outline-variant);
    padding: 18px 22px;
  }

  .content-text {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: inherit;
    font-size: 14px;
    line-height: 1.7;
    color: var(--md-sys-color-on-surface);
  }

  .no-summary-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 36px 24px;
    gap: 12px;
    border-radius: var(--lt-radius-card);
    background: var(--md-sys-color-surface-container);
    color: var(--md-sys-color-on-surface-variant);
  }

  .no-summary-card h3 {
    margin: 0;
    color: var(--md-sys-color-on-surface);
    font-size: 16px;
  }

  .no-summary-card p {
    margin: 0;
    max-width: 480px;
    font-size: 13px;
    line-height: 1.5;
  }

  /* Timeline */
  .timeline-wrapper {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .empty-timeline {
    text-align: center;
    padding: 40px;
    color: var(--md-sys-color-on-surface-variant);
  }

  .utterance-row {
    display: flex;
    gap: 14px;
    align-items: flex-start;
    padding: 8px 12px;
    border-radius: var(--lt-radius-control);
    background: var(--md-sys-color-surface-container);
  }

  .time-badge {
    font-size: 11px;
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    color: var(--md-sys-color-primary);
    background: var(--md-sys-color-surface-container-high);
    padding: 3px 6px;
    border-radius: var(--lt-radius-sm);
    flex: none;
    margin-top: 2px;
  }

  .utterance-text {
    flex: 1;
    min-width: 0;
  }
</style>
