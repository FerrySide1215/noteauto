# LUNA VEIL リール生成

LUNA VEIL（@lunaveilmagical）のリールを 9:16 / 1080x1920 / 30fps / BGM付きで書き出すスクリプト。

- `reels.py` … 7本の台本（テロップ・尺・背景シーン・キャプション・ハッシュタグ）
- `render.py` … 背景生成 → ズーム/パン → テロップ → 炎・きらめき・金の粒 → BGM合成 → mp4
- `LUNAVEIL_リール7本_台本.md` … 台本・キャプション・画像プロンプト一覧（`--doc` で再生成）

## 使い方

```bash
pip install pillow numpy          # ffmpeg も必要
python3 render.py                 # 7本すべて → out/LUNAVEIL_XX_*.mp4（表紙png・キャプションtxtも）
python3 render.py 01 03           # 指定したリールだけ
python3 render.py --stills        # 全カットの静止画一覧（確認用）
python3 render.py --doc           # 台本Markdownを書き出し
```

フォント（しっぽり明朝・Cormorant Garamond／どちらもOFL）は初回に `fonts/` へ自動ダウンロードする。

## 写実画像に差し替える

背景は今は自動生成のイラスト調。ChatGPTで画像を作って `_bg_in/{リールID}_{カット番号}.png`
（例: `_bg_in/01_3.png` = 01番リールの3カット目）に置いて書き出し直すと、そのカットだけ差し替わる。
プロンプトは `LUNAVEIL_リール7本_台本.md` の各リールの「画像プロンプト」に入っている。

## BGM

BGMはスクリプト内でその場で合成しているので著作権フリー。
インスタのおすすめに乗せたいときは、投稿時にアプリ内の音源を重ねるか、差し替えてもOK。
