"""叶結び 石川編 動画ビルドパイプライン。

使い方は video/README.md を参照。
モジュール構成:
  util        共通ヘルパ（設定読込・ffmpeg 呼び出し・フォント解決・尺見積り）
  scan_assets 素材スキャン→ inventory + manifest 雛形（EXIF / 重複判定 / 日付分類）
  timeline    EDL(config) + manifest + ナレーション → timeline_dayN.json
  ass         ASS 字幕・テロップ生成
  preflight   レンダー前チェック（仕様書 §25）
  render      ffmpeg でレンダー（Ken Burns / 字幕焼込 / ラウドネス正規化）
  cli         オーケストレータ
"""
