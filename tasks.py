"""Background orchestration. Workers communicate through events, never Tk widgets."""
from copy import copy
from pathlib import Path
import time
import convert_music as engine
import lyrics
import media_assets
from job import Cancelled, checkpoint

LABELS = {'audio':'音频','lyrics':'歌词','cover':'封面'}


def explain(error):
    if isinstance(error, FileExistsError):
        return '同名输出已存在；请改输出名称或另选目录。'
    if isinstance(error, ValueError):
        return str(error)
    if isinstance(error, PermissionError):
        return '没有文件访问权限；请关闭占用文件的程序或更换输出目录。'
    if isinstance(error, FileNotFoundError):
        return '文件不存在；请重新添加歌曲或检查输出目录。'
    return '处理失败；请检查文件完整性、目录权限和程序依赖。'


def run_batch(jobs, args, options, events):
    """One queue with independent results and retries for audio, lyrics and covers."""
    successful = failed = processed = 0
    try:
        import soundfile as sf
        import numpy as np
        for index,(path,kind) in enumerate(jobs):
            if args.cancel_event.is_set():
                break
            current = copy(args)
            item = options[path]
            current.output_stem = item['stem']
            current.lyric_offset = item.get('offset',0)
            last = [0.0,None]
            def progress(phase,fraction):
                now = time.monotonic()
                if phase==last[1] and now-last[0]<.08 and fraction<1:
                    return
                last[:] = [now,phase]
                events.put(('task_progress',str(path),kind,phase,round(fraction*100)))
            current.progress = progress
            current.notify = lambda message:events.put(('task_progress',str(path),kind,message,None))
            events.put(('task_result',str(path),kind,'处理中…','active',None))
            try:
                if kind=='audio':
                    target = engine.convert(path,current,sf,np)
                    try:
                        events.put(('media_info',str(path),media_assets.local_info(target)))
                    except Exception:
                        pass  # Optional metadata must not turn a committed conversion into failure.
                elif kind=='lyrics':
                    reference = item.get('mid') or lyrics.song_mid_from_file(path)
                    if not reference:
                        raise ValueError('缺少歌曲编号；双击歌曲，填写 QQ 音乐详情页链接后重试歌词。')
                    target,count = lyrics.export_lrc(path,args.output_dir,reference,current)
                else:
                    reference = item.get('mid') or lyrics.song_mid_from_file(path)
                    target = media_assets.export_cover(path,args.output_dir,reference,current)
                successful += 1
                events.put(('task_result',str(path),kind,'已完成 · '+target.name,'success',str(target)))
            except Cancelled:
                events.put(('task_result',str(path),kind,'已取消 · 已完成文件保留','muted',None))
                break
            except Exception as error:
                failed += 1
                events.put(('task_result',str(path),kind,'失败：'+explain(error),'failed',None))
            processed += 1
            events.put(('progress',processed))
        events.put(('batch_done',successful,failed,len(jobs)-processed))
    except Exception:
        events.put(('batch_error','任务组件加载失败，请重新解压完整发行包。'))
    finally:
        args.session_cache.clear()


def inspect_song(path, reference, events, args, dialog_id):
    try:
        if Path(path).suffix.lower() in engine.ENCRYPTED:
            if not reference:
                raise ValueError('缺少歌曲编号；填写链接后再读取在线歌曲信息。')
            info = media_assets.song_details(reference,args)
        else:
            info = media_assets.local_info(path)
        events.put(('inspection',dialog_id,info,None))
    except Cancelled:
        events.put(('inspection',dialog_id,None,'已取消。'))
    except Exception as error:
        events.put(('inspection',dialog_id,None,explain(error)))


def preview_lyrics(reference, args, events, dialog_id):
    try:
        text,count = lyrics.fetch_lrc(reference,args)
        events.put(('preview',dialog_id,text,None))
    except Cancelled:
        events.put(('preview',dialog_id,None,'已取消。'))
    except Exception as error:
        events.put(('preview',dialog_id,None,explain(error)))
