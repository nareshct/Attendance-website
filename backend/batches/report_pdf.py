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

# Same visual design as enrollments/report_pdf.py (1:1 course reports) — kept as a
# parallel copy rather than a shared import because the underlying data shapes
# differ: a batch has one shared session log for every enrolled student (see
# BatchSession's docstring), not per-student attendance, so "Detailed History"
# here carries a Conducted By column and is identical for every student in the
# batch, unlike the 1:1 version's per-student class list.
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


def _display_name(student):
    """B2B students train under their client's brand, not ours — swap the
    issuing name to the client's company name. B2C students (or a B2B
    student whose client link is somehow missing) fall back to our own."""
    if student.source_type == 'B2B' and student.client_id:
        return student.client.company_name
    return COMPANY_NAME


def _branding_client(student):
    """The Client whose logo/tagline should brand this student's report —
    same B2B-with-a-linked-client condition as _display_name."""
    if student.source_type == 'B2B' and student.client_id:
        return student.client
    return None


def _logo_flowable(client, max_height=12 * mm, max_width=42 * mm):
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


def _status_badge_for(batch_enrollment):
    """Batches have no per-student 'completed' state (see BatchEnrollment.
    STATUS_CHOICES) — completion is a property of the whole Batch, so the
    badge combines both: withdrawn always wins, then the batch's own status,
    else the student is simply active in an ongoing batch."""
    if batch_enrollment.status == 'withdrawn':
        return _badge('WITHDRAWN', GREY_BG, TEXT_GREY)
    if batch_enrollment.batch.status == 'completed':
        return _badge('COMPLETED', BLUE_LIGHT, BLUE)
    return _badge('ACTIVE', GREEN_BG, GREEN_TEXT)


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


def _progress_bar(fraction, width, height=7 * mm):
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
    style = ParagraphStyle('SectionTitle', fontName='Helvetica-Bold', fontSize=13, textColor=TEXT_DARK, spaceAfter=3)
    underline = Table([['']], colWidths=[18 * mm], rowHeights=[1.2 * mm])
    underline.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, 0), BLUE), ('ROUNDEDCORNERS', [1, 1, 1, 1])]))
    return [Paragraph(text, style), underline]


def _history_table(sessions):
    """Detailed History as a single grid — # / Date / Topic / Conducted By.
    Shared across every student in the batch (see BatchSession's docstring:
    no per-student attendance is recorded), so this table is identical
    regardless of which student's report it's printed on."""
    head_style = ParagraphStyle('HistoryHead', fontName='Helvetica-Bold', fontSize=9.5, textColor=TABLE_HEAD_TEXT, alignment=1)
    topic_head_style = ParagraphStyle('HistoryHeadLeft', fontName='Helvetica-Bold', fontSize=9.5, textColor=TABLE_HEAD_TEXT)
    topic_style = ParagraphStyle('Topic', fontName='Helvetica', fontSize=11, textColor=TABLE_BODY_TEXT, leading=14.5)
    num_style = ParagraphStyle('HistoryNum', fontName='Helvetica', fontSize=11, textColor=TABLE_BODY_TEXT, alignment=1)
    date_style = ParagraphStyle('HistoryDate', fontName='Helvetica-Bold', fontSize=11, textColor=TEXT_DARK, alignment=1)
    by_style = ParagraphStyle('HistoryBy', fontName='Helvetica', fontSize=10, textColor=TEXT_GREY)

    rows = [[
        Paragraph('#', head_style), Paragraph('DATE', head_style),
        Paragraph('TOPIC', topic_head_style), Paragraph('CONDUCTED BY', topic_head_style),
    ]]
    for i, s in enumerate(sessions, start=1):
        rows.append([
            Paragraph(str(i), num_style),
            Paragraph(f'{s.date:%b %d}', date_style),
            Paragraph(escape(s.topic_covered) or '-', topic_style),
            Paragraph(escape(s.conducted_by_name) or '-', by_style),
        ])
    if len(rows) == 1:
        rows.append([
            Paragraph('-', num_style), Paragraph('-', date_style),
            Paragraph('No sessions logged yet.', topic_style), Paragraph('-', by_style),
        ])

    topic_w = CONTENT_WIDTH - 12 * mm - 24 * mm - 34 * mm
    table = Table(rows, colWidths=[12 * mm, 24 * mm, topic_w, 34 * mm], repeatRows=1)
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
    months = []
    y, m = anchor.year, anchor.month
    for _ in range(n):
        months.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(months))


def _monthly_bar_chart(labels, values, width, height=32 * mm):
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


def render_batch_student_report_pdf(batch_enrollment):
    """Render a progress report for one student's membership in a Batch and
    return raw PDF bytes. Progress/Monthly Activity/Detailed History are all
    the batch's own shared session log (see BatchSession) — not a per-student
    attendance record, since batches don't track attendance individually."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
    )
    elements = []

    student = batch_enrollment.student
    batch = batch_enrollment.batch
    display_name = _display_name(student)
    branding_client = _branding_client(student)
    logo = _logo_flowable(branding_client)
    tagline = branding_client.tagline if branding_client else ''
    today = date.today()

    # A single flat row (not a Table nested inside a Table cell) — nesting a
    # wrapped multi-line Paragraph inside a nested cell has a known
    # row-height bug in this file (see the student-info card below), so this
    # mirrors that card's flat avatar/name/badge row instead.
    company_style = ParagraphStyle('Company', fontName='Helvetica-Bold', fontSize=17, leading=20, textColor=BLUE)
    tagline_style = ParagraphStyle('Tagline', fontName='Helvetica', fontSize=9, textColor=TEXT_GREY, spaceBefore=2)
    report_label_style = ParagraphStyle('ReportLabel', fontName='Helvetica-Bold', fontSize=11, textColor=TEXT_GREY, alignment=2)
    date_style = ParagraphStyle('DateLabel', fontName='Helvetica', fontSize=9, textColor=TEXT_GREY, alignment=2, spaceBefore=2)

    header_name_block = [Paragraph(escape(display_name), company_style)]
    if tagline:
        header_name_block.append(Paragraph(escape(tagline), tagline_style))
    header_right_block = [Paragraph('STUDENT REPORT', report_label_style), Paragraph(f'{today:%B} {today.day}, {today.year}', date_style)]

    header_right_w = 42 * mm
    if logo:
        header_logo_w, header_gap_w = 16 * mm, 4 * mm
        header_name_w = CONTENT_WIDTH - header_logo_w - header_gap_w - header_right_w
        header_table = Table(
            [[logo, '', header_name_block, header_right_block]],
            colWidths=[header_logo_w, header_gap_w, header_name_w, header_right_w],
        )
    else:
        header_name_w = CONTENT_WIDTH - header_right_w
        header_table = Table([[header_name_block, header_right_block]], colWidths=[header_name_w, header_right_w])
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
        Paragraph(f'{escape(batch.course.name)} · {escape(batch.name)}', course_style),
    ]
    letter = (student.name.strip()[:1] or '?').upper()
    info_row = Table(
        [[_avatar(letter, avatar_w), '', name_block, _status_badge_for(batch_enrollment)]],
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

    # Course progress card — the batch's own session count vs its total, shared
    # by every enrolled student (there's no per-student class count to show).
    all_sessions = list(batch.sessions.order_by('-date'))
    total = batch.total_classes or 1
    completed = min(len(all_sessions), total)
    remaining = max(batch.total_classes - completed, 0)
    fraction = completed / total

    heading_style = ParagraphStyle('CardHeading', fontName='Helvetica-Bold', fontSize=12.5, textColor=TEXT_DARK)
    pct_style = ParagraphStyle('PctLabel', fontName='Helvetica-Bold', fontSize=14, textColor=BLUE, alignment=2)
    heading_row = Table(
        [[Paragraph('Batch Progress', heading_style), Paragraph(f'{fraction * 100:.1f}%', pct_style)]],
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
            _stat_block(batch.total_classes, 'Total'),
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

    # Monthly activity card — sessions held per month, last 6 months.
    month_keys = _last_n_months(6, today)
    counts = {key: 0 for key in month_keys}
    for s in all_sessions:
        key = (s.date.year, s.date.month)
        if key in counts:
            counts[key] += 1
    month_labels = [date(y, m, 1).strftime('%b') for (y, m) in month_keys]
    month_values = [counts[key] for key in month_keys]

    activity_card = [
        Paragraph('Monthly Activity (Sessions)', heading_style), Spacer(1, 6 * mm),
        _monthly_bar_chart(month_labels, month_values, INNER_WIDTH),
    ]
    elements.append(_card(activity_card))
    elements.append(Spacer(1, 9 * mm))

    # Detailed history — most recent session first.
    elements.extend(_section_heading('Detailed History'))
    elements.append(Spacer(1, 5 * mm))
    elements.append(_history_table(all_sessions))

    doc.build(elements, onFirstPage=_draw_background, onLaterPages=_draw_background)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
