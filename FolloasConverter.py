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
import json
import sys
import subprocess
import ctypes

VERSION = "V1.33 2026/05/16"

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
            self.batch_mode = True
            # 引数を取得し、前後の空白除去とパスの正規化を行う
            input_path = os.path.normpath(os.path.abspath(sys.argv[1].strip()))
            
            # デバッグ用: 受け取ったパスを表示
            print(f"DEBUG: Received path = {input_path}")
            
            if os.path.isdir(input_path):
                print(f"DEBUG: Directory confirmed.")
                self.target_dir.set(input_path)
                # GUIが完全に構築されるのを少し待ってから開始
                self.root.after(500, self.start_conversion)
            else:
                self._show_message("error", "起動エラー", f"Error: Directory not found or invalid path - {input_path}")
                self.root.after(100, self.root.destroy)
                return

        # IME無効化 (Windowsのみ)
        if sys.platform == "win32":
            self.root.after(200, self._disable_ime)

    def _disable_ime(self):
        """WindowsのIMEを無効化する"""
        try:
            # 自身のウィンドウハンドルを取得してIMEを関連付け解除
            hwnd = self.root.winfo_id()
            ctypes.windll.imm32.ImmAssociateContext(hwnd, 0)
        except:
            pass

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
        if self.batch_mode:
            # バッチモード時はポップアップを出さず、標準エラー出力に表示する
            print(f"\n[{type.upper()}] {title}: {message}", file=sys.stderr)
            return

        if type == "error":
            self.root.after(0, lambda: messagebox.showerror(title, message))
        elif type == "warning":
            self.root.after(0, lambda: messagebox.showwarning(title, message))
        else:
            self.root.after(0, lambda: messagebox.showinfo(title, message))

    def _get_video_info(self, video_path):
        """ffprobeを使用して動画の情報を取得する"""
        try:
            video_path = os.path.abspath(video_path)
            v_dir = os.path.dirname(video_path)
            v_name = os.path.basename(video_path)

            # 漢字パス対策: 作業ディレクトリを動画の場所に移動して実行
            cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=nb_frames,duration,avg_frame_rate",
                   "-of", "json", v_name]
            
            # Windowsで新しいコンソールウィンドウを開かないように設定
            creationflags = 0
            if sys.platform == "win32":
                creationflags = 0x08000000 # CREATE_NO_WINDOW
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=v_dir, 
                                  encoding='utf-8', errors='replace',
                                  creationflags=creationflags)
            data = json.loads(result.stdout)
            
            if 'streams' in data and len(data['streams']) > 0:
                s = data['streams'][0]
                fps = 30.0
                rate_str = s.get('avg_frame_rate', '30/1')
                if '/' in rate_str:
                    num, den = map(float, rate_str.split('/'))
                    if den != 0: fps = num / den
                else:
                    fps = float(rate_str)
                
                duration = float(s.get('duration', 0))
                if duration == 0:
                    # ストリームから取れない場合はコンテナ(format)から取得を試みる
                    duration = float(data.get('format', {}).get('duration', 0))
                
                nb_frames = int(s.get('nb_frames', 0))
                
                # nb_framesが0の場合は推定
                if nb_frames == 0 and duration > 0:
                    nb_frames = int(duration * fps)
                
                return nb_frames, fps, duration
        except Exception as e:
            print(f"DEBUG: _get_video_info error: {e}")
        return 0, 30.0, 0.0

    def _find_video_file(self, input_dir, base_name, extensions=[".ts", ".mp4", ".mkv"]):
        """指定されたベース名と拡張子の組み合わせでファイルを探す"""
        for ext in extensions:
            path = os.path.join(input_dir, base_name + ext)
            if os.path.exists(path):
                return path
        return None

    def _strip_ts_payload(self, ts_path, out_mjpg_path, target_pid=0x64):
        """TSファイルから特定のPIDのペイロードを抽出し、MJPEGストリームとして保存する。
        同時に含まれるJPEGの数をカウントして返す。"""
        jpeg_count = 0
        try:
            print(f"DEBUG: Stripping TS headers from {os.path.basename(ts_path)} (Target PID: {hex(target_pid)})")
            with open(ts_path, 'rb') as f_in, open(out_mjpg_path, 'wb') as f_out:
                while True:
                    packet = f_in.read(188)
                    if len(packet) < 188: break
                    
                    if packet[0] != 0x47:
                        f_in.seek(-187, 1)
                        continue
                    
                    pid = ((packet[1] & 0x1f) << 8) | packet[2]
                    
                    if pid == target_pid:
                        afc = (packet[3] & 0x30) >> 4
                        header_len = 4
                        if afc == 0x00 or afc == 0x02: continue
                        if afc == 0x03:
                            af_len = packet[4]
                            header_len = 5 + af_len
                        
                        if header_len < 188:
                            payload = packet[header_len:]
                            # JPEG開始マーカー (FF D8) をカウント
                            jpeg_count += payload.count(b'\xff\xd8')
                            f_out.write(payload)
            return jpeg_count
        except Exception as e:
            print(f"DEBUG: _strip_ts_payload error: {e}")
            return 0

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

            # 各種ファイルパスの推定（拡張子 .ts / .mp4 両対応）
            live1_path = self._find_video_file(input_dir, f"{folder_name}_vlc_record_live1")
            live2_path = self._find_video_file(input_dir, f"{folder_name}_vlc_record_live2")
            screen_path = self._find_video_file(input_dir, f"{folder_name}_screen_capture", [".mkv", ".mp4"])
            log_path = os.path.join(input_dir, f"{folder_name}_head.log")

            if not live1_path:
                # フォールバック: 単純なファイル名チェック
                msg = f"Live1ファイルが見つかりません。以下のような名前であることを確認してください:\n{folder_name}_vlc_record_live1.ts または .mp4"
                self._show_message("error", "ファイル不足", msg)
                return

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
            if not self.batch_mode:
                self._show_message("info", "完了", f"変換が正常に完了しました。\n作業フォルダ: {output_dir}")

        except Exception as e:
            self._show_message("error", "エラー", f"処理中にエラーが発生しました:\n{str(e)}")
            self._update_status("エラーが発生しました")
        finally:
            self.root.after(0, self._reset_ui)

    def _extract_frames(self, video_path, output_dir, prefix, src_fps, target_fps, target_total_frames=None):
        if not os.path.exists(video_path):
            msg = f"動画ファイルが見つかりません:\n{os.path.basename(video_path)}\n\n(フルパス: {video_path})"
            print(f"WARNING: {msg}")
            self._show_message("warning", "ファイル未発見", msg)
            return target_total_frames if target_total_frames is not None else 0

        # パスの正規化
        video_path = os.path.abspath(video_path)
        output_dir = os.path.abspath(output_dir)
        v_dir = os.path.dirname(video_path)
        v_name = os.path.basename(video_path)
        
        # まず動画の情報を取得
        total_frames_est, fps_actual, duration = self._get_video_info(video_path)
        actual_target_fps = target_fps

        # 出力パターン（相対パスで使用するために調整）
        # FFmpegをv_dirで実行するため、output_dirを相対パスにする
        rel_output_dir = os.path.relpath(output_dir, v_dir)
        out_pattern = os.path.join(rel_output_dir, f"{prefix}_%06d.jpg")

        # 1回目の標準的なコマンド (TSデマクサ使用)
        # -fflags +genpts+igndts: タイムスタンプの修復
        # -max_interleave_delta 0: TSのパケット順序問題を無視
        cmd1 = [
            "ffmpeg", "-y", 
            "-probesize", "100M", "-analyzeduration", "100M",
            "-fflags", "+genpts+igndts",
            "-i", v_name,
            "-vf", f"fps={actual_target_fps}",
            "-q:v", "2",
            "-max_interleave_delta", "0",
            "-err_detect", "ignore_err",
            out_pattern
        ]

        # 2回目のフォールバックコマンド（強制MJPEG）
        cmd2 = [
            "ffmpeg", "-y",
            "-f", "mjpeg",
            "-i", v_name,
            "-vf", f"fps={actual_target_fps}",
            "-q:v", "2",
            out_pattern
        ]

        def run_cmd(cmd_args):
            try:
                # Windowsで新しいコンソールウィンドウを開かないように設定
                creationflags = 0
                if sys.platform == "win32":
                    creationflags = 0x08000000 # CREATE_NO_WINDOW

                print(f"DEBUG: Running FFmpeg: {' '.join(cmd_args)}")
                process = subprocess.Popen(cmd_args, stderr=subprocess.PIPE, universal_newlines=True, 
                                          encoding='cp932', errors='replace', cwd=v_dir,
                                          creationflags=creationflags)
                ffmpeg_log = []
                for line in process.stderr:
                    ffmpeg_log.append(line.strip())
                    if "frame=" in line:
                        try:
                            parts = line.split("frame=")[1].split()
                            if parts:
                                current_frame = int(parts[0])
                                if total_frames_est > 0:
                                    prog = (current_frame / total_frames_est) * 100
                                    self._update_progress(min(prog, 99.0))
                        except: pass
                    if self.cancel_requested:
                        process.terminate()
                        break
                process.wait()
                
                files = [f for f in os.listdir(output_dir) if f.startswith(prefix) and f.endswith(".jpg")]
                all_files = sorted(files)
                # 連番のリネーム (1-indexed -> 0-indexed)
                for i, old_name in enumerate(all_files):
                    new_name = f"{prefix}_{i:06d}.jpg"
                    if old_name != new_name:
                        try:
                            os.rename(os.path.join(output_dir, old_name), os.path.join(output_dir, new_name))
                        except: pass
                return len(all_files), ffmpeg_log, process.returncode
            except Exception as e:
                return 0, [str(e)], -1

        # 高速化: ffprobeですでに「未知」とわかっている場合はこの段階をスキップする
        ret1 = -1
        count = 0
        if total_frames_est > 0:
            count, log1, ret1 = run_cmd(cmd1)
        else:
            print(f"DEBUG: Unknown format detected by ffprobe. Skipping standard FFmpeg pass.")
        
        # リトライ判定: エラー終了、または極端に枚数が少ない場合 (推定の10%未満かつ100枚未満など)
        suspiciously_low = (total_frames_est > 0 and count < total_frames_est * 0.5 and count < 100)
        
        if (ret1 != 0 or suspiciously_low or total_frames_est == 0) and not self.cancel_requested:
            if total_frames_est > 0:
                print(f"DEBUG: FFmpeg failed or produced suspicious result (count={count}, ret={ret1}). Retrying with fallback...")
            
            # 既存のファイルを掃除（中途半端なファイルを消す）
            for f in os.listdir(output_dir):
                if f.startswith(prefix) and f.endswith(".jpg"):
                    try: os.remove(os.path.join(output_dir, f))
                    except: pass
            
            # --- 改善: TSパケットから直接ペイロードを抽出してリトライ ---
            if video_path.lower().endswith(".ts"):
                with tempfile.NamedTemporaryFile(suffix=".mjpg", delete=False) as tf:
                    temp_mjpg = tf.name
                
                # パケット抽出と同時に正確なフレーム数をカウント
                actual_count = self._strip_ts_payload(video_path, temp_mjpg)
                if actual_count > 0:
                    # 正確なフレーム数が判明したので更新 (これでプログレスバーが動く)
                    total_frames_est = actual_count
                    
                    # 抽出した生MJPEGストリームに対して再度FFmpegを実行
                    # (今度は相対パスではなく絶対パスで安全に処理)
                    cmd3 = [
                        "ffmpeg", "-y",
                        "-f", "mjpeg",
                        "-i", temp_mjpg,
                        "-vf", f"fps={actual_target_fps}",
                        "-q:v", "2",
                        out_pattern
                    ]
                    print(f"DEBUG: Retrying with stripped MJPEG stream...")
                    count, log3, ret3 = run_cmd(cmd3)
                    
                    # 一時ファイルの削除
                    try: os.remove(temp_mjpg)
                    except: pass
                    
                    if count > 0:
                        return count

            # --- 最終フォールバック: 強制MJPEG (元のファイルに対して) ---
            count, log2, ret2 = run_cmd(cmd2)
            if count == 0:
                print(f"DEBUG: Fallback also failed.")
                for log_line in log2[-15:]:
                    print(log_line)

        return count

    def _extract_meta_only(self, video_path, output_dir):
        """ScreenCaptureからパラメータ部分を抽出する (FFmpeg + OpenCV)"""
        if not os.path.exists(video_path): return

        # 1フレームだけ抜き出す (漢字パス問題を避けるため、システムのTempフォルダを使用)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            temp_jpg = tf.name
        
        cmd = ["ffmpeg", "-y", "-i", video_path, "-ss", "0.5", "-vframes", "1", temp_jpg]
        try:
            # FFmpegで画像を出力
            subprocess.run(cmd, capture_output=True, check=True)
            
            if os.path.exists(temp_jpg):
                # 日本語パス対応の読み込み方式
                with open(temp_jpg, 'rb') as f:
                    n = np.frombuffer(f.read(), np.uint8)
                    frame = cv2.imdecode(n, cv2.IMREAD_COLOR)
                
                if frame is not None:
                    # オリジナルの座標で切り抜き
                    cropped_meta = frame[760:875, 440:715]
                    meta_path = os.path.join(output_dir, "meta_info_panel.png")
                    
                    # 日本語パス対応の保存
                    result, encimg = cv2.imencode('.png', cropped_meta)
                    if result:
                        with open(meta_path, 'wb') as f:
                            encimg.tofile(f)
        except Exception as e:
            print(f"Meta extraction error: {e}")
        finally:
            if os.path.exists(temp_jpg):
                try: os.remove(temp_jpg)
                except: pass

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
            self.root.after(0, self.root.quit)
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

if __name__ == "__main__":
    root = tk.Tk()
    app = FolloasConverterApp(root)
    root.mainloop()