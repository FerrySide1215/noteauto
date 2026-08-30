"""レンダー前チェック（仕様書 §25）。

timeline.json + inventory + day config から機械的に検査できるものを検査する。
画素レベルの確認（人物トリミング・おみくじ文字の見切れ等）は最終目視が必要なため、
チェックリスト項目として "manual" で提示する。
"""
from __future__ import annotations

from pathlib import Path

from . import util

# 正式名称（誤字チェック用の正解表）
CANON_NAMES = {
    "金劔宮", "白山比咩神社", "服部神社",
    "那谷寺", "うはし神社", "安宅住吉神社",
}


def _inventory_day_index() -> dict[str, int | None]:
    inv_path = util.OUTPUTS_DIR / "asset_inventory.json"
    if not inv_path.exists():
        return {}
    return {r["file"]: r.get("day") for r in util.read_json(inv_path)}


def check(day: int) -> tuple[list[str], list[str], list[str]]:
    """returns (errors, warnings, manual_checklist)"""
    errors: list[str] = []
    warnings: list[str] = []
    manual: list[str] = []

    tl_path = util.OUTPUTS_DIR / f"day{day}" / f"timeline_day{day}.json"
    if not tl_path.exists():
        return ([f"timeline が未生成: {tl_path}"], [], [])
    timeline = util.read_json(tl_path)
    project = util.load_project()
    cfg = util.load_day_config(day)
    inv_day = _inventory_day_index()

    # 尺（目標 10〜14分 ±2）
    lo, hi = cfg["target_minutes"]
    mins = timeline["total_duration"] / 60
    if mins < lo - 2 or mins > hi + 2:
        warnings.append(f"合計尺 {mins:.1f}分 が目標 {lo}〜{hi}分(±2) を外れています")

    prev_file = None
    for scene in timeline["scenes"]:
        sid = scene["id"]
        for shot in scene["shots"]:
            f = shot.get("file")
            # 黒画面混入チェック：placeholder はラベル必須（黒ではない）
            if shot["type"] == "placeholder" and not shot.get("label"):
                errors.append(f"[{sid}] ラベルなし placeholder（黒画面の恐れ）")
            # 同じ写真の連続使用（おみくじの意図的連続は allow_repeat で除外）
            if f and f == prev_file and not shot.get("allow_repeat"):
                errors.append(f"[{sid}] 同じ写真を連続使用: {f}")
            # DAY 混入チェック
            if f and f in inv_day and inv_day[f] not in (None, day):
                errors.append(f"[{sid}] DAY{inv_day[f]}の素材がDAY{day}に混入: {f}")
            prev_file = f if f else prev_file
        # 素材不足（placeholder）→ warning
        n_ph = sum(1 for s in scene["shots"] if s["type"] == "placeholder")
        if n_ph:
            warnings.append(f"[{sid}] placeholder {n_ph}枚（実素材で差し替え推奨）")

        # 字幕：2行以内 / 長すぎ
        for cap in scene.get("captions", []):
            if cap["text"].count("\n") >= 2:
                errors.append(f"[{sid}] 字幕が3行以上: {cap['text'][:20]}…")
            if len(cap["text"].replace("\n", "")) > 40:
                warnings.append(f"[{sid}] 字幕が長め({len(cap['text'])}字) 折返し確認: {cap['text'][:24]}…")

        # 神社名の誤字
        loc = None
        for card in scene.get("cards", []):
            for ln in card["lines"]:
                t = ln["text"].replace("（表記要確認）", "")
                for canon in CANON_NAMES:
                    # 部分一致で近いのに一致しない綴りを検出（簡易）
                    if canon[:2] in t and canon not in t and ln.get("style") == "location":
                        warnings.append(f"[{sid}] 神社名の綴り要確認: '{t}' (正: {canon}?)")

        # 出典未確認の警告
        if scene.get("provenance_warning"):
            warnings.append(f"[{sid}] {scene['provenance_warning']}")

        # 無音が不自然に長くないか（字幕もナレーションも無いのに尺が長い＝実質無音）
        if not scene["audio"]["narration"] and not scene["captions"] and scene["duration"] > 6:
            warnings.append(f"[{sid}] 字幕もナレーションも無く {scene['duration']:.0f}秒（無音が長い恐れ）")

    # 目視必須項目
    manual += [
        "画像が縦横逆になっていない（縦写真の扱い）",
        "人物が不自然にトリミングされていない",
        "おみくじ文字が画面外に切れていない",
        "字幕が画面最下部ギリギリに被っていない",
        "音割れ（クリッピング）が無い",
        "おみくじ原文の文言が原本どおり（書き換えなし）",
    ]
    # 縦写真の存在を機械的に拾って注意喚起
    inv_path = util.OUTPUTS_DIR / "asset_inventory.json"
    if inv_path.exists():
        portraits = [r["file"] for r in util.read_json(inv_path)
                     if r.get("orientation") == "portrait" and r.get("day") == day]
        if portraits:
            warnings.append(f"縦向き素材 {len(portraits)}枚あり（16:9では余白/ぼかし背景処理を確認）")

    return errors, warnings, manual


def main(day: int) -> int:
    errors, warnings, manual = check(day)
    print(f"=== preflight DAY{day} ===")
    if errors:
        print(f"[ERROR] {len(errors)}件:")
        for e in errors:
            print("  ✗ " + e)
    else:
        print("[ERROR] なし")
    if warnings:
        print(f"[WARN] {len(warnings)}件:")
        for w in warnings:
            print("  ! " + w)
    print("[目視チェック]（レンダー後に確認）:")
    for m in manual:
        print("  □ " + m)
    return 1 if errors else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 1))
