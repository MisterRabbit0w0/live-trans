# 界面与发行包验收

当前版本的最终桌面验收尚未完成。开发过程中曾在 Windows、Python 3.13、Qt 6.11.1 上通过 37 项离线回归；之后的窗口边框、悬停动画及打包改动没有重新进行实机验收，旧记录不能作为当前发行包的通过结论。

## 自动检查范围

离线回归使用临时配置、假捕获和假识别 / 翻译引擎，覆盖设置草稿、校验与保存失败、外观更新、引擎重启、暂停状态和旧会话隔离。QML 检查使用离屏模式，不等同于 Windows 桌面材质和窗口交互验证。

构建检查分别读取 wheel、sdist、便携目录和单文件 EXE 的归档目录，确认 QML、SVG 图标、VAD 模型、Qt 插件及许可证收录。不会启动应用，也不会下载 Whisper 模型、录制音频或调用真实 API。

## 手动检查清单

- [ ] 安装程序按当前用户安装；开始菜单、可选桌面快捷方式、卸载正常，卸载后保留用户配置。
- [ ] 便携 ZIP 完整解压后、单文件 EXE 从不同目录启动后，都能加载控制中心和字幕窗。
- [ ] 无本机 Python 环境时仍可启动；CPU 自动识别不会选择 CUDA。
- [ ] 静默启动与自动翻译的四种组合；静默启动失败时托盘通知。
- [ ] 跨页草稿、应用、还原、字段错误、旧配置自定义目标语言及快捷字号同步。
- [ ] 外观修改不重启或清空字幕；引擎修改只重启一次并保留暂停状态。
- [ ] 浅 / 深主题下快速悬停、点击后移开、键盘焦点和禁用按钮，不出现暗灰闪变。
- [ ] 窗口四周没有白边或重复圆角描边；激活 / 失焦、最小化 / 还原后外框稳定。
- [ ] 拖动、边缘缩放、最大化、Windows Snap、Alt+空格及多显示器移动。
- [ ] 100% / 150% / 200% DPI、真实中文输入法、长字幕和键盘导航。
- [ ] 控制中心前台 Acrylic、失焦回退、字幕浮层、零背景不透明度、减少透明效果及高对比模式。
- [ ] 主窗隐藏后装饰动画停止，字幕增量更新不闪烁。
- [ ] 真实系统 / 软件音频捕获、CPU 模型加载、翻译服务、失败后修改配置重试。

边框修复处理 Windows 客户区与默认外框重绘，并在普通主题关闭 DWM 额外描边。悬停修复将底色透明度与颜色分离；深色配色与焦点边框保留。两者仍需按上述清单在实际桌面复验。

## 本地检查命令

```powershell
.venv\Scripts\ruff check .
.venv\Scripts\python -m compileall -q livetrans scripts tests packaging
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m build
.venv\Scripts\python scripts\check_package.py
.venv\Scripts\python scripts\preview_ui.py --backdrop
```

预览程序使用临时配置和模拟字幕。截图应区分 Qt 窗口自身内容与实际桌面合成结果，不能仅凭 DWM 接口返回成功就断言毛玻璃可见。发行包命令见 [发布指南](releasing.md)。

接口依据：[Windows 客户区计算](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-nccalcsize)、[激活时非客户区重绘](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-ncactivate)、[DWM 属性](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute)。
