"""Font pool: (regular, bold, italic) families with Greek coverage; text sanitising against the font cmap."""
import functools
import random

from fontTools.ttLib import TTFont
from PIL import ImageFont

G = "/usr/share/fonts/"
FAMILIES = {
    "gentium": (G + "truetype/gentiumplus/GentiumBookPlus-Regular.ttf", G + "truetype/gentiumplus/GentiumBookPlus-Bold.ttf",
                G + "truetype/gentiumplus/GentiumBookPlus-Italic.ttf"),
    "freeserif": (G + "truetype/freefont/FreeSerif.ttf", G + "truetype/freefont/FreeSerifBold.ttf", G + "truetype/freefont/FreeSerifItalic.ttf"),
    "didot": (G + "opentype/didot/GFSDidot.otf", G + "opentype/didot/GFSDidotBold.otf", G + "opentype/didot/GFSDidotItalic.otf"),
    "artemisia": (G + "opentype/artemisia/GFSArtemisia.otf", G + "opentype/artemisia/GFSArtemisiaBold.otf", G + "opentype/artemisia/GFSArtemisiaIt.otf"),
}
REPLACE = {"ϲ": "σ", "Ϲ": "Σ", "ϛ": "ς", "ʹ": "'", "̄": "", "̅": "", "ǁ": "|", "‖": "|", " ": " ", "’": "'", "’": "'"}


@functools.lru_cache(None)
def cmap(path):
    return set(TTFont(path, fontNumber=0, lazy=True).getBestCmap())


@functools.lru_cache(maxsize=512)
def _font(path, size):
    return ImageFont.truetype(path, size)


class Style:
    """a family at a given main size; get(role, scale) -> PIL font; roles r/b/i"""

    def __init__(self, family, size):
        self.family, self.size = family, size
        self.paths = dict(zip("rbi", FAMILIES[family]))

    def get(self, role="r", scale=1.0):
        return _font(self.paths[role], max(6, int(round(self.size * scale))))

    def clean(self, text):
        cm = cmap(self.paths["r"])
        out = []
        for ch in text:
            ch = REPLACE.get(ch, ch)
            if not ch:
                continue
            if ord(ch) in cm or ch == " ":
                out.append(ch)
            elif ch in "|" and ord("|") in cm:
                out.append(ch)
        return "".join(out)


def pick_family(rng):
    return rng.choice(list(FAMILIES))
