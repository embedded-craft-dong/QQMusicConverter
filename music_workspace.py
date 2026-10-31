"""Queue actions and song editor. Network and conversion work live in tasks.py."""
from copy import deepcopy
import os
from pathlib import Path
import queue
import subprocess
import threading
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk, messagebox
import convert_music as engine
import lyrics
import tasks
from job import SessionCache
from output_files import valid_stem, output_path, save_bytes
from settings import save_output
from ui_theme import BG, TEXT, MUTED


class Workspace:
    def setup_workspace(self, card):
        self.song_options = {}
        self.results = {}
        self.outputs = {}
        self.information = {}
        self.asset_failures = set()
        self.dialog_state = None
        self.dialog_serial = 0
        self.profile = tk.StringVar(value='高质量 MP3（保留采样率）')
        self.auto_lyrics = tk.BooleanVar(value=False)
        self.auto_cover = tk.BooleanVar(value=False)
        row = ttk.Frame(card,style='Card.TFrame')
        row.pack(fill='x',pady=(self.p(10),self.p(8)))
        ttk.Label(row,text='输出格式',style='CardMuted.TLabel').pack(side='left',padx=(0,self.p(12)))
        self.profile_box = ttk.Combobox(row,textvariable=self.profile,state='readonly',
            values=('高质量 MP3（保留采样率）','开发板 WAV（48 kHz / 16-bit / 双声道）'),width=40)
        self.profile_box.pack(side='left',fill='x',expand=True)
        self.controls.append(self.profile_box)
        for text,value in [('  转换后自动导出歌词（联网）',self.auto_lyrics),
                           ('  转换后保存封面（优先内嵌，缺失时联网）',self.auto_cover)]:
            check = ttk.Checkbutton(card,text=text,variable=value,style='Music.TCheckbutton')
            check.pack(anchor='w',pady=self.p(3))
            self.controls.append(check)
        self.tree.bind('<<TreeviewSelect>>',lambda event:self.refresh_actions())
        self.tree.bind('<Button-3>',self.context_menu)
        self.refresh_actions()

    def settings_for(self,path):
        path = Path(path)
        if path not in self.song_options:
            try:
                mid = lyrics.song_mid_from_file(path)
            except OSError:
                mid = None
            self.song_options[path] = {'stem':path.stem,'mid':mid or '', 'offset':0}
        return self.song_options[path]

    def selected(self):
        return tuple(Path(item) for item in self.tree.selection())

    def refresh_actions(self):
        if not hasattr(self,'asset_failures'):
            return
        selected = bool(self.tree.selection()) and not self.busy
        for name in ('lyric_button','cover_button','selected_button'):
            if hasattr(self,name):
                getattr(self,name).configure(state='normal' if selected else 'disabled')
        self.retry.configure(state='normal' if (self.failed_files or self.asset_failures) and not self.busy else 'disabled')

    def set_busy(self,busy):
        self.busy = busy
        widgets = self.controls+[self.go,self.retry,self.selected_button]
        if self.dialog_state:
            widgets += self.dialog_state['controls']
        for widget in widgets:
            if widget.winfo_exists():
                widget.configure(state='disabled' if busy else 'normal')
        if not busy:
            self.profile_box.configure(state='readonly')
        self.cancel.configure(state='normal' if busy else 'disabled')
        self.refresh_actions()

    def context_menu(self,event):
        if self.busy:
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        if item not in self.tree.selection():
            self.tree.selection_set(item)
        menu = tk.Menu(self.root,tearoff=False)
        for text,callback in [('转换选中歌曲',lambda:self.start(self.selected())),
                              ('导出选中歌词',self.open_lyrics),('保存选中封面',self.export_covers),
                              ('歌曲设置 / 信息 / 歌词预览',self.show_detail),
                              ('定位已生成文件',self.reveal_selected)]:
            menu.add_command(label=text,command=callback)
        try:
            menu.tk_popup(event.x_root,event.y_root)
        finally:
            menu.grab_release()

    def reveal_selected(self):
        for path in self.selected():
            targets = self.outputs.get(path,{})
            target = next((Path(p) for p in targets.values() if Path(p).is_file()),None)
            if target:
                try:
                    subprocess.Popen(['explorer.exe','/select,',str(target)])
                except OSError:
                    messagebox.showinfo('定位文件',str(target),parent=self.root)
                return
        self.open_folder()

    def start(self,files=None):
        files = tuple(self.files) if files is None else tuple(files)
        jobs = []
        for path in files:
            jobs.append((path,'audio'))
            if self.auto_lyrics.get():
                jobs.append((path,'lyrics'))
            if self.auto_cover.get():
                jobs.append((path,'cover'))
        self.start_jobs(jobs)

    def retry_failed(self):
        jobs = []
        for path in self.files:
            if path in self.failed_files:
                jobs.append((path,'audio'))
            for kind in ('lyrics','cover'):
                if (path,kind) in self.asset_failures:
                    jobs.append((path,kind))
        self.start_jobs(jobs)

    def open_lyrics(self):
        chosen = self.selected()
        if not chosen or self.busy:
            return
        if len(chosen)==1 and not self.settings_for(chosen[0])['mid']:
            self.show_detail()
            return
        self.start_jobs([(path,'lyrics') for path in chosen])

    def export_covers(self):
        self.start_jobs([(path,'cover') for path in self.selected()])

    def start_lyrics(self,source,folder,reference):
        # Backward-compatible entry point used by integration tests.
        self.settings_for(source)['mid'] = reference
        self.output.set(str(folder))
        self.start_jobs([(source,'lyrics')])

    def start_jobs(self,jobs):
        if self.busy:
            return
        jobs = list(dict.fromkeys((Path(path),kind) for path,kind in jobs))
        if not jobs:
            messagebox.showinfo('选择歌曲','请添加或选中歌曲。',parent=self.root)
            return
        if any(kind=='audio' and path.suffix.lower() in engine.ENCRYPTED for path,kind in jobs) and not self.auth.get():
            messagebox.showinfo('加密歌曲需要登录状态','请先登录 QQ 音乐，再勾选使用本机登录状态。',parent=self.root)
            return
        try:
            if not self.output.get().strip():
                raise ValueError('请选择输出目录。')
            folder = Path(self.output.get()).expanduser().resolve()
            options = {path:deepcopy(self.settings_for(path)) for path,kind in jobs}
            seen = {}
            for path,item in options.items():
                item['stem'] = valid_stem(item['stem'])
                stem = item['stem'].casefold()
                if stem in seen and seen[stem]!=path:
                    raise ValueError('有重复的输出名称；请双击歌曲设置不同名称。')
                seen[stem] = path
            suffix = '.wav' if self.profile.get().startswith('开发板') else '.mp3'
            originals = set(self.files)
            for path,kind in jobs:
                extension = {'audio':suffix,'lyrics':'.lrc','cover':'.jpg'}[kind]
                target = folder/(options[path]['stem']+extension)
                if target.resolve() in originals:
                    raise ValueError('输出会覆盖队列中的原文件；请更换目录或输出名称。')
        except (ValueError,OSError) as error:
            messagebox.showerror('无法开始',str(error),parent=self.root)
            return
        self.stop.clear()
        self.batch = tuple(jobs)
        self.result_folder = folder
        save_output(folder,self.settings_file)
        self.set_busy(True)
        self.progress.configure(mode='determinate',maximum=len(jobs),value=0)
        for path,kind in jobs:
            self.results.setdefault(path,{})[kind] = ('等待处理','muted')
            if kind=='audio':self.failed_files.discard(path)
            else:self.asset_failures.discard((path,kind))
            self.render_result(path)
        self.status.set(f'正在准备 · {len(options)} 首歌曲 / {len(jobs)} 项任务')
        args = SimpleNamespace(output_dir=folder,overwrite=self.overwrite.get(),qq_login=self.auth.get(),ekey_file=None,
                               cancel_event=self.stop,session_cache=SessionCache(),profile='wav' if suffix=='.wav' else 'mp3')
        self.thread = threading.Thread(target=tasks.run_batch,args=(jobs,args,options,self.events),daemon=True)
        self.thread.start()

    def render_result(self,path):
        result = self.results.get(path,{})
        summaries = []
        for kind in ('audio','lyrics','cover'):
            if kind not in result:continue
            text,tag = result[kind]
            if kind=='audio':summaries.append(text)
            else:summaries.append(tasks.LABELS[kind]+'：'+text)
        tags = [tag for text,tag in result.values()]
        tag = 'active' if 'active' in tags else 'failed' if 'failed' in tags else 'success' if 'success' in tags else 'muted'
        if self.tree.exists(str(path)):
            self.tree.set(str(path),'status',' | '.join(summaries))
            self.tree.item(str(path),tags=(tag,))

    def center_dialog(self,dialog,width,height):
        self.root.update_idletasks()
        width = min(width,self.root.winfo_screenwidth()-40)
        height = min(height,self.root.winfo_screenheight()-80)
        x = max(0,min(self.root.winfo_rootx()+(self.root.winfo_width()-width)//2,self.root.winfo_screenwidth()-width))
        y = max(0,min(self.root.winfo_rooty()+(self.root.winfo_height()-height)//2,self.root.winfo_screenheight()-height-50))
        dialog.geometry(f'{width}x{height}+{x}+{y}')

    def show_detail(self,event=None):
        if self.busy or len(self.selected())!=1:
            return
        if self.dialog_state and self.dialog_state['window'].winfo_exists():
            self.dialog_state['window'].lift()
            return
        path = self.selected()[0]
        item = self.settings_for(path)
        self.dialog_serial += 1
        dialog = tk.Toplevel(self.root)
        dialog.title('歌曲设置 · 信息与歌词')
        dialog.configure(bg=BG)
        dialog.transient(self.root)
        p = self.p
        body = ttk.Frame(dialog,padding=p(16))
        body.pack(fill='both',expand=True)
        ttk.Label(body,text=path.name,wraplength=p(540),font=('Microsoft YaHei UI',11,'bold')).pack(anchor='w')
        book = ttk.Notebook(body)
        book.pack(fill='both',expand=True,pady=p(10))
        general_tab,lyric_page = ttk.Frame(book),ttk.Frame(book,padding=p(12))
        book.add(general_tab,text='名称与歌曲信息');book.add(lyric_page,text='歌词预览与偏移')
        scroll_canvas = tk.Canvas(general_tab,bg=BG,highlightthickness=0)
        general_scroll = ttk.Scrollbar(general_tab,command=scroll_canvas.yview)
        general_scroll.pack(side='right',fill='y')
        scroll_canvas.pack(side='left',fill='both',expand=True)
        scroll_canvas.configure(yscrollcommand=general_scroll.set)
        general = ttk.Frame(scroll_canvas,padding=p(12))
        general_item = scroll_canvas.create_window(0,0,window=general,anchor='nw')
        scroll_canvas.bind('<Configure>',lambda event:scroll_canvas.itemconfigure(general_item,width=event.width))
        general.bind('<Configure>',lambda event:scroll_canvas.configure(scrollregion=scroll_canvas.bbox('all')))
        name,mid = tk.StringVar(value=item['stem']),tk.StringVar(value=item['mid'])
        offset = tk.StringVar(value=str(item.get('offset',0)))
        controls = []
        for label,var in [('统一输出名称（不带扩展名）',name),('QQ 音乐歌曲详情页链接 / songmid（可留空）',mid)]:
            ttk.Label(general,text=label).pack(anchor='w',pady=(p(6),p(4)))
            entry = ttk.Entry(general,textvariable=var)
            entry.pack(fill='x');controls.append(entry)
        ttk.Label(general,text='音频、歌词和封面共用此名称。不会按歌名猜测演唱版本。',style='Muted.TLabel',wraplength=p(510)).pack(anchor='w',pady=p(10))
        info_text = tk.StringVar(value=self.format_info(self.information.get(path)))
        ttk.Label(general,textvariable=info_text,justify='left',wraplength=p(510)).pack(anchor='w')
        info_button = ttk.Button(general,text='读取歌曲信息'+('（联网）' if path.suffix.lower() in engine.ENCRYPTED else '（本地）'),
                                 command=self.inspect_current)
        info_button.pack(anchor='w',pady=p(8));controls.append(info_button)
        result_text = '\n'.join(tasks.LABELS[k]+': '+v[0] for k,v in self.results.get(path,{}).items())
        ttk.Label(general,text=result_text or '尚未处理',wraplength=p(510),style='Muted.TLabel').pack(anchor='w',pady=p(8))
        line = ttk.Frame(lyric_page);line.pack(fill='x')
        fetch = ttk.Button(line,text='获取歌词预览（联网）',command=self.preview_current)
        fetch.pack(side='left');controls.append(fetch)
        ttk.Label(lyric_page,text='偏移（毫秒）：正值延后，负值提前；保存和批量导出均使用此值。',wraplength=p(510),style='Muted.TLabel').pack(anchor='w',pady=(p(10),p(5)))
        spin = ttk.Spinbox(lyric_page,from_=-600000,to=600000,increment=100,textvariable=offset,width=14)
        spin.pack(anchor='w');controls.append(spin)
        save = ttk.Button(lyric_page,text='保存预览为同名 LRC',command=self.save_preview)
        save.pack(side='bottom',anchor='w');controls.append(save)
        preview_frame = ttk.Frame(lyric_page);preview_frame.pack(fill='both',expand=True,pady=p(8))
        preview = tk.Text(preview_frame,height=8,bg='#14212c',fg=TEXT,insertbackground=TEXT,wrap='word',
                          font=('Microsoft YaHei UI',10),padx=p(8),pady=p(6),relief='flat',state='disabled')
        scroll = ttk.Scrollbar(preview_frame,command=preview.yview)
        scroll.pack(side='right',fill='y');preview.pack(fill='both',expand=True)
        preview.configure(yscrollcommand=scroll.set)
        notice = tk.StringVar(value='已有 LRC / JPG 不覆盖。歌词预览需要准确的歌曲链接。')
        ttk.Label(body,textvariable=notice,style='Muted.TLabel',wraplength=p(550)).pack(anchor='w')
        actions = ttk.Frame(body);actions.pack(fill='x',pady=(p(10),0))
        apply = ttk.Button(actions,text='应用设置',style='Go.TButton',command=lambda:self.apply_song(True))
        apply.pack(side='left');controls.append(apply)
        ttk.Button(actions,text='关闭',command=self.close_song).pack(side='right')
        self.dialog_state = dict(id=self.dialog_serial,window=dialog,path=path,name=name,mid=mid,offset=offset,book=book,
                                 controls=controls,preview=preview,raw=None,notice=notice,info=info_text)
        offset.trace_add('write',lambda *unused:self.render_preview())
        mid.trace_add('write',lambda *unused:self.invalidate_preview())
        dialog.protocol('WM_DELETE_WINDOW',self.close_song)
        dialog.bind('<Escape>',lambda event:self.close_song())
        self.center_dialog(dialog,p(620),p(650))
        dialog.grab_set()

    def invalidate_preview(self):
        if self.dialog_state:
            self.dialog_state['raw']=None
            self.render_preview()

    def apply_song(self,notify=False):
        state = self.dialog_state
        if not state:return False
        try:
            name = valid_stem(state['name'].get())
            reference = state['mid'].get().strip()
            mid = lyrics.parse_song_reference(reference) if reference else ''
            offset = int(state['offset'].get())
            if abs(offset)>600000:raise ValueError('偏移限制为 ±600000 毫秒。')
            self.song_options[state['path']] = dict(stem=name,mid=mid,offset=offset)
            if notify:state['notice'].set('设置已应用，本次打开程序期间有效。')
            return True
        except (ValueError,OSError) as error:
            state['notice'].set(str(error));return False

    def preview_current(self):
        if self.busy or not self.apply_song():return
        state = self.dialog_state
        mid = self.settings_for(state['path'])['mid']
        if not mid:
            state['notice'].set('请先在“名称与歌曲信息”中填写 QQ 音乐歌曲链接。');return
        self.stop.clear();self.set_busy(True)
        self.progress.configure(mode='indeterminate');self.progress.start(20)
        state['notice'].set('正在读取歌词…')
        self.thread = threading.Thread(target=tasks.preview_lyrics,args=(mid,SimpleNamespace(cancel_event=self.stop),self.events,state['id']),daemon=True)
        self.thread.start()

    def render_preview(self):
        state = self.dialog_state
        if not state:return
        text = ''
        if state['raw']:
            try:text,count = lyrics.shift_lrc(state['raw'],int(state['offset'].get()))
            except ValueError:
                state['notice'].set('请输入 ±600000 范围内的整数毫秒。');return
        state['preview'].configure(state='normal')
        state['preview'].delete('1.0','end');state['preview'].insert('1.0',text)
        state['preview'].configure(state='disabled')

    def save_preview(self):
        if self.busy or not self.apply_song():return
        state = self.dialog_state
        if not state['raw']:
            state['notice'].set('请先获取歌词预览。');return
        try:
            if not self.output.get().strip():raise ValueError('请在主界面选择输出目录。')
            item = self.settings_for(state['path'])
            text,count = lyrics.shift_lrc(state['raw'],item['offset'])
            folder = Path(self.output.get()).expanduser().resolve()
            target = output_path(state['path'],folder,'.lrc',SimpleNamespace(output_stem=item['stem']))
            save_bytes(target,text.encode('utf-8'))
            self.outputs.setdefault(state['path'],{})['lyrics']=str(target)
            self.asset_failures.discard((state['path'],'lyrics'))
            self.results.setdefault(state['path'],{})['lyrics']=('已完成 · '+target.name,'success')
            self.render_result(state['path']);self.refresh_actions()
            self.result_folder=folder
            state['notice'].set(f'已保存 {count} 行时间戳：{target.name}')
        except Exception as error:
            state['notice'].set(tasks.explain(error))

    def inspect_current(self):
        if self.busy or not self.apply_song():return
        state = self.dialog_state
        self.stop.clear();self.set_busy(True)
        state['notice'].set('正在读取歌曲信息…')
        self.thread = threading.Thread(target=tasks.inspect_song,args=(state['path'],self.settings_for(state['path'])['mid'],
            self.events,SimpleNamespace(cancel_event=self.stop),state['id']),daemon=True)
        self.thread.start()

    @staticmethod
    def format_info(info):
        if not info:return '点击读取信息。加密文件的采样率、声道等将在转换成功后显示。'
        duration = float(info.get('duration',0))
        lines = [f'时长：{int(duration)//60:02d}:{int(duration)%60:02d}']
        for key,label in [('title','歌曲'),('artist','歌手'),('album','专辑'),('samplerate','采样率 Hz'),('channels','声道'),('format','格式'),('subtype','编码'),('source','来源')]:
            if info.get(key):lines.append(f'{label}：{info[key]}')
        return '\n'.join(lines)

    def close_song(self):
        if self.busy:self.request_stop()
        if self.dialog_state:
            self.dialog_state['window'].destroy();self.dialog_state=None

    def poll(self):
        try:
            for _ in range(100):
                event = self.events.get_nowait()
                kind = event[0]
                if kind in ('task_result','task_progress'):
                    path,job = Path(event[1]),event[2]
                    if kind=='task_result':
                        text,tag,target = event[3:]
                        self.results.setdefault(path,{})[job]=(text,tag)
                        if tag=='failed':
                            if job=='audio':self.failed_files.add(path)
                            else:self.asset_failures.add((path,job))
                        if target:self.outputs.setdefault(path,{})[job]=target
                    else:
                        text = event[3]+(f' · {event[4]}%' if event[4] is not None else '')
                        self.results.setdefault(path,{})[job]=(text,'active')
                    self.render_result(path)
                    if not self.stop.is_set():self.status.set(path.name+' · '+tasks.LABELS[job]+' · '+text)
                elif kind=='progress':self.progress.configure(value=event[1])
                elif kind=='media_info':self.information[Path(event[1])]=event[2]
                elif kind in ('batch_done','batch_error'):
                    self.set_busy(False)
                    for path,job in self.batch:
                        if self.results.get(path,{}).get(job,('',))[0]=='等待处理':
                            self.results[path][job]=('未处理','muted');self.render_result(path)
                    if kind=='batch_done':self.status.set(f'处理结束 · 完成 {event[1]} 项 · 失败 {event[2]} 项 · 取消或未处理 {event[3]} 项')
                    else:self.status.set(event[1])
                elif kind in ('preview','inspection'):
                    self.progress.stop();self.progress.configure(mode='determinate',maximum=1,value=0)
                    self.set_busy(False)
                    state = self.dialog_state
                    if state and state['id']==event[1]:
                        if event[3]:state['notice'].set(event[3])
                        elif kind=='preview':
                            state['raw']=event[2];self.render_preview()
                            state['notice'].set('已载入歌词；调整偏移可即时预览，确认后保存。')
                        else:
                            self.information[state['path']]=event[2]
                            state['info'].set(self.format_info(event[2]));state['notice'].set('歌曲信息已更新。')
                    self.status.set('准备就绪' if not event[3] else event[3])
                if self.closing and not self.busy:
                    self.root.destroy();return
        except queue.Empty:
            pass
        self.poll_id=self.root.after(80,self.poll)
