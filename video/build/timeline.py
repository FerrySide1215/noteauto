"""EDL(config) + manifest + ナレーション → outputs/dayN/timeline_dayN.json

素材が無いグループは placeholder ショット（生成り札）で埋める（黒画面を入れない・§25）。
おみくじショットは「全体→寄り」を同一写真で行う（§6）ため allow_repeat=True を付ける。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import util


def _load_manifest() -> dict[str, list[dict]]:
    """assets/manifest.yaml → group -> [ {file, abspath, kind, day}, ... ]"""
    path = util.ASSETS_DIR / "manifest.yaml"
    groups: dict[str, list[dict]] = {}
    if not path.exists():
        return groups
    data = util.load_yaml(path) or {}
    # inventory から abspath / kind を引く
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
    """グループから順番にファイルを取り出す（尽きたら循環）。"""
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

    def has(self, group: str) -> bool:
        return bool(self.groups.get(group))


def _placeholder(label: str, dur: float) -> dict:
    return {"path": None, "type": "placeholder", "label": label,
            "dur": round(dur, 2), "kenburns": "none"}


def _shot(rec: dict, dur: float, kb: str, allow_repeat: bool = False) -> dict:
    return {"path": rec["abspath"], "type": rec.get("kind", "image"),
            "file": rec["file"], "dur": round(dur, 2), "kenburns": kb,
            "allow_repeat": allow_repeat}


_KB_CYCLE = ["in", "out", "left", "right"]


def _narration_audio(day: int, scene_id: str) -> tuple[str | None, float | None]:
    for ext in (".wav", ".m4a", ".mp3", ".aif", ".aiff"):
        p = util.VOICEOVER_DIR / f"day{day}" / f"{scene_id}{ext}"
        if p.exists():
            dur = util.ffprobe_duration(p) if util.have_ffmpeg() else None
            return str(p), (round(dur, 2) if dur else None)
    return None, None


def _lines_to_captions(lines: list[str], duration: float, red_words: list[str],
                       stills: dict) -> list[dict]:
    if not lines:
        return []
    weights = [max(1, len(x)) for x in lines]
    durs = util.weighted_split(duration, weights, min_each=1.0)
    caps, t = [], 0.0
    for line, d in zip(lines, durs):
        reds = [w for w in red_words if w and w in line]
        caps.append({"start": round(t, 2), "end": round(t + d, 2),
                     "text": line, "red": reds})
        t += d
    return caps


def _collect_red(scene: dict) -> list[str]:
    reds: list[str] = []
    om = scene.get("omikuji") or {}
    for h in om.get("highlights", []) or []:
        reds += h.get("red", []) or []
    return reds


def _scene_cards(scene: dict, project: dict, duration: float) -> list[dict]:
    """ロケーション札・番号テロップ・和歌・答え・一覧などを時間割付。"""
    cards: list[dict] = []
    kind = scene.get("kind")

    # タイトル / 答え / アウトロ：中央に据える
    if scene.get("onscreen"):
        lines = scene["onscreen"]
        # role from/to（矢印表現）は上下に配置
        rendered = []
        n = len(lines)
        for i, item in enumerate(lines):
            dy = int((i - (n - 1) / 2) * 110)
            rendered.append({**item, "dy": dy})
        cards.append({"start": 0.4, "end": max(2.0, duration - 0.3), "lines": rendered})

    # 一覧（共通点 / recap）
    if scene.get("onscreen_list"):
        items = scene["onscreen_list"]
        n = len(items)
        rendered = [{"text": t, "style": "listitem", "dy": int((i - (n - 1) / 2) * 96)}
                    for i, t in enumerate(items)]
        cards.append({"start": 0.5, "end": max(2.5, duration - 0.3), "lines": rendered})

    # 2カラム recap
    if scene.get("onscreen_columns"):
        cols = scene["onscreen_columns"]
        lines = []
        for ci, colblock in enumerate(cols):
            head = colblock["head"]
            items = colblock["items"]
            lines.append({"text": f"{head}", "style": "chapter", "dy": -220})
        # シンプルに見出しのみカード化（項目はナレーションで送る）
        cards.append({"start": 0.5, "end": max(3.0, duration - 0.3),
                      "lines": [{"text": " ／ ".join(c["head"] for c in cols),
                                 "style": "chapter", "dy": -180}]})

    # ロケーション札（左下・冒頭 3 秒）
    loc = scene.get("location_card")
    if loc:
        name = loc["name"] + ("（表記要確認）" if loc.get("name_unconfirmed") else "")
        region = loc.get("region", "")
        cards.append({"start": 0.5, "end": min(duration, 3.8),
                      "lines": [{"text": f"{name}", "style": "location", "dy": 380},
                                {"text": region, "style": "location", "dy": 430}]})

    # おみくじの番号・小吉・卦テロップ
    om = scene.get("omikuji") or {}
    if om.get("onscreen"):
        n = len(om["onscreen"])
        rendered = [{**it, "dy": int((i - (n - 1) / 2) * 96)} for i, it in enumerate(om["onscreen"])]
        cards.append({"start": max(0.5, duration * 0.30),
                      "end": min(duration, duration * 0.30 + 3.0), "lines": rendered})
    elif om.get("label"):
        cards.append({"start": max(0.5, duration * 0.30),
                      "end": min(duration, duration * 0.30 + 2.6),
                      "lines": [{"text": om["label"], "style": "onscreen", "dy": 0}]})

    # 和歌の逐次提示
    if om.get("waka_reveal"):
        seq = om["waka_reveal"]
        seg = max(1.5, (duration * 0.5) / max(1, len(seq)))
        base = duration * 0.45
        for i, w in enumerate(seq):
            s = base + i * seg
            cards.append({"start": round(s, 2), "end": round(min(duration, s + seg + 0.8), 2),
                          "lines": [{"text": w, "style": "onscreen", "dy": 0}]})

    # おみくじ原文の要点（赤ハイライト）— 画面中央下寄りに短く
    if om.get("highlights"):
        seq = om["highlights"]
        seg = max(2.0, (duration * 0.45) / max(1, len(seq)))
        base = duration * 0.5
        for i, h in enumerate(seq):
            s = base + i * seg
            cards.append({"start": round(s, 2), "end": round(min(duration, s + seg + 0.5), 2),
                          "lines": [{"text": h["text"], "style": "onscreen",
                                     "red": h.get("red", []), "dy": 300}]})
    return cards


def build(day: int) -> dict:
    project = util.load_project()
    # フォント解決（ASS が参照）
    project["fonts"]["_resolved_mincho"] = util.resolve_font(project["fonts"]["mincho_priority"])
    project["fonts"]["_resolved_gothic"] = util.resolve_font(project["fonts"]["gothic_priority"])

    cfg = util.load_day_config(day)
    narration = util.parse_narration(day)
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

        # --- 尺の決定 -------------------------------------------------
        vo_path, vo_dur = _narration_audio(day, sid)
        if vo_dur:
            duration = vo_dur + 0.6
        elif lines:
            duration = sum(util.estimate_line_seconds(x) for x in lines)
        else:
            duration = {"title": 4.0, "interstitial": 4.0, "outro": 6.0,
                        "answer": 6.0}.get(kind, 5.0)
        if sc.get("max_seconds"):
            duration = min(duration, float(sc["max_seconds"]))
        duration = round(max(duration, stills["min_dur"]), 2)

        # --- ショット割付 ---------------------------------------------
        shots: list[dict] = []
        montage = sc.get("montage_sequence") or sc.get("timeline_sequence")
        if kind == "title":
            # タイトルは代表ブロールで背景を作る
            grp = sc.get("group", "broll_day%d" % day)
            rec = picker.next(grp) or picker.next("montage")
            shots.append(_shot(rec, duration, "in") if rec else _placeholder(cfg["title"]["chapter"], duration))
        elif montage:
            per = util.weighted_split(duration, [1] * len(montage), min_each=stills["min_dur"] * 0.6)
            for grp, d in zip(montage, per):
                rec = picker.next(grp)
                if rec:
                    shots.append(_shot(rec, d, _KB_CYCLE[len(shots) % len(_KB_CYCLE)]))
                else:
                    shots.append(_placeholder(grp, d))
                    warnings.append(f"[{sid}] グループ '{grp}' に素材なし → placeholder")
        else:
            grp = sc.get("group", util.load_project()["assets"]["unknown_group"])
            om = sc.get("omikuji") or {}
            om_grp = om.get("group")
            # 通常ショット（境内など）＋おみくじ寄り
            n_shots = 2 if kind in ("shrine",) else 1
            has_om = bool(om.get("highlights") or om.get("label") or om.get("waka_reveal"))
            body = duration * (0.55 if has_om else 1.0)
            per = util.weighted_split(body, [1] * n_shots, min_each=stills["min_dur"] * 0.7)
            for d in per:
                rec = picker.next(grp)
                if rec:
                    shots.append(_shot(rec, d, _KB_CYCLE[len(shots) % len(_KB_CYCLE)]))
                else:
                    shots.append(_placeholder(sc.get("location_card", {}).get("name", grp), d))
                    warnings.append(f"[{sid}] グループ '{grp}' に素材なし → placeholder")
            if has_om:
                orec = picker.next(om_grp) if om_grp else None
                orec = orec or (picker.next(grp))
                om_total = duration - body
                if orec:
                    # 全体→寄り（同一写真の連続使用は §6 の意図的演出）
                    ov = round(stills["omikuji_overview_dur"], 2)
                    zoom = max(stills["min_dur"] * 0.7, om_total - ov)
                    shots.append(_shot(orec, ov, "none", allow_repeat=True))
                    shots.append(_shot(orec, zoom, "in", allow_repeat=True))
                else:
                    shots.append(_placeholder(om.get("label", "おみくじ"), om_total))
                    warnings.append(f"[{sid}] おみくじ素材 '{om_grp}' なし → placeholder")

        # ショット尺の合計を duration に一致させる（丸め誤差補正）
        s_sum = sum(s["dur"] for s in shots)
        if shots and abs(s_sum - duration) > 0.01:
            shots[-1]["dur"] = round(shots[-1]["dur"] + (duration - s_sum), 2)

        # --- 字幕・テロップ -------------------------------------------
        red_words = _collect_red(sc)
        captions = _lines_to_captions(lines, duration, red_words, stills)
        cards = _scene_cards(sc, project, duration)

        # --- BGM ------------------------------------------------------
        bgm_key = sc.get("bgm") or cfg.get("bgm") or f"day{day}"

        scenes_out.append({
            "id": sid,
            "kind": kind,
            "start": round(t_cursor, 2),
            "duration": duration,
            "shots": shots,
            "audio": {"narration": vo_path, "narration_dur": vo_dur, "bgm_key": bgm_key},
            "captions": captions,
            "cards": cards,
            "nat_sound_break": bool(sc.get("nat_sound_break")),
            "provenance_warning": sc.get("provenance_warning"),
        })
        t_cursor += duration

    timeline = {
        "day": day,
        "theme": cfg["theme"],
        "resolution": res,
        "fps": fps,
        "total_duration": round(t_cursor, 2),
        "fonts": {"mincho": project["fonts"]["_resolved_mincho"],
                  "gothic": project["fonts"]["_resolved_gothic"]},
        "scenes": scenes_out,
        "warnings": warnings,
    }
    return timeline


def main(day: int) -> Path:
    timeline = build(day)
    out = util.OUTPUTS_DIR / f"day{day}" / f"timeline_day{day}.json"
    util.write_json(out, timeline)
    mins = timeline["total_duration"] / 60
    print(f"timeline DAY{day}: {len(timeline['scenes'])}シーン / 合計 {mins:.1f}分 → {out}")
    if timeline["warnings"]:
        print(f"  ⚠ {len(timeline['warnings'])}件の素材不足（placeholderで継続）:")
        for w in timeline["warnings"][:12]:
            print("    " + w)
    return out


if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
