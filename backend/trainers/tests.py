import datetime
from decimal import Decimal

from django.contrib.auth import authenticate, get_user_model
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APIRequestFactory, APITestCase, force_authenticate

from attendance.models import Attendance, AttendanceRequest
from batches.models import Batch, BatchPayout
from billing.models import BillingCycle, Payout, PayoutAdjustment
from billing.services import get_or_create_cycle
from courses.models import Course
from enrollments.models import Enrollment, SubstituteAssignment
from students.models import Student

from .models import Trainer
from .views import TrainerViewSet


class TrainerSearchTests(APITestCase):
    """?search= must match name OR trainer_id OR place server-side (see
    TrainerViewSet.search_fields), so a match is found regardless of which
    page it would otherwise fall on.
    """

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_search_trainer', password='x', is_staff=True)
        self.factory = APIRequestFactory()
        user = get_user_model().objects.create_user(username='neha_search', password='x')
        self.target = Trainer.objects.create(
            user=user, name='Neha Suresh', phone_number='0000000000', place='Chennai',
            default_rate_per_class=Decimal('100'),
        )
        other_user = get_user_model().objects.create_user(username='other_search', password='x')
        Trainer.objects.create(
            user=other_user, name='Someone Else', phone_number='1111111111', place='Mumbai',
            default_rate_per_class=Decimal('100'),
        )

    def _search(self, term):
        request = self.factory.get(f'/api/trainers/?search={term}')
        force_authenticate(request, user=self.admin)
        return TrainerViewSet.as_view({'get': 'list'})(request)

    def test_search_by_name_finds_the_trainer(self):
        response = self._search('neha')
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Neha Suresh'])

    def test_search_by_place_finds_the_trainer(self):
        response = self._search('chennai')
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Neha Suresh'])

    def test_search_by_trainer_id_finds_the_trainer(self):
        response = self._search(self.target.trainer_id)
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Neha Suresh'])


class TrainerHardDeleteBlockedTests(APITestCase):
    """Trainers are only ever archived, never hard-deleted — see
    TrainerViewSet.http_method_names and the archive/unarchive actions.
    """

    def test_delete_is_not_allowed(self):
        admin = get_user_model().objects.create_user(username='admin_no_delete_trainer', password='x', is_staff=True)
        user = get_user_model().objects.create_user(username='keep_me_trainer', password='x')
        trainer = Trainer.objects.create(
            user=user, name='Keep Me', phone_number='0000000000', place='Here', default_rate_per_class=Decimal('100'),
        )
        factory = APIRequestFactory()

        request = factory.delete(f'/api/trainers/{trainer.id}/')
        force_authenticate(request, user=admin)
        response = TrainerViewSet.as_view({'delete': 'destroy'})(request, pk=trainer.id)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Trainer.objects.filter(id=trainer.id).exists())


class TrainerArchiveLoginTests(APITestCase):
    """Archiving a trainer must actually cut off their access — both blocking a
    future login attempt and immediately invalidating any session they're
    already logged in with (not just on their next login). See
    TrainerViewSet.archive/unarchive tying Trainer.status to user.is_active.
    """

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_archive_login', password='x', is_staff=True)
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_user(username='archive_me_trainer', password='pw12345')
        self.trainer = Trainer.objects.create(
            user=self.user, name='Archive Me', phone_number='0000000000', place='Here',
            default_rate_per_class=Decimal('100'),
        )

    def _archive(self):
        request = self.factory.post(f'/api/trainers/{self.trainer.id}/archive/')
        force_authenticate(request, user=self.admin)
        return TrainerViewSet.as_view({'post': 'archive'})(request, pk=self.trainer.id)

    def _unarchive(self):
        request = self.factory.post(f'/api/trainers/{self.trainer.id}/unarchive/')
        force_authenticate(request, user=self.admin)
        return TrainerViewSet.as_view({'post': 'unarchive'})(request, pk=self.trainer.id)

    def test_archiving_deactivates_the_trainers_login(self):
        response = self._archive()
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertIsNone(authenticate(username='archive_me_trainer', password='pw12345'))

    def test_unarchiving_reactivates_the_trainers_login(self):
        self._archive()
        response = self._unarchive()
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertIsNotNone(authenticate(username='archive_me_trainer', password='pw12345'))

    def test_archived_trainers_existing_token_stops_working_immediately(self):
        token = Token.objects.create(user=self.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

        # Confirm the token is good before archiving.
        response = client.get('/api/auth/me/')
        self.assertEqual(response.status_code, 200)

        self._archive()

        response = client.get('/api/auth/me/')
        self.assertEqual(response.status_code, 401)


class TrainerArchiveBlockersTests(APITestCase):
    """Archiving must be hard-blocked while a trainer still has ongoing
    batches/enrollments, pending attendance requests, or pending payouts —
    see trainers/services.get_archive_blockers and TrainerViewSet.archive/
    .archive_blockers. Each category is checked independently, then cleared
    one at a time to confirm archive only succeeds once everything's resolved.
    """

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_archive_blockers', password='x', is_staff=True)
        self.factory = APIRequestFactory()
        user = get_user_model().objects.create_user(username='blocked_trainer', password='x')
        self.trainer = Trainer.objects.create(
            user=user, name='Blocked Trainer', phone_number='0000000000', place='Here',
            default_rate_per_class=Decimal('100'),
        )
        self.course = Course.objects.create(name='Scratch Programming', total_classes=24, rate_per_class=Decimal('1000'))
        self.student = Student.objects.create(name='Kid', grade='5', source_type='B2C')

    def _archive_blockers(self):
        request = self.factory.get(f'/api/trainers/{self.trainer.id}/archive-blockers/')
        force_authenticate(request, user=self.admin)
        return TrainerViewSet.as_view({'get': 'archive_blockers'})(request, pk=self.trainer.id)

    def _archive(self):
        request = self.factory.post(f'/api/trainers/{self.trainer.id}/archive/')
        force_authenticate(request, user=self.admin)
        return TrainerViewSet.as_view({'post': 'archive'})(request, pk=self.trainer.id)

    def _settle(self):
        request = self.factory.post(f'/api/trainers/{self.trainer.id}/settle-current-cycle/')
        force_authenticate(request, user=self.admin)
        return TrainerViewSet.as_view({'post': 'settle_current_cycle'})(request, pk=self.trainer.id)

    def test_no_blockers_for_a_trainer_with_nothing_tied_to_them(self):
        response = self._archive_blockers()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            'ongoing_enrollments': [], 'ongoing_batches': [], 'pending_attendance_requests': [],
            'pending_payouts': [], 'pending_batch_payouts': [], 'active_substitute_assignments': [],
            'current_cycle_earnings': [],
        })

    def test_ongoing_enrollment_blocks_archive(self):
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, start_date=datetime.date(2026, 1, 1),
        )

        blockers = self._archive_blockers()
        self.assertEqual(len(blockers.data['ongoing_enrollments']), 1)
        self.assertEqual(blockers.data['ongoing_enrollments'][0]['id'], enrollment.id)

        response = self._archive()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(response.data['blockers']['ongoing_enrollments']), 1)
        self.trainer.refresh_from_db()
        self.assertEqual(self.trainer.status, 'active')

        # Completing (or withdrawing/transferring away) the enrollment clears it.
        enrollment.status = 'completed'
        enrollment.save(update_fields=['status'])
        self.assertEqual(self._archive_blockers().data['ongoing_enrollments'], [])
        self.assertEqual(self._archive().status_code, 200)

    def test_ongoing_batch_blocks_archive(self):
        batch = Batch.objects.create(
            name='Scratch — July batch', course=self.course, total_classes=24, fee_per_student=Decimal('4000'),
            start_date=datetime.date(2026, 7, 1), trainer_names=self.trainer.name,
        )

        blockers = self._archive_blockers()
        self.assertEqual(len(blockers.data['ongoing_batches']), 1)
        self.assertEqual(blockers.data['ongoing_batches'][0]['id'], batch.id)

        response = self._archive()
        self.assertEqual(response.status_code, 400)

        # Removing the trainer from the batch (or completing the batch) clears it.
        batch.trainer_names = ''
        batch.save(update_fields=['trainer_names'])
        self.assertEqual(self._archive_blockers().data['ongoing_batches'], [])
        self.assertEqual(self._archive().status_code, 200)

    def test_pending_attendance_request_blocks_archive(self):
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, start_date=datetime.date(2026, 1, 1),
            status='completed',
        )
        req = AttendanceRequest.objects.create(enrollment=enrollment, date=datetime.date(2026, 1, 5), requested_by=self.trainer)

        blockers = self._archive_blockers()
        self.assertEqual(len(blockers.data['pending_attendance_requests']), 1)
        self.assertEqual(blockers.data['pending_attendance_requests'][0]['id'], req.id)

        response = self._archive()
        self.assertEqual(response.status_code, 400)

        req.status = 'denied'
        req.save(update_fields=['status'])
        self.assertEqual(self._archive_blockers().data['pending_attendance_requests'], [])
        self.assertEqual(self._archive().status_code, 200)

    def test_pending_payout_blocks_archive(self):
        cycle = BillingCycle.objects.create(
            cycle_start=datetime.date(2026, 1, 1), cycle_end=datetime.date(2026, 1, 15), status='closed',
        )
        payout = Payout.objects.create(trainer=self.trainer, cycle=cycle, total_classes=5, total_amount=Decimal('500.00'))

        blockers = self._archive_blockers()
        self.assertEqual(len(blockers.data['pending_payouts']), 1)
        self.assertEqual(blockers.data['pending_payouts'][0]['id'], payout.id)

        response = self._archive()
        self.assertEqual(response.status_code, 400)

        payout.paid_status = 'paid'
        payout.save(update_fields=['paid_status'])
        self.assertEqual(self._archive_blockers().data['pending_payouts'], [])
        self.assertEqual(self._archive().status_code, 200)

    def test_pending_batch_payout_blocks_archive(self):
        batch = Batch.objects.create(
            name='Scratch — July batch', course=self.course, total_classes=24, fee_per_student=Decimal('4000'),
            start_date=datetime.date(2026, 7, 1),
        )
        payout = BatchPayout.objects.create(batch=batch, recipient_name=self.trainer.name, amount=Decimal('1000'))

        blockers = self._archive_blockers()
        self.assertEqual(len(blockers.data['pending_batch_payouts']), 1)
        self.assertEqual(blockers.data['pending_batch_payouts'][0]['id'], payout.id)

        response = self._archive()
        self.assertEqual(response.status_code, 400)

        payout.paid_status = 'cancelled'
        payout.save(update_fields=['paid_status'])
        self.assertEqual(self._archive_blockers().data['pending_batch_payouts'], [])
        self.assertEqual(self._archive().status_code, 200)

    def test_active_substitute_coverage_blocks_archive(self):
        # A different trainer's enrollment, with self.trainer covering as a temporary
        # substitute — distinct from self.trainer's own ongoing_enrollments, which
        # never touches SubstituteAssignment at all.
        other_user = get_user_model().objects.create_user(username='other_trainer_for_substitute', password='x')
        other_trainer = Trainer.objects.create(
            user=other_user, name='Other Trainer', phone_number='0000000000', place='Here',
            default_rate_per_class=Decimal('100'),
        )
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=other_trainer, start_date=datetime.date(2026, 1, 1),
        )
        today = timezone.now().date()
        assignment = SubstituteAssignment.objects.create(
            enrollment=enrollment, substitute_trainer=self.trainer,
            start_date=today - datetime.timedelta(days=2), end_date=today + datetime.timedelta(days=5),
        )

        blockers = self._archive_blockers()
        self.assertEqual(len(blockers.data['active_substitute_assignments']), 1)
        self.assertEqual(blockers.data['active_substitute_assignments'][0]['id'], assignment.id)

        response = self._archive()
        self.assertEqual(response.status_code, 400)

        # Cancelling the coverage early (the existing SubstituteAssignmentViewSet
        # DELETE action) clears it.
        assignment.delete()
        self.assertEqual(self._archive_blockers().data['active_substitute_assignments'], [])
        self.assertEqual(self._archive().status_code, 200)

    def test_substitute_coverage_that_already_ended_never_blocks(self):
        other_user = get_user_model().objects.create_user(username='other_trainer_ended_substitute', password='x')
        other_trainer = Trainer.objects.create(
            user=other_user, name='Other Trainer 2', phone_number='0000000000', place='Here',
            default_rate_per_class=Decimal('100'),
        )
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=other_trainer, start_date=datetime.date(2026, 1, 1),
        )
        today = timezone.now().date()
        SubstituteAssignment.objects.create(
            enrollment=enrollment, substitute_trainer=self.trainer,
            start_date=today - datetime.timedelta(days=30), end_date=today - datetime.timedelta(days=20),
        )
        self.assertEqual(self._archive_blockers().data['active_substitute_assignments'], [])
        self.assertEqual(self._archive().status_code, 200)

    def test_current_cycle_regular_attendance_blocks_archive(self):
        # Real, already-earned money that isn't a Payout row yet — those only get
        # created when the shared cycle formally closes for everyone at once (see
        # calculate_payouts_for_cycle), so pending_payouts alone can't see this.
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, start_date=datetime.date(2026, 1, 1),
            status='completed',
        )
        today = timezone.now().date()
        Attendance.objects.create(enrollment=enrollment, date=today, status='present', marked_by=self.trainer)

        blockers = self._archive_blockers()
        self.assertEqual(len(blockers.data['current_cycle_earnings']), 1)
        self.assertGreater(Decimal(str(blockers.data['current_cycle_earnings'][0]['total_amount'])), 0)

        response = self._archive()
        self.assertEqual(response.status_code, 400)

        # Settling materializes a real, immediately-payable Payout for just this
        # trainer's still-open cycle, without touching anyone else's.
        settle_request = self.factory.post(f'/api/trainers/{self.trainer.id}/settle-current-cycle/')
        force_authenticate(settle_request, user=self.admin)
        settle_response = TrainerViewSet.as_view({'post': 'settle_current_cycle'})(settle_request, pk=self.trainer.id)
        self.assertEqual(settle_response.status_code, 200, settle_response.data)
        self.assertEqual(settle_response.data['paid_status'], 'pending')

        self.assertEqual(self._archive_blockers().data['current_cycle_earnings'], [])
        self.assertEqual(len(self._archive_blockers().data['pending_payouts']), 1)

        # Still blocked — the newly-settled payout is itself pending, same as any
        # other pending payout, until it's marked paid.
        self.assertEqual(self._archive().status_code, 400)

        Payout.objects.filter(id=settle_response.data['id']).update(paid_status='paid')
        self.assertEqual(self._archive().status_code, 200)

    def test_settling_with_nothing_to_settle_is_rejected(self):
        settle_request = self.factory.post(f'/api/trainers/{self.trainer.id}/settle-current-cycle/')
        force_authenticate(settle_request, user=self.admin)
        response = TrainerViewSet.as_view({'post': 'settle_current_cycle'})(settle_request, pk=self.trainer.id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payout.objects.filter(trainer=self.trainer).count(), 0)

    def test_current_cycle_earnings_reblocks_if_more_accrues_after_a_pending_settle(self):
        # Real regression: settle once, then something else (e.g. approving another
        # attendance request) adds more to this same still-open cycle before archive
        # actually happens — the already-settled-but-still-pending Payout must not
        # silently under-report the new total.
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, start_date=datetime.date(2026, 1, 1),
            status='completed',
        )
        today = timezone.now().date()
        Attendance.objects.create(enrollment=enrollment, date=today, status='present', marked_by=self.trainer)

        first = self._settle()
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data['total_classes'], 1)
        self.assertEqual(self._archive_blockers().data['current_cycle_earnings'], [])

        # More attendance for the same trainer, same still-open cycle.
        enrollment2 = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, start_date=datetime.date(2026, 1, 1),
            status='completed', batch_number=2,
        )
        Attendance.objects.create(enrollment=enrollment2, date=today, status='present', marked_by=self.trainer)

        blockers = self._archive_blockers()
        self.assertEqual(len(blockers.data['current_cycle_earnings']), 1)
        self.assertEqual(blockers.data['current_cycle_earnings'][0]['total_classes'], 2)
        self.assertEqual(self._archive().status_code, 400)

        # Re-settling (still pending) safely refreshes the same Payout row, not a
        # second one, to the new total.
        second = self._settle()
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data['id'], first.data['id'])
        self.assertEqual(second.data['total_classes'], 2)
        self.assertEqual(Payout.objects.filter(trainer=self.trainer).count(), 1)
        self.assertEqual(self._archive_blockers().data['current_cycle_earnings'], [])

    def test_settling_again_after_already_paid_is_refused_if_amount_changed(self):
        # The dangerous case: the settled Payout was already marked paid, then more
        # accrued for the same cycle before archive happened. Silently bumping an
        # already-paid amount would misrepresent what was actually paid out — this
        # must refuse instead of quietly rewriting it.
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, start_date=datetime.date(2026, 1, 1),
            status='completed',
        )
        today = timezone.now().date()
        Attendance.objects.create(enrollment=enrollment, date=today, status='present', marked_by=self.trainer)

        settled = self._settle()
        self.assertEqual(settled.status_code, 200, settled.data)
        payout_id = settled.data['id']
        original_amount = settled.data['total_amount']
        Payout.objects.filter(id=payout_id).update(paid_status='paid')

        enrollment2 = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, start_date=datetime.date(2026, 1, 1),
            status='completed', batch_number=2,
        )
        Attendance.objects.create(enrollment=enrollment2, date=today, status='present', marked_by=self.trainer)

        self.assertEqual(len(self._archive_blockers().data['current_cycle_earnings']), 1)
        self.assertEqual(self._archive().status_code, 400)

        response = self._settle()
        self.assertEqual(response.status_code, 400)
        self.assertIn('already marked paid', response.data['detail'])

        payout = Payout.objects.get(id=payout_id)
        self.assertEqual(payout.paid_status, 'paid')
        self.assertEqual(str(payout.total_amount), original_amount)

    def test_carried_forward_payout_adjustment_blocks_archive_via_current_cycle(self):
        # Mirrors the exact real-world scenario: a trainer's attendance request for a
        # date in an already-closed cycle gets approved (see
        # AttendanceRequestViewSet.approve), crediting a PayoutAdjustment to their
        # current, still-open cycle rather than the closed one. That money must not
        # be silently archivable-away just because it isn't a real Payout row yet.
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, start_date=datetime.date(2026, 1, 1),
            status='completed',
        )
        closed_cycle = BillingCycle.objects.create(
            cycle_start=datetime.date(2026, 1, 1), cycle_end=datetime.date(2026, 1, 15), status='closed',
        )
        current_cycle, _ = get_or_create_cycle()
        attendance = Attendance.objects.create(
            enrollment=enrollment, date=datetime.date(2026, 1, 5), status='present', marked_by=self.trainer,
        )
        PayoutAdjustment.objects.create(
            trainer=self.trainer, attendance=attendance, source_cycle=closed_cycle,
            amount=Decimal('300.00'), applied_cycle=current_cycle,
        )

        blockers = self._archive_blockers()
        self.assertEqual(len(blockers.data['current_cycle_earnings']), 1)
        self.assertEqual(blockers.data['current_cycle_earnings'][0]['carried_forward_count'], 1)
        self.assertEqual(Decimal(str(blockers.data['current_cycle_earnings'][0]['carried_forward_amount'])), Decimal('300.00'))

        self.assertEqual(self._archive().status_code, 400)

    def test_completed_and_withdrawn_enrollments_never_block(self):
        Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, start_date=datetime.date(2026, 1, 1),
            status='completed',
        )
        Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, start_date=datetime.date(2026, 1, 1),
            status='withdrawn', batch_number=2,
        )
        self.assertEqual(self._archive_blockers().data['ongoing_enrollments'], [])
        self.assertEqual(self._archive().status_code, 200)

    def test_non_admin_cannot_view_archive_blockers(self):
        request = self.factory.get(f'/api/trainers/{self.trainer.id}/archive-blockers/')
        force_authenticate(request, user=self.trainer.user)
        response = TrainerViewSet.as_view({'get': 'archive_blockers'})(request, pk=self.trainer.id)
        self.assertEqual(response.status_code, 403)
