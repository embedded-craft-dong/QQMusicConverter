"""Read local metadata/artwork, or explicitly fetch QQ song metadata/artwork."""
import base64
import io
import json
from pathlib import Path
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from job import Cancelled, checkpoint
from lyrics import parse_song_reference
from output_files import output_path, save_bytes

MAX_IMAGE = 12 * 1024 * 1024


def download(url, args=None, limit=1024*1024):
    # Only fixed official endpoints are constructed by callers. No arbitrary URL fetch.
    request = urllib.request.Request(url, headers={'Referer':'https://y.qq.com/', 'User-Agent':'Mozilla/5.0'})
    deadline = time.monotonic()+20
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            content = bytearray()
            while True:
                checkpoint(args)
                if time.monotonic() > deadline:
                    raise TimeoutError()
                block = response.read(16384)
                if not block:
                    break
                content.extend(block)
                if len(content) > limit:
                    raise ValueError('响应超过大小限制，已停止读取。')
        checkpoint(args)
        return bytes(content)
    except Cancelled:
        raise
    except (TimeoutError, socket.timeout):
        raise ValueError('网络超时，请稍后重试失败项。') from None
    except urllib.error.HTTPError:
        raise ValueError('在线服务拒绝请求或资源已下架，请核对歌曲链接。') from None
    except urllib.error.URLError:
        raise ValueError('无法连接在线服务，请检查网络后重试。') from None


def song_details(reference, args=None):
    mid = parse_song_reference(reference)
    request = {'songinfo': {'module':'music.pf_song_detail_svr', 'method':'get_song_detail_yqq',
                           'param':{'song_mid':mid, 'song_type':0}}}
    url = 'https://u.y.qq.com/cgi-bin/musicu.fcg?data='+urllib.parse.quote(json.dumps(request))
    try:
        data = json.loads(download(url,args))
        track = data['songinfo']['data']['track_info']
        if track.get('mid') != mid:
            raise KeyError('mid')
        return {'title':str(track.get('title','')), 'artist':' / '.join(str(s.get('name','')) for s in track.get('singer',[])),
                'album':str(track.get('album',{}).get('name','')), 'album_mid':track.get('album',{}).get('mid',''),
                'duration':track.get('interval',0), 'source':'QQ 音乐歌曲信息（技术参数请查看本地音频）'}
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ValueError('没有找到对应歌曲信息，请检查歌曲详情页链接。') from None


def local_info(path):
    import soundfile as sf
    import mutagen
    result = {'title':'', 'artist':'', 'album':'', 'source':'本地音频'}
    info = sf.info(str(path))
    result.update(duration=info.duration, samplerate=info.samplerate, channels=info.channels,
                  format=info.format, subtype=info.subtype)
    try:
        tags = mutagen.File(str(path),easy=True)
        for key in ('title','artist','album'):
            if tags and tags.get(key):
                result[key] = ' / '.join(map(str,tags[key]))
    except Exception:
        pass  # Technical parameters remain useful when optional tags are malformed.
    return result


def embedded_cover(path):
    import mutagen
    from mutagen.flac import Picture
    tags = mutagen.File(str(path))
    if tags is None:
        return None
    pictures = list(getattr(tags,'pictures',[]))
    if getattr(tags,'tags',None) is not None:
        if hasattr(tags.tags,'getall'):
            pictures.extend(tags.tags.getall('APIC'))
        for value in tags.get('metadata_block_picture',[]):
            if len(value) <= MAX_IMAGE*2:
                try:
                    pictures.append(Picture(base64.b64decode(value,validate=True)))
                except Exception:
                    continue
    pictures.sort(key=lambda p:getattr(p,'type',0)!=3)
    for picture in pictures:
        if 0 < len(picture.data) <= MAX_IMAGE:
            return picture.data
    return None


def clean_jpeg(data):
    """Bound image decoding and strip metadata from the exported artwork."""
    from PIL import Image, ImageOps
    if len(data)>MAX_IMAGE:
        raise ValueError('封面超过 12 MiB 限制。')
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(data)) as picture:
                if picture.width*picture.height > 16_000_000:
                    raise ValueError('封面像素过大（最多 1600 万像素）。')
                picture = ImageOps.exif_transpose(picture).convert('RGB')
                result = io.BytesIO()
                picture.save(result,format='JPEG',quality=95)
                return result.getvalue()
        except (OSError,Image.DecompressionBombWarning,Image.DecompressionBombError):
            raise ValueError('封面内容无效或图片过大。') from None


def export_cover(source, folder, reference=None, args=None):
    target = output_path(source,folder,'.jpg',args)
    if target.exists():
        raise FileExistsError('同名封面已存在；请改输出名称或另选目录。')
    checkpoint(args)
    data = None
    if Path(source).suffix.lower() in {'.mp3','.wav','.flac','.ogg'}:
        try:
            data = embedded_cover(source)
        except Exception:
            pass
    if data is None:
        if not reference:
            raise ValueError('文件没有可用内嵌封面；请在歌曲设置中填写 QQ 音乐链接后重试。')
        album = song_details(reference,args)['album_mid']
        if not isinstance(album,str) or not __import__('re').fullmatch(r'[A-Za-z0-9]{14}',album):
            raise ValueError('这首歌没有可用的专辑封面。')
        data = download('https://y.gtimg.cn/music/photo_new/T002R800x800M000'+album+'.jpg',args,MAX_IMAGE)
    checkpoint(args)
    encoded = clean_jpeg(data)
    return save_bytes(target,encoded,args)
