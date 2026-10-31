"""Offline regression tests. Fixtures are synthesized in a temporary directory."""
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
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import convert_music as engine
import qmc_core as qmc
import qq_session
from job import Cancelled,SessionCache
import settings


def tone(path,seconds=1):
    x=.2*np.sin(np.arange(int(44100*seconds))*440*2*np.pi/44100)
    sf.write(path,np.stack((x,x*.4),axis=1),44100)
    return path


def args(folder,**kwargs):
    values=dict(output_dir=folder,overwrite=False,qq_login=False,ekey_file=None,
                cancel_event=threading.Event(),session_cache=SessionCache(),notify=lambda _:None)
    values.update(kwargs)
    return SimpleNamespace(**values)


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_known_tea_vectors(self):
        self.assertEqual(qmc.tea_block(bytes.fromhex('56276ba980b9ec16'),bytes.fromhex('0102030405060708090a0b0c0d0e0f00')),bytes(range(1,9)))
        self.assertEqual(qmc.tea(bytes.fromhex('91095162e3f5b6dc6b414b50d1a5b84ec50d0c1b1196fd3c'),b'12345678ABCDEFGH'),bytes(range(1,9)))

    def test_synthetic_encrypted_roundtrip_and_wrong_key(self):
        audio=tone(self.root/'tone.ogg').read_bytes()
        rawkey=bytes(range(1,129))
        keyfile=self.root/'synthetic-key.txt'
        keyfile.write_text(base64.b64encode(rawkey).decode())
        meta=bytearray(140)
        for offset,text in [(12,'testmid'),(72,'test.mgg')]:
            data=text.encode('utf-16le');meta[offset:offset+len(data)]=data
        source=self.root/'合成测试.mgg'
        source.write_bytes(qmc.decrypt(audio,rawkey)+meta+struct.pack('<II',156,1)+b'musicex\0')
        a=args(self.root/'out',ekey_file=keyfile)
        target=engine.convert(source,a,sf,np)
        info=sf.info(target)
        self.assertEqual((info.format,info.channels,info.samplerate),('MP3',2,44100))
        self.assertLess(abs(info.duration-1),.06)
        before=target.read_bytes()
        keyfile.write_text(base64.b64encode(bytes(range(128))).decode())
        a.overwrite=True
        with self.assertRaises(ValueError):engine.convert(source,a,sf,np)
        self.assertEqual(target.read_bytes(),before)

    def test_corrupt_ogg_and_unsupported_footer(self):
        data=tone(self.root/'tone.ogg').read_bytes()
        engine.validate_ogg(data)
        for bad in (b'',data[:10],data[:-2],data[:35]+b'X'+data[36:]):
            with self.subTest(length=len(bad)):
                with self.assertRaises(ValueError):engine.validate_ogg(bad)
        with self.assertRaises(ValueError):engine.musicex(b'bad')

    def test_overwrite_and_original_protection(self):
        source=tone(self.root/'tone.wav')
        a=args(self.root/'out')
        target=engine.convert(source,a,sf,np);before=target.read_bytes()
        with self.assertRaises(ValueError):engine.convert(source,a,sf,np)
        self.assertEqual(target.read_bytes(),before)
        a.overwrite=True
        engine.convert(source,a,sf,np)
        with self.assertRaises(ValueError):engine.convert(target,args(target.parent,overwrite=True),sf,np)

    def test_cancel_encoding_and_verification_preserve_existing_output(self):
        source=tone(self.root/'tone.wav',4)
        folder=self.root/'out';folder.mkdir()
        target=folder/'tone.mp3';target.write_bytes(b'existing output')
        for phase in ('编码 MP3','验证 MP3'):
            a=args(folder,overwrite=True)
            a.progress=lambda name,value:a.cancel_event.set() if name==phase else None
            with self.assertRaises(Cancelled):engine.convert(source,a,sf,np)
            self.assertEqual(target.read_bytes(),b'existing output')
            self.assertFalse(list(folder.glob('.convert-*')))

    def test_cancel_decrypt_and_crc(self):
        a=args(self.root)
        a.cancel_event.set()
        with self.assertRaises(Cancelled):engine.validate_ogg(tone(self.root/'tone.ogg').read_bytes(),a)
        def cancel(_):raise Cancelled()
        for key in (bytes(range(1,129)),bytes(range(256))*2):
            with self.assertRaises(Cancelled):qmc.decrypt(b'abc'*10000,key,cancel)

    def test_progress_is_meaningful(self):
        events=[]
        a=args(self.root/'out',progress=lambda name,value:events.append((name,value)))
        engine.convert(tone(self.root/'tone.wav',4),a,sf,np)
        for name in ('编码 MP3','验证 MP3'):
            values=[v for n,v in events if n==name]
            self.assertTrue(any(0<v<1 for v in values))
            self.assertEqual(values,sorted(values))
            self.assertEqual(values[-1],1)

    def test_session_scan_budget_and_token_boundaries(self):
        for budget in (0,1,qq_session.CHUNK_SIZE+2,5*1024*1024):
            chunks=list(qq_session.scan_chunks(0,2**36,budget))
            self.assertLessEqual(sum(size for _,size in chunks),budget)
        token='SYNTHETIC_TOKEN_FOR_OFFLINE_TEST'
        raw=json.dumps({'authst':token})
        for data in (raw.encode(),raw.encode('utf-16le'),b'x'+raw.encode('utf-16le')):
            self.assertEqual(qq_session.extract_tokens(data),{token})

    @unittest.skipUnless(sys.platform=='win32','Windows session adapter')
    def test_batch_reuses_session_without_live_credentials_or_network(self):
        config=self.root/'AppData/Roaming/Tencent/QQMusic/QQMusicServiceConfig.ini'
        config.parent.mkdir(parents=True);config.write_text('uin=12345')
        reply=json.dumps({'req_1':{'data':{'midurlinfo':[{'ekey':'SYNTHETIC_KEY'}]}}}).encode()
        a=args(self.root)
        with patch.object(engine.Path,'home',return_value=self.root), \
             patch.object(qq_session,'session_candidates',return_value={'SYNTHETIC_SESSION_ONLY'}) as scan, \
             patch.object(engine.urllib.request,'urlopen',side_effect=lambda *a,**k:io.BytesIO(reply)) as network:
            self.assertEqual(engine.login_key('one','one.mgg',a),'SYNTHETIC_KEY')
            engine.login_key('two','two.mgg',a)
            self.assertEqual(scan.call_count,1)
            self.assertEqual(network.call_count,2)
            a.session_cache.clear()
            self.assertFalse(a.session_cache.tokens)

    def test_settings_only_persist_output_and_survive_corruption(self):
        path=self.root/'settings.json'
        self.assertTrue(settings.save_output(self.root/'音乐',path))
        self.assertEqual(set(json.loads(path.read_text(encoding='utf-8'))),{'output_dir'})
        self.assertEqual(settings.load_output(path),str(self.root/'音乐'))
        path.write_text('invalid')
        self.assertIsInstance(settings.load_output(path),str)


if __name__=='__main__':unittest.main()
