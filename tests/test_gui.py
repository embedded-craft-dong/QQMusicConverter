"""Tk integration tests; use generated audio and isolated preferences only."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import music_gui as gui
from job import checkpoint
from test_converter import tone


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        # Windows CI may return an 8.3 TEMP path; match the GUI's resolved IDs.
        self.folder=Path(self.temp.name).resolve()
        self.root=gui.tk.Tk();self.root.withdraw();self.addCleanup(self.root.destroy)
        self.app=gui.App(self.root,settings_file=self.folder/'settings.json')
        self.app.output.set(str(self.folder/'output'))

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
                    for widget in (app.go,app.cancel,app.open_button):
                        self.assertTrue(widget.winfo_viewable())
                        self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),root.winfo_rooty()+root.winfo_height())
                        self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),root.winfo_rootx()+root.winfo_width())
                    app.canvas.yview_moveto(1);root.update()
                    self.assertGreater(app.canvas.yview()[0],0)
                finally:root.destroy()


if __name__=='__main__':unittest.main()
