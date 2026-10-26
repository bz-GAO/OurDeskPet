# RinaTomo 开发与维护

面向开发者：安装环境、命令行、配置字段、生命周期和测试。日常操作见[用户指南](../user/README.md)，本文件不是用户必须完成的配置清单。

## 源码环境

需要 Windows、Python 和独立的 NapCat Shell / QQ NT。首次准备或重建项目环境，在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Setup-RinaTomo.ps1
```

## 命令行与运行边界

也可以从终端使用入口：

```powershell
# 打开控制面板（无参数默认也是 ui）
.\Start-RinaTomo.cmd

# 仅检查已经运行的 OneBot 链路
.\Start-RinaTomo.cmd doctor

# 不使用控制面板，直接运行消息服务（要求 NapCat 已经就绪）
.\Start-RinaTomo.cmd run
```

日常运行只使用根目录的 `Start-RinaTomo.cmd`，不用进入 `.venv`，也不依赖其中由
pip 自动生成的命令。安装脚本从 `pyproject.toml` 读取依赖，但不把 RinaTomo 源码
安装进虚拟环境；启动器始终从自身所在目录的 `src` 加载源码。因此项目目录移动后不会
继续引用旧源码路径。如果 Python 本体变动导致虚拟环境失效，只需删除 `.venv` 并重新
运行安装脚本。

配置文件在启动时会校验：URL 必须使用 `ws://`/`wss://`，重连间隔必须大于 0，
开关和 QQ/群号列表也必须使用正确的 TOML 类型。错误配置会直接报错退出，避免带着
意外的宽松权限运行。

- `ui`：控制面板与默认入口；管理 NapCat、登录和消息服务完整生命周期。
- `doctor`：检查配置、尝试连接协议端并调用 `get_login_info`，成功即证明链路可用。
- `run`：常驻运行，收到的所有事件打印到日志；内置一个 `ping → pong` 响应器
  和可选的复读（echo）开关，用来验证收发闭环。

## 控制面板设置

`ping`、调试复读，以及管理员/私聊/群聊白名单，点击各区自己的
“应用”按钮后会立即更新；每一区都会明确显示“有未应用的更改”或“已应用”。OneBot 地址或 token 改动后，消息连接会自动重建；NapCat/QQ
路径或快速登录账号改动后，受管链路会完整重启。

主操作键会随状态在“启动”和“暂停”之间切换：暂停后 NapCat/QQ 仍保持连接，但状态
显示为离线且不会回复；再次点击“启动”即可恢复。“关闭服务”会结束消息服务以及由本次
RinaTomo 拉起的 NapCat/QQ 进程。页面底部的 NapCat WebUI 是高级恢复入口，主要用于
复杂设备验证、查看底层状态或二维码窗口无法完成登录的情况，日常无需打开。

快速登录 QQ 可留空，此时直接走二维码登录；填写后 NapCat 会先尝试指定账号，失败时
仍可在活动区登录层扫码。登录层可以关闭，登录成功后也会自动撤下；若简化界面无法完成设备确认，可点击“打开 NapCat”
进入完整登录页。

## 配置与敏感信息

真实配置（协议端地址、token、QQ 号等）只放在
`%LOCALAPPDATA%\RinaTomo\config.toml`，与 RinaYaki 的设置存放原则一致，
**不进仓库**。仓库里只有不含真实信息的 `config/config.example.toml`。
开发或便携运行时可用 `RINATOMO_CONFIG_HOME` 指定另一配置目录；显式传入的相对
`--config` 路径会在启动时转换为绝对路径，后续资源查找不再依赖工作目录。

```toml
[connection]
url = "ws://127.0.0.1:3001"   # 协议端 OneBot 11 WebSocket 地址
access_token = ""              # 协议端设置的 access token，可为空
reconnect_delay = 3.0          # 断线重连间隔（秒）

[bot]
name = "rinatomo"
echo = false                   # 复读所有消息（仅用于联调验证）

[features]
ping = true

[permissions]
admin_users = []               # 填自己的管理员 QQ 号，所有功能统一放行
private_whitelist = []         # 允许私聊触发的其他用户
enabled_groups = []            # 启用功能的群；空 = 所有群保持沉默

[llm]
enabled = false                # 文本 LLM 应答器
model = "qwen-turbo"
timeout_seconds = 30.0         # 单次请求超时
max_tokens = 512               # 单次回复长度上限
daily_token_budget = 200000    # 每日 token 保护额度（非计费账单）
min_reply_interval = 0.0       # 同一用户/群会话的最小触发间隔；0 = 不限制
max_input_chars = 2000         # 单条问题字符上限
max_concurrent_requests = 2    # 全局并发请求上限
```

LLM 的 API key 不在 config.toml 中，走环境变量：复制 `.env.example`
为 `%LOCALAPPDATA%\RinaTomo\.env` 或项目根目录下被 Git 忽略的 `.env`，
并填写 `DASHSCOPE_API_KEY`。`DASHSCOPE_MODEL` 可覆盖 `config.toml` 中的
模型名。优先级为真实环境变量、本机配置目录 `.env`、项目 `.env`，最后才是
`config.toml` 默认值。

### 文本 LLM 应答（最小版）

- 触发：通过统一白名单闸门的消息以 `问：` 或 `问:` 开头（冒号支持中英文），
  冒号后的内容作为问题；QQ 的 @、引用等非文本段不妨碍识别文本触发词。
- 默认请求只有系统提示和当前问题。仅当用户显式引用 3 分钟内由 Tomo 参与的消息时，
  才沿该引用分支带入最多 10 条上下文；账号、群聊和私聊之间严格隔离。
- 同一用户的多个请求也可并发，哪个模型请求先完成就先引用回复；并发总量和
  输入长度仍有上限。相同消息 ID 只处理一次，降低重连时重复回复的风险。
- 群聊回复使用“引用原消息 + @发送者 + 回答”，私聊使用“引用原消息 + 回答”。
- 系统提示为初步版本，方向是"极简"：身份一句话 + 回答尽量短的强约束。
- 出错回复固定提示；预算耗尽保持静默。每日用量只持久化日期和 token 数，
  不保存聊天内容；请求前预留额度，避免并发请求一起穿透上限。
- 管理面板暂停或热改配置会使正在途中的旧请求失效，不会在暂停后补发回复；
  普通热改不会重置当日额度。

权限是**默认拒绝**的：不在任何名单里的消息会被静默丢弃（日志留痕但不回复），
因此不需要额外的黑名单。管理员放行一切；普通用户需要群在 `enabled_groups`
里或本人（私聊）在 `private_whitelist` 里才会得到响应。

## 目录结构

```
Start-RinaTomo.vbs       日常双击入口（无控制台窗口）
Start-RinaTomo.cmd       终端入口（默认执行 ui，也可传 run / doctor）
scripts/
  Setup-RinaTomo.ps1     创建本地 Python 环境；从 pyproject.toml 安装第三方依赖
config/                  可复制的配置与回复库示例，不存真实配置
src/rinatomo/
  __main__.py      `python -m rinatomo` 的稳定内部入口
  cli.py           ui / run / doctor 命令编排
  config.py        配置加载（显式路径 > %LOCALAPPDATA%\RinaTomo\config.toml）
  ui.py            本机控制面板、活动区登录覆盖层与动态设置
  control.py       本机控制协议、请求限额与分组参数校验
  napcat.py        NapCat Shell 发现、进程托管和 WebUI API
  runtime.py       控制面板使用的线程化消息服务
  events.py        OneBot 11 事件 → 归一化事件模型
  permissions.py   默认拒绝的守卫层（admin/私聊/群三类白名单）
  llm.py           OpenAI 兼容客户端、私有凭据解析、持久化 token 保护额度
  conversation.py  有界且按会话隔离的引用回复链
  dispatcher.py    事件分发 + handler 注册 + 权限闸门
  actions.py       对协议端的能力调用（发私聊/群消息、get_login_info 等）
  transport/
    base.py        Transport 抽象接口（换协议端方式时只加新实现）
    onebot11.py    OneBot 11 WebSocket 客户端（含重连、echo 配对、心跳容忍）
  handlers/
    debug.py       ping / echo 联调验证器
    chat.py        “问：”触发、去重、并发与生命周期控制
tests/             单元测试 + 内置 fake OneBot 服务端的闭环测试
.venv/             本机生成的 Python 与第三方依赖；不含项目源码和正式启动入口
```

## 开发与验证

```powershell
# 仅在开发环境补装测试依赖
.\scripts\Setup-RinaTomo.ps1 -WithTests
.\.venv\Scripts\python.exe -m pytest -q
```

`.venv`、`__pycache__`、`.pytest_cache` 和 `*.egg-info` 都是可再生内容，已在
`.gitignore` 中排除。`tests/` 内保留的是当前协议解析、权限、handler 和本地 WebSocket
闭环的回归测试，不是运行缓存。

## 与 RinaDesk 的接口

公开核心目前只提供连通测试和默认关闭的调试复读，不附带个人回复库。
旧配置的已退役字段在读取时被忽略，下一次保存时清除；账号、白名单和连接参数保留。
将来个人行为应由用户目录中的显式本地扩展提供，不在公开源码里维护个人配置分支。
当前尚未实现动态插件加载，不会自动执行任意目录里的脚本。

RinaDesk 的 QQ Bot 页已支持状态、登录二维码、启动/暂停/关闭服务和功能/LLM/权限/自动启动设置。
独立面板与 Desk 使用同一份已应用配置；Desk 不直接编辑配置文件。
连接检测和活动记录仍由独立面板提供；底层连接字段默认收在高级设置中。

完整接口约定见 [CONTROL-PROTOCOL.md](../CONTROL-PROTOCOL.md)。修改共享功能时必须
同步两端 UI、参数校验与协议文档。修改源码后需要重启 Tomo，Desk 需要重新构建后才能运行新版本。

单机重装源码不会清除用户目录；新电脑默认没有账号、白名单和 token，自动启动关闭。
上传前从工作区运行 `scripts/check_workspace.py`，不要直接打包整个目录。
`.venv` 与 NapCat 安装/登录缓存必须在目标电脑单独准备。

## 原则（对齐工作区 README）

- RinaTomo 必须能脱离 RinaDesk 独立运行。
- 仓库内不出现任何真实 QQ 号、token、appid。
- 换接入方式（如未来 QQ 官方机器人 API）只新增 transport 实现，不动上层。


## 文档与检查点

用户指南仅维护必要操作和行为；配置字段、实现边界与测试留在本文件及控制协议。`docs/ASSISTANT.md` 是产品运行时知识，保留固定路径，不当作普通用户手册。

默认只建立本地 Git 快照；推送需用户明确要求。用户说明与开发说明按目录分别选择提交，不把两类更新自动合成一个提交，更不夹带已有代码改动。
