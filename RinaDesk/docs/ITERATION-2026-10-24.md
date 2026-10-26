# 2026-10-24 迭代记录：语音输入与 Agent 执行层

本文是当日一轮开发的历史记录，不作为当前待办；现行状态以
[STATUS.md](STATUS.md) 为准，功能契约见 [VOICE.md](VOICE.md) 与
[AGENT-TOOLS.md](AGENT-TOOLS.md)。

## 一、语音输入（voice/input，从零到可用）

**决策链**：最初设想"完整语音对话回路"，经讨论重排为三层——P0 桌宠状态
音效（未做）、P1 语音转文字输入（本轮完成）、P2 桌宠发声（远期）。
交互按用户指定：点击式、ConfirmDialog 风格弹窗、三态主按钮
（开始录音→停止录音→发送）、左下取消。

- 模型定死 `qwen-audio-3.0-asr-flash-streaming`（0.00033 元/秒、月免费
  10 小时，中英混说强；协议可从 Yaki venv 的 dashscope SDK 源码翻译）。
- 凭据两度修正后定型：**优先读注册 RinaYaki 项目根 `.env` 的
  DASHSCOPE_API_KEY/WEBSOCKET_URL**，与 Yaki 永远同 key；聊天方案为百炼时
  回退。最初版本错接"当前聊天方案 key"，用户实测（DeepSeek 原生方案）暴露。
- 「发送」行为按用户决定改为端到端直发（不再填草稿）。
- 输入行布局按用户指定重排：麦克风（左）｜填满的输入框｜Send（右），
  文件上传为输入框上方小标志。首次改动曾把 grid 改 flex 丢掉 1fr 致
  输入框缩块，次日反馈后恢复三列网格。
- 工程要点：cpal 0.15 的 Windows Stream 非 Send，流驻留专属采集线程；
  一阶低通+线性插值重采样；60 秒上限、连接 10s/收尾 8s 超时；
  仅对话窗口可调用。

## 二、Agent 只读工具层（增量 1）

- 封闭注册表（编译期常量表，绝不动态加载），首批三工具：
  `desk_diagnostics` / `tomo_status` / `yaki_status`，全部无参只读。
- 接入既有工具循环（stream_chat.rs），对话与项目助手两模式可用，
  独立预算（每轮 4 次）。
- 消息内芯片渲染（中文标签 + 三态符号），纯状态机 toolCalls.ts 带单测。
- 首次真机即验证成功：模型自主调用 yaki_status 并在回复中给出真实注册状态。

## 三、Agent 执行层（增量 2）：Yaki 翻译链

用户确认哲学落地为**双闸确认**：

1. 闸 1（唤起）：模型调用 `yaki_start_translation{url}` 只登记提案并弹窗；
   确认后仅跑免费的桥 preview，任务卡渲染为"待开始"（标题/时长/费用预估）。
2. 闸 2（消费）：卡片上点"开始翻译"再弹窗；确认后才调桥 create——
   create 即启动下载，这条边界就是付费闸门。
3. 运行态任务卡每 3 秒轮询桥 status；awaiting_style/failed/declined 终态。
   字幕样式与导出仍归 Yaki 扩展页（agent 不代做）。

实现：`agent/proposals.rs`（提案存储上限 5、URL 白名单 http/https、
费用预估）+ 四命令；前端 agentTasks.ts 纯状态机（proposalId/jobPath 双键
合并）+ 任务卡 + 轮询。

## 四、修复与排查记录

- **闸 1 卡死事故**（当日最重要一课）：用户点"创建翻译任务"后卡片停在
  "等待确认"。排查逐一排除桥（CLI 直跑 B站/YouTube 均 ≤8s 成功）、
  web_session（无持久会话，preview 全走 anonymous，"迁移内嵌浏览器"结论
  =无需迁移）、代理（本机无代理，直连可通）。最终 agent.log 破案：
  **闸 1 后端 4 秒即成功，卡在前端**——agent-task 事件订阅挂在回合作用域，
  回格结束即注销，确认发生在回合后，事件无人接收。修复：订阅移至组件
  挂载层。教训：回合作用域订阅只可用于回合内事件，任务生命周期事件必须
  挂载层订阅。
- **超时兜底**：所有桥子进程调用加墙钟超时（预览/执行 90s、状态 20s），
  挂死转为可见错误（含代理提示）。附 Windows 单测。
- **运行日志**：`%LOCALAPPDATA%\RinaDesk\logs\agent.log` 记录闸 1/闸 2 的
  start/ok/FAILED（本次破案的关键工具，保留）。
- **余额查询中断**：根因为 `%LOCALAPPDATA%\RinaDesk\billing-credentials.bin`
  （DPAPI 账务授权）缺失，用户在设置中重连后验证恢复（余额缓存文件出现
  =查询真实成功）。疑因清理 build-cache 时同目录陪葬。后续已将本地构建和
  安装器预览的默认编译缓存隔离到项目 `.build-cache`（Git 忽略）；授权位置
  保持不变，避免配置迁移风险，清理编译缓存也不再接触用户数据根。
- **侧边栏"打开像复制"**：存储层确认托管记录重开为原地复用（无副本）；
  导入的 JSON 重开会生成新托管记录（设计行为）。真正缺口是侧边栏无
  "当前打开"标记——已加 currentStorageId 高亮（"打开中"）。
- **工具链坑**：代码调用 `extension_tools::extension_status` 会使测试二进制
  以 STATUS_ENTRYPOINT_NOT_FOUND 启动失败（两次二分确认），改走
  `diagnostic()` 规避；原因未深究，代码注释有记录。

## 五、量化与工程状态

- Rust 测试 130 → 147（voice 11、agent 5、桥超时 2 等）；前端 mjs 单测
  10 → 13（voice-phase、tool-calls、agent-tasks）。
- 新增依赖：cpal 0.15、tokio-tungstenite 0.24（native-tls）、tokio 补
  sync/macros。
- 新文档：VOICE.md、AGENT-TOOLS.md；STATUS.md/README 索引/工作区
  AGENTS.md（agent 安全规则一行）同步。
- 用户同期并行完成：UI 测试并入 npm test（test:unit/test:ui 拆分）、
  context.ts 死代码清理——与本轮改动无冲突共存。
- 全部改动未提交 Git；最终构建已于当日装进 `%LOCALAPPDATA%\RinaDesk\bin`
  并修复两处快捷方式。

## 六、遗留与下一步入口

- **待真机验收**（装好最新构建后首选）：翻译链闸 2 → 运行卡进度 →
  awaiting_style/failed 终态；拒绝路径；语音 60 秒上限与非百炼提示。
- 侧边栏若仍见"真复制"（列表条目数增加），属导入对话转托管记录的行为，
  下次决定是否让导入直接转正。
- 远期候选（AGENT-TOOLS.md）：提案级设置动作、任务卡重试按钮/百分比、
  P0 状态音效、output 侧语音包。
