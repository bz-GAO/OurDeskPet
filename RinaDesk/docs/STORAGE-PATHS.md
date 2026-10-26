# OurDeskPet 运行时存储

发布程序通过可执行文件旁的 `release-manifest.json`、`rinadesk-root.txt` 和 `RinaDesk/release-profile.json` 确认安装根目录。启动时的工作目录不影响配置定位。

| 内容 | 安装根目录下的位置 |
| --- | --- |
| 桌面程序 | `OurDeskPet.exe` |
| 组件 | `RinaDesk`、`RinaYaki`、`RinaTomo` |
| Python 与公共依赖 | `runtime` |
| Desk 配置、用量及 WebView 数据 | `data/RinaDesk` |
| Yaki 配置 | `data/RinaYaki` |
| Tomo 配置 | `data/RinaTomo` |

Desk、Yaki、Tomo 各自保存配置与凭据。发布初始化设置固定的数据锚点，不自动导入开发版配置或私人音色。阿里云账务授权仍使用 Windows 用户的 DPAPI 加密。

用户明确选择的对话保存位置和视频工程目录保持其选择；修改保存位置不会自动搬动已有文件。生成数据、配置、媒体、账号缓存与构建缓存均排除在源码仓库之外。

选择安装父目录后，安装器在其下创建一层 `OurDeskPet`。静默安装 `/D=...` 参数仍表示完整目标路径。
