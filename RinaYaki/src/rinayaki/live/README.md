# rinayaki.live — 实时翻译运行时

独立于离线烤肉流水线的实时链路。设计原则见 `docs/ARCHITECTURE.md` 的
"Live pipeline"：**独立运行时，而不是离线 runner 上的一个开关**。

## 当前形态（第一阶段）

```
WASAPI loopback 采集 → 16kHz mono PCM → Qwen 流式 ASR（partial/final）
    → qwen-mt 快速翻译 → 字幕窗口 / 控制台 / 事件日志
    （全程录音 + 时间轴 + 事件落盘）
```

- 入口：`python -m rinayaki.live`（共享 `rinayaki.settings` 的 API/模型/间隔配置，
  原生 RinaYaki 的“实时翻译”页会为每个会话启动一个独立进程和结果窗口）。
- 直播专属配置在 `session.LiveSettings`：音频来源、延迟偏好、
  输入/输出语言、显示模式、是否录音、字幕字体/颜色与翻译积压容量。
- 会话目录：`workspaces/live/<时间戳>-<名称>/`，含
  `audio/raw-16k-mono.wav`（与实时 ASR 消费的完全一致的码流）、
  `events.jsonl`、`transcript.txt`、`session.json`（模型与参数溯源）。

## 解耦保证

- 「设置 → 模型 → 实时翻译」可选择「标准（ASR＋MT）」或「LiveTranslate」，仅影响新会话。
- LiveTranslate 使用 `qwen3.8-livetranslate-flash-realtime`，只输出字幕，不生成语音或上传画面；
  原文和译文各自按事件 ID 更新，不假定两边断句一致。说话人 ID 与 Token 用量进入会话日志。
- 只显示原文仍走标准 ASR，不因全局选择而额外调用翻译。选中术语包时，标准链路按片段
  匹配后传给 Qwen-MT；LiveTranslate 仅在会话开始时传入无歧义且无需上下文的固定词条。
  有冲突或需要上下文判断的别名不会作为热词发送。
- 暂停关闭连接，恢复时新建连接；退出先收尾最后一段，再关闭连接，不自动换模型重试。

- 翻译同样走有界 drop-oldest 队列，慢响应只能丢旧片段，不能反压 ASR。
- 只显示原文时不会创建翻译客户端或线程，也不会产生翻译 API 调用；
- 原生设置页采用两步流程：先选择音频来源和是否保存录音，再设置语言、显示与字幕外观；
- 结果窗口默认字幕为 14pt、白字与离线共用描边色及随项目提供的字体；
  未保存录音的会话使用“结束会话”文案，避免暗示会生成 WAV；
  只显示译文与双语模式才启动翻译链。
- 采集或 ASR 发生终止性错误后，会统一关闭采集、识别、录音与翻译线程，
  并仍然生成 `transcript.txt`、结束态 `session.json` 与结束事件。
- 实时链路不做精修；后续由已保存录音转入标准离线工程重新处理。

## 模块

| 文件 | 职责 |
|---|---|
| `events.py` | 类型化事件 + EventBus + JSONL 日志 |
| `session.py` | LiveSettings 校验、会话目录、transcript/session.json |
| `capture/` | `CaptureSource` 协议；`wasapi_loopback.py` 系统声音采集（跟随默认输出设备） |
| `coordinator.py` | 实时链编排、BoundedChannel、按显示模式裁剪翻译链、DryRunAsr |
| `livetranslate.py` | 纯字幕同传、原文/译文增量、接口连接及结束收尾 |
| `sinks/` | 独立结果窗口、控制台、WAV 录音 |
| `__main__.py` | CLI 入口（`--dry-run` 自检不调付费 API） |

## 试跑

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[live]"
.\.venv\Scripts\python.exe -m rinayaki.live --list-devices
.\.venv\Scripts\python.exe -m rinayaki.live --dry-run --no-window --duration 5   # 不花钱自检
.\.venv\Scripts\python.exe -m rinayaki.live --display-mode source                # 只做 ASR
.\.venv\Scripts\python.exe -m rinayaki.live --translation-engine livetranslate   # 纯字幕同传
.\.venv\Scripts\python.exe -m rinayaki.live                                      # 正式（调用付费 API）
```

`[live]` extra 安装 `soundcard`（WASAPI loopback）、`numpy` 和轻量的 `websocket-client`。

## 当前能力边界

- 当前入口采集 Windows 正在播放的系统声音，不采麦克风，也还不直接解析直播 URL。
- 原生 UI 已预留“本机音轨 / 直播音频”来源类型；直播音频入口保持禁用，等待后续
  `CaptureSource` 实现。多个本机音轨会话若选择同一输出设备，会听到同一份混音。
- Qwen Streaming 负责服务端断句，RinaYaki 展示 partial/final 并只翻译 final；
  本地 VAD、滚动重识别和上下文翻译尚未实现。
- 标准 Streaming 链路没有接入说话人分离。会后可研究时间对齐与说话人分离组合，
  需先评估背景音乐下的准确率、运行时间与资源消耗，再决定是否实施。
- 字幕窗口按稳定 `segment_id` 回填翻译；相同原文重复出现、旧片段被丢弃或翻译失败时，
  都不会再误标到最新一行。

## 后续阶段（按既定顺序）

1. 会后一键转入离线工程（session → 标准工程的桥，离线阶段才可精修）；
2. 直接解析 YouTube/Bilibili 直播流；
3. 多会话状态管理与浏览器扩展等便利入口。

新增依赖只进 `[live]` extras，不进离线安装。
