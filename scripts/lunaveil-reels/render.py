#!/usr/bin/env python3
"""LUNA VEIL リール書き出し（9:16 / 1080x1920 / 30fps / BGM付き）。

使い方:
  python3 render.py              # 7本すべて書き出し → out/
  python3 render.py 01 03        # 指定したリールだけ
  python3 render.py --stills     # 各カットの静止画と一覧（確認用）
  python3 render.py --doc        # 台本・キャプション・画像プロンプトのMarkdownを書き出し

背景は _bg_in/{リールID}_{カット番号}.png（例: _bg_in/01_3.png）があればその画像を使い、
なければ紫×金の世界観で自動生成した背景を使う。
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import tempfile
import urllib.request
import wave
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from reels import PROMPT_HEAD, PROMPT_TAIL, REELS, SCENE_PROMPTS  # noqa: E402

FONT_DIR = HERE / "fonts"
BG_IN = HERE / "_bg_in"
OUT = HERE / "out"

OW, OH, FPS = 1080, 1920, 30
BS = 1.15  # 背景はズーム・パン用に1.15倍で作る
BW, BH = round(OW * BS), round(OH * BS)
XF = 0.4  # カット間クロスフェード（秒）

GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONT_SRC = {
    "ShipporiMincho-Medium.ttf": GF + "shipporimincho/ShipporiMincho-Medium.ttf",
    "ShipporiMincho-SemiBold.ttf": GF + "shipporimincho/ShipporiMincho-SemiBold.ttf",
    "ShipporiMincho-ExtraBold.ttf": GF + "shipporimincho/ShipporiMincho-ExtraBold.ttf",
    "CormorantGaramond.ttf": GF + "cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf",
}


def ensure_fonts():
    FONT_DIR.mkdir(exist_ok=True)
    for name, url in FONT_SRC.items():
        p = FONT_DIR / name
        if not p.exists():
            print(f"フォント取得: {name}")
            urllib.request.urlretrieve(url, p)


def C(rgb):
    return np.array(rgb, np.float32) / 255.0


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# ───────────────────────── 背景キャンバス ─────────────────────────

STONES = {
    "amethyst": ((150, 85, 215), 0.55, None),
    "quartz": ((214, 220, 236), 0.45, "clear"),
    "citrine": ((246, 176, 56), 0.6, None),
    "tiger": ((178, 112, 36), 0.25, "tiger"),
    "carnelian": ((228, 92, 40), 0.5, None),
    "sunstone": ((242, 142, 72), 0.45, None),
    "moonstone": ((232, 218, 200), 0.35, "sheen"),
    "gold": ((236, 190, 92), 0.15, "metal"),
}


class Anim:
    def __init__(self):
        self.flames = []  # (x, y, scale, seed)  背景座標
        self.tw = []  # (x, y, size, phase, speed)

    def random_tw(self, n, seed, x0=0, y0=0, x1=BW, y1=BH):
        rng = np.random.default_rng(seed + 500)
        for _ in range(n):
            self.tw.append((rng.uniform(x0, x1), rng.uniform(y0, y1), rng.uniform(0.5, 1.0),
                            rng.uniform(0, 6.28), rng.uniform(1.2, 2.6)))


class Canvas:
    def __init__(self, w=BW, h=BH):
        self.w, self.h = w, h
        self.a = np.zeros((h, w, 3), np.float32)

    # 基本
    def vgrad(self, stops):
        ys = np.linspace(0, 1, self.h)
        pos = [p for p, _ in stops]
        cols = np.stack([np.interp(ys, pos, [c[i] / 255 for _, c in stops]) for i in range(3)], -1)
        self.a[:] = cols[:, None, :].astype(np.float32)

    def _box(self, cx, cy, rx, ry):
        x0, x1 = max(0, int(cx - rx)), min(self.w, int(cx + rx) + 2)
        y0, y1 = max(0, int(cy - ry)), min(self.h, int(cy + ry) + 2)
        return x0, x1, y0, y1

    def glow(self, cx, cy, r, color, k=1.0, ry=None):
        ry = ry or r
        x0, x1, y0, y1 = self._box(cx, cy, 3 * r, 3 * ry)
        if x0 >= x1 or y0 >= y1:
            return
        xs = (np.arange(x0, x1) - cx) / r
        ys = (np.arange(y0, y1) - cy) / ry
        g = np.exp(-(ys[:, None] ** 2 + xs[None, :] ** 2)) * k
        self.a[y0:y1, x0:x1] += g[..., None] * C(color)

    def shade(self, cx, cy, r, k=0.5, ry=None):
        ry = ry or r
        x0, x1, y0, y1 = self._box(cx, cy, 3 * r, 3 * ry)
        xs = (np.arange(x0, x1) - cx) / r
        ys = (np.arange(y0, y1) - cy) / ry
        g = np.exp(-(ys[:, None] ** 2 + xs[None, :] ** 2) * 1.6) * k
        self.a[y0:y1, x0:x1] *= (1 - g)[..., None]

    def band(self, cx, cy, length, width, ang, color, k, mode="add"):
        r = max(length, width)
        x0, x1, y0, y1 = self._box(cx, cy, 2.5 * r, 2.5 * r)
        X = np.arange(x0, x1)[None, :] - cx
        Y = np.arange(y0, y1)[:, None] - cy
        ca, sa = math.cos(ang), math.sin(ang)
        u, v = X * ca + Y * sa, -X * sa + Y * ca
        g = np.exp(-(u / length) ** 2 - (v / width) ** 2) * k
        if mode == "add":
            self.a[y0:y1, x0:x1] += g[..., None] * C(color)
        else:
            self.a[y0:y1, x0:x1] *= (1 - g)[..., None]

    def ellipse(self, cx, cy, rx, ry, color, alpha=1.0):
        x0, x1, y0, y1 = self._box(cx, cy, rx + 2, ry + 2)
        X = (np.arange(x0, x1) + 0.5 - cx) / rx
        Y = (np.arange(y0, y1) + 0.5 - cy) / ry
        D = np.sqrt(X[None, :] ** 2 + Y[:, None] ** 2)
        cov = (np.clip((1 - D) * min(rx, ry) + 0.5, 0, 1) * alpha)[..., None]
        reg = self.a[y0:y1, x0:x1]
        reg[:] = reg * (1 - cov) + C(color) * cov

    def rect(self, x0, y0, x1, y1, color):
        self.a[int(y0):int(y1), int(x0):int(x1)] = C(color)

    def stars(self, n, seed, y0=0, y1=None, tint="mixed", bright=1.0):
        rng = np.random.default_rng(seed)
        y1 = y1 or self.h
        tints = {"mixed": [(255, 255, 255), (200, 215, 255), (255, 228, 190)],
                 "gold": [(255, 220, 150), (255, 236, 190)]}[tint]
        for _ in range(n):
            x, y = rng.uniform(0, self.w), rng.uniform(y0, y1)
            b = rng.uniform(0, 1) ** 3 * 0.9 * bright + 0.05
            r = 0.6 + rng.uniform(0, 1) ** 4 * 1.6
            self.glow(x, y, r, tints[rng.integers(len(tints))], b)

    def bokeh(self, n, seed, x0, y0, x1, y1, color, rmin, rmax, k):
        rng = np.random.default_rng(seed + 7)
        for _ in range(n):
            cx, cy = rng.uniform(x0, x1), rng.uniform(y0, y1)
            r = rmin + (rmax - rmin) * rng.uniform(0, 1) ** 2
            a = rng.uniform(0.15, 0.55) * k
            bx0, bx1, by0, by1 = self._box(cx, cy, r + 2, r + 2)
            X = (np.arange(bx0, bx1) - cx) / r
            Y = (np.arange(by0, by1) - cy) / r
            D = np.sqrt(X[None, :] ** 2 + Y[:, None] ** 2)
            val = np.clip((1 - D) * r * 0.35, 0, 1) * (0.75 + 0.25 * D ** 4) * a
            self.a[by0:by1, bx0:bx1] += val[..., None] * C(color)

    def rays(self, ox, oy, n, length, color, k, a0, a1, seed, wmin=0.012, wmax=0.035, blur=22):
        rng = np.random.default_rng(seed + 3)
        sc = 0.5
        W, H = int(self.w * sc), int(self.h * sc)
        acc = np.zeros((H, W), np.float32)
        for _ in range(n):
            ang = math.radians(rng.uniform(a0, a1))
            hw = rng.uniform(wmin, wmax)
            pts = [(ox * sc, oy * sc)] + [((ox + length * math.sin(a)) * sc, (oy - length * math.cos(a)) * sc)
                                          for a in (ang - hw, ang + hw)]
            im = Image.new("L", (W, H), 0)
            ImageDraw.Draw(im).polygon(pts, fill=int(rng.uniform(70, 170)))
            acc += np.asarray(im, np.float32) / 255
        m = max(acc.max(), 1e-6)
        im = Image.fromarray((acc / m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur * sc))
        g = np.asarray(im.resize((self.w, self.h), Image.BILINEAR), np.float32) / 255 * m
        X = np.arange(self.w)[None, :] - ox
        Y = np.arange(self.h)[:, None] - oy
        fall = np.exp(-np.sqrt(X ** 2 + Y ** 2) / (length * 0.6))
        self.a += (g * fall)[..., None] * C(color) * k

    def table(self, y, top, bot, edge=(110, 80, 96), grain=True, seed=0):
        y = int(y)
        n = self.h - y
        t = np.linspace(0, 1, n)[:, None]
        col = C(top)[None, :] * (1 - t) + C(bot)[None, :] * t
        arr = np.repeat(col[:, None, :], self.w, axis=1)
        if grain:
            rng = np.random.default_rng(seed + 11)
            streak = np.convolve(rng.normal(0, 0.07, n + 4), np.ones(5) / 5, "same")[2:n + 2]
            xs = np.arange(self.w)[None, :]
            wave_ = 0.04 * np.sin(xs / 95 + np.arange(n)[:, None] / 37)
            arr *= (1 + streak[:, None] + wave_)[..., None]
        self.a[y:] = arr
        self.a[y:y + 3] = self.a[y:y + 3] * 0.4 + C(edge) * 0.6

    def silhouette(self, top, color):
        Y = np.arange(self.h)[:, None]
        cov = np.clip(Y - top[None, :] + 0.5, 0, 1)[..., None]
        self.a = self.a * (1 - cov) + C(color) * cov

    def vignette(self, k=0.62):
        xs = (np.arange(self.w) - self.w / 2) / (self.w / 2)
        ys = (np.arange(self.h) - self.h / 2) / (self.h / 2)
        d = np.sqrt(xs[None, :] ** 2 * 0.9 + ys[:, None] ** 2 * 0.72)
        self.a *= (1 - k * np.clip((d - 0.42) / 0.9, 0, 1) ** 1.6)[..., None]

    # PIL レイヤー（2倍で描いて縮小＝アンチエイリアス）
    def layer(self, ss=2):
        return Image.new("RGBA", (self.w * ss, self.h * ss), (0, 0, 0, 0))

    def comp(self, L, ss=2, k=1.0):
        if ss != 1:
            L = L.convert("RGBa").resize((self.w, self.h), Image.LANCZOS).convert("RGBA")
        arr = np.asarray(L, np.float32) / 255
        al = arr[..., 3:4] * k
        self.a = self.a * (1 - al) + arr[..., :3] * al

    # オブジェクト
    def moon(self, cx, cy, R, phase="full", halo=1.0, seed=1):
        x0, x1, y0, y1 = self._box(cx, cy, R + 2, R + 2)
        X = (np.arange(x0, x1)[None, :] + 0.5 - cx) / R
        Y = (np.arange(y0, y1)[:, None] + 0.5 - cy) / R
        D = np.sqrt(X ** 2 + Y ** 2)
        cov = np.clip((1 - D) * R + 0.5, 0, 1)
        nz = np.sqrt(np.clip(1 - D ** 2, 0, 1))
        rng = np.random.default_rng(seed)
        tex = np.ones_like(D)
        for _ in range(10):
            bx, by, br = rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(0.12, 0.38)
            tex -= 0.16 * np.exp(-((X - bx) ** 2 + (Y - by) ** 2) / br ** 2)
        for _ in range(30):
            bx, by, br = rng.uniform(-0.85, 0.85), rng.uniform(-0.85, 0.85), rng.uniform(0.02, 0.06)
            tex -= 0.08 * np.exp(-((X - bx) ** 2 + (Y - by) ** 2) / br ** 2)
        lit = (0.58 + 0.42 * nz) * tex
        if phase == "full":
            L = lit
        elif phase == "crescent":
            D2 = np.sqrt((X - 0.42) ** 2 + (Y + 0.12) ** 2)
            sh = np.clip((1 - D2) * R * 0.25 + 0.5, 0, 1)
            L = lit * (1 - sh) + lit * 0.05 * sh
        else:  # new
            ang = np.arctan2(Y, X)
            ring = np.exp(-(((1 - D) * R) / 3.5) ** 2) * (0.5 + 0.5 * np.cos(ang - 2.4))
            L = lit * 0.03 + ring * 0.75
        val = L[..., None] * C((242, 238, 222))
        reg = self.a[y0:y1, x0:x1]
        reg[:] = reg * (1 - cov[..., None]) + val * cov[..., None]
        if phase == "full":
            self.glow(cx, cy, R * 1.5, (205, 212, 255), 0.32 * halo)
            self.glow(cx, cy, R * 3.8, (120, 128, 220), 0.12 * halo)
        elif phase == "crescent":
            self.glow(cx, cy, R * 1.6, (195, 205, 255), 0.10 * halo)
        else:
            self.glow(cx, cy, R * 1.5, (150, 140, 235), 0.06 * halo)

    def bead(self, cx, cy, r, stone, dim=1.0):
        color, trans, pat = STONES[stone]
        x0, x1, y0, y1 = self._box(cx, cy, r + 2, r + 2)
        X = (np.arange(x0, x1)[None, :] + 0.5 - cx) / r
        Y = (np.arange(y0, y1)[:, None] + 0.5 - cy) / r
        D = np.sqrt(X ** 2 + Y ** 2)
        cov = np.clip((1 - D) * r + 0.5, 0, 1)[..., None]
        nz = np.sqrt(np.clip(1 - D ** 2, 0, 1))
        lx, ly, lz = -0.45, -0.6, 0.66
        n = math.sqrt(lx * lx + ly * ly + lz * lz)
        lam = np.clip((X * lx + Y * ly + nz * lz) / n, 0, 1)
        col = C(color)
        base = col * (0.16 + 0.72 * lam)[..., None]
        if pat == "tiger":
            bandv = np.exp(-((X * 0.7 + Y * 0.7 + 0.05) / 0.22) ** 2)
            stripes = 0.86 + 0.14 * np.sin((X * 0.7 - Y * 0.7) * 24)
            base = base * ((0.65 + 1.0 * bandv) * stripes)[..., None]
        elif pat == "sheen":
            base = base + C((150, 182, 255)) * (0.5 * np.exp(-((X + 0.05) ** 2 + (Y + 0.15) ** 2) / 0.12))[..., None]
        elif pat == "clear":
            base = base * 0.7 + col * (0.3 * (1 - nz))[..., None]
        elif pat == "metal":
            base = col * (0.22 + 1.0 * lam ** 3)[..., None]
        sss = col * (trans * np.exp(-((X - 0.3) ** 2 + (Y - 0.38) ** 2) / 0.16))[..., None]
        spec = np.exp(-((X + 0.32) ** 2 + (Y + 0.42) ** 2) / 0.010) * 0.95 \
            + np.exp(-((X + 0.18) ** 2 + (Y + 0.25) ** 2) / 0.06) * 0.12
        val = (base + sss + spec[..., None]) * dim
        reg = self.a[y0:y1, x0:x1]
        reg[:] = reg * (1 - cov) + val * cov

    def bracelet(self, cx, cy, rx, ry, n, r, palette, rot=0.15):
        self.shade(cx, cy + ry * 0.45, rx * 0.95, 0.55, ry * 0.75)
        beads = []
        for i in range(n):
            a = 2 * math.pi * i / n + rot
            depth = math.sin(a)
            beads.append((cy + ry * depth, cx + rx * math.cos(a), r * (0.86 + 0.14 * (depth + 1) / 2),
                          palette[i % len(palette)], depth))
        for y, x, rr, stone, depth in sorted(beads):
            self.bead(x, y, rr, stone, dim=0.7 + 0.3 * (depth + 1) / 2)

    def coin(self, cx, cy, r, tilt=0.42, thick=0.11):
        ry, t = r * tilt, r * thick
        dark, mid, light = (138, 90, 28), (222, 168, 66), (252, 214, 128)
        self.ellipse(cx, cy + t, r, ry, dark)
        self.rect(cx - r + 1, cy, cx + r - 1, cy + t, dark)
        self.ellipse(cx, cy, r, ry, light)
        self.ellipse(cx, cy, r * 0.97, ry * 0.97, mid)
        self.ellipse(cx, cy, r * 0.86, ry * 0.86, light, 0.85)
        self.ellipse(cx, cy, r * 0.82, ry * 0.82, mid)
        self.glow(cx - r * 0.35, cy - ry * 0.3, r * 0.3, (255, 236, 170), 0.22, ry=ry * 0.3)
        self.ellipse(cx, cy, r * 0.2, ry * 0.2, (18, 9, 14))

    def candle(self, A, cx, ybase, h, w, color, seed, holder=True):
        ytop = ybase - h
        if holder:
            self.ellipse(cx, ybase + 4, w * 0.95, w * 0.22, (96, 66, 30))
            self.ellipse(cx, ybase, w * 0.9, w * 0.2, (170, 126, 60))
            self.ellipse(cx, ybase - 2, w * 0.62, w * 0.13, (120, 84, 38))
        x0, x1 = int(cx - w / 2 - 2), int(cx + w / 2 + 2)
        y0, y1 = int(ytop), int(ybase)
        X = (np.arange(x0, x1) + 0.5 - cx) / (w / 2)
        covx = np.clip((1 - np.abs(X)) * w / 2 + 0.5, 0, 1)
        sh = 0.32 + 0.68 * np.sqrt(np.clip(1 - X ** 2, 0, 1)) * (0.85 + 0.15 * np.clip(-X, -1, 1))
        Yv = np.arange(y0, y1)
        vert = 0.55 + 0.45 * np.exp(-(Yv - ytop) / (h * 0.35))
        val = C(color) * (sh[None, :] * vert[:, None])[..., None]
        cov = covx[None, :, None]
        reg = self.a[y0:y1, x0:x1]
        reg[:] = reg * (1 - cov) + val * cov
        self.ellipse(cx, ytop, w / 2, w * 0.12, tuple(min(255, int(v * 1.15)) for v in color))
        self.ellipse(cx, ytop + 1, w * 0.36, w * 0.08, tuple(int(v * 0.8) for v in color))
        self.rect(cx - 1.5, ytop - 16, cx + 1.5, ytop, (20, 12, 10))
        self.glow(cx, ytop - 70, 330, (255, 160, 70), 0.16)
        A.flames.append((cx, ytop - 13, w / 90, seed))

    def crystal_cluster(self, A, cx, cy, sc, color, seed, n=7):
        rng = np.random.default_rng(seed + 21)
        self.glow(cx, cy - 150 * sc, 250 * sc, color, 0.3)
        ss = 2
        L = self.layer(ss)
        d = ImageDraw.Draw(L)
        if n > 1:
            d.ellipse([(cx - 190 * sc) * ss, (cy - 26 * sc) * ss, (cx + 190 * sc) * ss, (cy + 36 * sc) * ss],
                      fill=(30, 22, 34, 255))
        else:
            self.shade(cx + 10 * sc, cy + 6 * sc, 60 * sc, 0.5, 16 * sc)
        specs = []
        for i in range(n):
            f = (i / (n - 1) - 0.5) if n > 1 else 0.0
            h = (430 - abs(f) * 440) * sc * rng.uniform(0.82, 1.08)
            w = h * rng.uniform(0.25, 0.32)
            ang = f * 70 + rng.uniform(-7, 7)
            x = cx + f * 300 * sc + rng.uniform(-14, 14) * sc
            y = cy + rng.uniform(-10, 8) * sc
            specs.append((h, x, y, w, ang))
        for h, x, y, w, ang in sorted(specs, key=lambda s: -s[0]):
            tip = crystal_point(d, x, y, w, h, ang, color, ss)
            A.tw.append((tip[0], tip[1], 0.9, rng.uniform(0, 6.28), rng.uniform(1.4, 2.6)))
        self.comp(L, ss, k=0.95)

    def gem(self, A, cx, cy, r, color, seed):
        self.glow(cx, cy, r * 1.7, color, 0.42)
        self.shade(cx, cy + r * 0.6, r * 1.05, 0.55, r * 0.3)
        ss, sq = 2, 0.72
        L = self.layer(ss)
        d = ImageDraw.Draw(L)
        angs = [math.pi / 8 + i * math.pi / 4 for i in range(8)]
        outer = [(cx + r * math.cos(a), cy + r * sq * math.sin(a)) for a in angs]
        table = [(cx + 0.55 * r * math.cos(a), cy - 0.1 * r + 0.55 * r * sq * math.sin(a)) for a in angs]
        S = lambda pts: [(x * ss, y * ss) for x, y in pts]  # noqa: E731
        dark = tuple(int(v * 0.35) for v in color) + (255,)
        d.polygon(S([(x, y + r * 0.2) for x, y in outer]), fill=dark)
        for i in range(8):
            j = (i + 1) % 8
            mid = (angs[i] + angs[j]) / 2 if j else (angs[i] + angs[j] + 2 * math.pi) / 2
            shv = 0.5 + 0.55 * math.cos(mid - (-2.3))
            col = tuple(min(255, int(v * shv)) for v in color) + (255,)
            d.polygon(S([outer[i], outer[j], table[j], table[i]]), fill=col)
        d.polygon(S(table), fill=tuple(min(255, int(v * 1.12 + 25)) for v in color) + (255,))
        edge = tuple(min(255, int(v * 0.5 + 128)) for v in color) + (255,)
        for i in range(8):
            d.line(S([outer[i], table[i]]), fill=edge, width=2)
        d.line(S(outer + [outer[0]]), fill=edge, width=2)
        d.line(S(table + [table[0]]), fill=edge, width=2)
        self.comp(L, ss)
        A.tw.append((cx - r * 0.3, cy - r * 0.32, 1.0, seed % 6, 1.8))
        A.tw.append((cx + r * 0.42, cy + r * 0.05, 0.7, seed % 5 + 2, 2.3))

    def paper(self, cx, cy, w, h, ang, seed):
        self.shade(cx + 12, cy + 18, w * 0.55, 0.55, h * 0.55)
        ss = 2
        L = self.layer(ss)
        d = ImageDraw.Draw(L)
        a = math.radians(ang)
        ca, sa = math.cos(a), math.sin(a)
        R = lambda x, y: ((cx + x * ca - y * sa) * ss, (cy + x * sa + y * ca) * ss)  # noqa: E731
        d.polygon([R(-w / 2, -h / 2), R(w / 2, -h / 2), R(w / 2, h / 2), R(-w / 2, h / 2)], fill=(222, 212, 192, 255))
        d.polygon([R(-w / 2, 0), R(w / 2, 0), R(w / 2, h / 2), R(-w / 2, h / 2)], fill=(206, 196, 178, 255))
        d.line([R(-w / 2, 0), R(w / 2, 0)], fill=(184, 172, 156, 255), width=2 * ss)
        rng = np.random.default_rng(seed + 31)
        for row in (-0.33, -0.17, 0.12, 0.28):
            x = -w * 0.4
            while x < w * 0.38:
                seg = rng.uniform(40, 120)
                pts = []
                for k in range(int(seg / 6)):
                    xx = x + k * 6
                    pts.append(R(xx, row * h + 6 * math.sin(xx / 7 + rng.uniform(0, 1)) + rng.uniform(-2, 2)))
                if len(pts) > 1:
                    d.line(pts, fill=(78, 58, 88, 255), width=int(2 * ss))
                x += seg + rng.uniform(14, 30)
        self.comp(L, ss)

    def glass(self, cx, by, w, h):
        ss = 2
        L = self.layer(ss)
        d = ImageDraw.Draw(L)
        top = by - h
        S = lambda pts: [(x * ss, y * ss) for x, y in pts]  # noqa: E731
        d.polygon(S([(cx - w / 2, top), (cx + w / 2, top), (cx + w * 0.42, by), (cx - w * 0.42, by)]),
                  fill=(190, 210, 255, 40))
        lv = top + h * 0.35
        lw = w / 2 - (w / 2 - w * 0.42) * 0.35
        d.polygon(S([(cx - lw, lv), (cx + lw, lv), (cx + w * 0.42, by), (cx - w * 0.42, by)]),
                  fill=(140, 176, 255, 60))
        d.line(S([(cx - w / 2, top), (cx - w * 0.42, by)]), fill=(230, 240, 255, 170), width=3 * ss)
        d.line(S([(cx + w / 2, top), (cx + w * 0.42, by)]), fill=(200, 220, 255, 120), width=2 * ss)
        d.ellipse(S([(cx - w / 2, top - 10), (cx + w / 2, top + 10)]), outline=(230, 240, 255, 150), width=2 * ss)
        d.ellipse(S([(cx - lw, lv - 9), (cx + lw, lv + 9)]), outline=(200, 220, 255, 130), width=2 * ss)
        d.ellipse(S([(cx - w * 0.42, by - 9), (cx + w * 0.42, by + 9)]), outline=(200, 220, 255, 110), width=3 * ss)
        d.line(S([(cx - w * 0.3, top + 20), (cx - w * 0.26, by - 20)]), fill=(255, 255, 255, 110), width=4 * ss)
        self.comp(L, ss)

    def torii(self, cx, by, W, H, color=(9, 5, 12)):
        ss = 2
        L = self.layer(ss)
        d = ImageDraw.Draw(L)
        col = color + (255,)
        S = lambda pts: [(x * ss, y * ss) for x, y in pts]  # noqa: E731
        px, pw = W * 0.31, W * 0.065
        ptop = by - H * 0.86
        for sx in (-1, 1):
            x = cx + sx * px
            d.polygon(S([(x - pw / 2 - 4, by), (x + pw / 2 + 4, by), (x + pw / 2, ptop), (x - pw / 2, ptop)]), fill=col)
        kt = H * 0.075
        ytop = by - H
        top_pts, bot_pts = [], []
        for i in range(41):
            u = i / 40 * 2 - 1
            x = cx + u * W / 2
            lift = H * 0.06 * abs(u) ** 3
            top_pts.append((x, ytop - lift))
            bot_pts.append((x, ytop + kt - lift * 0.7))
        d.polygon(S(top_pts + bot_pts[::-1]), fill=col)
        d.rectangle(S([(cx - W * 0.44, ytop + kt), (cx + W * 0.44, ytop + kt * 1.7)]), fill=col)
        ny = by - H * 0.7
        d.rectangle(S([(cx - W * 0.43, ny), (cx + W * 0.43, ny + H * 0.055)]), fill=col)
        d.rectangle(S([(cx - W * 0.03, ytop + kt * 1.7), (cx + W * 0.03, ny)]), fill=col)
        self.comp(L, ss)

    def window_wall(self, x0, x1, ybase, ybot, wall=(15, 9, 23), frame=(52, 38, 66)):
        ss = 2
        L = self.layer(ss)
        d = ImageDraw.Draw(L)
        S = lambda v: v * ss  # noqa: E731
        r = (x1 - x0) / 2
        cx = (x0 + x1) / 2
        d.rectangle([0, 0, self.w * ss, self.h * ss], fill=wall + (255,))
        fr = 16
        d.rectangle([S(x0 - fr), S(ybase), S(x1 + fr), S(ybot + fr)], fill=frame + (255,))
        d.ellipse([S(cx - r - fr), S(ybase - r - fr), S(cx + r + fr), S(ybase + r + fr)], fill=frame + (255,))
        d.rectangle([S(x0), S(ybase), S(x1), S(ybot)], fill=(0, 0, 0, 0))
        d.ellipse([S(cx - r), S(ybase - r), S(cx + r), S(ybase + r)], fill=(0, 0, 0, 0))
        ymid = (ybase + ybot) / 2 + 40
        d.rectangle([S(cx - 9), S(ybase - r), S(cx + 9), S(ybot)], fill=frame + (255,))
        d.rectangle([S(x0), S(ymid - 9), S(x1), S(ymid + 9)], fill=frame + (255,))
        self.comp(L, ss)

    def zodiac_ring(self, cx, cy, R, k=0.5):
        ss = 2
        L = self.layer(ss)
        d = ImageDraw.Draw(L)
        g = (232, 196, 120, 255)
        for rr, wd in ((R, 3), (R * 0.86, 2), (R * 0.62, 2), (R * 0.58, 1)):
            d.ellipse([(cx - rr) * ss, (cy - rr) * ss, (cx + rr) * ss, (cy + rr) * ss], outline=g, width=wd * ss)
        for i in range(12):
            a = i * math.pi / 6
            d.line([((cx + R * 0.86 * math.cos(a)) * ss, (cy + R * 0.86 * math.sin(a)) * ss),
                    ((cx + R * math.cos(a)) * ss, (cy + R * math.sin(a)) * ss)], fill=g, width=2 * ss)
            am = a + math.pi / 12
            mx, my = cx + R * 0.93 * math.cos(am), cy + R * 0.93 * math.sin(am)
            s = 7
            d.polygon([((mx) * ss, (my - s) * ss), ((mx + s) * ss, my * ss), (mx * ss, (my + s) * ss),
                       ((mx - s) * ss, my * ss)], fill=g)
            j = (i + 5) % 12
            b = j * math.pi / 6
            d.line([((cx + R * 0.58 * math.cos(a)) * ss, (cy + R * 0.58 * math.sin(a)) * ss),
                    ((cx + R * 0.58 * math.cos(b)) * ss, (cy + R * 0.58 * math.sin(b)) * ss)],
                   fill=(232, 196, 120, 255), width=1 * ss)
        for i in range(72):
            a = i * math.pi / 36
            d.line([((cx + R * 0.62 * math.cos(a)) * ss, (cy + R * 0.62 * math.sin(a)) * ss),
                    ((cx + R * 0.655 * math.cos(a)) * ss, (cy + R * 0.655 * math.sin(a)) * ss)], fill=g, width=ss)
        self.comp(L, ss, k=k)
        self.glow(cx, cy, R * 0.25, (255, 210, 140), 0.12 * k / 0.5)

    def velvet(self, top, mid, bot, seed):
        self.vgrad([(0, top), (0.55, mid), (1, bot)])
        rng = np.random.default_rng(seed + 41)
        for _ in range(7):
            self.band(rng.uniform(0, self.w), rng.uniform(300, self.h), rng.uniform(500, 900), rng.uniform(40, 90),
                      rng.uniform(-0.6, 0.6), (255, 220, 255), rng.uniform(0.02, 0.05))
        for _ in range(7):
            self.band(rng.uniform(0, self.w), rng.uniform(300, self.h), rng.uniform(500, 900), rng.uniform(50, 110),
                      rng.uniform(-0.6, 0.6), (0, 0, 0), rng.uniform(0.25, 0.45), mode="mul")


def crystal_point(d, bx, by, w, h, ang, color, ss):
    P = {"L": (-w / 2, 0), "CL": (-w / 6, w * 0.06), "CR": (w / 6, w * 0.06), "R": (w / 2, 0),
         "Ls": (-w / 2, -0.72 * h), "CLs": (-w / 6, -0.70 * h), "CRs": (w / 6, -0.70 * h), "Rs": (w / 2, -0.72 * h),
         "T": (w * 0.04, -h)}
    a = math.radians(ang)
    ca, sa = math.cos(a), math.sin(a)

    def tr(p):
        x, y = p
        return ((bx + x * ca - y * sa) * ss, (by + x * sa + y * ca) * ss)

    faces = [(["L", "CL", "CLs", "Ls"], 1.0), (["CL", "CR", "CRs", "CLs"], 0.74), (["CR", "R", "Rs", "CRs"], 0.48),
             (["Ls", "CLs", "T"], 1.18), (["CLs", "CRs", "T"], 0.93), (["CRs", "Rs", "T"], 0.6)]
    for names, shv in faces:
        col = tuple(min(255, int(c * shv + 12)) for c in color) + (255,)
        d.polygon([tr(P[n]) for n in names], fill=col)
    for names, shv in faces:
        pts = [tr(P[n]) for n in names]
        ec = tuple(min(255, int(c * shv * 0.55 + 120)) for c in color) + (255,)
        d.line(pts + [pts[0]], fill=ec, width=max(1, int(1.2 * ss)))
    streak = [tr((-w * 0.40, -0.10 * h)), tr((-w * 0.31, -0.10 * h)), tr((-w * 0.31, -0.62 * h)), tr((-w * 0.40, -0.64 * h))]
    d.polygon(streak, fill=tuple(min(255, int(c * 0.4 + 160)) for c in color) + (255,))
    tx, ty = tr(P["T"])
    return tx / ss, ty / ss


# ───────────────────────── シーン ─────────────────────────

def sc_new_moon_sky(c, A, seed):
    c.vgrad([(0, (5, 4, 16)), (0.45, (19, 11, 42)), (0.78, (17, 9, 34)), (1, (8, 5, 14))])
    for i in range(16):
        t = i / 15
        c.glow(80 + t * 1080, 1800 - t * 1550, 190, (95, 70, 160), 0.07)
    c.stars(1000, seed)
    c.moon(900, 560, 100, "new")
    c.glow(621, 2350, 760, (130, 70, 170), 0.4)
    c.glow(621, 2300, 520, (235, 170, 90), 0.13)
    A.random_tw(26, seed, y1=1700)


def sc_night_window(c, A, seed, moon="crescent", candle=True, cluster=True, tone="purple"):
    if tone == "purple":
        c.vgrad([(0, (10, 12, 42)), (0.5, (30, 24, 74)), (1, (16, 12, 36))])
    else:
        c.vgrad([(0, (6, 14, 42)), (0.5, (18, 36, 84)), (1, (8, 14, 32))])
    c.stars(650, seed, y1=1480)
    if moon == "crescent":
        c.moon(790, 470, 72, "crescent")
    else:
        c.moon(621, 560, 165, "full", halo=0.9)
    A.random_tw(14, seed, 260, 240, 980, 1400)
    c.window_wall(230, 1012, 640, 1480)
    spill = (110, 130, 230) if tone == "purple" else (110, 150, 255)
    c.glow(621, 1060, 540, spill, 0.12)
    c.rect(196, 1480, 1046, 1514, (54, 42, 68))
    c.rect(196, 1480, 1046, 1484, (118, 104, 140))
    c.table(1640, top=(44, 26, 40), bot=(10, 6, 10), seed=seed)
    c.rays(800, 700, 5, 1500, (150, 172, 255), 0.10, 200, 214, seed, wmin=0.02, wmax=0.05, blur=30)
    if candle:
        c.candle(A, 360, 1890, 300, 92, (122, 72, 165), seed)
    if cluster:
        c.crystal_cluster(A, 860, 1885, 0.55, (206, 196, 236), seed)


def sc_wish_paper(c, A, seed, bracelet=False):
    c.vgrad([(0, (12, 8, 24)), (0.55, (30, 18, 40)), (1, (14, 8, 14))])
    c.bokeh(40, seed, 0, 0, 1242, 1150, (200, 170, 255), 4, 22, 0.35)
    c.table(1180, top=(50, 31, 42), bot=(16, 9, 12), seed=seed)
    c.candle(A, 220, 1430, 230, 74, (232, 216, 190), seed + 1)
    c.glow(950, 320, 620, (110, 130, 230), 0.12)
    c.paper(650, 1650, 640, 420, -7, seed)
    if bracelet:
        c.bracelet(660, 1640, 225, 98, 18, 30, ["amethyst", "quartz", "citrine"])
    else:
        c.crystal_cluster(A, 770, 1700, 0.42, (220, 226, 242), seed, n=1)


def sc_gold_altar(c, A, seed, palette="gold"):
    c.vgrad([(0, (16, 7, 22)), (0.5, (38, 17, 34)), (0.78, (64, 32, 28)), (1, (26, 12, 14))])
    c.bokeh(80, seed, 0, 0, 1242, 1500, (255, 200, 110), 5, 28, 0.55)
    c.glow(621, 1640, 560, (255, 165, 70), 0.30)
    c.table(1700, top=(72, 30, 62), bot=(20, 8, 20), edge=(140, 90, 110), seed=seed)
    c.candle(A, 1010, 1770, 250, 78, (232, 196, 120), seed)
    if palette == "gold":
        c.crystal_cluster(A, 520, 1830, 0.95, (246, 178, 60), seed)
        for k in range(5):
            c.coin(880, 1860 - k * 7, 62)
        c.coin(290, 1915, 54)
        c.coin(730, 1945, 50)
    else:
        c.crystal_cluster(A, 520, 1830, 0.95, (238, 118, 52), seed)
        for x, y, r, s in ((820, 1880, 40, "moonstone"), (900, 1905, 36, "sunstone"), (760, 1930, 34, "moonstone"),
                           (300, 1930, 36, "sunstone")):
            c.bead(x, y, r, s)


def sc_crystal_altar(c, A, seed):
    c.vgrad([(0, (10, 6, 22)), (0.6, (30, 14, 46)), (1, (10, 5, 14))])
    c.bokeh(50, seed, 0, 0, 1242, 1300, (210, 170, 255), 4, 20, 0.4)
    c.table(1680, top=(52, 26, 60), bot=(14, 6, 18), seed=seed)
    c.candle(A, 990, 1720, 220, 70, (122, 72, 165), seed)
    c.crystal_cluster(A, 600, 1860, 1.15, (150, 86, 220), seed, n=8)


def sc_bracelet(c, A, seed, palette=("amethyst", "quartz", "citrine"), warm=False):
    if warm:
        c.velvet((20, 10, 14), (46, 24, 22), (60, 30, 24), seed)
        candle_col = (232, 216, 190)
    else:
        c.velvet((12, 6, 20), (30, 12, 42), (42, 16, 52), seed)
        candle_col = (122, 72, 165)
    c.bokeh(30, seed, 0, 0, 1242, 1200, (255, 200, 120), 4, 22, 0.35)
    c.glow(250, 1350, 380, (255, 160, 80), 0.22)
    c.candle(A, 250, 1520, 240, 72, candle_col, seed)
    c.glow(640, 1700, 420, (255, 190, 110), 0.10)
    c.bracelet(640, 1720, 330, 150, 20, 44, list(palette))


def sc_bracelet_pair(c, A, seed):
    c.velvet((12, 6, 20), (30, 12, 42), (42, 16, 52), seed)
    c.bokeh(30, seed, 0, 0, 1242, 1200, (230, 190, 255), 4, 20, 0.3)
    c.glow(380, 1690, 330, (170, 100, 240), 0.2)
    c.glow(862, 1690, 330, (255, 130, 60), 0.2)
    c.bracelet(380, 1700, 195, 92, 15, 36, ["amethyst", "amethyst", "amethyst", "quartz"])
    c.bracelet(862, 1700, 195, 92, 15, 36, ["carnelian", "carnelian", "carnelian", "gold"], rot=0.35)


def sc_golden_sky(c, A, seed):
    c.vgrad([(0, (12, 6, 26)), (0.5, (42, 18, 50)), (0.85, (86, 46, 36)), (1, (60, 30, 22))])
    c.rays(621, -150, 16, 2700, (255, 214, 150), 0.55, -22, 22, seed)
    c.bokeh(130, seed, 0, 0, 1242, 2208, (255, 205, 120), 4, 34, 0.75)
    c.stars(350, seed, tint="gold")
    c.glow(621, 2050, 700, (255, 170, 80), 0.35)
    A.random_tw(24, seed)


def sc_torii_glow(c, A, seed):
    c.vgrad([(0, (7, 6, 24)), (0.55, (28, 16, 50)), (0.8, (66, 38, 58)), (1, (12, 7, 14))])
    c.stars(480, seed, y1=1250)
    c.glow(621, 1560, 520, (255, 175, 90), 0.38)
    c.glow(621, 1640, 200, (255, 220, 160), 0.28)
    c.table(1800, top=(20, 12, 20), bot=(6, 4, 8), edge=(60, 40, 50), grain=False)
    c.torii(621, 1810, 580, 500)
    rng = np.random.default_rng(seed + 51)
    for _ in range(12):
        c.glow(rng.uniform(0, 1242), 1790 + rng.uniform(-30, 30), rng.uniform(180, 320), (230, 190, 150), 0.07,
               ry=rng.uniform(25, 45))
    A.random_tw(16, seed, y1=1200)


def sc_full_moon(c, A, seed):
    c.vgrad([(0, (5, 7, 28)), (0.5, (17, 19, 58)), (1, (9, 8, 24))])
    c.stars(600, seed)
    c.moon(621, 660, 230, "full", halo=1.2)
    rng = np.random.default_rng(seed + 61)
    for _ in range(16):
        c.glow(rng.uniform(0, 1242), rng.uniform(1250, 1800), rng.uniform(180, 380), (150, 150, 215),
               rng.uniform(0.05, 0.11), ry=rng.uniform(30, 70))
    c.glow(621, 2300, 650, (80, 70, 160), 0.3)
    A.random_tw(20, seed, y1=1600)


def sc_moon_window(c, A, seed):
    sc_night_window(c, A, seed, moon="full", candle=False, cluster=False, tone="blue")
    c.glow(621, 1470, 520, (130, 160, 255), 0.16, ry=160)
    c.crystal_cluster(A, 420, 1482, 0.38, (150, 86, 220), seed)
    c.crystal_cluster(A, 820, 1482, 0.34, (215, 222, 242), seed + 1, n=3)
    c.bracelet(621, 1780, 220, 92, 16, 32, ["amethyst", "quartz", "moonstone"])


def sc_two_stones(c, A, seed):
    c.vgrad([(0, (6, 4, 16)), (0.6, (20, 10, 34)), (1, (8, 5, 12))])
    c.stars(520, seed, y1=1300)
    c.moon(930, 540, 70, "new")
    c.table(1560, top=(36, 20, 40), bot=(9, 5, 10), seed=seed)
    c.gem(A, 380, 1730, 150, (245, 182, 64), seed)
    c.gem(A, 862, 1730, 150, (84, 146, 255), seed + 1)
    A.random_tw(14, seed, y1=1200)


def sc_blue_window(c, A, seed):
    sc_night_window(c, A, seed, moon="crescent", candle=False, cluster=False, tone="blue")
    c.glow(621, 1400, 520, (120, 160, 255), 0.18, ry=260)
    c.glass(470, 1482, 150, 230)
    c.crystal_cluster(A, 790, 1482, 0.3, (200, 222, 255), seed, n=1)
    c.paper(760, 1790, 320, 200, 8, seed)
    for i in range(14):
        t = i / 13
        c.glow(760 + 30 * math.sin(t * 5), 1740 - t * 420, 18 + 20 * t, (190, 205, 255), 0.05)


def sc_zodiac_wheel(c, A, seed, dim=False):
    c.vgrad([(0, (7, 6, 26)), (0.5, (20, 14, 50)), (1, (7, 6, 18))])
    c.stars(900, seed)
    c.glow(621, 1012, 620, (110, 80, 190), 0.16 if not dim else 0.1)
    c.zodiac_ring(621, 1012, 540, k=0.5 if not dim else 0.2)
    if dim:
        c.a *= 0.8
    A.random_tw(18, seed)


def sc_dawn_rays(c, A, seed):
    c.vgrad([(0, (18, 9, 38)), (0.38, (64, 32, 84)), (0.62, (196, 112, 108)), (0.72, (255, 196, 132)),
             (0.79, (140, 70, 64)), (1, (18, 9, 16))])
    c.stars(220, seed, y1=650, bright=0.7)
    c.rays(621, 1600, 24, 2200, (255, 222, 165), 0.5, -80, 80, seed)
    c.glow(621, 1610, 200, (255, 236, 196), 0.55)
    c.glow(621, 1600, 760, (255, 160, 90), 0.24)
    rng = np.random.default_rng(seed + 71)
    for _ in range(12):
        c.glow(rng.uniform(0, 1242), rng.uniform(1250, 1560), rng.uniform(160, 320), (255, 190, 170), 0.07,
               ry=rng.uniform(22, 45))
    xs = np.arange(c.w)
    c.silhouette(1660 + 38 * np.sin(xs / 180) + 22 * np.sin(xs / 77 + 1), (18, 9, 16))


SCENES = {
    "new_moon_sky": sc_new_moon_sky,
    "night_window": sc_night_window,
    "wish_paper": sc_wish_paper,
    "wish_paper_bracelet": lambda c, A, s: sc_wish_paper(c, A, s, bracelet=True),
    "gold_altar": sc_gold_altar,
    "gold_altar_orange": lambda c, A, s: sc_gold_altar(c, A, s, palette="orange"),
    "crystal_altar": sc_crystal_altar,
    "bracelet": sc_bracelet,
    "bracelet_gold": lambda c, A, s: sc_bracelet(c, A, s, palette=("citrine", "tiger", "citrine", "gold")),
    "bracelet_orange": lambda c, A, s: sc_bracelet(c, A, s, palette=("carnelian", "moonstone", "sunstone", "moonstone"),
                                                   warm=True),
    "bracelet_pair": sc_bracelet_pair,
    "golden_sky": sc_golden_sky,
    "torii_glow": sc_torii_glow,
    "full_moon": sc_full_moon,
    "moon_window": sc_moon_window,
    "two_stones": sc_two_stones,
    "blue_window": sc_blue_window,
    "zodiac_wheel": sc_zodiac_wheel,
    "zodiac_wheel_dim": lambda c, A, s: sc_zodiac_wheel(c, A, s, dim=True),
    "dawn_rays": sc_dawn_rays,
}


def build_bg(reel, idx, scene):
    """背景（BW x BH の PIL RGB）とアニメ要素を返す。_bg_in に画像があればそれを優先。"""
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = BG_IN / f"{reel['id']}_{idx + 1}.{ext}"
        if p.exists():
            im = Image.open(p).convert("RGB")
            s = max(BW / im.width, BH / im.height)
            im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
            l, t = (im.width - BW) // 2, (im.height - BH) // 2
            return im.crop((l, t, l + BW, t + BH)), Anim(), True
    c, A = Canvas(), Anim()
    SCENES[scene](c, A, reel["seed"] * 10 + idx)
    c.vignette()
    rng = np.random.default_rng(reel["seed"] * 10 + idx + 999)
    c.a += rng.normal(0, 0.008, c.a.shape[:2]).astype(np.float32)[..., None]
    img = Image.fromarray((np.clip(c.a, 0, 1) * 255 + 0.5).astype(np.uint8))
    return img, A, False


# ───────────────────────── テロップ ─────────────────────────

STY = {"h": ("ShipporiMincho-ExtraBold.ttf", 84, 1.34), "m": ("ShipporiMincho-SemiBold.ttf", 58, 1.52),
       "s": ("ShipporiMincho-Medium.ttf", 40, 1.7), "n": ("ShipporiMincho-ExtraBold.ttf", 360, 1.0),
       "r": ("ShipporiMincho-SemiBold.ttf", 48, 1.95)}
TC = {"w": (250, 244, 230), "g": (240, 204, 122), "b": (150, 198, 255), "p": (212, 178, 252), "o": (247, 170, 106)}
MAXW = 840
SEG = re.compile(r"\{([gbpo]):([^}]*)\}")
_fonts = {}


def font(name, size):
    key = (name, size)
    if key not in _fonts:
        f = ImageFont.truetype(str(FONT_DIR / name), size)
        if name.startswith("Cormorant"):
            try:
                f.set_variation_by_axes([600])
            except Exception:
                pass
        _fonts[key] = f
    return _fonts[key]


def segments(text):
    out, pos = [], 0
    for m in SEG.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], "w"))
        out.append((m.group(2), m.group(1)))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], "w"))
    return out


def plain(text):
    return SEG.sub(lambda m: m.group(2), text)


def tracked(d, cx, cy, text, f, fill, track):
    w = sum(f.getlength(ch) for ch in text) + track * (len(text) - 1)
    x = cx - w / 2
    for ch in text:
        d.text((x, cy), ch, font=f, fill=fill, anchor="lm")
        x += f.getlength(ch) + track
    return w


def render_telop(tel):
    items, total = [], 0.0
    for raw in tel["lines"]:
        hidden = raw.startswith("_")
        st, text = raw.lstrip("_").split(":", 1)
        fname, size, lh = STY[st]
        f = font(fname, size)
        if st != "r":
            w = sum(f.getlength(s) for s, _ in segments(text))
            if w > MAXW:
                size = int(size * MAXW / w)
                f = font(fname, size)
        items.append((st, text, hidden, f, size, size * lh))
        total += size * lh
    yc = tel["y"] or 880
    txt = Image.new("RGBA", (OW, OH), (0, 0, 0, 0))
    glw = Image.new("RGBA", (OW, OH), (0, 0, 0, 0))
    d, gd = ImageDraw.Draw(txt), ImageDraw.Draw(glw)
    y = yc - total / 2
    for st, text, hidden, f, size, h in items:
        cy = y + h / 2
        if not hidden and st == "r":
            name, stone, kw = text.split("|")
            d.text((150, cy), name, font=f, fill=TC["g"] + (255,), anchor="lm", stroke_width=2,
                   stroke_fill=(28, 12, 34, 255))
            d.text((360, cy), stone, font=f, fill=TC["w"] + (255,), anchor="lm", stroke_width=2,
                   stroke_fill=(28, 12, 34, 255))
            d.text((765, cy), kw, font=font(STY["s"][0], 34), fill=(226, 200, 150, 255), anchor="lm",
                   stroke_width=2, stroke_fill=(28, 12, 34, 255))
            d.line([(150, cy + h / 2 - 4), (930, cy + h / 2 - 4)], fill=(232, 196, 120, 70), width=1)
        elif not hidden:
            segs = segments(text)
            x = (OW - sum(f.getlength(s) for s, _ in segs)) / 2
            sw = 3 if size >= 70 else 2
            for s, c in segs:
                d.text((x, cy), s, font=f, fill=TC[c] + (255,), anchor="lm", stroke_width=sw,
                       stroke_fill=(28, 12, 34, 255))
                if c != "w" or st == "n":
                    gd.text((x, cy), s, font=f, fill=TC[c] + (255,), anchor="lm")
                x += f.getlength(s)
        y += h
    if tel["orn"]:
        yo = yc - total / 2 - 22
        g = TC["g"] + (230,)
        d.line([(OW / 2 - 150, yo), (OW / 2 - 24, yo)], fill=g, width=2)
        d.line([(OW / 2 + 24, yo), (OW / 2 + 150, yo)], fill=g, width=2)
        d.polygon([(OW / 2, yo - 9), (OW / 2 + 9, yo), (OW / 2, yo + 9), (OW / 2 - 9, yo)], fill=g)
    if tel["cta"]:
        yb = 1400
        g = TC["g"] + (235,)
        w = tracked(d, OW / 2, yb, "LUNA VEIL", font("CormorantGaramond.ttf", 66), (244, 226, 184, 255), 14)
        d.line([(OW / 2 - w / 2 - 110, yb), (OW / 2 - w / 2 - 28, yb)], fill=g, width=2)
        d.line([(OW / 2 + w / 2 + 28, yb), (OW / 2 + w / 2 + 110, yb)], fill=g, width=2)
        tracked(d, OW / 2, yb + 62, "@lunaveilmagical", font("CormorantGaramond.ttf", 32), (220, 200, 165, 255), 3)
    alpha = txt.getchannel("A")
    bb = alpha.getbbox()
    out = Image.new("RGBA", (OW, OH), (0, 0, 0, 0))
    if bb:
        scrim = Image.new("L", (OW, OH), 0)
        ImageDraw.Draw(scrim).ellipse([bb[0] - 90, bb[1] - 70, bb[2] + 90, bb[3] + 70], fill=120)
        scrim = scrim.filter(ImageFilter.GaussianBlur(60))
        out.alpha_composite(Image.merge("RGBA", [Image.new("L", (OW, OH), v) for v in (8, 3, 12)] + [scrim]))
        sh = alpha.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.8))
        out.alpha_composite(Image.merge("RGBA", [Image.new("L", (OW, OH), v) for v in (10, 4, 14)] + [sh]))
        g2 = glw.filter(ImageFilter.GaussianBlur(14))
        g2.putalpha(g2.getchannel("A").point(lambda v: int(v * 0.5)))
        out.alpha_composite(g2)
        out.alpha_composite(txt)
    bb = out.getbbox() or (0, 0, 1, 1)
    crop = np.asarray(out.crop(bb), np.float32) / 255
    return dict(tel, rgb=crop[..., :3], a=crop[..., 3:4], px=bb[0], py=bb[1])


def brand_mark():
    im = Image.new("RGBA", (OW, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = tracked(d, OW / 2, 60, "LUNA VEIL", font("CormorantGaramond.ttf", 36), (238, 220, 178, 200), 11)
    d.line([(OW / 2 - w / 2 - 70, 60), (OW / 2 - w / 2 - 20, 60)], fill=(232, 196, 120, 150), width=1)
    d.line([(OW / 2 + w / 2 + 20, 60), (OW / 2 + w / 2 + 70, 60)], fill=(232, 196, 120, 150), width=1)
    arr = np.asarray(im, np.float32) / 255
    return arr[..., :3], arr[..., 3:4]


def blend(fr, rgb, a, x, y, op=1.0):
    h, w = a.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(OW, x + w), min(OH, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    sa = a[y0 - y:y1 - y, x0 - x:x1 - x] * op
    reg = fr[y0:y1, x0:x1]
    reg[:] = reg * (1 - sa) + rgb[y0 - y:y1 - y, x0 - x:x1 - x] * sa


# ───────────────────────── 動き（炎・きらめき・粒子） ─────────────────────────

def gauss_sprite(r):
    n = int(math.ceil(r * 3))
    xs = np.arange(-n, n + 1) / r
    return np.exp(-(xs[None, :] ** 2 + xs[:, None] ** 2)).astype(np.float32)


def sparkle_sprite(n=20):
    xs = np.arange(-n, n + 1, dtype=np.float32)
    X, Y = xs[None, :], xs[:, None]
    core = np.exp(-(X ** 2 + Y ** 2) / 4.0)
    cross = np.exp(-(Y / 1.1) ** 2) * np.exp(-np.abs(X) / 5.5) + np.exp(-(X / 1.1) ** 2) * np.exp(-np.abs(Y) / 5.5)
    return (core + 0.7 * cross).astype(np.float32)


SPARK = sparkle_sprite()
SPARK_S = np.asarray(Image.fromarray(SPARK).resize((25, 25), Image.BILINEAR), np.float32)
DUST = [gauss_sprite(r) for r in (1.2, 1.8, 2.6, 3.6)]
BOKEH = gauss_sprite(16)
_glows = {}


def add(fr, spr, cx, cy, col):
    h, w = spr.shape[:2]
    x, y = int(round(cx)) - w // 2, int(round(cy)) - h // 2
    x0, y0, x1, y1 = max(0, x), max(0, y), min(OW, x + w), min(OH, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    s = spr[y0 - y:y1 - y, x0 - x:x1 - x]
    if s.ndim == 2:
        s = s[..., None]
    fr[y0:y1, x0:x1] += s * col


def flame(t, seed, sc):
    fw, fh = max(8, int(64 * sc)), max(16, int(160 * sc))
    flick = 1 + 0.06 * math.sin(t * 13 + seed) + 0.04 * math.sin(t * 23.7 + seed * 2) + 0.03 * math.sin(t * 7.1)
    sway = 0.07 * math.sin(t * 3.3 + seed) + 0.05 * math.sin(t * 8.9 + seed * 1.7)
    y = np.linspace(1, 0, fh, dtype=np.float32)[:, None] / flick
    x = np.linspace(-1, 1, fw, dtype=np.float32)[None, :]
    width = 0.5 * np.clip(np.sin(np.pi * np.clip(y, 0, 1) ** 0.6), 0, None) * (1 - y * 0.2) + 1e-3
    xc = x - sway * y ** 2 * 2
    body = np.exp(-(xc / width) ** 2 * 2.5) * (y <= 1)
    core = np.exp(-(xc / (width * 0.45)) ** 2 * 3) * np.exp(-((y - 0.25) / 0.24) ** 2)
    base = np.exp(-((y - 0.05) / 0.06) ** 2) * np.exp(-(xc / 0.3) ** 2)
    rgb = body[..., None] * C((255, 140, 40)) + core[..., None] * C((255, 244, 200)) * 1.25 \
        + base[..., None] * C((40, 70, 170)) * 0.5
    return rgb, flick


def glow_sprite(r):
    r = int(r)
    if r not in _glows:
        _glows[r] = gauss_sprite(r)
    return _glows[r]


class Particles:
    def __init__(self, seed, n=55, nb=7):
        rng = np.random.default_rng(seed + 77)
        self.p = [(rng.uniform(0, OW), rng.uniform(0, OH + 100), rng.uniform(-6, 6), rng.uniform(-38, -10),
                   rng.integers(len(DUST)), rng.uniform(0.25, 0.9), rng.uniform(0.6, 2.2), rng.uniform(0, 6.28))
                  for _ in range(n)]
        self.b = [(rng.uniform(0, OW), rng.uniform(0, OH), rng.uniform(-4, 4), rng.uniform(-14, -5),
                   rng.uniform(0.03, 0.07), rng.uniform(0, 6.28)) for _ in range(nb)]

    def draw(self, fr, t):
        gold = C((255, 214, 140))
        for x, y, vx, vy, si, b, fq, ph in self.p:
            px = (x + vx * t + 8 * math.sin(t * 0.7 + ph)) % OW
            py = (y + vy * t) % (OH + 100) - 50
            add(fr, DUST[si], px, py, gold * b * (0.55 + 0.45 * math.sin(t * fq + ph)))
        for x, y, vx, vy, b, ph in self.b:
            add(fr, BOKEH, (x + vx * t) % OW, (y + vy * t) % OH, gold * b * (0.7 + 0.3 * math.sin(t * 0.8 + ph)))


# ───────────────────────── リール組み立て ─────────────────────────

def kb_box(motion, p):
    p = 0.5 - 0.5 * math.cos(math.pi * p)
    z = {"in": 1.0 + 0.08 * p, "out": 1.08 - 0.08 * p, "slow": 1.0 + 0.03 * p}.get(motion, 1.06)
    cw, ch = BW / z, BH / z
    cx, cy = BW / 2, BH / 2
    mx, my = (BW - cw) / 2, (BH - ch) / 2
    if motion == "left":
        cx += mx * (1 - 2 * p)
    elif motion == "right":
        cx -= mx * (1 - 2 * p)
    elif motion == "up":
        cy += my * (1 - 2 * p)
    return (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)


class Cut:
    def __init__(self, reel, idx, spec, t0, cache):
        self.dur, self.t0, self.motion = spec["dur"], t0, spec["motion"]
        key = (spec["scene"], idx) if (BG_IN / f"{reel['id']}_{idx + 1}.png").exists() else spec["scene"]
        if key not in cache:
            cache[key] = build_bg(reel, idx, spec["scene"])
        self.bg, self.anim, self.real = cache[key]
        self.tels = [render_telop(t) for t in spec["telops"]]
        self.first = idx == 0

    def tel_state(self, j, tl):
        tel = self.tels[j]
        fi = tel["fi"] if tel["fi"] is not None else (0.0 if (self.first and tel["at"] == 0) else 0.28)
        if tl < tel["at"]:
            return 0.0, 0.0
        a_in = 1.0 if fi == 0 else min(1.0, (tl - tel["at"]) / fi)
        a = a_in
        if j + 1 < len(self.tels):
            nxt = self.tels[j + 1]
            if nxt["stack"]:
                a *= 1.0 if tl < nxt["at"] + (nxt["fi"] or 0.28) else 0.0
            else:
                a *= min(1.0, max(0.0, (nxt["at"] - tl) / 0.18))
        rise = 0.0 if tel["stack"] or fi < 0.1 else (1 - smooth(a_in)) * 18
        return a, rise

    def frame(self, t):
        tl = t - self.t0
        box = kb_box(self.motion, min(1.0, max(0.0, (tl + XF) / (self.dur + XF))))
        img = self.bg.resize((OW, OH), Image.BILINEAR, box=box)
        fr = np.asarray(img, np.float32) / 255
        fr = fr.copy()
        k = OW / (box[2] - box[0])
        to = lambda x, y: ((x - box[0]) * k, (y - box[1]) * k)  # noqa: E731
        for x, y, sc, seed in self.anim.flames:
            rgb, fl = flame(t, seed, sc * k)
            ox, oy = to(x, y)
            add(fr, rgb, ox, oy - rgb.shape[0] / 2 + 4, 1.0)
            add(fr, glow_sprite(48 * sc * k), ox, oy - 40 * sc * k, C((255, 190, 110)) * 0.45 * fl)
        for x, y, sz, ph, sp in self.anim.tw:
            v = max(0.0, math.sin(t * sp + ph)) ** 3 * sz
            if v > 0.02:
                ox, oy = to(x, y)
                add(fr, SPARK if sz > 0.75 else SPARK_S, ox, oy, C((255, 240, 205)) * v)
        for j, tel in enumerate(self.tels):
            a, rise = self.tel_state(j, tl)
            if a > 0.003:
                blend(fr, tel["rgb"], tel["a"], tel["px"], tel["py"] + int(rise), a)
        return fr


def build_cuts(reel):
    cache, cuts, t = {}, [], 0.0
    for i, spec in enumerate(reel["cuts"]):
        cuts.append(Cut(reel, i, spec, t, cache))
        t += spec["dur"]
    return cuts, t


def render_reel(reel):
    ensure_fonts()
    OUT.mkdir(exist_ok=True)
    cuts, total = build_cuts(reel)
    parts = Particles(reel["seed"])
    brgb, ba = brand_mark()
    rng = np.random.default_rng(5)
    dither = (rng.random((OH, OW, 1), dtype=np.float32) - 0.5) / 255
    name = f"LUNAVEIL_{reel['id']}_{reel['slug']}"
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "bgm.wav"
        write_bgm(wav, total, reel["seed"], reel["chords"])
        mp4 = OUT / f"{name}.mp4"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OW}x{OH}",
               "-r", str(FPS), "-i", "-", "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
               "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-profile:v", "high", "-c:a", "aac",
               "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(mp4)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        nfr = int(round(total * FPS))
        for f in range(nfr):
            t = f / FPS
            i = max(j for j, c in enumerate(cuts) if c.t0 <= t + 1e-9)
            fr = cuts[i].frame(t)
            if i + 1 < len(cuts) and t > cuts[i + 1].t0 - XF:
                w = smooth((t - (cuts[i + 1].t0 - XF)) / XF)
                fr = fr * (1 - w) + cuts[i + 1].frame(t) * w
            parts.draw(fr, t)
            blend(fr, brgb, ba, 0, 205)
            if f == 0:
                Image.fromarray((np.clip(fr, 0, 1) * 255 + 0.5).astype(np.uint8)).save(OUT / f"{name}_cover.png")
            proc.stdin.write((np.clip(fr + dither, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed: {name}")
    (OUT / f"{name}_caption.txt").write_text(reel["caption"] + "\n\n" + " ".join(reel["tags"]) + "\n", encoding="utf-8")
    return str(mp4), total


# ───────────────────────── BGM（その場で合成・著作権フリー） ─────────────────────────

PROG = [[50, 57, 61, 64, 66], [47, 54, 57, 61, 62], [43, 50, 54, 57, 59], [45, 52, 57, 59, 64]]
KEYS = {"C": -2, "D": 0, "E": 2, "F": 3, "G": 5, "A": -5}


def write_bgm(path, dur, seed, key):
    sr = 44100
    n = int(sr * (dur + 0.05))
    t = np.arange(n) / sr
    off = KEYS.get(key, 0)
    mono = np.zeros(n, np.float64)
    seg = dur / len(PROG)
    hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)  # noqa: E731
    for i, chord in enumerate(PROG):
        s0, s1 = max(0.0, i * seg - 1.0), min(dur + 0.05, (i + 1) * seg + 1.6)
        a, b = int(s0 * sr), int(s1 * sr)
        tt = t[a:b]
        env = np.minimum(1, (tt - s0) / 1.4) * np.minimum(1, (s1 - tt) / 1.8)
        if i == 0:
            env = np.minimum(1, (tt + 0.6) / 1.4) * np.minimum(1, (s1 - tt) / 1.8)
        env = np.clip(env, 0, 1) ** 2
        notes = [m + off for m in chord] + [chord[0] + off - 12]
        for m in notes:
            f = hz(m)
            amp = 0.05 if m != notes[-1] else 0.045
            for det in (0.997, 1.0, 1.003):
                ph = 2 * np.pi * f * det * tt
                mono[a:b] += amp / 3 * env * (np.sin(ph) + 0.22 * np.sin(2 * ph) + 0.08 * np.sin(3 * ph))
    mono *= 1 + 0.08 * np.sin(2 * np.pi * 0.15 * t)
    rng = np.random.default_rng(seed)
    penta = [0, 2, 4, 7, 9]
    L, R = mono.copy(), mono.copy()
    bt = 0.05
    while bt < dur - 1.2:
        m = 74 + off + penta[rng.integers(5)] + 12 * rng.integers(0, 2)
        f = hz(m)
        a = int(bt * sr)
        b = min(n, a + int(3.2 * sr))
        tt = t[a:b] - bt
        amp = 0.075 * rng.uniform(0.6, 1.0)
        tone = (np.sin(2 * np.pi * f * tt) * np.exp(-tt / 1.6) + 0.3 * np.sin(2 * np.pi * 2.0 * f * tt) * np.exp(-tt / 0.7)
                + 0.1 * np.sin(2 * np.pi * 3.01 * f * tt) * np.exp(-tt / 0.4)) * np.minimum(1, tt / 0.004) * amp
        pan = rng.uniform(0.25, 0.75)
        L[a:b] += tone * (1 - pan) * 1.4
        R[a:b] += tone * pan * 1.4
        bt += rng.uniform(0.7, 1.9)
    ir_n = int(3.0 * sr)
    it = np.arange(ir_n) / sr
    out = []
    for ch, sd in ((L, 1), (R, 2)):
        noise = np.random.default_rng(seed + sd).normal(0, 1, ir_n)
        noise = np.convolve(noise, np.ones(8) / 8, "same")
        ir = noise * np.exp(-it / 0.85)
        ir[: int(0.02 * sr)] = 0
        ir /= np.sqrt(np.sum(ir ** 2))
        size = 1 << int(np.ceil(np.log2(n + ir_n)))
        wet = np.fft.irfft(np.fft.rfft(ch, size) * np.fft.rfft(ir, size), size)[:n]
        out.append(ch * 0.8 + wet * 0.55)
    st = np.stack(out, 1)
    fade = np.ones(n)
    fade[: int(0.06 * sr)] = np.linspace(0, 1, int(0.06 * sr))
    fo = int(1.0 * sr)
    fade[-fo:] = np.linspace(1, 0, fo)
    st *= fade[:, None]
    st *= 0.6 / max(1e-6, np.abs(st).max())
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((st * 32767).astype("<i2").tobytes())


# ───────────────────────── 確認用・台本 ─────────────────────────

def render_stills(reels):
    ensure_fonts()
    OUT.mkdir(exist_ok=True)
    thumbs = []
    for reel in reels:
        cuts, _ = build_cuts(reel)
        row = []
        for c in cuts:
            t = c.t0 + max(t["at"] for t in c.tels) + 0.6
            fr = c.frame(min(t, c.t0 + c.dur - 0.01))
            im = Image.fromarray((np.clip(fr, 0, 1) * 255 + 0.5).astype(np.uint8))
            row.append(im.resize((270, 480), Image.LANCZOS))
        thumbs.append(row)
    cols = max(len(r) for r in thumbs)
    sheet = Image.new("RGB", (cols * 280 + 10, len(thumbs) * 490 + 10), (20, 14, 26))
    for ri, row in enumerate(thumbs):
        for ci, im in enumerate(row):
            sheet.paste(im, (10 + ci * 280, 10 + ri * 490))
    p = OUT / "stills_sheet.jpg"
    sheet.save(p, quality=88)
    return p


def write_doc(path):
    L = ["# LUNA VEIL リール7本 台本・キャプション・画像プロンプト", "",
         "各リールは 9:16（1080x1920）・約22〜25秒・BGM付きで書き出し済み。",
         "背景はいま自動生成のイラスト調。ChatGPTで写実画像を作って `_bg_in/{リールID}_{カット番号}.png`"
         "（例: `_bg_in/01_3.png`）に置き、`python3 render.py 01` を実行すると、その画像に差し替えて書き出し直せる。", ""]
    for r in REELS:
        total = sum(c["dur"] for c in r["cuts"])
        L += [f"## {r['id']}｜{r['title']}", "",
              f"- 投稿目安：{r['post']}", f"- 尺：約{total:.0f}秒", f"- ねらい：{r['why']}", "",
              "| # | 時間 | テロップ | 背景 |", "|---|---|---|---|"]
        t = 0.0
        for i, c in enumerate(r["cuts"]):
            tels = []
            for tel in c["telops"]:
                lines = [plain(x.lstrip("_").split(":", 1)[1]).replace("|", "／") for x in tel["lines"]]
                tels.append(" / ".join(lines))
            uniq = []
            for x in tels:
                if x not in uniq:
                    uniq.append(x)
            if any(tel["stack"] for tel in c["telops"]):
                uniq = [uniq[-1] + "（1行ずつ表示）"]
            L.append(f"| {i + 1} | {t:.1f}–{t + c['dur']:.1f}s | {'<br>→ '.join(uniq)} | {c['scene']} |")
            t += c["dur"]
        L += ["", "**キャプション**", "", "```", r["caption"], "", " ".join(r["tags"]), "```", "",
              "<details><summary>画像プロンプト（ChatGPTにそのまま貼る）</summary>", ""]
        for i, c in enumerate(r["cuts"]):
            key = c["scene"].replace("_dim", "")
            L += [f"**{r['id']}_{i + 1}.png**（{c['scene']}）", "", "```",
                  PROMPT_HEAD + "\n" + SCENE_PROMPTS[key] + "\n" + PROMPT_TAIL, "```", ""]
        L += ["</details>", ""]
    Path(path).write_text("\n".join(L), encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--doc", action="store_true")
    ap.add_argument("-j", "--jobs", type=int, default=4)
    args = ap.parse_args()
    reels = [r for r in REELS if not args.ids or r["id"] in args.ids]
    if args.doc:
        print(write_doc(OUT.parent / "LUNAVEIL_リール7本_台本.md"))
        return
    if args.stills:
        print(render_stills(reels))
        return
    ensure_fonts()
    with ProcessPoolExecutor(max_workers=max(1, min(args.jobs, len(reels)))) as ex:
        for path, total in ex.map(render_reel, reels):
            print(f"{path}  ({total:.1f}s)")


if __name__ == "__main__":
    main()
