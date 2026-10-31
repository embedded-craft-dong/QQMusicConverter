"""Opt-in, offline executable self-test using temporary synthetic fixtures only."""
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace


def run(report_path):
    result = {'ok':False,'checks':[]}
    try:
        import numpy as np
        import soundfile as sf
        import tkinter as tk
        from PIL import Image
        from mutagen.flac import FLAC, Picture
        import io
        import convert_music as engine
        import lyrics
        import media_assets
        from job import SessionCache
        from output_files import save_bytes
        with tempfile.TemporaryDirectory(prefix='converter-self-test-') as directory:
            root = Path(directory)
            source = root/'generated.flac'
            sf.write(source,.2*np.sin(np.arange(44100)*2*np.pi*440/44100),44100)
            data=io.BytesIO();Image.new('RGB',(16,16),(20,90,130)).save(data,format='PNG')
            tag=FLAC(source);picture=Picture();picture.type=3;picture.mime='image/png';picture.data=data.getvalue()
            tag.add_picture(picture);tag.save()
            args=SimpleNamespace(output_dir=root/'out',qq_login=False,ekey_file=None,overwrite=False,
                cancel_event=threading.Event(),session_cache=SessionCache(),notify=lambda text:None)
            for profile in ('mp3','wav'):
                args.profile=profile
                target=engine.convert(source,args,sf,np)
                info=sf.info(target)
                assert info.frames>0
                if profile=='wav':assert (info.samplerate,info.channels,info.subtype)==(48000,2,'PCM_16')
                result['checks'].append(profile)
            cover=media_assets.export_cover(source,args.output_dir)
            with Image.open(cover) as image:assert image.format=='JPEG'
            result['checks'].append('embedded-artwork')
            text,count=lyrics.shift_lrc('[00:01.00]Synthetic self-test\n',250)
            assert text.startswith('[00:01.25]')
            save_bytes(args.output_dir/'generated.lrc',text.encode('utf-8'))
            result['checks'].append('lrc')
            window=tk.Tk();window.withdraw();window.update();window.destroy()
            result['checks'].append('tk-runtime')
            result['ok']=True
    except Exception as error:
        result['error_type']=type(error).__name__
    Path(report_path).write_text(json.dumps(result),encoding='utf-8')
    return 0 if result['ok'] else 1
