"""Dessin d'une page en PNG avec Pillow."""
from PIL import Image, ImageDraw

from . import fonts, textfit
from .model import Page, Pic, Rect, TextBox
from .textfit import MM_PER_PT, SMALLCAPS_SCALE

try:
    from PIL import features as _f
    _RAQM = _f.check("raqm")
except Exception:  # pragma: no cover
    _RAQM = False


def _px(mm, dpi):
    return mm / 25.4 * dpi


def _draw_text(draw, xy, text, font, fill):
    if _RAQM:
        try:
            draw.text(xy, text, font=font, fill=fill, anchor="ls", features=["-kern"])
            return
        except Exception:
            pass
    draw.text(xy, text, font=font, fill=fill, anchor="ls")


def _draw_run_text(draw, x_px, base_px, text, run, scale, dpi):
    """Dessine un morceau de texte (gère majuscules et petites capitales). Retourne la largeur en px."""
    path = fonts.resolve(run.family, run.bold, run.italic)
    size_px = run.size * scale
    if run.caps:
        text = text.upper()
    if run.smallcaps:
        x = x_px
        for seg, small in textfit.split_smallcaps(text):
            f = fonts.pil_font(path, max(1.0, size_px * (SMALLCAPS_SCALE if small else 1.0)))
            seg = seg.upper() if small else seg
            _draw_text(draw, (x, base_px), seg, f, run.color)
            x += textfit.text_width_pt(seg, run.family, run.size * (SMALLCAPS_SCALE if small else 1.0),
                                       run.bold, run.italic) * scale
        return x - x_px
    f = fonts.pil_font(path, max(1.0, size_px))
    _draw_text(draw, (x_px, base_px), text, f, run.color)
    return textfit.run_width(run, text if not run.caps else text) * scale


def _draw_textbox(img, tb: TextBox, dpi):
    scale = dpi / 72.0
    if tb.rot == 0:
        L_mm, T_mm = tb.w, tb.h
    else:
        L_mm, T_mm = tb.h, tb.w
    L_px, T_px = max(1, round(_px(L_mm, dpi))), max(1, round(_px(T_mm, dpi)))
    inset_pt = tb.inset / MM_PER_PT
    avail_w = (L_mm - 2 * tb.inset) / MM_PER_PT
    avail_h = (T_mm - 2 * tb.inset) / MM_PER_PT
    lines, total = textfit.layout(tb.paras, avail_w)
    if tb.anchor == "m":
        y0 = (avail_h - total) / 2
    elif tb.anchor == "b":
        y0 = avail_h - total
    else:
        y0 = 0.0
    canvas = Image.new("RGBA", (L_px, T_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    for line in lines:
        base = (inset_pt + y0 + line.y_pt + line.ascent_pt) * scale
        if line.bullet is not None:
            _draw_run_text(d, (inset_pt + line.bullet_x_pt) * scale, base, line.bullet.text, line.bullet.run, scale, dpi)
        x = (inset_pt + line.x_pt) * scale
        for piece in line.pieces:
            if piece.is_space:
                x += (piece.width + line.extra_space_pt) * scale
                continue
            _draw_run_text(d, x, base, piece.text, piece.run, scale, dpi)
            x += piece.width * scale
    if tb.rot == 270:
        canvas = canvas.rotate(90, expand=True)
    img.alpha_composite(canvas, (round(_px(tb.x, dpi)), round(_px(tb.y, dpi)))) if img.mode == "RGBA" else \
        img.paste(canvas, (round(_px(tb.x, dpi)), round(_px(tb.y, dpi))), canvas)


def _draw_rect(img, d, r: Rect, dpi):
    x0, y0 = _px(r.x, dpi), _px(r.y, dpi)
    x1, y1 = _px(r.x + r.w, dpi), _px(r.y + r.h, dpi)
    lw = _px(r.line_pt * MM_PER_PT, dpi) if r.line else 0
    if r.line and lw > 0:
        d.rectangle([round(x0 - lw / 2), round(y0 - lw / 2), round(x1 + lw / 2) - 1, round(y1 + lw / 2) - 1],
                    fill=r.line)
        if r.fill:
            d.rectangle([round(x0 + lw / 2), round(y0 + lw / 2), round(x1 - lw / 2) - 1, round(y1 - lw / 2) - 1],
                        fill=r.fill)
    elif r.fill:
        d.rectangle([round(x0), round(y0), max(round(x1) - 1, round(x0)), max(round(y1) - 1, round(y0))], fill=r.fill)


def _draw_pic(img, pic: Pic, dpi):
    w, h = max(1, round(_px(pic.w, dpi))), max(1, round(_px(pic.h, dpi)))
    im = pic.image
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
    else:
        im = im.convert("RGB")
    im = im.resize((w, h), Image.LANCZOS)
    pos = (round(_px(pic.x, dpi)), round(_px(pic.y, dpi)))
    if im.mode == "RGBA":
        img.paste(im, pos, im)
    else:
        img.paste(im, pos)


def render_page(page: Page, dpi=300, crop=True):
    W, H = round(_px(page.w, dpi)), round(_px(page.h, dpi))
    img = Image.new("RGB", (W, H), page.bg)
    d = ImageDraw.Draw(img)
    for el in page.elements:
        if isinstance(el, Rect):
            _draw_rect(img, d, el, dpi)
        elif isinstance(el, Pic):
            _draw_pic(img, el, dpi)
        elif isinstance(el, TextBox):
            _draw_textbox(img, el, dpi)
    if crop and page.crop:
        x0, y0, x1, y1 = page.crop
        img = img.crop((round(_px(x0, dpi)), round(_px(y0, dpi)), round(_px(x1, dpi)), round(_px(y1, dpi))))
    return img
