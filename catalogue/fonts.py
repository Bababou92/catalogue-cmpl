"""Résolution des polices.

On cherche d'abord les vraies polices Microsoft (Arial, Times New Roman,
Book Antiqua) installées sur la machine, sinon on retombe sur les polices
libres fournies dans cmpl/assets/fonts (Liberation = mêmes largeurs qu'Arial /
Times, TeX Gyre Pagella = proche de Book Antiqua).
"""
import os
import struct
import sys
from functools import lru_cache

from PIL import ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED = os.path.join(HERE, "assets", "fonts")

# famille -> style -> noms de fichiers possibles (par ordre de préférence)
CANDIDATES = {
    "arial": {
        "r": ["arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf"],
        "b": ["arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf"],
        "i": ["ariali.ttf", "Arial Italic.ttf", "LiberationSans-Italic.ttf"],
        "bi": ["arialbi.ttf", "Arial Bold Italic.ttf", "LiberationSans-BoldItalic.ttf"],
    },
    "times": {
        "r": ["times.ttf", "Times New Roman.ttf", "LiberationSerif-Regular.ttf"],
        "b": ["timesbd.ttf", "Times New Roman Bold.ttf", "LiberationSerif-Bold.ttf"],
        "i": ["timesi.ttf", "Times New Roman Italic.ttf", "LiberationSerif-Italic.ttf"],
        "bi": ["timesbi.ttf", "Times New Roman Bold Italic.ttf", "LiberationSerif-BoldItalic.ttf"],
    },
    "bkant": {
        "r": ["BKANT.TTF", "bkant.ttf", "texgyrepagella-regular.otf"],
        "b": ["ANTQUAB.TTF", "antquab.ttf", "texgyrepagella-bold.otf"],
        "i": ["ANTQUAI.TTF", "antquai.ttf", "texgyrepagella-italic.otf"],
        "bi": ["ANTQUABI.TTF", "antquabi.ttf", "texgyrepagella-bolditalic.otf"],
    },
    "mono": {
        "r": ["cour.ttf", "Courier New.ttf", "LiberationMono-Regular.ttf"],
        "b": ["cour.ttf", "LiberationMono-Regular.ttf"],
        "i": ["cour.ttf", "LiberationMono-Regular.ttf"],
        "bi": ["cour.ttf", "LiberationMono-Regular.ttf"],
    },
}

# nom de police écrit dans le PPTX
PPTX_NAMES = {"arial": "Arial", "times": "Times New Roman", "bkant": "Book Antiqua", "mono": "Courier New"}


def _system_dirs():
    dirs = []
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(os.path.join(windir, "Fonts"))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    elif sys.platform == "darwin":
        dirs += ["/Library/Fonts", "/System/Library/Fonts/Supplemental", os.path.expanduser("~/Library/Fonts")]
    else:
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts")]
    return dirs


@lru_cache(maxsize=None)
def _find_in_dirs(filename):
    for d in _system_dirs():
        direct = os.path.join(d, filename)
        if os.path.isfile(direct):
            return direct
        if not sys.platform.startswith("win"):
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.lower() == filename.lower():
                        return os.path.join(root, f)
    return None


@lru_cache(maxsize=None)
def font_path(family, style):
    for name in CANDIDATES[family][style]:
        bundled = os.path.join(BUNDLED, name)
        # les polices Microsoft passent avant les polices libres embarquées
        if os.path.isfile(bundled):
            return bundled
        found = _find_in_dirs(name)
        if found:
            return found
    raise FileNotFoundError(f"Police introuvable : {family} {style}")


def resolve(family, bold, italic):
    style = ("b" if bold else "") + ("i" if italic else "") or "r"
    return font_path(family, style)


@lru_cache(maxsize=None)
def pil_font(path, px):
    return ImageFont.truetype(path, px)


def _hhea(path):
    with open(path, "rb") as fh:
        full = fh.read()
    if full[:4] == b"ttcf":
        raise ValueError("ttc")
    num = struct.unpack(">H", full[4:6])[0]
    tables = {}
    for i in range(num):
        tag, _chk, off, _ln = struct.unpack(">4sIII", full[12 + 16 * i: 28 + 16 * i])
        tables[tag.decode("latin1")] = off
    upm = struct.unpack(">H", full[tables["head"] + 18: tables["head"] + 20])[0]
    asc, desc, gap = struct.unpack(">hhh", full[tables["hhea"] + 4: tables["hhea"] + 10])
    return upm, asc, desc, gap


@lru_cache(maxsize=None)
def line_factor(path):
    """Hauteur de ligne PowerPoint = (ascent + descent + lineGap) / unitsPerEm."""
    try:
        upm, asc, desc, gap = _hhea(path)
        return max(1.15, (asc - desc + gap) / upm)
    except Exception:
        return 1.15


@lru_cache(maxsize=None)
def ascent_factor(path):
    try:
        upm, asc, desc, gap = _hhea(path)
        return (asc + gap) / upm
    except Exception:
        return 0.95
