# 界面与发行包验收

当前版本的最终桌面验收尚未完成；桌面端已迁移到 Tauri v2 + Svelte 5，旧记录不能作为当前发行包的通过结论。

## 自动检查范围

Python 离线回归使用临时配置、假捕获和假识别 / 翻译引擎，覆盖设置草稿、校验与保存失败、外观更新、引擎重启、暂停状态、正常停止尾段排空、纪要异步任务与旧会话隔离。前端 Vitest 单测与 `svelte-check` 覆盖组件逻辑与类型，`cargo test` / `clippy` 覆盖 Rust 宿主，都不等同于 Windows 桌面材质和窗口交互验证。

构建检查分别读取 wheel、sdist 与冻结核心 onedir 目录，确认图标、VAD 模型与许可证收录；`check_release_layout.py` 核对发行布局并扫描壳二进制中的开发路径残留。构建不启动冻结核心或壳，不会录音、下载 Whisper 模型或调用真实 API。

这些静态检查只能证明文件齐全、布局正确，不能证明冻结后的程序能运行：PyInstaller 漏收隐式导入、DLL 加载失败或冻结环境下 stdio 异常，只有启动可执行文件才会暴露。构建链不再做进程级冻结烟测（在 CI 冷机上不稳定，误报多于实际发现的问题），这类问题由下方清单中便携版启动、无 Python 环境启动与模型下载/加载三项覆盖，因此这三项是每次发布的必检项。

## 手动检查清单

- [ ] 安装程序（NSIS）按当前用户安装；开始菜单、可选桌面快捷方式、卸载正常，卸载后保留用户配置。
- [ ] 便携 ZIP 完整解压后可启动，壳能找到旁边的 `livetrans-core/` 并加载控制中心和字幕窗；从非源码目录启动不回退开发路径。（必检：冻结核心启动）
- [ ] 无本机 Python 环境时仍可启动；CPU 自动识别不会选择 CUDA。（必检：冻结依赖完整）
- [ ] 静默启动与自动翻译的四种组合；静默启动失败时托盘通知。
- [ ] 跨页草稿、应用、还原、字段错误、旧配置自定义目标语言及快捷字号同步。
- [ ] 外观修改不重启或清空字幕；翻译与记录修改原地生效、不重新加载识别模型；声音 / 识别 / 切句修改只重启一次，并保留暂停状态和记录文件。
- [ ] 控制中心无边框窗口的拖动、缩放、最小化 / 还原，及多显示器移动；字幕浮层置顶、拖动、Ctrl + 滚轮调字号与多显示器位置。
- [ ] 100% / 150% / 200% DPI、真实中文输入法、长字幕和键盘导航。
- [ ] 主窗为不透明主题底色：前台 / 失焦、拖到不同壁纸或窗口上方外观不变；高对比与减少透明模式切换为实色面板。
- [ ] 主窗隐藏后字幕增量更新不闪烁，动画在后台暂停。
- [ ] 真实系统 / 软件音频捕获、模型下载与 CPU 模型加载、翻译服务、失败后修改配置重试。（必检：模型 worker 进程）

## 本地检查命令

```powershell
.venv\Scripts\ruff check .
.venv\Scripts\python -m compileall -q livetrans scripts tests packaging
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m build
.venv\Scripts\python scripts\check_package.py
npm test --prefix desktop
npm run check --prefix desktop
cargo test --locked --manifest-path desktop/src-tauri/Cargo.toml
cargo clippy --locked --manifest-path desktop/src-tauri/Cargo.toml -- -D warnings
python scripts\bump_version.py --check
```

`livetrans-core --preview` 使用临时模拟会话提供预览数据，不触碰音频、模型或网络；截图应区分 Webview 内容与实际桌面合成结果。发行包命令见 [发布指南](releasing.md)。

接口依据：[Windows 客户区计算](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-nccalcsize)、[DWM 属性](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute)、[Tauri 窗口 API](https://v2.tauri.app/reference/javascript/api/namespacewindow/)。
