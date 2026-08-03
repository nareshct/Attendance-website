import datetime
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from billing.models import BillingCycle, ClientInvoice, Payout
from courses.models import Course
from students.models import Student
from trainers.models import Trainer

from .models import Batch, BatchEnrollment, BatchInstallment, BatchPayout, BatchSession
from .services import all_batches_summary, batch_revenue_summary, create_batch_installments, source_report
from .views import (
    BatchEnrollmentViewSet,
    BatchInstallmentViewSet,
    BatchPayoutViewSet,
    BatchSessionViewSet,
    BatchViewSet,
    MyBatchesView,
)


def _make_batch(payment_type='one_time', fee=Decimal('4000'), total_classes=24, trainer_names=''):
    course = Course.objects.create(name='Scratch Programming', total_classes=24, rate_per_class=Decimal('1000'))
    return Batch.objects.create(
        name='Scratch — July batch', course=course, total_classes=total_classes,
        fee_per_student=fee, payment_type=payment_type, start_date=datetime.date(2026, 7, 1),
        trainer_names=trainer_names,
    )


def _make_student(name='Kid'):
    return Student.objects.create(name=name, grade='5', source_type='B2C')


def _make_trainer(username='trainer', name='Priya'):
    user = get_user_model().objects.create_user(username=username, password='x')
    return Trainer.objects.create(user=user, name=name, phone_number='0000000000', place='Here', default_rate_per_class=Decimal('100'))


class CreateBatchInstallmentsTests(TestCase):
    """Installments must always sum to exactly fee_per_student, and
    due_at_sessions milestones must be resolved from the batch's own
    total_classes, not tied to any per-student attendance."""

    def test_one_time_is_a_single_installment_due_immediately(self):
        batch = _make_batch(payment_type='one_time', fee=Decimal('4000'))
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        installments = create_batch_installments(enrollment)
        self.assertEqual(len(installments), 1)
        self.assertIsNone(installments[0].due_at_sessions)
        self.assertEqual(installments[0].amount, Decimal('4000.00'))

    def test_two_installments_even_split(self):
        batch = _make_batch(payment_type='two_installments', fee=Decimal('4000'), total_classes=24)
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        installments = create_batch_installments(enrollment)
        self.assertEqual(len(installments), 2)
        self.assertIsNone(installments[0].due_at_sessions)
        self.assertEqual(installments[0].amount, Decimal('2000.00'))
        self.assertEqual(installments[1].due_at_sessions, 12)  # 50% of 24 sessions
        self.assertEqual(installments[1].amount, Decimal('2000.00'))
        self.assertEqual(sum(i.amount for i in installments), Decimal('4000.00'))

    def test_three_installments_uneven_split_absorbed_by_last(self):
        batch = _make_batch(payment_type='three_installments', fee=Decimal('1000'), total_classes=24)
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        installments = create_batch_installments(enrollment)
        self.assertEqual(len(installments), 3)
        # 1000 / 3 = 333.33, 333.33, remainder absorbed by last -> 333.34
        self.assertEqual(installments[0].amount, Decimal('333.33'))
        self.assertEqual(installments[1].amount, Decimal('333.33'))
        self.assertEqual(installments[2].amount, Decimal('333.34'))
        self.assertEqual(sum(i.amount for i in installments), Decimal('1000.00'))
        self.assertEqual([i.due_at_sessions for i in installments], [None, 8, 16])  # 34%/67% of 24

    def test_four_installments_milestones(self):
        batch = _make_batch(payment_type='four_installments', fee=Decimal('4000'), total_classes=12)
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        installments = create_batch_installments(enrollment)
        due_dates = [i.due_at_sessions for i in installments]
        self.assertEqual(due_dates, [None, 3, 6, 9])  # 25%/50%/75% of 12
        self.assertEqual(sum(i.amount for i in installments), Decimal('4000.00'))


class BatchRevenueSummaryTests(TestCase):
    """batch_revenue_summary() must reflect real enrollment/payment state, and
    must never touch BillingCycle/Payout/ClientInvoice — this is a separate
    revenue stream from the individual per-class billing system."""

    def test_revenue_reflects_enrolled_count_and_paid_status(self):
        batch = _make_batch(payment_type='two_installments', fee=Decimal('4000'))
        for i in range(3):
            enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(f'Kid {i}'), joined_date=datetime.date(2026, 7, 1))
            create_batch_installments(enrollment)

        summary = batch_revenue_summary(batch)
        self.assertEqual(summary['enrolled_count'], 3)
        self.assertEqual(summary['gross_expected'], Decimal('12000.00'))
        self.assertEqual(summary['collected'], Decimal('0.00'))
        self.assertEqual(summary['pending'], Decimal('12000.00'))

        # Mark one student's first installment paid.
        first_enrollment = BatchEnrollment.objects.filter(batch=batch).first()
        inst = first_enrollment.installments.get(sequence=1)
        inst.paid_status = 'paid'
        inst.save()

        summary = batch_revenue_summary(batch)
        self.assertEqual(summary['collected'], Decimal('2000.00'))
        self.assertEqual(summary['pending'], Decimal('10000.00'))

    def test_net_after_payout_sums_every_payout_regardless_of_paid_status(self):
        batch = _make_batch(payment_type='one_time', fee=Decimal('4000'))
        BatchPayout.objects.create(batch=batch, recipient_name='Trainer 1', amount=Decimal('3000'))
        BatchPayout.objects.create(batch=batch, recipient_name='Trainer 2', amount=Decimal('2000'), paid=True)
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        inst = create_batch_installments(enrollment)[0]
        inst.paid_status = 'paid'
        inst.save()

        summary = batch_revenue_summary(batch)
        self.assertEqual(summary['collected'], Decimal('4000.00'))
        self.assertEqual(summary['total_payouts'], Decimal('5000.00'), 'both payouts count, paid or not')
        self.assertEqual(summary['net_after_payout'], Decimal('-1000.00'))

    def test_withdrawn_students_are_excluded(self):
        batch = _make_batch(payment_type='one_time', fee=Decimal('4000'))
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        create_batch_installments(enrollment)
        enrollment.status = 'withdrawn'
        enrollment.save()

        summary = batch_revenue_summary(batch)
        self.assertEqual(summary['enrolled_count'], 0)
        self.assertEqual(summary['gross_expected'], Decimal('0.00'))

    def test_batches_never_create_billing_cycle_records(self):
        batch = _make_batch(payment_type='two_installments', fee=Decimal('4000'))
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        create_batch_installments(enrollment)
        for inst in enrollment.installments.all():
            inst.paid_status = 'paid'
            inst.save()
        payout = BatchPayout.objects.create(batch=batch, recipient_name='Guest Instructor', amount=Decimal('1000'))
        payout.paid = True
        payout.save()

        self.assertEqual(BillingCycle.objects.count(), 0)
        self.assertEqual(Payout.objects.count(), 0)
        self.assertEqual(ClientInvoice.objects.count(), 0)


class BatchApiTests(APITestCase):
    """End-to-end through the real view layer: create a batch, enroll a
    student, mark payments/payout paid, log a session, withdraw."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='batch_admin', password='x', is_staff=True)
        self.factory = APIRequestFactory()
        self.course = Course.objects.create(name='Robotics', total_classes=24, rate_per_class=Decimal('1000'))

    def _req(self, method, path, data=None):
        request = getattr(self.factory, method)(path, data, format='json')
        force_authenticate(request, user=self.admin)
        return request

    def test_create_batch_enroll_student_and_pay(self):
        request = self._req('post', '/api/batches/', {
            'name': 'Robotics — August batch', 'course': self.course.id, 'total_classes': 24,
            'fee_per_student': '4000', 'payment_type': 'two_installments',
            'start_date': '2026-08-01', 'class_time': '17:00', 'class_days': 'MON,WED',
        })
        response = BatchViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 201, response.data)
        batch_id = response.data['id']

        student = _make_student('Enrolling Kid')
        request2 = self._req('post', '/api/batch-enrollments/', {'batch': batch_id, 'student': student.id})
        response2 = BatchEnrollmentViewSet.as_view({'post': 'create'})(request2)
        self.assertEqual(response2.status_code, 201, response2.data)
        self.assertEqual(len(response2.data['installments']), 2)

        # Duplicate enrollment must be rejected.
        request3 = self._req('post', '/api/batch-enrollments/', {'batch': batch_id, 'student': student.id})
        response3 = BatchEnrollmentViewSet.as_view({'post': 'create'})(request3)
        self.assertEqual(response3.status_code, 400)

        installment_id = response2.data['installments'][0]['id']
        request4 = self._req('post', f'/api/batch-installments/{installment_id}/mark_paid/', {})
        response4 = BatchInstallmentViewSet.as_view({'post': 'mark_paid'})(request4, pk=installment_id)
        self.assertEqual(response4.status_code, 200)
        self.assertEqual(response4.data['paid_status'], 'paid')

        request5 = self._req('get', f'/api/batches/{batch_id}/revenue/')
        response5 = BatchViewSet.as_view({'get': 'revenue'})(request5, pk=batch_id)
        self.assertEqual(response5.data['collected'], Decimal('2000.00'))

    def test_enroll_guest_without_registration(self):
        # A batch can include someone who was never registered as a Student —
        # only their name is required, everything else is optional lead capture.
        batch = _make_batch(payment_type='one_time')
        request = self._req('post', '/api/batch-enrollments/', {
            'batch': batch.id, 'guest_name': 'Walk-in Kid', 'guest_phone_number': '9876543210',
            'guest_source': 'Instagram ad',
        })
        response = BatchEnrollmentViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data['student'])
        self.assertEqual(response.data['student_name'], 'Walk-in Kid')
        self.assertIsNone(response.data['student_id_code'])
        self.assertTrue(response.data['is_guest'])
        self.assertEqual(response.data['guest_phone_number'], '9876543210')
        self.assertEqual(response.data['guest_source'], 'Instagram ad')
        self.assertEqual(len(response.data['installments']), 1)

        enrollment = BatchEnrollment.objects.get(id=response.data['id'])
        self.assertEqual(enrollment.display_name, 'Walk-in Kid')

    def test_enrollment_requires_either_student_or_guest_name(self):
        batch = _make_batch(payment_type='one_time')
        request = self._req('post', '/api/batch-enrollments/', {'batch': batch.id})
        response = BatchEnrollmentViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 400)

    def test_cannot_provide_both_student_and_guest_name(self):
        batch = _make_batch(payment_type='one_time')
        student = _make_student()
        request = self._req('post', '/api/batch-enrollments/', {
            'batch': batch.id, 'student': student.id, 'guest_name': 'Someone Else',
        })
        response = BatchEnrollmentViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 400)

    def test_cannot_double_enroll_same_guest_via_manual_add(self):
        # Manually re-submitting "Add student" for the same guest (e.g. a double-click,
        # or re-adding someone already added) must be rejected the same way the Excel
        # import rejects a repeated row — no unique_together to lean on since student=None.
        batch = _make_batch(payment_type='one_time')
        body = {'batch': batch.id, 'guest_name': 'Dup Kid', 'guest_phone_number': '90000 11111'}

        request1 = self._req('post', '/api/batch-enrollments/', body)
        response1 = BatchEnrollmentViewSet.as_view({'post': 'create'})(request1)
        self.assertEqual(response1.status_code, 201, response1.data)

        request2 = self._req('post', '/api/batch-enrollments/', body)
        response2 = BatchEnrollmentViewSet.as_view({'post': 'create'})(request2)
        self.assertEqual(response2.status_code, 400)
        self.assertEqual(BatchEnrollment.objects.filter(batch=batch, guest_name='Dup Kid').count(), 1)

    def test_guest_without_phone_can_be_added_more_than_once(self):
        # No phone means there's nothing reliable to dedup on — same policy as the import.
        batch = _make_batch(payment_type='one_time')
        body = {'batch': batch.id, 'guest_name': 'No Phone Kid'}

        request1 = self._req('post', '/api/batch-enrollments/', body)
        response1 = BatchEnrollmentViewSet.as_view({'post': 'create'})(request1)
        self.assertEqual(response1.status_code, 201, response1.data)

        request2 = self._req('post', '/api/batch-enrollments/', body)
        response2 = BatchEnrollmentViewSet.as_view({'post': 'create'})(request2)
        self.assertEqual(response2.status_code, 201, response2.data)
        self.assertEqual(BatchEnrollment.objects.filter(batch=batch, guest_name='No Phone Kid').count(), 2)

    def test_withdraw_cancels_pending_installments(self):
        batch = _make_batch(payment_type='two_installments')
        student = _make_student()
        enrollment = BatchEnrollment.objects.create(batch=batch, student=student, joined_date=datetime.date(2026, 7, 1))
        create_batch_installments(enrollment)

        request = self._req('post', f'/api/batch-enrollments/{enrollment.id}/withdraw/', {})
        response = BatchEnrollmentViewSet.as_view({'post': 'withdraw'})(request, pk=enrollment.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'withdrawn')
        statuses = set(BatchInstallment.objects.filter(batch_enrollment=enrollment).values_list('paid_status', flat=True))
        self.assertEqual(statuses, {'cancelled'})

    def test_session_log(self):
        batch = _make_batch(payment_type='one_time')

        request = self._req('post', '/api/batch-sessions/', {
            'batch': batch.id, 'date': '2026-07-05', 'conducted_by_name': 'Priya (co-founder)',
            'topic_covered': 'Intro to blocks', 'recording_link': 'https://drive.google.com/xyz',
        })
        response = BatchSessionViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(BatchSession.objects.filter(batch=batch).count(), 1)

    def test_batch_can_have_a_separate_payout_per_person(self):
        # The scenario this replaced: a batch co-taught by two trainers needs an
        # independent payout entry for each, not one shared lump sum.
        batch = _make_batch(payment_type='one_time')

        request1 = self._req('post', '/api/batch-payouts/', {
            'batch': batch.id, 'recipient_name': 'Trainer 1', 'amount': '3000',
        })
        response1 = BatchPayoutViewSet.as_view({'post': 'create'})(request1)
        self.assertEqual(response1.status_code, 201, response1.data)

        request2 = self._req('post', '/api/batch-payouts/', {
            'batch': batch.id, 'recipient_name': 'Trainer 2', 'amount': '2000',
        })
        response2 = BatchPayoutViewSet.as_view({'post': 'create'})(request2)
        self.assertEqual(response2.status_code, 201, response2.data)

        payout1_id = response1.data['id']
        mark_request = self._req('post', f'/api/batch-payouts/{payout1_id}/mark_paid/', {})
        mark_response = BatchPayoutViewSet.as_view({'post': 'mark_paid'})(mark_request, pk=payout1_id)
        self.assertEqual(mark_response.status_code, 200)
        self.assertTrue(mark_response.data['paid'])

        # Trainer 2's payout is untouched by marking Trainer 1's paid.
        payout2_id = response2.data['id']
        get_request = self._req('get', f'/api/batch-payouts/?batch={batch.id}')
        list_response = BatchPayoutViewSet.as_view({'get': 'list'})(get_request)
        by_id = {p['id']: p for p in list_response.data['results']}
        self.assertTrue(by_id[payout1_id]['paid'])
        self.assertFalse(by_id[payout2_id]['paid'])

    def test_batch_can_have_any_number_of_free_text_trainer_names(self):
        # No cap, and not restricted to the registered Trainer table — "any buddy" can
        # be listed, split schedules or larger co-teaching groups are both allowed.
        names = ['Priya (co-founder)', 'Ravi', 'Guest Instructor', 'Neha Suresh', 'Anjali', 'Karthik']
        request = self._req('post', '/api/batches/', {
            'name': 'Robotics — co-taught batch', 'course': self.course.id, 'total_classes': 24,
            'fee_per_student': '4000', 'payment_type': 'one_time', 'start_date': '2026-08-01',
            'class_time': '17:00', 'class_days': 'MON,WED',
            'trainer_names': ', '.join(names),
        })
        response = BatchViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 201, response.data)
        # validate_trainer_names strips stray whitespace around each comma-separated entry.
        self.assertEqual(response.data['trainer_names'], ','.join(names))


class BatchImportTests(APITestCase):
    """Bulk-enrolling students into a batch from an Excel export of a Google Form's
    responses (ad-driven batch sign-ups) — see services.import_students_from_excel."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='import_admin', password='x', is_staff=True)
        self.factory = APIRequestFactory()
        self.batch = _make_batch(payment_type='two_installments', fee=Decimal('4000'))

    def _make_excel(self, rows, headers=None):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(headers or ['Name', 'Phone Number', 'Occupation', 'Email', 'How did you know about us?', 'Payment Status'])
        for row in rows:
            sheet.append(row)
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            'import.xlsx', buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _import(self, batch_id, file_obj):
        request = self.factory.post(f'/api/batches/{batch_id}/import_students/', {'file': file_obj}, format='multipart')
        force_authenticate(request, user=self.admin)
        return BatchViewSet.as_view({'post': 'import_students'})(request, pk=batch_id)

    def test_import_creates_guest_enrollments_never_a_student_record(self):
        file_obj = self._make_excel([
            ['Asha Kumar', '9876543210', 'Engineer', 'asha@example.com', 'Instagram ad', 'Paid'],
            ['Vikram Rao', '9123456789', '', '', 'Referral', ''],
        ])
        response = self._import(self.batch.id, file_obj)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['enrolled'], 2)
        self.assertEqual(response.data['marked_paid'], 1)
        self.assertEqual(response.data['skipped'], [])

        self.assertEqual(Student.objects.count(), 0)

        enrollment = BatchEnrollment.objects.get(batch=self.batch, guest_name='Asha Kumar')
        self.assertIsNone(enrollment.student)
        self.assertEqual(enrollment.display_name, 'Asha Kumar')
        self.assertEqual(enrollment.guest_occupation, 'Engineer')
        self.assertEqual(enrollment.guest_source, 'Instagram ad')
        installments = list(enrollment.installments.order_by('sequence'))
        self.assertEqual(installments[0].paid_status, 'paid')
        self.assertEqual(installments[1].paid_status, 'pending')

        vikram_enrollment = BatchEnrollment.objects.get(batch=self.batch, guest_name='Vikram Rao')
        self.assertIsNone(vikram_enrollment.student)
        self.assertEqual(
            list(vikram_enrollment.installments.order_by('sequence').values_list('paid_status', flat=True)),
            ['pending', 'pending'],
        )

    def test_import_does_not_link_an_existing_registered_student(self):
        # Even if someone with this exact name + phone is already a registered
        # student, import must still create a guest row, never link/reuse them.
        Student.objects.create(name='Asha Kumar', grade='6', parent_phone_number='98765 43210', source_type='B2C')
        file_obj = self._make_excel([['Asha Kumar', '9876543210', '', '', '', '']])
        response = self._import(self.batch.id, file_obj)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['enrolled'], 1)
        self.assertEqual(Student.objects.count(), 1)
        enrollment = BatchEnrollment.objects.get(batch=self.batch)
        self.assertIsNone(enrollment.student)
        self.assertEqual(enrollment.guest_name, 'Asha Kumar')

    def test_import_skips_row_missing_name(self):
        file_obj = self._make_excel([['', '9876543210', '', '', '', '']])
        response = self._import(self.batch.id, file_obj)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['enrolled'], 0)
        self.assertEqual(len(response.data['skipped']), 1)
        self.assertIn('Name is required', response.data['skipped'][0]['reason'])

    def test_import_skips_duplicate_row_within_batch(self):
        file_obj = self._make_excel([
            ['Repeat Kid', '9000000000', '', '', '', ''],
            ['Repeat Kid', '9000000000', '', '', '', ''],
        ])
        response = self._import(self.batch.id, file_obj)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['enrolled'], 1)
        self.assertEqual(len(response.data['skipped']), 1)
        self.assertIn('already enrolled', response.data['skipped'][0]['reason'])

    def test_import_rejects_file_missing_name_column(self):
        file_obj = self._make_excel([['x']], headers=['Random Column'])
        response = self._import(self.batch.id, file_obj)
        self.assertEqual(response.status_code, 400)

    def test_import_template_download(self):
        request = self.factory.get('/api/batches/import_template/')
        force_authenticate(request, user=self.admin)
        response = BatchViewSet.as_view({'get': 'import_template'})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )


class BatchEnrollmentEditingTests(APITestCase):
    """PATCH/DELETE on an enrollment, plus undoing a withdraw — previously the only
    ways to touch an existing enrollment were create/withdraw."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='edit_admin', password='x', is_staff=True)
        self.factory = APIRequestFactory()
        self.batch = _make_batch(payment_type='one_time')

    def _req(self, method, path, data=None):
        request = getattr(self.factory, method)(path, data, format='json')
        force_authenticate(request, user=self.admin)
        return request

    def test_patch_updates_guest_fields(self):
        enrollment = BatchEnrollment.objects.create(
            batch=self.batch, guest_name='Typo Kid', guest_phone_number='9000000000',
            joined_date=datetime.date(2026, 7, 1),
        )
        request = self._req('patch', f'/api/batch-enrollments/{enrollment.id}/', {'guest_name': 'Fixed Kid'})
        response = BatchEnrollmentViewSet.as_view({'patch': 'partial_update'})(request, pk=enrollment.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['guest_name'], 'Fixed Kid')
        self.assertEqual(response.data['student_name'], 'Fixed Kid')

    def test_patch_cannot_reassign_batch_or_student(self):
        other_batch = _make_batch(payment_type='one_time')
        enrollment = BatchEnrollment.objects.create(
            batch=self.batch, guest_name='Kid', joined_date=datetime.date(2026, 7, 1),
        )
        request = self._req('patch', f'/api/batch-enrollments/{enrollment.id}/', {'batch': other_batch.id})
        response = BatchEnrollmentViewSet.as_view({'patch': 'partial_update'})(request, pk=enrollment.id)
        self.assertEqual(response.status_code, 400)

    def test_delete_removes_enrollment(self):
        enrollment = BatchEnrollment.objects.create(
            batch=self.batch, guest_name='Kid', joined_date=datetime.date(2026, 7, 1),
        )
        create_batch_installments(enrollment)
        request = self.factory.delete(f'/api/batch-enrollments/{enrollment.id}/')
        force_authenticate(request, user=self.admin)
        response = BatchEnrollmentViewSet.as_view({'delete': 'destroy'})(request, pk=enrollment.id)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(BatchEnrollment.objects.filter(id=enrollment.id).exists())

    def test_reactivate_undoes_withdraw(self):
        batch = _make_batch(payment_type='two_installments')
        enrollment = BatchEnrollment.objects.create(
            batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1),
        )
        create_batch_installments(enrollment)

        withdraw_req = self._req('post', f'/api/batch-enrollments/{enrollment.id}/withdraw/', {})
        BatchEnrollmentViewSet.as_view({'post': 'withdraw'})(withdraw_req, pk=enrollment.id)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, 'withdrawn')
        self.assertTrue(enrollment.installments.filter(paid_status='cancelled').exists())

        reactivate_req = self._req('post', f'/api/batch-enrollments/{enrollment.id}/reactivate/', {})
        response = BatchEnrollmentViewSet.as_view({'post': 'reactivate'})(reactivate_req, pk=enrollment.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'active')
        statuses = set(enrollment.installments.values_list('paid_status', flat=True))
        self.assertEqual(statuses, {'pending'})


class BatchLockedFieldsTests(APITestCase):
    """fee_per_student/payment_type must lock once a batch has enrollments — existing
    installments are never recalculated (see services.create_batch_installments)."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='lock_admin', password='x', is_staff=True)
        self.factory = APIRequestFactory()

    def _patch(self, batch_id, data):
        request = self.factory.patch(f'/api/batches/{batch_id}/', data, format='json')
        force_authenticate(request, user=self.admin)
        return BatchViewSet.as_view({'patch': 'partial_update'})(request, pk=batch_id)

    def test_cannot_change_fee_once_enrolled(self):
        batch = _make_batch(payment_type='one_time', fee=Decimal('4000'))
        BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        response = self._patch(batch.id, {'fee_per_student': '5000'})
        self.assertEqual(response.status_code, 400)
        batch.refresh_from_db()
        self.assertEqual(batch.fee_per_student, Decimal('4000.00'))

    def test_cannot_change_payment_type_once_enrolled(self):
        batch = _make_batch(payment_type='one_time')
        BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        response = self._patch(batch.id, {'payment_type': 'two_installments'})
        self.assertEqual(response.status_code, 400)

    def test_can_still_change_fee_before_any_enrollment(self):
        batch = _make_batch(payment_type='one_time', fee=Decimal('4000'))
        response = self._patch(batch.id, {'fee_per_student': '5000'})
        self.assertEqual(response.status_code, 200, response.data)

    def test_can_still_change_other_fields_once_enrolled(self):
        batch = _make_batch(payment_type='one_time')
        BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        response = self._patch(batch.id, {'status': 'completed'})
        self.assertEqual(response.status_code, 200, response.data)


class BatchRefundAndInstallmentEditTests(APITestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='refund_admin', password='x', is_staff=True)
        self.factory = APIRequestFactory()

    def _req(self, method, path, data=None):
        request = getattr(self.factory, method)(path, data, format='json')
        force_authenticate(request, user=self.admin)
        return request

    def test_withdraw_with_refund_reduces_collected(self):
        batch = _make_batch(payment_type='one_time', fee=Decimal('4000'))
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        installment = create_batch_installments(enrollment)[0]
        installment.paid_status = 'paid'
        installment.save()

        request = self._req(
            'post', f'/api/batch-enrollments/{enrollment.id}/withdraw/',
            {'refund_amount': '4000', 'refund_note': 'Full refund, moved cities'},
        )
        response = BatchEnrollmentViewSet.as_view({'post': 'withdraw'})(request, pk=enrollment.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Decimal(response.data['refunded_amount']), Decimal('4000.00'))

        summary = batch_revenue_summary(batch)
        self.assertEqual(summary['collected'], Decimal('0.00'))
        self.assertEqual(summary['total_refunded'], Decimal('4000.00'))

    def test_withdraw_without_refund_leaves_collected_untouched(self):
        # Money genuinely collected before withdrawal stays counted as revenue unless
        # explicitly refunded.
        batch = _make_batch(payment_type='one_time', fee=Decimal('4000'))
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        installment = create_batch_installments(enrollment)[0]
        installment.paid_status = 'paid'
        installment.save()

        request = self._req('post', f'/api/batch-enrollments/{enrollment.id}/withdraw/', {})
        BatchEnrollmentViewSet.as_view({'post': 'withdraw'})(request, pk=enrollment.id)

        summary = batch_revenue_summary(batch)
        self.assertEqual(summary['collected'], Decimal('4000.00'))

    def test_patch_pending_installment_amount(self):
        batch = _make_batch(payment_type='one_time', fee=Decimal('4000'))
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        installment = create_batch_installments(enrollment)[0]

        request = self._req('patch', f'/api/batch-installments/{installment.id}/', {'amount': '3500'})
        response = BatchInstallmentViewSet.as_view({'patch': 'partial_update'})(request, pk=installment.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Decimal(response.data['amount']), Decimal('3500.00'))

    def test_cannot_patch_amount_of_paid_installment(self):
        batch = _make_batch(payment_type='one_time', fee=Decimal('4000'))
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        installment = create_batch_installments(enrollment)[0]
        installment.paid_status = 'paid'
        installment.save()

        request = self._req('patch', f'/api/batch-installments/{installment.id}/', {'amount': '1000'})
        response = BatchInstallmentViewSet.as_view({'patch': 'partial_update'})(request, pk=installment.id)
        self.assertEqual(response.status_code, 400)


class AllBatchesSummaryPerformanceTests(TestCase):
    def test_query_count_does_not_scale_with_batch_count(self):
        for i in range(8):
            batch = _make_batch(payment_type='two_installments', fee=Decimal('4000'))
            enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(f'Kid {i}'), joined_date=datetime.date(2026, 7, 1))
            create_batch_installments(enrollment)

        with CaptureQueriesContext(connection) as ctx:
            summary = all_batches_summary()
        self.assertEqual(summary['batch_count'], 8)
        # A handful of aggregate queries total, not ~4-5 per batch.
        self.assertLess(len(ctx), 10)


class BatchDeleteTests(APITestCase):
    def test_delete_batch_is_blocked(self):
        admin = get_user_model().objects.create_user(username='delete_admin', password='x', is_staff=True)
        factory = APIRequestFactory()
        batch = _make_batch(payment_type='one_time')
        request = factory.delete(f'/api/batches/{batch.id}/')
        force_authenticate(request, user=admin)
        response = BatchViewSet.as_view({'delete': 'destroy'})(request, pk=batch.id)
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Batch.objects.filter(id=batch.id).exists())


class SourceReportTests(TestCase):
    def test_source_report_aggregates_guest_enrollments_by_source(self):
        batch = _make_batch(payment_type='one_time', fee=Decimal('4000'))
        e1 = BatchEnrollment.objects.create(batch=batch, guest_name='A', guest_source='Instagram ad', joined_date=datetime.date(2026, 7, 1))
        create_batch_installments(e1)
        e2 = BatchEnrollment.objects.create(batch=batch, guest_name='B', guest_source='Instagram ad', joined_date=datetime.date(2026, 7, 1))
        inst2 = create_batch_installments(e2)[0]
        inst2.paid_status = 'paid'
        inst2.save()
        e3 = BatchEnrollment.objects.create(batch=batch, guest_name='C', guest_source='Referral', joined_date=datetime.date(2026, 7, 1))
        create_batch_installments(e3)
        # A registered-student add has no source at all — grouped separately.
        e4 = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        create_batch_installments(e4)

        report = {row['source']: row for row in source_report()}
        self.assertEqual(report['Instagram ad']['enrolled_count'], 2)
        self.assertEqual(report['Instagram ad']['collected'], Decimal('4000.00'))
        self.assertEqual(report['Instagram ad']['pending'], Decimal('4000.00'))
        self.assertEqual(report['Referral']['enrolled_count'], 1)
        # A registered-student add (e4) has no guest_source at all — never appears
        # under a named source, and source_report() only looks at guest rows anyway.
        self.assertEqual(set(report), {'Instagram ad', 'Referral'})


class ConvertGuestToStudentTests(APITestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='convert_admin', password='x', is_staff=True)
        self.factory = APIRequestFactory()

    def test_converts_guest_to_registered_student(self):
        batch = _make_batch(payment_type='one_time')
        enrollment = BatchEnrollment.objects.create(
            batch=batch, guest_name='Future Regular', guest_phone_number='9123456789',
            joined_date=datetime.date(2026, 7, 1),
        )
        request = self.factory.post(f'/api/batch-enrollments/{enrollment.id}/convert_to_student/', {}, format='json')
        force_authenticate(request, user=self.admin)
        response = BatchEnrollmentViewSet.as_view({'post': 'convert_to_student'})(request, pk=enrollment.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNotNone(response.data['student'])
        self.assertFalse(response.data['is_guest'])

        enrollment.refresh_from_db()
        self.assertIsNotNone(enrollment.student)
        self.assertEqual(enrollment.student.name, 'Future Regular')
        self.assertEqual(enrollment.student.parent_phone_number, '9123456789')
        self.assertEqual(enrollment.student.source_type, 'B2C')

    def test_cannot_convert_an_already_registered_enrollment(self):
        batch = _make_batch(payment_type='one_time')
        enrollment = BatchEnrollment.objects.create(batch=batch, student=_make_student(), joined_date=datetime.date(2026, 7, 1))
        request = self.factory.post(f'/api/batch-enrollments/{enrollment.id}/convert_to_student/', {}, format='json')
        force_authenticate(request, user=self.admin)
        response = BatchEnrollmentViewSet.as_view({'post': 'convert_to_student'})(request, pk=enrollment.id)
        self.assertEqual(response.status_code, 400)


class ExportStudentsTests(APITestCase):
    def test_export_returns_xlsx_with_roster(self):
        admin = get_user_model().objects.create_user(username='export_admin', password='x', is_staff=True)
        factory = APIRequestFactory()
        batch = _make_batch(payment_type='one_time', fee=Decimal('4000'))
        enrollment = BatchEnrollment.objects.create(
            batch=batch, guest_name='Exportable Kid', guest_phone_number='9000000001',
            joined_date=datetime.date(2026, 7, 1),
        )
        create_batch_installments(enrollment)

        request = factory.get(f'/api/batches/{batch.id}/export_students/')
        force_authenticate(request, user=admin)
        response = BatchViewSet.as_view({'get': 'export_students'})(request, pk=batch.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        workbook = load_workbook(BytesIO(b''.join(response.streaming_content) if response.streaming else response.content))
        rows = list(workbook.active.iter_rows(values_only=True))
        self.assertEqual(rows[0][0], 'Name')
        self.assertEqual(rows[1][0], 'Exportable Kid')


class AcceptingEnrollmentsTests(APITestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='closed_admin', password='x', is_staff=True)
        self.factory = APIRequestFactory()

    def test_closed_batch_rejects_manual_add(self):
        batch = _make_batch(payment_type='one_time')
        batch.accepting_enrollments = False
        batch.save()
        request = self.factory.post('/api/batch-enrollments/', {'batch': batch.id, 'guest_name': 'Late Kid'}, format='json')
        force_authenticate(request, user=self.admin)
        response = BatchEnrollmentViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn('closed', response.data['detail'])

    def test_closed_batch_rejects_import(self):
        from batches.services import import_students_from_excel
        batch = _make_batch(payment_type='one_time')
        batch.accepting_enrollments = False
        batch.save()

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['Name', 'Phone Number', 'Occupation', 'Email', 'How did you know about us?', 'Payment Status'])
        sheet.append(['Late Kid', '9000000000', '', '', '', ''])
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)

        with self.assertRaises(ValueError):
            import_students_from_excel(batch, buffer)


class TrainerSelfServiceTests(APITestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.trainer = _make_trainer(username='priya_login', name='Priya')
        self.other_trainer = _make_trainer(username='ravi_login', name='Ravi')
        self.admin = get_user_model().objects.create_user(username='ss_admin', password='x', is_staff=True)
        self.my_batch = _make_batch(payment_type='one_time', trainer_names='Priya, Ravi')
        self.other_batch = _make_batch(payment_type='one_time', trainer_names='Ravi')

    def test_my_batches_only_lists_batches_the_trainer_is_on(self):
        request = self.factory.get('/api/my-batches/')
        force_authenticate(request, user=self.trainer.user)
        response = MyBatchesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        ids = {b['id'] for b in response.data['results']} if 'results' in response.data else {b['id'] for b in response.data}
        self.assertIn(self.my_batch.id, ids)
        self.assertNotIn(self.other_batch.id, ids)

    def test_trainer_can_log_session_for_their_own_batch(self):
        request = self.factory.post('/api/batch-sessions/', {
            'batch': self.my_batch.id, 'date': '2026-07-05', 'conducted_by_name': 'Priya',
        }, format='json')
        force_authenticate(request, user=self.trainer.user)
        response = BatchSessionViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 201, response.data)

    def test_trainer_cannot_log_session_for_a_batch_they_are_not_on(self):
        request = self.factory.post('/api/batch-sessions/', {
            'batch': self.other_batch.id, 'date': '2026-07-05', 'conducted_by_name': 'Priya',
        }, format='json')
        force_authenticate(request, user=self.trainer.user)
        response = BatchSessionViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 403)

    def test_trainer_only_sees_their_own_payouts(self):
        BatchPayout.objects.create(batch=self.my_batch, recipient_name='Priya', amount=Decimal('1000'))
        BatchPayout.objects.create(batch=self.my_batch, recipient_name='Ravi', amount=Decimal('2000'))

        request = self.factory.get(f'/api/batch-payouts/?batch={self.my_batch.id}')
        force_authenticate(request, user=self.trainer.user)
        response = BatchPayoutViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 200)
        names = {p['recipient_name'] for p in response.data['results']}
        self.assertEqual(names, {'Priya'})

    def test_trainer_cannot_create_a_payout(self):
        request = self.factory.post('/api/batch-payouts/', {
            'batch': self.my_batch.id, 'recipient_name': 'Priya', 'amount': '1000',
        }, format='json')
        force_authenticate(request, user=self.trainer.user)
        response = BatchPayoutViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 403)
