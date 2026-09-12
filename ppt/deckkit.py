"""Shared slide-building helpers for the KubeEdgeInfer decks.

Deliberately small: a handful of primitives (title, bullets, table, code box,
figure) styled once here so both decks look like one document. 16:9.
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image

SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.62
BODY_W = SLIDE_W - 2 * MARGIN
BODY_TOP = 1.62

# Palette shared with demo/dashboard.html so slides and live demo match.
INK = RGBColor(0x16, 0x1D, 0x26)
MUTED = RGBColor(0x5E, 0x6E, 0x7E)
FAINT = RGBColor(0x92, 0x9F, 0xAC)
LINE = RGBColor(0xD9, 0xE0, 0xE7)
NAVY = RGBColor(0x0E, 0x2A, 0x47)
BLUE = RGBColor(0x2A, 0x78, 0xD6)
ORANGE = RGBColor(0xD9, 0x76, 0x26)
GREEN = RGBColor(0x2C, 0x93, 0x55)
RED = RGBColor(0xC4, 0x3D, 0x3D)
PURPLE = RGBColor(0x74, 0x53, 0xB8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
WASH = RGBColor(0xF3, 0xF7, 0xFB)
CODEBG = RGBColor(0xF6, 0xF8, 0xFA)
CODEINK = RGBColor(0x1F, 0x29, 0x33)
CODECMT = RGBColor(0x6B, 0x7C, 0x8B)

SANS = "Segoe UI"
MONO = "Consolas"


# --------------------------------------------------------------------------
# deck / slide scaffolding
# --------------------------------------------------------------------------

def new_deck():
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)
    return prs


def blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def rect(slide, x, y, w, h, fill=None, line=None, shape=MSO_SHAPE.RECTANGLE,
         line_w=1.0, adj=None):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if adj is not None:
        try:
            s.adjustments[0] = adj
        except (IndexError, ValueError):
            pass
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(line_w)
    s.shadow.inherit = False
    return s


def tb(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP, wrap=True):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = wrap
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    return tf


def _emit(p, text, size, color, font, bold, italic):
    """Split on ** ** so bullets can bold inline without extra plumbing."""
    for i, part in enumerate(text.split("**")):
        if not part:
            continue
        r = p.add_run()
        r.text = part
        f = r.font
        f.size = Pt(size)
        f.name = font
        f.bold = bold or (i % 2 == 1)
        f.italic = italic
        f.color.rgb = color


def para(tf, text, size=16, color=INK, font=SANS, bold=False, italic=False,
         align=PP_ALIGN.LEFT, before=0, after=6, spacing=1.15, first=False,
         indent=None):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(before)
    p.space_after = Pt(after)
    p.line_spacing = spacing
    if indent is not None:
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(int(Inches(indent[0]))))
        pPr.set("indent", str(int(Inches(indent[1]))))
    _emit(p, text, size, color, font, bold, italic)
    return p


def title_slide(prs, title, subtitle, meta_lines, kicker=None):
    s = blank(prs)
    rect(s, 0, 0, SLIDE_W, SLIDE_H, fill=NAVY)
    rect(s, 0, 0, 0.19, SLIDE_H, fill=BLUE)
    if kicker:
        tf = tb(s, 1.15, 1.42, 11.0, 0.4)
        para(tf, kicker, size=13, color=RGBColor(0x8F, 0xBC, 0xEE), bold=True,
             first=True, after=0)
    tsize = 46.0
    while tsize > 30.0 and len(title) * tsize * 0.60 / 72 > 11.0:
        tsize -= 1.0
    tf = tb(s, 1.15, 1.95, 11.0, 1.9)
    para(tf, title, size=tsize, color=WHITE, bold=True, first=True, after=0,
         spacing=1.02)
    tf = tb(s, 1.15, 3.42, 10.4, 1.3)
    para(tf, subtitle, size=19, color=RGBColor(0xB9, 0xCC, 0xDE), first=True,
         after=0, spacing=1.24)
    rect(s, 1.17, 5.06, 1.5, 0.035, fill=BLUE)
    tf = tb(s, 1.15, 5.42, 11.0, 1.5)
    for i, ln in enumerate(meta_lines):
        para(tf, ln, size=13.5, color=RGBColor(0xA8, 0xBD, 0xD1), first=(i == 0),
             after=5)
    return s


def section_slide(prs, number, title, blurb=None):
    s = blank(prs)
    rect(s, 0, 0, SLIDE_W, SLIDE_H, fill=WASH)
    rect(s, 0, 0, 0.19, SLIDE_H, fill=BLUE)
    tf = tb(s, 1.5, 2.72, 10.0, 0.5)
    para(tf, number, size=15, color=BLUE, bold=True, first=True, after=4)
    tf = tb(s, 1.5, 3.2, 10.6, 1.0)
    para(tf, title, size=38, color=NAVY, bold=True, first=True, after=0)
    if blurb:
        tf = tb(s, 1.5, 4.35, 9.6, 0.9)
        para(tf, blurb, size=15.5, color=MUTED, first=True, spacing=1.3)
    return s


def slide(prs, title, kicker=None, subtitle=None):
    """Standard content slide. Returns (slide, y) where y is the content top.

    The title auto-shrinks to stay on one line; if it still cannot fit, the
    content start is pushed down instead of letting the two collide.
    """
    s = blank(prs)
    y = 0.52
    if kicker:
        tf = tb(s, MARGIN, y, BODY_W, 0.3)
        para(tf, kicker.upper(), size=11, color=BLUE, bold=True, first=True,
             after=0)
        y += 0.33
    # 0.56 em average advance: deliberately pessimistic, so the title still
    # fits one line if PowerPoint substitutes a wider face for Segoe UI.
    tsize = 27.0
    while tsize > 20.0 and len(title) * tsize * 0.60 / 72 > BODY_W:
        tsize -= 0.5
    two_lines = len(title) * tsize * 0.60 / 72 > BODY_W
    tf = tb(s, MARGIN, y, BODY_W, 1.1 if two_lines else 0.55)
    para(tf, title, size=tsize, color=NAVY, bold=True, first=True, after=0,
         spacing=1.05)
    y += 0.98 if two_lines else 0.56
    rect(s, MARGIN, y + 0.07, 0.95, 0.032, fill=BLUE)
    y += 0.30
    if subtitle:
        # Reserve a second line when the subtitle will wrap, so it cannot end
        # up underneath whatever the caller places at the returned y.
        sub_lines = 1 + int(len(subtitle) * 13.5 * 0.52 / 72 // BODY_W)
        tf = tb(s, MARGIN, y, BODY_W, 0.28 * sub_lines + 0.14)
        para(tf, subtitle, size=13.5, color=MUTED, italic=True, first=True,
             after=0, spacing=1.2)
        y += 0.26 * sub_lines + 0.22
    return s, max(y, 1.42)


def bullets(slide_obj, x, y, w, items, size=15.5, gap=7, spacing=1.2,
            h=None):
    """items: (level, text) or (level, text, color)."""
    tf = tb(slide_obj, x, y, w, h or (SLIDE_H - y - 0.55))
    for i, item in enumerate(items):
        lvl, text = item[0], item[1]
        color = item[2] if len(item) > 2 else INK
        if lvl < 0:                                   # bare line, no marker
            para(tf, text, size=size, color=color, first=(i == 0), after=gap,
                 spacing=spacing)
            continue
        mark = "▪  " if lvl == 0 else "–  "
        sz = size if lvl == 0 else size - 1.5
        col = color if len(item) > 2 else (INK if lvl == 0 else MUTED)
        para(tf, mark + text, size=sz, color=col, first=(i == 0), after=gap,
             spacing=spacing, indent=(0.30 + 0.30 * lvl, -0.30))
    return tf


def table(slide_obj, x, y, w, col_w, rows, font=10.5, row_h=0.30,
          head_h=0.36, head_fill=NAVY, zebra=True, align=None, mono_cols=()):
    """rows[0] is the header. col_w are relative weights."""
    n_rows, n_cols = len(rows), len(rows[0])
    total = sum(col_w)
    gf = slide_obj.shapes.add_table(n_rows, n_cols, Inches(x), Inches(y),
                                    Inches(w), Inches(head_h + row_h * (n_rows - 1)))
    t = gf.table
    t.first_row = True
    t.horz_banding = False
    for j, cw in enumerate(col_w):
        t.columns[j].width = Inches(w * cw / total)
    t.rows[0].height = Inches(head_h)
    for i in range(1, n_rows):
        t.rows[i].height = Inches(row_h)

    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.margin_left = c.margin_right = Inches(0.07)
            c.margin_top = c.margin_bottom = Inches(0.02)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.fill.solid()
            if i == 0:
                c.fill.fore_color.rgb = head_fill
            elif zebra and i % 2 == 0:
                c.fill.fore_color.rgb = WASH
            else:
                c.fill.fore_color.rgb = WHITE
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.line_spacing = 1.05
            p.space_before = Pt(0)
            p.space_after = Pt(0)
            if align:
                p.alignment = align[j]
            elif j > 0:
                p.alignment = PP_ALIGN.LEFT
            # Leading marker sets the cell colour. Deliberately NOT "+"/"-",
            # which would collide with signed numbers and mis-colour them.
            txt = str(val)
            col = WHITE if i == 0 else INK
            if i > 0 and txt.startswith("!"):
                txt, col = txt[1:], RED
            elif i > 0 and txt.startswith("^"):
                txt, col = txt[1:], GREEN
            fnt = MONO if j in mono_cols and i > 0 else SANS
            _emit(p, txt, font, col, fnt, bold=(i == 0), italic=False)
    return t


def code_box(slide_obj, x, y, w, h, code, size=10.5, caption=None,
             fill=CODEBG):
    """Monospace block that always fits its box.

    The font is shrunk until the listing fits both vertically (line count)
    and horizontally (longest line), so a box can never spill over the slide.
    """
    rect(slide_obj, x, y, w, h, fill=fill, line=LINE)
    if caption:
        tf = tb(slide_obj, x + 0.14, y + 0.10, w - 0.28, 0.24)
        para(tf, caption, size=9.5, color=BLUE, bold=True, first=True, after=0,
             font=MONO)
        ty = y + 0.36
    else:
        ty = y + 0.13
    lines = code.split("\n")

    avail_h = (y + h - 0.16) - ty
    avail_w = w - 0.34
    if lines:
        # 1.32, not the 1.16 line spacing actually set: renderers that
        # substitute for Consolas use a taller line box, and a listing that
        # spills past its frame looks far worse than one set a point smaller.
        by_height = avail_h * 72.0 / (1.32 * len(lines))
        widest = max(len(ln) for ln in lines) or 1
        by_width = avail_w * 72.0 / (0.5498 * widest)   # Consolas advance
        size = max(6.0, min(size, by_height, by_width))

    tf = tb(slide_obj, x + 0.16, ty, w - 0.32, avail_h)
    for i, ln in enumerate(lines):
        stripped = ln.lstrip()
        if stripped.startswith(("#", "//", "--")):
            col, it = CODECMT, True
        else:
            col, it = CODEINK, False
        para(tf, ln.replace(" ", " ") or " ", size=size, color=col,
             font=MONO, italic=it, first=(i == 0), after=0, spacing=1.16)
    return tf


def figure(slide_obj, path, x, y, w, h, caption=None, border=True):
    """Place an image fitted inside the (x, y, w, h) box, centred."""
    iw, ih = Image.open(path).size
    scale = min(w / iw, h / ih)
    fw, fh = iw * scale, ih * scale
    fx, fy = x + (w - fw) / 2, y + (h - fh) / 2
    if border:
        rect(slide_obj, fx - 0.05, fy - 0.05, fw + 0.10, fh + 0.10,
             fill=WHITE, line=LINE)
    slide_obj.shapes.add_picture(path, Inches(fx), Inches(fy),
                                 Inches(fw), Inches(fh))
    if caption:
        tf = tb(slide_obj, x, fy + fh + 0.12, w, 0.5)
        para(tf, caption, size=11.5, color=MUTED, align=PP_ALIGN.CENTER,
             first=True, after=0, spacing=1.18)
    return fx, fy, fw, fh


def callout(slide_obj, x, y, w, h, text, accent=BLUE, size=13, label=None):
    rect(slide_obj, x, y, w, h, fill=WASH)
    rect(slide_obj, x, y, 0.055, h, fill=accent)
    tf = tb(slide_obj, x + 0.24, y + 0.13, w - 0.42, h - 0.24,
            anchor=MSO_ANCHOR.MIDDLE)
    if label:
        para(tf, label.upper(), size=9.5, color=accent, bold=True, first=True,
             after=3)
        para(tf, text, size=size, color=INK, spacing=1.2, after=0)
    else:
        para(tf, text, size=size, color=INK, first=True, spacing=1.2, after=0)
    return tf


def stat(slide_obj, x, y, w, value, label, sub=None, accent=BLUE):
    rect(slide_obj, x, y, w, 1.42, fill=WHITE, line=LINE)
    rect(slide_obj, x, y, w, 0.05, fill=accent)
    tf = tb(slide_obj, x + 0.16, y + 0.22, w - 0.32, 0.6)
    para(tf, value, size=27, color=accent, bold=True, first=True, after=0)
    tf = tb(slide_obj, x + 0.16, y + 0.82, w - 0.32, 0.5)
    para(tf, label, size=11.5, color=INK, bold=True, first=True, after=2,
         spacing=1.1)
    if sub:
        para(tf, sub, size=9.5, color=MUTED, spacing=1.1, after=0)


def stage_box(slide_obj, x, y, w, h, num, title, lines, accent=BLUE):
    rect(slide_obj, x, y, w, h, fill=WHITE, line=LINE)
    rect(slide_obj, x, y, w, 0.055, fill=accent)
    tf = tb(slide_obj, x + 0.18, y + 0.20, w - 0.36, 0.3)
    para(tf, num, size=10, color=accent, bold=True, first=True, after=2)
    tf = tb(slide_obj, x + 0.18, y + 0.50, w - 0.36, 0.34)
    para(tf, title, size=15.5, color=NAVY, bold=True, first=True, after=0)
    tf = tb(slide_obj, x + 0.18, y + 0.92, w - 0.36, h - 1.05)
    for i, ln in enumerate(lines):
        para(tf, ln, size=10.5, color=MUTED, first=(i == 0), after=4,
             spacing=1.16)


def arrow(slide_obj, x, y, w, h=0.24, color=FAINT):
    s = slide_obj.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y),
                                   Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()
    s.shadow.inherit = False
    return s


def paginate(prs, label, skip_first=True):
    for i, s in enumerate(prs.slides):
        if skip_first and i == 0:
            continue
        tf = tb(s, MARGIN, SLIDE_H - 0.46, BODY_W, 0.26)
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        _emit(p, label, 9, FAINT, SANS, False, False)
        tf2 = tb(s, SLIDE_W - MARGIN - 1.2, SLIDE_H - 0.46, 1.2, 0.26)
        p2 = tf2.paragraphs[0]
        p2.alignment = PP_ALIGN.RIGHT
        _emit(p2, str(i + 1), 9, FAINT, SANS, False, False)


def notes(slide_obj, text):
    slide_obj.notes_slide.notes_text_frame.text = text
