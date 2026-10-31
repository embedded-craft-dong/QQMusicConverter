"""Timed LRC export from a QQ song identifier. No cookies, login or audio upload."""
import base64
import html
import json
from pathlib import Path
import re
import struct
import time
import urllib.parse
import urllib.request
import urllib.error
from job import Cancelled, checkpoint
from output_files import output_path, save_bytes

MID = re.compile(r'[A-Za-z0-9]{14}\Z')
STAMP = re.compile(r'\[(\d{1,5}):([0-5]\d)(?:\.(\d{1,3}))?\]')
MAX_RESPONSE = 1024 * 1024


def parse_song_reference(value):
    value=value.strip()
    if MID.fullmatch(value):return value
    url=urllib.parse.urlsplit(value)
    if url.scheme not in ('http','https') or url.hostname not in ('y.qq.com','www.y.qq.com'):
        raise ValueError('请输入 QQ 音乐歌曲详情页链接，或 14 位 songmid。')
    query=urllib.parse.parse_qs(url.query)
    candidates=query.get('songmid',[])+query.get('mid',[])
    match=re.search(r'/song(?:Detail)?/([A-Za-z0-9]{14})(?:\.html)?(?:/|$)',url.path)
    if match:candidates.insert(0,match.group(1))
    for candidate in candidates:
        if MID.fullmatch(candidate):return candidate
    raise ValueError('此链接没有歌曲编号。请在 QQ 音乐网页打开歌曲详情页，复制地址栏链接。')


def song_mid_from_file(path):
    """Read bounded musicex metadata only; never decrypt or scan client memory."""
    path=Path(path)
    with path.open('rb') as stream:
        length=stream.seek(0,2)
        if length<160:return None
        stream.seek(-16,2);tail=stream.read(16)
        if tail[8:]!=b'musicex\0':return None
        size,version=struct.unpack('<II',tail[:8])
        if version!=1 or not 156<=size<=min(65536,length-4):return None
        stream.seek(-size+12,2)
        try:mid=stream.read(60).decode('utf-16le').split('\0')[0]
        except UnicodeError:return None
    return mid if MID.fullmatch(mid) else None


def normalize_lrc(text, decode_entities=True):
    """Expand repeated stamps, apply offset, sort stably; emit UTF-8 centisecond LRC."""
    if decode_entities:text=html.unescape(text)
    text=text.lstrip('\ufeff').replace('\r\n','\n').replace('\r','\n')
    offset_matches=re.findall(r'\[offset:([+-]?\d+)\]',text,flags=re.I)
    offset=int(offset_matches[-1]) if offset_matches else 0
    rows=[];metadata=[]
    for line in text.split('\n'):
        line=line.strip()
        stamps=list(STAMP.finditer(line))
        if not stamps:
            if re.fullmatch(r'\[(?:ti|ar|al|by):[^\r\n]*\]',line,re.I):metadata.append(line)
            continue
        # A timestamp is a prefix, not lyric text or a value embedded in prose.
        if stamps[0].start()!=0:continue
        prefix_end=0;prefix=[]
        for stamp in stamps:
            if line[prefix_end:stamp.start()].strip():break
            prefix.append(stamp);prefix_end=stamp.end()
        words=line[prefix_end:].strip()
        for stamp in prefix:
            minutes,seconds,fraction=stamp.groups()
            # LRC header convention: positive offset advances the lyric.
            milliseconds=(int(minutes)*60+int(seconds))*1000+int((fraction or '').ljust(3,'0'))-offset
            centiseconds=(max(0,milliseconds)+5)//10
            rows.append((centiseconds,words))
    if not any(words for _,words in rows):
        raise ValueError('未获取到带时间戳的歌词（可能无歌词或仅有纯文本）；不会生成虚假的时间点。')
    rows.sort(key=lambda item:item[0])
    lines=metadata+[f'[{cs//6000:02d}:{cs//100%60:02d}.{cs%100:02d}]{words}' for cs,words in rows]
    return '\n'.join(lines)+'\n',len(rows)


def fetch_lrc(mid,args=None):
    mid=parse_song_reference(mid)
    checkpoint(args)
    query=urllib.parse.urlencode({'songmid':mid,'format':'json','nobase64':1,'g_tk':5381})
    url='https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?'+query
    request=urllib.request.Request(url,headers={'Referer':'https://y.qq.com/','User-Agent':'Mozilla/5.0'})
    deadline=time.monotonic()+15
    try:
        with urllib.request.urlopen(request,timeout=8) as response:
            raw=bytearray()
            while True:
                checkpoint(args)
                if time.monotonic()>deadline:raise TimeoutError()
                chunk=response.read(4096)
                if not chunk:break
                raw.extend(chunk)
                if len(raw)>MAX_RESPONSE:raise ValueError('歌词响应超过大小限制。')
        checkpoint(args)
        data=json.loads(raw.decode('utf-8-sig'))
    except Cancelled:raise
    except TimeoutError:
        raise ValueError('歌词请求超时，请稍后重试失败项。') from None
    except urllib.error.HTTPError:
        raise ValueError('歌词服务拒绝请求，请核对歌曲链接或稍后重试。') from None
    except urllib.error.URLError:
        raise ValueError('无法连接歌词服务，请检查网络后重试。') from None
    except Exception:
        raise ValueError('获取歌词失败：请检查网络；QQ 音乐接口也可能暂时不可用。') from None
    if not isinstance(data,dict) or data.get('code') not in (0,'0'):
        raise ValueError('QQ 音乐未返回歌词，请检查歌曲链接或稍后重试。')
    text=data.get('lyric')
    if not isinstance(text,str) or not text.strip():raise ValueError('这首歌曲没有可用歌词。')
    if not STAMP.search(html.unescape(text)):
        try:text=base64.b64decode(text,validate=True).decode('utf-8-sig')
        except (ValueError,UnicodeError):pass
    checkpoint(args)
    return normalize_lrc(text)


def shift_lrc(text, milliseconds=0):
    milliseconds=int(milliseconds)
    if abs(milliseconds)>600000:
        raise ValueError('歌词偏移限制为 ±600000 毫秒。')
    normalized,_=normalize_lrc(text,decode_entities=False)
    # UI adjustment uses positive=delay; the emitted file has adjusted stamps,
    # not an offset tag whose sign convention could confuse downstream players.
    return normalize_lrc(normalized+f'[offset:{-milliseconds}]\n',decode_entities=False)


def export_lrc(source,folder,reference,args=None,overwrite=False):
    """Save independently of MP3 conversion; existing LRC is protected by default."""
    source,folder=Path(source),Path(folder)
    target=output_path(source,folder,'.lrc',args)
    checkpoint(args)
    if target.exists() and not overwrite:raise FileExistsError('同名 LRC 已存在，未覆盖。')
    text,count=fetch_lrc(parse_song_reference(reference),args)
    text,count=shift_lrc(text,getattr(args,'lyric_offset',0))
    checkpoint(args)
    return save_bytes(target,text.encode('utf-8'),args,overwrite),count
