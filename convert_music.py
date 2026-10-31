#!/usr/bin/env python3
"""Convert ordinary audio or musicex-v1 QMC2 audio to MP3.

QMC implementation: qmc_core.py, adapted from ownlight6/qmc-decoder,
https://github.com/ownlight6/qmc-decoder (GPL-3.0), and tc_tea.
Login access is opt-in (--qq-login); no tokens or keys are logged/saved.
"""
import argparse
import io
import json
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import urllib.request
import time
from job import Cancelled, SessionCache, checkpoint, report
from output_files import output_path, publish

ENCRYPTED = {'.mgg', '.mflac', '.qmc0', '.qmcflac', '.qmcogg'}
ORDINARY = {'.ogg', '.wav', '.flac', '.mp3'}


def emit(args, text):
    callback = getattr(args, 'notify', None)
    if callback:
        callback(text)
    elif sys.stdout is not None:
        print(text, flush=True)


def musicex(data):
    if len(data) < 16 or data[-8:] != b'musicex\0':
        raise ValueError('不是支持的 musicex 文件；本脚本不支持所有旧 QMC 格式。')
    size, version = struct.unpack('<II', data[-16:-8])
    if version != 1 or size < 156 or size > len(data)-4:
        raise ValueError('musicex 版本或尾部长度不支持。')
    meta = data[-size:-16]
    mid = meta[12:72].decode('utf-16le').split('\0')[0]
    name = meta[72:140].decode('utf-16le').split('\0')[0]
    if not mid or not name:
        raise ValueError('musicex 缺少歌曲标识。')
    return data[:-size], mid, name


def validate_ogg(data, args=None):
    table = []
    for i in range(256):
        crc = i << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04c11db7 if crc & 0x80000000 else 0)) & 0xffffffff
        table.append(crc)
    pos = pages = 0
    eos = False
    while pos < len(data):
        checkpoint(args)
        if len(data)-pos < 27 or data[pos:pos+4] != b'OggS' or data[pos+4] != 0:
            raise ValueError('OGG 页头损坏，可能是密钥不匹配。')
        count = data[pos+26]
        if pos+27+count > len(data):
            raise ValueError('OGG 分段表被截断。')
        size = 27+count+sum(data[pos+27:pos+27+count])
        if pos+size > len(data):
            raise ValueError('OGG 页被截断。')
        page = bytearray(data[pos:pos+size])
        expected = struct.unpack_from('<I', page, 22)[0]
        page[22:26] = bytes(4)
        crc = 0
        for v in page:
            crc = ((crc << 8) & 0xffffffff) ^ table[(crc >> 24) ^ v]
        if crc != expected:
            raise ValueError('OGG CRC 校验失败，拒绝输出损坏音频。')
        eos = bool(page[5] & 4)
        pages += 1
        pos += size
        report(args, '校验源音频', pos / len(data))
    if not pages or not eos:
        raise ValueError('OGG 缺少结束页。')


def login_key(mid, name, args=None):
    checkpoint(args)
    if os.name != 'nt':
        raise ValueError('--qq-login 仅支持 Windows QQ 音乐客户端。')
    from qq_session import session_candidates
    cfg = Path.home()/'AppData/Roaming/Tencent/QQMusic/QQMusicServiceConfig.ini'
    if not cfg.is_file():
        raise ValueError('未找到 QQ 音乐配置；请先登录桌面客户端。')
    match = re.search(r'(?im)^\s*uin\s*=\s*(\d+)\s*$', cfg.read_text(encoding='utf-8-sig', errors='replace'))
    if not match:
        raise ValueError('未找到 QQ 音乐账户编号。')
    cache = getattr(args, 'session_cache', None)
    try:
        if cache is not None and cache.scanned:
            tokens = cache.tokens
        else:
            tokens = session_candidates(args=args)
            if cache is not None:
                cache.tokens.update(tokens)
                cache.scanned = True
    except Cancelled:
        raise
    except Exception:
        raise ValueError('无法读取运行中的 QQ 音乐登录状态；请打开并登录客户端，或用 --ekey-file。') from None
    if not tokens:
        raise ValueError('未找到可用登录状态；客户端版本可能不兼容。')
    uin = match.group(1)
    deadline = time.monotonic() + 25
    for token in sorted(tokens)[:3]:
        checkpoint(args)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        body = {'comm': {'authst': token, 'ct': '19', 'cv': '1859', 'uin': uin, 'tmeLoginType': '3'},
                'req_1': {'module': 'music.vkey.GetEVkey', 'method': 'CgiGetEVkey',
                          'param': {'filename': [name], 'guid': '10000', 'songmid': [mid],
                                    'songtype': [1], 'uin': uin, 'loginflag': 1, 'platform': '27', 'ctx': 1}}}
        request = urllib.request.Request('https://u.y.qq.com/cgi-bin/musicu.fcg',
            data=json.dumps(body).encode(), headers={'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0', 'Referer': 'https://y.qq.com/'})
        try:
            with urllib.request.urlopen(request, timeout=min(8, remaining)) as response:
                raw = bytearray()
                while True:
                    checkpoint(args)
                    if time.monotonic() >= deadline:
                        raise TimeoutError()
                    block = response.read(4096)
                    if not block:
                        break
                    raw.extend(block)
                    if len(raw) > 1024 * 1024:
                        raise ValueError('Oversized response')
                result = json.loads(raw)
            checkpoint(args)
            info = (result.get('req_1', {}).get('data', {}).get('midurlinfo') or [{}])[0]
            key = info.get('ekey')
            if isinstance(key, str) and key:
                return key
        except Cancelled:
            raise
        except Exception:
            continue
    raise ValueError('QQ 音乐未返回歌曲密钥：登录过期、权限不足或接口变更均可能导致失败。')


def open_audio(path, args):
    checkpoint(args)
    if path.suffix.lower() not in ENCRYPTED:
        return str(path)
    from qmc_core import parse_key, decrypt
    chunks = bytearray()
    with path.open('rb') as source:
        while block := source.read(1024 * 1024):
            checkpoint(args)
            chunks.extend(block)
    payload, mid, name = musicex(chunks)
    del chunks
    if args.ekey_file:
        ekey = args.ekey_file.read_text(encoding='utf-8-sig').strip()
    elif args.qq_login:
        emit(args, '正在向 QQ 音乐请求本首歌曲密钥…')
        ekey = login_key(mid, name, args)
    else:
        raise ValueError('加密文件需要 --qq-login（读取本机登录状态）或 --ekey-file（本首歌的密钥文件）。')
    try:
        key = parse_key(ekey)
        if not key:
            raise ValueError('empty key')
        emit(args, '正在还原音频…')
        audio = decrypt(payload, key, lambda fraction: report(args, '还原音频', fraction))
    except Cancelled:
        raise
    except Exception:
        raise ValueError('歌曲密钥格式无效，或此加密版本不支持。') from None
    if audio.startswith(b'OggS'):
        emit(args, '正在校验 OGG 完整性…')
        validate_ogg(audio, args)
    elif not audio.startswith(b'fLaC'):
        raise ValueError('还原后不是 OGG/FLAC；密钥不匹配或加密版本不支持。')
    return io.BytesIO(audio)


def convert(path, args, sf, np):
    checkpoint(args)
    folder = args.output_dir or path.parent/'mp3_output'
    folder.mkdir(parents=True, exist_ok=True)
    wav = getattr(args, 'profile', 'mp3') == 'wav'
    suffix = '.wav' if wav else '.mp3'
    label = 'WAV' if wav else 'MP3'
    target = output_path(path,folder,suffix,args)
    if target.resolve() == path.resolve():
        raise ValueError('输出不能覆盖输入文件。')
    if target.exists() and not args.overwrite:
        raise ValueError('输出已存在；如确实要替换，请使用 --overwrite。')
    source = open_audio(path, args)
    tmp = None
    try:
        emit(args, '正在编码 '+label+'…')
        with sf.SoundFile(source) as src:
            rate, channels = src.samplerate, src.channels
            if channels not in (1,2) or (not wav and rate not in (8000,11025,12000,16000,22050,24000,32000,44100,48000)):
                raise ValueError('输入采样率或声道数不适合此 MP3 编码流程，需先重采样。')
            input_rate, input_channels = rate, channels
            resampler = None
            if wav:
                import soxr
                rate, channels = 48000, 2
                if input_rate != rate:
                    resampler = soxr.ResampleStream(input_rate,rate,channels,dtype='float32',quality='HQ')
            fd, tmp = tempfile.mkstemp(prefix='.convert-', suffix=suffix, dir=folder)
            os.close(fd)
            frames = 0
            options = dict(format='WAV',subtype='PCM_16') if wav else dict(format='MP3',bitrate_mode='VARIABLE',compression_level=0.0)
            consumed = 0
            with sf.SoundFile(tmp, mode='w', samplerate=rate, channels=channels, **options) as dst:
                for block in src.blocks(blocksize=65536, dtype='float32', always_2d=True):
                    checkpoint(args)
                    if not np.isfinite(block).all():
                        raise ValueError('音频包含无效样本。')
                    consumed += len(block)
                    if wav:
                        if input_channels == 1:
                            block = np.repeat(block,2,axis=1)
                        if resampler is not None:
                            block = resampler.resample_chunk(block,last=consumed>=src.frames)
                        block = np.clip(block,-1.0,32767/32768)
                    dst.write(block)
                    frames += len(block)
                    report(args, '编码 '+label, consumed / max(1, src.frames))
            if not frames:
                raise ValueError('音频为空。')
            if wav and abs(frames-round(consumed*rate/input_rate))>1:
                raise ValueError('WAV 重采样时长校验失败。')
        # Decode the entire output, not merely its file header.
        decoded = 0
        emit(args, '正在完整解码校验 '+label+'…')
        with sf.SoundFile(tmp) as check:
            if check.format != label or check.samplerate != rate or check.channels != channels or (wav and check.subtype!='PCM_16'):
                raise ValueError(label+' 输出参数校验失败。')
            for block in check.blocks(blocksize=65536):
                checkpoint(args)
                if not np.isfinite(block).all():
                    raise ValueError('MP3 解码校验失败。')
                decoded += len(block)
                report(args, '验证 '+label, decoded / max(1, frames))
        if abs(decoded-frames) > (0 if wav else 2304):
            raise ValueError(label+' 时长校验失败。')
        checkpoint(args)
        if args.overwrite:
            os.replace(tmp, target)
        elif os.name == 'nt':
            os.rename(tmp, target)  # Windows refuses an existing destination.
        else:
            # Atomic publication without replacing an existing destination.
            os.link(tmp, target)
            os.unlink(tmp)
        tmp = None
        emit(args, f'完成：{target.name} · {frames/rate:.1f} 秒')
        return target
    finally:
        if tmp and Path(tmp).exists():
            Path(tmp).unlink()


def main():
    parser = argparse.ArgumentParser(description='本次 musicex-v1 MGG / 普通 OGG、FLAC、WAV 转高质量 VBR MP3；保留原件。')
    parser.add_argument('input', type=Path, help='一个音频文件或文件夹（不递归）')
    parser.add_argument('-o', '--output-dir', type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--qq-login', action='store_true', help='允许读取运行中 QQ 音乐的 authst 会话字段，仅发送到 QQ 音乐官方接口')
    group.add_argument('--ekey-file', type=Path, help='UTF-8 文本，包含本首歌曲的 ekey；仅单文件模式')
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--profile', choices=('mp3','wav'), default='mp3', help='wav: 48 kHz / PCM16 / stereo')
    args = parser.parse_args()
    args.session_cache = SessionCache()
    if not args.input.exists():
        parser.error('输入路径不存在。')
    if args.input.is_dir() and args.ekey_file:
        parser.error('--ekey-file 仅支持单文件，不能让不同歌曲复用同一个密钥。')
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        parser.exit(2, '请先运行：python -m pip install -r requirements.txt\n')
    if 'MP3' not in sf.available_formats():
        parser.exit(2, '当前 libsndfile 不支持 MP3，请安装 requirements.txt 中的 soundfile。\n')
    files = sorted(p for p in args.input.iterdir() if p.is_file() and p.suffix.lower() in ENCRYPTED|ORDINARY) if args.input.is_dir() else [args.input]
    if not files:
        parser.error('目录内没有支持的文件。')
    failed = 0
    for path in files:
        print(f'处理：{path.name}', flush=True)
        try:
            convert(path, args, sf, np)
        except Exception as exc:
            # Do not display HTTP responses, auth state, key material or traceback.
            message = str(exc) if isinstance(exc, (ValueError, FileExistsError)) else '处理失败，请检查文件权限、依赖和文件完整性。'
            print(f'  失败：{message}', file=sys.stderr)
            failed += 1
    print(f'结束：成功 {len(files)-failed}，失败 {failed}。')
    args.session_cache.clear()
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
