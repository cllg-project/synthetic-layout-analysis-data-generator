"""Page layout engine: builds typed regions / lines / draw ops in page pixel coordinates (before augmentation)."""
import random
import re
import unicodedata

from . import apparatus
from .fonts import Style, pick_family

TOL = 3.5  # pt-ish tolerance for "same row" (scaled by size/ 30)


class Page:
    def __init__(self, W, H, style):
        self.W, self.H, self.st = W, H, style
        self.ops = []        # ("t", x, ybase, text, font) | ("l", x0, y0, x1, y1, width)
        self.regions = []    # dict(id,type,lines[],extra[],header)
        self.lines = []
        self.tag = None      # (band id, column) while a parallel-column band is being laid out
        self.bands = 0

    # ---- primitives
    def region(self, rtype, header=False):
        r = dict(id="tb_%d" % len(self.regions), type=rtype, lines=[], extra=[], header=header)
        self.regions.append(r)
        return r

    def put_line(self, reg, placed, ybase, size_scale=1.0):
        """placed: list of (word, font, x). Adds draw ops and a line with its ink polygon."""
        if not placed:
            return None
        S = self.st.size * size_scale
        top, bot = 0.72 * S, 0.22 * S
        x0 = min(x for _, _, x in placed)
        x1 = 0
        for w, f, x in placed:
            l, t, r, b = f.getbbox(w, anchor="ls")
            top, bot = max(top, -t), max(bot, b)
            x1 = max(x1, x + f.getlength(w))
            self.ops.append(("t", x, ybase, w, f))
        top = min(top, 1.15 * S)
        text = " ".join(w for w, _, _ in placed)
        ln = dict(id="line_%d" % len(self.lines), region=reg["id"], text=text, x0=x0, x1=x1, y=ybase,
                  poly=[[x0 - 1, ybase - top - 1], [x1 + 1, ybase - top - 1], [x1 + 1, ybase + bot + 1], [x0 - 1, ybase + bot + 1]],
                  bl=[[x0, ybase], [x1, ybase]], header=reg["header"], size=S, tag=self.tag)
        self.lines.append(ln)
        reg["lines"].append(ln)
        return ln


def words_of(text, font):
    return [(w, font) for w in text.split()]


def wrap(words, width, space, indent=0.0, hang=0.0, justify=True, last_justify=False):
    """greedy wrap. returns list of rows, each (list of (word, font, x), is_last)"""
    rows, cur, cw = [], [], 0.0
    lim = lambda first: width - (indent if first else hang)
    for w, f in words:
        wl = f.getlength(w)
        add = wl if not cur else space + wl
        if cur and cw + add > lim(not rows):
            rows.append(cur)
            cur, cw = [(w, f, wl)], wl
        else:
            cur.append((w, f, wl))
            cw += add
    if cur:
        rows.append(cur)
    out = []
    for i, row in enumerate(rows):
        off = indent if i == 0 else hang
        avail = width - off
        n = len(row)
        tot = sum(wl for _, _, wl in row)
        last = i == len(rows) - 1
        gap = space
        if justify and n > 1 and (not last or last_justify):
            gap = max(space * .6, (avail - tot) / (n - 1))  # every non-final row reaches the right edge
        x, placed = off, []
        for w, f, wl in row:
            placed.append((w, f, x))
            x += wl + gap
        out.append((placed, last))
    return out


class Builder:
    def __init__(self, rng, corpus, W=None, parallel=0.0, parallel_only=False):
        self.rng, self.corpus = rng, corpus
        self.parallel_only = parallel_only  # evaluation mode: prose pages only, always with a band
        self.parallel = 1.0 if parallel_only else parallel  # probability that a prose page contains a two-column (parallel text) band
        W = W or rng.randint(1000, 1500)
        H = int(W * rng.uniform(1.32, 1.5))
        S = W / rng.uniform(32, 44)
        self.pg = Page(W, H, Style(pick_family(rng), int(round(S))))
        self.S = self.pg.st.size
        self.lh = self.S * rng.uniform(1.32, 1.55)
        self.space = self.S * 0.27

    # ------------------------------------------------------------------
    def build(self):
        rng, pg, S, W, H = self.rng, self.pg, self.S, self.pg.W, self.pg.H
        mode = rng.choices(["prose", "verse", "scholia"], [.45, .25, .30])[0]
        if self.parallel_only:
            mode = "prose"
        self.mode = mode
        marg_outer = rng.random() < .4
        self.mL = W * rng.uniform(.12, .16) if marg_outer else W * rng.uniform(.09, .14)
        self.mR = W * rng.uniform(.10, .15)
        if rng.random() < .5:
            self.mL, self.mR = self.mR, self.mL
        self.mL, self.mR = max(self.mL, W * .09), max(self.mR, W * .09)
        self.x0, self.x1 = self.mL, W - self.mR
        self.bw = self.x1 - self.x0
        top = H * rng.uniform(.045, .08)
        y = self.header(top)
        bottom = H * rng.uniform(.9, .95)
        self.margin_notes = rng.random() < .3
        self.page_words = []
        # apparatus reservation
        self.has_app = rng.random() < (.85 if mode != "scholia" else .0)
        self.asz = 0.74
        self.apl = S * self.asz * 1.3
        n_app = rng.randint(3, 9) if self.has_app else 0
        app_h = n_app * self.apl + self.lh * .9 if self.has_app else 0
        limit = bottom - app_h
        {"prose": self.prose, "verse": self.verse, "scholia": self.scholia}[mode](y, limit)
        if self.has_app:
            self.apparatus(limit + self.lh * .75, n_app)
        return pg

    # ------------------------------------------------------------------ header
    def header(self, top):
        rng, pg, S = self.rng, self.pg, self.S
        yb = top + S
        if rng.random() < .1:
            return yb - S * .2  # no header on this page
        f = pg.st.get("r")
        title = pg.st.clean(self.corpus.head(rng) if rng.random() < .5 else rng.choice(self.corpus.prose(rng)[1][:5]))
        words = title.split()[:rng.randint(1, 5)] or ["ΠΕΡΙ"]
        t = " ".join(words)
        t = t.upper() if rng.random() < .4 else t
        t = unicodedata.normalize("NFC", t)
        num = str(rng.randint(1, 400))
        fn = pg.st.get("r")
        numw = fn.getlength(num)
        side = rng.choice(["L", "R"])
        num_x = self.x0 if side == "L" else self.x1 - numw
        reg = pg.region("NumberingZone", header=True)
        pg.put_line(reg, [(num, fn, num_x)], yb)
        mode = rng.choice(["center", "center", "inner"])
        tw = sum(f.getlength(w) + self.space for w in t.split())
        tx = (pg.W - tw) / 2 if mode == "center" else (self.x1 - tw if side == "L" else self.x0)
        tx = max(tx, self.x0 + numw + 3 * S) if (side == "L" and mode == "center" and tx < self.x0 + numw + 3 * S) else tx
        reg2 = pg.region("RunningTitleZone", header=True)
        x, placed = tx, []
        for w in t.split():
            placed.append((w, f, x))
            x += f.getlength(w) + self.space
        pg.put_line(reg2, placed, yb)
        return yb

    # ------------------------------------------------------------------ helpers
    def _text(self, s):
        return self.pg.st.clean(s)

    def para_lines(self, text, indent, y, limit, font=None, x0=None, width=None, justify=True, hang=0.0, words=None):
        """wrap text, return list of (placed, baseline) that fit before limit"""
        font = font or self.pg.st.get("r")
        words = words or words_of(self._text(text), font)
        rows = wrap(words, width or self.bw, self.space, indent, hang, justify)
        out = []
        for placed, last in rows:
            if y > limit:
                break
            out.append(([(w, f, x + (x0 if x0 is not None else self.x0)) for w, f, x in placed], y))
            y += self.lh
        return out, y

    def emit(self, rtype, rows, scale=1.0):
        pg = self.pg
        reg = pg.region(rtype)
        for placed, yb in rows:
            pg.put_line(reg, placed, yb, scale)
            self.page_words += [w for w, _, _ in placed]
        return reg

    def margin_note(self, yb):
        rng, pg, S = self.rng, self.pg, self.S
        txt = rng.choice(["D", "B", "K", "Σ", "%d K." % rng.randint(20, 400), "%d" % rng.randint(1, 99) + rng.choice(["a", "b", "c", "r", "v"]),
                          "ἄλλως", "cf. %d" % rng.randint(1, 200)])
        txt = self._text(txt)
        f = pg.st.get("i" if rng.random() < .3 else "r", .8)
        w = f.getlength(txt)
        left = rng.random() < .5
        if left and self.mL < w + S * 1.5:
            left = False
        if (not left) and self.mR < w + S * 1.5:
            left = True
        if left and self.mL < w + S * 1.5:
            return
        x = self.x0 - S * .8 - w if left else self.x1 + S * .8
        reg = pg.region("MarginTextZone")
        pg.put_line(reg, [(txt, f, x)], yb, .8)

    def numbering_side(self, yb, txt, left):
        pg, S = self.pg, self.S
        f = pg.st.get("r")
        w = f.getlength(txt)
        avail = self.mL if left else self.mR
        if avail < w + S * 1.2:
            return
        x = self.x0 - S * .8 - w if left else self.x1 + S * .8
        reg = pg.region("NumberingZone")
        pg.put_line(reg, [(txt, f, x)], yb)

    def heading(self, y, limit):
        rng, pg, S = self.rng, self.pg, self.S
        txt = self._text(self.corpus.head(rng))
        f = pg.st.get("b" if rng.random() < .6 else "r")
        words = words_of(txt, f)
        rows = wrap(words, self.bw * .7, self.space, justify=False)
        y += self.lh * .7
        if y + self.lh * (len(rows) + 1.2) > limit:
            return y - self.lh * .7
        reg = pg.region("MainZone-Head")
        for placed, _ in rows:
            wid = sum(f.getlength(w) for w, _, _ in placed) + self.space * (len(placed) - 1)
            x = (pg.W - wid) / 2
            xs, xx = [], x
            for w, ff, _ in placed:
                xs.append((w, ff, xx))
                xx += ff.getlength(w) + self.space
            pg.put_line(reg, xs, y)
            y += self.lh
        return y + self.lh * .7

    def table(self, y, limit):
        rng, pg, S = self.rng, self.pg, self.S
        nc, nr = rng.randint(3, 5), rng.randint(3, 6)
        h = nr * self.lh * 1.15
        if y + self.lh * .5 + h > limit:
            return y
        y0 = y + self.lh * .4
        cw = self.bw / nc
        f = pg.st.get("r")
        reg = pg.region("TableZone")
        pg.bands += 1  # table cells share a tag: read column by column (see reading_order)
        for r in range(nr):
            yb = y0 + (r + .72) * self.lh * 1.15
            for c in range(nc):
                t = str(rng.randint(1, 999)) if rng.random() < .4 else rng.choice(self.page_words or ["ἀνήρ"]) if self.page_words else "α"
                t = self._text(t)
                x = self.x0 + c * cw + S * .5
                pg.tag = (pg.bands, c)
                pg.put_line(reg, [(t, f, x)], yb)
        pg.tag = None
        for r in range(nr + 1):
            yy = y0 + r * self.lh * 1.15
            pg.ops.append(("l", self.x0, yy, self.x1, yy, 2))
        for c in range(nc + 1):
            xx = self.x0 + c * cw
            pg.ops.append(("l", xx, y0, xx, y0 + h, 2))
        reg["extra"] = [[self.x0, y0], [self.x1, y0], [self.x1, y0 + h], [self.x0, y0 + h]]
        return y0 + h + self.lh * .5

    # ------------------------------------------------------------------ modes
    def prose(self, y, limit):
        rng, pg, S = self.rng, self.pg, self.S
        _, paras = self.corpus.prose(rng)
        y += self.lh * 1.9 if pg.lines else self.lh * .3
        cont = rng.random() < .3
        gap = rng.choice([0, 0, .35]) * self.lh
        indent = S * rng.uniform(1.2, 2.2) if gap == 0 else 0
        numbered = rng.random() < .3
        ref_left = rng.random() < .3
        count, first = 0, True
        did_head = did_table = False
        band_at = rng.randint(0, 1 if self.parallel_only else 3) if self.parallel and rng.random() < self.parallel else None
        for pi, p in enumerate(paras):
            if y > limit - self.lh:
                break
            if band_at is not None and pi == band_at:
                y, ok = self.parallel_band(y, limit, paras[pi:])
                band_at = None
                if ok:
                    first = False
                    continue
            if not first and not did_head and rng.random() < .2:
                did_head = True
                y = self.heading(y - gap, limit)
            if not first and not did_table and rng.random() < .15:
                did_table = True
                y = self.table(y, limit)
            quote = (not first) and rng.random() < .1
            if quote:
                rows, ny = self.para_lines(p, 0, y, limit, x0=self.x0 + S * 2.5, width=self.bw - S * 5)
                rt = "MainZone-Quote"
            else:
                rows, ny = self.para_lines(p, 0 if (first and cont) else indent, y, limit)
                rt = "MainZone-Continued" if (first and cont) else "MainZone-P"
            if not rows:
                break
            if numbered:
                for placed, yb in rows:
                    count += 1
                    if count % 5 == 0:
                        self.numbering_side(yb, str(count), ref_left)
            elif rng.random() < .15:
                self.numbering_side(rows[0][1], "%d%s" % (rng.randint(1, 600), rng.choice(["", "a", "b", "c"])), True)
            if self.margin_notes and rng.random() < .5:
                self.margin_note(rows[0][1])
            self.emit(rt, rows)
            y = ny + gap + (self.lh * .15 if quote else 0)
            first = False

    def parallel_band(self, y, limit, paras):
        """A stretch of the page set in two columns (text / parallel version), with a blank gutter.
        Afterwards the page returns to a single column, unless the band runs to the bottom."""
        rng, pg, S = self.rng, self.pg, self.S
        avail = limit - y
        if avail < self.lh * 6:
            return y, False
        to_end = rng.random() < .3
        h = avail if to_end else min(avail - self.lh * 2, self.lh * rng.randint(6, 18))
        if h < self.lh * 4:
            return y, False
        y += self.lh * rng.uniform(.5, 1.2)  # blank space above the band
        bottom = y + h
        gutter = S * rng.uniform(1.5, 4)
        cw = (self.bw - gutter) / 2
        srcs = [paras, self.corpus.prose(rng)[1]]
        pg.bands += 1
        ends = []
        # one column may stop early, leaving blank space under it (never both)
        short = rng.choice([0, 1]) if rng.random() < .55 else None
        for c in (0, 1):
            pg.tag = (pg.bands, c)
            cbottom = y + h * rng.uniform(.3, .85) if c == short else bottom
            x0 = self.x0 + c * (cw + gutter)
            yy = y + (self.lh * rng.randint(1, 2) if c and rng.random() < .2 else 0)  # right column may start lower
            for p in srcs[c]:
                if yy > cbottom - self.lh:
                    break
                rows, ny = self.para_lines(p, S * 1.2, yy, cbottom - self.lh * .5, x0=x0, width=cw)
                if not rows:
                    break
                self.emit("MainZone-P", rows)
                yy = ny
            ends.append(yy)
        pg.tag = None
        if rng.random() < .4:  # vertical separator rule centred in the gutter
            xr = self.x0 + cw + gutter / 2
            pg.ops.append(("l", xr, y - self.lh * .2, xr, max(ends) - self.lh * .2, 1))
        return max(ends) + self.lh * rng.uniform(.4, 1.4), True  # blank space below

    def verse(self, y, limit):
        rng, pg, S = self.rng, self.pg, self.S
        _, run = self.corpus.verse(rng)
        f = pg.st.get("r")
        run = [(n, self._text(t)) for n, t in run]
        mx = max(f.getlength(t) for _, t in run[:30])
        avail = self.bw - S * 3
        if mx > avail:  # shrink the face until the longest verse fits
            sc = avail / mx
            pg.st.size = max(14, int(S * sc))
            f = pg.st.get("r")
            S = self.S = pg.st.size
            self.lh = S * rng.uniform(1.4, 1.7)
        y += self.lh * 1.9
        elegiac = rng.random() < .25
        left_nums = rng.random() < .3
        every = rng.choice([5, 5, 10])
        stanza = rng.randint(5, 25)
        i, reg, k = 0, None, 0
        counter = rng.randint(1, 900) // every * every
        if rng.random() < .15:
            y = self.fragm_head(y)
        for n, t in run:
            if y > limit:
                break
            if reg is None or k >= stanza:
                if reg is not None:
                    y += self.lh * .6
                    if y > limit:
                        break
                reg = pg.region("MainZone-Lg")
                k, stanza = 0, rng.randint(5, 25)
            counter += 1
            ind = S * 2 if (elegiac and i % 2) else 0
            x = self.x0 + S * 1.5 + ind
            placed = [(w, f, x + sum(f.getlength(v) + self.space for v in t.split()[:j])) for j, w in enumerate(t.split())]
            pg.put_line(reg, placed, y)
            self.page_words += t.split()
            nn = n if n.isdigit() else str(counter)
            if int(nn) % every == 0:
                self.numbering_side(y, nn, left_nums)
            i += 1
            k += 1
            y += self.lh

    def fragm_head(self, y):
        pg = self.pg
        t = self.rng.choice(["fragm. %d" % self.rng.randint(1, 30), "fragmenta", "Φ", "P.Oxy. %d" % self.rng.randint(100, 4000)])
        f = pg.st.get("r")
        w = f.getlength(t)
        reg = pg.region("MainZone-Head")
        pg.put_line(reg, [(t, f, (pg.W - w) / 2)], y)
        return y + self.lh * 1.4

    def scholia(self, y, limit):
        rng, pg, S = self.rng, self.pg, self.S
        _, paras = self.corpus.prose(rng)
        fr, fb = pg.st.get("r"), pg.st.get("b")
        y += self.lh * 1.9
        num = rng.randint(1, 300)
        sub = False
        for p in paras:
            if y > limit - self.lh * 3:
                break
            sub = rng.random() < .25
            if sub:
                label = rng.choice("bcdefg") + "."
            else:
                num += rng.randint(1, 6)
                label = str(num) + (rng.choice(["", "", "-%d" % (num % 7 + 2) + rng.choice(["", "c"])]))
            label = self._text(label)
            words = [(label, fb)] + words_of(self._text(p[:rng.randint(120, 900)]), fr)
            rows, ny = self.para_lines(p, 0, y, limit, words=words)
            if not rows:
                break
            self.emit("MainZone-P", rows)
            y = ny
            if rng.random() < .85:
                n_l = rng.randint(1, 3)
                y = self.small_block(y + self.lh * .05, limit, n_l, rule=False) + self.lh * .85
            else:
                y += self.lh * .35

    def small_block(self, y, limit, n_lines, rule=False, hang=False, indent=None):
        rng, pg, S = self.rng, self.pg, self.S
        f = pg.st.get("r", self.asz)
        fi = pg.st.get("i", self.asz)
        fb = pg.st.get("b", self.asz)
        words_src = self.page_words[:] or ["λόγος", "ἀνήρ", "ἔστι"]
        txt = self._text(apparatus.make(words_src, rng, int(n_lines * 85 * (S * self.asz) ** -.0 * 1.6)))
        words = []
        for w in txt.split():
            if w in apparatus.ABBR_I or w.rstrip(":") in apparatus.ABBR_I:
                words.append((w, fi))
            elif re.fullmatch(r"\d+(\.\d+)?", w) and rng.random() < .3:
                words.append((w, fb))
            else:
                words.append((w, f))
        sp = self.space * self.asz
        rows = wrap(words, self.bw, sp, rng.choice([0, 0, S * 1.2]) if indent is None else indent, 0.0, True)
        reg = pg.region("ApparatusZone")
        step = self.apl
        yy = y + step
        for k, (placed, last) in enumerate(rows[:n_lines]):
            if yy > pg.H * .97:
                break
            pg.put_line(reg, [(w, ff, x + self.x0) for w, ff, x in placed], yy, self.asz)
            yy += step
        if not reg["lines"]:
            pg.regions.remove(reg)
        return yy - step * .3

    def apparatus(self, y, n):
        rng, pg = self.rng, self.pg
        if rng.random() < .5:
            pg.ops.append(("l", self.x0, y - self.lh * .3, self.x0 + self.bw * rng.uniform(.12, .25), y - self.lh * .3, 1))
        # one zone per run-in block; sometimes split into two blocks
        if n >= 6 and rng.random() < .4:
            k = rng.randint(2, n - 2)
            y2 = self.small_block(y, 10 ** 9, k, indent=0)
            self.small_block(y2 + self.apl * .2, 10 ** 9, n - k, indent=0)
        else:
            self.small_block(y, 10 ** 9, n)


def reading_order(page_lines, size):
    tol = TOL * size / 30
    hdr = sorted([l for l in page_lines if l["header"]], key=lambda l: (round(l["y"] / tol), l["x0"]))
    rest = sorted([l for l in page_lines if not l["header"] and not l.get("tag")], key=lambda l: l["y"])
    rows, cur = [], []
    for l in rest:
        if cur and l["y"] - cur[0]["y"] > tol:
            rows.append(cur)
            cur = []
        cur.append(l)
    if cur:
        rows.append(cur)
    items = [(r[0]["y"], sorted(r, key=lambda l: l["x0"])) for r in rows]
    bands = {}
    for l in page_lines:
        if not l["header"] and l.get("tag"):
            bands.setdefault(l["tag"][0], []).append(l)
    for b in bands.values():  # parallel-text bands and tables are read column by column, left then right
        b.sort(key=lambda l: (l["tag"][1], l["y"]))
        items.append((min(l["y"] for l in b), b))
    out = hdr[:]
    for _, grp in sorted(items, key=lambda t: t[0]):
        out += grp
    return out
