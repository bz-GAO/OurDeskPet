# RinaDesk 源码开发

完整发行构建以仓库级[构建说明](../../docs/BUILDING.md)为准。开发技术为 Tauri 2、React、TypeScript 和 Rust，需要 Windows Rust/MSVC、Windows SDK、Node.js 与 Python。

在 `RinaDesk/app` 运行 `npm ci` 安装前端依赖，再运行 `npm run tauri dev`。发布树仍依赖仓库根目录的组件和 `release-manifest.json`，请保留完整目录结构。

## 检查与构建

在 `RinaDesk/app` 运行 `npm test` 和 `npm run build`；Rust 检查在 `src-tauri` 运行 `cargo test`。付费和联网用例按现有忽略规则处理。

正式安装包使用仓库根目录 `scripts/Build-Release.ps1`，输出位于忽略目录 `artifacts`。构建缓存默认保存在 `.build-cache`。Cargo 缓存包含绝对路径，移动源码目录后可能需要清理缓存。

## 文档与配置

面向使用者的行为以仓库级[用户手册](../../docs/用户手册.md)为准；源码专题见[文档索引](README.md)。发布数据路径见[存储约定](STORAGE-PATHS.md)。

源码不包含真实 API Key、账务授权、账号缓存、私人录音或个人音色。贡献前检查差异与 `git diff --check`，运行仓库根目录的 `scripts/check-release.py` 审计源码候选，再建立本地提交。只有明确要求推送或发布时才更新远程仓库。
