# 音乐转 MP3

Windows 桌面批量音频转换工具。添加歌曲、选择目录，点击开始；无需命令行。

当前版本：**0.1.0-beta.1**。原文件保留，默认不覆盖同名输出。

**[下载 Windows 便携版](https://github.com/embedded-craft-dong/QQMusicConverter/releases/tag/v0.1.0-beta.1)** · [更新记录](CHANGELOG.md)

## 使用

解压发行 ZIP，双击 `QQMusicConverter.exe`。普通音频无需安装 Python、无需登录。

1. 点击“添加文件”或“添加文件夹”（只扫描当前目录，不递归）。
2. 选择输出位置。软件只记住这个目录。
3. 普通音频直接开始；支持的加密文件需要先打开并登录 QQ 音乐，再主动勾选登录选项。
4. 查看当前歌曲的处理阶段、百分比和批量总进度。失败项可以单独重试。
5. 点击“打开输出文件夹”查看结果。双击歌曲行查看完整路径和结果。

Ctrl+O 添加文件，Delete 移除选中项，Escape 停止当前任务。
复选框选中显示勾号；Tab 可移动焦点、空格可切换选项。
窄窗口可滚动内容，底部开始/停止按钮保持可见。

## 支持范围

| 输入 | 支持情况 |
| --- | --- |
| 普通 OGG、WAV、FLAC、MP3 | 支持 libsndfile 可解码的文件；单/双声道 |
| `musicex` v1 尾部的 QMC2 文件 | 实验性支持，通常为新版 MGG/MFLAC；需要匹配歌曲的密钥 |
| 其他旧 QMC、其他尾部版本 | 不支持；后缀相同也不保证兼容 |

输出为高质量 VBR MP3，保留输入采样率及声道数。采样率支持
8000、11025、12000、16000、22050、24000、32000、44100、48000 Hz。
不自动重采样，不保留封面、歌词和标签。MP3 为有损格式，转换不会提高原始音质。
为开发板准备 48 kHz / 16-bit WAV 的功能不在此版本中。

## 隐私与取消

普通音频转换全程离线。登录选项每次启动默认关闭，覆盖选项也不会记忆。
启用登录选项并开始处理加密文件时，程序会扫描 QQMusic 进程的可读内存查找 `authst`，
读取 QQ 音乐配置中的账户编号，向 `https://u.y.qq.com/cgi-bin/musicu.fcg`
请求该文件对应的歌曲密钥。没有第三方上传、遥测或自动更新。
扫描不是公开的登录接口，客户端或接口变更可能导致失败。

一次批量任务只扫描一次，会话只在内存中保留到任务结束；不写入配置、日志或发行包。
扫描最多尝试读取 512 MiB（计入失败读取和重叠区域），扫描循环限时 12 秒；查找进程另限时 5 秒。
密钥请求最多尝试三个候选会话，设有请求期限检查和 8 秒网络阻塞超时。
具体细节见 [隐私说明](docs/PRIVACY.md)。仅处理你有权访问和转换的本地文件。

“停止”在读取、还原、校验、编码阶段协作取消；临时文件会清理，已有输出与原件保留。
已完成的歌曲保留。正在进行的网络或系统调用可能需要等待返回/超时，不能承诺瞬间终止。
已经提交完成的文件也不会因随后点击停止而删除。

## 从源码运行与构建

使用 Windows x64、Python 3.12（带 Tcl/Tk）。本次构建使用 Python 3.12.14。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python music_gui.py
.venv\Scripts\python scripts/build_release.py
```

构建脚本会运行测试、收集许可证、生成图标、打包无控制台 EXE，并产出：

- `dist/QQMusicConverter.exe`：双击运行。
- `release/QQMusicConverter-0.1.0-beta.1-windows-x64.zip`：完整便携发行包。
- `release/QQMusicConverter-0.1.0-beta.1-source.zip`：经白名单筛选的源码。
- `release/SHA256SUMS.txt`：校验值。

依赖版本固定，但不同 Python、Windows、工具链或构建时刻的 EXE 不保证逐字节一致。
构建无须真实歌曲、QQ 音乐账户、密钥或网络请求；依赖需事先安装。

可选命令行接口：

```powershell
python convert_music.py "C:\Music\song.ogg" -o "C:\Music\Converted"
python convert_music.py "C:\Music\song.mgg" --qq-login -o "C:\Music\Converted"
```

`--ekey-file` 只用于单个文件自己的密钥，不适用于批量共享；请勿上传密钥文件。

## 测试与已知限制

自动测试生成正弦波与合成加密文件，覆盖转换、TEA 已知向量、损坏文件、取消清理、
防覆盖、进度、批次会话复用（模拟接口）、GUI 重试和 100%/125%/150%/200% 的小屏布局。
测试不会扫描真实 QQ 音乐进程，也不访问在线密钥接口。

维护者已完成本机试用并反馈运行正常；真实在线取密钥分支仍受账户和客户端版本影响。
布局自动测试不等于所有显卡、显示器与系统字体下的视觉验证。
此版本未签名，且尚未在独立的无 Python Windows 10/11 机器上验收。
请见 [发行验收记录](docs/RELEASE_CHECKS.md)，提交问题时只提供已脱敏的信息。

## 项目结构与发布

`music_gui.py` 负责界面和后台任务；`ui_theme.py` 负责样式与勾选图标；
`convert_music.py` 负责转换校验；`qmc_core.py` 负责解码；`qq_session.py` 为可选登录适配层；
`job.py` 提供取消与批次会话生命周期；`settings.py` 仅保存输出目录。

源码仓库不要提交音乐、密钥、凭据、个人设置、构建缓存或 EXE。
源码 ZIP 已按白名单排除这些内容；发行 ZIP 与校验值应作为 GitHub Releases 附件。
CI 仅测试和构建供下载的 artifact，不自动创建公开 Release。

## 许可证

本项目以 GPL-3.0 发布，完整文本见 [LICENSE](LICENSE)。
解码实现移植参考 [ownlight6/qmc-decoder](https://github.com/ownlight6/qmc-decoder)
及 [tc_tea](https://github.com/jixunmoe/tc_tea_rust)。保留上游授权和署名。
发行包附对应项目源码、构建脚本和第三方许可；依赖各自保持原许可证。
详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本项目非 QQ 音乐官方产品。
