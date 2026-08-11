import csv
from datetime import datetime

from django.db.models import Max
from django.http import HttpResponse
from rest_framework.views import APIView

from attendance.models import Attendance
from billing.models import Payout
from clients.models import Client
from config.permissions import IsAdmin
from enrollments.models import Enrollment


def csv_response(filename):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def bad_request(detail):
    return HttpResponse(detail, status=400, content_type='text/plain')


def valid_id(value):
    """A query-param value destined for a `.filter(<field>_id=value)` lookup — must be
    empty/absent or digits only, otherwise Django raises an unhandled ValueError when
    the queryset is evaluated (these are plain APIViews, so DRF's exception handler
    never sees it — it would 500 instead of a clean 400)."""
    return value is None or value.isdigit()


def valid_date(value):
    """Same reasoning as valid_id() but for a `date__gte`/`date__lte` filter — an
    unparseable string raises an unhandled ValidationError from the DB layer."""
    if value is None:
        return True
    try:
        datetime.strptime(value, '%Y-%m-%d')
        return True
    except ValueError:
        return False


# A cell starting with =, +, -, or @ is executed as a formula by Excel/Sheets/LibreOffice
# when the CSV is opened — topic_covered is free text a trainer types per class, so
# nothing stops it from starting with one of those, whether by accident (e.g. "-5 min
# review") or a deliberately crafted formula. Prefixing a leading apostrophe forces
# spreadsheet apps to treat the cell as literal text instead of a formula, without
# changing what a human reading the CSV sees.
def csv_safe(value):
    text = str(value)
    if text and text[0] in ('=', '+', '-', '@'):
        return f"'{text}"
    return text


class PayoutsReportView(APIView):
    """GET /api/reports/payouts/?trainer=&cycle= — CSV of payouts, optionally filtered."""

    permission_classes = [IsAdmin]

    def get(self, request):
        qs = Payout.objects.select_related('trainer', 'cycle').order_by('-cycle__cycle_start', 'trainer__name')
        trainer_id = request.query_params.get('trainer')
        cycle_id = request.query_params.get('cycle')
        if not valid_id(trainer_id):
            return bad_request('Invalid trainer filter.')
        if not valid_id(cycle_id):
            return bad_request('Invalid cycle filter.')
        if trainer_id:
            qs = qs.filter(trainer_id=trainer_id)
        if cycle_id:
            qs = qs.filter(cycle_id=cycle_id)

        response = csv_response('payouts.csv')
        writer = csv.writer(response)
        writer.writerow([
            'Trainer ID', 'Trainer Name', 'Cycle Start', 'Cycle End',
            'Total Classes', 'Total Amount', 'Paid Status',
        ])
        for p in qs:
            writer.writerow([
                p.trainer.trainer_id, p.trainer.name, p.cycle.cycle_start, p.cycle.cycle_end,
                p.total_classes, p.total_amount, p.paid_status,
            ])
        return response


class ClientReportView(APIView):
    """GET /api/reports/client/{client_id}/ — CSV of a B2B client's students & enrollment progress."""

    permission_classes = [IsAdmin]

    def get(self, request, client_id):
        client = Client.objects.filter(id=client_id).first()
        if client is None:
            return HttpResponse('Client not found.', status=404, content_type='text/plain')

        enrollments = (
            Enrollment.objects.select_related('student', 'course')
            .filter(student__client=client)
            .annotate(last_class_date=Max('attendance_records__date'))
            .order_by('student__name', '-start_date')
        )

        response = csv_response(f'client-{client.company_name}.csv')
        writer = csv.writer(response)
        writer.writerow([
            'Student ID', 'Student Name', 'Course', 'Batch', 'Classes Completed',
            'Classes Total', 'Enrollment Status', 'Start Date', 'Last Class Date',
        ])
        for e in enrollments:
            writer.writerow([
                e.student.student_id, e.student.name,
                e.course.name, e.batch_number, e.classes_completed,
                e.classes_total, e.status, e.start_date, e.last_class_date or '',
            ])
        return response


class ClientAttendanceReportView(APIView):
    """GET /api/reports/client/{client_id}/attendance/?start=&end= — CSV of every
    class taken by a B2B client's students (one row per class, across all their
    students), optionally scoped to a date range (both bounds inclusive)."""

    permission_classes = [IsAdmin]

    def get(self, request, client_id):
        client = Client.objects.filter(id=client_id).first()
        if client is None:
            return HttpResponse('Client not found.', status=404, content_type='text/plain')

        records = (
            Attendance.objects.filter(status='present', enrollment__student__client=client)
            .select_related('enrollment__student', 'enrollment__course')
            .order_by('enrollment__student__name', 'date')
        )

        start = request.query_params.get('start')
        end = request.query_params.get('end')
        if not valid_date(start):
            return bad_request('Invalid start date — use YYYY-MM-DD.')
        if not valid_date(end):
            return bad_request('Invalid end date — use YYYY-MM-DD.')
        if start:
            records = records.filter(date__gte=start)
        if end:
            records = records.filter(date__lte=end)

        filename_suffix = f'-{start or "start"}_to_{end or "now"}' if (start or end) else ''
        response = csv_response(f'client-{client.company_name}-attendance{filename_suffix}.csv')
        writer = csv.writer(response)
        writer.writerow(['Student ID', 'Student Name', 'Course', 'Batch', 'Date', 'Topic Covered'])
        for a in records:
            writer.writerow([
                a.enrollment.student.student_id, a.enrollment.student.name,
                a.enrollment.course.name, a.enrollment.batch_number,
                a.date, csv_safe(a.topic_covered),
            ])
        return response


class AttendanceReportView(APIView):
    """GET /api/reports/attendance/?trainer=&start=&end= — CSV of attendance
    records including trainer info, optionally filtered by trainer and/or a
    date range (both bounds inclusive). Internal/admin use — unlike the
    client/student exports, this one is not meant to be shared externally."""

    permission_classes = [IsAdmin]

    def get(self, request):
        records = (
            Attendance.objects.filter(status='present')
            .select_related('marked_by', 'enrollment__student', 'enrollment__course')
            .order_by('date', 'marked_by__name')
        )

        trainer_id = request.query_params.get('trainer')
        start = request.query_params.get('start')
        end = request.query_params.get('end')
        if not valid_id(trainer_id):
            return bad_request('Invalid trainer filter.')
        if not valid_date(start):
            return bad_request('Invalid start date — use YYYY-MM-DD.')
        if not valid_date(end):
            return bad_request('Invalid end date — use YYYY-MM-DD.')
        if trainer_id:
            records = records.filter(marked_by_id=trainer_id)
        if start:
            records = records.filter(date__gte=start)
        if end:
            records = records.filter(date__lte=end)

        filename_suffix = f'-{start or "start"}_to_{end or "now"}' if (start or end) else ''
        response = csv_response(f'attendance{filename_suffix}.csv')
        writer = csv.writer(response)
        writer.writerow([
            'Date', 'Trainer ID', 'Trainer Name', 'Student ID', 'Student Name',
            'Course', 'Batch', 'Topic Covered',
        ])
        for a in records:
            writer.writerow([
                a.date, a.marked_by.trainer_id, a.marked_by.name,
                a.enrollment.student.student_id, a.enrollment.student.name,
                a.enrollment.course.name, a.enrollment.batch_number, csv_safe(a.topic_covered),
            ])
        return response
