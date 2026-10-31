# Release validation

**English** | [简体中文](RELEASE_CHECKS.zh-CN.md)

## 0.3.0-beta.1

- 34 offline regression tests passed on Windows x64 with Python 3.12.14, using generated audio, artwork, and lyrics.
- WAV checks cover 44.1 kHz mono and 48/96 kHz stereo inputs, output parameters, duration, pitch, chunk continuity, anti-aliasing, and cancellation protection.
- GUI tests cover selected conversion, automatic assets, independent retries, lyric adjustment, existing-LRC protection, queued-original protection, and layouts at 100% / 125% / 150% / 200% scaling.
- Live-service checks successfully retrieved song information, album JPG artwork, and an LRC with 118 timed lines using a shared output name. Real media are excluded from the repository and release packages.
- Executable UI checks covered the main window, centered settings dialog, tabs, online lyric preview, and control recovery after completion.
- Portable EXE smoke tests passed for MP3, WAV, embedded artwork, LRC, and Tk after copying the EXE to a source-free directory, clearing Python environment variables, and restricting PATH to the Windows system directory.
- [Windows CI passed for the release commit](https://github.com/embedded-craft-dong/QQMusicConverter/actions/runs/41196381480), including regression tests, executable build, and portable smoke tests.
- All four published release assets were checked against their SHA-256 digests. The release tag matches the tested commit.

### Remaining limits

Validation has not been completed on a separate physical Windows 10/11 computer without Python. Isolation tests and CI do not cover every hardware environment.
Live checks do not guarantee availability for all songs. The encrypted-audio login adapter was retained from the previous implementation; this release does not claim compatibility testing against every QQ Music client version.

## 0.1.0-beta.1

The first public beta passed 14 offline tests and local executable checks. Coverage included synthetic OGG/WAV and musicex/QMC2 conversion, full output decoding, TEA vectors, corruption and wrong-key detection, overwrite protection, cancellation cleanup, mocked session reuse, GUI retries, settings, and display scaling.

Its Windows CI also passed. These results do not establish compatibility with every Windows installation or QQ Music client. Separate clean-machine and broader hardware/accessibility checks remain outside the verified scope.
