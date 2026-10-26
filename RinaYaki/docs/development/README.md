# RinaYaki 开发与维护

本页面向开发者或从源码准备环境的人；日常使用见[用户指南](../user/README.md)。

## 从源码准备环境

Windows 需要 Python 3.11+（含 Tk）。在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Setup-RinaYaki.ps1
.\Start-RinaYaki.cmd doctor
```

之后用 `Start-RinaYaki.vbs` 打开界面。运行环境、FFmpeg/yt-dlp 与实时依赖按安装脚本及[实时模块说明](../../src/rinayaki/live/README.md)核对；不把开发环境已配置当作安装包交付。当前桌面生产流程使用云端 API，保留的 Kotoba 等离线 provider 不等于默认工作流；程序不自动下载模型。

API 和模型默认值以 `src/rinayaki/settings.py` 为准，用户从设置页填写，不在手册维护第二份容易过期的模型表。`.env.example` 仅供命令行、兼容或测试参考。真实凭据、本机用户目录、视频、模型和缓存不得提交。

## 验证

在已准备依赖的项目环境中运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

常规测试使用替代云端响应，不运行付费 API smoke。真实 FFmpeg、GUI、音频设备或长视频需要另行验收，不能以单元测试通过代替。文档整理只核对现行源码、链接和差异，不触发媒体处理或付费服务。

## 维护规则

- 用户指南只写必要选择、自动发生的行为、产物位置和重要限制；模型请求、缓存键、数据结构、锁和重试留在技术专题。
- 修改共享设置和状态时，同步原生端、Desk 桥接及契约；产品行为变化再同步 `docs/ASSISTANT.md`。
- Git 默认仅保存本地检查点，用户明确要求时才推送。已有未提交变更不自动打包进本轮提交。
- 不为文档整齐随意更改协议、运行时指南或程序依赖的文件路径；技术专题见[索引](../README.md)。
