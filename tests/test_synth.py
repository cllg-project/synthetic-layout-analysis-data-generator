import numpy as np
from synth.generate import make_page


def test_deterministic():
    a, ma = make_page(7)
    b, mb = make_page(7)
    assert np.array_equal(a, b) and ma == mb


def test_invariants():
    for seed in range(25):
        img, m = make_page(seed)
        ids = [l["id"] for l in m["lines"]]
        assert sorted(ids) == sorted(m["order"]) and len(set(ids)) == len(ids)
        boxes = {r["id"]: r["box"] for r in m["regions"]}
        for l in m["lines"]:
            x0, y0, x1, y1 = boxes[l["region"]]
            assert all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in l["poly"])
            assert l["bl"][0][0] <= l["bl"][-1][0] and l["text"]
        assert img.shape[:2] == (m["h"], m["w"])


def _tagged(page):
    from synth.layout import reading_order
    return reading_order(page.lines, page.st.size)


def test_default_unchanged_by_parallel_option():
    a, ma = make_page(11)
    b, mb = make_page(11, parallel=0.0)
    assert np.array_equal(a, b) and ma == mb


def test_parallel_only_always_has_two_columns():
    import random
    from synth.corpus import Corpus
    from synth.layout import Builder
    c = Corpus()
    for seed in range(15):
        img, m = make_page(seed, parallel_only=True)
        assert len(m["order"]) == len(m["lines"]) == len(set(m["order"]))
        pg = Builder(random.Random(seed), c, parallel_only=True).build()
        if not pg.bands:
            continue  # make_page retries when a layout has no room
        band = {}
        for l in pg.lines:
            if l["tag"]:
                band.setdefault(l["tag"][0], {0: [], 1: []})[l["tag"][1]].append(l)
        for cols in band.values():
            if not (cols[0] and cols[1]):
                continue
            # gutter: left column strictly left of the right column
            assert max(l["x1"] for l in cols[0]) < min(l["x0"] for l in cols[1])
            # reading order: whole left column before the right one, each top to bottom
            ids = [l["id"] for l in _tagged(pg)]
            seq = [ids.index(l["id"]) for l in sorted(cols[0], key=lambda l: l["y"]) + sorted(cols[1], key=lambda l: l["y"])]
            assert seq == sorted(seq) and seq == list(range(seq[0], seq[0] + len(seq)))


def test_table_read_column_first():
    from synth.layout import reading_order
    cells = [dict(id="c%d%d" % (r, c), header=False, y=100 + 40 * r, x0=100 + 200 * c, tag=(1, c)) for r in range(3) for c in range(3)]
    order = [l["id"] for l in reading_order(cells, 30)]
    assert order == ["c00", "c10", "c20", "c01", "c11", "c21", "c02", "c12", "c22"]


def test_untagged_rows_still_left_to_right():
    from synth.layout import reading_order
    ls = [dict(id="b", header=False, y=100, x0=300, tag=None), dict(id="a", header=False, y=101, x0=50, tag=None),
          dict(id="c", header=False, y=200, x0=10, tag=None)]
    assert [l["id"] for l in reading_order(ls, 30)] == ["a", "b", "c"]
