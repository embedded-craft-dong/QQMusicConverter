"""Synthetic fixtures for board audio, independent assets, and batch behavior."""
import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import soundfile as sf
from PIL import Image
from mutagen.flac import FLAC, Picture
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import convert_music as engine
import lyrics
import media_assets as assets
import tasks
from job import Cancelled
from output_files import valid_stem, save_bytes
from test_converter import args, tone

MID='00123456789abc'


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def image(self):
        stream=io.BytesIO();Image.new('RGB',(24,16),(10,80,120)).save(stream,format='PNG')
        return stream.getvalue()

    def test_wav_resampling_mono_stereo_duration_pitch_and_chunk_boundary(self):
        for rate,channels,seconds in [(44100,1,2.731),(96000,2,1.371),(48000,2,.2)]:
            with self.subTest(rate=rate,channels=channels):
                data=.25*np.sin(np.arange(round(rate*seconds))*2*np.pi*997/rate)
                if channels==2:data=np.stack((data,data*.5),axis=1)
                source=self.root/f'{rate}.flac';sf.write(source,data,rate)
                target=engine.convert(source,args(self.root/'out',profile='wav',output_stem=f'board-{rate}'),sf,np)
                out,actual_rate=sf.read(target,always_2d=True)
                info=sf.info(target)
                self.assertEqual((actual_rate,out.shape[1],info.subtype),(48000,2,'PCM_16'))
                self.assertLessEqual(abs(len(out)-round(len(data)*48000/rate)),1)
                segment=out[1000:-1000,0]
                frequency=np.argmax(abs(np.fft.rfft(segment)))*48000/len(segment)
                self.assertLess(abs(frequency-997),8)
                self.assertLess(np.max(np.abs(np.diff(out[100:-100,0]))),.04)
                if channels==1:self.assertTrue(np.array_equal(out[:,0],out[:,1]))

    def test_wav_antialias_and_cancel_preserves_existing(self):
        rate=96000
        source=self.root/'ultrasonic.wav'
        data=.4*np.sin(np.arange(rate)*2*np.pi*30000/rate)
        sf.write(source,data,rate,subtype='FLOAT')
        target=engine.convert(source,args(self.root/'out',profile='wav'),sf,np)
        converted,_=sf.read(target)
        self.assertLess(float(np.sqrt(np.mean(converted[1000:-1000]**2))),.001)
        previous=target.read_bytes()
        a=args(self.root/'out',profile='wav',overwrite=True)
        a.progress=lambda phase,value:a.cancel_event.set() if phase=='编码 WAV' else None
        with self.assertRaises(Cancelled):engine.convert(source,a,sf,np)
        self.assertEqual(target.read_bytes(),previous)
        self.assertFalse(list(target.parent.glob('.convert-*')))

    def test_cover_embedded_and_metadata_without_network(self):
        path=tone(self.root/'art.flac')
        audio=FLAC(path);audio['title']='Generated';audio['artist']='Synthetic'
        picture=Picture();picture.type=3;picture.mime='image/png';picture.data=self.image()
        audio.add_picture(picture);audio.save()
        before=path.read_bytes()
        with patch.object(assets,'download') as network:
            target=assets.export_cover(path,self.root/'out',args=SimpleNamespace(output_stem='track'))
            network.assert_not_called()
        with Image.open(target) as image:
            self.assertEqual((image.format,image.size),('JPEG',(24,16)))
            self.assertFalse(image.getexif())
        self.assertEqual(path.read_bytes(),before)
        info=assets.local_info(path)
        self.assertEqual((info['title'],info['samplerate'],info['channels']),('Generated',44100,2))
        with self.assertRaises(FileExistsError):assets.export_cover(path,self.root/'out',args=SimpleNamespace(output_stem='track'))

    def test_online_cover_uses_validated_album_not_arbitrary_url(self):
        response=json.dumps({'songinfo':{'data':{'track_info':{'mid':MID,'album':{'mid':MID},'singer':[]}}}}).encode()
        with patch.object(assets,'download',side_effect=[response,self.image()]) as download:
            target=assets.export_cover(self.root/'encrypted.mgg',self.root/'out',MID)
            self.assertTrue(target.exists())
            self.assertEqual(download.call_args_list[1].args[0],f'https://y.gtimg.cn/music/photo_new/T002R800x800M000{MID}.jpg')
        bad=json.dumps({'songinfo':{'data':{'track_info':{'mid':MID,'album':{'mid':'../../private'},'singer':[]}}}}).encode()
        with patch.object(assets,'download',return_value=bad) as download:
            with self.assertRaises(ValueError):assets.export_cover(self.root/'other.mgg',self.root/'out',MID)
            self.assertEqual(download.call_count,1)

    def test_invalid_artwork_network_bound_and_cancellation(self):
        with self.assertRaises(ValueError):assets.clean_jpeg(b'not an image')
        with patch.object(assets.urllib.request,'urlopen',return_value=io.BytesIO(b'x'*100)):
            with self.assertRaises(ValueError):assets.download('https://y.gtimg.cn/test',limit=10)
        event=threading.Event();event.set()
        with patch.object(assets,'embedded_cover') as read:
            with self.assertRaises(Cancelled):assets.export_cover(self.root/'test.mp3',self.root/'out',args=SimpleNamespace(cancel_event=event))
            read.assert_not_called()

    def test_names_offset_and_atomic_file_protection(self):
        for name in ('../track','CON','a/b','a\\b','track.','a:b',''):
            with self.assertRaises(ValueError):valid_stem(name)
        self.assertEqual(valid_stem(' hello '),'hello')
        text,_=lyrics.shift_lrc('[00:01.00]Synthetic\n',250)
        self.assertEqual(text,'[00:01.25]Synthetic\n')
        self.assertEqual(lyrics.shift_lrc(text,-2000)[0],'[00:00.00]Synthetic\n')
        with self.assertRaises(ValueError):lyrics.shift_lrc(text,600001)
        target=self.root/'track.lrc';save_bytes(target,b'original')
        with self.assertRaises(FileExistsError):save_bytes(target,b'new')
        self.assertEqual(target.read_bytes(),b'original')

    def test_mixed_jobs_keep_audio_success_and_retries_independent(self):
        path=tone(self.root/'song.wav')
        events=queue.Queue()
        options={path:dict(stem='unified',mid=MID,offset=500)}
        a=args(self.root/'out',profile='wav')
        jobs=[(path,'audio'),(path,'lyrics'),(path,'cover')]
        with patch.object(lyrics,'fetch_lrc',return_value=('[00:01.00]Synthetic\n',1)), \
             patch.object(assets,'export_cover',side_effect=ValueError('No cover')):
            tasks.run_batch(jobs,a,options,events)
        messages=list(events.queue)
        self.assertEqual(messages[-1],('batch_done',2,1,0))
        self.assertTrue((a.output_dir/'unified.wav').exists())
        self.assertEqual((a.output_dir/'unified.lrc').read_text(encoding='utf-8'),'[00:01.50]Synthetic\n')
        with patch.object(engine,'convert') as convert,patch.object(assets,'export_cover',return_value=a.output_dir/'unified.jpg'):
            tasks.run_batch([(path,'cover')],a,options,queue.Queue())
            convert.assert_not_called()


if __name__=='__main__':unittest.main()
