import io
import math
from datetime import date
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Circle, Drawing, Polygon

# Same visual design as enrollments/certificate_pdf.py — see that file's module
# docstring-equivalent comment in batches/report_pdf.py for why this is a
# parallel copy rather than a shared import.
COMPANY_NAME = 'Apex Binary'

NAVY = colors.HexColor('#0f172a')
NAVY_DARK = colors.HexColor('#0a0f1c')
GOLD = colors.HexColor('#b8860b')
GOLD_LIGHT = colors.HexColor('#d4af37')
GREY = colors.HexColor('#64748b')
CREAM = colors.HexColor('#fdfbf5')
BODY_INK = colors.HexColor('#333333')

PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
MARGIN = 16 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

BORDER_X0, BORDER_Y0 = 11 * mm, 11 * mm
BORDER_X1, BORDER_Y1 = PAGE_WIDTH - 11 * mm, PAGE_HEIGHT - 11 * mm


def _display_name(student):
    """B2B students train under their client's brand, not ours — swap the
    issuing name shown on their report/certificate to the client's company
    name. B2C students (or a B2B student whose client link is somehow
    missing) fall back to our own name."""
    if student.source_type == 'B2B' and student.client_id:
        return student.client.company_name
    return COMPANY_NAME


def _branding_client(student):
    """The Client whose logo should brand this certificate — same
    B2B-with-a-linked-client condition as _display_name."""
    if student.source_type == 'B2B' and student.client_id:
        return student.client
    return None


def _logo_flowable(client, max_height=18 * mm, max_width=60 * mm):
    """The client's uploaded logo, sized to fit while preserving aspect
    ratio. None if there's no client, no logo, or the file can't be read
    (e.g. missing from disk after a media wipe) — falls back to text-only."""
    if not client or not client.logo:
        return None
    try:
        with PILImage.open(client.logo.path) as img:
            w, h = img.size
        if not w or not h:
            return None
        height = max_height
        width = height * (w / h)
        if width > max_width:
            width = max_width
            height = width * (h / w)
        return Image(client.logo.path, width=width, height=height)
    except Exception:
        return None


def _corner_ornament(canvas, x, y, flip_x, flip_y, size=9 * mm):
    dx = size if flip_x else -size
    dy = size if flip_y else -size
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(1.1)
    canvas.line(x, y, x + dx, y)
    canvas.line(x, y, x, y + dy)

    r = 1.6 * mm
    canvas.setFillColor(GOLD)
    path = canvas.beginPath()
    path.moveTo(x, y + r)
    path.lineTo(x + r, y)
    path.lineTo(x, y - r)
    path.lineTo(x - r, y)
    path.close()
    canvas.drawPath(path, fill=1, stroke=0)


def _draw_frame(canvas, doc, display_name, cert_no):
    canvas.saveState()
    canvas.setFillColor(CREAM)
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)

    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(2.5)
    canvas.rect(8 * mm, 8 * mm, PAGE_WIDTH - 16 * mm, PAGE_HEIGHT - 16 * mm, stroke=1, fill=0)

    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.9)
    canvas.rect(BORDER_X0, BORDER_Y0, BORDER_X1 - BORDER_X0, BORDER_Y1 - BORDER_Y0, stroke=1, fill=0)

    _corner_ornament(canvas, BORDER_X0, BORDER_Y0, flip_x=True, flip_y=True)
    _corner_ornament(canvas, BORDER_X1, BORDER_Y0, flip_x=False, flip_y=True)
    _corner_ornament(canvas, BORDER_X0, BORDER_Y1, flip_x=True, flip_y=False)
    _corner_ornament(canvas, BORDER_X1, BORDER_Y1, flip_x=False, flip_y=False)

    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(GREY)
    canvas.drawString(BORDER_X0 + 3 * mm, 13 * mm, f'Certificate No. {cert_no}')
    canvas.drawRightString(BORDER_X1 - 3 * mm, 13 * mm, f'{display_name} · Issued {date.today():%d %b %Y}')
    canvas.restoreState()


def _title_divider(width=70 * mm, height=6 * mm):
    d = Drawing(width, height)
    mid_y = height / 2
    d.add(Polygon(points=[0, mid_y - 0.35 * mm, width / 2 - 3 * mm, mid_y - 0.35 * mm,
                           width / 2 - 3 * mm, mid_y + 0.35 * mm, 0, mid_y + 0.35 * mm], fillColor=GOLD, strokeColor=None))
    d.add(Polygon(points=[width / 2 + 3 * mm, mid_y - 0.35 * mm, width, mid_y - 0.35 * mm,
                           width, mid_y + 0.35 * mm, width / 2 + 3 * mm, mid_y + 0.35 * mm], fillColor=GOLD, strokeColor=None))
    r = 2.1 * mm
    d.add(Polygon(points=[width / 2, mid_y + r, width / 2 + r, mid_y,
                           width / 2, mid_y - r, width / 2 - r, mid_y], fillColor=GOLD, strokeColor=None))
    return d


def _star_points(cx, cy, outer_r, inner_r, points=5, rotation_deg=90):
    pts = []
    angle = math.radians(rotation_deg)
    step = math.pi / points
    for i in range(points * 2):
        r = outer_r if i % 2 == 0 else inner_r
        a = angle + i * step
        pts.extend([cx + r * math.cos(a), cy + r * math.sin(a)])
    return pts


def _seal(diameter=24 * mm):
    d = Drawing(diameter, diameter)
    c = diameter / 2
    d.add(Circle(c, c, c, fillColor=GOLD, strokeColor=NAVY_DARK, strokeWidth=1.1))
    d.add(Circle(c, c, c - 2 * mm, fillColor=None, strokeColor=CREAM, strokeWidth=0.9))
    d.add(Circle(c, c, c - 3.2 * mm, fillColor=NAVY_DARK, strokeColor=None))
    d.add(Polygon(points=_star_points(c, c, c - 6 * mm, (c - 6 * mm) * 0.42), fillColor=GOLD_LIGHT, strokeColor=None))
    return d


def render_batch_certificate_pdf(batch_enrollment):
    """Render a completion certificate for a student's membership in a
    finished Batch and return raw PDF bytes. Caller (BatchEnrollmentViewSet.
    certificate) is responsible for only calling this once the batch itself
    is marked completed — batches have no per-student completion state."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )
    elements = []

    student = batch_enrollment.student
    batch = batch_enrollment.batch
    display_name = _display_name(student)
    logo = _logo_flowable(_branding_client(student))
    cert_no = f'CERT-B-{batch_enrollment.id:06d}'

    company_style = ParagraphStyle('Company', fontName='Times-Bold', fontSize=14, textColor=NAVY, alignment=1, spaceAfter=8)
    title_style = ParagraphStyle('Title', fontName='Times-Bold', fontSize=30, textColor=NAVY_DARK, alignment=1, leading=36, spaceAfter=2)
    sub_style = ParagraphStyle('Sub', fontName='Times-Italic', fontSize=13, textColor=GREY, alignment=1, spaceBefore=8, spaceAfter=10)
    name_style = ParagraphStyle('Name', fontName='Times-BoldItalic', fontSize=27, leading=34, textColor=NAVY, alignment=1, spaceBefore=4, spaceAfter=20)
    body_style = ParagraphStyle('Body', fontName='Times-Roman', fontSize=13, textColor=BODY_INK, alignment=1, leading=19, spaceAfter=4)
    course_style = ParagraphStyle('Course', fontName='Times-Bold', fontSize=18, textColor=GOLD, alignment=1, spaceBefore=4, spaceAfter=8)

    divider = Table([[_title_divider()]], colWidths=[CONTENT_WIDTH], hAlign='CENTER')
    divider.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))

    if logo:
        logo_wrapper = Table([[logo]], colWidths=[CONTENT_WIDTH], hAlign='CENTER')
        logo_wrapper.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
        elements.append(logo_wrapper)
        elements.append(Spacer(1, 3 * mm))

    elements.append(Paragraph(escape(display_name), company_style))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph('CERTIFICATE OF COMPLETION', title_style))
    elements.append(divider)
    elements.append(Paragraph('This certifies that', sub_style))
    elements.append(Paragraph(escape(student.name), name_style))
    elements.append(Paragraph('has successfully completed the course', body_style))
    elements.append(Paragraph(escape(batch.course.name), course_style))
    elements.append(Paragraph(
        f'{batch.total_classes} classes &nbsp;·&nbsp; '
        f'{batch.start_date:%d %b %Y} to {date.today():%d %b %Y}',
        body_style,
    ))
    elements.append(Spacer(1, 10 * mm))

    seal_wrapper = Table([[_seal()]], colWidths=[CONTENT_WIDTH], hAlign='CENTER')
    seal_wrapper.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    elements.append(seal_wrapper)
    elements.append(Spacer(1, 4 * mm))

    sig_style = ParagraphStyle('Sig', fontName='Times-Italic', fontSize=10, textColor=GREY, alignment=1)
    sig_name_style = ParagraphStyle('SigName', fontName='Times-Bold', fontSize=12, textColor=NAVY_DARK, alignment=1, spaceAfter=2)
    sig_table = Table(
        [
            [Paragraph(escape(display_name), sig_name_style)],
            [Paragraph('Coaching Center', sig_style)],
        ],
        colWidths=[CONTENT_WIDTH * 0.4],
        hAlign='CENTER',
    )
    sig_table.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (0, 0), 0.75, GOLD),
        ('TOPPADDING', (0, 0), (-1, 0), 4),
    ]))
    elements.append(sig_table)

    doc.build(
        elements,
        onFirstPage=lambda canvas, doc: _draw_frame(canvas, doc, display_name, cert_no),
        onLaterPages=lambda canvas, doc: _draw_frame(canvas, doc, display_name, cert_no),
    )
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
