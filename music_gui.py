"""Native Windows UI. All widget access stays on the Tk thread."""
import os
import sys
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import convert_music as engine
import lyrics
from settings import load_output, save_output
from ui_theme import BG, PANEL, TEXT, MUTED, ACCENT, install

from music_workspace import Workspace

VERSION = '0.3.0-beta.1'


class App(Workspace):
    def __init__(self, root, settings_file=None):
        self.root, self.settings_file = root, settings_file
        self.files, self.failed_files = [], set()
        self.events = queue.Queue()
        self.busy = self.closing = False
        self.stop = threading.Event()
        self.result_folder = None
        self.batch = ()
        self.scale = max(1.0, root.winfo_fpixels('1i') / 96)
        self.p = lambda value: round(value * self.scale)
        p = self.p
        root.title('音乐素材工作台 · '+VERSION)
        root.configure(bg=BG)
        icon=Path(__file__).resolve().parent/'assets/app.png'
        if icon.is_file():
            self.icon=tk.PhotoImage(file=str(icon))
            root.iconphoto(True,self.icon)
        self.style = install(root,self.scale)
        sw,sh = root.winfo_screenwidth(),root.winfo_screenheight()
        width,height = min(p(950),sw-p(40)),min(p(830),sh-p(90))
        root.geometry(f'{width}x{height}+{max(0,(sw-width)//2)}+{max(0,(sh-height)//2-p(20))}')
        root.minsize(min(p(680),width),min(p(480),height))

        # Footer stays reachable even when the settings area needs scrolling.
        footer = ttk.Frame(root, padding=(p(26),p(14),p(26),p(18)))
        footer.pack(side='bottom',fill='x')
        self.status = tk.StringVar(value='准备就绪 · 添加歌曲即可开始')
        self.status_label = ttk.Label(footer,textvariable=self.status,style='Muted.TLabel')
        self.status_label.pack(anchor='w',pady=(0,p(8)))
        self.progress = ttk.Progressbar(footer,maximum=100)
        self.progress.pack(fill='x',pady=(0,p(14)))
        actions = ttk.Frame(footer)
        actions.pack(fill='x')
        self.go = ttk.Button(actions,text='转换全部  →',style='Go.TButton',command=self.start)
        self.go.pack(side='left')
        self.selected_button=ttk.Button(actions,text='转换选中',command=lambda:self.start(self.selected()),state='disabled')
        self.selected_button.pack(side='left',padx=(p(8),0))
        self.cancel = ttk.Button(actions,text='停止',command=self.request_stop,state='disabled')
        self.cancel.pack(side='left',padx=p(8))
        self.open_button = ttk.Button(actions,text='打开输出文件夹',command=self.open_folder)
        self.open_button.pack(side='right')
        ttk.Separator(root).pack(side='bottom',fill='x')

        viewport = ttk.Frame(root)
        viewport.pack(fill='both',expand=True)
        self.canvas = tk.Canvas(viewport,bg=BG,highlightthickness=0,yscrollincrement=p(24))
        outer_scroll = ttk.Scrollbar(viewport,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=outer_scroll.set)
        outer_scroll.pack(side='right',fill='y')
        self.canvas.pack(side='left',fill='both',expand=True)
        body = ttk.Frame(self.canvas,padding=(p(26),p(24),p(16),p(10)))
        self.body = body
        self.body_id = self.canvas.create_window(0,0,window=body,anchor='nw')
        self.canvas.bind('<Configure>',self.resize_body)
        body.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        root.bind('<MouseWheel>',self.wheel,add='+')

        header = ttk.Frame(body)
        header.pack(fill='x',pady=(0,p(20)))
        title = ttk.Frame(header)
        title.pack(side='left')
        ttk.Label(title,text='AUDIO  /  CONVERTER',style='Eyebrow.TLabel').pack(anchor='w')
        ttk.Label(title,text='让音乐，自由随行。',style='Title.TLabel').pack(anchor='w',pady=(p(4),p(6)))
        ttk.Label(title,text='音频 · 歌词 · 封面，一次准备好播放器素材。',style='Muted.TLabel').pack(anchor='w')
        ttk.Label(header,text='MP3  /  WAV',style='Badge.TLabel').pack(side='right',anchor='n',pady=p(12))

        card = self.make_card(body,bottom=14)
        line = ttk.Frame(card,style='Card.TFrame')
        line.pack(fill='x',pady=(0,p(12)))
        ttk.Label(line,text='01   转换队列',style='Heading.TLabel').pack(side='left')
        self.count = tk.StringVar(value='0 首歌曲')
        ttk.Label(line,textvariable=self.count,style='CardMuted.TLabel').pack(side='right')
        toolbar = ttk.Frame(card,style='Card.TFrame')
        toolbar.pack(fill='x',pady=(0,p(12)))
        self.controls = []
        for text,command in [('＋ 添加文件',self.add_files),('添加文件夹',self.add_folder),('移除选中',self.remove)]:
            button = ttk.Button(toolbar,text=text,command=command)
            button.pack(side='left',padx=(0,p(7)))
            self.controls.append(button)
        self.retry = ttk.Button(toolbar,text='重试失败项',command=self.retry_failed,state='disabled')
        self.retry.pack(side='right')
        listbox = ttk.Frame(card,style='Card.TFrame')
        listbox.pack(fill='x')
        self.tree = ttk.Treeview(listbox,columns=('song','type','status'),show='headings',height=3)
        for key,text,colwidth,stretch in [('song','歌曲文件',400,True),('type','格式',65,False),('status','状态',220,True)]:
            self.tree.heading(key,text=text,anchor='w')
            self.tree.column(key,width=p(colwidth),minwidth=p(55),stretch=stretch,anchor='w')
        scrollbar = ttk.Scrollbar(listbox,orient='vertical',command=self.tree.yview)
        scrollbar.pack(side='right',fill='y')
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left',fill='x',expand=True)
        self.tree.tag_configure('success',foreground=ACCENT)
        self.tree.tag_configure('failed',foreground='#ffb1ad')
        self.tree.tag_configure('muted',foreground=MUTED)
        self.tree.tag_configure('active',foreground='#f1d999')
        self.empty = ttk.Label(self.tree,text='把喜欢的音乐加入队列\n点击「添加文件」开始',justify='center',style='CardMuted.TLabel')
        self.empty.place(relx=.5,rely=.58,anchor='center')
        hintline = ttk.Frame(card,style='Card.TFrame')
        hintline.pack(fill='x',pady=(p(10),0))
        ttk.Label(hintline,text='双击歌曲设置 · 支持多选',style='CardMuted.TLabel').pack(side='left')
        clear = ttk.Button(hintline,text='清空',command=self.clear)
        clear.pack(side='right')
        self.controls.append(clear)
        self.lyric_button=ttk.Button(hintline,text='导出歌词',command=self.open_lyrics)
        self.lyric_button.pack(side='right',padx=(0,p(8)))
        self.controls.append(self.lyric_button)
        self.cover_button=ttk.Button(hintline,text='保存封面',command=self.export_covers)
        self.cover_button.pack(side='right',padx=(0,p(8)))
        self.controls.append(self.cover_button)

        card = self.make_card(body)
        ttk.Label(card,text='02   输出与选项',style='Heading.TLabel').pack(anchor='w',pady=(0,p(12)))
        destination = ttk.Frame(card,style='Card.TFrame')
        destination.pack(fill='x',pady=(0,p(10)))
        self.output = tk.StringVar(value=load_output(settings_file))
        entry = ttk.Entry(destination,textvariable=self.output)
        entry.pack(side='left',fill='x',expand=True,padx=(0,p(8)))
        choose = ttk.Button(destination,text='选择位置',command=self.choose_output)
        choose.pack(side='right')
        self.controls.extend([entry,choose])
        self.auth,self.overwrite = tk.BooleanVar(value=False),tk.BooleanVar(value=False)
        self.auth_check = ttk.Checkbutton(card,text='  使用本机 QQ 音乐登录状态处理加密歌曲',variable=self.auth,style='Music.TCheckbutton')
        self.auth_check.pack(anchor='w',pady=(p(2),p(4)))
        self.overwrite_check = ttk.Checkbutton(card,text='  覆盖已有同名音频（歌词与封面不覆盖）',variable=self.overwrite,style='Music.TCheckbutton')
        self.overwrite_check.pack(anchor='w')
        self.controls.extend([self.auth_check,self.overwrite_check])
        self.setup_workspace(card)
        note = ttk.Frame(card,style='Card.TFrame')
        note.pack(fill='x',pady=(p(10),0))
        self.note = ttk.Label(note,text='普通音频无需登录。加密歌曲需先打开并登录 QQ 音乐；会扫描其可读内存查找会话，\n仅向 QQ 音乐接口请求密钥，不保存凭据。',style='CardMuted.TLabel',justify='left')
        self.note.pack(anchor='w')
        ttk.Label(body,text='原件保留  /  默认不覆盖  /  输出完整校验',style='Muted.TLabel').pack(anchor='center',pady=(p(16),p(6)))
        self.tree.bind('<Double-1>',self.show_detail)
        self.tree.bind('<Delete>',lambda e:self.remove())
        root.bind('<Control-o>',lambda e:self.add_files())
        root.bind('<Escape>',lambda e:self.request_stop() if self.busy else None)
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after_idle(lambda:self.canvas.yview_moveto(0))
        self.poll_id=root.after(80,self.poll)
        root.bind('<Destroy>',self.on_destroy,add='+')

    def on_destroy(self,event):
        if event.widget==self.root:
            self.stop.set()
            if self.poll_id:
                self.root.after_cancel(self.poll_id)
                self.poll_id=None

    def make_card(self,parent,bottom=0):
        p=self.p
        outer=tk.Canvas(parent,bg=BG,highlightthickness=0,height=1)
        outer.pack(fill='x',pady=(0,p(bottom)))
        frame=ttk.Frame(outer,style='Card.TFrame',padding=p(14))
        item=outer.create_window(p(5),p(5),window=frame,anchor='nw')
        def draw(event=None):
            width=outer.winfo_width()
            outer.itemconfigure(item,width=max(1,width-p(10)))
            height=frame.winfo_reqheight()+p(10)
            outer.configure(height=height)
            outer.delete('background')
            radius=p(14);w=width-1;h=height-1
            points=[radius,1,w-radius,1,w,1,w,radius,w,h-radius,w,h,w-radius,h,
                    radius,h,1,h,1,h-radius,1,radius,1,1]
            outer.create_polygon(points,smooth=True,splinesteps=24,fill=PANEL,outline='#263442',tags='background')
            outer.tag_lower('background')
        outer.bind('<Configure>',draw)
        frame.bind('<Configure>',draw)
        return frame

    def resize_body(self,event):
        self.canvas.itemconfigure(self.body_id,width=event.width)
        if hasattr(self,'note'):
            self.note.configure(wraplength=max(self.p(200),event.width-self.p(90)))
            self.status_label.configure(wraplength=max(self.p(200),event.width-self.p(60)))

    def wheel(self,event):
        if self.canvas.bbox('all') and self.canvas.bbox('all')[3] > self.canvas.winfo_height():
            # Keep the queue's own scrollbar when it has enough rows to scroll.
            if event.widget == self.tree and len(self.files)>3:
                return
            self.canvas.yview_scroll(-1 if event.delta>0 else 1,'units')

    def refresh_count(self):
        self.count.set(f'{len(self.files)} 首歌曲')
        if self.files:
            self.empty.place_forget()
        else:
            self.empty.place(relx=.5,rely=.58,anchor='center')
        self.refresh_actions()

    def insert(self,paths):
        if self.busy:return
        existing=set(self.files)
        for path in paths:
            p=Path(path).resolve()
            if p.is_file() and p.suffix.lower() in engine.ENCRYPTED|engine.ORDINARY and p not in existing:
                self.files.append(p);existing.add(p)
                self.tree.insert('','end',iid=str(p),values=(p.name,p.suffix[1:].upper(),'等待转换'),tags=('muted',))
        self.refresh_count()

    def add_files(self):
        if self.busy:return
        self.insert(filedialog.askopenfilenames(parent=self.root,title='选择歌曲，可多选',filetypes=[
            ('音频文件','*.ogg *.wav *.flac *.mp3 *.mgg *.mflac *.qmc0 *.qmcflac *.qmcogg'),('所有文件','*.*')]))

    def add_folder(self):
        if self.busy:return
        folder=filedialog.askdirectory(parent=self.root,title='选择歌曲文件夹（仅当前层）')
        if folder:
            try:
                before=len(self.files)
                self.insert(sorted(Path(folder).iterdir()))
                if len(self.files)==before:
                    messagebox.showinfo('没有新歌曲','未发现支持的新文件。',parent=self.root)
            except OSError:
                messagebox.showerror('无法读取','请检查文件夹访问权限。',parent=self.root)

    def remove(self):
        if self.busy:return
        for item in self.tree.selection():
            path=Path(item)
            self.files.remove(path);self.failed_files.discard(path);self.tree.delete(item)
            self.asset_failures={pair for pair in self.asset_failures if pair[0]!=path}
            for mapping in (self.song_options,self.results,self.outputs,self.information):mapping.pop(path,None)
        self.refresh_count()

    def clear(self):
        if self.busy:return
        self.files.clear();self.failed_files.clear();self.asset_failures.clear()
        for mapping in (self.song_options,self.results,self.outputs,self.information):mapping.clear()
        for item in self.tree.get_children():self.tree.delete(item)
        self.refresh_count()

    def choose_output(self):
        if self.busy:return
        folder=filedialog.askdirectory(parent=self.root,title='选择音频与素材保存位置')
        if folder:
            self.output.set(folder)
            save_output(folder,self.settings_file)

    def request_stop(self):
        if not self.busy:return
        self.stop.set();self.cancel.configure(state='disabled')
        self.status.set('正在取消并清理临时文件… 网络请求可能需要等待超时。')

    def close(self):
        save_output(self.output.get(),self.settings_file)
        if self.busy:
            self.closing=True;self.request_stop()
        else:self.root.destroy()

    def open_folder(self):
        folder=self.result_folder or Path(self.output.get())
        try:
            if folder.is_dir():os.startfile(str(folder))
            else:messagebox.showinfo('尚未创建文件夹','完成转换后，可在这里打开输出文件夹。',parent=self.root)
        except OSError:
            messagebox.showerror('无法打开','请检查输出目录是否存在。',parent=self.root)


def main():
    if len(sys.argv)==3 and sys.argv[1]=='--self-test':
        from frozen_smoke import run
        raise SystemExit(run(sys.argv[2]))
    if os.name=='nt':
        import ctypes
        try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError,AttributeError):pass
    root=tk.Tk()
    App(root)
    root.mainloop()


if __name__=='__main__':
    main()
