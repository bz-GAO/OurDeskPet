# 发布构建

> 工作区约定：所有源码、构建缓存、测试安装包与提交材料均放在名称带 `_test` 的开发工作区。无后缀的 `OurDeskPet` 目录只由安装包创建或更新，不作为源码仓库或构建目录。

## 使用者

从 Releases 安装。安装包包含三个组件、便携 Python 和媒体工具；普通使用不需要准备编译环境。QQ 服务另需 QQ / NapCat 及自己的账号。

## 构建者

本仓库是独立的发布树，开发历史保留在原三个组件仓库中。release-manifest.json 记录源码基线，发布限制与隔离修改在本仓库单独维护。

1. 准备 Windows Rust/MSVC、Windows SDK、Node.js 和 Python 3.14。
2. 在 RinaDesk/app 运行 `npm ci`。
3. 按 RinaYaki/pyproject.toml 准备含 live 与 webview 可选依赖的 Python 环境，按 RinaTomo/pyproject.toml 准备消息服务依赖。
4. 使用 scripts/prepare-runtime.py，将 Python 标准库、Tcl/Tk、所需依赖和 FFmpeg / yt-dlp 组装到本机忽略目录。该脚本需要明确给出 Python、依赖环境及媒体工具路径；不会复制任何用户配置。
5. 使用 scripts/collect-licenses.py 收集锁定依赖的许可；保留媒体工具来源、LICENSE 和对应源码信息。
6. 在 RinaDesk/app 运行 `npm test`、`npm run build`；运行两套 Python 离线回归。测试临时目录放在工作磁盘，勿使用真实 API Key。
7. 从根目录运行 `scripts/Build-Release.ps1`。输出在 artifacts，文件名为 `OurDeskPet-0.1.0-x64-setup.exe` 并附 SHA-256；可用 CacheRoot 指定已存在的增量缓存。

runtime、.venv、.tools、node_modules 和 artifacts 都不进入 Git。安装器通过资源清单打包它们。

原开发仓库中的本机快捷方式修复、安装清理和开发版构建脚本没有纳入发布工具链，避免误修改开发版安装。

## 版本与验收

公开发布使用一个统一版本；组件来源提交另行记录。安装注册、程序名和数据命名空间以 OurDeskPet 为准。发布版没有默认复制开发凭据或登录数据的迁移步骤。

在隔离目录验证首次安装、旧版维护、用户数据保留、组件加载和卸载后，再创建 GitHub Release。真实音频设备、QQ 登录和付费模型调用仍需使用者自己的环境验收。
