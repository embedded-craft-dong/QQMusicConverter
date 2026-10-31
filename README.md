# QQMusicConverter · Music Asset Workbench

**English** | [简体中文](README.zh-CN.md)

A Windows desktop tool for preparing audio, synchronized lyrics, and album artwork for everyday listening and embedded music players.

**[Download for Windows x64](https://github.com/embedded-craft-dong/QQMusicConverter/releases/tag/v0.3.0-beta.1)** · [Changelog](CHANGELOG.md) · [Privacy](docs/PRIVACY.md) · [Validation](docs/RELEASE_CHECKS.md)

Current version: **0.3.0-beta.1**. Extract the portable ZIP and run `QQMusicConverter.exe`; no Python installation is required.
The application interface is currently Simplified Chinese. The button guide below helps English-speaking users navigate it; an English interface is not included in this release.

## Features

- Batch conversion to high-quality VBR MP3 or board-ready 48 kHz / 16-bit / stereo PCM WAV.
- Independent batch export of timestamped UTF-8 LRC lyrics and JPG artwork, with optional automatic export during conversion.
- Lyric preview, millisecond timing adjustment, and shared output names for audio, lyrics, and artwork.
- Local audio information and embedded artwork; optional QQ Music metadata and album artwork lookup by an explicit song ID.
- Convert all or selected files, retry only failed tasks, cancel cooperatively, and locate generated files.
- Original-file protection, atomic output publication, and full decoding verification of converted audio.

## Quick start

1. Add files or a folder. Folder scanning covers only the selected directory, not its subdirectories. `Ctrl+O` also opens the file picker.
2. Choose an output directory and an MP3 or WAV preset.
3. Optionally enable automatic lyric or artwork export. Both options are off by default.
4. Convert the entire queue, or select one or more rows and convert only those files.
5. Open the output folder, or right-click a song to locate a generated file.

Lyrics and artwork can also be exported independently: select one or more songs and use the corresponding buttons.
Audio, lyric, and artwork results are tracked separately. Retrying failed lyrics or artwork does not re-encode successful audio.
Stopping preserves completed files and cleans up temporary output. A blocking network call may need to return or time out before cancellation takes effect.

| Chinese interface label | Meaning |
| --- | --- |
| 添加文件 / 添加文件夹 | Add files / Add folder |
| 选择位置 | Choose output directory |
| 高质量 MP3 / 开发板 WAV | High-quality MP3 / Embedded-player WAV preset |
| 转换全部 / 转换选中 | Convert all / Convert selected |
| 导出歌词 / 保存封面 | Export lyrics / Save artwork |
| 重试失败项 / 停止 | Retry failed tasks / Stop |
| 打开输出文件夹 | Open output folder |
| 名称与歌曲信息 | Output name and song information; double-click one song to open |
| 歌词预览与偏移 | Lyric preview and timing adjustment |
| 获取歌词预览（联网） | Fetch lyric preview (online) |
| 保存预览为同名 LRC / 应用设置 | Save preview as LRC / Apply settings |
| 转换后自动导出歌词 / 转换后保存封面 | Automatically export lyrics / artwork during conversion |
| 使用本机 QQ 音乐登录状态处理加密歌曲 | Opt in to the local QQ Music login adapter for encrypted audio |
| 覆盖已有同名音频（歌词与封面不覆盖） | Overwrite existing audio; LRC/JPG files remain protected |

## Output presets and filenames

| Preset | Output | Typical use |
| --- | --- | --- |
| MP3 | High-quality VBR; original sample rate and mono/stereo channel count | General playback |
| WAV | RIFF/WAVE PCM, 48,000 Hz, 16-bit, stereo | DMA / I2S / SD-card players |

The WAV preset uses SoXR HQ streaming resampling, duplicates mono audio into both channels, and clips samples to the PCM16 range.
Every conversion fully decodes the output to verify its parameters and duration. Duplicating mono does not create a stereo recording, and conversion does not improve the source recording's quality.
Stereo PCM16 at 48 kHz uses about 192,000 bytes per second, or 46 MB for four minutes. Multichannel downmixing is not supported.
The MP3 preset accepts 8 / 11.025 / 12 / 16 / 22.05 / 24 / 32 / 44.1 / 48 kHz; MP3 encoding is lossy.

Double-click a song and set a shared filename without an extension, such as `track01`. Outputs use that name:

- `track01.mp3` or `track01.wav`
- `track01.lrc`
- `track01.jpg`

The source filename is used by default. Names cannot contain paths or Windows-reserved characters.
Duplicate output names are rejected before a batch starts. Audio overwrite settings do not apply to LRC/JPG files: choose another name or folder if those files already exist.
Output cannot replace any original audio file in the queue. Song links, custom names, and timing adjustments last only for the current application session.

## Lyrics and timestamps

Supported `musicex` v1 files provide a song ID automatically. For ordinary MP3/OGG/WAV/FLAC files without an identifiable ID, double-click the song and enter its QQ Music song-detail URL or 14-character `songmid`.
Supported links include `https://y.qq.com/n/ryqq/songDetail/SONGMID`. Open shortened share links in a browser first, then copy the song-detail URL.
The application does not guess a match from the filename: live recordings, studio recordings, and edits can have different timelines.

In the lyric preview tab, fetch lyrics and adjust timing in milliseconds. **Positive values delay lyrics; negative values advance them.**
The preview updates immediately; saving or batch export applies the same adjustment. The range is ±600,000 ms.
LRC files use UTF-8 and `[mm:ss.xx]` timestamps. Repeated timestamps are expanded, and the source LRC offset is applied before the user adjustment.
Original LRC offset tags use their own convention: a positive tag advances lyrics. Exported files contain adjusted timestamps rather than an offset tag.

Lyrics are retrieved from an online service, not transcribed from audio. Missing lyrics, untimed text, and unavailable services produce an error instead of fabricated timestamps.
Word-level karaoke timing and translated lyric tracks are not exported. Check synchronization against the exact audio version being played.

## Artwork and song information

Artwork export first checks ordinary files for embedded images: MP3/WAV APIC frames, FLAC picture blocks, or OGG `metadata_block_picture` tags.
If no usable image is found and a song ID is available, it fetches QQ Music album information and artwork. Encrypted files can use their song ID without being decrypted again.
Images are exported as separate JPG files, preserving dimensions and removing attached metadata; artwork is not embedded into the output MP3.
Downloads are limited to 12 MiB and decoding to 16 million pixels. Online image quality depends on the artwork supplied by the service.

Song information includes duration, title, artist, album, and available sample rate, channels, format, and encoding.
Ordinary files are inspected locally. Reading information for encrypted files explicitly queries online song metadata; after conversion, technical parameters describe the output audio.
The application does not guess technical parameters for audio it has not decoded.

## Input support and privacy

| Input | Support |
| --- | --- |
| Ordinary OGG / WAV / FLAC / MP3 | Mono or stereo files supported by libsndfile |
| QMC2 with a musicex v1 footer | Experimental; commonly newer MGG/MFLAC files, requiring the matching song key |
| Older QMC or other footer versions | Unsupported; a matching extension does not guarantee compatibility |

Ordinary conversion, local metadata inspection, and embedded-artwork extraction work offline.
Requested online lyrics, artwork fallback, and song information send only song/album IDs to QQ Music.
These operations do not upload audio, lyrics, local filenames, or paths, and do not read login sessions.
Online services may become unavailable because of permissions, removed content, or API changes.

The optional login adapter for encrypted audio is **off by default**.
When explicitly enabled, it reads QQMusic process memory to find `authst`, reads the account number from QQ Music configuration,
and sends the session, account, embedded song ID, and embedded filename to the official `u.y.qq.com` key endpoint.
Sessions are reused within a batch and references cleared afterward; credentials and keys are not saved or logged.
Only process local files that you are authorized to access and convert. See [Privacy](docs/PRIVACY.md) for exact limits and data flows.

Only the output directory is persisted. There is no telemetry, automatic updater, or third-party logging service.
Release packages contain application files, documentation, licenses, and synthetic test fixtures; no real music, lyrics, artwork, credentials, or user configuration is distributed.

## Run from source or build

Use Windows x64 and Python 3.12 with Tcl/Tk. Local validation used Python 3.12.14.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python music_gui.py
.venv\Scripts\python scripts/build_release.py
```

The build script runs offline regression tests, collects licenses, generates the icon, builds the EXE, and runs a portable EXE smoke test. It produces:

- `dist/QQMusicConverter.exe`
- `release/QQMusicConverter-0.3.0-beta.1-windows-x64.zip`
- `release/QQMusicConverter-0.3.0-beta.1-source.zip`
- `release/SHA256SUMS.txt`

The portable test copies the EXE to a separate temporary directory, removes Python environment variables, and restricts PATH to the Windows system directory.
It exercises MP3, WAV, embedded artwork, LRC, and Tk. CI runs the same flow on a separate Windows runner.
This checks the bundled runtime; it is not exhaustive testing on clean Windows 10/11 physical machines.

Optional CLI: `python convert_music.py input.ogg -o output --profile wav`.
Encrypted files may use `--qq-login` or `--ekey-file` for that individual song's key. Never upload key files.

## Project structure

| Module | Responsibility |
| --- | --- |
| music_gui.py / ui_theme.py | Main window, styling, scaling, and fixed bottom actions |
| music_workspace.py | Queue interaction, song settings, lyric preview, main-thread widget updates |
| tasks.py / job.py | Background jobs, independent results, progress, cancellation, session lifecycle |
| convert_music.py | Input handling, MP3/WAV encoding, streaming resampling, full verification |
| lyrics.py | Song IDs, lyric retrieval, timestamp normalization and adjustment |
| media_assets.py | Local metadata, embedded artwork, online song/album information, image export |
| output_files.py | Shared naming and atomic file publication |
| qmc_core.py / qq_session.py | QMC decoding and optional login adapter |
| settings.py | Output-directory persistence only |

## Validation and limitations

Tests use generated audio, images, lyrics, and mocked services. They do not access live accounts or online endpoints.
Coverage includes resampling duration/pitch/anti-aliasing, chunk continuity, independent retries, cancellation, file protection, and multiple display scales.
See [Validation](docs/RELEASE_CHECKS.md) for separate live-service and executable checks.

This is an unsigned beta. Online APIs and client adapters are not guaranteed to remain compatible.
There is no built-in audio preview: lyric preview shows timestamped text, and synchronization should be checked on the target player.
The GUI is currently Simplified Chinese. CI builds artifacts but does not automatically publish a public release.

## License

GPL-3.0. Release packages include application source, build scripts, and third-party notices.
The decoding port references [qmc-decoder](https://github.com/ownlight6/qmc-decoder) and [tc_tea](https://github.com/jixunmoe/tc_tea_rust), retaining upstream attribution and licensing.
See [Third-party notices](THIRD_PARTY_NOTICES.md) for dependency sources, native-library replacement, and licenses.

This project is not an official QQ Music product and is not affiliated with Tencent.
