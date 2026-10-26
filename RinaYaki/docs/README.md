# RinaYaki 文档索引

## 面向用户

日常使用只需[用户指南](user/README.md)：配置一次 API，提交视频或开始实时翻译，了解处理结果、费用与恢复边界。旧的开户教程、流程讲解和导出说明已合并，不再要求用户阅读流水线实现或手动填环境文件。

## 面向开发与维护

以下均为技术文档，不是用户必须完成的操作步骤。保留既有专题路径，避免破坏桥接和源码阅读引用。

| 文档 | 维护范围 |
| --- | --- |
| [开发入口](development/README.md) | 源码安装、验证、文档维护和本地检查点 |
| [视频处理与字幕契约](development/VIDEO-WORKFLOW.md) | 页面与 prepare/export 边界、字幕格式及 CLI；合并原流程和字幕说明 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 模块、离线与实时边界 |
| [SETTINGS.md](SETTINGS.md) | 配置所有权、凭据、任务快照 |
| [PROJECT-STORAGE.md](PROJECT-STORAGE.md) | 项目布局、定位、旧任务迁移 |
| [PIPELINE-JOBS.md](PIPELINE-JOBS.md) | 作业执行、缓存、产物和回归测试 |
| [UI-AND-RECOVERY.md](UI-AND-RECOVERY.md) | 站点能力、登录隔离、工作进程与失败恢复 |
| [LANGUAGES.md](LANGUAGES.md) | 语言参数传播与缓存身份 |
| [LIVE-CONTROLS.md](LIVE-CONTROLS.md) | 暂停、恢复、流式显示与生命周期 |
| [TRANSLATION-GUIDANCE.md](TRANSLATION-GUIDANCE.md) | 术语检索及模型参数映射 |
| [DESK-BRIDGE.md](DESK-BRIDGE.md) | Desk 接口契约 |
| [AUTHENTICATED-VIDEO-DESIGN.md](AUTHENTICATED-VIDEO-DESIGN.md) | 登录视频的安全边界 |
| [实时模块说明](../src/rinayaki/live/README.md) | 实时依赖、运行和实现限制 |

## 面向内置助手

[ASSISTANT.md](ASSISTANT.md) 是 Desk 按固定路径读取的精简产品知识，不是额外用户手册，也不是开发代理的指令。用户行为变化需同步它；开发细节不堆入该文件。
