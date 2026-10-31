"""Tk integration tests; use generated audio and isolated preferences only."""
import os
import gc
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import music_gui as gui
import music_workspace as workspace
from job import checkpoint
from test_converter import tone


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        # Windows CI may return an 8.3 TEMP path; match the GUI's resolved IDs.
        self.folder=Path(self.temp.name).resolve()
        self.root=gui.tk.Tk();self.root.withdraw();self.addCleanup(self.cleanup_gui)
        self.app=gui.App(self.root,settings_file=self.folder/'settings.json')
        self.app.output.set(str(self.folder/'output'))

    def cleanup_gui(self):
        self.root.destroy()
        self.app=None
        self.root=None
        gc.collect()  # Dispose Tcl objects on their owner thread before the next worker starts.

    def wait(self):
        deadline=time.monotonic()+15
        while self.app.busy and time.monotonic()<deadline:
            self.root.update();time.sleep(.01)
        self.assertFalse(self.app.busy,'worker timeout')

    def test_checkbox_toggle_keyboard_disabled_and_default_off(self):
        self.assertFalse(self.app.auth.get());self.assertFalse(self.app.overwrite.get())
        self.app.overwrite_check.invoke();self.assertTrue(self.app.overwrite.get())
        self.app.overwrite_check.configure(state='disabled')
        self.app.overwrite_check.invoke();self.assertTrue(self.app.overwrite.get())
        self.app.overwrite_check.configure(state='normal')
        self.app.overwrite_check.event_generate('<Key-space>')
        self.root.update()
        # invoke verifies the native ttk action; physical keyboard is a visual QA check.
        self.app.auth_check.invoke();self.assertTrue(self.app.auth.get())

    def test_convert_fail_retry_and_dedup(self):
        first=tone(self.folder/'first.wav')
        broken=self.folder/'broken.wav';broken.write_bytes(b'bad')
        self.app.insert([first,first,broken]);self.assertEqual(len(self.app.files),2)
        self.app.start();self.assertTrue(self.app.busy)
        self.app.clear();self.assertEqual(len(self.app.files),2)
        self.wait()
        self.assertTrue(self.app.tree.set(str(first),'status').startswith('已完成'))
        self.assertIn(broken,self.app.failed_files)
        original=(self.folder/'output/first.mp3').read_bytes()
        tone(broken)
        self.app.retry_failed();self.wait()
        self.assertFalse(self.app.failed_files)
        self.assertEqual((self.folder/'output/first.mp3').read_bytes(),original)
        self.assertTrue((self.folder/'output/broken.mp3').exists())

    def test_stop_reenables_controls_and_leaves_remaining_unprocessed(self):
        paths=[tone(self.folder/f'{n}.wav') for n in (1,2)]
        self.app.insert(paths)
        def work(path,args,*rest):
            while True:
                checkpoint(args);time.sleep(.01)
        with patch.object(gui.engine,'convert',side_effect=work):
            self.app.start();self.root.after(50,self.app.request_stop);self.wait()
        self.assertFalse(self.app.failed_files)
        self.assertEqual(str(self.app.go['state']),'normal')
        self.assertTrue(self.app.tree.set(str(paths[0]),'status').startswith('已取消'))
        self.assertEqual(self.app.tree.set(str(paths[1]),'status'),'未处理')

    def test_lyrics_export_is_independent_of_conversion_and_login(self):
        source=tone(self.folder/'lyrics-test.wav')
        original=source.read_bytes()
        self.app.insert([source]);self.app.failed_files.add(source)
        with patch.object(gui.lyrics,'fetch_lrc',return_value=('[00:01.00]Generated test\n',1)), \
             patch.object(gui.engine,'convert') as convert:
            self.app.start_lyrics(source,self.folder/'output','00123456789abc')
            self.assertEqual(str(self.app.lyric_button['state']),'disabled')
            self.wait();convert.assert_not_called()
        self.assertTrue((self.folder/'output/lyrics-test.lrc').exists())
        self.assertFalse((self.folder/'output/lyrics-test.mp3').exists())
        self.assertEqual(source.read_bytes(),original)
        self.assertIn(source,self.app.failed_files)
        self.assertFalse(self.app.auth.get())
        self.assertEqual(str(self.app.lyric_button['state']),'disabled')  # No row selected.

    def test_selected_conversion_and_batch_lyrics_retry_do_not_reencode(self):
        first=tone(self.folder/'first.wav');second=tone(self.folder/'second.wav')
        self.app.insert([first,second])
        self.app.tree.selection_set(str(first));self.root.update()
        self.app.selected_button.invoke();self.wait()
        self.assertTrue((self.folder/'output/first.mp3').exists())
        self.assertFalse((self.folder/'output/second.mp3').exists())
        for path in (first,second):self.app.settings_for(path)['mid']='00123456789abc'
        self.app.tree.selection_set(str(first),str(second));self.root.update()
        with patch.object(gui.lyrics,'fetch_lrc',side_effect=[('[00:01.00]One\n',1),ValueError('network timeout')]):
            self.app.open_lyrics();self.wait()
        self.assertEqual(self.app.asset_failures,{(second,'lyrics')})
        with patch.object(gui.lyrics,'fetch_lrc',return_value=('[00:02.00]Two\n',1)),patch.object(gui.engine,'convert') as convert:
            self.app.retry_failed();self.wait();convert.assert_not_called()
        self.assertFalse(self.app.asset_failures)
        self.assertTrue((self.folder/'output/second.lrc').exists())

    def test_automatic_assets_share_name_and_keep_failures_separate(self):
        source=tone(self.folder/'song.wav');self.app.insert([source])
        self.app.settings_for(source).update(stem='track01',mid='00123456789abc')
        self.app.auto_lyrics.set(True);self.app.auto_cover.set(True)
        self.app.profile.set('开发板 WAV（48 kHz / 16-bit / 双声道）')
        with patch.object(gui.lyrics,'fetch_lrc',return_value=('[00:01.00]One\n',1)), \
             patch.object(workspace.tasks.media_assets,'export_cover',side_effect=ValueError('no cover')):
            self.app.start();self.wait()
        self.assertFalse(self.app.failed_files)
        self.assertIn((source,'cover'),self.app.asset_failures)
        self.assertTrue((self.folder/'output/track01.wav').exists())
        self.assertTrue((self.folder/'output/track01.lrc').exists())
        self.assertEqual(self.app.information[source]['samplerate'],48000)

    def test_preview_offset_save_and_existing_protection(self):
        source=tone(self.folder/'song.wav');self.app.insert([source]);self.app.tree.selection_set(str(source))
        self.app.settings_for(source)['mid']='00123456789abc'
        self.app.show_detail();state=self.app.dialog_state
        with patch.object(gui.lyrics,'fetch_lrc',return_value=('[00:01.00]One\n',1)):
            self.app.preview_current();self.wait()
        state['offset'].set('250');state['name'].set('preview')
        self.app.save_preview()
        target=self.folder/'output/preview.lrc'
        self.assertEqual(target.read_text(encoding='utf-8'),'[00:01.25]One\n')
        state['offset'].set('500');self.app.save_preview()
        self.assertEqual(target.read_text(encoding='utf-8'),'[00:01.25]One\n')
        self.assertIn('已存在',state['notice'].get())
        state['mid'].set('00987654321abc')
        self.assertIsNone(state['raw'])
        self.app.close_song()

    def test_output_cannot_overwrite_another_queued_original(self):
        first=tone(self.folder/'first.wav');second=tone(self.folder/'second.wav')
        self.app.insert([first,second]);self.app.profile.set('开发板 WAV')
        self.app.output.set(str(self.folder));self.app.overwrite.set(True)
        self.app.settings_for(first)['stem']='second'
        with patch.object(workspace.messagebox,'showerror') as error:
            self.app.start((first,));error.assert_called_once()
        self.assertFalse(self.app.busy)


class LayoutTests(unittest.TestCase):
    def test_small_screen_dpi_matrix_keeps_actions_accessible(self):
        for scale in (1,1.25,1.5,2):
            with self.subTest(scale=scale),tempfile.TemporaryDirectory() as folder:
                root=gui.tk.Tk()
                try:
                    root.tk.call('tk','scaling',96*scale/72)
                    root.winfo_screenwidth=lambda:1366
                    root.winfo_screenheight=lambda:768
                    app=gui.App(root,Path(folder)/'settings.json')
                    root.update()
                    self.assertLessEqual(root.winfo_height(),768)
                    for widget in (app.go,app.selected_button,app.cancel,app.open_button):
                        self.assertTrue(widget.winfo_viewable())
                        self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),root.winfo_rooty()+root.winfo_height())
                        self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),root.winfo_rootx()+root.winfo_width())
                    app.canvas.yview_moveto(1);root.update()
                    self.assertGreater(app.canvas.yview()[0],0)
                    source=tone(Path(folder)/'long-name-test.wav')
                    app.insert([source]);app.tree.selection_set(str(source.resolve()))
                    app.show_detail();root.update()
                    state=app.dialog_state;dialog=state['window']
                    self.assertLessEqual(dialog.winfo_height(),768)
                    state['book'].select(1);root.update()
                    for widget in state['controls']:
                        if widget.winfo_viewable():
                            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),dialog.winfo_rooty()+dialog.winfo_height())
                    app.close_song()
                finally:root.destroy()


if __name__=='__main__':unittest.main()
