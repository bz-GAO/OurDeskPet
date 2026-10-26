# OurDeskPet

面向教与学的个性化桌面 AI 助手。作者：[@bz-GAO](https://github.com/bz-GAO)。

## 下载与说明

- [Windows x64 安装包](https://github.com/bz-GAO/OurDeskPet/releases/latest/download/OurDeskPet-0.1.0-x64-setup.exe) · [SHA-256](https://github.com/bz-GAO/OurDeskPet/releases/latest/download/OurDeskPet-0.1.0-x64-setup.sha256)。
- [PDF 用户手册](https://github.com/bz-GAO/OurDeskPet/releases/latest/download/OurDeskPet-User-Manual.pdf) · [全部版本](https://github.com/bz-GAO/OurDeskPet/releases)。
- [用户手册](docs/用户手册.md)。
- [发布构建说明](docs/BUILDING.md)。
- [使用与资源许可](LICENSE.txt)：项目自有内容未经书面许可不得商用；素材传播须获相应权利人许可；第三方依赖遵循其原许可。

安装时选择父目录，安装器会在其下创建 `OurDeskPet`。例如选择 `E:\`，程序安装到 `E:\OurDeskPet`。三个组件与便携运行时一并安装；模型功能需要配置自己的 API，QQ Bot 还需要自行准备 QQ 与 NapCat。

## 三个组件

| 目录 | 功能 |
| --- | --- |
| RinaDesk | 桌宠、Chat、项目助手、语音与任务卡 |
| RinaYaki | 视频字幕提取、翻译、导出与实时字幕 |
| RinaTomo | QQ 消息服务、权限与任务提醒 |

本仓库保存经过筛选的发布版本。开发历史仍由三个独立开发仓库维护；版本对应关系见 [release-manifest.json](release-manifest.json)。

## 发布隔离

发布程序名为 `OurDeskPet.exe`，应用 ID 为 `com.bzgao.ourdeskpet`，与开发程序分开安装登记、WebView 数据和开机启动项。
用户数据位于安装目录下的 `data/RinaDesk`、`data/RinaYaki`、`data/RinaTomo`，不迁移开发凭据或私人音色。Tomo 控制端口为 37642，默认 OneBot 端口为 3002。
发布版仅包含一套默认像素人物；保留用户导入自有图片的能力。TTS 使用官方基础音色。三个组件内置接入，隐藏手动插件管理。

公开源码不等同于授予任意用途许可。素材和第三方依赖不因放入仓库而转移权利。
