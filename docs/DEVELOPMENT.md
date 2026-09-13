# 开发、构建和本机启动

从仓库根目录进入 `app`，执行 `npm ci`、`npm run tauri dev`。需要 Visual Studio C++ 工具链和 Windows SDK；若提示找不到 RC.EXE，使用已加载开发环境的终端，或将已安装 SDK 的 x64 bin 目录加入本次进程 PATH。

## 构建与测试

```powershell
cd app
npm run build
node tests/art.test.mjs
cd src-tauri
cargo test
cd ..
npm run tauri build -- --no-bundle
```

浏览器 UI 测试使用 Playwright + Edge，需要另外提供 Playwright；先启动 Vite，再执行 `node tests/settings-ui.test.cjs`。原生几何逻辑另有 Rust 单元测试，不能用浏览器截图代替 Windows 原生验证。

仓库不提交机器专用的 Cargo 输出路径。默认使用 Cargo target；本机如需继续更新现有快捷方式的目标，在构建前设置：

```powershell
$env:CARGO_TARGET_DIR='E:\OurDeskPetBuildCache\cargo-target'
```

现有本机快捷方式 `E:\OurDeskPet\RinaDesk.lnk` 指向该缓存目录的 release 程序，工作目录为 `E:\OurDeskPet`。快捷方式仍留在根目录但由 Git 忽略；它包含绝对路径，不适合其他电脑直接使用。无需 Start-Rina.cmd 或 Develop-Rina.cmd，两份旧脚本已本地归档。终端启动现有正式版：

```powershell
Set-Location E:\OurDeskPet
& E:\OurDeskPetBuildCache\cargo-target\release\our-desk-pet.exe
```

## API 与提示词

设置页新增／编辑／保存／启用 OpenAI 兼容 API；切换在下一次请求生效。`.env` 使用 `OURDESKPET_PROFILE_<代号大写>_{NAME,BASE_URL,API_KEY,MODEL}` 和 `OURDESKPET_ACTIVE_PROFILE=<小写代号>`，旧单组配置仍支持。密钥留空编辑表示保持原值。

文件修改会在设置页轮询及聚焦时同步；存在草稿冲突时不覆盖草稿。不要提交 `.env`。角色提示词默认读取 `prompts/rina_system_prompt.md`，支持 `OURDESKPET_PROMPT_FILE` 与内联覆盖；研究草稿不会自动加载。

## 提交前

`git status --short` 和 `git diff --stat` 查看变动。正式图片以 `assets/manifest.json` 为清单；所有参考原图、评审图、旧方案、日志截图、本机快捷方式和过程文档放在 `.local-archive` 或被忽略。不要用 `git add -f` 加入这些内容。运行 `python scripts/check_repository.py` 检查图片清单与提交候选范围。

本轮只整理工作区，未自动 stage、commit、push，也未改写历史。历史提交若曾包含旧图，删除工作区文件不会将它从历史移除。
