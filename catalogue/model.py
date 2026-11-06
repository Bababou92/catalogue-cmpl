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
