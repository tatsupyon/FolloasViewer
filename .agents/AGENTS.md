# FolloasViewer Project Context

## 1. Project Overview
- **目的**: AI認識ログと複数系統のライブ映像を統合するデータ最適化ツール(FolloasConverter)と、そのデータを同期再生・カット編集し再エンコードするGUIツール(FolloasViewer)からなるシステム(Windows用)。
- **リポジトリ**: `https://github.com/tatsupyon/FolloasViewer.git`
- **技術スタック**: Python 3.x, Tkinter, OpenCV, NumPy, Pillow (PIL)
- **エンコーディング**: 
  - ソースコード(`.py`)およびドキュメント(`.md`): **UTF-8**
  - Windows環境・外部通信/ツール連携: 一部CP932(Shift-JIS)との文字コード差異に留意

- **システム構成**:
  - **データコンバータ**: `FolloasConverter.py` (ログの欠損を補完し30fps基準で同期を維持するCSVパース処理。複数映像の同期抽出、TSからのMJPEG抽出)
  - **画像VIEWER**: `FolloasViewer.py` (_ViewReadyデータの読み込みと同期再生。スコア閾値の動的変更、認識枠の描画、START-END方式のカット編集とエクスポート機能)
  - **ビルド環境**: `make_FolloasViewer.bat`, `.spec` ファイル
- **仕様基準ドキュメント** (ソースの `.md` と閲覧用の `.html` をペアで管理):
  - `FolloasConverter_Spec.md` / `.html`
  - `FolloasConverter_Manual.md` / `.html`
  - `FolloasViewer_Spec.md` / `.html`
  - `FolloasViewer_Manual.md` / `.html`
  - `変更点.md` (機能追加・不具合修正・仕様変更の履歴一覧。無い場合は作成する)

---

## 2. 開発・実装プロトコル（絶対遵守）

### A. 動作安全性・環境制約
- **日本語パス問題の回避**:
  - OpenCVやPillow等でのファイル読み書き時、日本語を含むパスが原因でエラーになることを防ぐための回避機構（np.fromfile等の利用）を維持・活用すること。
- **待機コード（ギプス）の追加禁止**:
  - 安易な `time.sleep()` を用いた同期や待機処理を追加しないこと。

### B. バージョン管理・連動更新ルール
- **VERSION表記の書式**:
  - `VERSION = "V<メジャー>.<マイナー> YYYY/MM/DD"` (例: `VERSION = "V1.64 2026/05/20"`)
- **連動インクリメント (最重要)**:
  - `.py` ファイルを変更した場合、**必ず「変更対象ファイル自身」の VERSION 定数**を `+0.01` して更新すること（日付も現在日に更新）。
  - 同時に、仕様書や取説など、影響を受ける関連ドキュメントのバージョン表記も更新すること。

### C. 変更履歴の記録運用
- **`変更点.md` への記録**:
  - ソースコード変更を行った際は、必ずプロジェクトルートの `変更点.md` に表形式（`No.`、`日付`、`バージョン`、`カテゴリ`、`対象箇所`、`問題点 / 変更理由`、`修正点 / 対応内容`）で履歴を追記・更新すること。

### D. Git運用・コミットプロトコル
- **ユーザー承認後のコミット・プッシュ**:
  - ソースコード変更完了後、AIは**直ちにGitへのPushを行わないこと**。
  - まずユーザーへ動作確認・レビューを依頼し、ユーザーから明示的な「承認（OK、問題ない等）」の指示を受けた後に初めて、以下の一連のGit操作を実行しGitHubへ反映させること。
    1. 事前に `git pull` 等でリモートの最新状態と同期する。
    2. コミットメッセージを作成する。過去の履歴に倣い、先頭のバージョン表記は**対象アプリを明記**すること。
       - Viewer単体の変更: `V<VERSION>(Viewer) : 修正概要`
       - Converter単体の変更: `V<VERSION>(Converter) : 修正概要`
       - 両方の変更: `V<VERSION>(Viewer)/V<VERSION>(Converter) : 修正概要`
    3. `git add .`、`git commit`、`git push` を実行する。
    4. 実行後、プッシュが完了したことと、使用したコミットメッセージをユーザーに報告すること。
