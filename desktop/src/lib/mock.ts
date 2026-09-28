/**
 * Browser stand-in for the Python core, used for development and visual QA
 * when the page runs outside Tauri. Same surface as core.ts.
 */
import type {
  CoreEvent,
  CoreState,
  Snapshot,
  SubtitleRow,
  SystemAppearance,
} from "./core";
import fixture from "./fixtures/snapshot.json";

type Listener<T> = (value: T) => void;

const stateListeners = new Set<Listener<CoreState>>();
const subtitleListeners = new Set<Listener<SubtitleRow[]>>();
const eventListeners = new Set<Listener<CoreEvent>>();
const exitListeners = new Set<Listener<number | null>>();
const appearanceListeners = new Set<Listener<SystemAppearance>>();

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const params = new URLSearchParams(window.location.search);

const state: CoreState = clone(fixture.state) as unknown as CoreState;
const subtitles: SubtitleRow[] = clone(fixture.subtitles);
let subtitleSeq = 0;
let subtitleTimer: ReturnType<typeof setInterval> | null = null;

const SAMPLES: Array<[string, string]> = [
  ["The next session starts in five minutes.", "下一场将在五分钟后开始。"],
  ["Please remember to bring your laptop.", "请记得带上笔记本电脑。"],
  ["会場の受付は2階です。", "The reception is on the second floor."],
  ["We will review the release plan tomorrow.", "明天我们将评审发布计划。"],
];

if (!state.app.processes || state.app.processes.length === 0) {
  state.app.processes = [
    { label: "cloudmusic.exe · 发声中", value: "cloudmusic.exe" },
    { label: "QQ.exe", value: "QQ.exe" },
    { label: "chrome.exe", value: "chrome.exe" },
    { label: "steam.exe", value: "steam.exe" },
  ];
}
// ---- scenario query parameters (visual QA) -------------------------------
if (params.get("theme") === "light" || params.get("theme") === "dark") {
  state.app.committed.ui.theme = params.get("theme")!;
  (state.settings.draft.ui as Record<string, unknown>).theme =
    state.app.committed.ui.theme;
}
if (params.get("accent")) {
  state.app.committed.ui.accent = params.get("accent")!;
  (state.settings.draft.ui as Record<string, unknown>).accent =
    state.app.committed.ui.accent;
}
if (params.get("notice")) {
  state.app.notice =
    params.get("notice") === "error"
      ? "翻译服务连接失败，请检查服务地址。"
      : "模型文件夹已更新。";
  state.app.noticeIsError = params.get("notice") === "error";
}
if (params.get("dirty")) {
  (state.settings.draft.subtitle as Record<string, unknown>).font_size = 24;
  state.settings.dirty = true;
}
if (params.get("err")) {
  state.settings.errors[params.get("err")!] = "输入无效，请检查后再应用。";
  state.settings.dirty = true;
}
const seedSubs = Number(params.get("subs") ?? "0");
for (let i = 0; i < seedSubs; i++) {
  const [original, translation] = SAMPLES[i % SAMPLES.length];
  subtitles.push({ id: ++subtitleSeq, original, translation, language: "en" });
}
const startRunning = params.get("running") === "1";

function emitState() {
  const snapshot = clone(state);
  for (const cb of stateListeners) cb(snapshot);
}

function emitSubtitles() {
  const rows = clone(subtitles);
  for (const cb of subtitleListeners) cb(rows);
}

function emitEvent(name: string, payload: Record<string, unknown> = {}) {
  const event: CoreEvent = { name, payload };
  for (const cb of eventListeners) cb(event);
}

function setNested(path: string, value: unknown) {
  const keys = path.split(".");
  let node = state.settings.draft as Record<string, unknown>;
  for (const key of keys.slice(0, -1)) {
    const next = node[key];
    if (next === null || typeof next !== "object") return;
    node = next as Record<string, unknown>;
  }
  node[keys[keys.length - 1]] = value;
}

function stripSecrets(source: Record<string, unknown>) {
  const copy = clone(source);
  delete (copy.asr as Record<string, unknown>).cloud_api_key;
  delete (copy.translate as Record<string, unknown>).api_key;
  return copy;
}

function recomputeDirty() {
  state.settings.dirty =
    JSON.stringify(stripSecrets(state.settings.draft)) !==
    JSON.stringify(state.app.committed);
}

function pushSubtitle() {
  const [original, translation] = SAMPLES[subtitleSeq % SAMPLES.length];
  subtitles.push({
    id: ++subtitleSeq,
    original,
    translation,
    language: "en",
  });
  while (subtitles.length > 30) subtitles.shift();
  emitSubtitles();
}

function startTimer() {
  subtitleTimer ??= setInterval(pushSubtitle, 2500);
}

function stopTimer() {
  if (subtitleTimer) {
    clearInterval(subtitleTimer);
    subtitleTimer = null;
  }
}

const STATUS: Record<string, [string, string]> = {
  idle: ["尚未开始", "确认声音来源和模型后，点击开始翻译。"],
  starting: ["准备中", "正在初始化识别与翻译管线。"],
  running: ["正在翻译", "正在捕获音频并生成双语字幕。"],
  paused: ["已暂停", "翻译已暂停，字幕保留在悬浮窗中。"],
  stopping: ["停止中", "正在停止识别与翻译。"],
  error: ["需要检查", "发生错误，请查看日志或调整设置后重试。"],
};

function setRuntime(next: CoreState["app"]["state"]) {
  state.app.state = next;
  const [title, detail] = STATUS[next];
  state.app.statusTitle = title;
  state.app.statusDetail = detail;
  emitState();
}

function refreshModels() {
  state.models.state = "loading";
  state.models.busy = true;
  emitState();
  setTimeout(() => {
    state.models.state = "idle";
    state.models.busy = false;
    state.models.directory = "C:\\Users\\demo\\LiveTrans\\runtime\\models";
    state.models.writable = true;
    state.models.recommended = "large-v3-turbo";
    state.models.autoModel = "large-v3-turbo";
    state.models.installed = [
      { name: "large-v3-turbo", size: "1.6 GB" },
      { name: "small", size: "466 MB" },
    ];
    state.models.installedNames = state.models.installed.map((m) => m.name);
    emitState();
  }, 600);
}

function downloadModel(name: string) {
  state.models.state = "downloading";
  state.models.busy = true;
  state.models.target = name;
  state.models.progress = -1;
  state.models.progressText = "连接中…";
  emitState();
  let tick = 0;
  const timer = setInterval(() => {
    tick += 1;
    state.models.progress = Math.min(1, tick * 0.12);
    state.models.progressText = `${Math.round(state.models.progress * 100)}%`;
    emitState();
    if (state.models.progress >= 1) {
      clearInterval(timer);
      state.models.state = "idle";
      state.models.busy = false;
      state.models.progress = -1;
      state.models.progressText = "";
      if (!state.models.installedNames.includes(name)) {
        state.models.installed.push({ name, size: "1.5 GB" });
        state.models.installedNames.push(name);
      }
      emitState();
    }
  }, 300);
  const cancel = () => clearInterval(timer);
  downloadCanceller = cancel;
}

let downloadCanceller: (() => void) | null = null;

const METHODS: Record<
  string,
  (params: Record<string, unknown>) => unknown
> = {
  "app.snapshot": () => ({ state: clone(state), subtitles: clone(subtitles) }),
  "app.startup": () => null,
  "app.start": () => null,
  "app.togglePause": () => {
    const s = state.app.state;
    if (s === "idle" || s === "error") {
      setRuntime("starting");
      setTimeout(() => {
        setRuntime("running");
        startTimer();
      }, 600);
    } else if (s === "running") {
      setRuntime("paused");
    } else if (s === "paused") {
      setRuntime("running");
      startTimer();
    }
    return null;
  },
  "app.stop": () => {
    if (state.app.state === "idle") return null;
    setRuntime("stopping");
    setTimeout(() => {
      stopTimer();
      setRuntime("idle");
    }, 600);
    return null;
  },
  "app.toggleSubtitles": () => {
    state.app.subtitleVisible = !state.app.subtitleVisible;
    emitState();
    return null;
  },
  "app.applySettings": () => {
    state.app.committed = stripSecrets(
      state.settings.draft,
    ) as unknown as CoreState["app"]["committed"];
    state.settings.dirty = false;
    emitState();
    return null;
  },
  "app.discardSettings": () => {
    const committed = clone(state.app.committed);
    (committed.asr as Record<string, unknown>).cloud_api_key =
      (state.settings.draft.asr as Record<string, unknown>).cloud_api_key ??
      "";
    (committed.translate as Record<string, unknown>).api_key =
      (state.settings.draft.translate as Record<string, unknown>).api_key ??
      "ollama";
    state.settings.draft = committed as unknown as Record<string, unknown>;
    state.settings.errors = {};
    state.settings.dirty = false;
    emitState();
    return null;
  },
  "app.adjustFont": (p) => {
    const delta = Number(p.delta) || 0;
    const sub = state.app.committed.subtitle;
    sub.font_size = Math.min(48, Math.max(10, sub.font_size + delta));
    emitState();
    return null;
  },
  "app.dismissNotice": () => {
    state.app.notice = "";
    emitState();
    return null;
  },
  "app.refreshDevices": () => {
    state.app.refreshing = true;
    emitState();
    setTimeout(() => {
      state.app.refreshing = false;
      emitState();
    }, 800);
    return null;
  },
  "app.openLogDirectory": () => null,
  "app.openRecordDirectory": () => null,
  "app.requestQuit": () => {
    if (state.settings.dirty) emitEvent("quitConfirmationRequested");
    return null;
  },
  "app.confirmQuit": () => null,
  "app.shutdown": () => null,
  "app.showControlCenter": () => null,
  "settings.set": (p) => {
    setNested(String(p.path), p.value);
    recomputeDirty();
    emitState();
    return null;
  },
  "models.refresh": () => {
    refreshModels();
    return null;
  },
  "models.download": (p) => {
    downloadModel(String(p.name));
    return null;
  },
  "models.remove": (p) => {
    const name = String(p.name);
    state.models.installed = state.models.installed.filter(
      (m) => m.name !== name,
    );
    state.models.installedNames = state.models.installedNames.filter(
      (n) => n !== name,
    );
    emitState();
    return null;
  },
  "models.cancel": () => {
    downloadCanceller?.();
    state.models.state = "idle";
    state.models.busy = false;
    emitState();
    return null;
  },
  "models.openDirectory": () => null,
  "records.list": () => [
    {
      name: "20260928-223000.jsonl",
      stem: "20260928-223000",
      size: 4200,
      size_label: "4.2 KB",
      modified: Date.now() / 1000 - 600,
      date_str: "2026-09-28 22:30:00",
      utterances: 4,
      has_summary: true,
      is_current: false,
    },
    {
      name: "20260928-211500.jsonl",
      stem: "20260928-211500",
      size: 12800,
      size_label: "12.8 KB",
      modified: Date.now() / 1000 - 5400,
      date_str: "2026-09-28 21:15:00",
      utterances: 12,
      has_summary: false,
      is_current: false,
    },
  ],
  "records.get": (p) => {
    const name = String(p.name || "");
    const hasSum = name.includes("223000");
    return {
      name: name || "20260928-223000.jsonl",
      stem: "20260928-223000",
      meta: { source: "system", created: 1727500000 },
      size_label: "4.2 KB",
      date_str: "2026-09-28 22:30:00",
      entries: [
        {
          seq: 1,
          start: 2.5,
          end: 6.8,
          text: "The next session starts in five minutes.",
          translation: "下一场将在五分钟后开始。",
        },
        {
          seq: 2,
          start: 8.0,
          end: 12.4,
          text: "Please remember to bring your laptop.",
          translation: "请记得带上笔记本电脑。",
        },
        {
          seq: 3,
          start: 14.1,
          end: 18.9,
          text: "会場の受付は2階です。",
          translation: "The reception is on the second floor.",
        },
        {
          seq: 4,
          start: 20.2,
          end: 24.5,
          text: "We will review the release plan tomorrow.",
          translation: "明天我们将评审发布计划。",
        },
      ],
      summary: hasSum
        ? {
            content:
              "### 📌 主题与核心主旨\n本次会议主要就后续会议日程安排、参会注意事项及明天即将进行的发布计划评审进行了同步确认。\n\n### 📝 重点内容与讨论议题\n- **[日程与地点安排]**：下一场分会议将于五分钟后准时开始，参会接待处设立于大楼二层。\n- **[参会准备]**：请所有相关研发与产品团队成员务必携带个人笔记本电脑参会。\n- **[发布计划推进]**：团队将于明天正式组织版本上线与发布计划的整体评审。\n\n### 💡 关键结论与达成共识\n- 确认了后续议程的时间节点与物理场地。\n- 发布评审定于明日开展，各模块需在今晚前锁定代码状态。\n\n### ✅ 待办事项与行动项 (Action Items)\n- [ ] **[参会人员]** 带齐个人设备准时进入下一场会议\n- [ ] **[项目团队]** 准备明日发布计划评审材料",
            mode: "minutes",
            model: "qwen2.5:7b-instruct",
            created_at: Date.now() / 1000 - 300,
            utterance_count: 4,
          }
        : null,
    };
  },
  "records.delete": () => true,
  "records.summarize": (p) => ({
    content:
      p.mode === "concise"
        ? "本次会议确认了下场会议在五分钟后开始，接待处位于二层，并明确明日将举行发布计划评审。"
        : "### 📌 主题与核心主旨\n本次会议主要就后续会议日程安排、参会注意事项及明天即将进行的发布计划评审进行了同步确认。\n\n### 📝 重点内容与讨论议题\n- **[日程与地点安排]**：下一场分会议将于五分钟后准时开始，参会接待处设立于大楼二层。\n- **[参会准备]**：请所有相关研发与产品团队成员务必携带个人笔记本电脑参会。\n- **[发布计划推进]**：团队将于明天正式组织版本上线与发布计划的整体评审。\n\n### 💡 关键结论与达成共识\n- 确认了后续议程的时间节点与物理场地。\n- 发布评审定于明日开展，各模块需在今晚前锁定代码状态。\n\n### ✅ 待办事项与行动项 (Action Items)\n- [ ] **[参会人员]** 带齐个人设备准时进入下一场会议\n- [ ] **[项目团队]** 准备明日发布计划评审材料",
    mode: p.mode || "minutes",
    model: "qwen2.5:7b-instruct",
    created_at: Date.now() / 1000,
    utterance_count: 4,
  }),
  "records.export": (p) => ({
    filename: `${p.name || "record"}.md`,
    content: "# LiveTrans 会议记录导出\n\n- 日期：2026-09-28\n\n## 会议纪要\n...",
  }),
};

export function call<T = null>(
  method: string,
  params?: Record<string, unknown>,
): Promise<T> {
  const handler = METHODS[method];
  if (!handler) return Promise.reject(new Error(`Unknown method ${method}`));
  try {
    return Promise.resolve(handler(params ?? {}) as T);
  } catch (error) {
    return Promise.reject(error instanceof Error ? error : new Error(String(error)));
  }
}

export function restartCore(): Promise<void> {
  return Promise.resolve();
}

export function setMaterial(
  _window: string,
  _enabled: boolean,
  _dark: boolean,
): Promise<boolean> {
  return Promise.resolve(false);
}

export function systemAppearance(): Promise<SystemAppearance> {
  return Promise.resolve({
    accent: "#1767db",
    transparency: params.get("material") !== "solid",
  });
}

function listen<T>(
  set: Set<Listener<T>>,
  cb: Listener<T>,
): Promise<() => void> {
  set.add(cb);
  return Promise.resolve(() => set.delete(cb));
}

export function onState(cb: Listener<CoreState>) {
  return listen(stateListeners, cb);
}
export function onSubtitles(cb: Listener<SubtitleRow[]>) {
  return listen(subtitleListeners, cb);
}
export function onEvent(cb: Listener<CoreEvent>) {
  return listen(eventListeners, cb);
}
export function onExited(cb: Listener<number | null>) {
  return listen(exitListeners, cb);
}
export function onSystemAppearance(cb: Listener<SystemAppearance>) {
  return listen(appearanceListeners, cb);
}

if (startRunning) {
  state.app.state = "running";
  state.app.subtitleVisible = true;
  const [title, detail] = STATUS.running;
  state.app.statusTitle = title;
  state.app.statusDetail = detail;
  startTimer();
}
