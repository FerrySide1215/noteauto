"""timeline のナレーション字幕 → SRT（仕様書 §23）。

焼き込み版と字幕なし版は render 側で出し分ける。ここは配布用 .srt を書く。
"""
from __future__ import annotations

from pathlib import Path

from . import util


def _fmt(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build(slug: str) -> Path:
    out_slug = util.cut(slug)["out"]
    tl_path = util.OUTPUTS_DIR / out_slug / f"timeline_{out_slug}.json"
    timeline = util.read_json(tl_path)
    idx = 1
    out_lines: list[str] = []
    for scene in timeline["scenes"]:
        for cap in scene.get("captions", []):
            s = scene["start"] + cap["start"]
            e = scene["start"] + cap["end"]
            out_lines.append(str(idx))
            out_lines.append(f"{_fmt(s)} --> {_fmt(e)}")
            out_lines.append(cap["text"])
            out_lines.append("")
            idx += 1
    out = util.OUTPUTS_DIR / out_slug / f"{out_slug}.srt"
    out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"SRT [{slug}]: {idx-1}字幕 → {out}")
    return out


if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else "ishikawa")
