# 2026-09-13 整理及验证记录

## 功能修复

`pet_placement.rs` 在候选位置计算前检查人物底部 180×162 逻辑像素区域与可见聊天／设置窗口是否相交。使用人物当前屏幕的 DPI；透明宿主窗口上部不触发搬移。无相交返回 `side: unchanged`，不调用 set_position；相交仍采用原有右下优先和多窗口避让。

Rust 18 项测试通过，包括透明空白、贴边零相交、1像素相交、另一屏幕和缩放情况。独立 Windows 原生实例验证六种情况：首次聊天无相交不移动、聊天相交会移开、重复展开不再移动、首次设置无相交不移动、设置相交会移开、侧边无相交不移动。测试未访问真实 API。

## 文件范围

- 277 个过程图片、旧方案、参考、截图、旧文档及未用脚本已按清单移动到 `.local-archive/2026-09-13/project`，原件保留；上级的 moved-files.json 记录原路径、大小和 SHA-256。
- 另将仍被 index.html 引用的 Vite 图标替换为批准的璃奈 SVG，之后才归档 Vite 文件。
- 保留 20 个正式图片／图标，约 7.44 MiB。唯一正式人物目录为 app/public/assets/rina；保留 Tauri 配置需要的桌面图标和生成主图。
- Start-Rina.cmd 与 Develop-Rina.cmd 已归档。RinaDesk.lnk 仍在本机根目录且目标不变，但由 Git 忽略；终端操作写进 DEVELOPMENT.md。
- 旧阶段文档集中本地归档，README／DEVELOPMENT／ROADMAP 为当前入口。提示词研究与原创草稿单独存放，不修改实际 prompt。
- 清除 Cargo 配置内机器专属输出路径。当前本机 release 构建通过 CARGO_TARGET_DIR 继续写原缓存，新克隆可用 Cargo 默认目录。

## Git 行为

未 stage、commit、push 或重写历史。现有大量修改包含前几轮累计成果，不都来自本轮。旧文件在 git status 中显示 D 是本轮将其从提交目录移到本地归档的预期结果；原件可在本地归档查回。

`python scripts/check_repository.py` 检查正式图片哈希、提交候选图片白名单及 .env／快捷方式／归档排除。此检查不读取真实密钥内容，不替代人工审阅提交。

如需找旧记录：`.local-archive/2026-09-13/project/docs/DEV_LOG.md` 是完整旧开发日志；其余旧文档保持同级相对结构。历史提交中已经存在的旧图仍在 Git 历史，本轮没有清理历史。

最终复查：图片／Markdown／通知测试通过，正式 release 构建通过，当前文档相对链接无断链，277 个归档原件哈希一致。原有 RinaDesk.lnk 继续指向已更新程序。

