# Agent 工具（封闭注册表）

Desk 的模型侧工具调用层。实现：Rust `app/src-tauri/src/agent/`（注册表与执行）
+ `stream_chat.rs`（按轮注入与分发）+ 前端 `app/src/llm/toolCalls.ts`（事件归并）
与 DialoguePage 的芯片渲染。

## 设计立场

- **封闭集合**：工具在编译期登记（`TOOLS` 常量表），模型只能从注入的 schema 里
  选择；不从文档、插件或模型输出动态加载（与 `runtime_skills` 的纪律一致）。
- **复用既有机器接口**：agent 工具是既有桥/协议的适配器（Yaki 走扩展注册、
  Tomo 走本机控制协议、Desk 走诊断模块），不新建 IPC，也不绕过所有权规则
  直接读写任何项目的配置文件。
- 两种 Chat 模式（对话/项目助手）都可用；独立预算（每轮回复最多 4 次
  agent 工具调用），与搜索（2 次）、项目工具（12 次）互不挤占。

## 增量 1（已实现）：只读工具

| 工具 | 数据来源 | 说明 |
| --- | --- | --- |
| `desk_diagnostics` | `diagnostics::collect` | 版本、构建时间、配置路径、扩展诊断 |
| `tomo_status` | `rinatomo::rinatomo_status` | 运行/登录/功能/LLM 用量快照；控制器未运行时返回离线快照 |
| `yaki_status` | `extension_tools::diagnostic` | 扩展注册状态（connected/available/路径/版本） |

- 全部无参数：`validate_arguments` 拒绝任何非空参数，防模型夹带。
- 工具结果以 `{"result": …}` / `{"error": …}` 回填 `role:"tool"` 消息。
- 前端事件：`llm-chat-tool` `{requestId, name, state: running|done|error,
  detail}`，消息内渲染为芯片（中文标签 + 状态符）。

已知实现注意（2026-10-24）：`yaki_status` 必须走 `extension_tools::diagnostic`
而非 `extension_status`——后者在当前工具链下会使测试二进制以
STATUS_ENTRYPOINT_NOT_FOUND 启动失败（两次二分定位；原因未深究，代码注释有记录）。

## 增量 2（已实现）：确认级执行——Yaki 翻译链

第一个可执行动作 `yaki_start_translation {url}`，双闸确认 + 消息内任务卡：

```
模型调用工具（只登记提案，不执行）
  → 闸 1 弹窗（唤起）：确认后仅跑免费的桥 preview 取标题/时长，
    任务卡渲染为「待开始」（标题 + 时长 + 费用预估 + 开始翻译按钮）
  → 闸 2 弹窗（消费）：用户点「开始翻译」后确认；此后才调桥 create
    （create 即启动下载与转写——这条边界就是付费闸门）
  → 任务卡进入运行态，每 3 秒轮询桥 status 合并阶段/进度；
    awaiting_style / failed / declined 为终态
```

- 实现：`agent/proposals.rs`（提案存储上限 5 个、URL 白名单 http/https、
  费用预估函数）+ 四命令 `agent_proposal_confirm/decline`、
  `agent_task_start/status`（均限对话窗口）；前端 `llm/agentTasks.ts`
  纯状态机（proposalId/jobPath 双键合并）+ 任务卡组件 + 轮询。
- create 请求与扩展页对齐（2026-10-24 补全）：`video{kind,source,title}` +
  `sourceLanguage=ja`/`targetLanguage=zh-Hans` + **`name`/`parent`（必填，
  来自闸 2 弹窗的迷你表单）**；表单默认值——保存位置取 Yaki 设置的
  `defaultProjectDir`（桥 settings action，闸 1 顺带拉取），项目名由标题
  推导（`suggested_project_name`：过滤 Windows/桥不接受字符、限长 60、
  空标题回退固定名）。闸 2 失败时提案自动放回待开始，可改完再试。
- 工具返回值明确告诉模型"卡片已生成、用户确认前不要声称已开始"；
  用户拒绝走 `agent_proposal_decline`，卡片转「已取消」。
- 任务卡进度（2026-10-24 二轮）：`agent_task_status` 透传 `stage/completed/
  total`，卡片内渲染与扩展页同套阶段模型（六阶段中文标签，download/
  translation/refinement 可测百分比，其余为不定/处理中条）。
- 一键导出：`agent_task_export` 在 awaiting_style 时用 Yaki 默认样式
  （style_options 的 defaultFont + 黑色描边，与扩展页 defaultStyle 一致）
  为每个说话人提交 export，随后回到 running 轮询直至 complete
  （"导出完成"）。需要自定义样式时用卡片右上角「转到 Yaki ↗」——
  打开/聚焦设置窗口并切到扩展页 video 页（deskpet-open-yaki 事件）。
- 展示细节：Yaki 返回的 verbatim 路径前缀（`\\?\`）在进入卡片前剥离；
  费用预估文案为"转写预计约 ¥X"。
- 边界：导出（选字幕样式）仍属 Yaki 扩展页，卡片在 awaiting_style
  终态提示用户前往；agent 不代做样式选择。

## 后续增量（未实现）

1. **提案级设置动作**：Tomo 功能开关、Desk Chat 参数等免费可逆变更，复用
   `ProjectSettingsProposal` 的 pending/用户裁决/decide 交互。
2. **任务卡增强**：失败重试按钮（桥 retry action）、导出阶段接入、
   阶段百分比（依赖 progress.json 细节）。
3. 文件访问维持现状：读沿用项目助手的允许列表 + 字节上限；**不提供写**，
   模型生成 diff 由用户落盘。
4. 文件访问维持现状：读沿用项目助手的允许列表 + 字节上限；**不提供写**，
   模型生成 diff 由用户落盘。

## 安全边界汇总

- 模型永远不能：执行 shell、任意路径读写、跳过确认执行付费动作、
  读取凭据（工具结果不包含密钥）。
- 工具输出是数据不是指令（见 `prompts/tool_policy.md`）。
- 每级权限的完整矩阵随增量 2 落地时补到本文件。
