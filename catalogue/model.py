"""Éléments de mise en page (rectangles, images, zones de texte) en millimètres."""
from dataclasses import dataclass, field
from typing import List, Optional

from PIL import Image

from .textfit import Para

WHITE = "#FFFFFF"
BLACK = "#000000"


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    fill: Optional[str] = None
    line: Optional[str] = None
    line_pt: float = 0.0
    name: str = "Rectangle"
    bleed: str = ""             # côtés à prolonger dans les fonds perdus (l, r, t, b)


@dataclass
class Pic:
    x: float
    y: float
    w: float
    h: float
    image: Image.Image = None
    name: str = "Image"
    fmt: str = "PNG"            # format d'incorporation dans le PPTX
    bleed: str = ""             # côtés à prolonger dans les fonds perdus (l, r, t, b)


@dataclass
class TextBox:
    x: float
    y: float
    w: float
    h: float
    paras: List[Para] = field(default_factory=list)
    anchor: str = "t"           # t, m, b
    rot: int = 0                # 0 ou 270 (texte vertical, lecture de bas en haut)
    inset: float = 0.0          # mm, identique sur les 4 côtés
    name: str = "Texte"


@dataclass
class Page:
    name: str
    w: float
    h: float
    bg: str = WHITE
    elements: list = field(default_factory=list)
    crop: Optional[tuple] = None   # (x0, y0, x1, y1) mm : zone exportée en PNG (dos)


_rot_cache = {}


def _rot_image(im):
    """Image tournée de 90° (anti-horaire), mise en cache pour que les rendus PDF/PPTX la réutilisent."""
    key = id(im)
    hit = _rot_cache.get(key)
    if hit is None:
        hit = (im, im.rotate(90, expand=True))          # on garde im pour que l'id reste valable
        _rot_cache[key] = hit
    return hit[1]


def rotate_page_ccw(page):
    """Page paysage -> page portrait dont le contenu est tourné de 90° (sens anti-horaire).

    Le tableau se lit en penchant la tête à gauche, comme sur le catalogue papier. Un point (x, y) devient (y, W - x).
    Les zones cliquables (page.hot) suivent."""
    W = page.w
    out = Page(page.name, page.h, page.w, bg=page.bg)
    out.crop = None

    def box(x, y, w, h):
        return y, W - x - w, h, w

    for el in page.elements:
        if isinstance(el, Rect):
            x, y, w, h = box(el.x, el.y, el.w, el.h)
            bl = "".join({"l": "b", "r": "t", "t": "l", "b": "r"}.get(c, "") for c in el.bleed)   # côté d'origine -> côté après rotation
            out.elements.append(Rect(x, y, w, h, fill=el.fill, line=el.line, line_pt=el.line_pt, name=el.name, bleed=bl))
        elif isinstance(el, Pic):
            x, y, w, h = box(el.x, el.y, el.w, el.h)
            out.elements.append(Pic(x, y, w, h, image=_rot_image(el.image), name=el.name, fmt=el.fmt))
        elif isinstance(el, TextBox):
            x, y, w, h = box(el.x, el.y, el.w, el.h)
            out.elements.append(TextBox(x, y, w, h, el.paras, anchor=el.anchor, rot=270, inset=el.inset, name=el.name))
    out.hot = []
    for hz in getattr(page, "hot", []):
        x, y, w, h = box(hz["x"], hz["y"], hz["w"], hz["h"])
        out.hot.append(dict(hz, x=x, y=y, w=w, h=h))
    return out
