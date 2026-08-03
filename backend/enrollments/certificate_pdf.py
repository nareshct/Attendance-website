import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

COMPANY_NAME = 'Apex Binary'

NAVY = colors.HexColor('#1e3a5f')
NAVY_DARK = colors.HexColor('#152b47')
GOLD = colors.HexColor('#b8860b')
GREY = colors.HexColor('#6b7280')
CREAM = colors.HexColor('#fdfbf5')
BODY_INK = colors.HexColor('#333333')

PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
MARGIN = 16 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN


def _draw_frame(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(CREAM)
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)

    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(2.5)
    canvas.rect(8 * mm, 8 * mm, PAGE_WIDTH - 16 * mm, PAGE_HEIGHT - 16 * mm, stroke=1, fill=0)

    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.9)
    canvas.rect(11 * mm, 11 * mm, PAGE_WIDTH - 22 * mm, PAGE_HEIGHT - 22 * mm, stroke=1, fill=0)

    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(GREY)
    canvas.drawCentredString(PAGE_WIDTH / 2, 13 * mm, f'{COMPANY_NAME} · Issued {date.today():%d %b %Y}')
    canvas.restoreState()


def render_certificate_pdf(enrollment):
    """Render a completion certificate for a finished enrollment and return raw PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=26 * mm, bottomMargin=22 * mm,
    )
    elements = []

    student = enrollment.student
    course = enrollment.course

    company_style = ParagraphStyle('Company', fontName='Helvetica-Bold', fontSize=13, textColor=NAVY, alignment=1, spaceAfter=2)
    tagline_style = ParagraphStyle('Tagline', fontName='Helvetica', fontSize=9, textColor=GREY, alignment=1, spaceAfter=12)
    title_style = ParagraphStyle('Title', fontName='Helvetica-Bold', fontSize=28, textColor=NAVY_DARK, alignment=1, leading=34, spaceAfter=6)
    sub_style = ParagraphStyle('Sub', fontName='Helvetica', fontSize=12, textColor=GREY, alignment=1, spaceAfter=12)
    name_style = ParagraphStyle('Name', fontName='Helvetica-Bold', fontSize=25, textColor=NAVY, alignment=1, spaceAfter=10)
    body_style = ParagraphStyle('Body', fontName='Helvetica', fontSize=12.5, textColor=BODY_INK, alignment=1, leading=18, spaceAfter=4)
    course_style = ParagraphStyle('Course', fontName='Helvetica-Bold', fontSize=16, textColor=GOLD, alignment=1, spaceBefore=4, spaceAfter=6)

    elements.append(Paragraph(COMPANY_NAME, company_style))
    elements.append(Paragraph('Coaching center for kids', tagline_style))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph('CERTIFICATE OF COMPLETION', title_style))
    elements.append(Paragraph('This certifies that', sub_style))
    elements.append(Paragraph(escape(student.name), name_style))
    elements.append(Paragraph('has successfully completed the course', body_style))
    elements.append(Paragraph(escape(course.name), course_style))
    elements.append(Paragraph(
        f'{enrollment.classes_total} classes &nbsp;·&nbsp; '
        f'{enrollment.start_date:%d %b %Y} to {date.today():%d %b %Y}',
        body_style,
    ))
    elements.append(Spacer(1, 18 * mm))

    sig_style = ParagraphStyle('Sig', fontName='Helvetica', fontSize=9.5, textColor=GREY, alignment=1)
    sig_name_style = ParagraphStyle('SigName', fontName='Helvetica-Bold', fontSize=11, textColor=NAVY_DARK, alignment=1, spaceAfter=2)
    sig_table = Table(
        [
            [Paragraph(escape(enrollment.trainer.name), sig_name_style), '', Paragraph(COMPANY_NAME, sig_name_style)],
            [Paragraph('Trainer', sig_style), '', Paragraph('Coaching Center', sig_style)],
        ],
        colWidths=[CONTENT_WIDTH * 0.35, CONTENT_WIDTH * 0.3, CONTENT_WIDTH * 0.35],
    )
    sig_table.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (0, 0), 0.75, GREY),
        ('LINEABOVE', (2, 0), (2, 0), 0.75, GREY),
        ('TOPPADDING', (0, 0), (-1, 0), 4),
    ]))
    elements.append(sig_table)

    doc.build(elements, onFirstPage=_draw_frame, onLaterPages=_draw_frame)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
