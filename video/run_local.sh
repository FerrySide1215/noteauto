#!/usr/bin/env bash
# 叶結び 石川編 — Mac ローカル用ブートストラップ
# 使い方:
#   1) このリポジトリを Mac に clone
#   2) おみくじ・境内写真の入ったフォルダを用意
#   3) bash video/run_local.sh "<素材フォルダのパス>"
#      例: bash video/run_local.sh ~/Downloads/選択項目から作成したフォルダ
#
# やること: 依存チェック → venv作成 → pip install → 素材スキャン → 次の手順を表示
set -euo pipefail
cd "$(dirname "$0")"   # video/ へ

echo "== 依存チェック =="
command -v python3 >/dev/null || { echo "python3 が必要です"; exit 1; }
if ! command -v ffmpeg >/dev/null; then
  echo "⚠ ffmpeg が未インストールです。 brew install ffmpeg を実行してください（レンダーに必須）。"
fi

echo "== Python 環境 =="
if [ ! -d .venv ]; then python3 -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "  OK: $(python3 -c 'import PIL,yaml;print("Pillow/PyYAML ready")')"

SRC="${1:-}"
if [ -n "$SRC" ]; then
  echo "== 素材スキャン: $SRC =="
  python3 -m build.cli scan "$SRC"
  cat <<'NEXT'

── 次の手順 ─────────────────────────────
1) video/assets/manifest.yaml を開き、各写真の group を埋める
   DAY1: kinkengu / kinkengu_omikuji / shirayama / shirayama_kaiun_omikuji
         shirayama_futsu_omikuji / hattori / hattori_omikuji / broll_day1
   DAY2: natadera / natadera_omikuji / uhashi / uhashi_omikuji
         ataka / ataka_omikuji / broll_day2
   （*_omikuji にはおみくじの寄りカット。判別不能は travel_broll）
2) source video/.venv/bin/activate   ← 別ターミナルなら毎回
   python -m build.cli day1 --step all
   python -m build.cli day2 --step all
   → 出力は video/outputs/day1, video/outputs/day2
─────────────────────────────────────────
NEXT
else
  echo "素材フォルダのパスを渡すとスキャンまで実行します:"
  echo "  bash video/run_local.sh \"~/Downloads/選択項目から作成したフォルダ\""
fi
