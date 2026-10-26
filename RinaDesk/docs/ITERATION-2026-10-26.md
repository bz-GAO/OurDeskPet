# 2026-10-26/27 迭代记录：夜间自动化——语音 P0 与 Agent/Tomo 扩展

本文记录 2026-10-26 深夜至 10-27 凌晨的夜间自动化运行（按 NIGHT-TASK.md
协议执行）。历史记录；现行状态以 [STATUS.md](STATUS.md) 为准。

## 执行概况

按既定顺序完成四个定稿目标 + Desk 事件源接线，全程断点状态托管在
工作区 `NIGHT-TASK.md`。交付时全部测试绿：
Desk cargo 160 / tsc / test:unit / vite build；Tomo pytest 137。

## 一、目标 1：P0 事件音效（voice/output）

- Rust `voice/output/`：rodio 播放器。**rodio 的 OutputStream 与 cpal 同族
  非 Send，采用专属音频线程 + Play 命令通道**（同 capture.rs 模式）；打断式
  播放（新事件停旧的）。
- 语音包：`%LOCALAPPDATA%\RinaDesk\voicepacks\packs\default\`（pack.json +
  clips/）；`reviewed=false` 永不播放（铁律执行点）；clip 路径拒绝 `..`/
  绝对路径/父目录分量。占位"叮"为脚本合成的 0.35 秒正弦衰减 wav（30KB），
  交付后可随时替换为角色语音。
- 事件键 `notify`/`teleport`/`task_complete`/`task_failed`（三类别开关，task
  管后两个）；触发点：通知板 `notifying` 相位、量子传送 `out` 相位、agent
  任务终态事件。
- 设置：settings.json（enabled/events/volume/pack/ttsVoice）；设置页美术大类
  新增"音效"块（总开关 + 事件勾选 + 音量滑条），即改即存。

## 二、目标 2：实时语音结合回答（voice/tts + chat 管线）

- 语音输入弹窗新增"语音结合回答"勾选（默认关）；开启时 stream_chat 注入
  TTS 指引 system 消息：先输出 `说出："…"` 口述段（1-3 句口语），随后正常
  展示文本。
- 前端流式解析 `parseSpokenReply`（全角/半角引号兼容）；**模型不按格式时
  整体降级纯文本，永不丢内容**。
- 回复完成后口述段 → `voice_reply_synthesize`（qwen3-tts-flash，非实时
  HTTP，响应直接含 base64 wav；若只返回 24h 时效 URL 则当场下载转存）→
  data URL 存进消息 JSON（与图片同模式持久化，无临时文件）。
- 语音气泡卡片：微信式胶囊、不自动播放、点击播放、口述文字默认渲染、补充
  文本照常 markdown。播放走 webview `<audio>`（点击=用户手势）；rodio 只管
  事件音效，两条通路分离。
- 音色：本轮运行时代码仍使用 `qwen3-tts-flash` + 内置 Cherry；官方模型表确认
  该模型不支持复刻音色，`ttsVoice` 仅为预留字段。2026-10-26 后续实验已用
  同一参考音频注册 `cosyvoice-v3.5-plus` 与 `qwen-audio-3.1-tts-plus` 私有音色，
  等用户 A/B 试听后再选择并接入运行时。
- **计费更正**：百炼当前资料显示 CosyVoice 创建音色免费、按合成字符计费；
  Qwen 音色创建为 0.01 元/个，北京地域在有效期内有 1000 个免费额度。此前
  “9.9 元音色解锁”属于 MiniMax 口径，不适用于本次 CosyVoice 方案。

## 三、目标 4：模式跳转卡片（agent 增量 3 重定义版）

- agent 注册表新增 `suggest_project_mode`（零副作用信号，仅日常聊天模式
  注入；项目模式本身具备全部能力故不注入）。
- chat 模式 policy 文本加指引：请求涉及项目源码/工程操作/Desk 设置时调用
  一次并告知用户可跳转；同时写明设置边界（Desk 五开关可在项目模式提案；
  Tomo/Yaki 设置需去各自面板）。
- 前端：消息内"更适合项目助手模式 · 跳转"卡片 → ConfirmDialog split 布局
  （左取消/右确认）→ 切换到项目助手模式并把触发跳转的用户消息预填进新模式
  输入框。

## 四、目标 5：Tomo 通知 + # 命令（Tomo 端全量，Desk 事件源接线）

- config.toml 新增 `[notifications]`（enabled 默认开、night_sleep_enabled
  默认开、night_start 22:00 / night_end 08:00、events{translation 默认开,
  chat_reply 默认关, login_failure 默认开}）与 `[commands]` 别名段（别名→
  内置命令名或固定回复）。
- 控制协议 v1 增补：`notify` 命令（Desk→Tomo 推送，仅发 admin_users 白名
  单，模板文本不经 LLM，深夜休眠/事件关闭时拒绝并给原因）+ `notifications`
  update 分组 + 状态快照 `notifications` 节。CONTROL-PROTOCOL.md 已同步。
- 深夜休眠：runtime 内 30 秒巡检，窗口内 dispatcher 整体停用——消息、
  # 命令、通知全部静默；通知丢弃不排队（早晨 #yaki_state 可查）。
- `#yaki_state`（Tomo 直调 Yaki 桥 jobs，只读子进程）/`#tomo_state`（运行
  时长+今日 token）/`#help`；仅 admin 白名单；`#desk_state` 按决议不做。
- Tk 面板与 Desk RinaTomoPage 各加"通知与深夜休眠"设置区（两端 checkbox
  约定对齐）；tomoState 增 notifications 解析/合并/校验（parseNightTime）。
- Desk 事件源：agent 任务终态（awaiting_style/complete/failed）→ Rust
  `rinatomo::notify` 推送（每 任务×相位 去重，spawn_blocking 不阻塞轮询）。
  聊天回复与登录失效事件源留待后续（通知管道已就绪，推送即通）。

## 五、问题与遗留

1. **CUA 本会话不可用**：Computer Use runtime 拒绝（unavailable for this
   session），余额监控与模型自动切换未能执行——夜间全程跑在 Flash 上，
   靠 NIGHT-TASK.md 断点兜底。下次夜间任务前先验证 CUA 可用性。
2. **Windows 活动小时 7:00→01:00**：凌晨 1-7 点理论上允许更新重启（无管理
   员权限未改）；本轮检查确认无待重启更新，风险可控。彻底解决需管理员把
   活动小时覆盖夜间或暂停更新。
3. **TTS 音频为 wav（24kHz 单声道）**：单条约 200-400KB base64，比 mp3 大；
   如历史体积成为问题，后续可在 Rust 侧接编码器转 mp3/opus。
4. **CosyVoice / Qwen-Audio A/B**：私有样本已生成，待用户试听选择；尚未接入
   Desk 运行时，也不得把账号绑定音色 ID 或来源录音提交到公开仓库。
5. **TomO 通知的聊天回复/登录失效事件源**：Desk 侧尚未接线（管道已就绪）。
6. 语音包"叮"为占位：替换方式 = 覆盖 clips/*.wav 并按需更新 pack.json 的
   transcript。

## 六、工程状态

- Desk：cargo 160（+22）、前端 mjs 单测 14 个文件、tsc/vite 绿；新增 rodio。
- Tomo：pytest 137（+43）、无新依赖。
- 协议：CONTROL-PROTOCOL.md v1 增补 notify/notifications（向后兼容，旧客户端
  行为不变）。
- 两仓改动未提交 Git；Desk 未重建安装副本（重建方式见 Build-Local.ps1）。

## 七、2026-10-26 Desk 接手复查与修正

### 已修正并由自动化覆盖

1. 拖动无人机不再使用估算紧边界：拖动/释放期间临时原生区域改为完整
   `420×230` 下部画布，SVG 根允许阴影溢出；人物与无人机编队尺寸不放大。
2. 音效设置改入与人物/主题/高级特效一致的“音效”折叠卡；旧桥、空对象或
   字段缺失先归一化为安全默认值，不再让整个设置页崩溃。连续保存串行化，
   保存失败回滚到最近成功状态并允许重试。
3. 音效包缺失时仍可保存关闭开关和音量。设置文件改为同步写入临时文件后
   备份/替换，覆盖保存与失败回滚均有测试；缺失 `reviewed` 默认 false，clip
   原始路径拒绝空分段、`.`、`..`、绝对路径和路径前缀。
4. `suggest_project_mode` 原先只注册却未进入 stream_chat 分发分支，现已接通；
   跳转按钮在回复中禁用，确认后切模式并预填原消息，建议卡进入受管/导出会话。
5. 任务终态事件音效按任务路径与阶段去重，轮询同一终态不会反复播放。
6. TTS 只在完整完成时合成；取消/错误/截断不合成。内联/远端音频上限 10 MB，
   远端仅接受 HTTPS `aliyuncs.com`，非官方 URL 与无效 base64 均拒绝。
7. Tomo 通知 UI 重排为主开关、事件组、深夜休眠及时段；事件/时间子控件按主
   开关禁用，时间使用原生 24 小时输入。状态合并与时间校验测试已补齐。

验证结果：`npm test` 全绿（含模式跳转、旧音效 payload、无人机预览）；
`npm run build` 全绿；`cargo test` 为 161 passed / 3 ignored；`cargo fmt --check`
通过。3 个 ignored 是明确的真实账户余额/付费模型测试，不在自动化中执行。

### 留给用户的真实环境验收

- 用当前显示器/DPI 拖动像素 A.L.A.N，确认左右无人机、阴影、拖尾及释放动画
  都完整；同时观察释放 360 ms 后透明区是否恢复点击穿透。
- 使用真实麦克风完成中英混说、取消、60 秒上限；再用活动 DashScope Chat
  方案测试一次“语音结合回答”，确认实际计费、音色、气泡点击播放与保存重开。
- 提供或确认 `%LOCALAPPDATA%\RinaDesk\voicepacks\packs\default\` 的逐条已审核
  clip。本仓不替用户决定角色语音，也不把未审核音频打进安装器。
- 连接真实 Tomo/QQ 管理员白名单，验收翻译终态通知、跨午夜休眠、休眠期间不
  排队，以及恢复后不补发。聊天回复/登录失效事件源仍待后续开发。
- 用真实模型观察普通对话中的模式跳转建议是否克制、时机是否合理。

### 待讨论

- 是否长期让事件音效默认开启但在缺包时静默，还是首个已审核语音包安装后再
  自动开启；当前采用前者，设置页会明确显示包缺失。
- wav data URL 会放大会话 JSON；若实际历史增长明显，再决定改受管音频文件或
  mp3/opus，不在本轮预先增加编码依赖。
- CosyVoice 与 Qwen-Audio 已完成同素材 A/B；默认优先 CosyVoice，最终接入仍由
  用户试听结果决定。

## 八、2026-10-26 设置与扩展 UI 收尾

- 美术页“音效”保持与人物、主题、高级特效同级，明确占据底部整行并默认展开；
  防止旧的双栏规则把它挤入人物详情右侧。实际程序需重新构建后才能看到新布局。
- Desk 内嵌 Tomo 的通知时段改为“开始 / 至 / 结束”四列等高布局，时间输入允许
  收缩；页面、状态卡、fieldset 全部限制在可用宽度内，纵向内容由工具页自身滚动，
  不再横向裁掉 `HH:MM` 或右侧边框。
- 扩展页按钮、输入、次要说明和禁用态统一复用 Desk 主题令牌，提高纸白灰主题下
  的文字与边框辨识度。
- Tomo 通知、事件和深夜休眠继续留在 QQ Bot 工具页；保存仍通过 Tomo v1 控制
  协议同步，Desk 不直接写 Tomo 配置。Yaki 设置同样保留在对应工具页。
- “设置 / 扩展工具”入口互换以及设置内新增独立“扩展”大项仅记录为后续观察，
  本轮不改导航，避免出现两套设置入口。
- QQ Bot 离线态的“启动 Tomo”改为单次到端：启动隐藏控制器、等待控制协议就绪、
  发出 start，并立即显示“扫码登录 QQ”层等待二维码。无需先等“正在打开”再点第二次
  启动；启动超时或环境错误才退出登录层并显示错误。
- 弹板原生命中/绘制区域为出现动画和顶部星星预留 12 px 外沿；避免
  `SetWindowRgn` 偶然在缩放动画中间锁定较小区域，造成顶部星角时有时无。
- 本批验证：`npm test` 全绿，`npm run build` 全绿，`cargo test` 为
  161 passed / 3 ignored；ignored 仍是明确的真实账户/付费请求。
