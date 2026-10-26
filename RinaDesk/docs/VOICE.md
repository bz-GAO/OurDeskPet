# 语音输入与输出

Desk 的语音能力分为互不共享运行状态的 input（麦克风→文字）、事件音效
（预录制语音包）与语音结合回答（回答口述段→TTS）。实现位于
`app/src-tauri/src/voice/` 与 `app/src/voice/`。

## 行为契约

- 点击麦克风打开语音弹窗（复用确认弹窗视觉）：中间提示行 + 实时识别文本；
  左下「取消」，右下主按钮三态推进：**开始录音 → 停止录音 → 发送**。
- Esc 或取消会放弃本次识别并向后端发 `voice_input_cancel`，不产生任何结果。
- 「发送」为端到端确认：直接把识别文本作为一条消息发送（2026-10-24 按用户
  决定，不再先填输入框当草稿）。
- 空结果（停止后无文本）自动回到「开始录音」；出错显示原因并可重试。
- 回复发送中（isSending）麦克风按钮禁用，避免与发送锁竞争。
- 单次录音上限 60 秒，到点自动收尾；连接超时 10 秒；收尾等待 8 秒，
  超时按已有文本尽力交付。同一时间只允许一个会话。
- 仅对话窗口（dialogue）可调用语音命令；后端对窗口来源做校验。

## 事件音效（voice/output）

- 通知、量子传送、任务完成/失败只发送事件键；后端按总开关、分类开关、音量、
  语音包和逐 clip 的 `reviewed` 闸门决定是否播放。缺少或显式为 false 的
  `reviewed` 一律不播放。
- 设置位于“美术 > 音效”，采用与人物、主题、高级特效相同的折叠卡结构。
  音效包缺失时仍允许保存关闭开关和音量，不会因缺资源锁死设置。
- 语音包位于 `%LOCALAPPDATA%\RinaDesk\voicepacks\packs\<pack>\`；资源不进入
  Git 或默认安装器。clip 只允许语音包内的普通相对路径；绝对路径、空分段、
  `.`、`..` 与前缀路径均拒绝。
- 播放在线程内串行处理，新事件打断上一条。前端任务轮询对相同任务与阶段去重，
  不会因重复终态轮询反复播放完成音。

## 语音结合回答

- 语音输入弹窗中的“语音结合回答”默认关闭。开启后，模型首行按
  `说出："…"` 提供 1–3 句口述段，其余内容继续以 Markdown 展示；格式不匹配
  时整条保留为普通文本，不丢回答。
- 仅完整完成的回答触发当前系统音色模型 `qwen3-tts-flash` 合成；取消、错误或
  截断不合成。气泡不自动播放，必须由用户点击。口述文字始终同屏显示。
- TTS 只接受活动 Chat 方案为 DashScope 国内/国际主机；临时音频 URL 只允许
  HTTPS `aliyuncs.com` 域并当场转存。单条音频上限 10 MB，数据 URL 随会话保存。
- `qwen3-tts-flash` 官方不支持复刻音色，因此现有 `ttsVoice` 预留字段不能直接
  用于该模型。2026-10-26 已在项目外用同一参考音频完成
  `cosyvoice-v3.5-plus`（优先）与 `qwen-audio-3.1-tts-plus` 私有 A/B；待用户
  试听后再切换运行时模型和音色 ID，不由离线测试冒充完成。
- 当前 TTS 仍读取活动 Chat 方案；这与 ASR 优先复用 Yaki `DASHSCOPE_API_KEY`
  的约定不一致。正式接入获选复刻音色前，应先统一凭据解析。

## 模型与凭据（定死内置，不暴露给用户选择）

- 模型：`qwen-audio-3.0-asr-flash-streaming`（与 RinaYaki live 同款）。
  2026-10-24 选型依据：0.00033 元/秒、每月免费 10 小时，中英混说强，
  支持热词偏置与中间结果；协议有内部参考实现（Yaki venv 的 dashscope SDK）。
  参考：[模型计费](https://help.aliyun.com/zh/model-studio/model-pricing)、
  [实时语音识别指南](https://help.aliyun.com/zh/model-studio/real-time-speech-recognition-user-guide)。
- 凭据（2026-10-24 按用户决定调整）：**优先读已注册 RinaYaki 项目根 `.env` 的
  `DASHSCOPE_API_KEY`（含可选 `DASHSCOPE_WEBSOCKET_URL`）**，语音与 Yaki 永远
  同一把 key，不随聊天方案切换失效；聊天方案恰好是阿里云百炼时作为回退。
  两处都没有时提示原因。只读这几个文档化字段，与 `billing::credentials`
  的工具凭据边界一致；密钥不落日志、不进事件。
- 协议：DashScope 双工 run-task websocket（`/api-ws/v1/inference`），
  帧构造与事件解析在 `voice/input/asr.rs`，含单元测试；协议翻译自
  dashscope Python SDK 源码。ws 入口优先级：Yaki 显式 `DASHSCOPE_WEBSOCKET_URL`
  > base_url 主机映射 > 百炼国内默认。

## 实现要点

- 采集：cpal 默认麦克风，原生采样率单声道入队（有界、满则丢最旧），
  重采样（一阶低通 + 线性插值）在识别任务侧做。cpal 的 Windows 流不是
  Send，因此流驻留专属采集线程，对外只暴露 Send 安全句柄。
- 会话：`voice/input/mod.rs` 状态机（starting/recording/finishing + 事件
  `voice-input-state/partial/final/error`）；停止时先发完队列剩余音频再
  finish-task；取消直接丢弃不发事件。
- 前端：`app/src/voice/`——`voicePhase.ts`（纯状态机，单测覆盖）、
  `useVoiceInput.ts`（事件订阅与命令）、`VoiceDialog.tsx`、`voice.css`。

## 后续候选（动手前先在 STATUS.md 立项）

- 弹窗内文本可编辑（当前只读展示）。
- 热词偏置：把项目名词（RinaYaki/Tomo 等）作为识别偏置词表传入。
- ASR 用量本地记账并接入账户/账务区展示。
- 语音历史长期增长后，评估 wav data URL 改为受管音频文件或 mp3/opus。
