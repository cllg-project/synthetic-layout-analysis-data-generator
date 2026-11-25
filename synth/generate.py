"""python -m synth.generate --n 100 --out out/ --seed 0 --workers 4 [--overlay]"""
import argparse
import random
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

from . import altoio, augment
from .corpus import Corpus
from .layout import Builder, reading_order

_corpus = None


def make_page(seed, skew=False, parallel=0.0, parallel_only=False):
    """returns (rgb uint8 image, altoio page model)"""
    global _corpus
    _corpus = _corpus or Corpus()
    rng = random.Random(seed)
    page = Builder(rng, _corpus, parallel=parallel, parallel_only=parallel_only).build()
    for _ in range(8 if parallel_only else 3):  # a page with nothing on it (or, in parallel-only mode, no band) is useless
        if page.lines and (page.bands or not parallel_only):
            break
        page = Builder(rng, _corpus, parallel=parallel, parallel_only=parallel_only).build()
    order = reading_order(page.lines, page.st.size)
    img = augment.compose(page, rng)
    M = augment.homography(rng, page.W, page.H) if skew else np.eye(3)
    img = augment.finish(augment.apply(img, M), rng)
    W, H = page.W, page.H
    clip = lambda p: [[min(max(int(round(x)), 0), W - 1), min(max(int(round(y)), 0), H - 1)] for x, y in p]
    lines, boxes = [], {}
    for l in page.lines:
        poly = clip(augment.pts(M, l["poly"]))
        bl = clip(augment.pts(M, l["bl"]))
        lines.append(dict(id=l["id"], region=l["region"], type="", bl=bl, poly=poly, text=l["text"]))
        boxes.setdefault(l["region"], []).extend(poly)
    for r in page.regions:
        if r["extra"]:
            boxes.setdefault(r["id"], []).extend(clip(augment.pts(M, r["extra"])))
    regions = []
    for r in page.regions:
        p = boxes.get(r["id"])
        if not p:
            continue
        xs, ys = [q[0] for q in p], [q[1] for q in p]
        regions.append(dict(id=r["id"], type=r["type"], box=[min(xs), min(ys), max(xs), max(ys)]))
    model = dict(w=W, h=H, regions=regions, lines=lines, order=[l["id"] for l in order])
    return img, model


def job(args):
    i, seed, out, overlay, skew, parallel, parallel_only = args
    name = "synth_%06d" % i
    img, model = make_page(seed, skew, parallel, parallel_only)
    q = random.Random(seed).randint(70, 95)
    cv2.imwrite(str(out / (name + ".jpg")), cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, q])
    altoio.write_page(out / (name + ".xml"), name + ".jpg", model, note="cllg-synth-segmentation")
    if overlay:
        draw_overlay(img, model, out / "overlay" / (name + ".png"))
    return name


def draw_overlay(img, m, path):
    path.parent.mkdir(exist_ok=True)
    o = img.copy()
    cols = {}
    rng = random.Random(1)
    for r in m["regions"]:
        c = cols.setdefault(r["type"], tuple(rng.randint(40, 230) for _ in range(3)))
        cv2.rectangle(o, tuple(r["box"][:2]), tuple(r["box"][2:]), c, 2)
        cv2.putText(o, r["type"], (r["box"][0], max(12, r["box"][1] - 3)), cv2.FONT_HERSHEY_SIMPLEX, .5, c, 1)
    pos = {i: k for k, i in enumerate(m["order"], 1)}
    for l in m["lines"]:
        cv2.polylines(o, [np.int32(l["bl"])], False, (255, 0, 0), 1)
        cv2.putText(o, str(pos[l["id"]]), tuple(l["bl"][0]), cv2.FONT_HERSHEY_SIMPLEX, .4, (255, 0, 0), 1)
    cv2.imwrite(str(path), cv2.cvtColor(o, cv2.COLOR_RGB2BGR))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default="out")
    ap.add_argument("--start", type=int, default=0, help="first page index (>0 appends to an existing output dir and its splits.tsv)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--skew", action="store_true", help="optional rotation/perspective (off: pages stay straight)")
    ap.add_argument("--parallel", type=float, default=0.0, help="probability that a prose page has a two-column (parallel text) band")
    ap.add_argument("--parallel-only", action="store_true", help="evaluation: only prose pages, each with a two-column band")
    ap.add_argument("--overlay", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    Corpus()  # build cache before forking
    jobs = [(i, a.seed * 1_000_003 + i, out, a.overlay, a.skew, a.parallel, a.parallel_only) for i in range(a.start, a.start + a.n)]
    with Pool(a.workers) as p:
        names = p.map(job, jobs, chunksize=4)
    with open(out / "splits.tsv", "a" if a.start else "w") as f:
        for i, n in enumerate(names, a.start):
            f.write("%s\t%s\n" % (n, "test" if i % 20 == 0 else "val" if i % 20 == 1 else "train"))
    print("wrote", len(names), "pages to", out)


if __name__ == "__main__":
    main()
