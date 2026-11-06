"""Mise en page du texte (césures, alignement, ajustement automatique).

Tout est calculé en points typographiques (1 pt = 1/72 pouce) pour que le PNG
et le PPTX utilisent exactement les mêmes retours à la ligne.
"""
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import List, Optional

from PIL import ImageFont

from . import fonts

MM_PER_PT = 25.4 / 72.0
SMALLCAPS_SCALE = 0.8
MEASURE_PX = 240  # taille de mesure (px) : la largeur est ensuite remise à l'échelle


@dataclass(frozen=True)
class Run:
    text: str
    family: str = "arial"
    size: float = 12.0
    bold: bool = False
    italic: bool = False
    color: str = "#000000"
    smallcaps: bool = False
    caps: bool = False


@dataclass
class Para:
    runs: List[Run]
    align: str = "l"            # l, c, r, j
    left_mm: float = 0.0        # retrait gauche
    first_mm: float = 0.0       # retrait de première ligne (relatif à left_mm)
    bullet: Optional[str] = None
    space_before_pt: float = 0.0


# ---------------------------------------------------------------- mesure

@lru_cache(maxsize=None)
def _mfont(path):
    return ImageFont.truetype(path, MEASURE_PX)


def _kern_off():
    try:
        from PIL import features
        return features.check("raqm")
    except Exception:
        return False


_RAQM = _kern_off()


def text_width_pt(text, family, size, bold, italic, smallcaps=False, caps=False):
    """Largeur d'un texte en pt (sans crénage, comme PowerPoint par défaut)."""
    if not text:
        return 0.0
    path = fonts.resolve(family, bold, italic)
    f = _mfont(path)
    if caps:
        text = text.upper()
    if smallcaps:
        total = 0.0
        for seg, small in split_smallcaps(text):
            total += _raw(f, seg.upper() if small else seg) * (size * (SMALLCAPS_SCALE if small else 1.0)) / MEASURE_PX
        return total
    return _raw(f, text) * size / MEASURE_PX


def _raw(f, text):
    if _RAQM:
        try:
            return f.getlength(text, features=["-kern"])
        except Exception:
            pass
    return f.getlength(text)


def split_smallcaps(text):
    """Découpe en segments (texte, est_en_petites_capitales)."""
    out = []
    for ch in text:
        small = ch.islower()
        if out and out[-1][1] == small:
            out[-1] = (out[-1][0] + ch, small)
        else:
            out.append((ch, small))
    return out


def line_height_pt(run: Run):
    return fonts.line_factor(fonts.resolve(run.family, run.bold, run.italic)) * run.size


def ascent_pt(run: Run):
    return fonts.ascent_factor(fonts.resolve(run.family, run.bold, run.italic)) * run.size


def run_width(run: Run, text=None):
    return text_width_pt(run.text if text is None else text, run.family, run.size, run.bold, run.italic,
                         run.smallcaps, run.caps)


# ---------------------------------------------------------------- césures

@dataclass
class Piece:
    text: str
    run: Run
    width: float
    is_space: bool = False


@dataclass
class Line:
    pieces: List[Piece]
    x_pt: float = 0.0           # décalage horizontal de départ (alignement + retrait)
    y_pt: float = 0.0           # haut de la ligne
    height_pt: float = 0.0
    ascent_pt: float = 0.0
    bullet: Optional[Piece] = None
    bullet_x_pt: float = 0.0
    extra_space_pt: float = 0.0  # espace ajouté à chaque blanc (justification)
    last: bool = False


def _tokens(para: Para):
    toks = []
    for run in para.runs:
        buf = ""
        for ch in run.text:
            if ch == " " or ch == " ":
                if buf:
                    toks.append(Piece(buf, run, run_width(run, buf)))
                    buf = ""
                if ch == " ":
                    toks.append(Piece(" ", run, run_width(run, " "), True))
                else:
                    buf += ch
            else:
                buf += ch
        if buf:
            toks.append(Piece(buf, run, run_width(run, buf)))
    return toks


def _split_long(piece: Piece, max_w):
    """Coupe un mot plus large que la ligne (rare)."""
    out, cur = [], ""
    for ch in piece.text:
        if cur and run_width(piece.run, cur + ch) > max_w:
            out.append(Piece(cur, piece.run, run_width(piece.run, cur)))
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(Piece(cur, piece.run, run_width(piece.run, cur)))
    return out


def _wrap(para: Para, width_pt):
    toks = _tokens(para)
    left = para.left_mm / MM_PER_PT
    first = 0.0 if para.bullet else para.first_mm / MM_PER_PT
    lines, cur, cur_w = [], [], 0.0
    first_line = True

    def avail():
        return width_pt - left - (first if first_line else 0.0)

    i = 0
    while i < len(toks):
        t = toks[i]
        if t.is_space:
            if cur:
                cur.append(t)
                cur_w += t.width
            i += 1
            continue
        if t.width > avail() and not cur:
            parts = _split_long(t, max(avail(), 1))
            toks[i:i + 1] = parts
            continue
        if cur_w + t.width <= avail() + 1e-6:
            cur.append(t)
            cur_w += t.width
            i += 1
        else:
            while cur and cur[-1].is_space:
                cur_w -= cur[-1].width
                cur.pop()
            lines.append(cur)
            first_line = False
            cur, cur_w = [], 0.0
    if cur or not lines:
        while cur and cur[-1].is_space:
            cur.pop()
        lines.append(cur)
    return lines


def _line_w(pieces):
    return sum(p.width for p in pieces)


def count_lines(para: Para, width_pt):
    return len(_wrap(para, width_pt))


def layout(paras: List[Para], width_pt, default_run: Optional[Run] = None):
    """Retourne (lignes, hauteur totale en pt). Les lignes ont x/y relatifs au coin haut-gauche."""
    out: List[Line] = []
    y = 0.0
    for pi, para in enumerate(paras):
        left = para.left_mm / MM_PER_PT
        first_raw = para.first_mm / MM_PER_PT
        first = 0.0 if para.bullet else first_raw     # avec puce, le texte démarre au retrait gauche
        if para.runs:
            ref = max((r for r in para.runs), key=lambda r: r.size)
        else:
            ref = default_run or Run("", size=10)
        wrapped = _wrap(para, width_pt)
        if pi > 0 or para.space_before_pt:
            y += para.space_before_pt
        for li, pieces in enumerate(wrapped):
            if pieces:
                lh = max(line_height_pt(p.run) for p in pieces)
                asc = max(ascent_pt(p.run) for p in pieces)
            else:
                lh, asc = line_height_pt(ref), ascent_pt(ref)
            indent = left + (first if li == 0 else 0.0)
            avail = width_pt - indent
            w = _line_w(pieces)
            last = li == len(wrapped) - 1
            x = indent
            extra = 0.0
            if para.align == "c":
                x = indent + (avail - w) / 2
            elif para.align == "r":
                x = indent + (avail - w)
            elif para.align == "j" and not last:
                spaces = sum(1 for p in pieces if p.is_space)
                if spaces:
                    extra = (avail - w) / spaces
            line = Line(pieces, x_pt=x, y_pt=y, height_pt=lh, ascent_pt=asc, extra_space_pt=extra, last=last)
            if para.bullet and li == 0:
                brun = para.runs[0] if para.runs else ref
                line.bullet = Piece(para.bullet, brun, run_width(brun, para.bullet))
                line.bullet_x_pt = left + first_raw
            out.append(line)
            y += lh
    return out, y


def total_height(paras, width_pt):
    return layout(paras, width_pt)[1]


def longest_word(paras):
    m = 0.0
    for para in paras:
        for t in _tokens(para):
            if not t.is_space:
                m = max(m, t.width)
    return m


# ---------------------------------------------------------------- ajustement

def round_pt(v):
    return max(4.0, round(v * 2) / 2)


def fit_scale(make_paras, width_pt, height_pt, kmin=0.35, step=0.02, kmax=1.0):
    """Plus grand facteur k<=kmax tel que make_paras(k) tienne dans (width, height) sans mot coupé."""
    k = kmax
    while True:
        paras = make_paras(k)
        if longest_word(paras) <= width_pt + 1e-6 and total_height(paras, width_pt) <= height_pt + 1e-6:
            return k, paras
        if k <= kmin:
            return k, paras
        k = max(kmin, k - step)


def balanced_lines(text, run_for_size, width_pt):
    """Retours à la ligne équilibrés (pour les titres centrés).

    Renvoie la liste des lignes (str). Respecte les retours à la ligne saisis par l'utilisateur.
    """
    out = []
    for raw in text.split("\n"):
        raw = raw.strip()
        if not raw:
            out.append("")
            continue
        words = raw.split()
        greedy = _greedy(words, run_for_size, width_pt)
        n = len(greedy)
        if n <= 1:
            out.append(" ".join(words))
            continue
        lo = max(run_for_size(w) for w in words)
        hi = width_pt
        best = greedy
        # plus petite largeur qui donne encore n lignes
        for _ in range(24):
            mid = (lo + hi) / 2
            cand = _greedy(words, run_for_size, mid)
            if len(cand) <= n:
                best, hi = cand, mid
            else:
                lo = mid
        out.extend(best)
    return out


def _greedy(words, wfn, width):
    space = wfn(" ")
    lines, cur, cw = [], [], 0.0
    for w in words:
        ww = wfn(w)
        if not cur:
            cur, cw = [w], ww
        elif cw + space + ww <= width + 1e-6:
            cur.append(w)
            cw += space + ww
        else:
            lines.append(" ".join(cur))
            cur, cw = [w], ww
    if cur:
        lines.append(" ".join(cur))
    return lines
