"""Export PPTX éditable (vraies zones de texte, formes et images)."""
import io

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Mm, Pt

from . import fonts
from .model import Page, Pic, Rect, TextBox
from .textfit import MM_PER_PT

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _rgb(hexcolor):
    h = hexcolor.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _emu(mm):
    return Emu(int(round(mm * 36000)))


def _strip_style(shape):
    st = shape._element.find(qn("p:style"))
    if st is not None:
        shape._element.remove(st)


def _add_rect(slide, r: Rect):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, _emu(r.x), _emu(r.y), _emu(r.w), _emu(r.h))
    shp.name = r.name
    _strip_style(shp)
    if r.fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = _rgb(r.fill)
    else:
        shp.fill.background()
    if r.line:
        shp.line.color.rgb = _rgb(r.line)
        shp.line.width = Pt(r.line_pt)
    else:
        shp.line.fill.background()
    return shp


def _add_pic(slide, pic: Pic):
    buf = io.BytesIO()
    im = pic.image
    longest = max(im.size)
    if longest > 2600:
        k = 2600 / longest
        im = im.resize((round(im.width * k), round(im.height * k)))
    if pic.fmt == "AUTO" and im.mode not in ("RGBA", "LA", "P"):
        im.convert("RGB").save(buf, "JPEG", quality=93)
    else:
        im.save(buf, "PNG")
    buf.seek(0)
    p = slide.shapes.add_picture(buf, _emu(pic.x), _emu(pic.y), _emu(pic.w), _emu(pic.h))
    p.name = pic.name
    return p


_ALIGN = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT, "j": PP_ALIGN.JUSTIFY}


def _add_text(slide, tb: TextBox):
    shp = slide.shapes.add_textbox(_emu(tb.x), _emu(tb.y), _emu(tb.w), _emu(tb.h))
    shp.name = tb.name
    tf = shp.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    ins = _emu(tb.inset)
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = ins
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[tb.anchor]
    if tb.rot == 270:
        tf._txBody.find(qn("a:bodyPr")).set("vert", "vert270")

    first = True
    for para in tb.paras:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = _ALIGN[para.align]
        pPr = p._p.get_or_add_pPr()
        if para.left_mm or para.first_mm:
            pPr.set("marL", str(int(round((para.left_mm + 0) * 36000))))
            pPr.set("indent", str(int(round(para.first_mm * 36000))))
        if para.space_before_pt:
            spc = etree.SubElement(pPr, qn("a:spcBef"))
            etree.SubElement(spc, qn("a:spcPts")).set("val", str(int(round(para.space_before_pt * 100))))
        if para.bullet:
            etree.SubElement(pPr, qn("a:buFont")).set("typeface", "Arial")
            etree.SubElement(pPr, qn("a:buChar")).set("char", para.bullet)
        else:
            etree.SubElement(pPr, qn("a:buNone"))
        any_text = False
        for run in para.runs:
            if run.text == "":
                continue
            any_text = True
            r = p.add_run()
            r.text = run.text
            f = r.font
            f.name = fonts.PPTX_NAMES[run.family]
            f.size = Pt(run.size)
            f.bold = bool(run.bold)
            f.italic = bool(run.italic)
            f.color.rgb = _rgb(run.color)
            rPr = r._r.get_or_add_rPr()
            rPr.set("lang", "fr-FR")
            if run.caps:
                rPr.set("cap", "all")
            elif run.smallcaps:
                rPr.set("cap", "small")
            # police pour tous les alphabets
            for tag in ("a:ea", "a:cs"):
                el = etree.SubElement(rPr, qn(tag))
                el.set("typeface", fonts.PPTX_NAMES[run.family])
        if not any_text:
            size = para.runs[0].size if para.runs else 10
            end = etree.SubElement(p._p, qn("a:endParaRPr"))
            end.set("lang", "fr-FR")
            end.set("sz", str(int(round(size * 100))))
    return shp


def build_pptx(pages, path, title=""):
    prs = Presentation()
    W, H = pages[0].w, pages[0].h
    prs.slide_width, prs.slide_height = _emu(W), _emu(H)
    blank = prs.slide_layouts[6]
    for page in pages:
        slide = prs.slides.add_slide(blank)
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = _rgb(page.bg)
        for el in page.elements:
            if isinstance(el, Rect):
                _add_rect(slide, el)
            elif isinstance(el, Pic):
                _add_pic(slide, el)
            elif isinstance(el, TextBox):
                _add_text(slide, el)
    prs.core_properties.title = title or "Couverture CMPL"
    prs.core_properties.author = "CMPL Éditeur"
    prs.save(path)
