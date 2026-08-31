"""ffmpeg レンダー（Ken Burns / 字幕焼込 / ラウドネス正規化）。

出力（各 DAY）:
  kanau_musubi_ishikawa_dayN.mp4            本編（テロップ＋ナレーション字幕＋音声）
  kanau_musubi_ishikawa_dayN_no_caption.mp4 ナレーション字幕なし（テロップは保持）
  kanau_musubi_ishikawa_dayN_preview.mp4     720p 軽量プレビュー
  dayN.srt                                   （srt モジュールが生成）

ffmpeg / 日本語フォントが必要。無い環境では理由を表示して中断する。
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from . import ass, util


def font_file(family: str) -> str | None:
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", family],
                             capture_output=True, text=True).stdout.strip()
        return out or None
    except FileNotFoundError:
        return None


def _drawtext_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _kenburns_vf(shot: dict, res: list[int], fps: int) -> str:
    w, h = res
    frames = max(1, round(shot["dur"] * fps))
    st = 1.02
    en = 1.11
    kb = shot.get("kenburns", "in")
    # 上流でオーバースキャン（ズーム/パン用の余白）
    pre = f"scale={int(w*1.35)}:{int(h*1.35)}:force_original_aspect_ratio=increase," \
          f"crop={int(w*1.35)}:{int(h*1.35)}"
    if kb == "none":
        z = f"{(st+en)/2:.4f}"
        xy = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif kb == "out":
        z = f"if(lte(on,{frames}),{en}-({en}-{st})*on/{frames},{st})"
        xy = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif kb in ("left", "right"):
        z = f"{(st+en)/2:.4f}"
        prog = f"on/{frames}" if kb == "right" else f"(1-on/{frames})"
        xy = f"x='(iw-iw/zoom)*{prog}':y='ih/2-(ih/zoom/2)'"
    else:  # in
        z = f"if(lte(on,{frames}),{st}+({en}-{st})*on/{frames},{en})"
        xy = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    return (f"{pre},zoompan=z='{z}':{xy}:d={frames}:s={w}x{h}:fps={fps},"
            f"setsar=1,format=yuv420p")


def _render_shot(shot: dict, res: list[int], fps: int, tmp: Path, idx: int,
                 project: dict) -> Path:
    w, h = res
    out = tmp / f"shot_{idx:03d}.mp4"
    common = ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
              "-pix_fmt", "yuv420p", "-r", str(fps), "-an"]
    if shot["type"] == "placeholder":
        # 素材不足の札は「無地カード（生成り）」だけを敷く。ロケーション名・おみくじ・
        # 字幕は ASS レイヤーで焼き込まれるので文字はそちらが担う。
        # （drawtext は fontfile の .ttc 解決やテキストのエスケープに環境依存で落ちるため使わない。
        #   黒画面は入れない=§25 は満たし、「未挿入」通知は preflight 警告が担う。）
        vf = f"color=c=0xF2F4F5:s={w}x{h}:r={fps},format=yuv420p"
        util.run(["ffmpeg", "-y", "-f", "lavfi", "-i", vf, "-t", str(shot["dur"]),
                  *common, str(out)])
    elif shot["type"] == "video":
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0xF2F4F5,setsar=1,fps={fps},format=yuv420p")
        util.run(["ffmpeg", "-y", "-i", shot["path"], "-t", str(shot["dur"]),
                  "-vf", vf, *common, str(out)])
    else:  # image
        vf = _kenburns_vf(shot, res, fps)
        util.run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(fps),
                  "-t", str(shot["dur"]), "-i", shot["path"], "-vf", vf, *common, str(out)])
    return out


def _concat(clips: list[Path], out: Path, tmp: Path) -> None:
    listfile = tmp / "concat.txt"
    listfile.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
    util.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
              "-c", "copy", str(out)])


def _find_bgm(bgm_key: str, project: dict) -> Path | None:
    patt = project["bgm"].get(bgm_key)
    if not patt:
        return None
    stem = patt.split(".")[0]
    for p in util.BGM_DIR.glob(stem + ".*"):
        if p.suffix.lower() in (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"):
            return p
    return None


def _build_audio(timeline: dict, project: dict, tmp: Path) -> Path:
    a = project["audio"]
    total = timeline["total_duration"]
    sr = a["sample_rate"]
    inputs: list[str] = []
    filters: list[str] = []
    idx = 0
    narration_labels: list[str] = []

    for scene in timeline["scenes"]:
        vo = scene["audio"]["narration"]
        if vo:
            inputs += ["-i", vo]
            delay = int(scene["start"] * 1000)
            filters.append(f"[{idx}:a]aresample={sr},adelay={delay}|{delay}[n{idx}]")
            narration_labels.append(f"[n{idx}]")
            idx += 1

    # BGM（先頭シーンの bgm_key をベース。切替は簡易化）
    bgm_path = None
    for scene in timeline["scenes"]:
        bgm_path = _find_bgm(scene["audio"]["bgm_key"], project)
        if bgm_path:
            break

    out = tmp / "audio.m4a"

    if narration_labels:
        filters.append(f"{''.join(narration_labels)}amix=inputs={len(narration_labels)}:"
                       f"normalize=0:duration=longest[narr]")
    if bgm_path:
        inputs += ["-stream_loop", "-1", "-i", str(bgm_path)]
        bgm_idx = idx
        filters.append(f"[{bgm_idx}:a]aresample={sr},volume={a['bgm_gain_db']}dB,"
                       f"atrim=0:{total}[bgmraw]")
        if narration_labels:
            # ナレーションでダッキング（sidechaincompress）
            filters.append(f"[narr]asplit=2[narrmix][sc]")
            filters.append(f"[bgmraw][sc]sidechaincompress=threshold=0.03:ratio=8:"
                           f"attack=20:release=400[bgmduck]")
            filters.append(f"[narrmix][bgmduck]amix=inputs=2:normalize=0:duration=first[premix]")
        else:
            filters.append(f"[bgmraw]anull[premix]")
    else:
        if narration_labels:
            filters.append(f"[narr]anull[premix]")
        else:
            # 完全無音トラック
            inputs += ["-f", "lavfi", "-t", str(total), "-i",
                       f"anullsrc=r={sr}:cl=stereo"]
            filters.append(f"[{idx}:a]anull[premix]")

    # ラウドネス正規化
    filters.append(f"[premix]loudnorm=I={a['loudnorm_i']}:TP={a['loudnorm_tp']}:"
                   f"LRA={a['loudnorm_lra']}[out]")

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
           "-map", "[out]", "-t", str(total),
           "-c:a", a["acodec"], "-b:a", a["bitrate"], "-ar", str(sr), str(out)]
    util.run(cmd)
    return out


def _burn(video: Path, audio: Path, ass_files: list[Path], out: Path,
          project: dict, preview: bool = False) -> None:
    v = project["video"]
    vf_parts = [f"ass={a}" for a in ass_files]
    if preview:
        ph = v["preview"]["height"]
        vf_parts = [f"scale=-2:{ph}"] + vf_parts
        crf = str(v["preview"]["crf"])
        preset = v["preview"]["preset"]
    else:
        crf = str(v["crf"])
        preset = v["preset"]
    vf = ",".join(vf_parts)
    a = project["audio"]
    util.run(["ffmpeg", "-y", "-i", str(video), "-i", str(audio),
              "-vf", vf, "-c:v", v["vcodec"], "-preset", preset, "-crf", crf,
              "-pix_fmt", v["pix_fmt"], "-r", str(v["fps"]),
              "-c:a", a["acodec"], "-b:a", a["bitrate"], "-map", "0:v:0", "-map", "1:a:0",
              "-movflags", "+faststart", str(out)], quiet=False)


def render(day: int, quality: str = "hd", only_preview: bool = False) -> None:
    if not util.have_ffmpeg():
        raise SystemExit(
            "ffmpeg/ffprobe が見つかりません。ローカル環境（素材とffmpegがある場所）で実行してください。\n"
            "  macOS:  brew install ffmpeg\n"
            "  日本語フォント（ヒラギノ標準搭載）が使えることも確認してください。")

    project = util.load_project()
    project["fonts"]["_resolved_mincho"] = util.resolve_font(project["fonts"]["mincho_priority"])
    project["fonts"]["_resolved_gothic"] = util.resolve_font(project["fonts"]["gothic_priority"])

    tl_path = util.OUTPUTS_DIR / f"day{day}" / f"timeline_day{day}.json"
    timeline = util.read_json(tl_path)
    res = timeline["resolution"]
    if quality == "wqhd":
        res = project["video"]["wqhd"]
    fps = timeline["fps"]
    outdir = util.OUTPUTS_DIR / f"day{day}"
    outdir.mkdir(parents=True, exist_ok=True)

    # ASS 生成
    cards_ass = outdir / "cards.ass"
    caps_ass = outdir / "captions.ass"
    cards_ass.write_text(ass.build_cards(timeline, project), encoding="utf-8")
    caps_ass.write_text(ass.build_captions(timeline, project), encoding="utf-8")

    n_shots = sum(len(sc["shots"]) for sc in timeline["scenes"])
    print(f"レンダー開始 DAY{day}: {len(timeline['scenes'])}シーン / {n_shots}ショット "
          f"（ffmpeg出力は抑制。各ショットを1行ずつ表示します）", flush=True)

    with tempfile.TemporaryDirectory(prefix=f"kanau_day{day}_") as td:
        tmp = Path(td)
        # 視覚（ショット→連結）
        clips = []
        i = 0
        for scene in timeline["scenes"]:
            for shot in scene["shots"]:
                shot = dict(shot)
                kind = "札" if shot["type"] == "placeholder" else shot["type"]
                print(f"  [{i+1:>2}/{n_shots}] {scene['id']} … {kind} {shot['dur']:.1f}s",
                      flush=True)
                # WQHD 時はショット解像度も上げる
                clips.append(_render_shot(shot, res, fps, tmp, i, project))
                i += 1
        print("  連結中 …", flush=True)
        master = tmp / "master_silent.mp4"
        _concat(clips, master, tmp)

        # 音声
        print("  音声合成中（ナレーション/BGM/ラウドネス正規化）…", flush=True)
        audio = _build_audio(timeline, project, tmp)

        base = f"kanau_musubi_ishikawa_day{day}"
        if not only_preview:
            print("  本編を書き出し中（字幕焼き込み）…", flush=True)
            _burn(master, audio, [cards_ass, caps_ass], outdir / f"{base}.mp4", project)
            print("  字幕なし版を書き出し中 …", flush=True)
            _burn(master, audio, [cards_ass], outdir / f"{base}_no_caption.mp4", project)
        print("  プレビューを書き出し中 …", flush=True)
        _burn(master, audio, [cards_ass, caps_ass], outdir / f"{base}_preview.mp4",
              project, preview=True)

    print(f"レンダー完了 DAY{day} → {outdir}", flush=True)


if __name__ == "__main__":
    import sys
    render(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
