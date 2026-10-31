"""Synthetic lyrics only; no real songs, credentials or live requests in CI."""
import base64
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import lyrics
from job import Cancelled

MID='00123456789abc'
TEXT='[ti:Generated test]\n[offset:100]\n[00:02.50][00:03.5]Beta &amp; Gamma\n[00:01.000]Alpha\n[00:04.00]\n'


class LyricsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.args=SimpleNamespace(cancel_event=threading.Event())

    def response(self,text=TEXT,code=0):
        return io.BytesIO(json.dumps({'code':code,'lyric':text}).encode())

    def test_reference_forms_and_untrusted_hosts(self):
        for value in (MID,f'https://y.qq.com/n/ryqq/songDetail/{MID}',
                      f'https://y.qq.com/n/ryqq_v2/songDetail/{MID}',
                      f'https://y.qq.com/n/yqq/song/{MID}.html',f'https://y.qq.com/?songmid={MID}'):
            self.assertEqual(lyrics.parse_song_reference(value),MID)
        for value in ('song name','https://y.qq.com.attacker.test/?songmid='+MID,
                      'file:///songDetail/'+MID,'https://c6.y.qq.com/short-share'):
            with self.assertRaises(ValueError):lyrics.parse_song_reference(value)

    def test_musicex_footer_bounded_and_plain_audio(self):
        file=self.folder/'song.mgg'
        meta=bytearray(140);meta[12:40]=MID.encode('utf-16le')
        file.write_bytes(b'audio'+meta+struct.pack('<II',156,1)+b'musicex\0')
        self.assertEqual(lyrics.song_mid_from_file(file),MID)
        file.write_bytes(b'ordinary audio'*100)
        self.assertIsNone(lyrics.song_mid_from_file(file))
        file.write_bytes(b'x'*200+struct.pack('<II',2**31,1)+b'musicex\0')
        self.assertIsNone(lyrics.song_mid_from_file(file))

    def test_normalize_order_repeated_stamps_offset_and_empty_cues(self):
        text,count=lyrics.normalize_lrc(TEXT)
        self.assertEqual(count,4)
        self.assertEqual(text,'[ti:Generated test]\n[00:00.90]Alpha\n[00:02.40]Beta & Gamma\n[00:03.40]Beta & Gamma\n[00:03.90]\n')
        self.assertEqual(lyrics.normalize_lrc('[offset:2000]\n[00:01.005]Alpha')[0],'[00:00.00]Alpha\n')
        self.assertEqual(lyrics.normalize_lrc('[offset:-500]\n[00:01.00]Alpha')[0],'[00:01.50]Alpha\n')
        self.assertEqual(lyrics.normalize_lrc('[00:59.999]Alpha')[0],'[01:00.00]Alpha\n')

    def test_do_not_invent_timestamps(self):
        for value in ('','unsynced words','[00:99.00]Alpha','[00:01.00]','[ti:Title]'):
            with self.assertRaises(ValueError):lyrics.normalize_lrc(value)

    def test_plain_and_base64_responses(self):
        for value in (TEXT,base64.b64encode(TEXT.encode()).decode()):
            with patch.object(lyrics.urllib.request,'urlopen',return_value=self.response(value)) as network:
                text,count=lyrics.fetch_lrc(MID,self.args)
                self.assertEqual(count,4)
                request=network.call_args.args[0]
                self.assertTrue(request.full_url.startswith('https://c.y.qq.com/lyric/'))
                self.assertFalse(request.has_header('Authorization'))
                self.assertFalse(request.has_header('Cookie'))
                self.assertIsNone(request.data)

    def test_bad_response_no_output(self):
        for raw in (b'bad json',json.dumps({'code':1}).encode(),b'[]',b'x'*(lyrics.MAX_RESPONSE+1)):
            with patch.object(lyrics.urllib.request,'urlopen',return_value=io.BytesIO(raw)):
                with self.assertRaises(ValueError):lyrics.export_lrc(self.folder/'song.mp3',self.folder/'out',MID,self.args)
        self.assertFalse((self.folder/'out').exists())

    def test_atomic_save_no_overwrite_and_audio_unchanged(self):
        song=self.folder/'song.mp3';song.write_bytes(b'original audio')
        folder=self.folder/'out'
        with patch.object(lyrics.urllib.request,'urlopen',return_value=self.response()):
            target,count=lyrics.export_lrc(song,folder,MID,self.args)
        self.assertEqual(target.name,'song.lrc');self.assertEqual(count,4)
        original=target.read_bytes()
        with patch.object(lyrics.urllib.request,'urlopen') as network:
            with self.assertRaises(FileExistsError):lyrics.export_lrc(song,folder,MID,self.args)
            network.assert_not_called()
        self.assertEqual(target.read_bytes(),original);self.assertEqual(song.read_bytes(),b'original audio')
        self.assertFalse(list(folder.glob('.lyrics-*')))

    def test_cancel_before_and_during_network(self):
        self.args.cancel_event.set()
        with patch.object(lyrics.urllib.request,'urlopen') as network:
            with self.assertRaises(Cancelled):lyrics.fetch_lrc(MID,self.args)
            network.assert_not_called()
        self.args.cancel_event.clear()
        event=self.args.cancel_event
        class Response(io.BytesIO):
            def read(self,*args):
                event.set();return super().read(*args)
        with patch.object(lyrics.urllib.request,'urlopen',return_value=Response(json.dumps({'code':0,'lyric':TEXT}).encode())):
            with self.assertRaises(Cancelled):lyrics.export_lrc(self.folder/'song.mp3',self.folder/'out',MID,self.args)
        self.assertFalse((self.folder/'out/song.lrc').exists())


if __name__=='__main__':unittest.main()
