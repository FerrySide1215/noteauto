# 叶結び 石川編 — 動画ビルドパイプライン

実写の神社・おみくじを主役に、6か所のおみくじを旅の流れとしてつなぐ **1本・約10分の動画** を、
**素材フォルダ＋ffmpeg があるローカル環境で** 自動生成するためのツール一式です。
見た目はチャンネルのバナー世界観（ピンク・桜・柔らかい光・きらめき）で統一。
台本・資料は `docs/ishikawa_script.html`（構成表／ナレーション全文／縦書き／BGM）も参照。

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
│   ├── project.yaml              解像度・fps・音量・色（ブランド配色）・フォント・BGM の全体設定
│   ├── ishikawa.yaml             ★本番：単一動画の編集台本（シーン順・テロップ・縦書き・おみくじ）
│   ├── day1.yaml / day2.yaml     旧2本立て（参照用）
├── scripts/
│   ├── ishikawa_narration.txt    ★本番：ナレーション確定稿（各所20〜30秒・ふりがな付き）
│   └── day1_/day2_narration.txt  旧2本立て（参照用）
├── docs/ishikawa_script.html     台本＆資料ページ（アーティファクト公開元）
├── build/                        Python パイプライン本体
│   ├── scan_assets.py            素材スキャン→inventory＋manifest雛形
│   ├── timeline.py               台本＋manifest＋ナレーション→timeline_<slug>.json
│   ├── ass.py                    ASS字幕・テロップ・縦書き生成
│   ├── srt.py                    SRT生成
│   ├── preflight.py              レンダー前チェック
│   ├── render.py                 ffmpegレンダー（Ken Burns/字幕焼込/ラウドネス）
│   ├── tts_draft.py              仮ナレーション（DRAFT_TTS・確認用のみ）
│   └── cli.py                    オーケストレータ
├── assets/        （あなたが用意）撮影素材とmanifest.yaml   ※gitignore
├── voiceover/     （あなたが用意）録音ナレーション ishikawa/<scene>.wav ※gitignore
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
`video/voiceover/ishikawa/<scene>.wav`（scene は台本の `[id]`）に置く。

### 2. スキャン（inventory＋重複判定＋日付分類）
```bash
cd video && python -m build.cli scan ./assets
```
`outputs/asset_inventory.json` / `.csv` と、`assets/manifest.yaml` の**雛形**が出ます。
撮影日で日付を記録（1本にまとめるので DAY 分けは不要）。神社の判定は自動でしません。

### 3. manifest を埋める（重要）
`assets/manifest.yaml` の各素材に `group:` を記入します。グループ名（単一動画 ishikawa）:

- `kinkengu` `kinkengu_omikuji`
- `shirayama` `shirayama_kaiun_omikuji` `shirayama_futsu_omikuji`
- `hattori` `hattori_omikuji`
- `natadera` `natadera_omikuji`
- `uhashi` `uhashi_omikuji`
- `ataka` `ataka_omikuji`
- `title_bg`（OP背景）・`broll`（導入/転換/ED）・`woman`（総括＝バナーの女性）
- 判別不能: `travel_broll`

`*_omikuji` にはおみくじの寄りカットを入れてください。

### 4. タイムライン→チェック→レンダー（1本）
```bash
python -m build.cli ishikawa --step all       # timeline→srt→preflight→render
```
段階実行も可能:
```bash
python -m build.cli ishikawa --step timeline     # timeline_ishikawa.json だけ
python -m build.cli ishikawa --step preflight     # チェックだけ
python -m build.cli ishikawa --step render --quality wqhd    # 2560x1440
python -m build.cli ishikawa --step render --preview-only     # プレビューだけ素早く
```
※ 旧2本立て（`day1` / `day2`）も参照用に残していますが、本番は `ishikawa` 1本です。

### （任意）仮ナレーションで尺確認
録音前に構成を確認したいとき（macOSのみ）:
```bash
python -m build.cli ishikawa --step tts-draft   # voiceover/ishikawa/DRAFT_TTS_*.wav
```
これは**確認専用**。本番は `DRAFT_TTS_` を外した `<scene>.wav` に録音を置き換えます。

## 出力
```
outputs/
├── ishikawa/  kanau_musubi_ishikawa.mp4  / _no_caption.mp4 / _preview.mp4
│              timeline_ishikawa.json / ishikawa.srt / cards.ass / captions.ass
├── asset_inventory.json / .csv
```

## 尺・同期について
- 録音音声 `voiceover/ishikawa/<scene>.wav` があれば、その実尺でシーン長が決まります。
- 無い場合はナレーション文字数からの**見積り**でドラフト尺を組みます（`--preview-only`向き）。
- 字幕はシーン内で文字数比により配置します。精密な口パク同期が要る場合は、
  録音後に `captions.ass` を微調整するか、whisper 等での整音を検討してください。

## 守っていること（仕様書 §2・§25）
- おみくじ本文・神社名を**書き換え/推測しない**。出典は `omikuji_transcriptions.md` で管理。
- AI生成の神社映像は混ぜない。素材不足は**黒画面ではなく「素材未挿入」札**で継続し、
  preflight が警告します（該当箇所を実素材へ差し替えてください）。
- 過剰なエフェクト（光・桜吹雪・金粉・派手なトランジション）を入れない設計です。

## おみくじの出典
**6か所すべて実写真で確認済**（金劔宮・白山比咩神社2枚・服部神社・那谷寺・菟橋神社・安宅住吉神社）。
翻刻は `omikuji_transcriptions.md` を参照。実物にもとづく主な訂正:
- 服部神社の和歌「常盤に栄ゆる」→ 実物「常盤に**みどり**栄ゆる」
- 「うはし神社」= **菟橋神社（読み: うはし）**、**第四十一番 小吉**
- 安宅住吉神社の番号は仕様書「第四十一番」→ 実物 **第四十番 吉**（番号が菟橋と入替わっていた）
