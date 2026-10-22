"""장면 배경을 코드로 그린다 (인터넷·AI 없이 동작).

장면 종류(kind)마다 하늘, 언덕, 물, 빛, 별 같은 요소를 조합한 풍경화를 만든다.
같은 종류라도 seed 를 바꾸면 언덕 모양과 색이 조금씩 달라진다.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

# 장면 종류별 색과 구성
PALETTES = {
    # 하늘 위/아래, 해(빛) 색, 언덕 먼 쪽 → 가까운 쪽
    "pasture": dict(sky=("#5b7fb8", "#f6d6a8"), sun="#fff1c9", sun_pos=(0.72, 0.42), sun_size=0.10,
                    hills=("#9fb59a", "#6f9a63", "#4f7f45", "#2f5a2c"), mist=0.25),
    "water": dict(sky=("#3c5f94", "#f3c9a0"), sun="#ffe6b8", sun_pos=(0.30, 0.40), sun_size=0.07,
                  hills=("#7e8fa8", "#56708a", "#3d5a52"), water=True, mist=0.3),
    "sunrise": dict(sky=("#2d3f73", "#ffb26b"), sun="#fff0c2", sun_pos=(0.50, 0.62), sun_size=0.14,
                    hills=("#8a6f86", "#5b4f6e", "#3b3550", "#221f33"), rays=0.35, path=True, mist=0.2),
    "valley": dict(sky=("#0b1020", "#26304a"), sun="#c9d6ff", sun_pos=(0.5, 0.18), sun_size=0.025,
                   hills=("#2a3248", "#1d2436", "#131827", "#0b0e18"), steep=True, stars=0.6, mist=0.35),
    "presence": dict(sky=("#141d36", "#4c5d86"), sun="#fff4d6", sun_pos=(0.5, 0.0), sun_size=0.18,
                     hills=("#38415c", "#283049", "#1b2136", "#111526"), steep=True, rays=0.75, mist=0.3),
    "glory": dict(sky=("#6b4b2e", "#ffd99a"), sun="#fffaf0", sun_pos=(0.5, 0.35), sun_size=0.22,
                  hills=("#c79a6a", "#9a7150", "#6d4f3a"), rays=0.6, mist=0.4),
    "house": dict(sky=("#0d1430", "#3a3f6b"), sun="#ffe9b0", sun_pos=(0.62, 0.58), sun_size=0.05,
                  hills=("#2e3557", "#1f2542", "#141930"), stars=1.0, house=True, mist=0.15),
    "sky": dict(sky=("#3b5a8c", "#c9d8ec"), sun="#ffffff", sun_pos=(0.6, 0.3), sun_size=0.12,
                hills=("#8ea3c0", "#6c84a6"), clouds=True, mist=0.3),
}
KINDS = tuple(PALETTES)


def _rgb(hex_color: str) -> np.ndarray:
    h = hex_color.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def _ridge(rng: np.random.Generator, w: int, base: float, amp: float, steep: bool) -> np.ndarray:
    """언덕 윤곽선 (y 좌표, 0~1)."""
    x = np.linspace(0, 1, w)
    y = np.full(w, base)
    octaves = 5 if steep else 3
    for o in range(octaves):
        freq = (1.5 if not steep else 2.5) * (2 ** o) * rng.uniform(0.8, 1.2)
        phase = rng.uniform(0, 2 * np.pi)
        y -= amp / (1.8 ** o) * np.sin(2 * np.pi * freq * x + phase)
    if steep:  # 골짜기: 가운데가 낮고 양옆이 높다
        y -= amp * 2.2 * (np.abs(x - 0.5) * 2) ** 1.6
    return y


def paint(kind: str, width: int, height: int, seed: int = 0) -> Image.Image:
    if kind not in PALETTES:
        kind = "sky"
    p = PALETTES[kind]
    rng = np.random.default_rng(seed * 7919 + KINDS.index(kind))
    W, H = width, height
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    yn, xn = yy / H, xx / W

    # 1) 하늘 그라데이션
    top, bottom = _rgb(p["sky"][0]), _rgb(p["sky"][1])
    t = np.clip(yn / 0.75, 0, 1)[..., None] ** 1.2
    img = top * (1 - t) + bottom * t

    # 2) 별
    if p.get("stars"):
        n = int(W * H / 2500 * p["stars"])
        sx, sy = rng.integers(0, W, n), rng.integers(0, int(H * 0.6), n)
        b = rng.uniform(0.3, 1.0, n) * (1 - sy / (H * 0.6))
        star = np.zeros((H, W), np.float32)
        star[sy, sx] = b * 255
        star_img = Image.fromarray(star.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
        img += np.asarray(star_img, np.float32)[..., None] * 2.2

    # 3) 해 / 빛 무리
    sun = _rgb(p["sun"])
    cx, cy = p["sun_pos"]
    d = np.sqrt(((xn - cx) * W / H) ** 2 + (yn - cy) ** 2)
    r = p["sun_size"]
    glow = np.exp(-(d / (r * 2.8)) ** 2) * 0.65 + np.exp(-(d / (r * 8)) ** 2) * 0.35
    core = np.clip(1 - (d - r * 0.35) / (r * 0.08), 0, 1) if kind not in ("presence", "glory") else 0
    a = np.clip(glow + core, 0, 1)[..., None]
    img = img * (1 - a) + sun * a

    # 4) 빛줄기
    if p.get("rays"):
        ang = np.arctan2(yn - cy, (xn - cx) * W / H)
        n_rays = rng.integers(9, 15)
        rays = (np.sin(ang * n_rays + rng.uniform(0, 6)) * 0.5 + 0.5) ** 6
        rays *= np.exp(-d * 1.4) * p["rays"]
        rays_img = Image.fromarray((np.clip(rays, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))
        ra = np.asarray(rays_img, np.float32)[..., None] / 255
        img = img * (1 - ra) + sun * ra

    # 5) 구름
    if p.get("clouds"):
        noise = rng.random((H // 40 + 2, W // 40 + 2)).astype(np.float32)
        cl = Image.fromarray((noise * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
        cl = np.asarray(cl.filter(ImageFilter.GaussianBlur(30)), np.float32) / 255
        ca = (np.clip((cl - 0.5) * 3, 0, 1) * (1 - yn) ** 2 * 0.7)[..., None]
        img = img * (1 - ca) + 255 * ca

    # 6) 언덕 (먼 곳 → 가까운 곳)
    hills = p["hills"]
    horizon = 0.62 if not p.get("water") else 0.58
    water_line = None
    steep = p.get("steep", False)
    for i, color in enumerate(hills):
        k = i / max(len(hills) - 1, 1)
        base = horizon + k * (0.25 if not p.get("water") else 0.06)
        amp = (0.05 + 0.03 * k) * (1.6 if steep else 1.0)
        ridge = _ridge(rng, W, base, amp, steep)
        mask = (yn >= ridge[None, :]).astype(np.float32)
        mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5)),
                          np.float32)[..., None] / 255
        c = _rgb(color)
        # 언덕 안에서도 아래로 갈수록 살짝 어둡게
        shade = (1 - 0.25 * np.clip((yn - base) / 0.4, 0, 1))[..., None]
        img = img * (1 - mask) + (c * shade) * mask
        # 먼 산과 가까운 산 사이 안개
        if p.get("mist") and i < len(hills) - 1:
            m = np.exp(-((yn - (base + 0.03)) / 0.05) ** 2)[..., None] * p["mist"]
            img = img * (1 - m) + bottom * m
        if p.get("water") and i == len(hills) - 1:
            water_line = int(H * (base + 0.04))

    # 7) 물 (하늘 반사 + 잔물결)
    if water_line:
        sky_part = img[: water_line][::-1]
        h = H - water_line
        reflect = np.zeros((h, W, 3), np.float32)
        reflect[: min(h, len(sky_part))] = sky_part[:h]
        ripple = np.sin(np.arange(h)[:, None] * 0.9 + np.sin(np.arange(W)[None, :] * 0.01) * 3) * 0.015
        dark = np.linspace(0.85, 0.55, h)[:, None, None]
        img[water_line:] = reflect * (dark + ripple[..., None]) + _rgb("#1c2b3f") * (1 - dark) * 0.6

    # 8) 길 (해를 향해 굽이굽이 이어지는 오솔길)
    if p.get("path"):
        depth = np.clip((yn - 0.74) / 0.26, 0, 1)          # 0 = 먼 곳, 1 = 화면 아래
        width_at = 0.003 + 0.07 * depth ** 1.8
        center = 0.5 + 0.08 * np.sin(depth * 5.5 + 0.6) * depth
        on_path = (np.abs(xn - center) < width_at) & (yn > 0.74)
        pa = np.asarray(Image.fromarray((on_path * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)),
                        np.float32)[..., None] / 255 * (0.25 + 0.35 * depth[..., None])
        img = img * (1 - pa) + _rgb("#f0c08e") * pa

    # 9) 언덕 위 작은 성당과 창문 불빛
    if p.get("house"):
        hx, hy = int(W * 0.62), int(H * 0.60)
        hw, hh = int(W * 0.06), int(H * 0.06)
        dark = _rgb("#0b0f1f")
        body = (np.abs(xx - hx) < hw / 2) & (yy > hy - hh) & (yy < hy + 6)
        roof_h = hw * 0.35
        roof = (yy <= hy - hh) & (yy > hy - hh - roof_h) & (np.abs(xx - hx) < (yy - (hy - hh - roof_h)) * (hw / 2) / roof_h)
        # 왼쪽 종탑 + 십자가
        tx, tw = hx - hw * 0.32, hw * 0.16
        tower_top = hy - hh - hw * 0.75
        tower = (np.abs(xx - tx) < tw) & (yy > tower_top) & (yy <= hy - hh + 2)
        spire = (yy <= tower_top) & (yy > tower_top - hw * 0.3) & (np.abs(xx - tx) < (yy - (tower_top - hw * 0.3)) * tw / (hw * 0.3))
        ctop = tower_top - hw * 0.3
        cross = ((np.abs(xx - tx) < 2.5) & (yy > ctop - hw * 0.22) & (yy <= ctop)) | \
                ((np.abs(xx - tx) < hw * 0.06) & (np.abs(yy - (ctop - hw * 0.15)) < 2.5))
        img[body | roof | tower | spire | cross] = dark
        win = (np.abs(xx - (hx + hw * 0.12)) < hw * 0.07) & (yy > hy - hh * 0.8) & (yy < hy - hh * 0.3)
        door = (np.abs(xx - (hx + hw * 0.12)) < hw * 0.07) & (yy > hy - hh * 0.25) & (yy < hy + 6)
        img[win | door] = _rgb("#ffd889")
        dw = np.sqrt(((xx - hx) / H) ** 2 + ((yy - (hy - hh / 2)) / H) ** 2)
        wa = (np.exp(-(dw / 0.09) ** 2) * 0.45)[..., None]
        img = img * (1 - wa) + _rgb("#ffcf7a") * wa

    # 10) 가장자리 어둡게 + 고운 필름 입자
    vig = 1 - 0.35 * (((xn - 0.5) * 1.3) ** 2 + ((yn - 0.5) * 1.1) ** 2)
    img = img * vig[..., None]
    img += rng.normal(0, 3.0, img.shape[:2])[..., None]
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    return out.filter(ImageFilter.GaussianBlur(0.6))
