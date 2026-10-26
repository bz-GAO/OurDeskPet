# 视频处理与字幕契约（开发文档）

本文合并原 `THREE-STAGE-WORKFLOW.md` 与 `SUBTITLE_EXPORT.md` 中仍有效的技术边界。用户操作统一见[用户指南](../user/README.md)，不再保留旧施工顺序、过时模型列表或单次素材测试作为当前功能说明。

## 页面与任务边界

桌面流程为预览、工程设置、处理、样式与导出。工程设置在开始前确定目录、名称和语言；默认保存目录由设置服务提供。新任务直接写入目标工程，旧缓存任务保留验证后发布路径，详见[项目存储](../PROJECT-STORAGE.md)。

预览只做来源/元数据/封面检查，不启动云端转写。处理阶段依次准备输入、ASR、翻译和按配置精修，持久化 `prepared.json` 后才允许继续。UI 使用 `--phase prepare`，确认样式后使用 `--phase export`；显式无界面 CLI 仍可使用 `--phase all`。

导出读取已准备数据，不重发云端转写/翻译。样式与字体变化进入内容指纹，产生版本化输出。翻译/精修可按完成 cue 数显示进度；ASR 显示服务任务状态与耗时，不制造文件内识别百分比。网页解析、下载或复制进度与 ASR 进度不是同一指标。

## 说话人和样式

识别结果中的 speaker group 是模型分组，不是人物姓名；全片只有一个组不证明实际只有一个人。试听是短源音频片段，不是分离后的纯人声。不得根据字幕内容擅自认定人物。

样式保存于 `intermediates/styles.json` 并绑定准备结果指纹，按分组选择字体、预设或自定义描边色。当前字体、颜色与默认值由实现提供；不要把早期 CLI 默认字体描述成桌面默认。导出布局与尺寸见[作业专题](../PIPELINE-JOBS.md)。

## 数据与格式

版本化 JSON 保存时间轴、原文、译文、speaker 信息与来源，是生成字幕的结构化输入。SRT/VTT/ASS 为输出，不从排版结果反向恢复权威数据。缺少译文时，translated/bilingual 导出应报错，不混入空字幕或原文充数。

| 格式 | 边界 |
| --- | --- |
| SRT | 通用字幕交换，不可靠地携带字体样式 |
| VTT | 网页字幕，展示可由播放器控制 |
| ASS | 字体、颜色、描边、位置及双语样式 |
| MP4 | 默认顶层观看产物，字幕烧录到画面 |
| MKV | 保留可开关的软字幕轨与字体，存于子目录 |

文件名带语言与版本信息；日语→简中只是一个例子，不是固定方向。语言传播、旧工程兼容和缓存验证见[语言契约](../LANGUAGES.md)，目录和原子完成规则见[作业专题](../PIPELINE-JOBS.md)。

## 高级 CLI 导出

以下仅面向开发调试，从项目根目录运行；不会替代 GUI 的自动流程：

```powershell
.\.venv\Scripts\rinayaki.exe export-subtitles transcript\raw.json --output-dir subtitles --stem episode-01 --mode source --formats json srt vtt ass
.\.venv\Scripts\rinayaki.exe export-subtitles translation\reviewed.json --output-dir subtitles --stem episode-01 --mode bilingual --formats srt vtt ass
```

第二条需要输入已有译文。完整流水线 CLI 会调用付费 API；上述已有字幕导出与重新推理必须区分。

## 验证与来源

验证准备/导出隔离、多分组样式、内容版本、缺译文拒绝、恢复与并发写入保护。使用替代云端响应和可选 FFmpeg fixture，不把 fixture 分组当作真实多说话人准确率证明。开发过程中的后台视频研究和测试播放默认静音，除非用户要求听音频；这不改变软件中用户主动试听的行为。

字体与样式来源保留：[Nijigumi 样式](https://github.com/sora-jpht/nijigumi_subtitle_styles)、[GenSen Rounded](https://github.com/ButTaiwan/gensen-font)。授权、字体打包与署名按资源原许可证维护，不因文档合并而移除。
