import os
import cv2  # type: ignore
import csv
import re
import numpy as np  # type: ignore
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
from typing import Optional
import tempfile
import shutil
from contextlib import contextmanager
import sys

VERSION = "V1.09 2026/05/03"

class FolloasConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Folloas データコンバータ ({VERSION})")
        self.root.geometry("500x220")
        self.root.resizable(False, False)

        self.target_dir = tk.StringVar()
        self.is_running = False
        self.cancel_requested = False
        self.batch_mode = False

        # 変数の事前宣言（Pyre2等のType Checkerによるmissing-attribute警告対策）
        self.status_var: tk.StringVar
        self.progress_var: tk.DoubleVar
        self.progress_bar: ttk.Progressbar
        self.btn_start: tk.Button
        self.btn_cancel: tk.Button

        self._setup_ui()

        # 引数チェック
        if len(sys.argv) > 1:
            # 引数を取得し、前後の空白除去とパスの正規化を行う
            input_path = os.path.normpath(os.path.abspath(sys.argv[1].strip()))
            
            if os.path.isdir(input_path):
                self.target_dir.set(input_path)
                self.batch_mode = True
                # GUIが完全に構築されるのを少し待ってから開始
                self.root.after(500, self.start_conversion)
            else:
                print(f"Error: Directory not found - {input_path}")
                self.root.after(100, self.root.destroy)

    def _setup_ui(self):
        # フォルダ選択セクション
        frame_top = tk.Frame(self.root, pady=10, padx=10)
        frame_top.pack(fill=tk.X)
        tk.Label(frame_top, text="処理対象フォルダ:").pack(anchor=tk.W)
        
        entry_frame = tk.Frame(frame_top)
        entry_frame.pack(fill=tk.X, pady=5)
        tk.Entry(entry_frame, textvariable=self.target_dir, state='readonly').pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(entry_frame, text="参照", command=self.browse_folder).pack(side=tk.RIGHT, padx=5)

        # プログレスセクション
        frame_mid = tk.Frame(self.root, pady=10, padx=10)
        frame_mid.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="待機中...")
        tk.Label(frame_mid, textvariable=self.status_var).pack(anchor=tk.W)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(frame_mid, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)

        # 制御ボタンセクション
        frame_bottom = tk.Frame(self.root, pady=10)
        frame_bottom.pack()
        self.btn_start = tk.Button(frame_bottom, text="変換開始", command=self.start_conversion, width=15, bg="lightblue")
        self.btn_start.pack(side=tk.LEFT, padx=10)
        self.btn_cancel = tk.Button(frame_bottom, text="キャンセル", command=self.cancel_conversion, width=15, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=10)

    def browse_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.target_dir.set(os.path.normpath(folder_selected))

    # --- UI更新用ヘルパー (メインスレッドで実行) ---
    def _update_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def _update_progress(self, value):
        self.root.after(0, lambda: self.progress_var.set(value))

    def _show_message(self, type, title, message):
        if type == "error":
            self.root.after(0, lambda: messagebox.showerror(title, message))
        elif type == "warning":
            self.root.after(0, lambda: messagebox.showwarning(title, message))
        else:
            self.root.after(0, lambda: messagebox.showinfo(title, message))

    @contextmanager
    def _video_capture_context(self, video_path):
        """OpenCVの日本語パス問題を回避するためのコンテキストマネージャ"""
        temp_file = None
        cap = None
        try:
            # パスに日本語が含まれているかチェック
            has_unicode = any(ord(c) > 127 for c in video_path)
            if has_unicode and os.path.exists(video_path):
                suffix = os.path.splitext(video_path)[1]
                fd, temp_path = tempfile.mkstemp(suffix=suffix)
                os.close(fd)
                shutil.copy2(video_path, temp_path)
                temp_file = temp_path
                cap = cv2.VideoCapture(temp_path)
            else:
                cap = cv2.VideoCapture(video_path)
            yield cap
        finally:
            if cap is not None:
                cap.release()
            if temp_file is not None and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

    def cancel_conversion(self):
        if self.is_running:
            self.cancel_requested = True
            self.btn_cancel.config(state=tk.DISABLED)
            self.status_var.set("キャンセル処理中... お待ちください")

    def start_conversion(self):
        input_dir = self.target_dir.get()
        if not input_dir or not os.path.isdir(input_dir):
            messagebox.showerror("エラー", "有効なフォルダを選択してください。")
            return

        self.is_running = True
        self.cancel_requested = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL)
        self.progress_var.set(0)

        # バックグラウンドスレッドで処理を開始
        threading.Thread(target=self.process_folder, args=(input_dir,), daemon=True).start()

    def process_folder(self, input_dir):
        try:
            input_dir = os.path.normpath(input_dir)
            folder_name = os.path.basename(input_dir)
            output_dir = f"{input_dir}_ViewReady"
            os.makedirs(output_dir, exist_ok=True)

            # サブフォルダの作成
            live1_dir = os.path.join(output_dir, "live1")
            live2_dir = os.path.join(output_dir, "live2")
            os.makedirs(live1_dir, exist_ok=True)
            os.makedirs(live2_dir, exist_ok=True)

            # 各種ファイルパスの推定
            live1_path = os.path.join(input_dir, f"{folder_name}_vlc_record_live1.ts")
            live2_path = os.path.join(input_dir, f"{folder_name}_vlc_record_live2.ts")
            screen_path = os.path.join(input_dir, f"{folder_name}_screen_capture.mkv")
            log_path = os.path.join(input_dir, f"{folder_name}_head.log")

            # 1. Live1 (30fps) の展開を基準とする
            self._update_status("1/4: Live1 (30fps基準) の静止画抽出中...")
            total_frames_30fps = self._extract_frames(live1_path, live1_dir, "live1", 30, 30)
            if self.cancel_requested:
                return self._handle_cancel()

            # 2. Live2 (25fps -> 30fps) の展開
            self._update_status("2/4: Live2 (25fps -> 30fps) の同期変換中...")
            self._extract_frames(live2_path, live2_dir, "live2", 25, 30, total_frames_30fps)
            if self.cancel_requested:
                return self._handle_cancel()

            # 3. ScreenCapture からメタ情報画像の切り抜き
            self._update_status("3/4: Screenからメタ情報画像を抽出中...")
            self._extract_meta_only(screen_path, output_dir)
            if self.cancel_requested:
                return self._handle_cancel()

            # 4. ログの同期
            self._update_status("4/4: ログのデータクレンジングとタイムライン同期中...")
            self._sync_log(log_path, output_dir, total_frames_30fps)
            if self.cancel_requested:
                return self._handle_cancel()

            # 完了処理
            self._update_status("変換完了！ VIEWERで読み込めます。")
            self._update_progress(100)
            self._show_message("info", "完了", f"変換が正常に完了しました。\n作業フォルダ: {output_dir}")

        except Exception as e:
            self._show_message("error", "エラー", f"処理中にエラーが発生しました:\n{str(e)}")
            self._update_status("エラーが発生しました")
        finally:
            self.root.after(0, self._reset_ui)

    def _extract_frames(self, video_path, output_dir, prefix, src_fps, target_fps, target_total_frames=None):
        if not os.path.exists(video_path):
            self._show_message("warning", "警告", f"{os.path.basename(video_path)} が見つかりません。")
            return target_total_frames if target_total_frames is not None else 0

        with self._video_capture_context(video_path) as cap:
            if cap is None or not cap.isOpened():
                self._show_message("error", "エラー", f"動画ファイルを開けませんでした: {os.path.basename(video_path)}")
                return target_total_frames if target_total_frames is not None else 0

            src_total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            total_frames: int = src_total_frames if target_total_frames is None else target_total_frames

            ratio = src_fps / target_fps
            current_src_idx: int = -1
            frame = None

            for target_idx in range(total_frames):
                if self.cancel_requested:
                    break

                calc_src_idx = int(round(target_idx * ratio))
                calc_src_idx = min(calc_src_idx, src_total_frames - 1)

                while current_src_idx < calc_src_idx:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    current_src_idx = current_src_idx + 1  # type: ignore

                if frame is not None:
                    out_path = os.path.join(output_dir, f"{prefix}_{target_idx:06d}.jpg")
                    # 高画質JPG & 日本語パス対応の保存
                    result, encimg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                    if result:
                        with open(out_path, 'wb') as f:
                            encimg.tofile(f)

                if target_idx % 50 == 0:
                    self._update_progress((target_idx / total_frames) * 100)  # type: ignore

        return total_frames

    def _extract_meta_only(self, video_path, output_dir):
        """ScreenCaptureから絶対座標でパラメータ部分だけを切り抜いて保存する"""
        self._update_progress(50)

        if not os.path.exists(video_path):
            self._show_message("warning", "警告", f"{os.path.basename(video_path)} が見つかりません。")
            self._update_progress(100)
            return

        with self._video_capture_context(video_path) as cap:
            if cap is None or not cap.isOpened():
                self._show_message("error", "エラー", f"動画ファイルを開けませんでした: {os.path.basename(video_path)}")
                self._update_progress(100)
                return

            # ブラックアウト対策として、15フレーム（約1秒分）読み飛ばす
            ret = False
            frame = None
            for _ in range(15):
                ret, frame = cap.read()
                if not ret:
                    break

            if ret and frame is not None:
                # ユーザー指定の絶対座標で切り抜き [y1:y2, x1:x2]
                cropped_meta = frame[760:875, 440:715]
                meta_path = os.path.join(output_dir, "meta_info_panel.png")

                # 日本語パス対応のPNG保存
                result, encimg = cv2.imencode('.png', cropped_meta)
                if result:
                    with open(meta_path, 'wb') as f:
                        encimg.tofile(f)

        self._update_progress(100)

    def _sync_log(self, log_path: str, output_dir: str, total_frames_30fps: int):
        if not os.path.exists(log_path):
            return

        # --- ① ログの読み込みとフレーム単位のグルーピング ---
        grouped_logs: list[tuple[int, str]] = []
        current_time: Optional[int] = None
        current_vals: list[str] = []
        first_detection_found = False

        # ### (空フレームマーカー) を見つける正規表現
        pattern_empty: re.Pattern = re.compile(r"^(\d+),###")
        # @@@ OK class (検出結果) から 6つの数値を抽出する正規表現
        pattern_det: re.Pattern = re.compile(r"^(\d+),.*score:\s*([0-9.]+).*?=\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)")

        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                # 1. 空のフレームマーカー (###) の検出
                match_empty = pattern_empty.match(line)  # type: ignore
                if match_empty:
                    # 前のグループが完成していればリストに追加
                    if current_time is not None:
                        grouped_logs.append((current_time, ",".join(current_vals)))  # type: ignore

                    # 新しいフレームの開始
                    current_time = int(match_empty.group(1))
                    current_vals = []
                    first_detection_found = False
                    continue

                # 2. 認識結果 (@@@) の検出
                match_det = pattern_det.search(line)  # type: ignore
                if match_det:
                    # 万が一 ### より先に @@@ が来た場合の安全処理
                    if current_time is None:
                        current_time = int(match_det.group(1))

                    timestamp_ms = int(match_det.group(1))
                    # 抽出した数値をカンマ区切りで整形: score, x, y, w, h, s
                    vals = f"{match_det.group(2)},{match_det.group(3)},{match_det.group(4)},{match_det.group(5)},{match_det.group(6)},{match_det.group(7)}"

                    if not first_detection_found:
                        # フレーム内で最初の検出なら、その時間を代表OS時間に上書きする
                        current_time = timestamp_ms
                        first_detection_found = True

                    current_vals.append(vals)

        # 最後の行が終わったあとの残りを追加
        if current_time is not None:
            grouped_logs.append((current_time, ",".join(current_vals)))  # type: ignore

        if not grouped_logs:
            return

        # --- ② 30fpsタイムラインへのマッピング (Nearest) ---
        base_time = grouped_logs[0][0]
        sync_log_path = os.path.join(output_dir, "sync_log.csv")

        with open(sync_log_path, 'w', encoding='utf-8', newline='') as out_f:
            writer = csv.writer(out_f)

            log_idx: int = 0

            for frame_idx in range(total_frames_30fps):
                frame_time_ms = base_time + (frame_idx * (1000.0 / 30.0))

                # 最も近いロググループを探す
                while log_idx < len(grouped_logs) - 1:
                    current_grp_time, _ = grouped_logs[log_idx]  # type: ignore
                    next_grp_time, _ = grouped_logs[log_idx + 1]  # type: ignore

                    diff_current = abs(frame_time_ms - current_grp_time)
                    diff_next = abs(frame_time_ms - next_grp_time)

                    if diff_next <= diff_current:
                        log_idx += 1  # type: ignore
                    else:
                        break

                current_grp_time, current_group_vals = grouped_logs[log_idx]

                # 100ms以上ログが全く無い場合は「処理落ち」とみなす
                if abs(frame_time_ms - current_grp_time) > 100:
                    # 認識データはコピーせず空にする
                    selected_vals = ""
                    # タイムスタンプ重複を防ぐため、計算上のフレーム時間を採用して時間を進める
                    selected_time = int(frame_time_ms)
                else:
                    # 正常にマッチした場合（空の場合も含む）
                    selected_vals = current_group_vals
                    selected_time = current_grp_time

                # ご指示通りのフラットな数値CSVフォーマットで書き出し
                if selected_vals:
                    # 例: [1741, 132401, 0.25, 223, 363, 207, 222, 45954, ...]
                    row = [frame_idx, selected_time] + selected_vals.split(',')
                else:
                    # 認識がゼロの場合はフレーム番号と時間だけ出力
                    row = [frame_idx, selected_time]

                writer.writerow(row)

                if frame_idx % 100 == 0:
                    self._update_progress((frame_idx / total_frames_30fps) * 100)  # type: ignore

    def _handle_cancel(self):
        self._update_status("キャンセルされました")
        self._update_progress(0)
        if self.batch_mode:
            self.root.after(1000, self.root.destroy)
        else:
            self._show_message("warning", "キャンセル", "変換処理が中断されました。")
        self.root.after(0, self._reset_ui)

    def _reset_ui(self):
        self.is_running = False
        if self.batch_mode:
            self.root.after(2000, self.root.destroy)
        else:
            self.btn_start.config(state=tk.NORMAL)
            self.btn_cancel.config(state=tk.DISABLED)
            self._show_message("info", "完了", "変換処理がすべて完了しました！")

if __name__ == "__main__":
    root = tk.Tk()
    app = FolloasConverterApp(root)
    root.mainloop()