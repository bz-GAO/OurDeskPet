# RinaDesk 安装器页面预览

更新日期：2026-10-25。以下图片来自工作区顶层 `RinaDesk-preview-x64-setup.exe` 的真实 Windows 原生窗口，不是网页复刻。

自动验收使用 Windows UI Automation 和原生窗口截图，不使用 CUA。首次安装通过 NSIS `/D` 参数进入工作区顶层 `.rinadesk-installer-review`；随后真实启动同版本安装页、临时把测试登记版本改为 `0.0.9` 验证更新页，恢复后调用卸载器。验收结束已确认测试目录、卸载登记、进程与桌面快捷方式均未残留。

| 顺序 | 页面 | 当前行为 |
| --- | --- | --- |
| 1 | [语言](screenshots/01-language.png) | 居中的“选择语言”与下拉框；简体中文默认选中，可切换 English |
| 2 | [欢迎](screenshots/02-welcome.png) | 当前仍使用 NSIS 默认欢迎布局 |
| 3 | [协议占位](screenshots/03-agreement-placeholder.png) | 勾选接受后“下一步”才可用；正式文本尚未编写 |
| 4 | [安装位置](screenshots/04-install-location.png) | 显示真实目标、占用与可用空间，可浏览修改 |
| 5 | [安装进度](screenshots/05-install-progress.png) | 单项只显示当前动作；总进度由进度条表示，不开放详情 |
| 6 | [完成](screenshots/06-finish.png) | 成功后自动进入；启动程序和创建桌面快捷方式均默认不勾选 |
| 7 | [已是当前版本](screenshots/07-current-version.png) | 默认修复当前版本，也可卸载；用户数据默认保留 |
| 8 | [旧版本更新](screenshots/08-update-version.png) | 默认更新到安装包版本，也可直接覆盖程序文件 |

## 待审核与待实现

- 欢迎页和完成页已接入用户确认的墨绿像素璃奈竖幅。无损源图位于 `app/src-tauri/installer/art/sidebar-rina-source.png`，NSIS 使用同目录下的 164 × 314、24 位 `sidebar-rina.bmp`。
- `app/src-tauri/installer/PREVIEW-LICENSE.txt` 是开发占位。正式发布前必须补齐正式协议与第三方许可清单。
- Yaki/Tomo 选择页只有在版本化发行物、下载体积、SHA-256、许可和兼容协议齐全后才显示；当前没有灰色占位页。
- 当前实现覆盖本地安装包的更新底线。连接 GitHub Release、签名校验、自动更新和回滚仍属于后续阶段。
- 干净 Windows 虚拟机验收时，可将顶层 Setup.exe 通过 VirtualBox 共享文件夹复制进虚拟机，再断开共享目录进行离线／联网两轮测试；不要直接从共享目录运行安装器。

重新生成截图：先构建预览，再运行 `scripts/Capture-InstallerPreview.ps1`。脚本只接受固定 E 盘测试目录；若该目录已存在会拒绝覆盖。
