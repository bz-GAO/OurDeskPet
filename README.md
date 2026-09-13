# RinaDesk Agent

Windows 桌宠，使用 Tauri 2、React、TypeScript 和 Rust。当前提供璃奈夏服、冬服和 Astromeda 单图三套外观，电子璃奈板控制、独立聊天与设置窗口。

- 夏／冬服包含待机、拖动、说话、睡眠状态；美术在设置页预览后启用。
- OpenAI 兼容的流式聊天、停止回复、Markdown 代码高亮和公式、图片附件与 Windows 截图粘贴。
- 设置管理多组 API；支持手工编辑 `.env` 后重新识别。
- 回复完成提醒、未读点和任务栏提示；展开面板只在人物确实遮挡时移动桌宠。

## 启动与开发

准备 Windows、Node.js/npm、Rust MSVC、Visual Studio C++ 工具与 Windows SDK、WebView2。

在仓库根目录的 PowerShell 中：

```powershell
Copy-Item .env.example .env
cd app
npm ci
npm run tauri dev
```

只在首次配置时复制 `.env.example`，不要覆盖已有配置。也可在设置页添加 API。纯网页预览使用 `npm run dev`，原生窗口功能需要 Tauri。

构建：在 `app` 中运行 `npm run tauri build -- --no-bundle`。默认程序在 `app/src-tauri/target/release/our-desk-pet.exe`；设置 `CARGO_TARGET_DIR` 后改用指定目录。构建与本机快捷方式说明见 [开发说明](docs/DEVELOPMENT.md)。

## 目录

| 路径 | 内容 |
| --- | --- |
| `app/src`、`app/src-tauri/src` | 前端与 Rust 源码 |
| `app/public/assets/rina` | 唯一的正式人物和板面图片 |
| `app/src-tauri/icons` | 桌面应用实际使用的图标 |
| `assets` | 图片来源、SHA-256 清单和图标 SVG 源文件 |
| `prompts/rina_system_prompt.md` | 当前实际使用的提示词 |
| `docs` | 当前说明、路线图、提示词研究草稿 |
| `.local-archive` | 本地原始参考、生成过程和旧文档，不提交 |

文档入口：[docs/README.md](docs/README.md)。提示词研究仅为草稿，未替换运行提示词。

角色和商品形象来自 Love Live! 虹咲相关作品；图片来源与处理方式见 [素材说明](assets/README.md)。这是非官方个人项目，素材记录不等于对原角色及参考图的授权声明。
