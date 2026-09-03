"""共通ヘルパ。"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML が必要です:  pip install -r video/requirements.txt", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent.parent          # video/
CONFIG_DIR = ROOT / "config"
SCRIPTS_DIR = ROOT / "scripts"
ASSETS_DIR = ROOT / "assets"
VOICEOVER_DIR = ROOT / "voiceover"
BGM_DIR = ROOT / "supplied_audio"
OUTPUTS_DIR = ROOT / "outputs"


# ---------------------------------------------------------------- config / io
def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_project() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "project.yaml")


def load_day_config(day: int) -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / f"day{day}.yaml")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------- cuts registry
# 1本の書き出し単位（slug）→ 設定・原稿・音声・出力の対応。
CUTS: dict[str, dict[str, str]] = {
    "ishikawa": {"config": "ishikawa.yaml", "narration": "ishikawa_narration.txt",
                 "vo": "ishikawa", "out": "ishikawa"},
    # 旧2本立て（後方互換・参照用）
    "day1": {"config": "day1.yaml", "narration": "day1_narration.txt", "vo": "day1", "out": "day1"},
    "day2": {"config": "day2.yaml", "narration": "day2_narration.txt", "vo": "day2", "out": "day2"},
}


def cut(slug: str) -> dict[str, str]:
    if slug not in CUTS:
        raise KeyError(f"unknown cut: {slug} (choices: {', '.join(CUTS)})")
    return CUTS[slug]


# ------------------------------------------------------------- narration read
def parse_narration_file(name: str) -> dict[str, list[str]]:
    """scripts/<name> を {scene_id: [行, ...]} に。

    '#' 始まりはコメント、'[id]' がブロック見出し。空行は行区切り扱い。
    """
    path = SCRIPTS_DIR / name
    blocks: dict[str, list[str]] = {}
    cur: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.startswith("#"):
            continue
        m = re.match(r"^\[([A-Za-z0-9_]+)\]\s*$", line)
        if m:
            cur = m.group(1)
            blocks[cur] = []
            continue
        if cur is None:
            continue
        if line.strip() == "":
            continue
        blocks[cur].append(line.strip())
    return blocks


def parse_narration(day: int) -> dict[str, list[str]]:
    """後方互換: dayN のナレーションを読む。"""
    return parse_narration_file(f"day{day}_narration.txt")


# ------------------------------------------------------------ ffmpeg wrappers
def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def run(cmd: list[str], quiet: bool = True) -> subprocess.CompletedProcess:
    if not quiet:
        print("+ " + " ".join(str(c) for c in cmd))
    return subprocess.run(
        [str(c) for c in cmd],
        check=True,
        capture_output=True,
        text=True,
    )


def ffprobe_duration(path: Path) -> float:
    out = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def ffprobe_dimensions(path: Path) -> tuple[int, int]:
    out = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0", str(path),
    ])
    try:
        w, h = out.stdout.strip().split("x")[:2]
        return int(w), int(h)
    except ValueError:
        return 0, 0


# ---------------------------------------------------------------- fonts
def resolve_font(priority: list[str]) -> str:
    """fc-list で使えるフォント名を優先順に探す。無ければ先頭を返す（フォールバック）。"""
    try:
        listing = subprocess.run(
            ["fc-list", ":", "family"], capture_output=True, text=True
        ).stdout
    except FileNotFoundError:
        return priority[0]
    families = listing.lower()
    for name in priority:
        if name.lower() in families:
            return name
    return priority[0]


# ------------------------------------------------------ 尺見積り（かなベース）
_KANA_ONLY = re.compile(r"[ぁ-んァ-ヶー０-９0-9A-Za-z]")


def estimate_line_seconds(text: str, sec_per_char: float = 0.16, pad: float = 0.5) -> float:
    """録音音声が無いときのナレーション尺のざっくり見積り。

    句読点・記号でわずかに間を足す。あくまでドラフト用（実録音があればそちらの実尺を使う）。
    """
    chars = len(re.sub(r"\s", "", text))
    pause = 0.18 * len(re.findall(r"[、。！？「」…]", text))
    return round(chars * sec_per_char + pause + pad, 2)


def weighted_split(total: float, weights: list[float], min_each: float = 0.8) -> list[float]:
    """total 秒を weights 比で分配。各要素 min_each 秒を確保。"""
    if not weights:
        return []
    n = len(weights)
    if total < min_each * n:
        return [total / n] * n
    base = min_each * n
    rest = total - base
    wsum = sum(weights) or 1.0
    return [round(min_each + rest * (w / wsum), 3) for w in weights]
