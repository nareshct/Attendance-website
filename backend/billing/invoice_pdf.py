import io
from decimal import Decimal
from xml.sax.saxutils import escape

from django.db.models import Sum
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from clients.services import client_course_breakdown

from .models import ClientInvoiceAdjustment

# Same card-based visual language as enrollments/report_pdf.py (blue "operational
# document" theme, as opposed to the ceremonial gold certificate) — a parallel
# copy rather than a shared import, same reasoning as batches/report_pdf.py.
COMPANY_NAME = 'Apex Binary'

PAGE_BG = colors.HexColor('#eef1f6')
CARD_BG = colors.white
TEXT_DARK = colors.HexColor('#111827')
TEXT_GREY = colors.HexColor('#6b7280')
BLUE = colors.HexColor('#2563eb')
BLUE_LIGHT = colors.HexColor('#dbeafe')
GREEN_BG = colors.HexColor('#dcfce7')
GREEN_TEXT = colors.HexColor('#16a34a')
RED_BG = colors.HexColor('#fee2e2')
RED_TEXT = colors.HexColor('#dc2626')
AMBER_BG = colors.HexColor('#fef3c7')
AMBER_TEXT = colors.HexColor('#b45309')
BORDER = colors.HexColor('#e5e7eb')
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


def _badge(text, bg, fg, width=32 * mm):
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


def _status_badge(invoice):
    if invoice.status == 'received':
        return _badge('RECEIVED', GREEN_BG, GREEN_TEXT)
    if invoice.is_overdue:
        return _badge('OVERDUE', RED_BG, RED_TEXT)
    return _badge('PENDING', AMBER_BG, AMBER_TEXT)


def _section_heading(text):
    style = ParagraphStyle('SectionTitle', fontName='Helvetica-Bold', fontSize=13, textColor=TEXT_DARK, spaceAfter=3)
    underline = Table([['']], colWidths=[18 * mm], rowHeights=[1.2 * mm])
    underline.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, 0), BLUE), ('ROUNDEDCORNERS', [1, 1, 1, 1])]))
    return [Paragraph(text, style), underline]


def _meta_block(label, value, width):
    label_style = ParagraphStyle('MetaLabel', fontName='Helvetica', fontSize=8.5, textColor=TEXT_GREY)
    value_style = ParagraphStyle('MetaValue', fontName='Helvetica-Bold', fontSize=11, textColor=TEXT_DARK, spaceBefore=1.5)
    table = Table([[Paragraph(label, label_style)], [Paragraph(value, value_style)]], colWidths=[width])
    table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return table


def _grid_table(header_labels, rows, col_widths, right_align_from=1):
    """Shared app-matching grid: light slate uppercase header, zebra-striped
    body rows, hairline dividers, rounded card border — same look as the
    Detailed History table on the student report."""
    head_style = ParagraphStyle('GridHead', fontName='Helvetica-Bold', fontSize=8.5, textColor=TABLE_HEAD_TEXT)
    head_style_right = ParagraphStyle('GridHeadRight', parent=head_style, alignment=2)
    body_style = ParagraphStyle('GridBody', fontName='Helvetica', fontSize=9.5, textColor=TABLE_BODY_TEXT, leading=13)
    body_style_right = ParagraphStyle('GridBodyRight', parent=body_style, alignment=2)

    header_row = [
        Paragraph(label, head_style_right if i >= right_align_from else head_style)
        for i, label in enumerate(header_labels)
    ]
    data = [header_row]
    for row in rows:
        data.append([
            Paragraph(escape(str(cell)), body_style_right if i >= right_align_from else body_style)
            for i, cell in enumerate(row)
        ])

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEAD_BG),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, TABLE_STRIPE_BG]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -2), 0.6, TABLE_ROW_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 6.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.75, BORDER),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    return table


def render_invoice_pdf(invoice):
    """Render a ClientInvoice as a one-page (or more, if adjustments run
    long) PDF and return the raw bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
    )
    elements = []
    client = invoice.client

    # Header — issuer name left, "INVOICE" + invoice number right. Always our
    # own name here (never client-branded like the student report/certificate)
    # — a client can't be billed under its own letterhead.
    company_style = ParagraphStyle('Company', fontName='Helvetica-Bold', fontSize=20, textColor=BLUE)
    doc_label_style = ParagraphStyle('DocLabel', fontName='Helvetica-Bold', fontSize=11, textColor=TEXT_GREY, alignment=2)
    doc_number_style = ParagraphStyle('DocNumber', fontName='Helvetica-Bold', fontSize=13, textColor=TEXT_DARK, alignment=2, spaceBefore=2)
    header_table = Table(
        [[
            Paragraph(COMPANY_NAME, company_style),
            [Paragraph('INVOICE', doc_label_style), Paragraph(f'INV-{invoice.id:05d}', doc_number_style)],
        ]],
        colWidths=[CONTENT_WIDTH * 0.6, CONTENT_WIDTH * 0.4],
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 8 * mm))

    # Bill-to card — client details + status badge, then a meta strip
    # (billing period / due date / classes billed).
    bill_to_label_style = ParagraphStyle('BillToLabel', fontName='Helvetica', fontSize=8.5, textColor=TEXT_GREY, spaceAfter=3)
    client_name_style = ParagraphStyle('ClientName', fontName='Helvetica-Bold', fontSize=15, textColor=TEXT_DARK, spaceAfter=8)
    contact_style = ParagraphStyle('Contact', fontName='Helvetica', fontSize=9.5, textColor=TEXT_GREY)

    bill_to_block = [Paragraph('BILL TO', bill_to_label_style), Paragraph(escape(client.company_name), client_name_style)]
    contact_bits = [escape(v) for v in (client.contact_phone, client.contact_email) if v]
    if contact_bits:
        bill_to_block.append(Paragraph(' &nbsp;·&nbsp; '.join(contact_bits), contact_style))

    bill_to_row = Table(
        [[bill_to_block, _status_badge(invoice)]],
        colWidths=[INNER_WIDTH - 32 * mm, 32 * mm],
    )
    bill_to_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    meta_w = INNER_WIDTH / 3
    meta_row = Table(
        [[
            _meta_block('BILLING PERIOD', f'{invoice.cycle.cycle_start:%d %b} – {invoice.cycle.cycle_end:%d %b %Y}', meta_w),
            _meta_block('DUE DATE', f'{invoice.due_date:%d %b %Y}', meta_w),
            _meta_block('CLASSES BILLED', str(invoice.total_classes), meta_w),
        ]],
        colWidths=[meta_w, meta_w, meta_w],
    )
    meta_row.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    elements.append(_card([bill_to_row, Spacer(1, 6 * mm), meta_row]))
    elements.append(Spacer(1, 9 * mm))

    # Line items.
    adjustments = ClientInvoiceAdjustment.objects.filter(
        client=client, applied_cycle=invoice.cycle,
    ).select_related('attendance__enrollment__student').order_by('attendance__date')
    carried_forward_total = adjustments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    breakdown = client_course_breakdown(client, invoice.cycle.cycle_start, invoice.cycle.cycle_end)
    breakdown_total = sum((row['amount'] for row in breakdown), Decimal('0.00'))

    item_rows = []
    if breakdown and breakdown_total + carried_forward_total == invoice.total_amount:
        # Itemized per-course lines — only shown when they reconcile exactly with the
        # invoice's frozen total (they use today's rates, which could in principle
        # have changed since this invoice closed). Falls back to a single blended-
        # average line below if they don't, so the PDF is never internally inconsistent.
        for row in breakdown:
            item_rows.append([
                f"{row['course_name']} ({invoice.cycle.cycle_start:%d %b} to {invoice.cycle.cycle_end:%d %b})",
                row['classes'], f"Rs. {row['rate_per_class']:.2f}", f"Rs. {row['amount']}",
            ])
    else:
        non_adjustment_classes = invoice.total_classes - adjustments.count()
        non_adjustment_amount = invoice.total_amount - carried_forward_total
        avg_rate = (non_adjustment_amount / non_adjustment_classes) if non_adjustment_classes else 0
        item_rows.append([
            f'Classes attended ({invoice.cycle.cycle_start:%d %b} to {invoice.cycle.cycle_end:%d %b})',
            non_adjustment_classes, f'Rs. {avg_rate:.2f}', f'Rs. {non_adjustment_amount}',
        ])

    elements.extend(_section_heading('Line Items'))
    elements.append(Spacer(1, 5 * mm))
    elements.append(_grid_table(
        ['DESCRIPTION', 'CLASSES', 'RATE/CLASS', 'AMOUNT'], item_rows,
        col_widths=[CONTENT_WIDTH - 25 * mm - 30 * mm - 30 * mm, 25 * mm, 30 * mm, 30 * mm],
        right_align_from=1,
    ))
    elements.append(Spacer(1, 9 * mm))

    # Carried-forward adjustments, if any.
    if adjustments.exists():
        elements.extend(_section_heading('Includes Carried-Forward Classes'))
        elements.append(Spacer(1, 5 * mm))
        adjustment_rows = [
            [f'{adj.attendance.date:%d %b %Y}', adj.attendance.enrollment.student.name, adj.attendance.topic_covered or '-']
            for adj in adjustments
        ]
        elements.append(_grid_table(
            ['DATE', 'STUDENT', 'TOPIC'], adjustment_rows,
            col_widths=[28 * mm, 45 * mm, CONTENT_WIDTH - 73 * mm],
            right_align_from=3,
        ))
        elements.append(Spacer(1, 9 * mm))

    # Total due.
    total_label_style = ParagraphStyle('TotalLabel', fontName='Helvetica-Bold', fontSize=12.5, textColor=TEXT_DARK, alignment=2)
    total_amount_style = ParagraphStyle('TotalAmount', fontName='Helvetica-Bold', fontSize=20, textColor=BLUE, alignment=2)
    total_row = Table(
        [[Paragraph('Total Due', total_label_style), Paragraph(f'Rs. {invoice.total_amount}', total_amount_style)]],
        colWidths=[INNER_WIDTH * 0.5, INNER_WIDTH * 0.5],
    )
    total_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(_card(total_row))
    elements.append(Spacer(1, 8 * mm))

    footer_style = ParagraphStyle('Footer', fontName='Helvetica', fontSize=9, textColor=TEXT_GREY)
    elements.append(Paragraph(
        f'Payment due within {invoice.OVERDUE_GRACE_DAYS} days of the billing period ending. '
        'Thank you for your business.',
        footer_style,
    ))

    doc.build(elements, onFirstPage=_draw_background, onLaterPages=_draw_background)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
