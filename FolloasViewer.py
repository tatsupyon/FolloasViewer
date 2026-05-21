import os
import cv2
import csv
import glob
import time
import threading
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import shutil
import tempfile
import sys

# ==========================================
# バージョン定義
# ==========================================
VERSION = "V1.64 2026/05/20"

# ==========================================
# 外部モジュール（log_summarizer.py）の完全統合
# ==========================================
def run_summarize_log(folder_path, threshold, prefix):
    """指定されたフォルダの head2.csv を集計し、output.csv を生成する"""
    X1, Y1, X2, Y2, SCORE, CLASS_NUM = 7, 9, 11, 13, 15, 17
    
    header_row = f'ログファイル,認識回数,未認識,(除外)複数認識,認識率,平均スコア,{threshold}以上,{threshold}未満,大きさ(X2-X1)*(Y2-Y1)'
    
    input_filepath = os.path.join(folder_path, f'{prefix}_head2.csv')
    output_filepath = os.path.join(folder_path, f'{prefix}_output.csv')

    if not os.path.exists(input_filepath):
        raise FileNotFoundError(f"入力ファイル {input_filepath} が見つかりません。")

    def summarize(count, recognized, unrecognized, exclusion, total_score, score_above, score_below, total_area, score, area):
        if count == 0: unrecognized += 1
        elif count == 1:
            recognized += 1
            total_score += score
            total_area += area
            if score >= threshold: score_above += 1
            else: score_below += 1
        else: exclusion += 1
        return recognized, unrecognized, exclusion, total_score, score_above, score_below, total_area

    with open(output_filepath, 'w', encoding='cp932', newline='') as csv_file, open(input_filepath, 'r', encoding='cp932') as f:
        csv_file.write(header_row + '\n')
        recognized, unrecognized, exclusion = 0, -1, 0
        total_score, score_above, score_below, total_area = 0.0, 0, 0, 0
        count, score, area = 0, 0.0, 0
        datalist = f.readlines()
        for line in datalist:
            line = line.strip()
            data = line.split(',')
            if data and data[0] == '#':
                if data[1] == 'Frame':
                    recognized, unrecognized, exclusion, total_score, score_above, score_below, total_area = summarize(count, recognized, unrecognized, exclusion, total_score, score_above, score_below, total_area, score, area)
                    count = 0
                elif len(data) > CLASS_NUM and data[CLASS_NUM] == '0':
                    count += 1
                    score = float(data[SCORE])
                    area = (int(data[X2]) - int(data[X1])) * (int(data[Y2]) - int(data[Y1]))
        recognized, unrecognized, exclusion, total_score, score_above, score_below, total_area = summarize(count, recognized, unrecognized, exclusion, total_score, score_above, score_below, total_area, score, area)
        ratio = recognized / (recognized + unrecognized) if (recognized + unrecognized) > 0 else 0.0
        recognized2 = recognized if recognized > 0 else 1
        avg_score, avg_area = total_score / recognized2, total_area / recognized2
        
        log_file_basename = f"{prefix}_head2.csv"
        csv_file.write(f"{log_file_basename},{recognized},{unrecognized},{exclusion},{ratio},{avg_score},{score_above},{score_below},{avg_area}\n")




class FolloasViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Folloas キャプチャ画像 VIEWER ({VERSION})")
        self.root.geometry("1866x1000")
        self.root.resizable(False, False)
        self.root.configure(bg='#f0f0f0')

        # --- 描画・解析用設定 (V1.06準拠) ---
        self.fontsize = 10
        self.fontpitchx = 7
        self.fontpitchy = 14
        self.fontsize2 = 20
        self.fontpitchx2 = 14
        self.fontpitchy2 = 28
        self.score_var = tk.DoubleVar(value=0.4)
        self.target_dir = ""
        self.total_frames = 0
        self.current_frame = 0
        self.is_playing = False
        self.log_data = {} 
        
        # カット管理（フラグ配列方式）
        self.cut_flags = []
        self.current_out = None
        self.is_exporting = False
        
        self.tk_meta = None
        self.last_time = 0
        self.fps_val = 0.0

        self.batch_mode = False
        self._setup_ui()
        self.root.bind("<Key>", self._on_key)
        
        # 引数チェック
        if len(sys.argv) > 1:
            # 引数を取得し、前後の空白除去とパスの正規化を行う
            input_path = os.path.normpath(os.path.abspath(sys.argv[1].strip()))
            
            if os.path.isdir(input_path):
                self.batch_mode = True
                self.root.after(500, lambda: self.browse_folder(input_path))
                # 読み込み完了（の少し後）にエクスポートを開始
                self.root.after(2000, self.start_batch_export)
            else:
                print(f"Error: Directory not found - {input_path}")
                self.root.after(100, self.root.destroy)

        # IME無効化 (Windowsのみ)
        if sys.platform == "win32":
            self.root.after(200, self._disable_ime)

    def _disable_ime(self):
        """WindowsのIMEを無効化する"""
        try:
            import ctypes
            hwnd = self.root.winfo_id()
            ctypes.windll.imm32.ImmAssociateContext(hwnd, 0)
        except:
            pass

    def _setup_ui(self):
        # 1. メインキャンバス (1866x880)
        self.main_canvas = tk.Canvas(self.root, width=1866, height=880, bg='#f0f0f0', highlightthickness=0)
        self.main_canvas.pack(side=tk.TOP)

        # 2. 下部操作パネル
        self.ctrl_panel = tk.Frame(self.root, height=120, bg='#f0f0f0')
        self.ctrl_panel.pack(side=tk.BOTTOM, fill=tk.X)

        self.timeline_width = 1846
        self.timeline_canvas = tk.Canvas(self.ctrl_panel, width=self.timeline_width, height=30, bg='#444444', highlightthickness=0)
        self.timeline_canvas.place(x=10, y=5)
        self.timeline_canvas.bind("<Button-1>", self._on_timeline_click)
        self.timeline_canvas.bind("<B1-Motion>", self._on_timeline_click)

        # SCORE閾値入力用 (Y=830)
        self.score_unit = tk.Frame(self.main_canvas, bg='#f0f0f0')
        self.main_canvas.create_window(60, 830, window=self.score_unit, anchor=tk.NW)
        tk.Label(self.score_unit, text="SCORE閾値=", bg='#f0f0f0', font=("游ゴシック", 10), fg="blue").pack(side=tk.LEFT)
        self.score_entry = tk.Entry(self.score_unit, textvariable=self.score_var, width=5, font=("游ゴシック", 10), justify='center')
        self.score_entry.pack(side=tk.LEFT)
        self.score_entry.bind("<Return>", lambda e: self.update_view())

        # 解析位相 (Y=745)
        self.ana_unit = tk.Frame(self.main_canvas, bg='#f0f0f0')
        self.main_canvas.create_window(182, 745, window=self.ana_unit, anchor=tk.N)
        tk.Label(self.ana_unit, text="解析位相：", bg='#f0f0f0', font=("MS Gothic", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(self.ana_unit, text="◀", width=3, command=lambda: self.adjust_offset("log", -1)).pack(side=tk.LEFT, padx=2)
        self.offset_var = tk.IntVar(value=0)
        ana_stack = tk.Frame(self.ana_unit, bg='#f0f0f0'); ana_stack.pack(side=tk.LEFT, padx=2)
        tk.Entry(ana_stack, textvariable=self.offset_var, width=5, justify='center').pack()
        tk.Scale(ana_stack, from_=-9999, to=9999, orient=tk.HORIZONTAL, variable=self.offset_var, length=150, showvalue=False, command=self._on_offset_change).pack()
        tk.Button(self.ana_unit, text="▶", width=3, command=lambda: self.adjust_offset("log", 1)).pack(side=tk.LEFT, padx=2)

        # Live1枠表示用チェックボックス追加 (Y=745, X=729)
        self.show_live1_box_var = tk.BooleanVar(value=True)
        self.cb_live1_box = tk.Checkbutton(self.main_canvas, variable=self.show_live1_box_var, bg='#f0f0f0', command=self.update_view)
        self.main_canvas.create_window(729, 745, window=self.cb_live1_box, anchor=tk.NW)

        # フレーム情報 (Y=745)
        self.frame_unit = tk.Frame(self.main_canvas, bg='#f0f0f0')
        self.main_canvas.create_window(880, 745, window=self.frame_unit, anchor=tk.NW)
        tk.Label(self.frame_unit, text="Frame(30fps):", bg='#f0f0f0', font=("MS Gothic", 10, "bold")).pack(side=tk.LEFT)
        
        self.frame_var = tk.StringVar(value="0")
        # ★ フレーム番号入力用Entryの作成とイベントバインド (V1.28)
        self.frame_entry = tk.Entry(self.frame_unit, textvariable=self.frame_var, width=7, justify='right', font=("MS Gothic", 10, "bold"))
        self.frame_entry.pack(side=tk.LEFT, padx=2)
        self.frame_entry.bind("<Return>", self._on_frame_enter)
        
        self.total_lbl = tk.Label(self.frame_unit, text=" / 0", bg='#f0f0f0', font=("MS Gothic", 10, "bold")); self.total_lbl.pack(side=tk.LEFT)
        self.fps_var = tk.StringVar(value="[ 0.0 fps ]")
        tk.Label(self.frame_unit, textvariable=self.fps_var, bg='#f0f0f0', font=("MS Gothic", 10, "bold")).pack(side=tk.LEFT, padx=15)
        self.cut_lbl = tk.Label(self.frame_unit, text="", bg='#f0f0f0', fg='red', font=("MS Gothic", 10, "bold"))
        self.cut_lbl.pack(side=tk.LEFT)

        # LIVE2位相 (Y=745)
        self.l2_unit = tk.Frame(self.main_canvas, bg='#f0f0f0')
        self.main_canvas.create_window(1656, 745, window=self.l2_unit, anchor=tk.N)
        tk.Label(self.l2_unit, text="LIVE2位相：", bg='#f0f0f0', font=("MS Gothic", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(self.l2_unit, text="◀", width=3, command=lambda: self.adjust_offset("live2", -1)).pack(side=tk.LEFT, padx=2)
        self.offset_live2_var = tk.IntVar(value=0)
        l2_stack = tk.Frame(self.l2_unit, bg='#f0f0f0'); l2_stack.pack(side=tk.LEFT, padx=2)
        tk.Entry(l2_stack, textvariable=self.offset_live2_var, width=5, justify='center').pack()
        tk.Scale(l2_stack, from_=-9999, to=9999, orient=tk.HORIZONTAL, variable=self.offset_live2_var, length=150, showvalue=False, command=self._on_offset_change).pack()
        tk.Button(self.l2_unit, text="▶", width=3, command=lambda: self.adjust_offset("live2", 1)).pack(side=tk.LEFT, padx=2)

        # フォルダ参照・再生コントロール
        tk.Button(self.ctrl_panel, text="フォルダ参照", width=12, command=self.browse_folder).place(x=10, y=60)
        tk.Button(self.ctrl_panel, text="設定記録", width=10, command=self.save_config).place(x=110, y=60)
        play_grp = tk.Frame(self.ctrl_panel, bg='#f0f0f0'); play_grp.place(x=1040, y=60, anchor=tk.N)
        tk.Button(play_grp, text="◀ コマ戻し", width=10, command=self.step_backward).pack(side=tk.LEFT, padx=2)
        self.btn_play = tk.Button(play_grp, text="再生", width=10, command=self.toggle_play); self.btn_play.pack(side=tk.LEFT, padx=2)
        tk.Button(play_grp, text="コマ送り ▶", width=10, command=self.step_forward).pack(side=tk.LEFT, padx=2)

        # エクスポートUI (V1.45)
        edit_grp = tk.Frame(self.ctrl_panel, bg='#f0f0f0'); edit_grp.place(x=1400, y=60, anchor=tk.N)
        self.cut_mode_var = tk.BooleanVar(value=True)
        tk.Checkbutton(edit_grp, text="CUT", variable=self.cut_mode_var, bg='#f0f0f0', font=("MS Gothic", 10), command=self.redraw_timeline).pack(side=tk.LEFT, padx=2)
        self.btn_start = tk.Button(edit_grp, text="START", width=7, command=self.mark_start)
        self.btn_start.pack(side=tk.LEFT, padx=2)
        self.btn_end = tk.Button(edit_grp, text="END", width=7, command=self.mark_end)
        self.btn_end.pack(side=tk.LEFT, padx=2)
        self.btn_export = tk.Button(edit_grp, text="EXPORT", width=10, command=self.on_export_click)
        self.btn_export.pack(side=tk.LEFT, padx=15)

    def _on_key(self, event):
        key = event.keysym
        if key == 'Up': 
            self.score_var.set(round(min(1.0, self.score_var.get() + 0.05), 2))
            self.update_view()
        elif key == 'Down': 
            self.score_var.set(round(max(0.0, self.score_var.get() - 0.05), 2))
            self.update_view()

    # ★ V1.28 追加: フレーム番号入力からのジャンプ処理
    def _on_frame_enter(self, event):
        if self.total_frames == 0:
            self.frame_var.set("0")
            self.main_canvas.focus_set()
            return
        
        try:
            val = int(self.frame_var.get())
            # 入力値を安全な範囲に補正
            val = max(0, min(val, self.total_frames - 1))
            self.current_frame = val
        except ValueError:
            # 数字以外が入力された場合は現在のフレームに戻す
            self.frame_var.set(str(self.current_frame))
        
        self.update_view()
        # 入力後にキャンバスへフォーカスを移す
        self.main_canvas.focus_set()

    def _read_img(self, p):
        if not os.path.exists(p): return np.zeros((720, 720, 3), dtype=np.uint8)
        img = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
        return img if img is not None else np.zeros((720, 720, 3), dtype=np.uint8)

    def update_view(self):
        if self.total_frames == 0: return
        self.main_canvas.delete("img_layer")
        self.main_canvas.create_rectangle(2, 7, 722, 727, fill='black', outline='gray', tags="img_layer")
        self.main_canvas.create_rectangle(729, 7, 1449, 727, fill='black', outline='', tags="img_layer")
        self.main_canvas.create_rectangle(1456, 7, 1856, 727, fill='black', outline='', tags="img_layer")

        # フォルダパスを表示 (横位置: Frame情報の1054、縦位置: バージョンの850)
        if self.target_dir:
            self.main_canvas.create_text(1054, 850, text=self.target_dir, fill="blue", font=("游ゴシック", 10), anchor=tk.N, tags="img_layer")

        if self.tk_meta:
            self.main_canvas.create_image(440, 760, image=self.tk_meta, anchor=tk.NW, tags="img_layer")
            self.main_canvas.create_rectangle(484, 852, 484+112, 852+16, fill="#f0f0f0", outline="#f0f0f0", tags="img_layer")
            self.main_canvas.create_text(60, 850, text=VERSION, fill="blue", font=("游ゴシック", 10), anchor=tk.NW, tags="img_layer")

        off_log = self.offset_var.get(); off_l2 = self.offset_live2_var.get()
        img1 = self._read_img(os.path.join(self.target_dir, "live1", f"live1_{self.current_frame:06d}.jpg"))
        l1 = (img1.shape[1]-720)//2 if img1.shape[1]>720 else 0
        img1_f = img1[0:720, l1:l1+720] if img1.shape[1]>720 else cv2.resize(img1, (720,720))

        idx2 = self.current_frame + off_l2
        if 0 <= idx2 < self.total_frames:
            img2 = self._read_img(os.path.join(self.target_dir, "live2", f"live2_{idx2:06d}.jpg"))
        else: img2 = np.zeros((720, 400, 3), dtype=np.uint8)
        l2 = (img2.shape[1]-400)//2 if img2.shape[1]>400 else 0
        img2_f = cv2.resize(img2[0:720, l2:l2+400] if img2.shape[1]>400 else img2, (400, 720))

        self.tk1 = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(img1_f, cv2.COLOR_BGR2RGB)))
        self.tk2 = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(img2_f, cv2.COLOR_BGR2RGB)))
        self.main_canvas.create_image(729, 7, image=self.tk1, anchor=tk.NW, tags="img_layer")
        self.main_canvas.create_image(1456, 7, image=self.tk2, anchor=tk.NW, tags="img_layer")

        # --- ログ描画とタイムスタンプ計算 ---
        idx_log = self.current_frame + off_log
        first_log_time = self.log_data[min(self.log_data.keys())]["time"] if self.log_data else 0
        last_log_time = self.log_data[max(self.log_data.keys())]["time"] if self.log_data else 0
        interval = 1000 / 30.0
        
        status = "OK"
        if 0 <= idx_log < self.total_log:
            entry = self.log_data.get(idx_log)
            if entry:
                abs_f = entry["time"]
                boxes = entry["boxes"]
            else:
                abs_f = first_log_time + idx_log * interval
                boxes = []
                status = "###"
        elif idx_log < 0:
            abs_f = first_log_time - (0 - idx_log) * interval
            boxes = []
            status = "###"
        else:
            abs_f = last_log_time + (idx_log - (self.total_log - 1)) * interval
            boxes = []
            status = "###"

        if boxes:
            for i, b in enumerate(boxes):
                self.draw_rectangles(self.main_canvas, b[0], b[1], b[2], b[3], b[4], b[5], i, abs_f, status)
        else:
            # ボックスがない場合でもタイムスタンプ（###）だけは表示する
            self.draw_rectangles(self.main_canvas, 0, 0, 0, 0, 0, 0, 0, abs_f, status)

        self.frame_var.set(str(self.current_frame))
        self.total_lbl.config(text=f" / {max(0, self.total_frames-1)}")

        # カット区間内なら[CUT]を赤文字表示（Viewing専用）
        if self.cut_flags and 0 <= self.current_frame < len(self.cut_flags) and self.cut_flags[self.current_frame]:
            self.cut_lbl.config(text="[CUT]")
        else:
            self.cut_lbl.config(text="")

        self.redraw_timeline()

    # =========================================================
    # V1.06 オリジナル仕様の完全復元 (Viewing用)
    # =========================================================
    def draw_rectangles(self, canvas, score, x, y, w, h, s, listno, abs_f, status):
        ox, oy = 2, 7
        color = "red" if score >= self.score_var.get() else "blue"
        
        # V1.06 仕様のメッセージ生成
        t1 = f"{score:.2f}"
        t2 = f"({int(x): >3},{int(y): >3})({int(w): >3},{int(h): >3}){int(s): >6}"
        t3 = f"{int(abs_f): >8}"
        
        if score > 0:
            x1, y1, x2, y2 = x, y, x + w, y + h
            # 矩形描画
            canvas.create_rectangle(x1+ox, y1+oy, x2+ox, y2+oy, outline=color, width=4, tags="img_layer")
            if self.show_live1_box_var.get():
                canvas.create_rectangle(x1+ox+729, y1+oy, x2+ox+729, y2+oy, outline=color, width=4, tags="img_layer")
            
            # 枠上のスコア表示 (V1.06 ロジックを完全移植)
            text_y = y1 if y1 > self.fontpitchy2 * 2 else y2 + self.fontpitchy2 + 6
            text_x = 8 if x1 < 8 else x1
            
            canvas.create_text(text_x+ox, text_y+oy - self.fontpitchy2, text=t1, fill='white', font=('Lucida Console', self.fontsize2), anchor="nw", tags="img_layer")
            if self.show_live1_box_var.get():
                canvas.create_text(text_x+ox+729, text_y+oy - self.fontpitchy2, text=t1, fill='white', font=('Lucida Console', self.fontsize2), anchor="nw", tags="img_layer")

        # 上部メッセージ表示 (V1.06 仕様: fontpitchy2(28px)を使用)
        if status == "OK" and score > 0:
            canvas.create_text(8+ox, listno * self.fontpitchy2 + 6 + oy, text=t1, fill='white', font=('Lucida Console', self.fontsize2), anchor="nw", tags="img_layer")
            canvas.create_text(8+ox + (self.fontpitchx2 * 5), listno * self.fontpitchy2 + 6 + oy, text=t2, fill='white', font=('Lucida Console', self.fontsize2), anchor="nw", tags="img_layer")
            canvas.create_text(577+ox, listno * self.fontpitchy2 + 6 + oy, text=t3, fill='white', font=('Lucida Console', self.fontsize2), anchor="nw", tags="img_layer")
        elif listno == 0: # ボックスがないか、最初の行としてタイムスタンプのみ表示
            canvas.create_text(577+ox, listno * self.fontpitchy2 + 6 + oy, text=t3, fill='white', font=('Lucida Console', self.fontsize2), anchor="nw", tags="img_layer")

    def redraw_timeline(self):
        self.timeline_canvas.delete("all")
        if self.total_frames == 0: return
        n = len(self.cut_flags) if self.cut_flags else self.total_frames
        self.timeline_canvas.create_rectangle(0, 0, self.timeline_width, 30, fill='#2ECC71', outline='')
        # フラグ配列からカット区間を走査して描画
        i = 0
        while i < len(self.cut_flags):
            if self.cut_flags[i]:
                start = i
                while i < len(self.cut_flags) and self.cut_flags[i]: i += 1
                x1 = (start / n) * self.timeline_width
                x2 = ((i - 1) / n) * self.timeline_width
                self.timeline_canvas.create_rectangle(x1, 0, x2, 30, fill='#E74C3C', outline='')
            else:
                i += 1
        # OUT仮設定中のプレビュー
        if self.current_out is not None:
            x1 = (self.current_out / n) * self.timeline_width
            x2 = (self.current_frame / n) * self.timeline_width
            # CUT ONなら暗い赤、OFFなら暗い黄緑
            p_color = '#C0392B' if self.cut_mode_var.get() else '#27AE60'
            self.timeline_canvas.create_rectangle(min(x1, x2), 0, max(x1, x2), 30, fill=p_color, outline='')
            # ボタン色も同期
            self.btn_start.config(bg=p_color, fg='white')
        else:
            # デフォルトに戻す
            self.btn_start.config(bg='SystemButtonFace', fg='black')
        cx = (self.current_frame / n) * self.timeline_width
        self.timeline_canvas.create_line(cx, 0, cx, 30, fill='black', width=2)

    def browse_folder(self, folder_path=None):
        f = folder_path if folder_path else filedialog.askdirectory()
        if f:
            f = os.path.normpath(f)
            print(f"DEBUG: Loading folder = {f}")
            self.target_dir = f
            self.offset_var.set(0); self.offset_live2_var.set(0)
            
            meta_p = os.path.join(f, "meta_info_panel.png")
            if os.path.exists(meta_p):
                img_arr = self._read_img(meta_p); self.tk_meta = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(img_arr, cv2.COLOR_BGR2RGB)))
            else: self.tk_meta = None
            
            csv_p = os.path.join(f, "sync_log.csv")
            
            # glob.glob の代わりに os.listdir を使用 (日本語パス対策)
            def count_jpgs(sub):
                p = os.path.join(f, sub)
                print(f"DEBUG: Checking sub-folder: {p}")
                if not os.path.isdir(p):
                    print(f"DEBUG: {sub} is NOT a directory or not found.")
                    return 0
                files = [name for name in os.listdir(p) if name.lower().endswith(".jpg")]
                print(f"DEBUG: {sub} contains {len(files)} jpgs.")
                if len(files) > 0:
                    print(f"DEBUG: Sample file: {files[0]}")
                return len(files)
            
            self.total_l1 = count_jpgs("live1")
            self.total_l2 = count_jpgs("live2")
            print(f"DEBUG: Found Live1={self.total_l1}, Live2={self.total_l2}")
            
            self.total_frames = self.total_l1
            self.log_data.clear()
            if os.path.exists(csv_p):
                # エンコーディングのフォールバック
                lines = []
                for enc in ['utf-8', 'cp932']:
                    try:
                        with open(csv_p, 'r', encoding=enc) as fs:
                            lines = fs.readlines()
                        print(f"DEBUG: sync_log.csv loaded with {enc}")
                        break
                    except: continue
                
                for line in lines:
                    row = line.strip().split(',')
                    if len(row) >= 2:
                        try:
                            bx = [[float(row[i]), int(row[i+1]), int(row[i+2]), int(row[i+3]), int(row[i+4]), int(row[i+5])] for i in range(2, len(row), 6) if i+5 < len(row)]
                            self.log_data[int(row[0])] = {"time": int(row[1]), "boxes": bx}
                        except: continue
            
            self.total_log = max(self.log_data.keys()) + 1 if self.log_data else 0
            self.current_frame = 0; self.cut_flags = [False] * self.total_frames; self.current_out = None
            self.load_config()
            self.update_view()
            
            if self.total_frames == 0:
                messagebox.showwarning("警告", f"画像が見つかりません。\nパスを確認してください:\n{f}")

    def toggle_play(self):
        self.is_playing = not self.is_playing
        self.btn_play.config(text="停止" if self.is_playing else "再生")
        if self.is_playing: self.last_time = time.time(); self._play_loop()
        else: self.fps_var.set("[ 0.0 fps ]")

    def _play_loop(self):
        if self.is_playing and self.current_frame < self.total_frames - 1:
            now = time.time(); delta = now - self.last_time
            if delta > 0: self.fps_var.set(f"[ {1.0/delta:4.1f} fps ]")
            self.last_time = now; self.current_frame += 1; self.update_view(); self.root.after(33, self._play_loop)
        else: self.is_playing = False; self.btn_play.config(text="再生"); self.fps_var.set("[ 0.0 fps ]")

    def step_forward(self):
        if self.current_frame < self.total_frames-1: self.current_frame += 1; self.update_view()
    def step_backward(self):
        if self.current_frame > 0: self.current_frame -= 1; self.update_view()
    def _on_timeline_click(self, event):
        if self.total_frames > 0: self.current_frame = int((max(0, min(event.x, self.timeline_width)) / self.timeline_width) * self.total_frames); self.update_view()
    def _on_offset_change(self, v): 
        if not self.is_playing: self.update_view()
    def adjust_offset(self, mode, delta):
        v = self.offset_var if mode == "log" else self.offset_live2_var
        v.set(max(-9999, min(9999, v.get() + delta))); self.update_view()
    def mark_start(self):
        if self.current_out is not None:
            self.current_out = None
        else:
            self.current_out = self.current_frame
        self.redraw_timeline()
    def mark_end(self):
        if self.current_out is not None and self.cut_flags:
            s, e = min(self.current_out, self.current_frame), max(self.current_out, self.current_frame)
            fill_val = self.cut_mode_var.get() # True(CUT) か False(解除)
            for i in range(s, min(e + 1, len(self.cut_flags))): self.cut_flags[i] = fill_val
            self.current_out = None; self.update_view()

    def save_config(self):
        if not self.target_dir: return
        ini_p = os.path.join(self.target_dir, "viewer.ini")
        # CUT情報を範囲リストに変換
        cuts = []
        i = 0
        while i < len(self.cut_flags):
            if self.cut_flags[i]:
                s = i
                while i < len(self.cut_flags) and self.cut_flags[i]: i += 1
                cuts.extend([s, i - 1])
            else: i += 1
        
        try:
            with open(ini_p, 'w', encoding='cp932') as f:
                f.write(f"SCORE_THRESHOLD={self.score_var.get():.2f}\n")
                f.write(f"ANALYSIS_PHASE={self.offset_var.get()}\n")
                f.write(f"LIVE2_PHASE={self.offset_live2_var.get()}\n")
                f.write(f"SHOW_LIVE1_BOX={'ON' if self.show_live1_box_var.get() else 'OFF'}\n")
                f.write(f"CUT_RANGES={','.join(map(str, cuts))}\n")
            messagebox.showinfo("成功", f"設定を保存しました:\n{ini_p}")
        except Exception as e:
            messagebox.showerror("エラー", f"設定の保存に失敗しました: {e}")

    def load_config(self):
        ini_p = os.path.join(self.target_dir, "viewer.ini")
        if not os.path.exists(ini_p): return
        try:
            with open(ini_p, 'r', encoding='cp932') as f:
                for line in f:
                    if '=' not in line: continue
                    k, v = line.strip().split('=', 1)
                    if k == "SCORE_THRESHOLD": self.score_var.set(float(v))
                    elif k == "ANALYSIS_PHASE": self.offset_var.set(int(v))
                    elif k == "LIVE2_PHASE": self.offset_live2_var.set(int(v))
                    elif k == "SHOW_LIVE1_BOX": self.show_live1_box_var.set(v == "ON")
                    elif k == "CUT_RANGES" and v:
                        r = list(map(int, v.split(',')))
                        for j in range(0, len(r), 2):
                            s, e = r[j], r[j+1]
                            for idx in range(s, min(e + 1, len(self.cut_flags))):
                                self.cut_flags[idx] = True
        except Exception as e:
            print(f"Config load error: {e}")

    # =========================================================
    # エクスポート機能
    # =========================================================
    def on_export_click(self):
        if self.total_frames == 0: return
        if self.is_playing: self.toggle_play(); self.root.update_idletasks()
        
        base_dir = os.path.basename(os.path.normpath(self.target_dir))
        default_path = os.path.join(os.path.dirname(os.path.normpath(self.target_dir)), base_dir.replace("_ViewReady","")+"_Edit")
        
        dialog = tk.Toplevel(self.root); dialog.title("エクスポート設定"); dialog.geometry("600x120"); dialog.grab_set()
        tk.Label(dialog, text="保存先フォルダ:").place(x=10, y=15)
        path_var = tk.StringVar(value=default_path)
        tk.Entry(dialog, textvariable=path_var, width=80).place(x=10, y=40)
        
        def browse():
            d = filedialog.askdirectory(title="保存先選択", initialdir=os.path.dirname(path_var.get()))
            if d: path_var.set(os.path.normpath(d))
        tk.Button(dialog, text="参照...", width=8, command=browse).place(x=510, y=36)
        
        def start():
            p = path_var.get().strip()
            if p: dialog.destroy(); self._run_export(p)
        tk.Button(dialog, text="実行", width=12, bg="#E74C3C", fg="white", command=start).place(x=250, y=80)
    
    def start_batch_export(self):
        if self.total_frames == 0: return
        if self.is_playing: self.toggle_play(); self.root.update_idletasks()
        
        base_dir = os.path.basename(os.path.normpath(self.target_dir))
        default_path = os.path.join(os.path.dirname(os.path.normpath(self.target_dir)), base_dir.replace("_ViewReady","")+"_Edit")
        self._run_export(default_path)

    def _run_export(self, export_path):
        self.btn_export.config(state=tk.DISABLED); self.is_exporting = True
        
        self.progress_win = tk.Toplevel(self.root); self.progress_win.title("出力中"); self.progress_win.geometry("400x150")
        self.progress_win.transient(self.root); self.progress_win.grab_set()
        
        def on_cancel():
            self.is_exporting = False; self.progress_win.destroy(); self.btn_export.config(state=tk.NORMAL)
        self.progress_win.protocol("WM_DELETE_WINDOW", on_cancel)
        
        self.p_lbl_phase = tk.Label(self.progress_win, text="動画(mp4)とデータを構築中...", font=("bold"))
        self.p_lbl_phase.pack(pady=10)
        self.p_bar = ttk.Progressbar(self.progress_win, length=300, mode='determinate'); self.p_bar.pack(padx=20)
        self.p_lbl_status = tk.Label(self.progress_win, text="準備中...")
        self.p_lbl_status.pack(pady=5)
        tk.Button(self.progress_win, text="キャンセル", command=on_cancel).pack(pady=5)

        show_live1_box = self.show_live1_box_var.get()
        threading.Thread(target=self._export_thread, args=(export_path, show_live1_box), daemon=True).start()

    def _export_thread(self, export_path, show_live1_box):
        try:
            off_log = self.offset_var.get(); off_l2 = self.offset_live2_var.get()
            max_j = max(self.total_l1, self.total_l2 - off_l2, self.total_log - off_log)
            
            # cut_flagsのサイズがmax_jより小さい場合は拡張
            if len(self.cut_flags) < max_j:
                self.cut_flags.extend([False] * (max_j - len(self.cut_flags)))
            valid_j_list = [j for j in range(max_j) if not self.cut_flags[j]]
            if not valid_j_list: return
            
            os.makedirs(export_path, exist_ok=True); prefix = os.path.basename(os.path.normpath(export_path))
            
            mp4_cap = os.path.join(export_path, f"{prefix}_screen_capture.mp4")
            mp4_l1 = os.path.join(export_path, f"{prefix}_vlc_record_live1.mp4")
            mp4_l2 = os.path.join(export_path, f"{prefix}_vlc_record_live2.mp4")
            
            has_unicode = any(ord(c) > 127 for c in export_path)
            if has_unicode:
                tmp_dir = tempfile.gettempdir()
                tmp_cap = os.path.join(tmp_dir, f"tmp_{time.time()}_cap.mp4")
                tmp_l1 = os.path.join(tmp_dir, f"tmp_{time.time()}_l1.mp4")
                tmp_l2 = os.path.join(tmp_dir, f"tmp_{time.time()}_l2.mp4")
            else:
                tmp_cap, tmp_l1, tmp_l2 = mp4_cap, mp4_l1, mp4_l2
    
            log_p = os.path.join(export_path, f"{prefix}_head.log")
            h2_p = os.path.join(export_path, f"{prefix}_head2.csv")
    
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer_cap = cv2.VideoWriter(tmp_cap, fourcc, 30.0, (1866, 880))
            writer_l1 = cv2.VideoWriter(tmp_l1, fourcc, 30.0, (1280, 720))
            writer_l2 = cv2.VideoWriter(tmp_l2, fourcc, 30.0, (720, 720))
    
            first_log_time = self.log_data[min(self.log_data.keys())]["time"] if self.log_data else 0
            last_log_time = self.log_data[max(self.log_data.keys())]["time"] if self.log_data else 0
            interval = 1000 / 30.0
            
            try: font_lucon = ImageFont.truetype("lucon.ttf", 26)
            except: font_lucon = ImageFont.load_default()
            try: font_gothic_bold = ImageFont.truetype("msgothic.ttc", 14)
            except: font_gothic_bold = ImageFont.load_default()
            try: font_yu_meta = ImageFont.truetype("YuGothM.ttc", 14)
            except:
                try: font_yu_meta = ImageFont.truetype("YuGothR.ttc", 14)
                except: font_yu_meta = font_gothic_bold
    
            with open(log_p, 'w', encoding='cp932') as f_log, open(h2_p, 'w', encoding='cp932', newline='') as f_h2:
                h2_w = csv.writer(f_h2)
                
                for count, j in enumerate(valid_j_list):
                    if not self.is_exporting: break
                    
                    self.root.after(0, lambda c=count+1, t=len(valid_j_list): (
                        self.p_bar.configure(value=(c/t)*100), 
                        self.p_lbl_status.configure(text=f"処理中: {c}/{t}")
                    ))
                    
                    # Live1: 基準
                    if 0 <= j < self.total_l1:
                        img1 = self._read_img(os.path.join(self.target_dir, "live1", f"live1_{j:06d}.jpg"))
                        l1 = (img1.shape[1]-720)//2 if img1.shape[1]>720 else 0
                        img1_f = img1[0:720, l1:l1+720] if img1.shape[1]>720 else cv2.resize(img1, (720,720))
                    else:
                        img1 = np.zeros((720, 1280, 3), dtype=np.uint8)
                        l1 = 0
                        img1_f = np.zeros((720, 720, 3), dtype=np.uint8)
                    img1_for_vid = cv2.resize(img1, (1280, 720)) if img1.shape[:2] != (720, 1280) else img1.copy()

                    # Live2: 位相調整
                    idx2 = j + off_l2
                    if 0 <= idx2 < self.total_l2:
                        img2 = self._read_img(os.path.join(self.target_dir, "live2", f"live2_{idx2:06d}.jpg"))
                        l2 = (img2.shape[1]-400)//2 if img2.shape[1]>400 else 0
                        img2_f = cv2.resize(img2[0:720, l2:l2+400] if img2.shape[1]>400 else img2, (400, 720))
                    else: 
                        img2 = np.zeros((720, 720, 3), dtype=np.uint8)
                        img2_f = np.zeros((720, 400, 3), dtype=np.uint8)
                    img2_for_vid = cv2.resize(img2, (720, 720)) if img2.shape[:2] != (720, 720) else img2.copy()

                    pil_img = Image.new('RGB', (1866, 880), '#f0f0f0')
                    draw = ImageDraw.Draw(pil_img)
                    
                    draw.rectangle([2, 7, 722, 727], fill='black', outline='gray')
                    draw.rectangle([729, 7, 1449, 727], fill='black')
                    draw.rectangle([1456, 7, 1856, 727], fill='black')
                    pil_img.paste(Image.fromarray(cv2.cvtColor(img1_f, cv2.COLOR_BGR2RGB)), (729, 7))
                    pil_img.paste(Image.fromarray(cv2.cvtColor(img2_f, cv2.COLOR_BGR2RGB)), (1456, 7))
                    
                    meta_p = os.path.join(self.target_dir, "meta_info_panel.png")
                    if os.path.exists(meta_p):
                        m_img = self._read_img(meta_p)
                        if m_img.shape[0]>0: pil_img.paste(Image.fromarray(cv2.cvtColor(m_img, cv2.COLOR_BGR2RGB)), (440, 760))
                    
                    draw.text((182, 745), f"解析位相：{off_log}", fill='black', font=font_gothic_bold, anchor="mt")
                    draw.text((1054, 745), f"Frame(30fps): {j} / {max_j-1}", fill='black', font=font_gothic_bold, anchor="mt")
                    draw.text((1656, 745), f"LIVE2位相：{off_l2}", fill='black', font=font_gothic_bold, anchor="mt")
                    draw.rectangle([484, 852, 596, 868], fill="#f0f0f0")
                    draw.text((1054, 850), self.target_dir, fill="blue", font=font_yu_meta, anchor="mt")
                    draw.text((60, 830), f"SCORE閾値={self.score_var.get():.2f}", fill="blue", font=font_yu_meta)
                    draw.text((60, 850), VERSION, fill="blue", font=font_yu_meta)

                    ia = j + off_log
                    boxes = []
                    status = "OK"
                    
                    if 0 <= ia < self.total_log:
                        entry = self.log_data.get(ia)
                        if entry:
                            abs_f = entry["time"]
                            boxes = entry["boxes"]
                        else:
                            abs_f = first_log_time + ia * interval
                            status = "###"
                    elif ia < 0:
                        abs_f = first_log_time - (0 - ia) * interval
                        status = "###"
                    else:
                        abs_f = last_log_time + (ia - (self.total_log - 1)) * interval
                        status = "###"

                    # head.log: 全フレームで「時刻,###」を出力し、検出物体があれば @@@ 行を追加
                    f_log.write(f"{int(abs_f)},###\n")
                    if status == "OK":
                        for b in boxes:
                            sc, x, y, w, h, s = b
                            f_log.write(f"{int(abs_f)},@@@ OK class:0, score:{sc:.2f}, x, y, w, h, s = {int(x)}, {int(y)}, {int(w)}, {int(h)}, {int(s)}\n")
                    # head2.csv: 各フレームの情報を出力
                    h2_w.writerow(["#", "Frame", int(abs_f), "Count", len(boxes)])
                    for bi, b in enumerate(boxes):
                        sc, x, y, w, h, s = b
                        x2c, y2c = int(x + w), int(y + h)
                        h2_w.writerow(["#", "", "", "", "", f"[{bi}]",
                                       "x1", int(x), "y1", int(y),
                                       "x2", x2c, "y2", y2c,
                                       "score", f"{sc:.6f}", "class_num", 0])



                    ox, oy = 2, 7
                    if status == "OK":
                        # Live1 動画 (img1_for_vid) へのスコア焼き込みのため PIL オブジェクトを用意
                        pil_l1 = None
                        draw_l1 = None
                        if show_live1_box and 0 <= j < self.total_l1:
                            pil_l1 = Image.fromarray(cv2.cvtColor(img1_for_vid, cv2.COLOR_BGR2RGB))
                            draw_l1 = ImageDraw.Draw(pil_l1)

                        for ln, b in enumerate(boxes):
                            sc, x, y, w, h, s = b
                            x1, y1, x2, y2 = int(x), int(y), int(x + w), int(y + h)
                            color = "red" if sc >= self.score_var.get() else "blue"
                            
                            # 枠上のスコア表示の動的配置ロジック
                            text_y = y1 if y1 > self.fontpitchy2 * 2 else y2 + self.fontpitchy2 + 6
                            text_x = 8 if x1 < 8 else x1
                            
                            draw.rectangle([x1+ox, y1+oy, x2+ox, y2+oy], outline=color, width=4)
                            # 枠上のスコア表示追加 (V1.06風) - 動的配置対応
                            draw.text((text_x+ox, text_y+oy - 28), f"{sc:.2f}", fill='white', font=font_lucon)

                            t1 = f"{sc:.2f}"; t2 = f"({int(x): >3},{int(y): >3})({int(w): >3},{int(h): >3}){int(s): >6}"; t3 = f"{int(abs_f): >8}"
                            draw.text((8+ox, ln * self.fontpitchy2 + 6 + oy), t1, fill='white', font=font_lucon)
                            draw.text((8+ox + (self.fontpitchx2 * 5), ln * self.fontpitchy2 + 6 + oy), t2, fill='white', font=font_lucon)
                            draw.text((577+ox, ln * self.fontpitchy2 + 6 + oy), t3, fill='white', font=font_lucon)
                            
                            if draw_l1 is not None:
                                draw_l1.rectangle([x1 + l1, y1, x2 + l1, y2], outline=color, width=4)
                                text_x_l1 = 8 + l1 if x1 + l1 < 8 + l1 else x1 + l1
                                # Live1上のスコア表示追加 (V1.06風) - 動的配置対応
                                draw_l1.text((text_x_l1, text_y - 28), f"{sc:.2f}", fill='white', font=font_lucon)
                                
                                # Capture画像内の Live1 枠上スコア追加 (V1.06風) - 動的配置対応
                                draw.rectangle([x1 + 729 + ox, y1 + oy, x2 + 729 + ox, y2 + oy], outline=color, width=4)
                                draw.text((text_x + 729 + ox, text_y + oy - 28), f"{sc:.2f}", fill='white', font=font_lucon)

                        if pil_l1 is not None:
                            img1_for_vid = cv2.cvtColor(np.array(pil_l1), cv2.COLOR_RGB2BGR)

                        if not boxes:
                            draw.text((577+ox, 6 + oy), f"{int(abs_f): >8}", fill='white', font=font_lucon)
                    else:
                        draw.text((577+ox, 6 + oy), f"{int(abs_f): >8}", fill='white', font=font_lucon)

                    writer_cap.write(cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR))
                    writer_l1.write(img1_for_vid)
                    writer_l2.write(img2_for_vid)

            writer_cap.release(); writer_l1.release(); writer_l2.release()
            
            # フェーズ2: 一時ファイルを本来の場所に移動（日本語パス対応）
            if has_unicode:
                move_targets = [(tmp_cap, mp4_cap, "screen_capture"), (tmp_l1, mp4_l1, "live1"), (tmp_l2, mp4_l2, "live2")]
                for idx, (src, dst, label) in enumerate(move_targets, 1):
                    self.root.after(0, lambda i=idx, lb=label: (
                        self.p_lbl_phase.config(text=f"動画ファイルを移動中... ({i}/3)  [{lb}]"),
                        self.p_bar.configure(mode='determinate', value=int((i-1)/3*100))
                    ))
                    if os.path.exists(src):
                        if os.path.exists(dst): os.remove(dst)
                        shutil.move(src, dst)
                self.root.after(0, lambda: self.p_bar.configure(value=100))
            
            if not self.is_exporting: return

            # フェーズ3: 解析結果の集計（indeterminateアニメーションに切り替え）
            self.root.after(0, lambda: (
                self.p_lbl_phase.config(text="解析結果を集計中..."),
                self.p_lbl_status.config(text="output.csv を生成しています"),
                self.p_bar.configure(mode='indeterminate'),
                self.p_bar.start(15)
            ))
            summary_error = None
            try:
                run_summarize_log(export_path, self.score_var.get(), prefix)
            except Exception as summ_e:
                summary_error = str(summ_e)
            self.root.after(0, lambda: self.p_bar.stop())

            def finish_export():
                if hasattr(self, 'progress_win') and self.progress_win.winfo_exists():
                    self.progress_win.destroy()
                if summary_error:
                    messagebox.showwarning("集計エラー", f"動画の出力は完了しましたが、output.csvの作成に失敗しました:\n{summary_error}")
                else:
                    if self.batch_mode:
                        self.root.after(2000, self.root.destroy)
                    else:
                        messagebox.showinfo("完了", f"エクスポートが完了しました:\n{export_path}")
                self.btn_export.config(state=tk.NORMAL)

            self.root.after(0, finish_export)
            
        except Exception as e:
            self.root.after(0, lambda: (
                self.progress_win.destroy() if hasattr(self, 'progress_win') and self.progress_win.winfo_exists() else None,
                messagebox.showerror("エラー", str(e)),
                self.btn_export.config(state=tk.NORMAL)
            ))

if __name__ == "__main__":
    root = tk.Tk()
    app = FolloasViewerApp(root)
    root.mainloop()