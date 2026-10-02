# 10/11 新月×一粒万倍日 リール

- `reel.mp4` … 投稿用動画（1080×1920 / 30fps / 32秒 / 無音。音楽はインスタのアプリで追加）
- `cover.png` … 表紙画像（「カバーを編集」で設定）

## 暦データ（ephem で計算）
- 新月：2026/10/11（日）0:50 JST、天秤座
- 一粒万倍日：戊午の日（寒露 10/9 以降の戌月 → 午・酉の日）
- 月のボイド：10/11 8:08 〜 10/12 0:22 JST
- 同日：不成就日（旧暦9/1）・先負

## 作り直すとき
```bash
cd source
npm install
node render.js stills 3.2,8.5,19.5   # 確認用の静止画
node render.js video ../reel.mp4     # 動画を書き出し
node render.js cover 3.4 ../cover.png
```
`render.js` は Chromium のパス `/opt/pw-browsers/chromium` を前提にしています。環境に合わせて変更してください。
