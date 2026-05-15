@echo off
setlocal
cd /d %~dp0

echo ==========================================
echo FolloasConverter 一括処理を開始します
echo ==========================================

python FolloasConverter.py "I:\260424\3ﾃﾞｯｷｰ02_260424_141328"
python FolloasConverter.py "I:\260424\S4deck_260424_095937"
python FolloasConverter.py "I:\260424\S5deck-0.2_260424_134003"
python FolloasConverter.py "I:\260424\s5deck-0.2-緑_260424_141135"
python FolloasConverter.py "I:\260424\S5デッキ_260424_094327"
python FolloasConverter.py "I:\260424\S5デッキ_260424_100506"
python FolloasConverter.py "I:\260424\デッキ3_260424_134922"
python FolloasConverter.py "I:\260424\炉3_260424_111848"
python FolloasConverter.py "I:\260424\炉3-0.2_260424_114051"
python FolloasConverter.py "I:\260424\炉4_260424_103426"
python FolloasConverter.py "I:\260424\炉4-0.2_260424_104921"
python FolloasConverter.py "I:\260424\炉502_260424_110322"
python FolloasConverter.py "I:\260424\炉５_260424_103414"
python FolloasConverter.py "I:\260424\炉6_260424_111940"
python FolloasConverter.py "I:\260424\炉6-0.2_260424_112627"

echo ==========================================
echo 全ての処理が完了しました。
echo ==========================================
pause
