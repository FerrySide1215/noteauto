"""オーケストレータ。

  python -m build.cli scan <素材フォルダ>
  python -m build.cli day1 --step timeline
  python -m build.cli day1 --step all
  python -m build.cli day2 --step render --quality wqhd
  python -m build.cli day1 --step tts-draft     # 仮ナレーション（DRAFT_TTS）を生成

--step:
  timeline    timeline_dayN.json を生成
  srt         dayN.srt を生成
  preflight   §25 チェック
  tts-draft   ドラフト確認用の仮ナレーション音声（DRAFT_TTS_*）
  render      本編/字幕なし/プレビューをレンダー（ffmpeg必須）
  all         timeline → srt → preflight → render
"""
from __future__ import annotations

import argparse
import sys

from . import preflight, scan_assets, srt, timeline


def _do(day: int, step: str, quality: str, only_preview: bool) -> int:
    if step in ("timeline", "all"):
        timeline.main(day)
    if step in ("srt", "all"):
        srt.build(day)
    if step in ("tts-draft",):
        from . import tts_draft
        tts_draft.main(day)
    if step in ("preflight", "all"):
        rc = preflight.main(day)
        if step == "preflight":
            return rc
        if rc != 0:
            print("\n[preflight ERROR] があります。render 続行しますが、修正を推奨します。\n")
    if step in ("render", "all"):
        from . import render  # ffmpeg 依存を遅延 import
        render.render(day, quality=quality, only_preview=only_preview)
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="build.cli", description="叶結び 石川編 ビルド")
    p.add_argument("target", help="scan | day1 | day2")
    p.add_argument("src", nargs="?", help="scan 時の素材フォルダ")
    p.add_argument("--step", default="all",
                   choices=["timeline", "srt", "preflight", "tts-draft", "render", "all"])
    p.add_argument("--quality", default="hd", choices=["hd", "wqhd"])
    p.add_argument("--preview-only", action="store_true", help="プレビューのみレンダー")
    args = p.parse_args(argv)

    if args.target == "scan":
        if not args.src:
            p.error("scan には素材フォルダが必要です")
        scan_assets.main(args.src)
        return 0
    if args.target in ("day1", "day2"):
        day = int(args.target[-1])
        return _do(day, args.step, args.quality, args.preview_only)
    p.error("target は scan / day1 / day2 のいずれか")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
