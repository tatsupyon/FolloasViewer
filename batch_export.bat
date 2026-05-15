@echo off
setlocal
cd /d %~dp0

echo ==========================================
echo FolloasViewer 一括エクスポートを開始します
echo ==========================================

python FolloasViewer.py "I:\260424\3ﾃﾞｯｷｰ02_260424_141328_ViewReady"
python FolloasViewer.py "I:\260424\S4deck_260424_095937_ViewReady"
python FolloasViewer.py "I:\260424\S5deck-0.2_260424_134003_ViewReady"
python FolloasViewer.py "I:\260424\s5deck-0.2-緑_260424_141135_ViewReady"
python FolloasViewer.py "I:\260424\S5デッキ_260424_094327_ViewReady"
python FolloasViewer.py "I:\260424\S5デッキ_260424_100506_ViewReady"
python FolloasViewer.py "I:\260424\デッキ3_260424_134922_ViewReady"
python FolloasViewer.py "I:\260424\炉3_260424_111848_ViewReady"
python FolloasViewer.py "I:\260424\炉3-0.2_260424_114051_ViewReady"
python FolloasViewer.py "I:\260424\炉4_260424_103426_ViewReady"
python FolloasViewer.py "I:\260424\炉4-0.2_260424_104921_ViewReady"
python FolloasViewer.py "I:\260424\炉502_260424_110322_ViewReady"
python FolloasViewer.py "I:\260424\炉５_260424_103414_ViewReady"
python FolloasViewer.py "I:\260424\炉6_260424_111940_ViewReady"
python FolloasViewer.py "I:\260424\炉6-0.2_260424_112627_ViewReady"

echo ==========================================
echo 全てのエクスポート処理が完了しました。
echo ==========================================
pause
