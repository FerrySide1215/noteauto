"""素材スキャン → inventory + manifest 雛形（仕様書 §3）。

- ファイル名 / 静止画・動画 / 解像度 / 動画尺 / EXIF DateTimeOriginal / 撮影日時
  / 縦横方向 / GPS / 重複判定（average hash のハミング距離）
- 撮影日時で時系列化し、DAY1/DAY2 を日付で分類。
- 神社・寺を機械判定はしない（推測しない）。グループは manifest 雛形で人が埋める。

出力:
  outputs/asset_inventory.json
  outputs/asset_inventory.csv
  assets/manifest.yaml   （未作成なら雛形を生成。既存なら上書きしない）
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

from . import util

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp"}
VIDEO_EXT = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}

try:
    from PIL import Image, ExifTags
    _HAVE_PIL = True
except ImportError:
    _HAVE_PIL = False

_EXIF_TAG = {v: k for k, v in ExifTags.TAGS.items()} if _HAVE_PIL else {}


def _ahash(img) -> int:
    """8x8 average hash（perceptual hash 簡易版）。重複検出用。"""
    g = img.convert("L").resize((8, 8))
    px = list(g.getdata())
    avg = sum(px) / len(px)
    bits = 0
    for i, p in enumerate(px):
        if p >= avg:
            bits |= 1 << i
    return bits


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _exif(img) -> dict:
    out: dict = {}
    try:
        raw = img._getexif() or {}
    except Exception:
        raw = {}
    for tag_id, val in raw.items():
        name = ExifTags.TAGS.get(tag_id, str(tag_id))
        out[name] = val
    return out


def _parse_dt(exif: dict) -> str | None:
    for key in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
        v = exif.get(key)
        if v:
            try:
                return datetime.strptime(str(v), "%Y:%m:%d %H:%M:%S").isoformat()
            except ValueError:
                continue
    return None


def _gps(exif: dict):
    gps = exif.get("GPSInfo")
    if not gps:
        return None

    def conv(coord, ref):
        d, m, s = [float(x[0]) / float(x[1]) if isinstance(x, tuple) else float(x) for x in coord]
        val = d + m / 60 + s / 3600
        if ref in ("S", "W"):
            val = -val
        return round(val, 6)

    try:
        lat = conv(gps[2], gps[1])
        lon = conv(gps[4], gps[3])
        return {"lat": lat, "lon": lon}
    except Exception:
        return None


def scan(src: Path) -> list[dict]:
    items: list[dict] = []
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in IMAGE_EXT and ext not in VIDEO_EXT:
            continue
        rec: dict = {
            "file": str(path.relative_to(src)),
            "abspath": str(path),
            "kind": "image" if ext in IMAGE_EXT else "video",
            "width": None, "height": None, "orientation": None,
            "duration": None, "shot_at": None, "gps": None, "ahash": None,
        }
        if rec["kind"] == "image" and _HAVE_PIL:
            try:
                with Image.open(path) as im:
                    rec["width"], rec["height"] = im.size
                    rec["orientation"] = "portrait" if im.height > im.width else "landscape"
                    exif = _exif(im)
                    rec["shot_at"] = _parse_dt(exif)
                    rec["gps"] = _gps(exif)
                    rec["ahash"] = _ahash(im)
            except Exception as e:  # pragma: no cover
                rec["error"] = str(e)
        elif rec["kind"] == "video" and util.have_ffmpeg():
            w, h = util.ffprobe_dimensions(path)
            rec["width"], rec["height"] = w or None, h or None
            rec["orientation"] = "portrait" if (h or 0) > (w or 0) else "landscape"
            rec["duration"] = round(util.ffprobe_duration(path), 2)
        items.append(rec)
    return items


def dedup(items: list[dict], threshold: int) -> None:
    """ahash のハミング距離が threshold 以下なら duplicate_of を付与。"""
    seen: list[tuple[int, str]] = []
    for rec in items:
        h = rec.get("ahash")
        if h is None:
            continue
        dup = None
        for sh, sfile in seen:
            if _hamming(h, sh) <= threshold:
                dup = sfile
                break
        if dup:
            rec["duplicate_of"] = dup
        else:
            seen.append((h, rec["file"]))


def classify_day(items: list[dict], day1_date: str, day2_date: str) -> None:
    for rec in items:
        day = None
        if rec.get("shot_at"):
            d = rec["shot_at"][:10]
            if d == day1_date:
                day = 1
            elif d == day2_date:
                day = 2
        rec["day"] = day


def _sort_key(rec: dict):
    return (rec.get("shot_at") or "9999", rec["file"])


def write_manifest_skeleton(items: list[dict], project: dict) -> Path:
    """グループ未割当の雛形を assets/manifest.yaml に出力（既存は上書きしない）。"""
    path = util.ASSETS_DIR / "manifest.yaml"
    if path.exists():
        return path
    lines = [
        "# 素材 → グループ割当。各 file の group: を埋める（推測での自動判定はしない）。",
        "# 単一動画(ishikawa)のグループ:",
        "#   kinkengu / kinkengu_omikuji",
        "#   shirayama / shirayama_kaiun_omikuji / shirayama_futsu_omikuji",
        "#   hattori / hattori_omikuji",
        "#   natadera / natadera_omikuji",
        "#   uhashi / uhashi_omikuji",
        "#   ataka / ataka_omikuji",
        "#   title_bg（OP背景） / broll（導入・転換・ED） / woman（総括=バナーの女性）",
        "# omikuji 系にはおみくじの寄りカットを。判別不能は travel_broll。",
        "assets:",
    ]
    for rec in sorted(items, key=_sort_key):
        if rec.get("duplicate_of"):
            continue  # 重複は雛形から除外
        day = rec.get("day")
        hint = f"day{day}" if day else "?"
        lines.append(f"  - file: \"{rec['file']}\"")
        lines.append(f"    day: {day if day else 'null'}   # {rec.get('shot_at') or 'no-exif'} ({rec['kind']}, {hint})")
        lines.append("    group: \"\"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(src_dir: str) -> None:
    src = Path(src_dir).expanduser().resolve()
    if not src.is_dir():
        print(f"素材フォルダが見つかりません: {src}", file=sys.stderr)
        sys.exit(1)
    if not _HAVE_PIL:
        print("[warn] Pillow が無いため画像のEXIF/重複判定はスキップされます。"
              "  pip install -r video/requirements.txt", file=sys.stderr)

    project = util.load_project()
    a = project["assets"]
    items = scan(src)
    dedup(items, a["dedup_hamming_threshold"])
    classify_day(items, a["day1_date"], a["day2_date"])
    items.sort(key=_sort_key)

    util.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    util.write_json(util.OUTPUTS_DIR / "asset_inventory.json", items)

    cols = ["file", "kind", "day", "width", "height", "orientation",
            "duration", "shot_at", "gps", "duplicate_of"]
    with open(util.OUTPUTS_DIR / "asset_inventory.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for rec in items:
            row = dict(rec)
            row["gps"] = "" if not rec.get("gps") else f"{rec['gps']['lat']},{rec['gps']['lon']}"
            w.writerow(row)

    mpath = write_manifest_skeleton(items, project)
    n_dup = sum(1 for r in items if r.get("duplicate_of"))
    n1 = sum(1 for r in items if r.get("day") == 1)
    n2 = sum(1 for r in items if r.get("day") == 2)
    print(f"スキャン完了: {len(items)}件  (DAY1={n1} DAY2={n2} 重複={n_dup} 日付不明={len(items)-n1-n2})")
    print(f"  → {util.OUTPUTS_DIR/'asset_inventory.json'}")
    print(f"  → {util.OUTPUTS_DIR/'asset_inventory.csv'}")
    print(f"  → {mpath} {'(既存を保持)' if 'existed' else ''}")
    print("次: manifest.yaml の group を埋めてから  `python -m build.cli day1 --step timeline`")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m build.scan_assets <素材フォルダ>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
