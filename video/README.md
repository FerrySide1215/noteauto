# 叶結び 石川編 — 動画ビルドパイプライン

実写の神社・おみくじを主役に、複数のおみくじを旅の流れとしてつなぐ動画（DAY1 / DAY2）を、
**素材フォルダ＋ffmpeg があるローカル環境で** 自動生成するためのツール一式です。
仕様書（叶結び YouTube「石川編」完全仕様書）に準拠しています。

> ⚠️ **このパイプラインはあなたのMac（素材とffmpegがある場所）で動かします。**
> クラウド側のセッションはあなたの `ダウンロード` フォルダや ffmpeg にアクセスできないため、
> 最終MP4の書き出しはローカルで実行してください。台本・字幕・タイムライン等の
> テキスト成果物はこのリポジトリに用意済みです。

---

## 何が入っているか

```
video/
├── README.md                     ← これ
├── requirements.txt
├── omikuji_transcriptions.md     おみくじ翻刻＋出典管理（写真確認済 / 仕様書のみ を明示）
├── config/
│   ├── project.yaml              解像度・fps・音量・色・フォント・BGM・素材分類の全体設定
│   ├── day1.yaml                 DAY1 編集台本（シーン順・テロップ・おみくじ強調）
│   └── day2.yaml                 DAY2 編集台本
├── scripts/
│   ├── day1_narration.txt        DAY1 ナレーション確定稿
│   └── day2_narration.txt        DAY2 ナレーション確定稿
├── build/                        Python パイプライン本体
│   ├── scan_assets.py            素材スキャン→inventory＋manifest雛形
│   ├── timeline.py               台本＋manifest＋ナレーション→timeline_dayN.json
│   ├── ass.py                    ASS字幕・テロップ生成
│   ├── srt.py                    SRT生成
│   ├── preflight.py              レンダー前チェック（§25）
│   ├── render.py                 ffmpegレンダー（Ken Burns/字幕焼込/ラウドネス）
│   ├── tts_draft.py              仮ナレーション（DRAFT_TTS・確認用のみ）
│   └── cli.py                    オーケストレータ
├── assets/        （あなたが用意）撮影素材とmanifest.yaml   ※gitignore
├── voiceover/     （あなたが用意）録音ナレーション dayN/<scene>.wav ※gitignore
├── supplied_audio/（あなたが用意）BGM素材                   ※gitignore
└── outputs/        生成物（timeline / srt / mp4 …）
```

## セットアップ（ローカル）

```bash
cd video
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# ffmpeg（未導入なら）:  macOS→ brew install ffmpeg
```

## 手順

### 1. 素材を置く
石川旅行の写真・動画を `video/assets/` に入れる（サブフォルダ可）。
BGMがあれば `video/supplied_audio/` に、録音ナレーションがあれば
`video/voiceover/day1/<scene>.wav`（scene は台本の `[id]`）に置く。

### 2. スキャン（inventory＋重複判定＋日付分類）
```bash
cd video && python -m build.cli scan ./assets
```
`outputs/asset_inventory.json` / `.csv` と、`assets/manifest.yaml` の**雛形**が出ます。
撮影日で DAY1(2026-08-22)/DAY2(2026-08-23) を自動仕分け。神社の判定は自動でしません。

### 3. manifest を埋める（重要）
`assets/manifest.yaml` の各素材に `group:` を記入します。グループ名:

- **DAY1**: `kinkengu` `kinkengu_omikuji` `shirayama` `shirayama_kaiun_omikuji`
  `shirayama_futsu_omikuji` `hattori` `hattori_omikuji` `broll_day1`
- **DAY2**: `natadera` `natadera_omikuji` `uhashi` `uhashi_omikuji`
  `ataka` `ataka_omikuji` `broll_day2`
- 判別不能: `travel_broll`

`*_omikuji` にはおみくじの寄りカットを入れてください。

### 4. タイムライン→チェック→レンダー
```bash
python -m build.cli day1 --step all       # timeline→srt→preflight→render
python -m build.cli day2 --step all
```
段階実行も可能:
```bash
python -m build.cli day1 --step timeline    # timeline_day1.json だけ
python -m build.cli day1 --step preflight    # §25 チェックだけ
python -m build.cli day1 --step render --quality wqhd   # 2560x1440
python -m build.cli day1 --step render --preview-only    # プレビューだけ素早く
```

### （任意）仮ナレーションで尺確認
録音前に構成を確認したいとき（macOSのみ）:
```bash
python -m build.cli day1 --step tts-draft   # voiceover/day1/DRAFT_TTS_*.wav
```
これは**確認専用**。本番は `DRAFT_TTS_` を外した `<scene>.wav` に録音を置き換えます。

## 出力（§24）
```
outputs/
├── day1/  kanau_musubi_ishikawa_day1.mp4  / _no_caption.mp4 / _preview.mp4
│          timeline_day1.json / day1.srt / cards.ass / captions.ass
├── day2/  （同上）
├── asset_inventory.json / .csv
```

## 尺・同期について
- 録音音声 `voiceover/dayN/<scene>.wav` があれば、その実尺でシーン長が決まります。
- 無い場合はナレーション文字数からの**見積り**でドラフト尺を組みます（`--preview-only`向き）。
- 字幕はシーン内で文字数比により配置します。精密な口パク同期が要る場合は、
  録音後に `captions.ass` を微調整するか、whisper 等での整音を検討してください。

## 守っていること（仕様書 §2・§25）
- おみくじ本文・神社名を**書き換え/推測しない**。出典は `omikuji_transcriptions.md` で管理。
- AI生成の神社映像は混ぜない。素材不足は**黒画面ではなく「素材未挿入」札**で継続し、
  preflight が警告します（該当箇所を実素材へ差し替えてください）。
- 過剰なエフェクト（光・桜吹雪・金粉・派手なトランジション）を入れない設計です。

## 出典が未確認のおみくじ
DAY1の服部神社、DAY2の那谷寺・うはし神社・安宅住吉神社のおみくじ本文は、
現時点で**仕様書のテキストのみ**が根拠です（実写真は未受領）。
`omikuji_transcriptions.md` の ⚠️ 印を、撮影原本と必ず照合してから確定してください。
特に「うはし神社」の**正式な漢字表記**は現地看板で確認が必要です。
