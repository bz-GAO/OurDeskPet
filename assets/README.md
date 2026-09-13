# 正式素材与来源

正式图片只有一份，位于 `app/public/assets/rina`；Tauri 构建图标位于 `app/src-tauri/icons`。完整路径、字节数、SHA-256 和来源分组见 [manifest.json](manifest.json)。更新图片时同步清单，运行 `python scripts/check_repository.py` 验证。

| 资源 | 处理与来源 |
| --- | --- |
| `summer-v1/{idle,drag,talk,sleep}.png` | 夏服开衫方案，按动画第一季宣传立绘做 Q 版重绘。待机／拖动经服装校对，说话／睡眠来自批准的双姿势图；本地抠图、边缘清理和统一画布 |
| `winter-v1/{idle,drag,talk,sleep}.png` | 冬服外套方案，按第二季宣传立绘；说话／睡眠沿夏服姿势转换冬服。两种制服名称按项目美术方案区分，不表示一季只能穿一种服装 |
| `rina-idle-v1.png` | Astromeda 商品造型参考重绘，去掉展示底座／背景，保留原版通用单图 |
| `boards/paper-v3.png` | 动画纸板参考重绘，聊天中裁切为浅色背景 |
| `boards/electronic-v3.png`、`electronic-blank-v3.png` | 电子板表情与空屏图，供遮罩／提示使用 |
| `boards/electronic-faithful.svg` | 嵌入表情图并裁去外部背景的正式显示资源；不是完全矢量重画，依然保留栅格像素 |
| `icon.svg` 与 Tauri 图标 | 用户批准的璃奈应援标志重绘与尺寸导出；SVG 同时用作网页图标 |

来源链接记录在 manifest：制服为 SPICE／Comic Natalie 动画宣传图；Astromeda 为商品页；纸板为 Animate Times，电子板为动画第6话相关画面。图标依据之前留存的角色资料，旧 SIF2 页面现已失效（本次 404），没有把失效链接伪称为当前可访问授权。

原始参考、生成提示、弃稿、抠图脚本和评审截图已归档到 `.local-archive/2026-09-13/project`，保留原相对结构及 `moved-files.json` 哈希记录，不提交。资源可追踪不要求把所有过程图片放进 Git。

这些是非官方角色衍生素材。来源标注与 AI 重绘过程不改变原角色、商品形象或参考画面的权利归属；本仓库没有替原权利人授予这些内容的许可。
