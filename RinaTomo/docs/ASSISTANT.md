# RinaTomo 简要使用指南

维护日期：2026-10-11。本文随项目功能修改，由 Desk 项目助手在每次提问时读取。

RinaTomo 是独立 QQ Bot。Desk → 扩展工具 → QQ Bot 可以管理它，原生面板也可单独运行。

1. 首次准备 NapCat Shell 和 QQ NT，在 Tomo 设置中确认检测结果。
2. 点击“启动”，需要时扫描界面显示的 QQ 登录二维码。
3. 配置管理员、允许私聊用户和启用群聊，并应用修改；未放行的用户/群默认拒绝。

大模型对话使用 Tomo 自己的 API 配置，Desk Chat 的密钥不会自动写入 Tomo。
“打开控制面板后自动启动 Bot”默认关闭。首次打开不会自动启动消息服务。

独立启动时关闭原生窗口会退出服务及由本次 Tomo 启动的 NapCat/QQ。
Desk 托管时关闭面板或离开工具页只隐藏界面；退出整个 Desk 或关闭服务才结束托管运行。
外部已经运行的 NapCat 不会被接管关闭。

源码入口：`docs/CONTROL-PROTOCOL.md`、`src/`、`scripts/`。
Desk 集成界面在 Desk 的 `app/src/extensions/rinatomo/`；双方行为以控制协议核对。
Tomo 定位沿用 Desk 启动器的同级项目约定；移动整组项目后重新定位 Desk，不能靠聊天指定磁盘路径。
助手只能解释和核验受限源码，不能登录 QQ、读取账号/密钥、修改白名单或启动服务。
