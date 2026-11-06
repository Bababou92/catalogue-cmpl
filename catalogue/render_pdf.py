"""PDF vectoriel (texte sélectionnable) à partir des mêmes éléments que l'aperçu PNG et le PPTX."""
import hashlib
import io

from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from . import fonts, textfit
from .model import Page, Pic, Rect, TextBox
from .textfit import MM_PER_PT

PT_PER_MM = 72.0 / 25.4
_registered = {}
_jpeg_cache = {}


def _font_name(run):
    path = fonts.resolve(run.family, run.bold, run.italic)
    name = _registered.get(path)
    if not name:
        name = "F" + hashlib.md5(path.encode()).hexdigest()[:10]
        pdfmetrics.registerFont(TTFont(name, path))
        _registered[path] = name
    return name


def _image_reader(im):
    key = id(im)
    if key in _jpeg_cache:
        return _jpeg_cache[key][1]
    if im.mode in ("RGBA", "LA", "P"):
        rd = ImageReader(im.convert("RGBA"))
    else:
        b = io.BytesIO()
        im.convert("RGB").save(b, "JPEG", quality=90)
        b.seek(0)
        rd = ImageReader(b)
    _jpeg_cache[key] = (im, rd)             # on garde im pour que l'id reste valable
    return rd


def _draw_text(c, tb: TextBox, page_h_pt):
    if tb.rot:
        return
    x0, y0 = tb.x * PT_PER_MM, tb.y * PT_PER_MM
    inset = tb.inset / MM_PER_PT
    avail_w = (tb.w - 2 * tb.inset) / MM_PER_PT
    avail_h = (tb.h - 2 * tb.inset) / MM_PER_PT
    lines, total = textfit.layout(tb.paras, avail_w)
    off = {"t": 0.0, "m": (avail_h - total) / 2, "b": avail_h - total}[tb.anchor]
    for line in lines:
        base = y0 + inset + off + line.y_pt + line.ascent_pt
        x = x0 + inset + line.x_pt
        if line.bullet is not None:
            run = line.bullet.run
            c.setFont(_font_name(run), run.size)
            c.setFillColor(HexColor(run.color))
            c.drawString(x0 + inset + line.bullet_x_pt, page_h_pt - base, line.bullet.text)
        # on dessine chaque ligne d'un seul tenant (mots + espaces) pour que le texte du PDF reste copiable / cherchable
        groups, cur = [], None
        for p in line.pieces:
            if cur is not None and cur["run"] == p.run and not line.extra_space_pt:
                cur["text"] += p.text
                cur["w"] += p.width
            else:
                cur = {"run": p.run, "text": p.text, "w": p.width + (line.extra_space_pt if p.is_space else 0.0)}
                groups.append(cur)
        for g in groups:
            run = g["run"]
            text = g["text"].upper() if run.caps else g["text"]
            if text.strip():
                c.setFont(_font_name(run), run.size)
                c.setFillColor(HexColor(run.color))
                c.drawString(x, page_h_pt - base, text)
            x += g["w"]


def build_pdf(pages, path, title="Catalogue CMPL", author="CMPL"):
    W, H = pages[0].w * PT_PER_MM, pages[0].h * PT_PER_MM
    c = canvas.Canvas(path, pagesize=(W, H), pageCompression=1)
    c.setTitle(title)
    c.setAuthor(author)
    for page in pages:
        if page.bg and page.bg.upper() != "#FFFFFF":
            c.setFillColor(HexColor(page.bg))
            c.rect(0, 0, W, H, fill=1, stroke=0)
        for el in page.elements:
            if isinstance(el, Rect):
                x, y, w, h = el.x * PT_PER_MM, el.y * PT_PER_MM, el.w * PT_PER_MM, el.h * PT_PER_MM
                if el.fill:
                    c.setFillColor(HexColor(el.fill))
                if el.line:
                    c.setStrokeColor(HexColor(el.line))
                    c.setLineWidth(el.line_pt)
                if el.fill or el.line:
                    c.rect(x, H - y - h, w, h, fill=1 if el.fill else 0, stroke=1 if el.line else 0)
            elif isinstance(el, Pic):
                c.drawImage(_image_reader(el.image), el.x * PT_PER_MM, H - (el.y + el.h) * PT_PER_MM,
                            el.w * PT_PER_MM, el.h * PT_PER_MM, mask="auto")
            elif isinstance(el, TextBox):
                _draw_text(c, el, H)
        c.showPage()
    c.save()
