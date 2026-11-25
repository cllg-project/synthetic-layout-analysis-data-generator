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
