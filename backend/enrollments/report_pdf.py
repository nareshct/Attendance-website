import io
from datetime import date
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Circle, Drawing, Rect, String

COMPANY_NAME = 'Apex Binary'

PAGE_BG = colors.HexColor('#eef1f6')
CARD_BG = colors.white
TEXT_DARK = colors.HexColor('#111827')
TEXT_GREY = colors.HexColor('#6b7280')
BLUE = colors.HexColor('#2563eb')
BLUE_LIGHT = colors.HexColor('#dbeafe')
GREEN_BG = colors.HexColor('#dcfce7')
GREEN_TEXT = colors.HexColor('#16a34a')
GREY_BG = colors.HexColor('#f3f4f6')
BORDER = colors.HexColor('#e5e7eb')
BAR_TRACK = colors.HexColor('#e5e7eb')
WHITE = colors.white

# Mirrors the app's own table styling (frontend/src/index.css .table-head-row/
# .table-head-cell/.table-row/.table-cell) so the "Detailed History" table
# reads as the same design language as the rest of the product.
TABLE_HEAD_BG = colors.HexColor('#f1f5f9')
TABLE_HEAD_TEXT = colors.HexColor('#64748b')
TABLE_BODY_TEXT = colors.HexColor('#374151')
TABLE_ROW_BORDER = colors.HexColor('#e2e8f0')
TABLE_STRIPE_BG = colors.HexColor('#e2e8f2')

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

CARD_PAD = 6 * mm
INNER_WIDTH = CONTENT_WIDTH - 2 * CARD_PAD

STATUS_BADGES = {
    'ongoing': ('ACTIVE', GREEN_BG, GREEN_TEXT),
    'completed': ('COMPLETED', BLUE_LIGHT, BLUE),
    'withdrawn': ('WITHDRAWN', GREY_BG, TEXT_GREY),
}


def _display_name(student):
    """B2B students train under their client's brand, not ours — swap the
    issuing name shown on their report/certificate to the client's company
    name. B2C students (or a B2B student whose client link is somehow
    missing) fall back to our own name."""
    if student.source_type == 'B2B' and student.client_id:
        return student.client.company_name
    return COMPANY_NAME


def _branding_client(student):
    """The Client whose logo/tagline should brand this student's report —
    same B2B-with-a-linked-client condition as _display_name, just returning
    the object instead of only its name."""
    if student.source_type == 'B2B' and student.client_id:
        return student.client
    return None


def _logo_flowable(client, max_height=12 * mm, max_width=42 * mm):
    """The client's uploaded logo, sized to fit within max_height/max_width
    while preserving its own aspect ratio. None if there's no client, no
    logo, or the file can't be read (e.g. missing from disk after a media
    wipe — see Client.logo's comment) — callers fall back to text-only."""
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


def _draw_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)
    canvas.restoreState()


def _card(flowables, pad=CARD_PAD):
    wrapper = Table([[flowables]], colWidths=[CONTENT_WIDTH])
    wrapper.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CARD_BG),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
        ('TOPPADDING', (0, 0), (-1, -1), pad),
        ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
        ('LEFTPADDING', (0, 0), (-1, -1), pad),
        ('RIGHTPADDING', (0, 0), (-1, -1), pad),
    ]))
    return wrapper


def _avatar(letter, diameter=16 * mm):
    d = Drawing(diameter, diameter)
    d.add(Circle(diameter / 2, diameter / 2, diameter / 2, fillColor=BLUE, strokeColor=None))
    d.add(String(
        diameter / 2, diameter / 2 - diameter * 0.16, letter,
        fontName='Helvetica-Bold', fontSize=diameter * 0.42, fillColor=WHITE, textAnchor='middle',
    ))
    return d


def _badge(text, bg, fg, width=30 * mm):
    style = ParagraphStyle('Badge', fontName='Helvetica-Bold', fontSize=8.5, textColor=fg, alignment=1)
    table = Table([[Paragraph(text, style)]], colWidths=[width])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('ROUNDEDCORNERS', [9, 9, 9, 9]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return table


def _status_badge(status):
    text, bg, fg = STATUS_BADGES.get(status, (status.upper(), GREY_BG, TEXT_GREY))
    return _badge(text, bg, fg)


def _progress_bar(fraction, width, height=7 * mm):
    """A single-row Table rendering a filled/empty progress bar for `fraction` (0-1)."""
    radii = [height / 2] * 4
    if 0 < fraction < 1:
        filled = width * fraction
        table = Table([['', '']], colWidths=[filled, width - filled], rowHeights=[height])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), BLUE),
            ('BACKGROUND', (1, 0), (1, 0), BAR_TRACK),
            ('ROUNDEDCORNERS', radii),
        ]))
        return table

    table = Table([['']], colWidths=[width], rowHeights=[height])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), BLUE if fraction >= 1 else BAR_TRACK),
        ('ROUNDEDCORNERS', radii),
    ]))
    return table


def _stat_block(value, label):
    """A list of flowables (not a nested Table of rows) — this file's cards
    already learned the hard way that a nested single-column Table can
    under-measure a wrapped/stacked cell's height and overlap the next
    flowable (see the student-name fix); a plain list in the parent cell
    doesn't have that problem."""
    big_style = ParagraphStyle('StatValue', fontName='Helvetica-Bold', fontSize=15, textColor=BLUE, alignment=1, spaceAfter=4)
    label_style = ParagraphStyle('StatLabel', fontName='Helvetica', fontSize=9, textColor=TEXT_GREY, alignment=1)
    return [Paragraph(str(value), big_style), Paragraph(label, label_style)]


def _section_heading(text):
    """A bold title with a short accent underline — gives standalone (not
    card-wrapped) sections like Detailed History the same designed feel as
    the cards above them, instead of a bare heading floating on the page."""
    style = ParagraphStyle('SectionTitle', fontName='Helvetica-Bold', fontSize=13, textColor=TEXT_DARK, spaceAfter=3)
    underline = Table([['']], colWidths=[18 * mm], rowHeights=[1.2 * mm])
    underline.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, 0), BLUE), ('ROUNDEDCORNERS', [1, 1, 1, 1])]))
    return [Paragraph(text, style), underline]


def _history_table(records):
    """Detailed History as a single grid — # / Date / Topic — with a light
    app-matching header and alternating row tints so a long list stays easy
    to scan without turning into a wall of identical white rows."""
    head_style = ParagraphStyle('HistoryHead', fontName='Helvetica-Bold', fontSize=9.5, textColor=TABLE_HEAD_TEXT, alignment=1)
    topic_head_style = ParagraphStyle('HistoryHeadLeft', fontName='Helvetica-Bold', fontSize=9.5, textColor=TABLE_HEAD_TEXT)
    topic_style = ParagraphStyle('Topic', fontName='Helvetica', fontSize=11, textColor=TABLE_BODY_TEXT, leading=14.5)
    num_style = ParagraphStyle('HistoryNum', fontName='Helvetica', fontSize=11, textColor=TABLE_BODY_TEXT, alignment=1)
    date_style = ParagraphStyle('HistoryDate', fontName='Helvetica-Bold', fontSize=11, textColor=TEXT_DARK, alignment=1)

    rows = [[Paragraph('#', head_style), Paragraph('DATE', head_style), Paragraph('TOPIC', topic_head_style)]]
    for i, a in enumerate(records, start=1):
        rows.append([
            Paragraph(str(i), num_style),
            Paragraph(f'{a.date:%b %d}', date_style),
            Paragraph(escape(a.topic_covered) or '-', topic_style),
        ])
    if len(rows) == 1:
        rows.append([Paragraph('-', num_style), Paragraph('-', date_style), Paragraph('No classes taken yet.', topic_style)])

    table = Table(rows, colWidths=[12 * mm, 24 * mm, CONTENT_WIDTH - 36 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEAD_BG),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, TABLE_STRIPE_BG]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -2), 0.6, TABLE_ROW_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.75, BORDER),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    return table


def _last_n_months(n, anchor):
    """The n calendar months ending with `anchor`'s month, oldest first."""
    months = []
    y, m = anchor.year, anchor.month
    for _ in range(n):
        months.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(months))


def _monthly_bar_chart(labels, values, width, height=32 * mm):
    """A hand-drawn bar chart (Drawing of Rects/Strings) rather than
    reportlab's chart package — matches the hairline-rounded bar look used
    everywhere else in this file (_progress_bar) and keeps full control over
    the zero-value "sliver" bar and value/label placement."""
    d = Drawing(width, height)
    n = len(values)
    if n == 0:
        return d
    max_val = max(values) or 1
    gap = 6 * mm
    bar_w = (width - gap * (n - 1)) / n
    label_h = 10
    value_h = 12
    chart_h = height - label_h - value_h
    for i, (label, val) in enumerate(zip(labels, values)):
        x = i * (bar_w + gap)
        if val > 0:
            bar_h = max((val / max_val) * chart_h, 3)
            radius = min(2.5, bar_w / 2)
            d.add(Rect(x, label_h, bar_w, bar_h, fillColor=BLUE, strokeColor=None, rx=radius, ry=radius))
            d.add(String(
                x + bar_w / 2, label_h + bar_h + 3, str(val),
                fontName='Helvetica-Bold', fontSize=8, fillColor=TEXT_DARK, textAnchor='middle',
            ))
        else:
            d.add(Rect(x, label_h, bar_w, 1.2, fillColor=BAR_TRACK, strokeColor=None))
        d.add(String(
            x + bar_w / 2, 0, label,
            fontName='Helvetica', fontSize=8, fillColor=TEXT_GREY, textAnchor='middle',
        ))
    return d


def render_student_report_pdf(enrollment):
    """Render a progress report for one student's enrollment/batch and return raw PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
    )
    elements = []

    student = enrollment.student
    course = enrollment.course
    display_name = _display_name(student)
    branding_client = _branding_client(student)
    logo = _logo_flowable(branding_client)
    tagline = branding_client.tagline if branding_client else ''
    today = date.today()

    # Header — company/client logo+name+tagline left, "STUDENT REPORT" + date
    # right. A single flat row (not a Table nested inside a Table cell) —
    # nesting a wrapped multi-line Paragraph inside a nested cell has a known
    # row-height bug in this file (see the student-info card's earlier fix),
    # so this mirrors that card's flat avatar/name/badge row instead.
    company_style = ParagraphStyle('Company', fontName='Helvetica-Bold', fontSize=17, leading=20, textColor=BLUE)
    tagline_style = ParagraphStyle('Tagline', fontName='Helvetica', fontSize=9, textColor=TEXT_GREY, spaceBefore=2)
    report_label_style = ParagraphStyle('ReportLabel', fontName='Helvetica-Bold', fontSize=11, textColor=TEXT_GREY, alignment=2)
    date_style = ParagraphStyle('DateLabel', fontName='Helvetica', fontSize=9, textColor=TEXT_GREY, alignment=2, spaceBefore=2)

    name_block = [Paragraph(escape(display_name), company_style)]
    if tagline:
        name_block.append(Paragraph(escape(tagline), tagline_style))
    right_block = [Paragraph('STUDENT REPORT', report_label_style), Paragraph(f'{today:%B} {today.day}, {today.year}', date_style)]

    right_w = 42 * mm
    if logo:
        logo_w, gap_w = 16 * mm, 4 * mm
        name_w = CONTENT_WIDTH - logo_w - gap_w - right_w
        header_table = Table([[logo, '', name_block, right_block]], colWidths=[logo_w, gap_w, name_w, right_w])
    else:
        name_w = CONTENT_WIDTH - right_w
        header_table = Table([[name_block, right_block]], colWidths=[name_w, right_w])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (-1, 0), (-1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 8 * mm))

    # Student info card — avatar, name + course/batch, status badge.
    avatar_w, gap_w, badge_w = 16 * mm, 4 * mm, 30 * mm
    name_w = INNER_WIDTH - avatar_w - gap_w - badge_w
    name_style = ParagraphStyle('StudentName', fontName='Helvetica-Bold', fontSize=17, textColor=TEXT_DARK, spaceAfter=9)
    course_style = ParagraphStyle('CourseLine', fontName='Helvetica', fontSize=10, textColor=TEXT_GREY)
    name_block = [
        Paragraph(escape(student.name), name_style),
        Paragraph(f'{escape(course.name)} · Batch {enrollment.batch_number}', course_style),
    ]
    letter = (student.name.strip()[:1] or '?').upper()
    info_row = Table(
        [[_avatar(letter, avatar_w), '', name_block, _status_badge(enrollment.status)]],
        colWidths=[avatar_w, gap_w, name_w, badge_w],
    )
    info_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (3, 0), (3, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(_card(info_row))
    elements.append(Spacer(1, 6 * mm))

    # Course progress card.
    total = enrollment.classes_total or 1
    completed = min(enrollment.classes_completed, total)
    remaining = max(enrollment.classes_total - completed, 0)
    fraction = completed / total

    heading_style = ParagraphStyle('CardHeading', fontName='Helvetica-Bold', fontSize=12.5, textColor=TEXT_DARK)
    pct_style = ParagraphStyle('PctLabel', fontName='Helvetica-Bold', fontSize=14, textColor=BLUE, alignment=2)
    heading_row = Table(
        [[Paragraph('Course Progress', heading_style), Paragraph(f'{fraction * 100:.1f}%', pct_style)]],
        colWidths=[INNER_WIDTH * 0.5, INNER_WIDTH * 0.5],
    )
    heading_row.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    stat_w = INNER_WIDTH / 3
    stats_row = Table(
        [[
            _stat_block(completed, 'Completed'),
            _stat_block(remaining, 'Remaining'),
            _stat_block(enrollment.classes_total, 'Total'),
        ]],
        colWidths=[stat_w, stat_w, stat_w],
    )
    stats_row.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    progress_card = [
        heading_row, Spacer(1, 4 * mm),
        _progress_bar(fraction, INNER_WIDTH), Spacer(1, 6 * mm),
        stats_row,
    ]
    elements.append(_card(progress_card))
    elements.append(Spacer(1, 6 * mm))

    # Monthly activity card — classes taken per month, last 6 months.
    all_present = list(enrollment.attendance_records.filter(status='present').order_by('-date'))
    month_keys = _last_n_months(6, today)
    counts = {key: 0 for key in month_keys}
    for a in all_present:
        key = (a.date.year, a.date.month)
        if key in counts:
            counts[key] += 1
    month_labels = [date(y, m, 1).strftime('%b') for (y, m) in month_keys]
    month_values = [counts[key] for key in month_keys]

    activity_card = [
        Paragraph('Monthly Activity (Classes)', heading_style), Spacer(1, 6 * mm),
        _monthly_bar_chart(month_labels, month_values, INNER_WIDTH),
    ]
    elements.append(_card(activity_card))
    elements.append(Spacer(1, 9 * mm))

    # Detailed history — most recent class first.
    elements.extend(_section_heading('Detailed History'))
    elements.append(Spacer(1, 5 * mm))
    elements.append(_history_table(all_present))

    doc.build(elements, onFirstPage=_draw_background, onLaterPages=_draw_background)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
