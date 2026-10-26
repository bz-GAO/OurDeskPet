"""Standalone rolling result window (tkinter, no extra dependencies).

The window consumes events through a queue and redraws on a timer, so sink
calls from chain threads stay cheap and never block. Closing the window asks
the coordinator to stop through ``on_close``.
"""
from __future__ import annotations

import queue
import tkinter as tk

from .. import events as ev
from ...styling import tk_family


BG = "#101418"
STATUS_FG = "#5C6670"
ERROR_FG = "#E8B84B"


class SubtitleWindow:
    def __init__(
        self,
        *,
        lines: int = 4,
        font_size: int = 14,
        font_family: str = "Noto Sans CJK SC Medium",
        subtitle_color: str = "#000000",
        display_mode: str = "bilingual",
        session_name: str | None = None,
        record_session: bool = True,
        on_close=None,
        on_pause=None,
    ) -> None:
        self._queue: "queue.Queue[ev.LiveEvent]" = queue.Queue()
        self._on_close = on_close
        self._on_pause = on_pause
        self._paused = False
        self._ended = False
        self._history: list[dict] = []  # [{segment_id, source, translation}]
        self._history_limit = max(1000, lines * 10)
        self._rendered = None
        self._rendered_rows = []
        self._row_items: list[list[int]] = []
        self._row_heights: list[int] = []
        self._rendered_status = None
        self._partial: str | None = None
        self._status = "启动中…"
        self._error: str | None = None
        self._display_mode = display_mode
        self._translation_available = display_mode != "source"
        self._running_label = "实时翻译中" if self._translation_available else "实时识别中"
        self._font_family = font_family
        self._font_size = font_size
        self._subtitle_color = subtitle_color
        self._record_session = record_session
        self._closing = False

        self._root = tk.Tk()
        self._root.withdraw()  # Map only after geometry and all controls are ready.
        title = "Yaki Live" + (f" · {session_name.strip()}" if session_name and session_name.strip() else "")
        self._root.title(title)
        self._root.configure(bg=BG)
        self._root.geometry("820x560")
        self._root.minsize(560, 320)

        header = tk.Frame(self._root, bg=BG)
        header.pack(fill="x", padx=14, pady=(10, 4))
        self._status_label = tk.Label(
            header, text=self._status, bg=BG, fg=STATUS_FG,
            font=("Microsoft YaHei UI", 9), anchor="w",
        )
        self._status_label.pack(side="left", fill="x", expand=True)
        self._mode_button = tk.Menubutton(
            header,bg=BG,fg="#FFFFFF",activebackground="#283038",
            activeforeground="#FFFFFF",relief="flat",padx=8,pady=4,
            state="normal" if self._translation_available else "disabled",
        )
        menu = tk.Menu(self._mode_button,tearoff=False)
        self._mode_selection = tk.StringVar(value=display_mode)
        for mode, label in (("source", "原文"), ("translation", "译文"), ("bilingual", "双语")):
            menu.add_radiobutton(
                label=label,value=mode,variable=self._mode_selection,
                command=lambda value=mode:self._set_display_mode(value),
                state="normal" if mode == "source" or self._translation_available else "disabled",
            )
        self._mode_button.configure(menu=menu)
        self._mode_button.pack(side="left",padx=(3,0))
        self._pause_button = tk.Button(
            header, text="暂停",state="disabled",
            command=self._toggle_pause,
            bg="#332326", fg="#F0B2B2", activebackground="#4A292E",
            activeforeground="#FFFFFF", relief="flat", padx=10, pady=4,
        )
        self._pause_button.pack(side="left", padx=(10, 0))

        self._line_frame = tk.Frame(self._root, bg=BG)
        self._line_frame.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        scrollbar = tk.Scrollbar(self._line_frame, orient="vertical")
        self._canvas = tk.Canvas(self._line_frame, bg=BG, relief="flat", borderwidth=0,
                                 highlightthickness=0, yscrollincrement=20)
        self._canvas.pack(side="left", fill="both", expand=True)
        def update_scrollbar(first, last):
            scrollbar.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                scrollbar.pack_forget()
            elif not scrollbar.winfo_manager():
                scrollbar.pack(side="right", fill="y")
        self._canvas.configure(yscrollcommand=update_scrollbar)
        scrollbar.configure(command=self._canvas.yview)
        self._canvas.bind("<Configure>", lambda _event: self._invalidate_layout())
        self._canvas.bind("<MouseWheel>", lambda event: self._canvas.yview_scroll(-int(event.delta / 120), "units"))

        self._root.protocol("WM_DELETE_WINDOW", self._handle_close)
        self._make_draggable()
        self._layout_rows()
        self._update_mode_buttons()
        self._root.after(50, self._drain)

    # -- event plumbing ----------------------------------------------------

    def handle(self, event: ev.LiveEvent) -> None:
        self._queue.put(event)

    def run(self) -> None:
        self._root.deiconify()
        self._root.mainloop()

    def _drain(self) -> None:
        try:
            while True:
                self._apply(self._queue.get_nowait())
        except queue.Empty:
            pass
        self._redraw()
        self._root.after(50, self._drain)

    def _apply(self, event: ev.LiveEvent) -> None:
        if event.kind == ev.KIND_CAPTION_UPDATED:
            entry = next((item for item in reversed(self._history)
                          if item["segment_id"] == event.payload["segment_id"]), None)
            if entry is None:
                entry = {"segment_id": event.payload["segment_id"],
                         "source": "", "translation": "", "independent": True}
                self._history.append(entry)
                if len(self._history) > self._history_limit:
                    del self._history[:-self._history_limit]
            entry[event.payload["side"]] = event.payload["text"]
        elif event.kind == ev.KIND_PARTIAL_TRANSCRIPT:
            self._partial = event.payload["text"]
        elif event.kind == ev.KIND_FINAL_TRANSCRIPT:
            self._history.append({
                "segment_id": event.payload["segment_id"],
                "source": event.payload["text"],
                "translation": "",
            })
            if len(self._history) > self._history_limit:
                del self._history[:-self._history_limit]
            self._partial = None
        elif event.kind in (ev.KIND_TRANSLATION_PARTIAL, ev.KIND_TRANSLATION):
            self._set_translation(event.payload["segment_id"], event.payload["text"])
        elif event.kind == ev.KIND_TRANSLATION_ERROR:
            segment_id = event.payload["segment_id"]
            existing = next((entry["translation"] for entry in reversed(self._history)
                             if entry["segment_id"] == segment_id), "")
            self._set_translation(segment_id, existing + "（未完成）" if existing else "（翻译失败）")
        elif event.kind == ev.KIND_TRANSLATION_SKIPPED:
            self._set_translation(event.payload["segment_id"], "（跳过）", only_if_empty=True)
        elif event.kind in (ev.KIND_ASR_ERROR, ev.KIND_CAPTURE_ERROR, ev.KIND_RUNTIME_ERROR):
            self._error = f"{event.payload['message']}"
        elif event.kind == ev.KIND_SESSION_STARTED:
            self._status = f"{self._running_label} · 会话已开始"
            if not self._closing and self._on_pause is not None:
                self._pause_button.configure(state="normal")
        elif event.kind in (ev.KIND_SESSION_PAUSED,ev.KIND_SESSION_RESUMED):
            self._paused = event.kind == ev.KIND_SESSION_PAUSED
            self._partial = None
            self._status = "已暂停 · 不采集、不录音" if self._paused else self._running_label
            if not self._closing:
                self._pause_button.configure(text="继续" if self._paused else "暂停",state="normal")
        elif event.kind == ev.KIND_SESSION_ENDED:
            self._ended = True
            self._status = "会话已结束"
            self._partial = None
            self._pause_button.configure(state="disabled",text="已结束")
            if self._closing:
                self._root.after_idle(self._root.destroy)

    def _redraw(self) -> None:
        status = (f"{self._status} · {self._error}",ERROR_FG) if self._error else (self._status,STATUS_FG)
        if status != self._rendered_status:
            self._status_label.configure(text=status[0],fg=status[1])
            self._rendered_status = status

        visible: list[dict] = list(self._history)
        if self._partial and self._display_mode != "translation":
            visible.append({"source": self._partial, "translation": "…"})
        snapshot = (self._display_mode, self._canvas.winfo_width(),
                    tuple((e['source'],e['translation']) for e in visible))
        if snapshot == self._rendered:
            return
        following = self._canvas.yview()[1] >= 0.995
        previous_top = self._canvas.canvasy(0)
        rows = []
        for entry in visible:
            if self._display_mode != 'translation' and (entry['source'] or not entry.get('independent')):
                rows.append((entry['source'],'source'))
            if self._display_mode != 'source' and (entry['translation'] or not entry.get('independent')):
                rows.append(((entry['translation'] or '…'),'translation'))
            if not entry.get('independent') or (
                entry['source'] and self._display_mode != 'translation' or
                entry['translation'] and self._display_mode != 'source'
            ):
                rows.append(('', 'gap'))
        width = max(100, self._canvas.winfo_width() - 20)
        old = self._rendered_rows
        if not self._rendered or self._rendered[:2] != snapshot[:2]:
            self._canvas.delete('caption')
            old = []
            self._row_items = []
            self._row_heights = []
        prefix = 0
        while prefix < min(len(old),len(rows)) and old[prefix] == rows[prefix]:
            prefix += 1
        suffix = 0
        while suffix < min(len(old),len(rows))-prefix and old[-1-suffix] == rows[-1-suffix]:
            suffix += 1
        old_end,new_end = len(old)-suffix,len(rows)-suffix
        old_start_y = 6 + sum(self._row_heights[:prefix])
        old_middle_height = sum(self._row_heights[prefix:old_end])
        for items in self._row_items[prefix:old_end]:
            for item in items:
                self._canvas.delete(item)
        y, created, heights = old_start_y, [], []
        for value, kind in rows[prefix:new_end]:
            items = []
            if kind == 'gap':
                height = 12
            else:
                size = (self._font_size if kind == 'translation' or self._display_mode == 'source'
                        else max(10, self._font_size - 7))
                family = tk_family(self._font_family)
                face = (family, size, 'bold') if kind == 'translation' else (family, size)
                stroke = 2 if size >= 28 else 1
                for dx, dy in ((-stroke,-stroke),(-stroke,0),(-stroke,stroke),
                               (0,-stroke),(0,stroke),(stroke,-stroke),(stroke,0),(stroke,stroke)):
                    items.append(self._canvas.create_text(10+dx, y+dy, text=value, anchor='nw', width=width,
                                                          fill=self._subtitle_color, font=face, tags='caption'))
                item = self._canvas.create_text(10, y, text=value, anchor='nw', width=width,
                                                fill='#FFFFFF', font=face, tags='caption')
                items.append(item)
                bounds = self._canvas.bbox(item)
                height = max(size + 4, (bounds[3] - bounds[1]) if bounds else size + 4) + 4
            created.append(items)
            heights.append(height)
            y += height
        delta = sum(heights) - old_middle_height
        for items in self._row_items[old_end:]:
            for item in items:
                self._canvas.move(item, 0, delta)
        self._row_items = self._row_items[:prefix] + created + self._row_items[old_end:]
        self._row_heights = self._row_heights[:prefix] + heights + self._row_heights[old_end:]
        total_height = max(6 + sum(self._row_heights), self._canvas.winfo_height())
        self._canvas.configure(scrollregion=(0, 0, self._canvas.winfo_width(), total_height))
        if following:
            self._canvas.yview_moveto(1.0)
        else:
            if previous_top >= old_start_y + old_middle_height:
                previous_top += delta
            self._canvas.yview_moveto(previous_top / max(1,total_height))
        self._rendered_rows = rows
        self._rendered = snapshot

    def _set_display_mode(self, mode: str) -> None:
        if mode not in {"source", "translation", "bilingual"}:
            return
        if mode != "source" and not self._translation_available:
            return
        self._display_mode = mode
        self._layout_rows()
        self._update_mode_buttons()
        self._redraw()

    def _layout_rows(self) -> None:
        self._invalidate_layout()

    def _invalidate_layout(self) -> None:
        self._rendered = None

    def _update_mode_buttons(self) -> None:
        label = {"source":"原文","translation":"译文","bilingual":"双语"}[self._display_mode]
        self._mode_selection.set(self._display_mode)
        self._mode_button.configure(text=label+(" ▾" if self._translation_available else ""))

    def _set_translation(self, segment_id: str, text: str, *, only_if_empty: bool = False) -> None:
        for entry in reversed(self._history):
            if entry["segment_id"] == segment_id:
                if not only_if_empty or not entry["translation"]:
                    entry["translation"] = text
                return

    # -- window behaviour ----------------------------------------------------

    def _make_draggable(self) -> None:
        for widget in (self._status_label,):
            widget.bind("<Button-1>", self._start_move)
            widget.bind("<B1-Motion>", self._do_move)

    def _start_move(self, event) -> None:
        self._dx = event.x
        self._dy = event.y

    def _do_move(self, event) -> None:
        self._root.geometry(f"+{event.x_root - self._dx}+{event.y_root - self._dy}")

    def _toggle_pause(self) -> None:
        if self._closing or self._ended or self._on_pause is None:
            return
        self._pause_button.configure(state="disabled")
        self._status = "正在恢复…" if self._paused else "正在暂停…"
        self._on_pause(not self._paused)
        self._redraw()

    def _handle_close(self) -> None:
        if self._ended or self._on_close is None:
            self._root.destroy()
            return
        if self._closing:
            return
        self._closing = True
        self._status = "正在停止并保存录音…" if self._record_session else "正在结束会话…"
        self._pause_button.configure(state="disabled")
        if self._on_close is not None:
            self._on_close("window-stop")
        # keep the window alive until the runner destroys it after cleanup

    def finish(self, message: str) -> None:
        self._ended = True
        self._status = message
        self._pause_button.configure(state="disabled",text="已结束")
        self._redraw()
        if self._closing:
            self._root.after_idle(self._root.destroy)
