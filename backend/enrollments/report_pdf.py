import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

COMPANY_NAME = 'Apex Binary'

NAVY = colors.HexColor('#0f172a')
NAVY_DARK = colors.HexColor('#0a0f1c')
SKY = colors.HexColor('#3b82f6')
GREEN = colors.HexColor('#176b41')
ACCENT = colors.HexColor('#4338ca')
GREY = colors.HexColor('#64748b')
LINE = colors.HexColor('#e2e8f0')
CARD_BG = colors.HexColor('#eef2ff')
STRIPE_BG = colors.HexColor('#f1f5f9')
BAR_BG = colors.HexColor('#e5e7eb')
WHITE = colors.white

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

HEADER_HEIGHT = 32 * mm
FOOTER_HEIGHT = 16 * mm

BAR_WIDTH = CONTENT_WIDTH - 4 * mm - 22 * mm
BAR_HEIGHT = 7 * mm


def _progress_bar(fraction):
    """A single-row Table rendering a filled/empty progress bar for `fraction` (0-1)."""
    radii = [BAR_HEIGHT / 2] * 4
    if 0 < fraction < 1:
        filled = BAR_WIDTH * fraction
        table = Table([['', '']], colWidths=[filled, BAR_WIDTH - filled], rowHeights=[BAR_HEIGHT])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), GREEN),
            ('BACKGROUND', (1, 0), (1, 0), BAR_BG),
            ('BOX', (0, 0), (-1, -1), 0.75, LINE),
            ('ROUNDEDCORNERS', radii),
        ]))
        return table

    table = Table([['']], colWidths=[BAR_WIDTH], rowHeights=[BAR_HEIGHT])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), GREEN if fraction >= 1 else BAR_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, LINE),
        ('ROUNDEDCORNERS', radii),
    ]))
    return table


def _section_heading(text):
    style = ParagraphStyle('SectionHeading', fontName='Helvetica-Bold', fontSize=12, textColor=NAVY, spaceAfter=0)
    underline = Table([['']], colWidths=[16 * mm], rowHeights=[1.2 * mm])
    underline.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, 0), ACCENT)]))
    heading_table = Table([[Paragraph(text, style)], [underline]], colWidths=[CONTENT_WIDTH])
    heading_table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 0),
    ]))
    return heading_table


def _draw_header_footer(canvas, doc):
    canvas.saveState()

    # Header band
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_HEIGHT - HEADER_HEIGHT, PAGE_WIDTH, HEADER_HEIGHT, stroke=0, fill=1)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_HEIGHT - HEADER_HEIGHT - 1.5 * mm, PAGE_WIDTH, 1.5 * mm, stroke=0, fill=1)

    canvas.setFillColor(WHITE)
    canvas.setFont('Helvetica-Bold', 17)
    canvas.drawString(MARGIN, PAGE_HEIGHT - HEADER_HEIGHT / 2 - 2 * mm, COMPANY_NAME)

    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.HexColor('#c7d2fe'))
    canvas.drawString(MARGIN, PAGE_HEIGHT - HEADER_HEIGHT / 2 + 4 * mm, 'Coaching center for kids')

    canvas.setFont('Helvetica-Bold', 19)
    canvas.setFillColor(WHITE)
    canvas.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - HEADER_HEIGHT / 2 - 1 * mm, 'STUDENT REPORT')

    # Footer
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.75)
    canvas.line(MARGIN, FOOTER_HEIGHT - 4 * mm, PAGE_WIDTH - MARGIN, FOOTER_HEIGHT - 4 * mm)

    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(GREY)
    canvas.drawString(MARGIN, FOOTER_HEIGHT - 8 * mm, f'Generated on {date.today():%d %b %Y} · {COMPANY_NAME}')
    canvas.drawRightString(PAGE_WIDTH - MARGIN, FOOTER_HEIGHT - 8 * mm, f'Page {canvas.getPageNumber()}')

    canvas.restoreState()


def render_student_report_pdf(enrollment):
    """Render a progress report for one student's enrollment/batch and return raw PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=HEADER_HEIGHT + 10 * mm, bottomMargin=FOOTER_HEIGHT + 6 * mm,
    )
    styles = getSampleStyleSheet()
    elements = []

    student = enrollment.student

    # Student info card — accent stripe + tinted background
    name_style = ParagraphStyle('StudentName', fontName='Helvetica-Bold', fontSize=15, textColor=NAVY_DARK)
    meta_style = ParagraphStyle('StudentMeta', fontName='Helvetica', fontSize=9.5, textColor=GREY, spaceBefore=2)
    card_inner = Table(
        [[Paragraph(escape(student.name), name_style)],
         [Paragraph(
             f'Student ID: <b>{escape(student.student_id)}</b> &nbsp;&nbsp;|&nbsp;&nbsp; '
             f'Course: <b>{escape(enrollment.course.name)}</b>',
             meta_style,
         )]],
        colWidths=[CONTENT_WIDTH - 20 * mm],
    )
    card_inner.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, 0), 0),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 0),
        ('TOPPADDING', (0, 1), (-1, 1), 3 * mm),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 2),
    ]))
    card = Table([['', card_inner]], colWidths=[6 * mm, CONTENT_WIDTH - 6 * mm])
    card.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), GREEN),
        ('BACKGROUND', (1, 0), (1, 0), CARD_BG),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('LEFTPADDING', (1, 0), (1, 0), 8 * mm),
        ('RIGHTPADDING', (1, 0), (1, 0), 6 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 6 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6 * mm),
    ]))
    elements.append(card)
    elements.append(Spacer(1, 9 * mm))

    # Progress section
    elements.append(_section_heading('Course Progress'))
    elements.append(Spacer(1, 4 * mm))

    total = enrollment.classes_total or 1
    completed = min(enrollment.classes_completed, total)
    fraction = completed / total
    pct = round(fraction * 100)
    pct_color = GREEN if fraction >= 1 else NAVY

    count_style = ParagraphStyle('CountLabel', fontName='Helvetica', fontSize=10, textColor=GREY)
    elements.append(Paragraph(
        f'Classes taken: <b><font color="#0f172a">{enrollment.classes_completed}</font></b> / {enrollment.classes_total}',
        count_style,
    ))
    elements.append(Spacer(1, 3 * mm))

    pct_style = ParagraphStyle('PctLabel', fontName='Helvetica-Bold', fontSize=11, textColor=pct_color, alignment=1)
    bar_row = Table(
        [[_progress_bar(fraction), Paragraph(f'{pct}%', pct_style)]],
        colWidths=[BAR_WIDTH, CONTENT_WIDTH - BAR_WIDTH],
    )
    bar_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(bar_row)
    elements.append(Spacer(1, 10 * mm))

    # Sessions table
    elements.append(_section_heading('Class Sessions'))
    elements.append(Spacer(1, 4 * mm))

    records = enrollment.attendance_records.filter(status='present').order_by('date')
    rows = [['#', 'Date', 'Topic Covered']]
    for i, a in enumerate(records, start=1):
        rows.append([str(i), str(a.date), a.topic_covered or '-'])
    if len(rows) == 1:
        rows.append(['-', '-', 'No classes taken yet.'])

    sessions_table = Table(rows, colWidths=[15 * mm, 30 * mm, CONTENT_WIDTH - 45 * mm], repeatRows=1)
    sessions_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, ACCENT),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, STRIPE_BG]),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, LINE),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    elements.append(sessions_table)

    doc.build(elements, onFirstPage=_draw_header_footer, onLaterPages=_draw_header_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
