"""TEI corpus loader: prose paragraphs, verse runs, headings of the Greek texts in ../cllg-nova/data (cached to JSON)."""
import json
import random
import re
import unicodedata
from pathlib import Path

from lxml import etree

DEFAULT_SRC = Path(__file__).resolve().parents[2] / "cllg-nova" / "data"
CACHE = Path(__file__).resolve().parents[1] / "cache" / "corpus.json"
GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")


def _clean(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip()


def _greek_ratio(s):
    letters = [c for c in s if c.isalpha()]
    return sum(1 for c in letters if GREEK.match(c)) / len(letters) if letters else 0.0


def _load_file(path):
    root = etree.parse(str(path)).getroot()
    body = root.find(".//{*}body")
    if body is None:
        return None
    etree.strip_elements(body, "{*}note", "{*}app", "{*}bibl", with_tail=False)
    prose, heads, verse = [], [], []
    for el in body.iter("{*}p", "{*}ab", "{*}head", "{*}l"):
        tag = etree.QName(el).localname
        txt = _clean("".join(el.itertext()))
        if not txt or _greek_ratio(txt) < 0.85:
            continue
        if tag == "l":
            continue
        if tag == "head":
            if len(txt) < 80:
                heads.append(txt)
        elif len(txt) >= 60:
            prose.append(txt)
    for parent in body.iter():
        ls = [c for c in parent if etree.QName(c).localname == "l"] if isinstance(parent.tag, str) else []
        run = []
        for c in ls:
            txt = _clean("".join(c.itertext()))
            if txt and _greek_ratio(txt) >= 0.85:
                run.append([c.get("n") or "", txt])
        if len(run) >= 8:
            verse.append(run)
    return dict(prose=prose, heads=heads, verse=verse)


def build(src=DEFAULT_SRC):
    out = {}
    for f in sorted(Path(src).glob("*/*.xml")):
        if f.name == "metadata.xml":
            continue
        try:
            d = _load_file(f)
        except Exception as e:  # noqa
            print("skip", f, e)
            continue
        if d and (d["prose"] or d["verse"]):
            out[f.stem] = d
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(out, ensure_ascii=False))
    return out


class Corpus:
    def __init__(self, src=DEFAULT_SRC):
        self.data = json.loads(CACHE.read_text()) if CACHE.exists() else build(src)
        self.prose_books = [k for k, v in self.data.items() if len(v["prose"]) >= 5]
        self.verse_books = [k for k, v in self.data.items() if v["verse"]]
        self.all_heads = [h for v in self.data.values() for h in v["heads"]]

    def prose(self, rng):
        """a (book, list of consecutive paragraphs) sample"""
        b = rng.choice(self.prose_books)
        ps = self.data[b]["prose"]
        i = rng.randrange(len(ps))
        return b, ps[i:] + ps[:i]

    def verse(self, rng):
        b = rng.choice(self.verse_books)
        run = rng.choice(self.data[b]["verse"])
        i = rng.randrange(max(1, len(run) - 12))
        return b, run[i:]

    def head(self, rng):
        return rng.choice(self.all_heads) if self.all_heads else "ΠΕΡΙ ΤΩΝ ΑΡΧΩΝ"


if __name__ == "__main__":
    c = Corpus()
    for k, v in c.data.items():
        print(k, len(v["prose"]), len(v["heads"]), len(v["verse"]))
