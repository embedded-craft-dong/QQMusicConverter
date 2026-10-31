# Changelog

**English** | [简体中文](CHANGELOG.zh-CN.md)

## 0.3.0-beta.1

- Batch lyric and artwork export, optional automatic processing during conversion, and retries by task type.
- Embedded-player WAV preset: SoXR HQ streaming resampling to 48 kHz / PCM16 / stereo.
- Shared output names, song information, timestamped lyric preview, millisecond adjustment, and LRC saving.
- Embedded-artwork extraction and online album-artwork fallback using an explicit song ID.
- Separate conversion actions for all or selected files, context menus, and generated-file location.
- Separate UI, worker, lyric, media-asset, and file-publication modules; improved errors, cancellation, and original-file protection.
- Dark dropdowns and tabs, centered dialogs, small-screen scrolling, and isolated portable EXE smoke tests.
- Corrected source LRC offset direction; positive UI adjustments delay the exported timestamps.
- Includes lyric functionality developed in the unreleased 0.2.0 milestone.

## 0.2.0-beta.1 (not released separately)

- Independent UTF-8 LRC export for a selected song, preserving line timestamps.
- Automatic song-ID detection for musicex v1; manual QQ Music detail links for ordinary audio.
- Lyric requests without login-session access or audio uploads; existing LRC protection.
- Repeated timestamps, offset handling, entity decoding, cancellation, and network-error handling.

## 0.1.0-beta.1

- Dark card UI, mint accents, keyboard navigation, and check-mark indicators.
- Scrollable content with fixed bottom actions for small screens and high DPI.
- Per-song phase progress, batch progress, and failed-item retries.
- Cooperative cancellation during input reading, decoding, verification, and encoding, with temporary-output cleanup.
- Batch session reuse and limits on memory scanning, elapsed time, and network response size.
- Output-directory persistence only; login and overwrite options off by default.
- Offline synthetic-audio tests, allowlisted source packaging, pinned dependencies, licenses, and checksums.
