"""ASS 字幕・テロップ生成（libass で焼き込む）。

- captions.ass : ナレーション字幕（白・濃色の細い縁取り・重要語だけ赤/金・最大2行）
- cards.ass    : タイトル / 章 / テロップ / 答え（明朝・中央・余白多め）
仕様書 §4,§5。過剰装飾はしない。
"""
from __future__ import annotations

from typing import Any


def _c(v: str) -> str:
    """project.yaml の色 (&HBBGGRR&) を ASS の &HAABBGGRR& (不透明) に。"""
    h = v.replace("&H", "").replace("&", "").strip().upper()
    h = h.zfill(6)[-6:]
    return f"&H00{h}"


def fmt_time(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("\n", "\\N")


def colorize(text: str, red_words: list[str], base: str, accent: str) -> str:
    """red_words を accent 色でハイライト。前後は base 色に戻す。"""
    if not red_words:
        return _escape(text)
    out = _escape(text)
    for w in red_words:
        if not w:
            continue
        ew = _escape(w)
        out = out.replace(ew, f"{{\\c{accent}}}{ew}{{\\c{base}}}")
    return out


def _styles(project: dict) -> list[str]:
    col = project["colors"]
    f = project["fonts"]
    mincho = f["_resolved_mincho"]
    gothic = f["_resolved_gothic"]
    white = _c(col["caption_fill"])
    outline = _c(col["caption_outline"])
    sumi = _c(col["sumi"])
    gold = _c(col["gold"])
    # Style: Name,Font,Size,PrimaryC,SecondaryC,OutlineC,BackC,Bold,Italic,Underline,
    #        StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,
    #        Alignment,MarginL,MarginR,MarginV,Encoding
    bm = project["caption"]["bottom_margin_px"]
    return [
        # 通常字幕（ゴシック・下・細縁）
        f"Style: caption,{gothic},{f['caption_size']},{white},{white},{outline},&H64000000,"
        f"0,0,0,0,100,100,1,0,1,2.4,0,2,180,180,{bm},1",
        # タイトル（明朝・大・中央）
        f"Style: title,{mincho},{f['title_size']},{white},{white},{sumi},&H50000000,"
        f"0,0,0,0,100,100,3,0,1,2.0,1,5,80,80,80,1",
        # 章タイトル（明朝）
        f"Style: chapter,{mincho},{f['chapter_size']},{white},{white},{sumi},&H50000000,"
        f"0,0,0,0,100,100,2,0,1,2.0,1,5,80,80,80,1",
        # サブタイトル
        f"Style: subtitle,{mincho},48,{white},{white},{sumi},&H50000000,"
        f"0,0,0,0,100,100,1,0,1,1.6,1,5,80,80,80,1",
        # テロップ（明朝）
        f"Style: onscreen,{mincho},{f['onscreen_size']},{white},{white},{sumi},&H50000000,"
        f"0,0,0,0,100,100,2,0,1,2.0,1,5,80,80,80,1",
        # 答え（大・明朝・金の縁取りは使わず墨）
        f"Style: answer,{mincho},{f['title_size']},{white},{white},{sumi},&H50000000,"
        f"0,0,0,0,100,100,4,0,1,2.4,1,5,120,120,120,1",
        f"Style: answer_sub,{mincho},{f['chapter_size']},{white},{white},{sumi},&H50000000,"
        f"0,0,0,0,100,100,2,0,1,2.0,1,5,120,120,120,1",
        # 一覧（共通点リスト）
        f"Style: listitem,{mincho},58,{white},{white},{sumi},&H50000000,"
        f"0,0,0,0,100,100,2,0,1,1.8,1,5,120,120,120,1",
        # ロケーション札（左下・ゴシック・小）
        f"Style: location,{gothic},44,{white},{white},{outline},&H64000000,"
        f"0,0,0,0,100,100,1,0,1,2.0,0,1,120,120,140,1",
    ]


def header(project: dict, resolution: tuple[int, int]) -> str:
    w, h = resolution
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        f"PlayResX: {w}",
        f"PlayResY: {h}",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    lines += _styles(project)
    lines += ["", "[Events]",
              "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    return "\n".join(lines) + "\n"


def _ev(start: float, end: float, style: str, text: str, layer: int = 0,
        fadein: int = 200, fadeout: int = 200) -> str:
    fade = f"{{\\fad({fadein},{fadeout})}}"
    return f"Dialogue: {layer},{fmt_time(start)},{fmt_time(end)},{style},,0,0,0,,{fade}{text}"


def build_captions(timeline: dict, project: dict) -> str:
    col = project["colors"]
    base = _c(col["caption_fill"])
    accent = _c(col["keyword_red"])
    res = tuple(timeline["resolution"])
    out = [header(project, res)]
    for scene in timeline["scenes"]:
        for cap in scene.get("captions", []):
            s = scene["start"] + cap["start"]
            e = scene["start"] + cap["end"]
            text = colorize(cap["text"], cap.get("red", []), base, accent)
            out.append(_ev(s, e, "caption", text))
    return "\n".join(out) + "\n"


def build_cards(timeline: dict, project: dict) -> str:
    col = project["colors"]
    base = _c(col["caption_fill"])
    accent = _c(col["keyword_red"])
    res = tuple(timeline["resolution"])
    out = [header(project, res)]
    for scene in timeline["scenes"]:
        for card in scene.get("cards", []):
            s = scene["start"] + card["start"]
            e = scene["start"] + card["end"]
            for i, item in enumerate(card["lines"]):
                style = item.get("style", "onscreen")
                # 複数行は縦にずらして中央寄せ
                text = colorize(item["text"], item.get("red", []), base, accent)
                dy = item.get("dy")
                if dy is not None:
                    text = f"{{\\pos({res[0]//2},{res[1]//2 + dy})}}" + text
                out.append(_ev(s, e, style, text, layer=1,
                               fadein=item.get("fadein", 300),
                               fadeout=item.get("fadeout", 300)))
    return "\n".join(out) + "\n"
