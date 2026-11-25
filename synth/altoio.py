"""ALTO <-> JSON page model used by the review app (review_app/server.py).

Page model:
  {w, h, regions:[{id,type,box:[x0,y0,x1,y1]}],
   lines:[{id,region,type,bl:[[x,y],..],poly:[[x,y],..],text}], order:[line ids, global reading order]}
Line type is derived from the region type on save (LINE_FOR_REGION), same rule as build_dataset.py.
"""
from pathlib import Path

from lxml import etree

ALTO = "http://www.loc.gov/standards/alto/ns-v4#"
NS = {"a": ALTO}
Q = lambda t: "{%s}%s" % (ALTO, t)

REGIONS = ["MainZone-P", "MainZone-Continued", "MainZone-Head", "MainZone-Lg", "MainZone-Quote", "NumberingZone",
           "RunningTitleZone", "MarginTextZone", "TableZone", "ApparatusZone", "GraphicZone", "DropCapitalZone", "CustomZone-Noise"]
LINES = ["DefaultLine", "DefaultLine-Margin", "HeadingLine", "ApparatusLine"]
LINE_FOR_REGION = {r: "DefaultLine" for r in REGIONS}
LINE_FOR_REGION.update({"ApparatusZone": "ApparatusLine", "MarginTextZone": "DefaultLine-Margin", "MainZone-Head": "HeadingLine"})
LEGACY = {"MainZone-Text": "MainZone-P", "MainZone-Text#latin": "MainZone-P", "MainZone-Continued#latin": "MainZone-Continued",
          "MainZone-Margin#att_crit": "ApparatusZone", "text": "MainZone-P"}


def _pts(s):
    v = [int(round(float(x))) for x in s.split()]
    return [[a, b] for a, b in zip(v[::2], v[1::2])]


def image_path(xml):
    xml = Path(xml)
    p = xml.with_suffix(".png")
    if p.exists():
        return p
    t = etree.parse(str(xml)).getroot().find(".//a:fileName", NS)
    return xml.parent / (t.text if t is not None and t.text else xml.stem + ".png")


def read_page(xml):
    root = etree.parse(str(xml)).getroot()
    tags = {o.get("ID"): o.get("LABEL") for o in root.iterfind(".//a:OtherTag", NS)}
    page = root.find(".//a:Page", NS)
    regions, lines, seq = [], [], []
    for ri, tb in enumerate(root.iterfind(".//a:TextBlock", NS), 1):
        label = tags.get((tb.get("TAGREFS") or "").split()[0], None) if tb.get("TAGREFS") else None
        label = LEGACY.get(label, label) or "MainZone-P"
        rid = "r%d" % ri
        xs, ys = [], []
        for tl in tb.iterfind("a:TextLine", NS):
            bl = _pts(tl.get("BASELINE"))
            pg = tl.find("a:Shape/a:Polygon", NS)
            poly = _pts(pg.get("POINTS")) if pg is not None else []
            st = tl.find("a:String", NS)
            lid = tl.get("ID") or "%s_l%d" % (rid, len(lines) + 1)
            while lid in seq:                      # duplicate ids (segfix add_line in one batch): keep the first, rename the others
                lid += "_d"
            lines.append(dict(id=lid, region=rid, type=label, bl=bl, poly=poly,
                              text=(st.get("CONTENT") if st is not None else "") or ""))
            seq.append(lid)
            for p in (poly or bl):
                xs.append(p[0]); ys.append(p[1])
        if tb.get("HPOS") is not None:
            x0, y0 = int(float(tb.get("HPOS"))), int(float(tb.get("VPOS")))
            box = [x0, y0, x0 + int(float(tb.get("WIDTH"))), y0 + int(float(tb.get("HEIGHT")))]
        elif xs:
            box = [min(xs), min(ys), max(xs), max(ys)]
        else:
            continue
        regions.append(dict(id=rid, type=label, box=box))
    ids = {l["id"] for l in lines}
    order = [e.get("REF") for e in root.iterfind(".//a:ReadingOrder//a:ElementRef", NS) if e.get("REF") in ids]
    order = list(dict.fromkeys(order))
    order += [i for i in seq if i not in set(order)]
    return dict(w=int(page.get("WIDTH")), h=int(page.get("HEIGHT")), regions=regions, lines=lines, order=order)


def write_page(path, img_name, pg, note="cllg-segmentation review app"):
    W, H = pg["w"], pg["h"]
    rtag = {r: "BT%d" % (i + 1) for i, r in enumerate(REGIONS)}
    ltag = {l: "LT%d" % (i + 1) for i, l in enumerate(LINES)}
    root = etree.Element(Q("alto"), nsmap={None: ALTO})
    d = etree.SubElement(root, Q("Description"))
    etree.SubElement(d, Q("MeasurementUnit")).text = "pixel"
    sii = etree.SubElement(d, Q("sourceImageInformation")); etree.SubElement(sii, Q("fileName")).text = img_name
    pr = etree.SubElement(d, Q("Processing"), ID="proc_1")
    etree.SubElement(pr, Q("processingCategory")).text = "other"
    etree.SubElement(pr, Q("processingStepDescription")).text = note
    tg = etree.SubElement(root, Q("Tags"))
    for r in REGIONS:
        etree.SubElement(tg, Q("OtherTag"), ID=rtag[r], LABEL=r, DESCRIPTION="block type " + r)
    for l in LINES:
        etree.SubElement(tg, Q("OtherTag"), ID=ltag[l], LABEL=l, DESCRIPTION="line type " + l)
    lmap = {l["id"]: l for l in pg["lines"]}
    order = [i for i in pg["order"] if i in lmap] + [i for i in lmap if i not in set(pg["order"])]
    ro = etree.SubElement(root, Q("ReadingOrder")); og = etree.SubElement(ro, Q("OrderedGroup"), ID="ro_0")
    for k, i in enumerate(order, 1):
        etree.SubElement(og, Q("ElementRef"), ID="o_%d" % k, REF=i)
    lay = etree.SubElement(root, Q("Layout"))
    page = etree.SubElement(lay, Q("Page"), WIDTH=str(W), HEIGHT=str(H), PHYSICAL_IMG_NR="0", ID="page_0")
    ps = etree.SubElement(page, Q("PrintSpace"), HPOS="0", VPOS="0", WIDTH=str(W), HEIGHT=str(H))
    pos = {i: k for k, i in enumerate(order)}
    regs = sorted(pg["regions"], key=lambda r: min([pos[l["id"]] for l in pg["lines"] if l["region"] == r["id"]] or [10 ** 9]))
    for r in regs:
        x0, y0, x1, y1 = (int(round(v)) for v in r["box"])
        x0, x1 = max(0, min(x0, x1)), min(W, max(x0, x1)); y0, y1 = max(0, min(y0, y1)), min(H, max(y0, y1))
        tb = etree.SubElement(ps, Q("TextBlock"), ID=r["id"], HPOS=str(x0), VPOS=str(y0), WIDTH=str(x1 - x0),
                              HEIGHT=str(y1 - y0), TAGREFS=rtag.get(r["type"], rtag["MainZone-P"]))
        sh = etree.SubElement(tb, Q("Shape"))
        etree.SubElement(sh, Q("Polygon"), POINTS="%d %d %d %d %d %d %d %d" % (x0, y0, x0, y1, x1, y1, x1, y0))
        for l in sorted((l for l in pg["lines"] if l["region"] == r["id"]), key=lambda l: pos[l["id"]]):
            poly = l["poly"] if len(l.get("poly", [])) >= 3 else [[l["bl"][0][0], l["bl"][0][1] - 30], [l["bl"][-1][0], l["bl"][-1][1] - 30],
                                                                 [l["bl"][-1][0], l["bl"][-1][1] + 8], [l["bl"][0][0], l["bl"][0][1] + 8]]
            px = [p[0] for p in poly]; py = [p[1] for p in poly]
            tl = etree.SubElement(tb, Q("TextLine"), ID=l["id"], TAGREFS=ltag[LINE_FOR_REGION.get(r["type"], "DefaultLine")],
                                  BASELINE=" ".join("%d %d" % (round(p[0]), round(p[1])) for p in l["bl"]),
                                  HPOS=str(min(px)), VPOS=str(min(py)), WIDTH=str(max(px) - min(px)), HEIGHT=str(max(py) - min(py)))
            sh = etree.SubElement(tl, Q("Shape"))
            etree.SubElement(sh, Q("Polygon"), POINTS=" ".join("%d %d" % (round(p[0]), round(p[1])) for p in poly))
            etree.SubElement(tl, Q("String"), CONTENT=l.get("text", ""))
    etree.ElementTree(root).write(str(path), xml_declaration=True, encoding="UTF-8", pretty_print=True)


def clean_baseline(b, w=None, h=None):
    """integer points, consecutive duplicates removed, optionally clamped to the image; None when the line is shorter than 6 px"""
    pts = []
    for p in b:
        q = (int(round(p[0])), int(round(p[1])))
        if w is not None:
            q = (min(max(q[0], 0), w - 1), min(max(q[1], 0), h - 1))
        if not pts or q != pts[-1]:
            pts.append(q)
    length = sum(((pts[k + 1][0] - pts[k][0]) ** 2 + (pts[k + 1][1] - pts[k][1]) ** 2) ** .5 for k in range(len(pts) - 1))
    return pts if len(pts) >= 2 and length >= 6 else None


def polygons(img_path, baselines):
    """kraken polygon masks for a list of baselines ([[x,y],..]); a band above the baseline when kraken cannot (zero-length or
    degenerate baselines, lines on the image edge: those made kraken print NaN / TopologyException warnings)."""
    import warnings
    import numpy as np
    from PIL import Image
    from kraken.lib.segmentation import calculate_polygonal_environment
    img = Image.open(img_path).convert("L")
    hgt = max(14, img.width // 45)
    band = lambda b: [[b[0][0], b[0][1] - hgt], [b[-1][0], b[-1][1] - hgt], [b[-1][0], b[-1][1] + hgt // 4], [b[0][0], b[0][1] + hgt // 4]]
    clean = [clean_baseline(b, img.width, img.height) for b in baselines]
    good = [i for i, c in enumerate(clean) if c]
    res = [None] * len(baselines)
    if good:
        try:
            with warnings.catch_warnings(), np.errstate(all="ignore"):
                warnings.simplefilter("ignore")
                polys = calculate_polygonal_environment(img, [[tuple(p) for p in clean[i]] for i in good])
            for i, p in zip(good, polys):
                if p is not None and len(p) >= 3 and np.isfinite(np.asarray(p, dtype=float)).all():
                    res[i] = [[int(a), int(c)] for a, c in p]
        except Exception:
            pass
    return [res[i] or band([list(q) for q in (clean[i] or [(int(round(p[0])), int(round(p[1]))) for p in b])]) for i, b in enumerate(baselines)]


def auto_order(pg):
    """Geometric reading order for a page model: columns / facing pages left to right; inside a column the header band
    (running title, numbering above the first text line) first, then rows top to bottom, left to right inside a row
    (so a margin number is read next to its line). Columns come from the x-extent of the body regions (overlapping regions
    merge); numbering / marginal / running-title lines join the nearest column."""
    H = pg["h"]; tol = max(6, H / 400)
    SIDE = ("NumberingZone", "RunningTitleZone", "MarginTextZone")
    rt = {r["id"]: r["type"] for r in pg["regions"]}
    mid = lambda l: ((l["bl"][0][0] + l["bl"][-1][0]) / 2, (l["bl"][0][1] + l["bl"][-1][1]) / 2)
    boxes = sorted([r["box"] for r in pg["regions"] if r["type"] not in SIDE and r["box"][2] - r["box"][0] >= .12 * pg["w"]
                    and any(l["region"] == r["id"] for l in pg["lines"])])   # narrow stubs (stray margin numbers) never make a column
    cols = []                                  # merged [x0, x1]
    for b in boxes:
        for c in cols:
            ov = min(c[1], b[2]) - max(c[0], b[0])
            if ov >= .3 * min(c[1] - c[0], b[2] - b[0]):
                c[0], c[1] = min(c[0], b[0]), max(c[1], b[2]); break
        else:
            cols.append([b[0], b[2]])
    cols.sort()
    for _ in range(2):                         # a merge can make two columns overlap
        out = []
        for c in cols:
            if out and min(out[-1][1], c[1]) - max(out[-1][0], c[0]) > 0:
                out[-1] = [min(out[-1][0], c[0]), max(out[-1][1], c[1])]
            else:
                out.append(c)
        cols = out
    if not cols:
        cols = [[0, pg["w"]]]
    def colof(l):
        x = mid(l)[0]
        return min(range(len(cols)), key=lambda i: 0 if cols[i][0] <= x <= cols[i][1] else min(abs(x - cols[i][0]), abs(x - cols[i][1])))
    out = []
    for ci in range(len(cols)):
        ls = [l for l in pg["lines"] if colof(l) == ci]
        body = [mid(l)[1] for l in ls if rt.get(l["region"]) not in SIDE]  # (numbers typed Apparatus etc. still count; harmless)
        y0 = min(body) if body else 0
        hd = [l for l in ls if rt.get(l["region"]) == "RunningTitleZone" or (rt.get(l["region"]) == "NumberingZone" and mid(l)[1] < y0 - tol)]
        hid = {l["id"] for l in hd}
        for grp in (hd, [l for l in ls if l["id"] not in hid]):
            grp = sorted(grp, key=lambda l: mid(l)[1]); row = []
            for l in grp:
                if row and mid(l)[1] - mid(row[0])[1] > tol:
                    out += [r["id"] for r in sorted(row, key=lambda r: min(p[0] for p in r["bl"]))]; row = []
                row.append(l)
            out += [r["id"] for r in sorted(row, key=lambda r: min(p[0] for p in r["bl"]))]
    return out
