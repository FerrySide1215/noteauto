"""EDL(config) + manifest + ナレーション → outputs/<slug>/timeline_<slug>.json

素材が無いグループは placeholder ショット（札）で埋める（黒画面は入れない）。
おみくじショットは「全体→寄り」を同一写真で行うため allow_repeat=True を付ける。
vtext = 画面中央の縦書き（受け取った言葉）。fixed_seconds = ナレ無しシーンの固定尺。
"""
from __future__ import annotations

from pathlib import Path

from . import util


def _load_manifest() -> dict[str, list[dict]]:
    """assets/manifest.yaml → group -> [ {file, abspath, kind, day}, ... ]"""
    path = util.ASSETS_DIR / "manifest.yaml"
    groups: dict[str, list[dict]] = {}
    if not path.exists():
        return groups
    data = util.load_yaml(path) or {}
    inv: dict[str, dict] = {}
    inv_path = util.OUTPUTS_DIR / "asset_inventory.json"
    if inv_path.exists():
        for rec in util.read_json(inv_path):
            inv[rec["file"]] = rec
    for entry in data.get("assets", []) or []:
        g = (entry.get("group") or "").strip()
        if not g:
            continue
        rec = inv.get(entry["file"], {})
        groups.setdefault(g, []).append({
            "file": entry["file"],
            "abspath": rec.get("abspath") or str(util.ASSETS_DIR / entry["file"]),
            "kind": rec.get("kind", "image"),
            "day": entry.get("day") or rec.get("day"),
        })
    return groups


class _Picker:
    def __init__(self, groups: dict[str, list[dict]]):
        self.groups = groups
        self.cursor: dict[str, int] = {}

    def next(self, group: str) -> dict | None:
        items = self.groups.get(group) or []
        if not items:
            return None
        i = self.cursor.get(group, 0)
        self.cursor[group] = i + 1
        return items[i % len(items)]


def _placeholder(label: str, dur: float) -> dict:
    return {"path": None, "type": "placeholder", "label": label,
            "dur": round(dur, 2), "kenburns": "none"}


def _shot(rec: dict, dur: float, kb: str, allow_repeat: bool = False) -> dict:
    return {"path": rec["abspath"], "type": rec.get("kind", "image"),
            "file": rec["file"], "dur": round(dur, 2), "kenburns": kb,
            "allow_repeat": allow_repeat}


_KB_CYCLE = ["in", "out", "left", "right"]


def _narration_audio(vo_subdir: str, scene_id: str) -> tuple[str | None, float | None]:
    for ext in (".wav", ".m4a", ".mp3", ".aif", ".aiff"):
        p = util.VOICEOVER_DIR / vo_subdir / f"{scene_id}{ext}"
        if p.exists():
            dur = util.ffprobe_duration(p) if util.have_ffmpeg() else None
            return str(p), (round(dur, 2) if dur else None)
    return None, None


def _lines_to_captions(lines: list[str], duration: float, red_words: list[str]) -> list[dict]:
    if not lines:
        return []
    weights = [max(1, len(x)) for x in lines]
    durs = util.weighted_split(duration, weights, min_each=1.0)
    caps, t = [], 0.0
    for line, d in zip(lines, durs):
        reds = [w for w in red_words if w and w in line]
        caps.append({"start": round(t, 2), "end": round(t + d, 2), "text": line, "red": reds})
        t += d
    return caps


def _collect_red(scene: dict) -> list[str]:
    reds: list[str] = []
    for h in (scene.get("omikuji") or {}).get("highlights", []) or []:
        reds += h.get("red", []) or []
    return reds


def _scene_cards(scene: dict, duration: float) -> list[dict]:
    cards: list[dict] = []

    # タイトル / 章 / 答え / アウトロの中央テロップ
    if scene.get("onscreen"):
        lines = scene["onscreen"]
        n = len(lines)
        rendered = [{**it, "dy": int((i - (n - 1) / 2) * 118)} for i, it in enumerate(lines)]
        cards.append({"start": 0.4, "end": max(2.0, duration - 0.3), "lines": rendered})

    if scene.get("onscreen_list"):
        items = scene["onscreen_list"]
        n = len(items)
        rendered = [{"text": t, "style": "listitem", "dy": int((i - (n - 1) / 2) * 96)}
                    for i, t in enumerate(items)]
        cards.append({"start": 0.5, "end": max(2.5, duration - 0.3), "lines": rendered})

    # ロケーション札（左下・冒頭）
    loc = scene.get("location_card")
    if loc:
        name = loc["name"]
        if loc.get("reading"):
            name = f"{name}（{loc['reading']}）"
        cards.append({"start": 0.5, "end": min(duration, 4.0),
                      "lines": [{"text": name, "style": "location", "dy": 380},
                                {"text": loc.get("region", ""), "style": "location", "dy": 430}]})

    om = scene.get("omikuji") or {}
    if om.get("onscreen"):
        n = len(om["onscreen"])
        rendered = [{**it, "dy": int((i - (n - 1) / 2) * 96)} for i, it in enumerate(om["onscreen"])]
        cards.append({"start": max(0.5, duration * 0.28),
                      "end": min(duration, duration * 0.28 + 3.0), "lines": rendered})
    elif om.get("label"):
        cards.append({"start": max(0.5, duration * 0.28),
                      "end": min(duration, duration * 0.28 + 2.6),
                      "lines": [{"text": om["label"], "style": "onscreen", "dy": 0}]})

    if om.get("waka_reveal"):
        seq = om["waka_reveal"]
        seg = max(1.4, (duration * 0.4) / max(1, len(seq)))
        base = duration * 0.38
        for i, w in enumerate(seq):
            s = base + i * seg
            cards.append({"start": round(s, 2), "end": round(min(duration, s + seg + 0.6), 2),
                          "lines": [{"text": w, "style": "onscreen", "dy": 0}]})

    if om.get("highlights"):
        seq = om["highlights"]
        seg = max(1.8, (duration * 0.4) / max(1, len(seq)))
        base = duration * 0.45
        for i, h in enumerate(seq):
            s = base + i * seg
            cards.append({"start": round(s, 2), "end": round(min(duration, s + seg + 0.5), 2),
                          "lines": [{"text": h["text"], "style": "onscreen",
                                     "red": h.get("red", []), "dy": 300}]})

    # vtext：中央の縦書き（受け取った言葉）
    vt = scene.get("vtext") or []
    if vt:
        n = len(vt)
        seg = max(2.2, (duration * 0.42) / n)
        base = duration * 0.55
        style = "vtext_em" if scene.get("vtext_emphasis") else "vtext"
        for i, t in enumerate(vt):
            s = base + i * seg
            cards.append({"start": round(s, 2), "end": round(min(duration, s + seg + 1.0), 2),
                          "lines": [{"text": t, "style": style, "vertical": True, "dy": 0}]})
    return cards


def build(slug: str) -> dict:
    project = util.load_project()
    project["fonts"]["_resolved_mincho"] = util.resolve_font(project["fonts"]["mincho_priority"])
    project["fonts"]["_resolved_gothic"] = util.resolve_font(project["fonts"]["gothic_priority"])

    cut = util.cut(slug)
    cfg = util.load_yaml(util.CONFIG_DIR / cut["config"])
    narration = util.parse_narration_file(cut["narration"])
    groups = _load_manifest()
    picker = _Picker(groups)
    stills = project["stills"]
    res = [project["video"]["width"], project["video"]["height"]]
    fps = project["video"]["fps"]

    scenes_out: list[dict] = []
    t_cursor = 0.0
    warnings: list[str] = []

    for sc in cfg["scenes"]:
        sid = sc["id"]
        kind = sc.get("kind", "shrine")
        lines = narration.get(sc.get("narration_ref", ""), [])

        # --- 尺 -------------------------------------------------------
        vo_path, vo_dur = _narration_audio(cut["vo"], sid)
        if vo_dur:
            duration = vo_dur + 0.6
        elif sc.get("fixed_seconds"):
            duration = float(sc["fixed_seconds"])
        elif lines:
            duration = sum(util.estimate_line_seconds(x) for x in lines)
        else:
            duration = {"title": 8.0, "interstitial": 6.0, "outro": 10.0}.get(kind, 6.0)
        duration = round(max(duration, stills["min_dur"]), 2)

        # --- ショット -------------------------------------------------
        shots: list[dict] = []
        om = sc.get("omikuji") or {}
        has_om = bool(om.get("highlights") or om.get("label") or om.get("waka_reveal"))
        grp = sc.get("group", project["assets"]["unknown_group"])

        if kind == "shrine":
            body = duration * (0.55 if has_om else 1.0)
            per = util.weighted_split(body, [1, 1], min_each=stills["min_dur"] * 0.7)
            for d in per:
                rec = picker.next(grp)
                if rec:
                    shots.append(_shot(rec, d, _KB_CYCLE[len(shots) % 4]))
                else:
                    shots.append(_placeholder(sc.get("location_card", {}).get("name", grp), d))
                    warnings.append(f"[{sid}] グループ '{grp}' に素材なし → placeholder")
            if has_om:
                orec = picker.next(om.get("group")) if om.get("group") else picker.next(grp)
                om_total = duration - body
                if orec:
                    ov = round(stills["omikuji_overview_dur"], 2)
                    zoom = max(stills["min_dur"] * 0.7, om_total - ov)
                    shots.append(_shot(orec, ov, "none", allow_repeat=True))
                    shots.append(_shot(orec, zoom, "in", allow_repeat=True))
                else:
                    shots.append(_placeholder(om.get("label", "おみくじ"), om_total))
                    warnings.append(f"[{sid}] おみくじ素材 '{om.get('group')}' なし → placeholder")
        else:
            # title / intro / turn / summary_woman / outro：1枚をゆっくり
            rec = picker.next(grp)
            kb = "in" if kind in ("summary_woman", "title") else "none"
            if rec:
                shots.append(_shot(rec, duration, kb))
            else:
                lbl = {"title": cfg.get("title_text", "叶結び"),
                       "summary_woman": "（女性静止画＝バナー）",
                       "turn": "そして翌日"}.get(kind, sid)
                shots.append(_placeholder(lbl, duration))
                warnings.append(f"[{sid}] グループ '{grp}' に素材なし → placeholder")

        # 尺合わせ
        s_sum = sum(s["dur"] for s in shots)
        if shots and abs(s_sum - duration) > 0.01:
            shots[-1]["dur"] = round(shots[-1]["dur"] + (duration - s_sum), 2)

        captions = _lines_to_captions(lines, duration, _collect_red(sc))
        cards = _scene_cards(sc, duration)
        bgm_key = sc.get("bgm") or "op"

        scenes_out.append({
            "id": sid, "kind": kind, "start": round(t_cursor, 2), "duration": duration,
            "shots": shots,
            "audio": {"narration": vo_path, "narration_dur": vo_dur, "bgm_key": bgm_key},
            "captions": captions, "cards": cards,
            "nat_sound_break": bool(sc.get("nat_sound_break")),
        })
        t_cursor += duration

    return {
        "slug": slug,
        "theme": cfg.get("theme", ""),
        "resolution": res, "fps": fps,
        "total_duration": round(t_cursor, 2),
        "fonts": {"mincho": project["fonts"]["_resolved_mincho"],
                  "gothic": project["fonts"]["_resolved_gothic"]},
        "scenes": scenes_out, "warnings": warnings,
    }


def main(slug: str) -> Path:
    timeline = build(slug)
    out_slug = util.cut(slug)["out"]
    out = util.OUTPUTS_DIR / out_slug / f"timeline_{out_slug}.json"
    util.write_json(out, timeline)
    mins = timeline["total_duration"] / 60
    print(f"timeline [{slug}]: {len(timeline['scenes'])}シーン / 合計 {mins:.1f}分 → {out}")
    if timeline["warnings"]:
        print(f"  ⚠ {len(timeline['warnings'])}件の素材不足（placeholderで継続）")
        for w in timeline["warnings"][:12]:
            print("    " + w)
    return out


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "ishikawa")
