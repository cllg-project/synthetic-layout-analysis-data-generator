"""Fake critical apparatus built from the page's own words."""
import random
import unicodedata

SIGLA = ["L", "Lp", "Wa", "GR", "M", "F", "A", "B", "D", "K", "V", "Vat", "Par", "Ald", "Σ", "Q", "x", "p(NO)", "p(NFWa)", "q(ΗΔ)", "Pc", "ac"]
ABBR_I = {"om.", "del.", "cj.", "add.", "coni.", "corr.", "scr.", "suppl.", "tr."}
SWAP = str.maketrans({"ε": "η", "η": "ε", "ο": "ω", "ω": "ο", "α": "ε", "ι": "η", "υ": "ι", "τ": "δ", "δ": "τ", "κ": "χ", "π": "φ"})


def _strip(w):
    return "".join(c for c in w if c.isalpha() or unicodedata.combining(c))


def perturb(w, rng):
    base = unicodedata.normalize("NFD", w)
    k = rng.random()
    if k < .45 and len(base) > 3:
        i = rng.randrange(len(base))
        return unicodedata.normalize("NFC", base[:i].translate(SWAP) + base[i:i + 1].translate(SWAP) + base[i + 1:])
    if k < .7:
        return unicodedata.normalize("NFC", "".join(c for c in base if not unicodedata.combining(c)))
    return w + rng.choice(["ν", "ς", "σι", "ται"]) if k < .85 else w[:-1] if len(w) > 3 else w


def make(words, rng, n_chars, sigla=None):
    """words: Greek tokens of the page; returns a run-in apparatus string of about n_chars characters."""
    words = [_strip(w) for w in words if len(_strip(w)) > 2] or ["λόγος", "ἀνήρ", "τοῦτο"]
    sigla = sigla or rng.sample(SIGLA, rng.randint(4, 9))
    out, line = [], rng.randint(1, 400)
    while sum(len(x) + 1 for x in out) < n_chars:
        line += rng.randint(0, 30)
        lemma = rng.choice(words)
        e = ["%d.%d" % (line, rng.randint(1, 6)) if rng.random() < .8 else "%d" % line, lemma]
        e += rng.sample(sigla, rng.randint(1, 3))
        for _ in range(rng.choice([0, 1, 1, 2])):
            r = rng.random()
            if r < .15:
                e += [rng.choice(sorted(ABBR_I))]
            else:
                e += [perturb(rng.choice(words), rng)]
            e += rng.sample(sigla, rng.randint(1, 2))
        out.append(" ".join(e))
        out.append("ǁ")
    return " ".join(out).rstrip(" ǁ")
