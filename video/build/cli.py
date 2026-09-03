"""オーケストレータ。

  python -m build.cli scan <素材フォルダ>
  python -m build.cli ishikawa --step timeline
  python -m build.cli ishikawa --step all
  python -m build.cli ishikawa --step render --quality wqhd
  python -m build.cli ishikawa --step render --preview-only

対象(slug): ishikawa（本番・1本約10分） / day1 / day2（旧2本立て・参照用）

--step:
  timeline    timeline_<slug>.json を生成
  srt         <slug>.srt を生成
  preflight   §25 チェック
  tts-draft   ドラフト確認用の仮ナレーション（DRAFT_TTS_*）
  render      本編/字幕なし/プレビューをレンダー（ffmpeg必須）
  all         timeline → srt → preflight → render
"""
from __future__ import annotations

import argparse
import sys

from . import preflight, scan_assets, srt, timeline, util

FILM = "ishikawa"


def _do(slug: str, step: str, quality: str, only_preview: bool) -> int:
    if step in ("timeline", "all"):
        timeline.main(slug)
    if step in ("srt", "all"):
        srt.build(slug)
    if step == "tts-draft":
        from . import tts_draft
        tts_draft.main(slug)
    if step in ("preflight", "all"):
        rc = preflight.main(slug)
        if step == "preflight":
            return rc
        if rc != 0:
            print("\n[preflight ERROR] があります。render 続行しますが、修正を推奨します。\n")
    if step in ("render", "all"):
        from . import render  # ffmpeg 依存を遅延 import
        render.render(slug, quality=quality, only_preview=only_preview)
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="build.cli", description="叶結び 石川編 ビルド")
    p.add_argument("target", help="scan | ishikawa | day1 | day2")
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
    if args.target in ("film", FILM):
        return _do(FILM, args.step, args.quality, args.preview_only)
    if args.target in util.CUTS:
        return _do(args.target, args.step, args.quality, args.preview_only)
    p.error(f"target は scan / {' / '.join(util.CUTS)} のいずれか")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
