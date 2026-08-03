import io
from decimal import Decimal
from xml.sax.saxutils import escape

from django.db.models import Sum
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from clients.services import client_course_breakdown

from .models import ClientInvoiceAdjustment

NAVY = colors.HexColor('#1e3a5f')
GREY = colors.HexColor('#666666')
LIGHT_GREY = colors.HexColor('#f3f4f6')
LINE = colors.HexColor('#dddddd')


def render_invoice_pdf(invoice):
    """Render a ClientInvoice as a one-page PDF and return the raw bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph('INVOICE', styles['Title']))
    elements.append(Spacer(1, 6 * mm))

    status_label = 'Overdue' if invoice.is_overdue else invoice.get_status_display()
    meta_rows = [
        ['Invoice #', f'INV-{invoice.id:05d}'],
        ['Billing period', f'{invoice.cycle.cycle_start} to {invoice.cycle.cycle_end}'],
        ['Due date', str(invoice.due_date)],
        ['Status', status_label],
    ]
    meta_table = Table(meta_rows, colWidths=[40 * mm, 100 * mm])
    meta_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), GREY),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 8 * mm))

    elements.append(Paragraph('Bill to', styles['Heading3']))
    elements.append(Paragraph(escape(invoice.client.company_name), styles['Normal']))
    if invoice.client.contact_phone:
        elements.append(Paragraph(escape(invoice.client.contact_phone), styles['Normal']))
    if invoice.client.contact_email:
        elements.append(Paragraph(escape(invoice.client.contact_email), styles['Normal']))
    elements.append(Spacer(1, 8 * mm))

    adjustments = ClientInvoiceAdjustment.objects.filter(
        client=invoice.client, applied_cycle=invoice.cycle,
    ).select_related('attendance__enrollment__student').order_by('attendance__date')
    carried_forward_total = adjustments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    breakdown = client_course_breakdown(invoice.client, invoice.cycle.cycle_start, invoice.cycle.cycle_end)
    breakdown_total = sum((row['amount'] for row in breakdown), Decimal('0.00'))

    line_items = [['Description', 'Classes', 'Rate/class', 'Amount']]
    if breakdown and breakdown_total + carried_forward_total == invoice.total_amount:
        # Itemized per-course lines — only shown when they reconcile exactly with the
        # invoice's frozen total (they use today's rates, which could in principle
        # have changed since this invoice closed). Falls back to a single blended-
        # average line below if they don't, so the PDF is never internally inconsistent.
        for row in breakdown:
            line_items.append([
                f"{row['course_name']} ({invoice.cycle.cycle_start} to {invoice.cycle.cycle_end})",
                str(row['classes']),
                f"Rs. {row['rate_per_class']:.2f}",
                f"Rs. {row['amount']}",
            ])
    else:
        non_adjustment_classes = invoice.total_classes - adjustments.count()
        non_adjustment_amount = invoice.total_amount - carried_forward_total
        avg_rate = (non_adjustment_amount / non_adjustment_classes) if non_adjustment_classes else 0
        line_items.append([
            f'Classes attended ({invoice.cycle.cycle_start} to {invoice.cycle.cycle_end})',
            str(non_adjustment_classes),
            f'Rs. {avg_rate:.2f}',
            f'Rs. {non_adjustment_amount}',
        ])
    items_table = Table(line_items, colWidths=[85 * mm, 25 * mm, 30 * mm, 30 * mm])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, LINE),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 4 * mm))

    if adjustments.exists():
        elements.append(Paragraph('Includes carried-forward classes', styles['Heading3']))
        elements.append(Spacer(1, 2 * mm))
        adjustment_rows = [['Date', 'Student', 'Topic']]
        for adj in adjustments:
            adjustment_rows.append([
                str(adj.attendance.date),
                adj.attendance.enrollment.student.name,
                adj.attendance.topic_covered or '-',
            ])
        adjustments_table = Table(adjustment_rows, colWidths=[30 * mm, 55 * mm, 85 * mm])
        adjustments_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), LIGHT_GREY),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, LINE),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(adjustments_table)
        elements.append(Spacer(1, 4 * mm))

    total_table = Table([['Total due', f'Rs. {invoice.total_amount}']], colWidths=[140 * mm, 30 * mm])
    total_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    elements.append(total_table)

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
