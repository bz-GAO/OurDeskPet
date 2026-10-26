# 第三方内容与许可

## 许可范围

根目录 `LICENSE.txt` 的非商业限制只适用于项目自有内容。下面列出的依赖、运行时、字体和媒体工具继续遵守各自许可，不因本项目的条款而失去原有授权。

## 软件与运行时

| 内容 | 来源与许可入口 | 随包位置 |
| --- | --- | --- |
| Python 3.14.3 / Tcl / Tk | [Python 许可](https://docs.python.org/3/license.html)及分发包内的许可文本 | `runtime/python/LICENSE.txt`、`runtime/python/tcl/` |
| Python 依赖 | 各发行包的 `METADATA`、`licenses` 和 `LICENSE` | `runtime/site-packages/*.dist-info/` |
| FFmpeg / FFprobe | [FFmpeg 许可](https://ffmpeg.org/legal.html)、[所用构建提供方](https://www.gyan.dev/ffmpeg/builds/) | `RinaYaki/.tools/ffmpeg/`；同目录提供所用分发包的 LICENSE |
| yt-dlp | [项目与许可](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE) | `RinaYaki/.tools/yt-dlp.exe` |
| Tauri、React、KaTeX 等前端／Rust 依赖 | 各项目原许可，依赖版本见 package-lock.json 和 Cargo.lock | 源码锁文件；安装包内 `THIRD-PARTY-LICENSES.txt` |
| 字幕字体 | 以字体资源旁随附的原许可为准 | `RinaYaki/assets/` |

发布包中的媒体工具未作修改；相关构建选项、版本及匹配源代码信息应与随包记录一并保留。不要把第三方软件描述为由本项目独占许可。

本轮 FFmpeg / FFprobe 来自 `9.0.1-essentials_build-www.gyan.dev`，上游分发说明明确标为 GPL v3，并给出匹配的 [FFmpeg 源码提交 bf1b838f2a](https://github.com/FFmpeg/FFmpeg/commit/bf1b838f2a)。该构建的 LICENSE 与 README 需保留在媒体工具目录中。

## 角色、美术与声音

像素人物与璃奈板包含角色相关表达。项目署名不代表取得角色或第三方素材的全部权利；本文件不为这些内容作权属转让或额外授权。

发布版仅保留默认像素人物及运行所需板面，其他人物库和私人实验音频不进入安装资源。语音合成使用服务商基础音色；不携带来源录音、私人克隆音色 ID 或私人语音包。

自行导入的图片、音频及视频由使用者确认其使用权限。模型服务、QQ、视频站点和 NapCat 分别遵循其自身服务条款或许可；安装三个项目组件不表示已取得第三方服务账号、配额或素材授权。
