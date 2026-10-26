# 本机控制协议 v1

独立 Tk 面板拥有 Bot 状态、持久化配置和 NapCat 生命周期；Desk 只通过接口操作。
OurDeskPet 发布版监听 `127.0.0.1:37642`，与开发版的 37641 分离；默认 OneBot 为 3002。一条 TCP 连接处理一个 UTF-8 JSON 请求。
客户端发送完请求后关闭写方向，继续读取到 EOF；服务支持分段到达并限制请求为 64 KiB。
空闲连接有超时，不会无限阻塞状态轮询。

请求：`{"protocolVersion":1,"command":"status","payload":{}}`。
响应：`{"ok":true,"data":{...}}` 或 `{"ok":false,"error":"..."}`。
旧版 `RINATOMO_SHOW\n` 唤回窗口命令保留。

| command | 行为 |
| --- | --- |
| status | 读取状态和已应用的设置，不返回连接 token |
| show | 打开现有独立面板 |
| start | 启动链路或从暂停恢复 |
| pause | 暂停回复，保留 QQ/NapCat 连接 |
| refreshLogin | 在需要登录时刷新二维码 |
| shutdown | 退出 Tomo，并关闭它本次托管启动的 NapCat/QQ |
| update | 校验、保存并热应用一个设置分组 |
| notify | 把一条"错过的事项"推送给 admin_users 白名单（模板文本，不经 LLM） |

`update.payload` 每次只包含一个分组：

- `features`: `ping`、`echo` 布尔值。
- `llm`: `enabled` 布尔值；`minReplyInterval`、`timeoutSeconds` 数字；
  `maxTokens`、`dailyTokenBudget`、`maxInputChars`、`maxConcurrentRequests` 正整数。
- `permissions`: `adminUsers`、`privateWhitelist`、`enabledGroups`，正整数列表；缺省字段保留已应用值，空数组清空。
- `autoStart`: 布尔值；只保存启动策略，不应用面板里尚未确认的连接字段，也不立即启动链路。
- `notifications`: `enabled`、`nightSleepEnabled` 布尔值；`nightStart`、`nightEnd`
  为 `HH:MM` 24 小时制字符串且不能相同；`events` 为 `{translation, chatReply,
  loginFailure}` 布尔值。深夜休眠窗口内 Tomo 完全不服务：消息与 # 命令静默忽略，
  notify 通知丢弃不排队。

`notify.payload` 为 `{"event": "...", "title": "...", "lines": ["..."]}`：`event`
取 `translation` / `chat_reply` / `login_failure`（是否推送由 `notifications.events`
对应开关决定）；`title` ≤80 字符；`lines` 为 1-10 条非空字符串（每条 ≤300 字符），
最终消息为模板拼接、总长 ≤1500 字符。收件人**只有** `permissions.admin_users`
白名单；通知关闭、事件未开启、深夜休眠或 bot 未运行时返回 `accepted:false` 与原因。
它只推模板文本，绝不调用 LLM 生成内容。

状态快照中的 `login` 包含 `required`、`message` 和可为空的 `qrcodeDataUrl`；二维码
只在本机控制端口上传输。`llm` 返回已应用的运行策略和只读 `effectiveModel` 与
`usage`（`used`/`dailyLimit`/`remaining`，来自当日 token 预算守卫；服务停止时读自
`llm-usage.json`），不返回 API key 或 URL。`notifications` 返回已应用的通知策略
（`enabled`、`nightSleepEnabled`、`nightStart`、`nightEnd`、`events`）。顶层 `owner`
为 `standalone` 或 `desk`，表示当前控制器的生命周期所有者；它只在进程创建时确定，
后连接的客户端不会接管。公开调试功能集合仍只包含 `ping` 和 `echo`。

独立入口创建 `standalone` 控制器：关闭原生窗口会关闭服务并退出。Desk 创建 `desk`
控制器：关闭/离开工具页面不发送退出命令，退出整个 Desk 时仅对 `owner=desk` 的实例
发送 `shutdown`。显式“关闭服务”始终发送 `shutdown`。

更新两端后应重启旧控制器；旧客户端发送已退役功能字段时返回明确错误，不重新启用旧行为。

shutdown 响应表示已接受异步关闭请求，不表示子进程已经退出。状态里的
shuttingDown 表示正在关闭；shutdownError 为空或最近一次关闭失败的提示。
running 同时覆盖仍在运行的链路、消息工作线程和本次托管的 NapCat/QQ。
关闭失败时保留进程归属和控制端口，禁止重新启动第二条链路，两端均保留可重试的
“关闭服务”。关闭成功后控制器才退出。若 Desk 已退出或原生面板被隐藏，关闭失败会
重新显示原生面板，以便重试。旧控制器没有上述新增字段时，Desk 按未在关闭且无错误处理。

未知字段和无效值返回失败，校验期间不修改运行配置。跨分组需要分别请求，避免部分设置成功、部分失败。
两端均应保留其他分组的未应用输入；断线时的占位快照不能当成已保存配置覆盖草稿。
共享设置、状态语义和协议更改必须同步修改两端，并运行 Python 控制协议测试及 Desk 的 tomo-state 测试。

当前端口只面向受信任本机用户，没有跨系统用户的身份认证。不要转发或暴露该端口到网络。
进程实例按机器端口唯一；配置目录覆盖用于独立配置/测试，不意味着可同时开启多个控制器。
