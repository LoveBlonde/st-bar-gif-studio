"""
ST-BAR GIF Studio — Transparent Screen Recorder & Spatio-Temporal GIF/WebP Optimizer GUI.
"""

import io
import os
import sys
import time
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import numpy as np
import cv2
from PIL import Image, ImageTk, ImageGrab
import mss

from .st_gif_codec import encode_st_gif, map_quality_to_st_gif_params
from .st_bar_webp import encode_st_bar_webp

# Enable High-DPI awareness on Windows so screen capture coordinates match physical pixels 1:1
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

TRANSPARENT_KEY = "#010203"


class ScreenRecorderOverlay(tk.Toplevel):
    """
    Movable, resizable transparent capture frame window.
    The interior region uses `-transparentcolor` so the user can see and click right through
    onto the game or video underneath.
    """

    def __init__(self, parent, on_capture_finished):
        super().__init__(parent)
        self.parent = parent
        self.on_capture_finished = on_capture_finished

        self.title("ST-BAR Screen Recorder")
        self.geometry("640x420+250+180")
        self.minsize(260, 180)
        self.attributes("-topmost", True)
        self.overrideredirect(True)  # Frameless hollow capture overlay
        self.configure(bg="#181c28")

        self.is_recording = False
        self.captured_frames = []
        self.captured_durations = []
        self.record_thread = None
        self.capture_bbox = {"left": 254, "top": 222, "width": 632, "height": 330}
        self._last_hole_sig = None
        self._rec_elapsed = 0.0
        self._rec_error: str | None = None
        self._drag_data = {"x": 0, "y": 0}
        self._resize_data = {"x": 0, "y": 0, "w": 0, "h": 0}

        self._build_overlay_ui()
        self.bind("<F9>", lambda e: self.toggle_recording())
        self.bind("<Escape>", lambda e: self.close_overlay())

    def _build_overlay_ui(self):
        # Top Control Bar (Draggable)
        self.top_bar = tk.Frame(self, bg="#181c28", height=38, cursor="fleur")
        self.top_bar.pack(side="top", fill="x")
        self.top_bar.bind("<ButtonPress-1>", self._start_move)
        self.top_bar.bind("<B1-Motion>", self._on_move)

        self.title_lbl = tk.Label(
            self.top_bar,
            text=" 🎯 ST-BAR 캡처 프레임 (드래그하여 이동 / F9 녹화)",
            bg="#181c28",
            fg="#e2e8f0",
            font=("Malgun Gothic", 9, "bold"),
        )
        self.title_lbl.pack(side="left", padx=8, pady=6)
        self.title_lbl.bind("<ButtonPress-1>", self._start_move)
        self.title_lbl.bind("<B1-Motion>", self._on_move)

        self.close_btn = tk.Button(
            self.top_bar,
            text="✕ 닫기",
            bg="#333b4d",
            fg="#ffffff",
            activebackground="#ff4757",
            relief="flat",
            font=("Malgun Gothic", 9, "bold"),
            command=self.close_overlay,
            padx=8,
        )
        self.close_btn.pack(side="right", padx=6, pady=4)

        # Bottom Control Bar
        self.bottom_bar = tk.Frame(self, bg="#181c28", height=44)
        self.bottom_bar.pack(side="bottom", fill="x")

        self.rec_btn = tk.Button(
            self.bottom_bar,
            text="● REC 녹화 시작 (F9)",
            bg="#ff4757",
            fg="#ffffff",
            activebackground="#ff6b81",
            relief="flat",
            font=("Malgun Gothic", 10, "bold"),
            padx=14,
            pady=4,
            command=self.toggle_recording,
        )
        self.rec_btn.pack(side="left", padx=8, pady=6)

        tk.Label(
            self.bottom_bar, text="FPS:", bg="#181c28", fg="#a0aec0", font=("Malgun Gothic", 9, "bold")
        ).pack(side="left", padx=(6, 2))

        self.fps_var = tk.StringVar(value="30")
        self.fps_menu = tk.OptionMenu(self.bottom_bar, self.fps_var, "15", "20", "24", "30", "50")
        self.fps_menu.config(bg="#252b3b", fg="#ffffff", relief="flat", highlightthickness=0)
        self.fps_menu.pack(side="left", padx=4)

        self.info_lbl = tk.Label(
            self.bottom_bar,
            text="대기 중",
            bg="#181c28",
            fg="#1dd1a1",
            font=("Consolas", 10, "bold"),
        )
        self.info_lbl.pack(side="left", padx=12)

        # Bottom-right resize grip
        self.resize_grip = tk.Label(
            self.bottom_bar,
            text="◢ 크기조절",
            bg="#252b3b",
            fg="#48dbfb",
            cursor="size_nw_se",
            font=("Malgun Gothic", 9, "bold"),
            padx=8,
            pady=6,
        )
        self.resize_grip.pack(side="right")
        self.resize_grip.bind("<ButtonPress-1>", self._start_resize)
        self.resize_grip.bind("<B1-Motion>", self._on_resize)

        # Middle Frame Border + Cutout Interior (via Win32 SetWindowRgn)
        self.border_frame = tk.Frame(
            self,
            bg="#181c28",
            highlightbackground="#1dd1a1",
            highlightcolor="#1dd1a1",
            highlightthickness=4,
        )
        self.border_frame.pack(side="top", fill="both", expand=True)

        self.BindConfigure = self.bind("<Configure>", self._update_dimensions_label)
        self.after(50, self._update_dimensions_label)

    def _apply_window_hole(self):
        """
        Cut a true OS-level rectangular hole inside `border_frame` using Win32 `SetWindowRgn`.
        Unlike `-transparentcolor` (`WS_EX_LAYERED` + `LWA_COLORKEY`), which DWM renders as
        opaque black `[0, 0, 0, 255]` during `BitBlt(..., CAPTUREBLT)`, `SetWindowRgn` physically
        removes the interior pixels from the window so screen capture and mouse clicks pass 100% through.
        """
        if sys.platform != "win32" or not self.winfo_exists():
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            win_w = self.winfo_width()
            win_h = self.winfo_height()
            hx1 = self.border_frame.winfo_x() + 4
            hy1 = self.border_frame.winfo_y() + 4
            raw_w = max(16, self.border_frame.winfo_width() - 8)
            raw_h = max(16, self.border_frame.winfo_height() - 8)
            sig = (win_w, win_h, hx1, hy1, raw_w, raw_h)
            if sig == self._last_hole_sig:
                return
            self._last_hole_sig = sig

            hwnd = user32.GetAncestor(self.winfo_id(), 2) or self.winfo_id()
            r_full = gdi32.CreateRectRgn(0, 0, win_w, win_h)
            r_hole = gdi32.CreateRectRgn(hx1, hy1, hx1 + raw_w, hy1 + raw_h)
            gdi32.CombineRgn(r_full, r_full, r_hole, 4)  # RGN_DIFF = 4
            user32.SetWindowRgn(hwnd, r_full, True)
            gdi32.DeleteObject(r_hole)
        except Exception:
            pass

    def _get_capture_bbox(self):
        self.update_idletasks()
        self._apply_window_hole()
        # Exclude the 4px highlight border so only the clean cutout interior is captured
        x = self.border_frame.winfo_rootx() + 4
        y = self.border_frame.winfo_rooty() + 4
        w = max(16, (self.border_frame.winfo_width() - 8) // 2 * 2)
        h = max(16, (self.border_frame.winfo_height() - 8) // 2 * 2)
        self.capture_bbox = {"left": x, "top": y, "width": w, "height": h}
        return self.capture_bbox

    def _update_dimensions_label(self, event=None):
        if not self.winfo_exists():
            return
        bbox = self._get_capture_bbox()
        if not self.is_recording:
            self.info_lbl.config(text=f"{bbox['width']} × {bbox['height']} px")

    def _start_move(self, event):
        self._drag_data["x"] = event.x_root - self.winfo_x()
        self._drag_data["y"] = event.y_root - self.winfo_y()

    def _on_move(self, event):
        nx = event.x_root - self._drag_data["x"]
        ny = event.y_root - self._drag_data["y"]
        self.geometry(f"+{nx}+{ny}")

    def _start_resize(self, event):
        self._resize_data["x"] = event.x_root
        self._resize_data["y"] = event.y_root
        self._resize_data["w"] = self.winfo_width()
        self._resize_data["h"] = self.winfo_height()

    def _on_resize(self, event):
        dw = event.x_root - self._resize_data["x"]
        dh = event.y_root - self._resize_data["y"]
        nw = max(260, self._resize_data["w"] + dw)
        nh = max(180, self._resize_data["h"] + dh)
        self.geometry(f"{nw}x{nh}")

    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        self.capture_bbox = self._get_capture_bbox()
        self.is_recording = True
        self.captured_frames = []
        self.captured_durations = []
        self._rec_elapsed = 0.0
        self._rec_error = None
        self.border_frame.config(highlightbackground="#ff4757", highlightcolor="#ff4757")
        self.rec_btn.config(text="■ 정지 및 편집 (F9)", bg="#feca57", fg="#12151e")
        fps = int(self.fps_var.get())
        self.record_thread = threading.Thread(target=self._record_loop, args=(fps,), daemon=True)
        self.record_thread.start()
        self.after(80, self._poll_recording_status)

    def _poll_recording_status(self):
        if not self.is_recording or not self.winfo_exists():
            return
        self._get_capture_bbox()
        n_f = len(self.captured_frames)
        el = self._rec_elapsed
        self.info_lbl.config(text=f"● REC {el:.1f}s ({n_f} frames)", fg="#ff6b81")
        self.after(80, self._poll_recording_status)

    @staticmethod
    def _capture_via_printwindow(bbox: dict) -> np.ndarray | None:
        """
        Fallback for hybrid-GPU or restricted GDI desktops using Win32 PrintWindow(PW_RENDERFULLCONTENT).
        """
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD),
                    ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            cx = bbox["left"] + bbox["width"] // 2
            cy = bbox["top"] + bbox["height"] // 2
            hit_hwnd = user32.WindowFromPoint(POINT(cx, cy))
            if not hit_hwnd:
                return None
            target_hwnd = user32.GetAncestor(hit_hwnd, 2) or hit_hwnd

            w_rect = wintypes.RECT()
            if not user32.GetWindowRect(target_hwnd, ctypes.byref(w_rect)):
                return None
            ww = max(1, w_rect.right - w_rect.left)
            wh = max(1, w_rect.bottom - w_rect.top)

            wnd_dc = user32.GetWindowDC(target_hwnd)
            if not wnd_dc:
                return None
            mem_dc = gdi32.CreateCompatibleDC(wnd_dc)
            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = ww
            bmi.biHeight = -wh
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bits = ctypes.c_void_p()
            hbmp = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
            gdi32.SelectObject(mem_dc, hbmp)

            ok = user32.PrintWindow(target_hwnd, mem_dc, 2)  # PW_RENDERFULLCONTENT = 2
            arr_rgb = None
            if ok and bits.value:
                full_bgra = np.ctypeslib.as_array((ctypes.c_uint8 * (wh * ww * 4)).from_address(bits.value)).reshape(wh, ww, 4)
                full_rgb = cv2.cvtColor(full_bgra, cv2.COLOR_BGRA2RGB)
                out = np.zeros((bbox["height"], bbox["width"], 3), dtype=np.uint8)
                ox1 = max(bbox["left"], w_rect.left)
                oy1 = max(bbox["top"], w_rect.top)
                ox2 = min(bbox["left"] + bbox["width"], w_rect.right)
                oy2 = min(bbox["top"] + bbox["height"], w_rect.bottom)
                if ox2 > ox1 and oy2 > oy1:
                    out[oy1 - bbox["top"] : oy2 - bbox["top"], ox1 - bbox["left"] : ox2 - bbox["left"]] = full_rgb[
                        oy1 - w_rect.top : oy2 - w_rect.top, ox1 - w_rect.left : ox2 - w_rect.left
                    ]
                arr_rgb = out

            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(target_hwnd, wnd_dc)
            return arr_rgb
        except Exception:
            return None

    def _record_loop(self, fps: int):
        target_interval = 1.0 / float(fps)
        t_start = time.perf_counter()
        last_t = t_start
        target_hw = None

        with mss.mss() as sct:
            while self.is_recording:
                now = time.perf_counter()
                bbox = dict(self.capture_bbox)
                arr_rgb = None
                try:
                    shot = sct.grab(bbox)
                    arr_bgra = np.array(shot, dtype=np.uint8)
                    arr_rgb = cv2.cvtColor(arr_bgra, cv2.COLOR_BGRA2RGB)
                except Exception as e_mss:
                    self._rec_error = str(e_mss)

                if arr_rgb is None or int(arr_rgb[::8, ::8].max()) == 0:
                    try:
                        pil_shot = ImageGrab.grab(
                            bbox=(bbox["left"], bbox["top"], bbox["left"] + bbox["width"], bbox["top"] + bbox["height"]),
                            include_layered_windows=False,
                            all_screens=True,
                        )
                        cand = np.array(pil_shot.convert("RGB"), dtype=np.uint8)
                        if int(cand[::8, ::8].max()) > 0 or arr_rgb is None:
                            arr_rgb = cand
                    except Exception:
                        pass

                if arr_rgb is None or int(arr_rgb[::8, ::8].max()) == 0:
                    pw_rgb = self._capture_via_printwindow(bbox)
                    if pw_rgb is not None and (int(pw_rgb[::8, ::8].max()) > 0 or arr_rgb is None):
                        arr_rgb = pw_rgb

                if arr_rgb is None:
                    self.is_recording = False
                    break

                if target_hw is None:
                    target_hw = (arr_rgb.shape[0], arr_rgb.shape[1])
                elif (arr_rgb.shape[0], arr_rgb.shape[1]) != target_hw:
                    arr_rgb = cv2.resize(arr_rgb, (target_hw[1], target_hw[0]), interpolation=cv2.INTER_AREA)

                self.captured_frames.append(arr_rgb)

                dt_ms = int(round((now - last_t) * 1000.0)) if len(self.captured_frames) > 1 else int(round(target_interval * 1000.0))
                self.captured_durations.append(max(10, dt_ms))
                last_t = now
                self._rec_elapsed = now - t_start

                sleep_t = target_interval - (time.perf_counter() - now)
                if sleep_t > 0:
                    time.sleep(sleep_t)

    def stop_recording(self):
        self.is_recording = False
        if self.record_thread is not None:
            self.record_thread.join(timeout=1.5)
        frames = self.captured_frames
        durs = self.captured_durations
        rec_err = self._rec_error
        self.destroy()
        self.parent.deiconify()
        self.parent.update_idletasks()
        self.parent.lift()
        if len(frames) > 0:
            self.on_capture_finished(frames, durs, "화면 녹화 캡처")
        elif rec_err:
            messagebox.showerror("화면 녹화 오류", f"화면을 캡처하지 못했습니다:\n{rec_err}")

    def close_overlay(self):
        self.is_recording = False
        self.destroy()
        self.parent.deiconify()


class STBarGifStudioApp(ctk.CTk):
    """
    Main Studio Window:
    - Load existing WebP / GIF / MP4 / WebM or launch Transparent Screen Recorder
    - Interactive animated preview with Start/End frame trim, Resolution scale, Playback speed
    - Continuous Quality Slider (1 ~ 100) with real-time parameter display & instant preview compression test
    """

    def __init__(self):
        super().__init__()
        self.title("ST-BAR GIF Studio — 시공간 LZW-RDO 움짤 녹화 & 최적화 스튜디오")
        self.geometry("1120x740")
        self.minsize(980, 660)

        self.raw_frames: list[np.ndarray] = []
        self.raw_durations: list[int] = []
        self.source_name: str = "없음"
        self.source_size_bytes: int = 0

        # Compressed preview cache
        self.compressed_bytes: bytes | None = None
        self.compressed_ext: str = ".gif"
        self.preview_frames: list[np.ndarray] = []
        self.preview_durations: list[int] = []
        self.showing_compressed_preview: bool = False

        self.is_playing: bool = True
        self.current_frame_idx: int = 0
        self._play_job = None
        self._photo_ref = None
        self._worker_queue: queue.Queue = queue.Queue()

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        # --- Top Toolbar ---
        top_frame = ctk.CTkFrame(self, height=56, corner_radius=10)
        top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 6))

        ctk.CTkButton(
            top_frame,
            text="🎥 화면 영역 녹화 (투명 캡처 프레임)",
            fg_color="#e84118",
            hover_color="#c23616",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            height=38,
            command=self.open_screen_recorder,
        ).pack(side="left", padx=10, pady=8)

        ctk.CTkButton(
            top_frame,
            text="📂 파일 열기 (WebP / GIF / MP4 / WebM)",
            fg_color="#2f3640",
            hover_color="#353b48",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            height=38,
            command=self.open_file_dialog,
        ).pack(side="left", padx=6, pady=8)

        docs_dir = os.path.join(os.path.expanduser("~"), "Documents")
        if os.path.isdir(docs_dir):
            ctk.CTkButton(
                top_frame,
                text="📁 내 문서 폴더 열기",
                fg_color="#3c6382",
                hover_color="#0a3d62",
                font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
                height=38,
                command=lambda: self.open_file_dialog(initial_dir=docs_dir),
            ).pack(side="left", padx=6, pady=8)

        self.source_info_lbl = ctk.CTkLabel(
            top_frame,
            text="파일을 열거나 [화면 영역 녹화]를 눌러 움짤을 캡처하세요.",
            font=ctk.CTkFont(family="Malgun Gothic", size=12),
            text_color="#a4b0be",
        )
        self.source_info_lbl.pack(side="right", padx=14)

        # --- Left Panel: Live Animated Preview & Timeline Trim ---
        left_panel = ctk.CTkFrame(self, corner_radius=10)
        left_panel.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(6, 12))
        left_panel.grid_rowconfigure(1, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        self.preview_badge_lbl = ctk.CTkLabel(
            left_panel,
            text="🎬 프리뷰 화면 (대기 중)",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            text_color="#48dbfb",
        )
        self.preview_badge_lbl.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))

        self.canvas_bg = tk.Canvas(left_panel, bg="#0f1219", highlightthickness=0)
        self.canvas_bg.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.canvas_bg.bind("<Configure>", self._on_canvas_configure)

        # Playback & Trim Bar
        trim_frame = ctk.CTkFrame(left_panel, fg_color="#181c28", corner_radius=8)
        trim_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 12))
        trim_frame.grid_columnconfigure(1, weight=1)

        self.play_btn = ctk.CTkButton(
            trim_frame,
            text="⏸ 일시정지",
            width=96,
            height=30,
            command=self.toggle_play,
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
        )
        self.play_btn.grid(row=0, column=0, padx=10, pady=8)

        self.frame_counter_lbl = ctk.CTkLabel(
            trim_frame,
            text="Frame: 0 / 0",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        )
        self.frame_counter_lbl.grid(row=0, column=1, sticky="w", padx=8)

        self.toggle_preview_btn = ctk.CTkButton(
            trim_frame,
            text="🔍 원본 / 압축본 비교 전환",
            width=160,
            height=30,
            fg_color="#3c40c6",
            state="disabled",
            command=self.toggle_compressed_preview,
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
        )
        self.toggle_preview_btn.grid(row=0, column=2, padx=10, pady=8)

        # Start / End Trim Sliders
        ctk.CTkLabel(trim_frame, text="시작 프레임:", font=ctk.CTkFont(family="Malgun Gothic", size=11)).grid(
            row=1, column=0, padx=10, pady=(0, 6), sticky="e"
        )
        self.start_trim_slider = ctk.CTkSlider(
            trim_frame, from_=0, to=100, number_of_steps=100, command=self._on_trim_changed
        )
        self.start_trim_slider.set(0)
        self.start_trim_slider.grid(row=1, column=1, columnspan=2, sticky="ew", padx=10, pady=(0, 6))

        ctk.CTkLabel(trim_frame, text="끝 프레임:", font=ctk.CTkFont(family="Malgun Gothic", size=11)).grid(
            row=2, column=0, padx=10, pady=(0, 10), sticky="e"
        )
        self.end_trim_slider = ctk.CTkSlider(
            trim_frame, from_=0, to=100, number_of_steps=100, command=self._on_trim_changed
        )
        self.end_trim_slider.set(100)
        self.end_trim_slider.grid(row=2, column=1, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

        # --- Right Panel: Compression Engine, Quality Slider & Export ---
        right_panel = ctk.CTkFrame(self, corner_radius=10)
        right_panel.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(6, 12))
        right_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right_panel,
            text="⚙️ ST-BAR / ST-GIF 압축 최적화 설정",
            font=ctk.CTkFont(family="Malgun Gothic", size=15, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        # 1. Output Format Selection
        fmt_box = ctk.CTkFrame(right_panel, fg_color="#181c28", corner_radius=8)
        fmt_box.grid(row=1, column=0, sticky="ew", padx=14, pady=6)
        ctk.CTkLabel(
            fmt_box, text="출력 움짤 포맷:", font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold")
        ).pack(side="left", padx=12, pady=10)

        self.format_var = ctk.StringVar(value="GIF (ST-GIF v3)")
        self.format_seg = ctk.CTkSegmentedButton(
            fmt_box,
            values=["GIF (ST-GIF v3)", "WebP (ST-BAR v4)"],
            variable=self.format_var,
            command=lambda _: self._update_quality_label(self.quality_slider.get()),
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
        )
        self.format_seg.pack(side="right", padx=12, pady=10)

        # 2. Scale & Playback Speed
        trans_box = ctk.CTkFrame(right_panel, fg_color="#181c28", corner_radius=8)
        trans_box.grid(row=2, column=0, sticky="ew", padx=14, pady=6)
        trans_box.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(trans_box, text="크기 조절:", font=ctk.CTkFont(family="Malgun Gothic", size=12)).grid(
            row=0, column=0, padx=12, pady=10, sticky="w"
        )
        self.scale_var = ctk.StringVar(value="100%")
        ctk.CTkOptionMenu(
            trans_box, values=["100%", "85%", "75%", "60%", "50%"], variable=self.scale_var, width=95
        ).grid(row=0, column=1, padx=6, pady=10)

        ctk.CTkLabel(trans_box, text="재생 배속:", font=ctk.CTkFont(family="Malgun Gothic", size=12)).grid(
            row=0, column=2, padx=12, pady=10, sticky="w"
        )
        self.speed_var = ctk.StringVar(value="1.0x")
        ctk.CTkOptionMenu(
            trans_box, values=["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"], variable=self.speed_var, width=95
        ).grid(row=0, column=3, padx=12, pady=10)

        # 3. Continuous Quality Slider (1 ~ 100)
        q_box = ctk.CTkFrame(right_panel, fg_color="#181c28", corner_radius=8)
        q_box.grid(row=3, column=0, sticky="ew", padx=14, pady=6)
        q_box.grid_columnconfigure(0, weight=1)

        self.quality_title_lbl = ctk.CTkLabel(
            q_box,
            text="🎚️ 압축 품질(Quality) 슬라이더: 75 / 100",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            text_color="#1dd1a1",
        )
        self.quality_title_lbl.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        self.quality_slider = ctk.CTkSlider(
            q_box,
            from_=1,
            to=100,
            number_of_steps=99,
            command=self._update_quality_label,
            progress_color="#1dd1a1",
            button_color="#48dbfb",
        )
        self.quality_slider.set(75)
        self.quality_slider.grid(row=1, column=0, sticky="ew", padx=14, pady=6)

        # Quick Preset Buttons for the Slider
        preset_row = ctk.CTkFrame(q_box, fg_color="transparent")
        preset_row.grid(row=2, column=0, sticky="ew", padx=12, pady=2)
        for label, q_val in [("초경량 (35)", 35), ("컴팩트 (50)", 50), ("밸런스 추천 (75)", 75), ("고화질 (90)", 90)]:
            ctk.CTkButton(
                preset_row,
                text=label,
                height=26,
                width=82,
                fg_color="#2f3640",
                hover_color="#3c40c6",
                font=ctk.CTkFont(family="Malgun Gothic", size=11),
                command=lambda v=q_val: self._set_quality_preset(v),
            ).pack(side="left", padx=3, pady=2, expand=True, fill="x")

        self.param_detail_lbl = ctk.CTkLabel(
            q_box,
            text="",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#a4b0be",
            justify="left",
        )
        self.param_detail_lbl.grid(row=3, column=0, sticky="w", padx=14, pady=(4, 10))
        self._update_quality_label(75)

        # 4. Live Compression Test & Metrics Readout Card
        stat_box = ctk.CTkFrame(right_panel, fg_color="#141824", corner_radius=8, border_width=1, border_color="#2f3640")
        stat_box.grid(row=4, column=0, sticky="ew", padx=14, pady=8)
        stat_box.grid_columnconfigure(0, weight=1)

        self.result_size_lbl = ctk.CTkLabel(
            stat_box,
            text="예상 압축 용량: [압축 테스트] 버튼을 눌러 확인하세요",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            text_color="#feca57",
        )
        self.result_size_lbl.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        self.result_sub_lbl = ctk.CTkLabel(
            stat_box,
            text="슬라이더를 조절한 뒤 압축 결과를 프리뷰 화면에서 바로 비교할 수 있습니다.",
            font=ctk.CTkFont(family="Malgun Gothic", size=11),
            text_color="#a4b0be",
        )
        self.result_sub_lbl.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 8))

        self.progress_bar = ctk.CTkProgressBar(stat_box, height=10, progress_color="#1dd1a1")
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=2, column=0, sticky="ew", padx=14, pady=(2, 12))

        # 5. Action Buttons: Preview Test & Save File
        btn_box = ctk.CTkFrame(right_panel, fg_color="transparent")
        btn_box.grid(row=5, column=0, sticky="ew", padx=14, pady=(6, 12))
        btn_box.grid_columnconfigure(0, weight=1)

        self.test_compress_btn = ctk.CTkButton(
            btn_box,
            text="⚡ 현재 품질로 압축 테스트 & 화질 미리보기",
            fg_color="#0097e6",
            hover_color="#00a8ff",
            height=42,
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            command=self.run_preview_compression,
        )
        self.test_compress_btn.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.save_btn = ctk.CTkButton(
            btn_box,
            text="💾 최적화된 움짤 저장하기 (Export GIF / WebP)",
            fg_color="#10ac84",
            hover_color="#1dd1a1",
            height=46,
            font=ctk.CTkFont(family="Malgun Gothic", size=14, weight="bold"),
            command=self.export_file,
        )
        self.save_btn.grid(row=1, column=0, sticky="ew")

    def _set_quality_preset(self, val: int):
        self.quality_slider.set(val)
        self._update_quality_label(val)

    def _update_quality_label(self, val):
        q = int(round(float(val)))
        self.quality_title_lbl.configure(text=f"🎚️ 압축 품질(Quality) 슬라이더: {q} / 100")
        if self.format_var.get().startswith("GIF"):
            p = map_quality_to_st_gif_params(q, 1.5)
            self.param_detail_lbl.configure(
                text=(
                    f"• 팔레트 색상: {p['num_colors']}색 (+투명 255)  |  보로노이 고정 임계값: ±{p['voronoi_keep_tol']}\n"
                    f"• LZW 수평 런 병합 허용치: ±{p['lzw_run_tol']}  |  시공간 고정 Bayer 디더: {p['dither_str']:.2f}"
                )
            )
        else:
            sigma_s = 1.65 - 1.05 * (q / 100.0)
            self.param_detail_lbl.configure(
                text=(
                    f"• ST-BAR v4 서브프레임 라우팅: VP8(q={q}) + 16x16 블록 알파 + Near-Lossless VP8L\n"
                    f"• 시공간 노이즈 게이트 배율: {sigma_s:.2f}x  |  이중 델타 스파이크 제거: 활성"
                )
            )

    def open_screen_recorder(self):
        self.is_playing = False
        if self._play_job is not None:
            self.after_cancel(self._play_job)
            self._play_job = None
        self.source_size_bytes = 0
        self.withdraw()
        ScreenRecorderOverlay(self, self.on_sequence_loaded)

    def open_file_dialog(self, initial_dir=None):
        filetypes = [
            ("움짤 및 비디오 파일", "*.webp *.gif *.mp4 *.webm *.avi *.mkv"),
            ("모든 파일", "*.*"),
        ]
        path = filedialog.askopenfilename(
            title="최적화할 움짤 또는 비디오 선택",
            initialdir=initial_dir or os.getcwd(),
            filetypes=filetypes,
        )
        if not path:
            return

        self.result_size_lbl.configure(text="파일을 디코딩하는 중입니다...", text_color="#48dbfb")
        self.update_idletasks()

        ext = os.path.splitext(path)[1].lower()
        frames = []
        durs = []

        try:
            if ext in (".webp", ".gif", ".png", ".apng"):
                im = Image.open(path)
                while True:
                    # Load first: Pillow's WebP plugin sets info["duration"] only on load (else it is
                    # the previous frame's duration).
                    frames.append(np.array(im.convert("RGB")))
                    durs.append(max(15, int(im.info.get("duration", 33) or 33)))
                    im.seek(im.tell() + 1)
            else:
                cap = cv2.VideoCapture(path)
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                dur_ms = max(15, int(round(1000.0 / fps)))
                while len(frames) < 400:
                    ret, bgr = cap.read()
                    if not ret:
                        break
                    frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                    durs.append(dur_ms)
                cap.release()
        except EOFError:
            pass
        except Exception as e:
            messagebox.showerror("파일 열기 오류", f"파일을 읽는 중 오류가 발생했습니다:\n{e}")
            return

        if len(frames) == 0:
            messagebox.showwarning("빈 파일", "프레임을 추출할 수 없습니다.")
            return

        self.source_size_bytes = os.path.getsize(path)
        self.on_sequence_loaded(frames, durs, os.path.basename(path))

    def on_sequence_loaded(self, frames: list[np.ndarray], durs: list[int], name: str):
        self.raw_frames = frames
        self.raw_durations = durs
        self.source_name = name
        self.compressed_bytes = None
        self.showing_compressed_preview = False
        self.toggle_preview_btn.configure(state="disabled")

        n = len(frames)
        H, W, _ = frames[0].shape
        steps = max(1, n - 1)
        slider_max = max(1, n - 1)
        self.start_trim_slider.configure(from_=0, to=slider_max, number_of_steps=steps)
        self.end_trim_slider.configure(from_=0, to=slider_max, number_of_steps=steps)
        self.start_trim_slider.set(0)
        self.end_trim_slider.set(n - 1)

        sz_str = f" ({self.source_size_bytes/1024:,.1f} KB)" if self.source_size_bytes > 0 else ""
        self.source_info_lbl.configure(
            text=f"📄 {name}{sz_str}  |  {W}×{H} px  |  {n} 프레임"
        )
        self.preview_badge_lbl.configure(text=f"🎬 원본 프리뷰 ({W}×{H}, {n} 프레임)", text_color="#48dbfb")
        self.result_size_lbl.configure(
            text="준비가 완료되었습니다. [압축 테스트] 또는 [저장하기]를 누르세요.",
            text_color="#feca57",
        )
        self.current_frame_idx = 0
        self.is_playing = True
        self.play_btn.configure(text="⏸ 일시정지")
        self.update_idletasks()
        self._schedule_next_frame()

    def _on_canvas_configure(self, event=None):
        if not self.is_playing and (self.raw_frames or self.preview_frames):
            self._schedule_next_frame()

    def _on_trim_changed(self, _=None):
        s = int(round(self.start_trim_slider.get()))
        e = int(round(self.end_trim_slider.get()))
        if s > e:
            self.end_trim_slider.set(s)
            e = s
        n = len(self.raw_frames)
        if n > 0:
            self.frame_counter_lbl.configure(text=f"구간: {s} ~ {e} (총 {e - s + 1} 프레임)")

    def _get_transformed_sequence(self) -> tuple[list[np.ndarray], list[int]]:
        s = int(round(self.start_trim_slider.get()))
        e = int(round(self.end_trim_slider.get()))
        s = max(0, min(s, len(self.raw_frames) - 1))
        e = max(s, min(e, len(self.raw_frames) - 1))

        scale_pct = int(self.scale_var.get().replace("%", "")) / 100.0
        speed_mult = float(self.speed_var.get().replace("x", ""))

        sub_frames = self.raw_frames[s : e + 1]
        sub_durs = [max(15, int(round(d / speed_mult))) for d in self.raw_durations[s : e + 1]]

        if scale_pct != 1.0:
            H, W, _ = sub_frames[0].shape
            nw = max(16, int(round(W * scale_pct)) // 2 * 2)
            nh = max(16, int(round(H * scale_pct)) // 2 * 2)
            sub_frames = [cv2.resize(f, (nw, nh), interpolation=cv2.INTER_AREA) for f in sub_frames]

        return sub_frames, sub_durs

    def toggle_play(self):
        self.is_playing = not self.is_playing
        self.play_btn.configure(text="⏸ 일시정지" if self.is_playing else "▶ 재생")
        if self.is_playing:
            self._schedule_next_frame()

    def toggle_compressed_preview(self):
        if not self.preview_frames:
            return
        self.showing_compressed_preview = not self.showing_compressed_preview
        if self.showing_compressed_preview:
            sz_kb = len(self.compressed_bytes) / 1024.0
            self.preview_badge_lbl.configure(
                text=f"✨ 압축 결과 프리뷰 ({self.compressed_ext.upper()} — {sz_kb:,.1f} KB, Q={int(self.quality_slider.get())})",
                text_color="#1dd1a1",
            )
        else:
            self.preview_badge_lbl.configure(
                text=f"🎬 원본 프리뷰 ({self.source_name})",
                text_color="#48dbfb",
            )

    def _schedule_next_frame(self):
        if self._play_job is not None:
            self.after_cancel(self._play_job)
            self._play_job = None

        active_seq = self.preview_frames if (self.showing_compressed_preview and self.preview_frames) else self.raw_frames
        active_durs = self.preview_durations if (self.showing_compressed_preview and self.preview_durations) else self.raw_durations

        if not active_seq:
            return

        if not self.showing_compressed_preview:
            s = int(round(self.start_trim_slider.get()))
            e = int(round(self.end_trim_slider.get()))
            if self.current_frame_idx < s or self.current_frame_idx > e:
                self.current_frame_idx = s
        else:
            s, e = 0, len(active_seq) - 1
            if self.current_frame_idx > e:
                self.current_frame_idx = 0

        frame_rgb = active_seq[self.current_frame_idx]
        dur_ms = active_durs[self.current_frame_idx]

        # Fit image to canvas while preserving aspect ratio
        cw = max(100, self.canvas_bg.winfo_width())
        ch = max(100, self.canvas_bg.winfo_height())
        fh, fw, _ = frame_rgb.shape
        scale = min(cw / float(fw), ch / float(fh))
        dw, dh = max(1, int(fw * scale)), max(1, int(fh * scale))

        pil_im = Image.fromarray(frame_rgb)
        if (dw, dh) != (fw, fh):
            pil_im = pil_im.resize((dw, dh), Image.Resampling.BILINEAR)

        self._photo_ref = ImageTk.PhotoImage(pil_im)
        self.canvas_bg.delete("all")
        self.canvas_bg.create_image(cw // 2, ch // 2, image=self._photo_ref, anchor="center")

        self.frame_counter_lbl.configure(
            text=f"Frame: {self.current_frame_idx + 1} / {len(active_seq)}  (구간 {s}..{e})"
        )

        if self.is_playing:
            self.current_frame_idx += 1
            if self.current_frame_idx > e:
                self.current_frame_idx = s
            speed_mult = float(self.speed_var.get().replace("x", "")) if not self.showing_compressed_preview else 1.0
            wait_ms = max(15, int(round(dur_ms / speed_mult)))
            self._play_job = self.after(wait_ms, self._schedule_next_frame)

    def run_preview_compression(self, save_after: str | None = None):
        if not self.raw_frames:
            messagebox.showinfo("알림", "먼저 움짤 파일을 열거나 화면을 녹화해주세요.")
            return

        self.test_compress_btn.configure(state="disabled")
        self.save_btn.configure(state="disabled")
        q = int(round(self.quality_slider.get()))
        is_gif = self.format_var.get().startswith("GIF")
        frames, durs = self._get_transformed_sequence()

        def update_prog(p: float, msg: str):
            self._worker_queue.put(("progress", (p, msg)))

        def worker():
            try:
                if is_gif:
                    out_bytes, elapsed_ms = encode_st_gif(frames, durs, quality=q, progress_callback=update_prog)
                    ext = ".gif"
                else:
                    out_bytes, elapsed_ms = encode_st_bar_webp(frames, durs, quality=q, progress_callback=update_prog)
                    ext = ".webp"

                # Decode compressed output so user can preview exact compressed visual quality!
                im = Image.open(io.BytesIO(out_bytes))
                dec_f, dec_d = [], []
                try:
                    while True:
                        dec_f.append(np.array(im.convert("RGB")))
                        dec_d.append(max(15, int(im.info.get("duration", 30) or 30)))
                        im.seek(im.tell() + 1)
                except EOFError:
                    pass

                self._worker_queue.put(("done", (out_bytes, ext, dec_f, dec_d, elapsed_ms, q, save_after)))
            except Exception as e:
                self._worker_queue.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()
        self.after(40, self._poll_worker_queue)

    def _poll_worker_queue(self):
        keep_polling = True
        while True:
            try:
                kind, payload = self._worker_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "progress":
                p, msg = payload
                self.progress_bar.set(p)
                self.result_sub_lbl.configure(text=msg)
            elif kind == "done":
                out_bytes, ext, dec_f, dec_d, elapsed_ms, q, save_after = payload
                self._on_compression_done(out_bytes, ext, dec_f, dec_d, elapsed_ms, q, save_after)
                keep_polling = False
            elif kind == "error":
                messagebox.showerror("압축 오류", payload)
                self.test_compress_btn.configure(state="normal")
                self.save_btn.configure(state="normal")
                keep_polling = False

        if keep_polling:
            self.after(40, self._poll_worker_queue)

    def _on_compression_done(self, out_bytes, ext, dec_f, dec_d, elapsed_ms, q, save_after):
        self.compressed_bytes = out_bytes
        self.compressed_ext = ext
        self.preview_frames = dec_f
        self.preview_durations = dec_d
        self.showing_compressed_preview = True

        self.test_compress_btn.configure(state="normal")
        self.save_btn.configure(state="normal")
        self.toggle_preview_btn.configure(state="normal")

        sz_kb = len(out_bytes) / 1024.0
        sz_mb = sz_kb / 1024.0
        ratio_txt = ""
        if self.source_size_bytes > 0:
            diff_pct = (1.0 - len(out_bytes) / float(self.source_size_bytes)) * 100.0
            ratio_txt = f"  (원본 파일 대비 {diff_pct:+.1f}%)"

        self.result_size_lbl.configure(
            text=f"✅ 압축 결과: {sz_kb:,.1f} KB ({sz_mb:.2f} MB){ratio_txt}",
            text_color="#1dd1a1",
        )
        self.result_sub_lbl.configure(
            text=f"인코딩 소요 시간: {elapsed_ms/1000.0:.2f}초  |  현재 프리뷰에 압축된 실제 화질이 표시됩니다."
        )
        self.preview_badge_lbl.configure(
            text=f"✨ 압축 결과 프리뷰 ({ext.upper()} — {sz_kb:,.1f} KB, Quality={q})",
            text_color="#1dd1a1",
        )

        if save_after:
            with open(save_after, "wb") as f:
                f.write(out_bytes)
            messagebox.showinfo(
                "저장 완료",
                f"움짤 저장이 완료되었습니다!\n\n경로: {save_after}\n크기: {sz_kb:,.1f} KB ({sz_mb:.2f} MB)",
            )

    def export_file(self):
        if not self.raw_frames:
            messagebox.showinfo("알림", "먼저 움짤 파일을 열거나 화면을 녹화해주세요.")
            return

        is_gif = self.format_var.get().startswith("GIF")
        ext = ".gif" if is_gif else ".webp"
        base = os.path.splitext(self.source_name)[0]
        q = int(round(self.quality_slider.get()))
        default_name = f"{base}_st_q{q}{ext}"

        save_path = filedialog.asksaveasfilename(
            title="최적화된 움짤 저장",
            initialfile=default_name,
            defaultextension=ext,
            filetypes=[("GIF 움짤", "*.gif"), ("Animated WebP", "*.webp")],
        )
        if not save_path:
            return

        self.run_preview_compression(save_after=save_path)


def launch_studio():
    app = STBarGifStudioApp()
    app.mainloop()


if __name__ == "__main__":
    launch_studio()
