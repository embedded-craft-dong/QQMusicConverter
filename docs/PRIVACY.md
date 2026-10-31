# Data handling and privacy

**English** | [简体中文](PRIVACY.zh-CN.md)

## Ordinary audio

Selected local audio is read and converted to MP3 or PCM WAV in the chosen directory. Conversion does not access the network or inspect other processes.
Output is written to a temporary file and fully decoded for verification before publication. Cancellation and errors clean up temporary files.

## Requested lyrics

Clicking Export lyrics or Fetch lyric preview, or starting conversion with automatic lyrics enabled, sends the song's `songmid` to:
`https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg`.
The ID comes from bounded musicex metadata or a QQ Music detail link supplied by the user.

Audio, lyric files, local paths, and filenames are not uploaded. This feature does not read client processes, accounts, or cookies.
Only the requested UTF-8 LRC is saved; song IDs and query history are not automatically persisted.
Responses are limited to 1 MiB. Blocking network calls time out after 8 seconds; the read loop has a 15-second deadline and cancellation checks.

## Artwork and song information

Ordinary-file tags, technical parameters, and embedded artwork are read locally without network requests.
When artwork is missing and a song ID is available, or online information is explicitly requested for encrypted audio,
the song ID is submitted to the song-detail method at `https://u.y.qq.com/cgi-bin/musicu.fcg`, without login fields.
The returned album ID is used to request artwork under `https://y.gtimg.cn/music/photo_new/`.

No audio or local paths are uploaded, and client processes, accounts, and cookies are not read.
Song-information responses are limited to 1 MiB and artwork to 12 MiB. Blocking calls time out after 8 seconds; read loops have a 20-second deadline.
Image decoding is limited to 16 million pixels. Exported JPGs omit EXIF and other attached source-image metadata.
Automatic lyric/artwork processing is off at startup. Song links, shared names, and timing adjustments stay in memory only.

## Optional login adapter for encrypted audio

This option is off at startup. When explicitly enabled and encrypted audio is converted, the adapter:

1. Reads the account number from the current user's QQMusic configuration.
2. Locates QQMusic processes and scans readable memory for ASCII/UTF-16 `authst` fields using read-only access. Memory blocks also contain unrelated data; only matching session fields are extracted, and no memory dump is saved.
3. Sends the session, account number, embedded song ID, and embedded filename over HTTPS to QQ Music's `u.y.qq.com` key endpoint. Audio content itself is not uploaded.
4. Uses the returned key for the individual song without writing it to disk. Session candidates are reused within one batch and references are cleared when it finishes.

Clearing Python references is not verifiable physical memory erasure; the application does not claim secure erasure.
Network responses, sessions, keys, and tracebacks containing them are not printed. The adapter does not elevate privileges or modify the target process.
If session access fails, ordinary audio remains usable; the CLI also supports an external key file for an individual song.
Do not include configuration files, memory dumps, sessions, keys, or copyrighted music in bug reports.

## Limits and cancellation

- The PowerShell process lookup waits at most 5 seconds.
- Memory scanning has a 12-second loop deadline and a 512 MiB attempted-read budget, including failed reads and overlapping bytes.
- Cancellation is checked between blocks; a running OS call cannot be preempted.
- Key requests try at most three session candidates, with a 25-second request/read-loop deadline and blocking calls limited to 8 seconds.

Deadlines are cooperative checks, not forced thread termination. A network or OS call may finish after the next intended check point.
Cancellation does not interrupt an already committed output or delete other completed files.

## Local settings

Only the output directory is saved, in `%LOCALAPPDATA%/QQMusicConverter/settings.json`.
Login and overwrite options, the file queue, accounts, and keys are not persisted.
There is no telemetry, third-party logging service, or automatic updater. Windows file dialogs may maintain their own recently used file history.
