"""Paper compositing + degradations. The geometric part returns the 3x3 homography so geometry can follow the image."""
import math
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

BG_DIR = Path(__file__).resolve().parents[1] / "background"
_cache = {}


def backgrounds():
    return sorted(BG_DIR.glob("*.jp*g")) + sorted(BG_DIR.glob("*.png"))


def paper(rng, W, H):
    files = backgrounds()
    f = rng.choice(files)
    if f not in _cache:
        _cache.clear()
        _cache[f] = np.asarray(Image.open(f).convert("RGB"))
    im = _cache[f]
    h, w = im.shape[:2]
    ar = W / H
    ch = int(min(h, w / ar) * rng.uniform(.55, 1.0))
    cw = int(ch * ar)
    y = rng.randint(0, max(0, h - ch))
    x = rng.randint(0, max(0, w - cw))
    crop = im[y:y + ch, x:x + cw]
    if rng.random() < .5:
        crop = crop[:, ::-1]
    if rng.random() < .3:
        crop = crop[::-1]
    crop = cv2.resize(np.ascontiguousarray(crop), (W, H), interpolation=cv2.INTER_AREA if cw > W else cv2.INTER_CUBIC).astype(np.float32)
    m = crop.mean()
    if m < 170:   # keep text readable on dark scans
        crop = np.clip(crop * (185 / m), 0, 255)
    return crop


def render_ink(page):
    """flat ink coverage (0..1) of the page ops"""
    img = Image.new("L", (page.W, page.H), 0)
    d = ImageDraw.Draw(img)
    for op in page.ops:
        if op[0] == "t":
            _, x, y, t, f = op
            d.text((x, y), t, font=f, fill=255, anchor="ls")
        else:
            _, x0, y0, x1, y1, w = op
            d.line([(x0, y0), (x1, y1)], fill=255, width=w)
    return np.asarray(img, dtype=np.float32) / 255


def compose(page, rng):
    W, H = page.W, page.H
    a = render_ink(page)
    a = cv2.GaussianBlur(a, (0, 0), rng.uniform(.4, 1.0))
    a *= 1 - 0.25 * cv2.GaussianBlur(np.random.default_rng(rng.randint(0, 2 ** 31)).random((H, W)).astype(np.float32), (0, 0), 1.2)
    bg = paper(rng, W, H)
    ink = np.array([rng.uniform(5, 50), rng.uniform(5, 40), rng.uniform(5, 35)], np.float32) / 255
    if rng.random() < .3:
        ink = np.array([.25, .15, .08], np.float32) * rng.uniform(.6, 1)
    strength = rng.uniform(.8, 1.0)
    out = bg * (1 - a[..., None] * strength * (1 - ink))
    if rng.random() < .4:  # bleed-through of the verso
        b = cv2.GaussianBlur(a[:, ::-1], (0, 0), rng.uniform(1.5, 3))
        out *= 1 - (b * rng.uniform(.04, .16))[..., None]
    gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
    shade = 1 - rng.uniform(0, .12) * (gx / W * math.cos(rng.uniform(0, 6.28)) + gy / H * math.sin(rng.uniform(0, 6.28)))
    out *= shade[..., None]
    if rng.random() < .4:  # gutter
        left = rng.random() < .5
        d = (gx / W) if left else 1 - gx / W
        out *= (1 - rng.uniform(.1, .35) * np.exp(-(d / rng.uniform(.03, .08)) ** 2))[..., None]
    out += np.random.default_rng(rng.randint(0, 2 ** 31)).normal(0, rng.uniform(1, 5), out.shape).astype(np.float32)
    return np.clip(out, 0, 255)


def homography(rng, W, H):
    ang = math.radians(rng.uniform(-1.3, 1.3))
    c, s = math.cos(ang), math.sin(ang)
    cx, cy = W / 2, H / 2
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    rot = np.float32([[cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c] for x, y in src])
    j = rng.uniform(0, .012)
    dst = rot + np.float32([[rng.uniform(-j, j) * W, rng.uniform(-j, j) * H] for _ in range(4)])
    return cv2.getPerspectiveTransform(src, dst)


def apply(img, M):
    return cv2.warpPerspective(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def pts(M, p):
    a = np.float32(p).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(a, M).reshape(-1, 2).tolist()


def finish(img, rng):
    if rng.random() < .4:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(.4, 1.1))
    return np.clip(img, 0, 255).astype(np.uint8)
