"""Small native launcher; pipeline workers remain independent of this window."""
from pathlib import Path
import hashlib
import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from urllib.request import urlopen
from PIL import Image, ImageTk
from rinayaki.video_input import preview, local_thumbnail
from rinayaki.job import job_lock
from rinayaki.languages import SOURCE_LABELS, TARGET_LABELS, stored_languages, stored_speaker_count
from rinayaki.project_storage import (create_cached_project, destination_path,
    update_destination, lifecycle_lock, control_path, checked_cache_job,
    create_direct_project, is_direct_project)
from rinayaki.styling import PRESETS, FONTS, DEFAULT_FONT, normalize_color, validate_styles, register_private_fonts, tk_family
from rinayaki.style_preview import render_style_preview
from rinayaki.settings import (DEFAULT_ASR_MODEL, DEFAULT_BASE_URL, DEFAULT_HTTP_API_URL,
    DEFAULT_REFINEMENT_MODEL, DEFAULT_TRANSLATION_MODEL, DEFAULT_WEBSOCKET_URL,
    load_settings, save_settings as save_user_settings)
from rinayaki.live.capture import list_loopback_devices
from rinayaki.live.session import LiveSettings
from rinayaki.guidance import discover_packs, load_guidance
from rinayaki.web_session import can_open_session, launch_session, session_target
from full_video_pipeline import write_json

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT.parent / 'RinaYakiCache'
PROJECT_INDEX = ROOT/'.local/projects.json'
LIVE_SOURCE_LOCAL = '本机音轨'
LIVE_SOURCE_STREAM = '直播音频（暂未开放）'
LIVE_DISPLAY_MODES = {'只显示原文':'source', '只显示译文':'translation', '双语显示':'bilingual'}
LIVE_ENGINE_LABELS = {'标准（ASR＋MT）':'asr-mt', 'LiveTranslate':'livetranslate'}


def build_live_command(python, config):
    """Build a secret-free command for one independent live session process."""
    command = [str(python), '-m', 'rinayaki.live',
               '--project-root', str(ROOT),
               '--source', config['source_language'],
               '--target', config['target_language'],
               '--display-mode', config['display_mode'],
               '--font-family', config['font_family'],
               '--font-size', str(config.get('font_size',14)),
               '--subtitle-color', config['subtitle_color'],
               '--subtitle-lines', '8']
    if config.get('translation_engine'):
        command.extend(['--translation-engine',config['translation_engine']])
    if config.get('device'):
        command.extend(['--device', config['device']])
    if config.get('session_name'):
        command.extend(['--session-name', config['session_name']])
    if not config.get('record_session', True):
        command.append('--no-record')
    if config['display_mode'] != 'source':
        for pack_id in config.get('guidance_packs',()):
            command.extend(['--guidance-pack',pack_id])
        if config.get('guidance_packs') and config.get('allow_draft_guidance'):
            command.append('--allow-draft-guidance')
    return command


class ScrollBody(ttk.Frame):
    """Scrollable form; action bars stay outside and always retain their space."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self,highlightthickness=0,width=1,height=1)
        self.bar = ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        self.bar.pack(side='right',fill='y')
        self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=self._update_scrollbar)
        self.content = ttk.Frame(self.canvas)
        self.item = self.canvas.create_window(0,0,window=self.content,anchor='nw')
        self.content.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda event:self.canvas.itemconfigure(self.item,width=event.width))
        # Only mouse events within this form; no global keyboard/focus bindings.
        self.winfo_toplevel().bind('<MouseWheel>',self._wheel,add='+')

    def _update_scrollbar(self, first, last):
        self.bar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.bar.pack_forget()
        elif not self.bar.winfo_manager():
            self.bar.pack(side='right', fill='y', before=self.canvas)

    def _wheel(self,event):
        if str(event.widget).startswith(str(self)+'.') and not isinstance(event.widget,ttk.Combobox):
            if self.canvas.yview() != (0.0,1.0):
                self.canvas.yview_scroll(-int(event.delta/120),'units')


class QualityPicker(ttk.Menubutton):
    """Compact quality menu with hover help for selectable locked entries."""
    def __init__(self, parent, variable, on_locked):
        super().__init__(parent, textvariable=variable, width=23)
        self.variable = variable
        self.on_locked = on_locked
        self.items = []
        self.tooltip = None
        self.menu = tk.Menu(self, tearoff=False)
        self.configure(menu=self.menu)
        self.menu.bind('<<MenuSelect>>', self._menu_hover, add='+')
        self.menu.bind('<Unmap>', lambda _event: self.hide_tooltip(), add='+')

    def set_items(self, items):
        self.hide_tooltip()
        self.menu.delete(0, 'end')
        self.items = [item for item in items if isinstance(item, dict)]
        available = []
        for item in self.items:
            locked = not item.get('available', True)
            label = item.get('label', '') + ('  🔒' if locked else '')
            if locked:
                command = lambda value=item: self.on_locked(value)
            else:
                available.append(item)
                command = lambda value=item: self.variable.set(value['label'])
            self.menu.add_command(label=label, command=command)
        valid_labels = {item['label'] for item in available}
        if self.variable.get() not in valid_labels:
            self.variable.set(available[0]['label'] if available else '')

    def _menu_hover(self, _event=None):
        try:
            index = self.menu.index('active')
            item = self.items[index] if index is not None else None
        except (tk.TclError, IndexError, TypeError):
            item = None
        if not item or item.get('available', True):
            self.hide_tooltip()
            return
        self.show_tooltip(item.get('message') or '当前没有此画质的访问权限。')

    def show_tooltip(self, text):
        self.hide_tooltip()
        self.tooltip = tk.Toplevel(self)
        self.tooltip.overrideredirect(True)
        self.tooltip.attributes('-topmost', True)
        x, y = self.winfo_pointerx() + 12, self.winfo_pointery() + 12
        self.tooltip.geometry(f'+{x}+{y}')
        ttk.Label(self.tooltip, text=text, padding=7, wraplength=320).pack()

    def hide_tooltip(self):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def destroy(self):
        self.hide_tooltip()
        super().destroy()


class TransientNotice:
    """Small non-blocking notice that can be dismissed and expires by itself."""
    def __init__(self, owner, text, duration=3500):
        self.window = tk.Toplevel(owner)
        self.window.overrideredirect(True)
        self.window.transient(owner)
        self.window.attributes('-topmost', True)
        frame = tk.Frame(self.window, background='#fff2f4', highlightthickness=1,
                         highlightbackground='#e58c9d')
        frame.pack(fill='both', expand=True)
        close = tk.Label(frame, text='×', background='#fff2f4', foreground='#7a3341',
                         cursor='hand2', font=('Segoe UI', 12))
        close.pack(side='right', anchor='n', padx=(8, 9), pady=(5, 0))
        close.bind('<Button-1>', lambda _event:self.destroy())
        tk.Label(frame, text=text, background='#fff2f4', foreground='#5d2631',
                 justify='left', wraplength=420, padx=14, pady=12,
                 font=('Microsoft YaHei UI', 10)).pack(side='left', fill='both', expand=True)
        self.window.update_idletasks()
        width = min(480, max(280, self.window.winfo_reqwidth()))
        height = self.window.winfo_reqheight()
        x = owner.winfo_rootx() + 18
        y = owner.winfo_rooty() + max(18, owner.winfo_height() - height - 22)
        self.window.geometry(f'{width}x{height}+{x}+{y}')
        self.timer = self.window.after(duration, self.destroy)

    def destroy(self):
        if self.window.winfo_exists():
            self.window.destroy()


class App:
    def __init__(self, window):
        self.window = window
        window.title('RinaYaki')
        window.geometry('820x640')
        window.minsize(780, 540)
        style = ttk.Style(window)
        style.configure('.',font=('Microsoft YaHei UI',10))
        style.configure('Primary.TButton',font=('Microsoft YaHei UI',10,'bold'),padding=(18,10))
        self.events = queue.Queue()
        self.selected = None
        self.job = None
        self.worker = None
        self.managed_job = None
        self.editing_job = None
        self.worker_started = 0
        self.revision = 0
        self.screen = 'input'
        self.styles = {}
        self.prepared = None
        self.sample_revision = 0
        self.tooltip = None
        self.notice = None
        self.web_sessions = {}
        self.user_settings = load_settings(ROOT)
        self.value = tk.StringVar()
        self.status = tk.StringVar()
        body = ttk.Frame(window, padding=18)
        body.pack(fill='both', expand=True)
        heading = ttk.Frame(body)
        heading.pack(fill='x',pady=(0,12))
        ttk.Label(heading, text='RinaYaki', font=('Segoe UI',24,'bold')).pack(side='left')
        ttk.Button(heading,text='设置',command=self.open_settings).pack(side='right')
        self.mode_notebook = ttk.Notebook(body)
        self.mode_notebook.pack(fill='both',expand=True)
        self.video_tab = ttk.Frame(self.mode_notebook,padding=(2,18,2,0))
        self.live_tab = ttk.Frame(self.mode_notebook,padding=(2,18,2,0))
        self.mode_notebook.add(self.video_tab,text='视频翻译')
        self.mode_notebook.add(self.live_tab,text='实时翻译')
        self.mode_notebook.bind('<<NotebookTabChanged>>',self.mode_changed)
        self.mode_notebook.bind('<ButtonPress-1>',self.release_live_input_focus,add='+')
        outer = self.video_tab
        self.input_page = ttk.Frame(outer)
        self.input_page.pack(fill='both',expand=True)
        controls = ttk.Frame(self.input_page)
        controls.pack(side='bottom',fill='x',pady=(8,4))
        self.open_project_button = ttk.Button(controls,text='打开项目文件夹',command=self.open_folder)
        self.open_project_button.pack(anchor='e')
        self.start = ttk.Button(controls,text='继续',style='Primary.TButton',state='disabled',command=self.open_project_settings)
        self.start.pack(fill='x',pady=(8,0))
        self.video_scroll = ScrollBody(self.input_page)
        self.video_scroll.pack(fill='both',expand=True)
        body = self.video_scroll.content
        ttk.Label(body, text='上传视频链接/视频号/本地视频').pack(anchor='w', pady=(0,6))
        row = ttk.Frame(body)
        row.pack(fill='x')
        self.entry = ttk.Entry(row, textvariable=self.value)
        self.entry.pack(side='left',fill='x',expand=True,ipady=7)
        self.entry.bind('<Return>',lambda _:self.preview_action())
        ttk.Button(row,text='📁',width=4,command=self.choose).pack(side='left',padx=8)
        self.preview_button = ttk.Button(row,text='预览',command=self.preview_action)
        self.preview_button.pack(side='left')
        self.login_button = ttk.Button(row,text='登录',state='disabled',command=self.open_login_window)
        self.login_button.pack(side='left',padx=(8,0))
        self.cover_frame = ttk.Frame(body,width=310,height=175)
        self.cover_frame.pack(anchor='center',pady=(20,12))
        self.cover_frame.pack_propagate(False)
        self.cover = tk.Label(self.cover_frame,text='▶',anchor='center',font=('Segoe UI',40),
                              background='#eee8ed',foreground='#111111')
        self.cover.pack(fill='both',expand=True)
        self.title = ttk.Label(body,text='',wraplength=700,font=('Microsoft YaHei UI',11))
        self.title.pack(anchor='w')
        self.duration = ttk.Label(body,text='')
        self.duration.pack(anchor='w',pady=8)
        self.quality = tk.StringVar(value='自动')
        self.quality_ids = {'自动': 'auto'}
        self.quality_picker = QualityPicker(body, self.quality, self.show_quality_requirement)
        self.build_work_pages(outer)
        self.build_live_page(self.live_tab)
        self.footer = ttk.Label(outer,textvariable=self.status,wraplength=700)
        self.value.trace_add('write',self.changed)
        window.protocol('WM_DELETE_WINDOW', self.close_window)
        self.fit_initial_window()
        window.after(150,self.poll)

    def fit_initial_window(self):
        """Measure real Tk font metrics (including Windows scaling), once at startup."""
        self.window.update_idletasks()
        forms = (self.video_scroll,self.live_source_scroll,self.live_display_scroll)
        groups = self.live_option_groups
        options_width = sum(group.winfo_reqwidth() for group in groups)+14
        width = max(820,max(options_width,*(form.content.winfo_reqwidth() for form in forms))+80)
        # Header, tabs, page heading, fixed actions and margins also scale with fonts.
        chrome = max(0,self.mode_notebook.winfo_reqheight()-self.video_tab.winfo_reqheight())
        font_height = ttk.Label(self.window,font=('Microsoft YaHei UI',10),text='测试')
        line = font_height.winfo_reqheight()
        font_height.destroy()
        display_height = (self.live_display_scroll.content.winfo_reqheight()
                          - self.live_options.winfo_reqheight()
                          + max(group.winfo_reqheight() for group in groups))
        height = max(660,max(self.video_scroll.content.winfo_reqheight(),
                            self.live_source_scroll.content.winfo_reqheight(),display_height)+chrome+line*7+100)
        width = min(width,self.window.winfo_screenwidth()-60)
        height = min(height,self.window.winfo_screenheight()-100)
        self.window.minsize(min(780,width),min(540,height))
        x = max(0,(self.window.winfo_screenwidth()-width)//2)
        y = max(20,(self.window.winfo_screenheight()-height-40)//2)
        self.window.geometry(f'{width}x{height}+{x}+{y}')

    def open_settings(self):
        current = load_settings(ROOT)
        dialog = tk.Toplevel(self.window)
        dialog.title('RinaYaki 设置')
        dialog.geometry('660x570')
        dialog.minsize(620,540)
        dialog.transient(self.window)
        dialog.grab_set()
        frame = ttk.Frame(dialog,padding=20)
        frame.pack(fill='both',expand=True)
        notebook = ttk.Notebook(frame)
        notebook.pack(fill='both',expand=True)
        api_page, model_page, general_page = (ttk.Frame(notebook,padding=16) for _ in range(3))
        notebook.add(api_page,text='API')
        notebook.add(model_page,text='模型')
        notebook.add(general_page,text='通用')

        api_key = tk.StringVar()
        base_url = tk.StringVar(value=current.base_url)
        http_url = tk.StringVar(value=current.http_api_url)
        websocket_url = tk.StringVar(value=current.websocket_url)
        interval = tk.StringVar(value=str(current.minimum_interval_seconds))
        asr_model = tk.StringVar(value=current.asr_model)
        translation_model = tk.StringVar(value=current.translation_model)
        refinement_model = tk.StringVar(value=current.refinement_model)
        live_engine = tk.StringVar(value=next(label for label,value in LIVE_ENGINE_LABELS.items()
                                             if value == current.live_engine))
        project_dir = tk.StringVar(value=current.default_project_dir)

        def labelled(parent, row, text, variable, *, secret=False, button=None, button_text='→'):
            ttk.Label(parent,text=text).grid(row=row,column=0,sticky='w',pady=(0,5))
            entry = ttk.Entry(parent,textvariable=variable,show='•' if secret else '')
            entry.grid(row=row+1,column=0,sticky='ew',pady=(0,13),ipady=4)
            if button:
                ttk.Button(parent,text=button_text,width=4,command=button).grid(row=row+1,column=1,padx=(8,0),pady=(0,13))
            parent.columnconfigure(0,weight=1)
            return entry

        ttk.Label(api_page,text='服务商').grid(row=0,column=0,sticky='w',pady=(0,5))
        provider = ttk.Entry(api_page)
        provider.insert(0,'阿里云百炼')
        provider.configure(state='readonly')
        provider.grid(row=1,column=0,sticky='ew',pady=(0,13),ipady=4)
        key_entry = labelled(api_page,2,'API Key',api_key,secret=True,
            button=lambda:messagebox.showinfo('获取 API Key','登录阿里云百炼控制台，在 API Key 管理页面创建按量付费 Key。\n\nKey 通常以 sk- 开头，只保存在当前 Windows 用户的本地配置中。',parent=dialog),button_text='?')
        if current.api_key:
            key_entry.insert(0,'')
        labelled(api_page,4,'兼容 API 地址',base_url,
            button=lambda:(base_url.set(DEFAULT_BASE_URL),http_url.set(DEFAULT_HTTP_API_URL),websocket_url.set(DEFAULT_WEBSOCKET_URL)))
        labelled(api_page,6,'最小请求间隔（秒）',interval)
        advanced = ttk.LabelFrame(api_page,text='高级地址',padding=10)
        advanced.grid(row=8,column=0,columnspan=2,sticky='ew',pady=(3,0))
        labelled(advanced,0,'语音 HTTP API',http_url)
        labelled(advanced,2,'实时语音 WebSocket',websocket_url)

        labelled(model_page,0,'语音识别',asr_model,button=lambda:asr_model.set(DEFAULT_ASR_MODEL))
        labelled(model_page,2,'字幕翻译',translation_model,button=lambda:translation_model.set(DEFAULT_TRANSLATION_MODEL))
        labelled(model_page,4,'字幕精修',refinement_model,button=lambda:refinement_model.set(DEFAULT_REFINEMENT_MODEL))
        ttk.Label(model_page,text='实时翻译').grid(row=6,column=0,sticky='w',pady=(0,5))
        self.live_engine_combo = ttk.Combobox(model_page,textvariable=live_engine,
            values=list(LIVE_ENGINE_LABELS),state='readonly')
        self.live_engine_combo.grid(row=7,column=0,sticky='ew',pady=(0,13),ipady=4)

        def choose_default():
            value = filedialog.askdirectory(title='选择默认项目目录',parent=dialog)
            if value:
                project_dir.set(value)
        labelled(general_page,0,'默认项目目录',project_dir,button=choose_default,button_text='📁')
        ttk.Button(general_page,text='打开翻译指导文件夹',command=self.open_guidance_folder).grid(row=2,column=0,sticky='w',pady=(4,0))

        status = tk.StringVar()
        ttk.Label(frame,textvariable=status,foreground='#668f8b').pack(anchor='w',pady=(10,0))
        actions = ttk.Frame(frame)
        actions.pack(fill='x',pady=(10,0))
        ttk.Button(actions,text='取消',command=dialog.destroy).pack(side='right')
        def save():
            try:
                self.user_settings = save_user_settings({
                    'apiKey':api_key.get().strip() or None,'baseUrl':base_url.get(),
                    'httpApiUrl':http_url.get(),'websocketUrl':websocket_url.get(),
                    'minimumIntervalSeconds':interval.get(),'asrModel':asr_model.get(),
                    'translationModel':translation_model.get(),'refinementModel':refinement_model.get(),
                    'liveEngine':LIVE_ENGINE_LABELS[live_engine.get()],
                    'defaultProjectDir':project_dir.get()},ROOT)
                if not self.job and self.user_settings.default_project_dir:
                    self.project_parent.set(self.user_settings.default_project_dir)
                status.set('已保存；新项目会使用这套配置。')
                dialog.after(500,dialog.destroy)
            except (OSError,ValueError) as error:
                messagebox.showerror('无法保存设置',str(error),parent=dialog)
        ttk.Button(actions,text='保存设置',command=save).pack(side='right',padx=(0,8))

    def build_live_page(self, parent):
        self.live_devices_loaded = False
        self.live_device_ids = {'跟随系统默认输出设备':None}
        self.live_source_kind = tk.StringVar(value=LIVE_SOURCE_LOCAL)
        self.live_device = tk.StringVar(value='跟随系统默认输出设备')
        self.live_stream_url = tk.StringVar()
        self.live_session_name = tk.StringVar()
        self.live_source_language = tk.StringVar(value='日本語')
        self.live_target_language = tk.StringVar(value='简体中文')
        self.live_display_mode = tk.StringVar(value='双语显示')
        self.live_font_family = tk.StringVar(value=DEFAULT_FONT)
        self.live_font_size = tk.StringVar(value='14')
        self.live_guidance_selection = {}
        self.live_guidance_summary = tk.StringVar(value='术语指导：未启用')
        self.live_subtitle_color = tk.StringVar(value=PRESETS['默认'])
        self.live_color_preset = tk.StringVar(value='默认')
        self.live_record_session = tk.BooleanVar(value=True)
        self.live_status = tk.StringVar(value='选择本机正在播放声音的设备。')
        self.live_source_summary = tk.StringVar()
        self.live_step = 'source'

        ttk.Label(parent,text='实时翻译',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w',pady=(0,8))

        ttk.Label(parent,textvariable=self.live_status,wraplength=740,foreground='#668f8b').pack(side='bottom',fill='x')
        self.live_stage = ttk.Frame(parent)
        self.live_stage.pack(fill='both',expand=True)
        self.live_source_page = ttk.Frame(self.live_stage)
        self.live_display_page = ttk.Frame(self.live_stage)

        source_actions = ttk.Frame(self.live_source_page)
        source_actions.pack(side='bottom',fill='x',pady=(10,0))
        self.live_continue_button = ttk.Button(source_actions,text='继续 · 语言与显示',style='Primary.TButton',
                                               command=self.advance_live_setup)
        self.live_continue_button.pack(fill='x')
        self.live_source_scroll = ScrollBody(self.live_source_page)
        self.live_source_scroll.pack(fill='both',expand=True)
        source_body = self.live_source_scroll.content
        display_actions = ttk.Frame(self.live_display_page)
        display_actions.pack(side='bottom',fill='x',pady=(10,0))
        ttk.Button(display_actions,text='返回音频设置',command=lambda:self.show_live_step('source')).pack(side='left')
        self.live_start_button = ttk.Button(display_actions,text='开始实时翻译',style='Primary.TButton',
                                            command=self.start_live_session)
        self.live_start_button.pack(side='right',fill='x',expand=True,padx=(12,0))
        self.live_display_scroll = ScrollBody(self.live_display_page)
        self.live_display_scroll.pack(fill='both',expand=True)
        display_body = self.live_display_scroll.content

        ttk.Label(source_body,text='第 1 步 · 音频与会话',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w',pady=(0,10))
        source_group = ttk.LabelFrame(source_body,text='音频来源',padding=12)
        source_group.pack(fill='x',pady=(0,14))
        source_group.columnconfigure(1,weight=1)
        ttk.Label(source_group,text='来源类型').grid(row=0,column=0,sticky='w',padx=(0,12),pady=5)
        self.live_source_combo = ttk.Combobox(source_group,textvariable=self.live_source_kind,
            values=[LIVE_SOURCE_LOCAL,LIVE_SOURCE_STREAM],state='readonly',width=25)
        self.live_source_combo.grid(row=0,column=1,sticky='ew',pady=5)
        self.live_source_combo.bind('<<ComboboxSelected>>',self.update_live_source)
        ttk.Label(source_group,text='本机播放设备').grid(row=1,column=0,sticky='w',padx=(0,12),pady=5)
        device_row = ttk.Frame(source_group)
        device_row.grid(row=1,column=1,sticky='ew',pady=5)
        device_row.columnconfigure(0,weight=1)
        self.live_device_combo = ttk.Combobox(device_row,textvariable=self.live_device,state='readonly')
        self.live_device_combo.grid(row=0,column=0,sticky='ew')
        ttk.Button(device_row,text='刷新',command=self.refresh_live_devices).grid(row=0,column=1,padx=(8,0))
        ttk.Label(source_group,text='直播地址').grid(row=2,column=0,sticky='w',padx=(0,12),pady=5)
        self.live_stream_entry = ttk.Entry(source_group,textvariable=self.live_stream_url,state='disabled')
        self.live_stream_entry.grid(row=2,column=1,sticky='ew',pady=5)
        ttk.Label(source_group,text='会话名称').grid(row=3,column=0,sticky='w',padx=(0,12),pady=5)
        self.live_session_name_entry = ttk.Entry(source_group,textvariable=self.live_session_name)
        self.live_session_name_entry.grid(row=3,column=1,sticky='ew',pady=5)

        ttk.Checkbutton(source_body,text='保存有关结果',
                        variable=self.live_record_session).pack(anchor='w',pady=(2,0))

        ttk.Label(display_body,text='第 2 步 · 语言与显示',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w',pady=(0,5))
        summary = ttk.Label(display_body,textvariable=self.live_source_summary,foreground='#887788',wraplength=700)
        summary.pack(fill='x',pady=(0,12))
        display_body.bind('<Configure>',lambda event:summary.configure(wraplength=event.width-8) if event.width>100 else None,add='+')
        options = ttk.Frame(display_body)
        options.pack(fill='x',pady=(0,8))
        options.columnconfigure(0,weight=1)
        options.columnconfigure(1,weight=1)
        language_group = ttk.LabelFrame(options,text='语言与显示',padding=12)
        language_group.grid(row=0,column=0,sticky='nsew',padx=(0,7))
        style_group = ttk.LabelFrame(options,text='字幕外观',padding=12)
        style_group.grid(row=0,column=1,sticky='nsew',padx=(7,0))
        self.live_options = options
        self.live_option_groups = (language_group,style_group)
        def arrange_options(event):
            if event.width < 100:  # Hidden tab's initial 1px geometry is not a real viewport.
                return
            narrow = event.width < language_group.winfo_reqwidth()+style_group.winfo_reqwidth()+14
            language_group.grid_configure(columnspan=2 if narrow else 1,padx=0 if narrow else (0,7))
            style_group.grid_configure(row=1 if narrow else 0,column=0 if narrow else 1,
                columnspan=2 if narrow else 1,padx=0 if narrow else (7,0),pady=(8,0) if narrow else 0)
        options.bind('<Configure>',arrange_options)

        ttk.Label(language_group,text='原语言').grid(row=0,column=0,sticky='w')
        ttk.Label(language_group,text='目标语言').grid(row=0,column=1,sticky='w',padx=(10,0))
        source_values = [label for label,code in SOURCE_LABELS.items() if code != 'auto']
        self.live_source_language_combo = ttk.Combobox(
            language_group,textvariable=self.live_source_language,values=source_values,
            state='readonly',width=18)
        self.live_source_language_combo.grid(row=1,column=0,sticky='ew',pady=(4,12))
        self.live_target_language_combo = ttk.Combobox(
            language_group,textvariable=self.live_target_language,values=list(TARGET_LABELS),
            state='readonly',width=18)
        self.live_target_language_combo.grid(row=1,column=1,sticky='ew',padx=(10,0),pady=(4,12))
        ttk.Label(language_group,text='显示内容').grid(row=2,column=0,columnspan=2,sticky='w')
        self.live_display_mode_combo = ttk.Combobox(
            language_group,textvariable=self.live_display_mode,values=list(LIVE_DISPLAY_MODES),
            state='readonly')
        self.live_display_mode_combo.grid(row=3,column=0,columnspan=2,sticky='ew',pady=(4,0))
        self.live_display_mode_combo.bind('<<ComboboxSelected>>',self.update_live_display_mode)
        language_group.columnconfigure(0,weight=1)
        language_group.columnconfigure(1,weight=1)
        self.live_guidance_button = ttk.Button(language_group,text='选择术语包…',command=self.open_live_guidance)
        self.live_guidance_button.grid(row=4,column=0,columnspan=2,sticky='ew',pady=(12,0))
        ttk.Label(language_group,textvariable=self.live_guidance_summary,wraplength=270).grid(row=5,column=0,columnspan=2,sticky='w',pady=(4,0))

        ttk.Label(style_group,text='字体').pack(anchor='w')
        live_fonts = list(dict.fromkeys(FONTS.values()))
        ttk.Combobox(style_group,textvariable=self.live_font_family,values=live_fonts,
                     state='readonly').pack(fill='x',pady=(4,12))
        size_row = ttk.Frame(style_group)
        size_row.pack(fill='x',pady=(0,12))
        ttk.Label(size_row,text='字号（pt）').pack(side='left')
        ttk.Combobox(size_row,textvariable=self.live_font_size,width=6,state='readonly',
            values=[10,12,14,16,18,20,24,28,32,40,48]).pack(side='right')
        ttk.Label(style_group,text='描边颜色').pack(anchor='w')
        ttk.Combobox(style_group,textvariable=self.live_color_preset,
                     values=[*PRESETS,'自定义'],state='readonly').pack(fill='x',pady=(4,8))
        self.live_color_preset.trace_add('write',lambda *_: self.live_subtitle_color.set(PRESETS[self.live_color_preset.get()])
            if self.live_color_preset.get() in PRESETS else None)
        color_row = ttk.Frame(style_group)
        color_row.pack(fill='x',pady=(4,0))
        self.live_color_entry = ttk.Entry(color_row,textvariable=self.live_subtitle_color)
        self.live_color_entry.pack(side='left',fill='x',expand=True)
        self.live_color_button = ttk.Button(color_row,text='选择',command=self.choose_live_color)
        self.live_color_button.pack(side='left',padx=(8,0))

        ttk.Label(display_body,text='字幕预览').pack(anchor='w',pady=(0,4))
        self.live_preview = tk.Frame(display_body,background='#101518',padx=12,pady=10)
        self.live_preview.pack(fill='x')
        self.live_preview_canvas = tk.Canvas(self.live_preview,background='#101518',height=76,
                                             borderwidth=0,highlightthickness=0)
        self.live_preview_canvas.pack(fill='x')
        self.live_preview_canvas.bind('<Configure>',self.update_live_preview)
        self.live_preview_sizes = tk.StringVar()
        ttk.Label(display_body,textvariable=self.live_preview_sizes,foreground='#887788').pack(anchor='w',pady=(4,0))
        for variable in (self.live_font_family,self.live_font_size,self.live_subtitle_color,
                         self.live_source_language,self.live_target_language,self.live_display_mode):
            variable.trace_add('write',self.update_live_preview)
        self.update_live_preview()
        self.live_text_inputs = (self.live_session_name_entry,self.live_color_entry)
        self.show_live_step('source')
        self.update_live_display_mode()

    def update_live_preview(self,*_args):
        self.update_live_guidance()
        samples = {'ja':'テスト','zh':'测试','zh-Hans':'测试','en':'Test'}
        mode = LIVE_DISPLAY_MODES[self.live_display_mode.get()]
        size = int(self.live_font_size.get())
        source_size = size if mode == 'source' else max(10,size-7)
        try:
            color = normalize_color(self.live_subtitle_color.get())
        except ValueError:
            color = PRESETS['默认']  # An unfinished hex value must not interrupt typing.
        selected = next((name for name,value in PRESETS.items() if value==color),'自定义')
        if self.live_color_preset.get()!=selected:
            self.live_color_preset.set(selected)
        family = tk_family(self.live_font_family.get())
        canvas = self.live_preview_canvas
        canvas.delete('all')
        x = max(50,canvas.winfo_width()/2)
        def draw_caption(text,y,face):
            for dx,dy in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
                canvas.create_text(x+dx,y+dy,text=text,fill=color,font=face)
            canvas.create_text(x,y,text=text,fill='#FFFFFF',font=face)
        if mode != 'translation':
            draw_caption(samples[SOURCE_LABELS[self.live_source_language.get()]],
                         22 if mode=='bilingual' else 38,(family,source_size))
        if mode != 'source':
            draw_caption(samples[TARGET_LABELS[self.live_target_language.get()]],
                         55 if mode=='bilingual' else 38,(family,size,'bold'))
        sizes = []
        if mode != 'translation':
            sizes.append(f'原文 {source_size} pt')
        if mode != 'source':
            sizes.append(f'译文 {size} pt')
        self.live_preview_sizes.set(' · '.join(sizes))

    def open_guidance_folder(self):
        folder = ROOT/'translation_guidance'
        folder.mkdir(parents=True,exist_ok=True)
        os.startfile(str(folder))

    def active_live_guidance(self):
        if LIVE_DISPLAY_MODES[self.live_display_mode.get()] == 'source':
            return []
        source,target = SOURCE_LABELS[self.live_source_language.get()],TARGET_LABELS[self.live_target_language.get()]
        return [pack_id for pack_id,pack in self.live_guidance_selection.items() if pack.compatible(source,target)]

    def update_live_guidance(self):
        source_only = LIVE_DISPLAY_MODES[self.live_display_mode.get()] == 'source'
        self.live_guidance_button.configure(state='disabled' if source_only else 'normal')
        active = self.active_live_guidance()
        names = [self.live_guidance_selection[key].manifest['name'] for key in active]
        if source_only:
            text = '仅识别原文：术语指导不使用'
        elif names:
            text = '本会话：'+ '、'.join(names)
        elif self.live_guidance_selection:
            text = '语言方向不匹配：已选包不使用'
        else:
            text = '术语指导：未启用'
        self.live_guidance_summary.set(text)

    def open_live_guidance(self):
        dialog = tk.Toplevel(self.window)
        dialog.title('本会话 · 术语指导')
        dialog.geometry('650x430')
        dialog.minsize(500,320)
        dialog.transient(self.window)
        dialog.grab_set()
        frame = ttk.Frame(dialog,padding=16)
        frame.pack(fill='both',expand=True)
        actions = ttk.Frame(frame)
        actions.pack(side='bottom',fill='x',pady=(10,0))
        ttk.Label(frame,text='按会话选择；每句只发送命中的术语。\n草案勾选即表示本次试用；候选爱称文件不加载。',wraplength=590).pack(fill='x',pady=(0,10))
        scroller = ScrollBody(frame)
        scroller.pack(fill='both',expand=True)
        self.live_guidance_dialog = dialog
        choices, available = {}, {}
        source,target = SOURCE_LABELS[self.live_source_language.get()],TARGET_LABELS[self.live_target_language.get()]
        def refresh():
            selected = {key for key,var in choices.items() if var.get()} if choices else set(self.live_guidance_selection)
            choices.clear()
            available.clear()
            for child in scroller.content.winfo_children():
                child.destroy()
            packs, errors = discover_packs(ROOT)
            for pack in packs:
                compatible = pack.compatible(source,target)
                variable = tk.BooleanVar(value=compatible and pack.id in selected)
                choices[pack.id],available[pack.id] = variable,pack
                label = f"{pack.manifest['name']} · {pack.manifest['version']}"
                label += '（草案试用）' if pack.draft else ''
                if not compatible:
                    label += '（语言方向不匹配）'
                ttk.Checkbutton(scroller.content,text=label,variable=variable,
                    state='normal' if compatible else 'disabled').pack(anchor='w',pady=6)
            for error in errors:
                ttk.Label(scroller.content,text=error,wraplength=570,foreground='#a04040').pack(fill='x')
            if not packs and not errors:
                ttk.Label(scroller.content,text='未发现术语包。将包文件夹放入 translation_guidance/packs 后刷新。',wraplength=570).pack(fill='x')
            self.live_guidance_choices = choices
        def apply():
            chosen = {key:available[key] for key,var in choices.items() if var.get()}
            try:
                load_guidance(ROOT,tuple(chosen),source,target,allow_draft=True)
            except (OSError,ValueError,TypeError) as error:
                messagebox.showerror('术语包无法使用',str(error),parent=dialog)
                return
            self.live_guidance_selection = chosen
            self.update_live_guidance()
            dialog.destroy()
        ttk.Button(actions,text='打开文件夹',command=self.open_guidance_folder).pack(side='left')
        ttk.Button(actions,text='刷新',command=refresh).pack(side='left',padx=8)
        ttk.Button(actions,text='应用到本会话',command=apply).pack(side='right')
        ttk.Button(actions,text='取消',command=dialog.destroy).pack(side='right',padx=8)
        self.apply_live_guidance_selection = apply
        refresh()

    def show_live_step(self, step):
        if step not in {'source','display'}:
            return
        if step != self.live_step:
            self.release_live_input_focus()
        self.live_source_page.pack_forget()
        self.live_display_page.pack_forget()
        self.live_step = step
        if step == 'source':
            self.live_source_page.pack(fill='both',expand=True)
        else:
            recording = '保存结果' if self.live_record_session.get() else '不保存结果'
            self.live_source_summary.set(f"{self.live_source_kind.get()} · {self.live_device.get()} · {recording}")
            self.live_display_page.pack(fill='both',expand=True)
        self.update_live_hint()

    def release_live_input_focus(self, _event=None):
        focused = self.window.focus_get()
        if focused is not None and focused in getattr(self,'live_text_inputs',()):
            self.mode_notebook.focus_set()
            self.window.update_idletasks()

    def advance_live_setup(self):
        if self.live_source_kind.get() != LIVE_SOURCE_LOCAL:
            self.live_status.set('直播音频接口尚未开放。')
            return
        self.show_live_step('display')

    def mode_changed(self, _event=None):
        if self.mode_notebook.index(self.mode_notebook.select()) == 1 and not self.live_devices_loaded:
            self.refresh_live_devices()

    def refresh_live_devices(self):
        self.live_status.set('正在读取本机播放设备…')
        try:
            devices = list_loopback_devices()
            mapping = {'跟随系统默认输出设备':None}
            for device in devices:
                label = device['name']
                if label in mapping:
                    label = f"{label} · {device['id']}"
                mapping[label] = device['id']
            self.live_device_ids = mapping
            self.live_device_combo.configure(values=list(mapping))
            if self.live_device.get() not in mapping:
                self.live_device.set(next(iter(mapping)))
            self.live_devices_loaded = True
            self.live_status.set(f'已找到 {len(devices)} 个系统声音设备。')
        except Exception as error:
            self.live_devices_loaded = False
            self.live_status.set(f'无法读取系统声音设备：{error}')

    def update_live_source(self, _event=None):
        local = self.live_source_kind.get() == LIVE_SOURCE_LOCAL
        self.live_device_combo.configure(state='readonly' if local else 'disabled')
        self.live_stream_entry.configure(state='disabled')
        self.live_continue_button.configure(state='normal' if local else 'disabled')
        self.live_start_button.configure(state='normal' if local else 'disabled')
        self.update_live_hint()

    def update_live_display_mode(self, _event=None):
        source_only = LIVE_DISPLAY_MODES.get(self.live_display_mode.get()) == 'source'
        self.live_target_language_combo.configure(state='disabled' if source_only else 'readonly')
        self.live_start_button.configure(text='开始实时识别' if source_only else '开始实时翻译')
        self.update_live_hint()

    def update_live_hint(self):
        if self.live_source_kind.get() != LIVE_SOURCE_LOCAL:
            self.live_status.set('直播音频接口已预留，本版暂不开放直接直播地址采集。')
        else:
            self.live_status.set('')

    def choose_live_color(self):
        try:
            initial = normalize_color(self.live_subtitle_color.get())
        except ValueError:
            initial = PRESETS['默认']
        _rgb, value = colorchooser.askcolor(initialcolor=initial,parent=self.window,title='选择实时字幕描边颜色')
        if value:
            self.live_subtitle_color.set(value.upper())

    def start_live_session(self):
        if self.live_source_kind.get() != LIVE_SOURCE_LOCAL:
            self.live_status.set('直播音频接口尚未开放。')
            return
        self.user_settings = load_settings(ROOT)
        if not self.user_settings.api_key:
            messagebox.showerror('无法开始','尚未配置 DASHSCOPE_API_KEY，请先打开设置完成配置。',parent=self.window)
            return
        try:
            config = {
                'device':self.live_device_ids.get(self.live_device.get()),
                'source_language':SOURCE_LABELS[self.live_source_language.get()],
                'target_language':TARGET_LABELS[self.live_target_language.get()],
                'display_mode':LIVE_DISPLAY_MODES[self.live_display_mode.get()],
                'font_family':self.live_font_family.get(),
                'font_size':int(self.live_font_size.get()),
                'subtitle_color':normalize_color(self.live_subtitle_color.get()),
                'session_name':self.live_session_name.get().strip(),
                'record_session':self.live_record_session.get(),
                'translation_engine':self.user_settings.live_engine,
                'guidance_packs':tuple(self.active_live_guidance()),
                'allow_draft_guidance':any(self.live_guidance_selection[key].draft for key in self.active_live_guidance()),
            }
            if config['guidance_packs'] and config['translation_engine'] == 'asr-mt':
                if not self.user_settings.translation_model.startswith('qwen-mt-'):
                    raise ValueError('术语指导目前仅支持 Qwen-MT 翻译模型。')
                load_guidance(ROOT,config['guidance_packs'],config['source_language'],config['target_language'],
                              allow_draft=config['allow_draft_guidance'])
            LiveSettings(audio_device=config['device'],source_language=config['source_language'],
                translation_engine=config['translation_engine'],
                target_language=config['target_language'],display_mode=config['display_mode'],
                subtitle_font_family=config['font_family'],subtitle_color=config['subtitle_color'],
                subtitle_font_size=config['font_size'],
                guidance_packs=config['guidance_packs'],allow_draft_guidance=config['allow_draft_guidance'],
                record_session=config['record_session'],subtitle_lines=8)
            python = ROOT/'.venv/Scripts'/('pythonw.exe' if os.name == 'nt' else 'python')
            if not python.is_file():
                raise FileNotFoundError('RinaYaki 的 Python 环境不完整。')
            flags = 0
            if os.name == 'nt':
                flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(build_live_command(python,config),cwd=ROOT,
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=flags)
            label = config['session_name'] or time.strftime('%H:%M:%S')
            detail = '仅识别原文，不调用翻译 API' if config['display_mode']=='source' else '识别并翻译'
            stream_note = '原文与译文会逐段流式更新；' if config['display_mode'] != 'source' else ''
            self.live_status.set(f'已启动独立会话“{label}” · {detail}；{stream_note}可以继续启动其他会话。')
        except (OSError,ValueError,KeyError,TypeError) as error:
            messagebox.showerror('无法开始实时翻译',str(error),parent=self.window)

    def build_work_pages(self, outer):
        self.project_page = ttk.Frame(outer)
        ttk.Label(self.project_page,text='项目设置',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w',pady=(0,20))
        self.pending_choice = tk.StringVar()
        self.pending_combo = ttk.Combobox(self.project_page,textvariable=self.pending_choice,state='readonly')
        ttk.Label(self.project_page,text='未完成的同源任务').pack(anchor='w')
        self.pending_combo.pack(fill='x',pady=(5,20))
        self.pending_combo.bind('<<ComboboxSelected>>',lambda _:self.select_pending_job())
        self.project_parent = tk.StringVar()
        self.project_name = tk.StringVar()
        self.destination_display = tk.StringVar()
        ttk.Label(self.project_page,text='保存位置').pack(anchor='w')
        row = ttk.Frame(self.project_page)
        row.pack(fill='x',pady=(5,18))
        ttk.Entry(row,textvariable=self.project_parent).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='📁',width=4,command=self.choose_destination).pack(side='left',padx=(8,0))
        ttk.Label(self.project_page,text='项目名称').pack(anchor='w')
        ttk.Entry(self.project_page,textvariable=self.project_name).pack(fill='x',pady=(5,18))
        self.source_language = tk.StringVar(value='自动识别')
        self.target_language = tk.StringVar(value='简体中文')
        self.speaker_count = tk.StringVar(value='自动')
        languages = ttk.Frame(self.project_page)
        languages.pack(fill='x',pady=(0,8))
        ttk.Label(languages,text='原视频语言').grid(row=0,column=0,sticky='w')
        ttk.Label(languages,text='字幕目标语言').grid(row=0,column=1,sticky='w',padx=(20,0))
        ttk.Label(languages,text='说话人数').grid(row=0,column=2,sticky='w',padx=(20,0))
        self.source_language_combo = ttk.Combobox(languages,textvariable=self.source_language,values=list(SOURCE_LABELS),state='readonly',width=22)
        self.target_language_combo = ttk.Combobox(languages,textvariable=self.target_language,values=list(TARGET_LABELS),state='readonly',width=22)
        self.speaker_count_combo = ttk.Combobox(languages,textvariable=self.speaker_count,values=['自动']+[str(i) for i in range(1,21)],state='readonly',width=12)
        self.source_language_combo.grid(row=1,column=0,pady=5,sticky='w')
        self.target_language_combo.grid(row=1,column=1,pady=5,padx=(20,0),sticky='w')
        self.speaker_count_combo.grid(row=1,column=2,pady=5,padx=(20,0),sticky='w')
        ttk.Label(self.project_page,textvariable=self.destination_display,wraplength=730).pack(anchor='w',pady=12)
        self.project_parent.trace_add('write',self.update_destination_display)
        self.project_name.trace_add('write',self.update_destination_display)
        row = ttk.Frame(self.project_page)
        row.pack(fill='x',pady=20)
        ttk.Button(row,text='返回预览',command=lambda:self.show_page('input')).pack(side='left')
        self.project_continue = ttk.Button(row,text='开始翻译',style='Primary.TButton',command=self.confirm_project)
        self.project_continue.pack(side='right')
        self.progress_page = ttk.Frame(outer)
        ttk.Label(self.progress_page,text='处理进度',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w',pady=(0,8))
        self.progress_title = ttk.Label(self.progress_page,wraplength=700)
        self.progress_title.pack(anchor='w',pady=(0,10))
        self.progress_rows = {}
        for key, label in [('download','读取视频'),('audio','提取音频'),('asr','语音识别'),('translation','翻译'),('refinement','精修'),('export_and_mux','导出成片')]:
            text = ttk.Label(self.progress_page,text=label+' · 等待')
            text.pack(anchor='w')
            bar = ttk.Progressbar(self.progress_page,maximum=100) if key in {'download','translation','refinement'} else None
            if bar:
                bar.pack(fill='x',pady=(3,10))
            self.progress_rows[key] = (label,text,bar)
        self.progress_rows['export_and_mux'][1].pack_forget()
        self.progress_actions = ttk.Frame(self.progress_page)
        self.progress_actions.pack(fill='x',pady=10)
        ttk.Button(self.progress_actions,text='返回首页',command=lambda:self.show_page('input')).pack(side='left')
        self.next_button = ttk.Button(self.progress_actions,text='继续',style='Primary.TButton',state='disabled',command=self.open_styles)
        self.next_button.pack(side='right')
        ttk.Button(self.progress_actions,text='打开项目文件夹',command=self.open_folder).pack(side='right',padx=8)
        self.retry_button = ttk.Button(self.progress_actions,text='重试',state='disabled',command=self.retry_job)
        self.retry_button.pack(side='right',padx=8)
        self.style_page = ttk.Frame(outer)
        ttk.Label(self.style_page,text='字幕样式',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w')
        self.speaker_note = ttk.Label(self.style_page,wraplength=700)
        self.speaker_note.pack(anchor='w',pady=10)
        self.speaker_choice = tk.StringVar()
        self.speaker_combo = ttk.Combobox(self.style_page,textvariable=self.speaker_choice,state='readonly')
        self.speaker_combo.pack(fill='x')
        self.speaker_combo.bind('<<ComboboxSelected>>',lambda _:self.select_speaker())
        self.sample_button = ttk.Button(self.style_page,text='▶ 试听原声片段',command=self.play_sample)
        self.sample_button.pack(anchor='w',pady=10)
        ttk.Label(self.style_page,text='字体').pack(anchor='w')
        self.font_name = tk.StringVar(value=next(iter(FONTS)))
        self.font_combo = ttk.Combobox(self.style_page,textvariable=self.font_name,
                                       values=list(FONTS),state='readonly')
        self.font_combo.current(0)
        self.font_combo.pack(fill='x',pady=(3,12))
        self.font_combo.bind('<<ComboboxSelected>>',lambda _:self.update_font())
        ttk.Label(self.style_page,text='描边颜色').pack(anchor='w')
        row = ttk.Frame(self.style_page)
        row.pack(fill='x',pady=5)
        self.preset = tk.StringVar(value='默认')
        choice = ttk.Combobox(row,textvariable=self.preset,values=list(PRESETS)+['自定义'],state='readonly',width=22)
        choice.pack(side='left')
        choice.bind('<<ComboboxSelected>>',lambda _:self.color.set(PRESETS[self.preset.get()]) if self.preset.get() in PRESETS else None)
        self.color = tk.StringVar(value='#000000')
        ttk.Entry(row,textvariable=self.color,width=13).pack(side='left',padx=10)
        self.swatch = tk.Label(row,width=5,background='#000000',relief='solid',borderwidth=1)
        self.swatch.pack(side='left')
        self.swatch.bind('<Enter>',self.show_color_tooltip)
        self.swatch.bind('<Leave>',lambda _:self.hide_tooltip())
        choice.bind('<Enter>',self.show_color_tooltip)
        choice.bind('<Leave>',lambda _:self.hide_tooltip())
        self.color_hint = ttk.Label(self.style_page,text='')
        self.color_hint.pack(anchor='w')
        self.style_preview_text = '白字与描边颜色预览'
        self.style_preview_photo = None
        self.sample_text = tk.Label(self.style_page,background='#24242A',borderwidth=0)
        self.sample_text.pack(fill='x',pady=14)
        row = ttk.Frame(self.style_page)
        row.pack(fill='x',pady=8)
        ttk.Button(row,text='返回进度',command=lambda:self.show_page('progress')).pack(side='left')
        self.location_button = ttk.Button(row,text='修改保存位置',command=self.edit_project_settings)
        self.location_button.pack(side='left',padx=8)
        self.export_button = ttk.Button(row,text='继续 · 导出成片',style='Primary.TButton',command=self.export_styles)
        self.export_button.pack(side='right')
        self.color.trace_add('write',self.update_color)
        self.complete_page = ttk.Frame(outer)
        ttk.Label(self.complete_page,text='翻译完成',font=('Microsoft YaHei UI',18,'bold')).pack(anchor='w',pady=(0,14))
        self.complete_name = ttk.Label(self.complete_page,wraplength=700)
        self.complete_name.pack(anchor='w',pady=(0,7))
        self.complete_path = ttk.Label(self.complete_page,wraplength=700)
        self.complete_path.pack(anchor='w',pady=(0,20))
        row = ttk.Frame(self.complete_page)
        row.pack(fill='x')
        ttk.Button(row,text='翻译新视频',command=self.return_home).pack(side='left')
        ttk.Button(row,text='打开项目文件夹',command=self.open_folder).pack(side='left',padx=8)

    def return_home(self):
        self.exit_preview()
        self.status.set('')
        self.show_page('input')

    def show_page(self, name):
        for page in (self.input_page,self.project_page,self.progress_page,self.style_page,self.complete_page):
            page.pack_forget()
        {'input':self.input_page,'project':self.project_page,'progress':self.progress_page,'style':self.style_page,'complete':self.complete_page}[name].pack(fill='both',expand=True)
        self.screen = name
        if name == 'input':
            self.footer.pack_forget()
        elif not self.footer.winfo_manager():
            self.footer.pack(side='bottom', fill='x', pady=(8, 0))
        self.hide_tooltip()

    def show_notice(self, text, duration=3500):
        if self.notice:
            self.notice.destroy()
        self.notice = TransientNotice(self.window, text, duration)

    def hide_tooltip(self):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def show_color_tooltip(self,event):
        self.hide_tooltip()
        try:
            text = normalize_color(self.color.get())
        except ValueError:
            return
        self.tooltip = tk.Toplevel(self.window)
        self.tooltip.overrideredirect(True)
        self.tooltip.geometry(f'+{event.x_root+12}+{event.y_root+12}')
        ttk.Label(self.tooltip,text=text,padding=6).pack()

    def changed(self,*_):
        self.revision += 1
        self.selected = None
        self.start.configure(state='disabled')
        self.preview_button.configure(text='预览',state='normal')
        self.cover.configure(image='',text='▶')
        self.photo = None
        self.title.configure(text='')
        self.duration.configure(text='')
        self.quality_picker.pack_forget()
        self.status.set('')
        self.login_button.configure(
            state='normal' if can_open_session(self.value.get()) else 'disabled')

    def preview_action(self):
        if self.selected is not None:
            self.exit_preview()
        else:
            self.resolve()

    def exit_preview(self):
        # Only leave the preview; detached pipeline processes keep running.
        self.job = None
        self.worker = None
        self.managed_job = None
        self.value.set('')
        self.entry.focus_set()

    def choose(self):
        path = filedialog.askopenfilename(title='选择视频',filetypes=[('视频','*.mp4 *.mkv *.mov *.webm *.avi *.flv *.m4v'),('所有文件','*.*')])
        if path:
            self.value.set(path)
            self.resolve()

    def resolve(self):
        self.revision += 1
        value, revision = self.value.get(), self.revision
        self.selected = None
        self.quality_picker.pack_forget()
        self.start.configure(state='disabled')
        self.preview_button.configure(state='disabled')
        def work():
            cookie_file = None
            try:
                try:
                    target = session_target(value)
                    active = self.web_sessions.get(target.site)
                except ValueError:
                    active = None
                if active and active.process.poll() is None:
                    cookie_file = active.snapshot_cookies(value)
                info = preview(value, ROOT, cookie_file=cookie_file,
                               use_app_session=True)
                cover = None
                if info['kind'] == 'local':
                    raw = local_thumbnail(info['source'],info['duration'],ROOT)
                    if raw:
                        cover = Image.open(io.BytesIO(raw))
                        cover.thumbnail((310,175))
                        cover.load()
                if info.get('thumbnail'):
                    try:
                        with urlopen(info['thumbnail'],timeout=15) as response:
                            raw = response.read(8*1024*1024+1)
                        if len(raw) <= 8*1024*1024:
                            cover = Image.open(io.BytesIO(raw))
                            cover.thumbnail((310,175))
                            cover.load()
                    except Exception:
                        cover = None
                self.events.put(('preview',revision,info,cover))
            except Exception as error:
                self.events.put(('error',revision,str(error),None))
            finally:
                if cookie_file:
                    try:
                        cookie_file.unlink(missing_ok=True)
                    except OSError:
                        pass
        threading.Thread(target=work,daemon=True).start()

    def source_record(self):
        info = self.selected
        source = {key:info[key] for key in ('kind','source','title')}
        if info['kind'] == 'web':
            source['acquisition'] = {**info['acquisition'], 'quality': self.quality_ids[self.quality.get()]}
        if info['kind'] == 'local':
            stat = Path(info['source']).stat()
            source.update(size=stat.st_size,mtime_ns=stat.st_mtime_ns)
        return source

    def show_quality_requirement(self, item):
        dialog = tk.Toplevel(self.window)
        dialog.title('画质权限')
        dialog.transient(self.window)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='没有权限', font=('Microsoft YaHei UI', 13, 'bold'),
                  justify='center', anchor='center').pack(fill='x', pady=(2, 8))
        ttk.Label(frame, text=item.get('message') or '当前没有此画质的访问权限。',
                  justify='center', anchor='center', wraplength=360).pack(fill='both', expand=True)
        action = item.get('action') or {}
        if action.get('kind') == 'open_source':
            ttk.Button(frame, text=action.get('label') or '打开网页',
                       command=lambda:self.open_quality_page(dialog)).pack(side='bottom', anchor='e')
        dialog.update_idletasks()
        width, height = max(420, dialog.winfo_reqwidth()), max(170, dialog.winfo_reqheight())
        x = self.window.winfo_rootx() + max(0, (self.window.winfo_width() - width) // 2)
        y = self.window.winfo_rooty() + max(0, (self.window.winfo_height() - height) // 2)
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        dialog.grab_set()

    def open_quality_page(self, dialog):
        source = self.selected.get('source') if self.selected else None
        self.open_login_window(source=source, dialog=dialog)

    def open_login_window(self, source=None, dialog=None):
        source = source or self.value.get()
        try:
            target = session_target(source)
            current = self.web_sessions.get(target.site)
            if current and current.process.poll() is None:
                self.show_notice('登录窗口已打开。')
                if dialog:
                    dialog.destroy()
                return
            launched = launch_session(source)
            self.web_sessions[launched.site] = launched
        except (RuntimeError, ValueError) as error:
            self.show_notice(str(error))
            return
        if dialog:
            dialog.destroy()
        self.show_notice('登录窗口已打开。')

    def close_web_sessions(self):
        sessions, self.web_sessions = list(self.web_sessions.values()), {}
        for session in sessions:
            session.close()

    def close_window(self):
        self.close_web_sessions()
        self.window.destroy()

    def choose_destination(self):
        path = filedialog.askdirectory(title='选择保存项目的文件夹')
        if path:
            self.project_parent.set(path)

    def update_destination_display(self,*_):
        parent,name = self.project_parent.get().strip(),self.project_name.get().strip()
        self.destination_display.set(str(Path(parent)/name) if parent and name else '')

    def set_project_languages(self, record=None):
        source, target = stored_languages(record) if record is not None else ('auto','zh-Hans')
        count = stored_speaker_count(record) if record is not None else None
        self.source_language.set(next(k for k,v in SOURCE_LABELS.items() if v==source))
        self.target_language.set(next(k for k,v in TARGET_LABELS.items() if v==target))
        self.speaker_count.set(str(count) if count is not None else '自动')
        for widget in (self.source_language_combo,self.target_language_combo,self.speaker_count_combo):
            widget.configure(state='disabled' if record is not None else 'readonly')

    def open_project_settings(self):
        if not self.selected:
            return
        self.user_settings = load_settings(ROOT)
        self.editing_job = None
        self.settings_return = None
        self.project_parent.set(self.user_settings.default_project_dir)
        self.project_name.set('')
        self.project_continue.configure(text='开始翻译')
        self.pending_combo.configure(state='readonly')
        self.pending_jobs = []
        try:
            for value in json.loads(PROJECT_INDEX.read_text(encoding='utf-8')):
                job = Path(value)
                if not is_direct_project(job):
                    continue
                data = json.loads(control_path(job,RUNS).read_text(encoding='utf-8'))
                source = data.get('source',{})
                if data.get('status')!='complete' and source.get('source')==self.selected['source'] and source.get('kind')==self.selected['kind']:
                    self.pending_jobs.append((job,{**data,'destination':str(job)}))
        except (OSError,ValueError):
            pass
        for path in (RUNS/'.control').glob('job-*.json'):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                source = data.get('source',{})
                job = checked_cache_job(RUNS/path.stem,RUNS)
                if data.get('status') != 'complete' and source.get('source')==self.selected['source'] and source.get('kind')==self.selected['kind']:
                    self.pending_jobs.append((job,data))
            except (OSError,ValueError):
                pass
        self.pending_combo.configure(values=['新建项目']+[f"{i+1}. {data.get('project_name',job.name)} · {Path(data.get('destination','')).parent}" for i,(job,data) in enumerate(self.pending_jobs)])
        self.pending_combo.current(0)
        self.set_project_languages()
        self.status.set('')
        self.show_page('project')

    def select_pending_job(self):
        index = self.pending_combo.current()-1
        if index < 0:
            self.set_project_languages()
            self.editing_job = None
            self.project_parent.set(self.user_settings.default_project_dir)
            self.project_name.set('')
            self.project_continue.configure(text='开始翻译')
            return
        self.editing_job,data = self.pending_jobs[index]
        self.set_project_languages(json.loads((self.editing_job/'intermediates/destination.local.json').read_text(encoding='utf-8'))['source'])
        self.project_parent.set(str(Path(data['destination']).parent))
        self.project_name.set(data['project_name'])
        self.project_continue.configure(text='继续任务')

    def edit_project_settings(self):
        if not self.managed_job or self.job != self.managed_job or is_direct_project(self.job):
            return
        self.open_project_settings()
        self.editing_job = self.managed_job
        self.settings_return = 'style'
        self.pending_combo.configure(state='disabled')
        data = json.loads((self.job/'intermediates/destination.local.json').read_text(encoding='utf-8'))
        self.project_parent.set(str(Path(data['destination']).parent))
        self.project_name.set(data['project_name'])
        self.set_project_languages(data['source'])
        self.project_continue.configure(text='保存并返回')

    def confirm_project(self):
        try:
            if self.editing_job:
                self.job = self.editing_job
                # Resume without rewriting the source tree during a transfer.
                control = json.loads(control_path(self.job,RUNS).read_text(encoding='utf-8'))
                entered = str(Path(self.project_parent.get().strip())/self.project_name.get())
                if is_direct_project(self.job):
                    if Path(entered).resolve()!=self.job.resolve():
                        raise ValueError('项目已开始处理，保存位置和名称已固定。')
                elif entered != control.get('destination'):
                    update_destination(self.job,RUNS,self.project_parent.get(),self.project_name.get())
            else:
                count = None if self.speaker_count.get() == '自动' else int(self.speaker_count.get())
                self.job = create_direct_project(self.project_parent.get(),self.project_name.get(),{**self.source_record(), 'source_language':SOURCE_LABELS[self.source_language.get()], 'target_language':TARGET_LABELS[self.target_language.get()], **({'speaker_count':count} if count is not None else {})},RUNS,PROJECT_INDEX)
            self.managed_job = self.job
            if self.settings_return:
                self.show_page(self.settings_return)
                return
            self.launch()
        except (OSError,ValueError,RuntimeError) as error:
            self.status.set(str(error))

    def launch(self):
        self.progress_title.configure(text=self.selected['title'])
        self.show_page('progress')
        self.next_button.configure(state='disabled')
        try:
            with lifecycle_lock(self.managed_job,RUNS):
                pass
        except RuntimeError:
            self.status.set('该视频正在后台处理，已接入进度。')
            return
        state = json.loads(control_path(self.managed_job,RUNS).read_text(encoding='utf-8'))
        if not is_direct_project(self.job) and (state.get('phase') == 'publish' or (RUNS/'.transfers'/(self.managed_job.name+'.json')).exists()):
            self.spawn_worker('publish')
            return
        self.spawn_worker('prepare')

    def edit_lock(self):
        if self.managed_job:
            if self.job != self.managed_job:
                raise ValueError('该项目已迁移完成。')
            return lifecycle_lock(self.managed_job,RUNS)
        return job_lock(self.job)

    def spawn_worker(self, phase):
        selector = ['--project-dir',str(self.managed_job)] if is_direct_project(self.managed_job) else ['--job-id',self.managed_job.name]
        python = ROOT/'.venv/Scripts'/('pythonw.exe' if os.name == 'nt' else 'python')
        command = [str(python),'-u',str(ROOT/'scripts/run_ui_job.py'),
                   *selector,'--cache-root',str(RUNS),'--phase',phase]
        try:
            self.close_web_sessions()
            self.worker_started = time.time()
            self.worker = subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.status.set('已开始，可关闭此窗口；任务继续在后台运行。')
            self.start.configure(state='disabled')
            self.next_button.configure(state='disabled')
            self.show_page('progress')
        except OSError as error:
            self.status.set(str(error))

    def retry_job(self):
        if not self.managed_job:
            return
        try:
            state = json.loads(control_path(self.managed_job,RUNS).read_text(encoding='utf-8'))
            self.spawn_worker(state.get('phase','prepare'))
        except (OSError,ValueError) as error:
            self.status.set(str(error))

    def open_styles(self):
        if not self.job:
            return
        try:
            with self.edit_lock():
                pass
            self.prepared = json.loads((self.job/'intermediates/prepared.json').read_text(encoding='utf-8'))
            self.styles = {}
            saved = self.job/'intermediates/styles.json'
            if saved.is_file():
                settings = json.loads(saved.read_text(encoding='utf-8'))
                if settings.get('prepared_key') == self.prepared['key']:
                    self.styles = validate_styles(settings['speakers'])
            self.speaker_ids = list(self.prepared['speakers'])
            labels = [f'说话人 {i+1}' for i in range(len(self.speaker_ids))]
            self.speaker_combo.configure(values=labels)
            self.speaker_combo.current(0)
            count = len(labels)
            self.speaker_note.configure(text=(f'识别出 {count} 个说话人分组。试听片段用于辨认声音。' if count > 1 else '当前结果只有一个说话人分组，不代表视频中实际只有一人。'))
            self.select_speaker()
            self.location_button.configure(state='disabled' if is_direct_project(self.job) else 'normal')
            self.status.set('')
            self.show_page('style')
        except (OSError,ValueError,RuntimeError,KeyError) as error:
            self.status.set(str(error))

    def select_speaker(self):
        self.sample_revision += 1
        self.sample_button.configure(state='normal')
        if os.name == 'nt':
            import winsound
            winsound.PlaySound(None,0)
        self.current_speaker = self.speaker_ids[self.speaker_combo.current()]
        sample = self.prepared['speakers'][self.current_speaker]
        self.style_preview_text = (sample.get('translation') or sample['text'])[:120]
        style = self.styles.get(self.current_speaker,{})
        font = style.get('font',DEFAULT_FONT)
        self.font_name.set(next((label for label,value in FONTS.items() if value == font),next(iter(FONTS))))
        self.color.set(style.get('color','#000000'))
        self.update_style_preview()

    def update_style_preview(self):
        if not self.prepared:
            return
        try:
            image = render_style_preview(
                self.style_preview_text,
                font_name=FONTS[self.font_name.get()],
                fonts_directory=ROOT/'assets/fonts',
                outline_color=self.color.get(),
            )
            photo = ImageTk.PhotoImage(image)
            self.sample_text.configure(image=photo, text='')
            self.style_preview_photo = photo
        except (KeyError, OSError, ValueError) as error:
            self.sample_text.configure(image='', text=str(error), foreground='white')
            self.style_preview_photo = None

    def update_font(self):
        if not self.prepared:
            return
        font = FONTS[self.font_name.get()]
        previous = self.styles.get(self.current_speaker,{})
        self.styles[self.current_speaker] = {
            'color': previous.get('color','#000000'), 'font': font}
        try:
            with self.edit_lock():
                write_json(self.job/'intermediates/styles.json',
                           {'prepared_key':self.prepared['key'],'speakers':self.styles})
        except (OSError,ValueError,RuntimeError) as error:
            self.status.set(str(error))
        self.update_style_preview()

    def update_color(self,*_):
        try:
            color = normalize_color(self.color.get())
            self.swatch.configure(background=color)
            self.preset.set(next((name for name,value in PRESETS.items() if value==color),'自定义'))
            if self.prepared:
                previous = self.styles.get(self.current_speaker,{})
                self.styles[self.current_speaker] = {
                    'color':color,'font':previous.get('font',FONTS[self.font_name.get()])}
                with self.edit_lock():
                    write_json(self.job/'intermediates/styles.json',{'prepared_key':self.prepared['key'],'speakers':self.styles})
            self.color_hint.configure(text='')
            self.export_button.configure(state='normal')
            self.update_style_preview()
        except (ValueError,OSError,RuntimeError) as error:
            self.color_hint.configure(text=str(error))
            self.export_button.configure(state='disabled')

    def export_styles(self):
        try:
            self.sample_revision += 1
            if os.name == 'nt':
                import winsound
                winsound.PlaySound(None,0)
            normalize_color(self.color.get())
            with self.edit_lock():
                write_json(self.job/'intermediates/styles.json',{'prepared_key':self.prepared['key'],'speakers':validate_styles(self.styles)})
            self.spawn_worker('export')
        except (OSError,ValueError,RuntimeError) as error:
            self.status.set(str(error))

    def play_sample(self):
        sample = self.prepared['speakers'][self.current_speaker]
        job = self.job
        source = (job/self.prepared['audio']).resolve()
        if not source.is_relative_to(job.resolve()):
            self.status.set('试听文件路径无效。')
            return
        token = self.sample_revision
        self.sample_button.configure(state='disabled')
        def work():
            try:
                destination = job/'intermediates/preview'/('speaker-'+hashlib.sha256(str(sample).encode()).hexdigest()[:12]+'.wav')
                guard = lifecycle_lock(job,RUNS) if self.managed_job else job_lock(job)
                with guard:
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    subprocess.run([str(ROOT/'.tools/ffmpeg/ffmpeg.exe'),'-v','error','-y','-ss',str(sample['start_ms']/1000),'-i',str(source),'-t',str(sample['length_ms']/1000),'-ac','1','-ar','22050','-c:a','pcm_s16le',str(destination)],capture_output=True,check=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
                self.events.put(('sample',token,str(destination),None))
            except Exception:
                self.events.put(('sample_error',token,'无法读取试听片段。',None))
        threading.Thread(target=work,daemon=True).start()

    def open_folder(self):
        if self.job and self.job.is_dir():
            os.startfile(self.job)
        else:
            self.status.set('请先创建或选择项目。')

    def poll(self):
        try:
            while True:
                kind, revision, data, cover = self.events.get_nowait()
                if kind in {'sample','sample_error'}:
                    if revision == self.sample_revision and self.screen == 'style':
                        self.sample_button.configure(state='normal')
                        if kind == 'sample':
                            import winsound
                            try:
                                winsound.PlaySound(data,winsound.SND_FILENAME | winsound.SND_ASYNC)
                            except RuntimeError:
                                self.status.set('无法播放试听片段，请检查音频设备。')
                        else:
                            self.status.set(data)
                    continue
                if revision != self.revision:
                    continue
                self.preview_button.configure(state='normal')
                if kind == 'error':
                    if self.screen == 'input':
                        self.show_notice(data)
                    else:
                        self.status.set(data)
                    continue
                self.selected = data
                qualities = data.get('qualities', [])
                self.quality_ids = {item['label']: item['id'] for item in qualities if item.get('available', True)}
                if self.quality_ids:
                    self.quality_picker.set_items(qualities)
                    self.quality_picker.pack(anchor='w', pady=(0, 8))
                self.preview_button.configure(text='退出预览')
                self.title.configure(text=data['title'])
                seconds = int(data['duration'])
                self.duration.configure(text=f"{seconds//60:02d}:{seconds%60:02d} · {'本地视频' if data['kind']=='local' else '在线视频'}")
                self.photo = ImageTk.PhotoImage(cover) if cover else None
                self.cover.configure(image=self.photo or '',text='' if cover else '▶')
                self.start.configure(state='normal')
                self.status.set('')
        except queue.Empty:
            pass
        if self.job and self.screen not in {'style','project','complete'}:
            try:
                try:
                    progress = json.loads((self.job/'intermediates/progress.json').read_text(encoding='utf-8'))
                except (OSError,ValueError):
                    progress = {'status':'running','stage':'starting'}
                control = json.loads(control_path(self.managed_job,RUNS).read_text(encoding='utf-8')) if self.managed_job else {}
                if self.worker and self.worker.poll() is None and control.get('updated_at',0) < self.worker_started:
                    progress = {'status':'running','stage':'starting'}
                elif control.get('status') == 'running':
                    progress['status'] = 'running'
                elif control.get('status') in {'awaiting_style','failed','publishing','complete'}:
                    progress = {**progress,**control}
                self.retry_button.configure(state='normal' if progress['status']=='failed' else 'disabled')
                names = {'download':'读取视频','audio':'提取音频','asr':'识别语音','translation':'翻译字幕','refinement':'校对字幕','export_and_mux':'生成成片'}
                self.update_progress_bars(progress)
                if progress['status']=='running':
                    self.status.set(names.get(progress.get('stage'),'正在处理')+'…')
                    self.next_button.configure(state='disabled')
                elif progress['status']=='awaiting_style':
                    self.status.set('处理完成，点击继续设置字幕样式。')
                    self.next_button.configure(state='normal')
                elif progress['status']=='complete':
                    if progress.get('final_dir'):
                        self.job = Path(progress['final_dir'])
                    self.complete_name.configure(text=self.selected['title'] if self.selected else self.job.name)
                    self.complete_path.configure(text=str(self.job))
                    self.status.set('')
                    self.next_button.configure(state='disabled' if self.managed_job else 'normal')
                    self.show_page('complete')
                    self.window.deiconify()
                    self.window.lift()
                    self.window.attributes('-topmost',True)
                    self.window.after(800,lambda:self.window.attributes('-topmost',False))
                elif progress['status']=='publishing':
                    self.status.set({'copying':'正在迁移项目…','verifying':'正在校验项目文件…','cleanup':'正在清理已迁移的缓存…'}.get(progress.get('stage'),'正在准备迁移…'))
                    self.next_button.configure(state='disabled')
                else:
                    self.status.set('任务暂停：'+progress.get('error','请查看运行记录'))
                    self.next_button.configure(state='disabled')
            except (OSError,ValueError):
                pass
            if self.worker and self.worker.poll() is not None:
                if self.worker.returncode:
                    self.status.set('任务已停止，请查看运行文件夹中的记录；再次开始将复用已完成结果。')
                if self.selected:
                    self.start.configure(state='normal')
                self.worker = None
        self.window.after(500,self.poll)

    def update_progress_bars(self, progress):
        keys = list(self.progress_rows)
        stage = progress.get('stage')
        status = progress.get('status')
        index = keys.index(stage) if stage in keys else -1
        if status == 'awaiting_style':
            index = 5
        if status in {'complete','publishing'}:
            index = 6
        export_label = self.progress_rows['export_and_mux'][1]
        if status in {'complete','publishing'} or ((status in {'running','failed'}) and (progress.get('phase') == 'export' or stage == 'export_and_mux')):
            if not export_label.winfo_manager():
                export_label.pack(anchor='w',pady=(3,10),before=self.progress_actions)
        elif export_label.winfo_manager():
            export_label.pack_forget()
        for i,(key,(label,text,bar)) in enumerate(self.progress_rows.items()):
            if bar:
                bar.stop()
                bar.configure(mode='determinate')
            if i < index:
                if bar: bar['value'] = 100
                text.configure(text=label+' · 完成')
            elif i == index and status == 'running':
                total = progress.get('total')
                if bar and total:
                    completed = progress.get('completed',0)
                    bar['value'] = min(100,100*completed/total)
                    text.configure(text=(f'{label} · {100*completed/total:.0f}%' if key == 'download'
                                         else f'{label} · {completed}/{total} 条 · {100*completed/total:.0f}%'))
                else:
                    if bar:
                        bar.configure(mode='indeterminate')
                        bar.start(20)
                    elapsed = max(0,int(time.time()-progress.get('stage_started_at',time.time())))
                    state = {'PENDING':'排队中','RUNNING':'处理中','SUCCEEDED':'读取结果'}.get(progress.get('provider_status'),'处理中')
                    text.configure(text=f'{label} · {state} · {elapsed//60:02d}:{elapsed%60:02d}')
            else:
                if bar: bar['value'] = 0
                text.configure(text=label+(' · 等待样式确认' if key=='export_and_mux' and status=='awaiting_style' else ' · 等待'))


if __name__ == '__main__':
    if os.name == 'nt':
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        register_private_fonts(ROOT/'assets/fonts')
    window = tk.Tk()
    App(window)
    window.mainloop()
