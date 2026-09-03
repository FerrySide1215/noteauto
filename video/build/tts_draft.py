"""ドラフト確認用の仮ナレーション音声を生成（仕様書 §22）。

- 最終動画用に低品質TTSを勝手に確定採用しない。あくまで draft 用。
- macOS の `say`（日本語音声 Kyoko 等）が使える場合のみ生成。
- 生成物は voiceover/dayN/DRAFT_TTS_<scene>.wav（仮音声とわかるファイル名）。
  ※ timeline は本番用に <scene>.wav を探すので、これらは自動採用されない。
    ドラフトを尺見積りに使いたい場合のみ、手動で DRAFT_TTS_ を外してリネームする。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import util


def main(slug: str) -> None:
    cut = util.cut(slug)
    say = shutil.which("say")
    if not say:
        print("macOS の `say` が見つかりません。仮ナレーションはスキップします。")
        print(f"（本番は voiceover/{cut['vo']}/<scene>.wav に録音音声を置いてください）")
        return
    blocks = util.parse_narration_file(cut["narration"])
    outdir = util.VOICEOVER_DIR / cut["vo"]
    outdir.mkdir(parents=True, exist_ok=True)
    for sid, lines in blocks.items():
        if not lines:
            continue
        text = "。".join(lines)
        aiff = outdir / f"DRAFT_TTS_{sid}.aiff"
        wav = outdir / f"DRAFT_TTS_{sid}.wav"
        subprocess.run([say, "-v", "Kyoko", "-o", str(aiff), text], check=False)
        if util.have_ffmpeg() and aiff.exists():
            util.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "48000", str(wav)])
            aiff.unlink(missing_ok=True)
    print(f"仮ナレーション（DRAFT_TTS_*）を {outdir} に生成しました。")
    print("本番録音は DRAFT_TTS_ を外したファイル名（<scene>.wav）で置き換えてください。")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "ishikawa")
